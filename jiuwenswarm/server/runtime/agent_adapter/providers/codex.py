"""Direct Codex main-agent adapter; Swarm owns scheduling, controls and history."""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import hashlib
import json
import logging
import time
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk
from jiuwenswarm.common.schema.message import ReqMethod
from .codex_config import availability, config_snapshot, model_overrides, resolve_model
from .subagent_projection import SubagentProjection
from . import session_recovery as recovery
from ..execution_input import AdapterCapabilities


_CANCEL_TIMEOUT = 15
_TOOL_OUTPUT_CHAR_LIMIT = 60000
_ACTIVITY_CHAR_LIMIT = 2000


def _bounded_output(text: str, limit: int) -> tuple[str, dict]:
    """Bound the Swarm projection, leaving the native tool/model context intact."""
    if len(text) <= limit:
        return text, {}
    received_bytes = len(text.encode("utf-8"))
    marker = (f"\n[Output truncated by Swarm; SDK returned {len(text)} characters / "
              f"{received_bytes} UTF-8 bytes.]")
    displayed = text[:limit - len(marker)] + marker
    return displayed, {
        "output_truncated": True,
        "received_output_chars": len(text),
        "received_output_bytes": received_bytes,
        "displayed_output_chars": len(displayed),
        "displayed_output_bytes": len(displayed.encode("utf-8")),
    }


class _Terminal(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    itemId: str
    processId: str


class _Terminals(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    data: list[_Terminal]
    nextCursor: str | None


class _Terminated(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    terminated: bool


@dataclass
class Session:
    directory: str
    root: Path
    swarm_id: str = ""
    client: Any = None
    thread_id: str = ""
    turn_id: str = ""
    model_revision: str = ""
    active: bool = False
    cancelled: bool = False
    cancel_acknowledged: bool = False
    cancel_confirmed: bool = False
    command_ids: set[str] = field(default_factory=set)
    turn_ready: asyncio.Event = field(default_factory=asyncio.Event)
    turn_ended: asyncio.Event = field(default_factory=asyncio.Event)
    native_terminal: bool = False
    cancel_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    effective_permission: str | None = None
    desired_permission: str = "default"
    pending: dict = field(default_factory=dict)
    control_ready: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    subagents: SubagentProjection | None = None


def command_result(item: dict) -> dict:
    code = item.get("exitCode")
    code = code if type(code) is int else None
    native_status = item.get("status")
    output = item.get("aggregatedOutput") or ("Command was not executed: permission declined" if native_status == "declined" else "")
    output, projection = _bounded_output(output, _TOOL_OUTPUT_CHAR_LIMIT)
    result = {"event_type": "chat.tool_result", "tool_call_id": item["id"],
            "tool_name": "shell", "content": output,
            "result": output, "status": "error" if native_status == "declined" else native_status,
            "invocation_status": item.get("status"), "exit_code": code,
            "command_success": code == 0 if code is not None else None,
            "success": code == 0 if code is not None else None, "task_acceptance": "unknown"}
    if projection:
        result["provider"] = {"codex": projection}
    return result


class CodexAdapter:
    capabilities = AdapterCapabilities(native_resume=True)
    permission_profiles = ("default", "full_access")
    supports_native_model_forks = False
    supports_native_plan_state = False

    def __init__(self, *, mode="agent"):
        self._validate_mode(mode)
        self._sessions: dict[str, Session] = {}
        self._settings = None
        self._permission_profile = "default"

    @staticmethod
    def _validate_mode(mode):
        from gateway.common.mode_matrix import deprecate_mode, NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL
        if deprecate_mode(mode) not in {NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL}:
            raise ValueError("Codex supports single Agent/code only")

    @staticmethod
    def _profile(config):
        permissions = config.get("permissions") or {}
        if permissions.get("enabled") is False:
            return "full_access"
        if permissions.get("mode") == "auto":
            raise ValueError("Codex Automatic permissions are not supported; select Default or Full Access")
        return "default"

    async def create_instance(self, config=None, *, mode="agent", sub_mode=None):
        from jiuwenswarm.common.config import get_config
        self._validate_mode(mode)
        if sub_mode not in {None, "normal"} or (config or {}).get("run_permissions_enabled"):
            raise ValueError("Codex does not support Native run permissions or this sub-mode")
        if self._settings is not None:
            raise ValueError("Codex adapter is already configured")
        root = get_config()
        settings = (config or {}).get("codex", config_snapshot(root)["codex"])
        if not settings.get("enabled"):
            raise ValueError("Enable Codex in Third-party Agents first")
        import importlib.metadata
        try:
            importlib.metadata.version("openai-codex")
        except importlib.metadata.PackageNotFoundError:
            raise ValueError("Install the codex-direct optional dependency (official Codex SDK)") from None
        self._permission_profile = self._profile(config if config and "permissions" in config else root)
        settings = dict(settings)
        if settings.get("cli_path"):
            from jiuwenswarm.common.windows_cli_paths import resolve_preserved_cli_path
            from .cli import resolve_cli
            settings["cli_path"] = resolve_cli("codex", explicit=resolve_preserved_cli_path(settings["cli_path"]))
        self._settings = settings

    def build_query(self, request, turn):
        if request.params.get("answers"):
            return "", turn
        if not isinstance(turn.text, str):
            raise ValueError("Codex currently accepts text input only")
        if any(request.params.get(key) for key in ("files", "team", "run", "cron", "moa_enabled", "skills", "plugin_names", "agent_template_name")):
            raise ValueError("Codex main-agent pilot does not support this equipment or mode yet")
        rendered = turn.render()
        try:
            if json.loads(rendered).get("skills_to_use"):
                raise ValueError("Codex Skill selection is not supported yet")
        except (json.JSONDecodeError, AttributeError):
            pass
        return rendered, turn

    def execution_input_policy(self, request):
        from ..execution_input import ExecutionInputPolicy
        session = self._sessions.get(request.session_id or "default")
        return ExecutionInputPolicy(bound_directory=session.directory if session else None)

    async def reconcile_session_mcp(self, session_id, needed, *, execution_request=None):
        if needed:
            raise ValueError("Codex Swarm MCP equipment is not supported yet")

    async def prepare_session(self, *, session_id, channel_id, mode, project_dir=None, facts=None):
        self._validate_mode(mode)
        if self._settings is None:
            raise RuntimeError("Codex adapter has not been configured")
        from jiuwenswarm.common.utils import get_default_project_session_workspace_dir
        current = self._sessions.get(session_id)
        directory = Path(project_dir or (current.directory if current else get_default_project_session_workspace_dir())).expanduser()
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError("Codex requires an existing absolute project directory")
        directory = str(directory.resolve())
        if current:
            if directory != current.directory:
                raise ValueError("Codex session workspace cannot change after binding")
            return
        from ..execution_input import session_facts
        facts = facts or session_facts(session_id)
        binding = recovery.load("codex", session_id, directory)
        if binding:
            recovery.require_settings(binding, self._settings)
            self._sessions[session_id] = Session(directory, Path(binding["root"]), swarm_id=session_id,
                thread_id=binding["native_id"], model_revision=binding["model_revision"],
                desired_permission=binding["permission"])
            return
        if facts.has_assistant_history:
            raise ValueError("Codex cannot restore a released session without a recovery binding; its original native thread cannot be identified")
        parent = facts.storage_dir / ".codex-direct"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = Path(tempfile.mkdtemp(prefix="session-", dir=parent))
        self._sessions[session_id] = Session(directory, root, swarm_id=session_id, desired_permission=self._permission_profile)

    def _save_binding(self, session):
        if session.swarm_id and session.thread_id:
            recovery.save("codex", session.swarm_id, root=session.root, directory=session.directory,
                native_id=session.thread_id, model_revision=session.model_revision,
                settings_revision=recovery.settings_revision(self._settings), permission=session.desired_permission)

    def has_session_runtime(self, session_id=None):
        return session_id in self._sessions if session_id else bool(self._sessions)

    def is_external_harness_session(self, session_id):
        return session_id in self._sessions

    def _chunk(self, request, payload, *, complete=False, outcome=None):
        return AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
                                  payload=payload, is_complete=complete, runtime_completion=outcome)

    def _approval(self, session, loop, method, params):
        params = params or {}
        if method not in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            # Unknown permissions/tools never inherit the SDK's accept-all default.
            if method == "item/permissions/requestApproval":
                return {"permissions": {}, "scope": "turn"}
            raise ValueError("Unsupported Codex interaction")
        future = concurrent.futures.Future()
        identity = uuid.uuid4().hex

        def publish():
            if future.done():
                return
            if not session.active or session.cancelled or params.get("threadId") != session.thread_id:
                future.set_result({"decision": "cancel"})
                return
            if session.turn_id and params.get("turnId") != session.turn_id:
                future.set_result({"decision": "cancel"})
                return
            session.pending[identity] = (future, method, params)
            session.control_ready.set()

        loop.call_soon_threadsafe(publish)
        try:
            return future.result(timeout=180)
        except concurrent.futures.TimeoutError:
            future.cancel()
            loop.call_soon_threadsafe(session.pending.pop, identity, None)
            return {"decision": "cancel"}

    @staticmethod
    def _release_controls(session):
        for future, _, _ in session.pending.values():
            if not future.done():
                future.set_result({"decision": "cancel"})
        session.pending.clear()
        session.control_ready.set()

    async def _connect(self, session, model):
        from openai_codex.client import CodexClient, CodexConfig
        revision = hashlib.sha256(model.model_dump_json().encode()).hexdigest()
        if session.model_revision and revision != session.model_revision:
            raise ValueError("Codex model configuration changed; restore the original configuration before resuming")
        if session.client:
            if revision != session.model_revision:
                raise ValueError("Codex model configuration changed; create a new session")
            return
        loop = asyncio.get_running_loop()
        home = session.root / "home"
        home.mkdir(mode=0o700, exist_ok=True)
        (session.root / "codex").mkdir(mode=0o700, exist_ok=True)
        env = {"HOME": str(home), "USERPROFILE": str(home), "CODEX_HOME": str(session.root / "codex"),
               "XDG_CONFIG_HOME": str(session.root / "config"), "XDG_DATA_HOME": str(session.root / "data"),
               "XDG_CACHE_HOME": str(session.root / "cache"), "APPDATA": str(session.root / "appdata"),
               "LOCALAPPDATA": str(session.root / "localappdata"), "OPENAI_API_KEY": "", "CODEX_API_KEY": "",
               "SWARM_CODEX_MODEL_KEY": model.api_key}
        config = CodexConfig(codex_bin=self._settings.get("cli_path"), cwd=session.directory, env=env,
                             config_overrides=model_overrides(model, self._settings), client_name="swarm_agent_adapter")
        if model.client_options.get("timeout") is not None:
            logging.getLogger(__name__).info("Codex model HTTP timeout is not mapped to a Turn deadline; native stream idle policy applies")
        try:
            client = CodexClient(config, approval_handler=lambda method, params: self._approval(session, loop, method, params))
        except TypeError:
            raise RuntimeError("The installed Codex SDK does not support Swarm's required client/approval interface") from None
        try:
            await asyncio.to_thread(client.start)
            await asyncio.wait_for(asyncio.to_thread(client.initialize), 30)
            options = {
                "cwd": session.directory, "model": model.model_name, "modelProvider": "swarm",
                **self._permission_options(session.desired_permission),
            }
            if session.thread_id:
                response = await asyncio.wait_for(asyncio.to_thread(client.thread_resume, session.thread_id, options), 30)
                if response.thread.id != session.thread_id:
                    raise ValueError("Codex resumed a different thread")
                native = response.thread.model_dump(mode="json", by_alias=True)
                if Path(native["cwd"]).resolve() != Path(session.directory):
                    raise ValueError("Codex resumed another workspace")
                if native.get("status", {}).get("type") not in {"idle", "notLoaded"}:
                    raise ValueError("Codex native thread is not idle; recovery was not started")
            else:
                response = await asyncio.wait_for(asyncio.to_thread(client.thread_start, options), 30)
            session.thread_id = response.thread.id
            effective = response.model_dump(mode="json", by_alias=True)
            expected = self._permission_options(session.desired_permission)
            if effective.get("approvalPolicy") != expected["approvalPolicy"] or effective.get("approvalsReviewer") != "user" or effective.get("sandbox", {}).get("type") != ("dangerFullAccess" if session.desired_permission == "full_access" else "workspaceWrite"):
                raise ValueError("Codex did not confirm the requested permission policy")
        except BaseException as exc:
            self._release_controls(session)
            with contextlib.suppress(Exception):
                await asyncio.to_thread(client.close)
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                raise
            raise RuntimeError("Codex initialization failed; check the configured CLI and model service") from None
        session.client = client
        session.model_revision = revision
        session.effective_permission = session.desired_permission
        try:
            self._save_binding(session)
        except BaseException:
            await asyncio.to_thread(client.close)
            session.client = None
            raise

    @staticmethod
    def _permission_options(profile):
        if profile not in CodexAdapter.permission_profiles:
            raise ValueError("Unsupported Codex permissions")
        return {"approvalPolicy": "never" if profile == "full_access" else "on-request",
                "approvalsReviewer": "user", "sandbox": "danger-full-access" if profile == "full_access" else "workspace-write"}

    async def _collab_events(self, session, request, method, item):
        if item.get("senderThreadId") != session.thread_id:
            return
        children = session.subagents
        receivers = item.get("receiverThreadIds", [])
        tool = item.get("tool", "collaboration")
        if method == "item/started":
            yield self._chunk(request, {"event_type": "chat.tool_call", "tool_call": {
                "id": item["id"], "name": tool, "arguments": {"agents": receivers, "prompt": item.get("prompt")}}})
        if item.get("tool") == "spawnAgent":
            for native_id in receivers:
                if isinstance(native_id, str) and native_id:
                    prompt = item.get("prompt") or ""
                    children.register(native_id, prompt[:80] or native_id)
        owned = [n for n in receivers if n in children.children]
        if not owned:
            return
        results = {}
        for native_id in owned:
            state = item.get("agentsStates", {}).get(native_id, {})
            status = state.get("status")
            if method == "item/completed":
                # A public snapshot request on a proven child; no second event reader.
                async for payload in self._child_snapshot(session, native_id):
                    yield self._chunk(request, payload)
            message = state.get("message")
            if status in {"completed", "errored"} and isinstance(message, str) and message.strip():
                children.result(native_id, message, source="collabAgentToolCall.agentsStates.message")
                results[children.children[native_id]["subagent_id"]] = message
            activity = children.activity(native_id, "error" if status == "errored" else "tool_result" if method == "item/completed" else "tool_call",
                message or f"{tool}: {status or item.get('status', 'unknown')}", identity=item["id"], tool_name=tool, tool_call_id=item["id"])
            if activity:
                yield self._chunk(request, activity)
            outcome = {"completed": "completed", "errored": "failed", "interrupted": "cancelled", "shutdown": "parent_ended", "notFound": "parent_ended"}.get(status)
            yield self._chunk(request, children.roster(native_id, outcome=outcome,
                closed=status in {"shutdown", "notFound"}, native_status=status))
        if method == "item/completed":
            yield self._chunk(request, {"event_type": "chat.tool_result", "tool_call_id": item["id"],
                "tool_name": tool, "content": json.dumps({n: item.get("agentsStates", {}).get(n, {}) for n in owned}, ensure_ascii=False),
                "invocation_status": item.get("status"), "task_acceptance": "unknown",
                "tool_result": {"subagent_wait": {"results": results}}})

    async def _child_snapshot(self, session, native_id):
        children = session.subagents
        try:
            response = await asyncio.wait_for(asyncio.to_thread(session.client.thread_read, native_id, include_turns=True), 5)
            thread = response.model_dump(mode="json", by_alias=True)["thread"]
            if thread.get("id") != native_id:
                raise ValueError("Codex returned a different child thread")
        except Exception as exc:
            logging.getLogger(__name__).info("Codex child snapshot unavailable error_type=%s", type(exc).__name__)
            return
        for turn in thread.get("turns", []):
            if not turn.get("id"):
                continue
            children.register(native_id, "", task_id=turn["id"])
            final = []
            for item in turn.get("items", []):
                if item.get("type") == "commandExecution":
                    done = item.get("status") in {"completed", "failed", "declined"}
                    summary = item.get("aggregatedOutput", "") if done else item.get("command", "")
                    summary, _ = _bounded_output(summary or "", _ACTIVITY_CHAR_LIMIT)
                    activity = children.activity(native_id, "tool_result" if done else "tool_call", summary,
                        identity=item["id"], tool_name="shell", tool_call_id=item["id"],
                        ok=False if item.get("status") in {"failed", "declined"} else item["exitCode"] == 0 if type(item.get("exitCode")) is int else None)
                    if activity:
                        yield activity
                elif item.get("type") == "agentMessage" and item.get("phase") != "commentary":
                    final.append(item.get("text", ""))
            if turn.get("status") == "completed":
                children.result(native_id, "\n".join(final), source="thread.read.turns")

    async def process_message_stream_impl(self, request, inputs):
        if request.req_method not in {None, ReqMethod.CHAT_SEND} or request.params.get("answers"):
            raise ValueError("Use the active Codex control input channel")
        from ..execution_input import prepared_input
        execution = prepared_input(request, inputs)
        sid = request.session_id or "default"
        await self.prepare_session(session_id=sid, channel_id=request.channel_id,
                                   mode=request.params.get("mode", "agent"),
                                   project_dir=execution.directory if execution else inputs.get("workspace_dir") or inputs.get("project_dir") or inputs.get("cwd"),
                                   facts=execution.session if execution else None)
        session = self._sessions[sid]
        if session.subagents is None:
            session.subagents = SubagentProjection("codex", sid)
        from jiuwenswarm.common.codex_adapter_config import validate_model
        model = validate_model(execution.model) if execution else resolve_model(request)
        async with session.lock:
            if session.cancelled and not session.cancel_confirmed:
                raise RuntimeError("Codex cancellation is not confirmed; retry cancel before continuing this session")
            if session.active:
                raise ValueError("Session already has a producer; use Runtime scheduling")
            await self._connect(session, model)
            if session.desired_permission != session.effective_permission:
                # Resume the same thread with the new policy; no conversation replacement.
                try:
                    response = await asyncio.wait_for(asyncio.to_thread(
                        session.client.thread_resume, session.thread_id,
                        self._permission_options(session.desired_permission)), 30)
                except Exception:
                    raise RuntimeError("Codex permission update could not be confirmed; execution was not started") from None
                if response.thread.id != session.thread_id:
                    raise ValueError("Codex resumed a different thread")
                effective = response.model_dump(mode="json", by_alias=True)
                expected = self._permission_options(session.desired_permission)
                if effective.get("approvalPolicy") != expected["approvalPolicy"] or effective.get("approvalsReviewer") != "user" or effective.get("sandbox", {}).get("type") != ("dangerFullAccess" if session.desired_permission == "full_access" else "workspaceWrite"):
                    raise ValueError("Codex permission update was not confirmed")
                session.effective_permission = session.desired_permission
                self._save_binding(session)
            session.turn_id = ""
            session.command_ids.clear()
            session.turn_ready.clear()
            session.turn_ended.clear()
            session.native_terminal = session.cancel_confirmed = False
            session.control_ready.clear()
            session.active, session.cancelled, session.cancel_acknowledged = True, False, False
        reader = None
        terminal = False
        text_parts = {}
        started = time.monotonic()
        last_event = "none"
        try:
            response = await asyncio.to_thread(session.client.turn_start, session.thread_id, inputs["query"])
            session.turn_id = response.turn.id
            session.turn_ready.set()
            while True:
                if reader is None:
                    reader = asyncio.create_task(asyncio.to_thread(session.client.next_turn_notification, session.turn_id))
                control = asyncio.create_task(session.control_ready.wait())
                try:
                    done, _ = await asyncio.wait({reader, control}, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    control.cancel()
                    await asyncio.gather(control, return_exceptions=True)
                if session.control_ready.is_set():
                    session.control_ready.clear()
                    for identity, (future, method, params) in list(session.pending.items()):
                        if future.done():
                            continue
                        description = params.get("command") or params.get("reason") or "file change"
                        yield self._chunk(request, {"event_type": "chat.ask_user_question", "request_id": identity,
                            "source": "permission_interrupt", "questions": [{"question": "Codex: " + str(description),
                            "options": [{"label": "允许一次", "value": "allow_once"}, {"label": "拒绝", "value": "reject"}], "multiSelect": False}]})
                if reader not in done:
                    continue
                notification = reader.result()
                reader = None
                method = notification.method
                last_event = method
                payload = notification.payload.model_dump(mode="json", by_alias=True)
                item = payload.get("item", {})
                if method == "error":
                    # Native retries remain owned by Codex. Do not turn a
                    # retry notification into a second terminal event.
                    logging.getLogger(__name__).warning("Codex native error request=%s will_retry=%s elapsed=%.3fs", request.request_id, payload.get("willRetry"), time.monotonic() - started)
                if method in {"item/started", "item/completed"} and item.get("type") == "collabAgentToolCall":
                    async for projected in self._collab_events(session, request, method, item):
                        yield projected
                elif method == "item/agentMessage/delta":
                    yield self._chunk(request, {"event_type": "chat.delta", "content": payload.get("delta", "")})
                elif method == "item/started" and item.get("type") == "commandExecution":
                    session.command_ids.add(item["id"])
                    yield self._chunk(request, {"event_type": "chat.tool_call", "tool_call": {"id": item["id"], "name": "shell", "arguments": {"command": item.get("command", ""), "cwd": item.get("cwd")}}})
                elif method == "item/completed":
                    if item.get("type") == "commandExecution":
                        session.command_ids.add(item["id"])
                        yield self._chunk(request, command_result(item))
                    elif item.get("type") == "agentMessage":
                        text_parts[item["id"]] = (item.get("phase"), item.get("text", ""))
                    elif item.get("type") == "fileChange":
                        yield self._chunk(request, {"event_type": "chat.tool_call", "tool_call": {"id": item["id"], "name": "file_change", "arguments": {"changes": item.get("changes", [])}}})
                        yield self._chunk(request, {"event_type": "chat.tool_result", "tool_call_id": item["id"], "tool_name": "file_change", "content": json.dumps(item.get("changes", [])), "success": item.get("status") == "completed", "task_acceptance": "unknown"})
                elif method == "turn/completed":
                    terminal = True
                    session.native_terminal = True
                    session.turn_ended.set()
                    status = payload["turn"]["status"]
                    if status == "completed":
                        yield self._chunk(request, {"event_type": "chat.final", "content": self._final_response(text_parts), "invocation_status": status, "task_acceptance": "unknown"}, complete=True, outcome="completed")
                    else:
                        cancelled = status == "interrupted"
                        yield self._chunk(request, {"event_type": "chat.error", "code": "cancelled" if cancelled else "codex_turn_failed", "error": "Codex execution cancelled" if cancelled else "Codex model request failed; check model endpoint compatibility and authentication"}, complete=True, outcome="cancelled" if cancelled else "error")
                    return
        except TimeoutError:
            logging.getLogger(__name__).warning("Codex timeout request=%s last_event=%s elapsed=%.3fs source=native_sdk", request.request_id, last_event, time.monotonic() - started)
            yield self._chunk(request, {"event_type": "chat.error", "code": "codex_timeout", "error": "Codex native SDK operation timed out"}, complete=True, outcome="error")
        except Exception:
            yield self._chunk(request, {"event_type": "chat.error", "code": "codex_transport_failed", "error": "Codex runtime connection failed or an unsupported interaction was requested"}, complete=True, outcome="error")
        finally:
            self._release_controls(session)
            try:
                if not terminal and not session.cancelled and session.client:
                    # A failed reader cannot establish native termination.
                    # Retain this Thread and the existing cancellation fence.
                    session.cancelled = True
                    # The callback is released above before any reader-dependent RPC.
                    if session.turn_id:
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(asyncio.to_thread(session.client.turn_interrupt, session.thread_id, session.turn_id), 5)
            finally:
                if reader is not None:
                    reader.cancel()
                    await asyncio.gather(reader, return_exceptions=True)
                if session.turn_id and session.client:
                    session.client.unregister_turn_notifications(session.turn_id)
                session.active = False
                session.turn_ready.set()
                session.turn_ended.set()
                # User cancellation keeps its evidence until the native stop is
                # confirmed. EOF/ACK alone cannot admit another Turn.
                if not terminal and not session.cancelled:
                    await self.cleanup_session_adapter(sid)

    @staticmethod
    def _final_response(messages):
        # Match the official SDK: final_answer wins; otherwise the last
        # unclassified message is the response. Commentary stays in the stream.
        ordered = list(reversed(messages.values()))
        for phase, text in ordered:
            if phase == "final_answer":
                return text
        return next((text for phase, text in ordered if phase is None), "")

    async def deliver_control_input_impl(self, request, inputs):
        session = self._sessions.get(request.session_id or "default")
        identity = request.params.get("request_id")
        if request.params.get("source") != "permission_interrupt":
            raise ValueError("Codex control input must answer the active permission request")
        if session is None or not session.active or identity not in session.pending:
            raise ValueError("No matching active Codex approval")
        future, _, _ = session.pending[identity]
        answers = request.params.get("answers", [])
        if len(answers) != 1 or future.done():
            raise ValueError("Codex requires one answer to an active approval")
        from jiuwenswarm.agents.harness.common.rails.interrupt.permission_options import resolve_permission_action
        selected = answers[0].get("selected_options", [])
        if selected and (not isinstance(selected, list) or len(selected) != 1):
            raise ValueError("Select one Codex approval option")
        action = resolve_permission_action(selected[0] if selected else answers[0].get("value") or answers[0].get("answer"))
        decision = {"allow_once": "accept", "reject": "decline"}.get(action)
        if decision is None:
            raise ValueError("Codex supports allow_once or reject")
        del session.pending[identity]
        future.set_result({"decision": decision})
        yield self._chunk(request, {"event_type": "runtime.accepted", "control_request_id": identity}, complete=True)

    async def process_interrupt(self, request):
        if request.params.get("intent", "cancel") != "cancel":
            raise ValueError("Codex supports cancel only")
        session = self._sessions.get(request.session_id or "default")
        if session and (session.active or session.cancelled):
            session.cancelled = True
            self._release_controls(session)
            async with session.cancel_lock:
                if not session.cancel_confirmed:
                    try:
                        async with asyncio.timeout(_CANCEL_TIMEOUT):
                            await session.turn_ready.wait()
                            if not session.turn_id:
                                raise RuntimeError("Codex did not return a Turn identity")
                            if not session.native_terminal and not session.cancel_acknowledged:
                                await asyncio.to_thread(session.client.turn_interrupt, session.thread_id, session.turn_id)
                                session.cancel_acknowledged = True
                            await session.turn_ended.wait()
                            if not session.native_terminal:
                                raise RuntimeError("Codex stream closed without a native terminal event")
                            await self._stop_turn_terminals(session)
                            session.cancel_confirmed = True
                    except Exception as exc:
                        # Preserve the Thread and ownership evidence for retry;
                        # never report success or silently start a replacement.
                        raise RuntimeError("Codex cancellation could not be confirmed; retry cancel before continuing this session") from exc
        return AgentResponse(request.request_id, request.channel_id, payload={"event_type": "chat.interrupt_result", "intent": "cancel", "success": True})

    @staticmethod
    async def _stop_turn_terminals(session):
        if not session.command_ids:
            return

        async def owned_terminals():
            cursor = None
            seen = set()
            owned = []
            while True:
                params = {"threadId": session.thread_id}
                if cursor is not None:
                    params["cursor"] = cursor
                page = await asyncio.to_thread(session.client.request, "thread/backgroundTerminals/list",
                                               params, response_model=_Terminals)
                owned.extend(t for t in page.data if t.itemId in session.command_ids)
                cursor = page.nextCursor
                if cursor is None:
                    return owned
                if cursor in seen:
                    raise RuntimeError("Codex repeated a terminal-list cursor")
                seen.add(cursor)

        for terminal in await owned_terminals():
            # itemId came from this Turn's sole event consumer; processId is
            # resolved by the official API, never guessed from OS processes.
            await asyncio.to_thread(session.client.request, "thread/backgroundTerminals/terminate",
                                    {"threadId": session.thread_id, "processId": terminal.processId},
                                    response_model=_Terminated)
        if await owned_terminals():
            raise RuntimeError("Codex still reports terminals belonging to the cancelled Turn")

    async def cleanup_session_adapter(self, session_id):
        session = self._sessions.get(session_id)
        if session is None:
            return False
        async with session.lock:
            if session.active:
                raise RuntimeError("Cancel and drain the Codex producer before closing")
            self._release_controls(session)
            if session.client:
                await asyncio.to_thread(session.client.close)
            self._save_binding(session)
            if not session.thread_id:
                shutil.rmtree(session.root)
            self._sessions.pop(session_id, None)
        return True

    async def cleanup(self):
        for sid in list(self._sessions):
            await self.cleanup_session_adapter(sid)
        self._settings = None

    def runtime_permission_status(self, session_id):
        session = self._sessions.get(session_id)
        desired = session.desired_permission if session else self._permission_profile
        effective = session.effective_permission if session else None
        return {"supported_profiles": list(self.permission_profiles), "update_timing": "idle",
                "desired_profile": desired, "effective_profile": effective,
                "state": "not_started" if effective is None else "applied" if effective == desired else "pending"}

    async def reload_agent_config(self, config_base=None, env_overrides=None, target_session_id=None, reload_scopes=None):
        if reload_scopes and "permissions" not in reload_scopes:
            return
        from jiuwenswarm.common.config import get_config
        profile = self._profile(config_base if config_base is not None else get_config())
        if target_session_id is None:
            self._permission_profile = profile
        for sid, session in self._sessions.items():
            if target_session_id is None or sid == target_session_id:
                session.desired_permission = profile
                self._save_binding(session)

    async def process_message_impl(self, request, inputs):
        chunks = [chunk.payload async for chunk in self.process_message_stream_impl(request, inputs)]
        return AgentResponse(request.request_id, request.channel_id, ok=not any(c.get("event_type") == "chat.error" for c in chunks), payload={"chunks": chunks, "content": next((c.get("content", "") for c in reversed(chunks) if c.get("event_type") == "chat.final"), "")})

    async def handle_user_answer(self, request):
        raise ValueError("Use the active session control input channel")

    async def handle_swarmflow_reply(self, request):
        raise ValueError("Codex does not support Team")

    async def handle_goal_command_structured(self, params, session_id):
        action = params.get("action", "get")
        if action == "get":
            return {"result_type": "goal_snapshot", "action": action, "goal": None}
        return {"result_type": "goal_error", "action": action,
                "error_code": "provider_capability_unsupported",
                "error": "Codex does not support continuous goals"}

    async def handle_heartbeat(self, request):
        raise ValueError("Codex does not support heartbeat")


# Preserve the existing import while discovery uses a lightweight entry point.
from jiuwenswarm.common.external_adapter_factories import create_codex as create
