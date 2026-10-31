"""Direct Codex main-agent adapter; Swarm owns scheduling, controls and history."""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import hashlib
import json
import math
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk
from jiuwenswarm.common.schema.message import ReqMethod
from .codex_config import availability, config_snapshot, model_overrides, resolve_model


@dataclass
class Session:
    directory: str
    root: Path
    client: Any = None
    thread_id: str = ""
    turn_id: str = ""
    model_revision: str = ""
    active: bool = False
    cancelled: bool = False
    cancel_acknowledged: bool = False
    effective_permission: str | None = None
    desired_permission: str = "default"
    pending: dict = field(default_factory=dict)
    control_ready: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def command_result(item: dict) -> dict:
    code = item.get("exitCode")
    code = code if type(code) is int else None
    native_status = item.get("status")
    output = item.get("aggregatedOutput") or ("Command was not executed: permission declined" if native_status == "declined" else "")
    return {"event_type": "chat.tool_result", "tool_call_id": item["id"],
            "tool_name": "shell", "content": output,
            "result": output, "status": "error" if native_status == "declined" else native_status,
            "invocation_status": item.get("status"), "exit_code": code,
            "command_success": code == 0 if code is not None else None,
            "success": code == 0 if code is not None else None, "task_acceptance": "unknown"}


class CodexAdapter:
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

    async def reconcile_session_mcp(self, session_id, needed, *, execution_request=None):
        if needed:
            raise ValueError("Codex Swarm MCP equipment is not supported yet")

    async def prepare_session(self, *, session_id, channel_id, mode, project_dir=None):
        self._validate_mode(mode)
        if self._settings is None:
            raise RuntimeError("Codex adapter has not been configured")
        from jiuwenswarm.common.utils import get_agent_sessions_dir, get_default_project_session_workspace_dir
        current = self._sessions.get(session_id)
        directory = Path(project_dir or (current.directory if current else get_default_project_session_workspace_dir())).expanduser()
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError("Codex requires an existing absolute project directory")
        directory = str(directory.resolve())
        if current:
            if directory != current.directory:
                raise ValueError("Codex session workspace cannot change after binding")
            return
        from jiuwenswarm.server.runtime.session.session_history import read_session_history_records
        if any(row.get("role") == "assistant" and row.get("event_type") != "chat.request_completed" for row in read_session_history_records(session_id)):
            raise ValueError("Codex cannot restore a released Swarm session yet; create a new session")
        parent = get_agent_sessions_dir() / ".codex-direct"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = Path(tempfile.mkdtemp(prefix="session-", dir=parent))
        self._sessions[session_id] = Session(directory, root, desired_permission=self._permission_profile)

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
                             config_overrides=model_overrides(model), client_name="swarm_agent_adapter")
        try:
            client = CodexClient(config, approval_handler=lambda method, params: self._approval(session, loop, method, params))
        except TypeError:
            raise RuntimeError("The installed Codex SDK does not support Swarm's required client/approval interface") from None
        try:
            await asyncio.to_thread(client.start)
            await asyncio.wait_for(asyncio.to_thread(client.initialize), 30)
            response = await asyncio.wait_for(asyncio.to_thread(client.thread_start, {
                "cwd": session.directory, "model": model.model_name, "modelProvider": "swarm",
                **self._permission_options(session.desired_permission),
            }), 30)
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

    @staticmethod
    def _permission_options(profile):
        if profile not in CodexAdapter.permission_profiles:
            raise ValueError("Unsupported Codex permissions")
        return {"approvalPolicy": "never" if profile == "full_access" else "on-request",
                "approvalsReviewer": "user", "sandbox": "danger-full-access" if profile == "full_access" else "workspace-write"}

    async def process_message_stream_impl(self, request, inputs):
        if request.req_method not in {None, ReqMethod.CHAT_SEND} or request.params.get("answers"):
            raise ValueError("Use the active Codex control input channel")
        sid = request.session_id or "default"
        await self.prepare_session(session_id=sid, channel_id=request.channel_id,
                                   mode=request.params.get("mode", "agent"),
                                   project_dir=inputs.get("workspace_dir") or inputs.get("project_dir") or inputs.get("cwd"))
        session = self._sessions[sid]
        model = resolve_model(request)
        timeout = float(model.client_options.get("timeout", 180))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Codex model timeout must be positive and finite")
        async with session.lock:
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
            session.turn_id = ""
            session.control_ready.clear()
            session.active, session.cancelled, session.cancel_acknowledged = True, False, False
        reader = None
        terminal = False
        text_parts = {}
        try:
            async with asyncio.timeout(timeout):
                response = await asyncio.to_thread(session.client.turn_start, session.thread_id, inputs["query"])
                session.turn_id = response.turn.id
                if session.cancelled:
                    await asyncio.wait_for(asyncio.to_thread(session.client.turn_interrupt, session.thread_id, session.turn_id), 5)
                    session.cancel_acknowledged = True
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
                    payload = notification.payload.model_dump(mode="json", by_alias=True)
                    item = payload.get("item", {})
                    if method == "item/agentMessage/delta":
                        yield self._chunk(request, {"event_type": "chat.delta", "content": payload.get("delta", "")})
                    elif method == "item/started" and item.get("type") == "commandExecution":
                        yield self._chunk(request, {"event_type": "chat.tool_call", "tool_call": {"id": item["id"], "name": "shell", "arguments": {"command": item.get("command", ""), "cwd": item.get("cwd")}}})
                    elif method == "item/completed":
                        if item.get("type") == "commandExecution":
                            yield self._chunk(request, command_result(item))
                        elif item.get("type") == "agentMessage":
                            text_parts[item["id"]] = (item.get("phase"), item.get("text", ""))
                        elif item.get("type") == "fileChange":
                            yield self._chunk(request, {"event_type": "chat.tool_call", "tool_call": {"id": item["id"], "name": "file_change", "arguments": {"changes": item.get("changes", [])}}})
                            yield self._chunk(request, {"event_type": "chat.tool_result", "tool_call_id": item["id"], "tool_name": "file_change", "content": json.dumps(item.get("changes", [])), "success": item.get("status") == "completed", "task_acceptance": "unknown"})
                    elif method == "turn/completed":
                        terminal = True
                        status = payload["turn"]["status"]
                        if status == "completed":
                            yield self._chunk(request, {"event_type": "chat.final", "content": self._final_response(text_parts), "invocation_status": status, "task_acceptance": "unknown"}, complete=True, outcome="completed")
                        else:
                            cancelled = status == "interrupted"
                            yield self._chunk(request, {"event_type": "chat.error", "code": "cancelled" if cancelled else "codex_turn_failed", "error": "Codex execution cancelled" if cancelled else "Codex model request failed; check model endpoint compatibility and authentication"}, complete=True, outcome="cancelled" if cancelled else "error")
                        return
        except TimeoutError:
            yield self._chunk(request, {"event_type": "chat.error", "code": "codex_timeout", "error": "Codex execution exceeded the configured model timeout"}, complete=True, outcome="error")
        except Exception:
            yield self._chunk(request, {"event_type": "chat.error", "code": "codex_transport_failed", "error": "Codex runtime connection failed or an unsupported interaction was requested"}, complete=True, outcome="error")
        finally:
            self._release_controls(session)
            cancelled_turn_stopped = session.cancelled and session.cancel_acknowledged
            try:
                if not terminal and not cancelled_turn_stopped and session.client and session.turn_id:
                    # The callback is released above before any reader-dependent RPC.
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(asyncio.to_thread(session.client.turn_interrupt, session.thread_id, session.turn_id), 5)
                        cancelled_turn_stopped = session.cancelled
            finally:
                if reader is not None:
                    reader.cancel()
                    await asyncio.gather(reader, return_exceptions=True)
                if session.turn_id and session.client:
                    session.client.unregister_turn_notifications(session.turn_id)
                session.active = False
                # A confirmed user interrupt ends the Turn, not its Thread.
                # Failed interrupts and other nonterminal exits still dispose it.
                if not terminal and not cancelled_turn_stopped:
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
        if session and session.active:
            session.cancelled = True
            self._release_controls(session)
            if session.turn_id:
                try:
                    await asyncio.wait_for(asyncio.to_thread(session.client.turn_interrupt, session.thread_id, session.turn_id), 5)
                    session.cancel_acknowledged = True
                except Exception:
                    await asyncio.to_thread(session.client.close)
                    raise
        return AgentResponse(request.request_id, request.channel_id, payload={"event_type": "chat.interrupt_result", "intent": "cancel", "success": True})

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
