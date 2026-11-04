"""Official Claude SDK integration; the original Runtime owns each producer."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import logging
import os
import time
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jiuwenswarm.common.external_adapter_factories import create_claude
from jiuwenswarm.common.claude_adapter_config import config_snapshot, resolve_model, native_timeout_env
from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk
from jiuwenswarm.common.schema.message import ReqMethod
from .subagent_projection import SubagentProjection
from .claude_usage import ClaudeUsage
from . import session_recovery as recovery


logger = logging.getLogger(__name__)


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


@dataclass
class _NativeTasks:
    """Observe official lifecycle facts; scheduling stays in the CLI/Runtime."""
    tasks: dict = field(default_factory=dict)
    active: set = field(default_factory=set)
    stop_requested: set = field(default_factory=set)
    state_events: bool = False
    idle: bool = False

    def observe(self, subtype, data, native_id):
        if data.get("session_id", native_id) != native_id:
            return
        if subtype == "session_state_changed":
            self.state_events = True
            self.idle = data.get("state") == "idle"
        elif subtype == "background_tasks_changed" and isinstance(data.get("tasks"), list):
            # This is an authoritative *live* snapshot, not completion proof.
            self.active = {t["task_id"] for t in data["tasks"]
                           if isinstance(t, dict) and t.get("task_id") and not t.get("ambient")}
            for task_id in self.active:
                self.tasks.setdefault(task_id, {"task_id": task_id, "status": "unknown"})
        elif subtype in {"task_started", "task_progress", "task_updated", "task_notification"}:
            task_id = data.get("task_id")
            if not task_id or data.get("owned_by_subagent"):
                return
            if subtype != "task_started" and task_id not in self.tasks:
                return
            task = self.tasks.setdefault(task_id, {"task_id": task_id, "status": "unknown"})
            for key in ("tool_use_id", "description", "task_type", "subagent_type"):
                if key in data:
                    if key != "description" or subtype == "task_started" or key not in task:
                        task[key] = data[key]
            status = (data.get("patch") or {}).get("status") if subtype == "task_updated" else data.get("status")
            if subtype == "task_started":
                status = "running"
            if status is not None:
                task["status"] = status
            if subtype == "task_notification" and isinstance(data.get("summary"), str):
                task["summary"] = data["summary"]
            if status in {"completed", "failed", "stopped", "killed"}:
                self.active.discard(task_id)
            elif subtype == "task_started":
                self.active.add(task_id)
            task.setdefault("created_at", int(time.time() * 1000))
            task["updated_at"] = int(time.time() * 1000)
            task["revision"] = task.get("revision", 0) + 1
            return task

    @staticmethod
    def web_update(task, session_id):
        if task.get("task_type") not in {"local_agent", "remote_agent"}:
            return None
        outcome = {"completed": "completed", "failed": "failed", "stopped": "cancelled", "killed": "cancelled"}.get(task["status"])
        return {"event_type": "chat.subtask_update", "session_id": session_id,
                "parent_session_id": session_id, "subagent_id": "claude-" + task["task_id"],
                "task_id": task["task_id"], "subagent_type": task.get("subagent_type", ""),
                "display_name": task.get("description") or task["task_id"],
                "task_description": task.get("description", ""),
                "status": "closed" if outcome else "running", "turn_outcome": outcome,
                "lifecycle": "closed" if outcome else "live", "can_send_input": False,
                "needs_resume": False, "closed_reason": outcome,
                "closed_at": task["updated_at"] if outcome else None,
                "created_at": task["created_at"], "updated_at": task["updated_at"],
                "revision": task["revision"],
                "provider": {"claude": {"task_id": task["task_id"], "status": task["status"]}}}


@dataclass
class Session:
    directory: str
    root: Path
    swarm_id: str = ""
    native_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started: bool = False
    active: bool = False
    cancelled: bool = False
    client: Any = None
    model_revision: str = ""
    desired_permission: str = "default"
    effective_permission: str | None = None
    close_unconfirmed: bool = False
    pending: dict = field(default_factory=dict)
    control_ready: asyncio.Event = field(default_factory=asyncio.Event)
    native_tasks: _NativeTasks = field(default_factory=_NativeTasks)
    producer_done: asyncio.Event = field(default_factory=asyncio.Event)
    usage: ClaudeUsage = field(default_factory=ClaudeUsage)


class ClaudeAdapter:
    capabilities = create_claude.capabilities
    permission_profiles = ("default", "full_access")
    supports_native_model_forks = False
    supports_native_plan_state = False

    def __init__(self, *, mode="agent"):
        self._validate_mode(mode)
        self._sessions = {}
        self._settings = None
        self._permission_profile = "default"

    @staticmethod
    def _validate_mode(mode):
        from gateway.common.mode_matrix import deprecate_mode, NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL
        if deprecate_mode(mode) not in {NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL}:
            raise ValueError("Claude supports single Agent/code only")

    @staticmethod
    def _profile(config):
        permissions = config.get("permissions") or {}
        if permissions.get("enabled") is False:
            return "full_access"
        if permissions.get("mode") == "auto":
            raise ValueError("Claude Automatic permissions are not supported; select Default or Full Access")
        return "default"

    async def create_instance(self, config=None, *, mode="agent", sub_mode=None):
        from jiuwenswarm.common.config import get_config
        self._validate_mode(mode)
        if sub_mode not in {None, "normal"} or (config or {}).get("run_permissions_enabled"):
            raise ValueError("Claude does not support Native run permissions or this sub-mode")
        if self._settings is not None:
            raise ValueError("Claude adapter is already configured")
        root = get_config()
        settings = dict((config or {}).get("claude", config_snapshot(root)["claude"]))
        if not settings.get("enabled"):
            raise ValueError("Enable Claude in Third-party Agents first")
        try:
            importlib.metadata.version("claude-agent-sdk")
        except importlib.metadata.PackageNotFoundError:
            raise ValueError("Install the claude-direct optional dependency") from None
        self._permission_profile = self._profile(config if config and "permissions" in config else root)
        if settings.get("cli_path"):
            from jiuwenswarm.common.windows_cli_paths import resolve_preserved_cli_path
            from .cli import resolve_cli
            settings["cli_path"] = resolve_cli("claude", explicit=resolve_preserved_cli_path(settings["cli_path"]))
        self._settings = settings

    def build_query(self, request, turn):
        if request.params.get("answers"):
            return "", turn
        if not isinstance(turn.text, str) or any(request.params.get(key) for key in ("files", "team", "run", "cron", "moa_enabled", "skills", "plugin_names", "agent_template_name")):
            raise ValueError("Claude currently accepts single-agent text only; selected equipment is not supported")
        rendered = turn.render()
        try:
            if json.loads(rendered).get("skills_to_use"):
                raise ValueError("Claude Skill selection is not supported yet")
        except (json.JSONDecodeError, AttributeError):
            pass
        return rendered, turn

    def execution_input_policy(self, request):
        from ..execution_input import ExecutionInputPolicy
        session = self._sessions.get(request.session_id or "default")
        return ExecutionInputPolicy(bound_directory=session.directory if session else None)

    async def reconcile_session_mcp(self, session_id, needed, *, execution_request=None):
        if needed:
            raise ValueError("Claude Swarm MCP equipment is not supported yet")

    async def prepare_session(self, *, session_id, channel_id, mode, project_dir=None, facts=None):
        self._validate_mode(mode)
        if self._settings is None:
            raise RuntimeError("Claude adapter has not been configured")
        from jiuwenswarm.common.utils import get_default_project_session_workspace_dir
        current = self._sessions.get(session_id)
        directory = Path(project_dir or (current.directory if current else get_default_project_session_workspace_dir())).expanduser()
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError("Claude requires an existing absolute project directory")
        directory = str(directory.resolve())
        if current:
            if current.close_unconfirmed:
                raise RuntimeError("Claude SDK shutdown is unconfirmed; close this session before continuing")
            if current.directory != directory:
                raise ValueError("Claude session workspace cannot change after binding")
            return
        from ..execution_input import session_facts
        facts = facts or session_facts(session_id)
        binding = recovery.load("claude", session_id, directory)
        if binding:
            recovery.require_settings(binding, self._settings)
            self._sessions[session_id] = Session(directory, Path(binding["root"]), swarm_id=session_id,
                native_id=binding["native_id"], started=True, model_revision=binding["model_revision"],
                desired_permission=binding["permission"])
            return
        if facts.has_assistant_history:
            raise ValueError("Claude cannot restore a released session without a recovery binding; its original native session cannot be identified")
        parent = facts.storage_dir / ".claude-direct"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = Path(tempfile.mkdtemp(prefix="session-", dir=parent))
        self._sessions[session_id] = Session(directory, root, swarm_id=session_id, desired_permission=self._permission_profile)

    def _save_binding(self, session):
        if session.swarm_id and session.started:
            recovery.save("claude", session.swarm_id, root=session.root, directory=session.directory,
                native_id=session.native_id, model_revision=session.model_revision,
                settings_revision=recovery.settings_revision(self._settings), permission=session.desired_permission)

    def has_session_runtime(self, session_id=None):
        return session_id in self._sessions if session_id else bool(self._sessions)

    def is_external_harness_session(self, session_id):
        return session_id in self._sessions

    @staticmethod
    def _chunk(request, payload, *, complete=False, outcome=None):
        return AgentResponseChunk(request.request_id, request.channel_id, payload=payload, is_complete=complete, runtime_completion=outcome)

    async def _approval(self, session, name, inputs, context):
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
        if name == "AskUserQuestion" or session.cancelled:
            return PermissionResultDeny(message="User questions are not supported by this integration yet", interrupt=session.cancelled)
        identity = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        session.pending[identity] = (future, name, inputs)
        session.control_ready.set()
        try:
            allowed = await asyncio.wait_for(future, 180)
            return PermissionResultAllow(updated_input=inputs) if allowed else PermissionResultDeny(message="Permission declined by the user")
        except (TimeoutError, asyncio.CancelledError):
            return PermissionResultDeny(message="Permission request cancelled", interrupt=True)
        finally:
            session.pending.pop(identity, None)

    @staticmethod
    def _release_controls(session):
        for future, _, _ in session.pending.values():
            if not future.done():
                future.set_result(False)
        session.pending.clear()
        session.control_ready.set()

    def _options(self, session, model, role: str | None = None):
        from claude_agent_sdk import ClaudeAgentOptions
        home = session.root / "home"
        home.mkdir(exist_ok=True, mode=0o700)
        env = {"HOME": str(home), "USERPROFILE": str(home), "CLAUDE_CONFIG_DIR": str(session.root / "config"),
               "XDG_CONFIG_HOME": str(session.root / "config"), "XDG_DATA_HOME": str(session.root / "data"),
               "XDG_CACHE_HOME": str(session.root / "cache"), "APPDATA": str(session.root / "appdata"),
               "LOCALAPPDATA": str(session.root / "localappdata"), "ANTHROPIC_BASE_URL": model.api_base,
               "ANTHROPIC_API_KEY": model.api_key, "ANTHROPIC_AUTH_TOKEN": "", "CLAUDE_CODE_OAUTH_TOKEN": "",
               "CLAUDE_CODE_USE_BEDROCK": "0", "CLAUDE_CODE_USE_VERTEX": "0", "CLAUDE_CODE_USE_FOUNDRY": "0",
               "CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS": "1"}
        env.update(native_timeout_env(self._settings, model))
        hostname = urlparse(model.api_base).hostname
        if hostname in {"localhost", "127.0.0.1", "::1"}:
            # A local model gateway must not be forwarded through an inherited
            # outbound proxy. Keep the existing bypass entries for other hosts.
            bypass = ",".join(value for value in (
                os.environ.get("NO_PROXY", ""), os.environ.get("no_proxy", ""), hostname,
            ) if value)
            env["NO_PROXY"] = env["no_proxy"] = bypass
        extra_args = {"replay-user-messages": None}
        if role is not None:
            # The CLI otherwise reuses the original system prompt on resume.
            extra_args["system-prompt-snapshot"] = "off"
        return ClaudeAgentOptions(cwd=session.directory, cli_path=self._settings.get("cli_path"),
            model=model.model_name, env=env, setting_sources=[], strict_mcp_config=True,
            session_id=None if session.started else session.native_id,
            resume=session.native_id if session.started else None,
            extra_args=extra_args,
            permission_mode="bypassPermissions" if session.desired_permission == "full_access" else "default",
            can_use_tool=lambda name, inputs, context: self._approval(session, name, inputs, context),
            include_partial_messages=True,
            system_prompt={"type": "preset", "preset": "claude_code", "append": role} if role else None)

    async def process_message_stream_impl(self, request, inputs):
        from claude_agent_sdk import ClaudeSDKClient, AssistantMessage, UserMessage, SystemMessage, StreamEvent, ResultMessage, ToolUseBlock, ToolResultBlock, TextBlock
        if request.req_method not in {None, ReqMethod.CHAT_SEND} or request.params.get("answers"):
            raise ValueError("Use the active Claude control input channel")
        from ..execution_input import prepared_input
        execution = prepared_input(request, inputs)
        sid = request.session_id or "default"
        await self.prepare_session(session_id=sid, channel_id=request.channel_id, mode=request.params.get("mode", "agent"),
                                   project_dir=execution.directory if execution else inputs.get("workspace_dir") or inputs.get("project_dir") or inputs.get("cwd"),
                                   facts=execution.session if execution else None)
        session = self._sessions[sid]
        from jiuwenswarm.common.claude_adapter_config import validate_model
        model = validate_model(execution.model) if execution else resolve_model(request)
        revision = hashlib.sha256(model.model_dump_json().encode()).hexdigest()
        if session.model_revision and session.model_revision != revision:
            raise ValueError("Claude model configuration changed; create a new session")
        if session.active:
            raise ValueError("Session already has a producer; use Runtime scheduling")
        session.active, session.cancelled = True, False
        session.producer_done.clear()
        session.native_tasks = tasks = _NativeTasks()
        children = SubagentProjection("claude", sid)
        session.control_ready.clear()
        terminal = False
        tools = {}
        result_message = None
        input_id = str(uuid.uuid4())
        input_accepted = False
        reader = None
        stream = None
        client = None
        phase = "sdk_connect"
        last_event = "none"
        started = time.monotonic()
        try:
            # Official connect/disconnect stay on this producer/AnyIO owner.
            role = execution.main_agent_role if execution else None
            options = self._options(session, model) if role is None else self._options(session, model, role.instructions)
            client = ClaudeSDKClient(options)
            await client.connect()
            session.client = client
            phase = "permission_update"
            await client.set_permission_mode("bypassPermissions" if session.desired_permission == "full_access" else "default")
            session.effective_permission = session.desired_permission
            session.model_revision = revision
            phase = "query_submit"
            async def native_input():
                yield {"type": "user", "uuid": input_id, "parent_tool_use_id": None,
                       "message": {"role": "user", "content": inputs["query"]}}
            await client.query(native_input(), session_id=session.native_id)
            phase = "execution"
            # receive_response stops at the main result, even while native
            # background agents and their automatic follow-up turns still run.
            stream = client.receive_messages()
            while True:
                if reader is None:
                    reader = asyncio.create_task(anext(stream))
                control = asyncio.create_task(session.control_ready.wait())
                try:
                    done, _ = await asyncio.wait({reader, control}, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    control.cancel()
                    await asyncio.gather(control, return_exceptions=True)
                if session.control_ready.is_set():
                    session.control_ready.clear()
                    for identity, (future, name, args) in list(session.pending.items()):
                        if not future.done():
                            yield self._chunk(request, {"event_type": "chat.ask_user_question", "request_id": identity,
                                "source": "permission_interrupt", "questions": [{"question": name + ": " + json.dumps(args, ensure_ascii=False),
                                "options": [{"label": "允许一次", "value": "allow_once"}, {"label": "拒绝", "value": "reject"}], "multiSelect": False}]})
                if reader not in done:
                    continue
                message = reader.result()
                last_event = type(message).__name__
                reader = None
                if isinstance(message, UserMessage) and message.uuid == input_id:
                    # Resume can first emit an orphan task's zero-turn result.
                    # The official input echo identifies this request exactly.
                    if not input_accepted:
                        commit_role = inputs.get("_commit_role_selection")
                        if commit_role is not None:
                            commit_role()
                    input_accepted = True
                    result_message = None
                    tasks.idle = False
                    continue
                if isinstance(message, SystemMessage):
                    if input_accepted or message.subtype == "session_state_changed":
                        task = tasks.observe(message.subtype, message.data, session.native_id)
                        if task is not None:
                            payload = tasks.web_update(task, sid)
                            if payload is not None:
                                native_id = task["task_id"]
                                children.register(native_id, task.get("description", ""))
                                data = message.data
                                summary = data.get("summary") if message.subtype == "task_notification" else data.get("description")
                                if isinstance(summary, str) and summary.strip():
                                    terminal_task = task["status"] in {"completed", "failed", "stopped", "killed"}
                                    if message.subtype == "task_notification":
                                        children.result(native_id, summary, source="task_notification.summary")
                                    activity = children.activity(native_id,
                                        "error" if task["status"] == "failed" else "tool_result" if terminal_task else "thinking",
                                        summary, identity="progress" if message.subtype == "task_progress" else data.get("uuid") or message.subtype + str(task["revision"]),
                                        tool_name=data.get("last_tool_name"))
                                    if activity:
                                        yield self._chunk(request, activity)
                                yield self._chunk(request, children.roster(native_id,
                                    outcome=payload["turn_outcome"], closed=payload["lifecycle"] == "closed",
                                    native_status=task["status"]))
                    if session.cancelled:
                        await self._stop_native_tasks(session)
                    if input_accepted and tasks.idle and not tasks.active and result_message is not None:
                        break
                if getattr(message, "parent_tool_use_id", None):
                    # Route only children proven by this producer's task_started.
                    task = next((t for t in tasks.tasks.values()
                        if t.get("tool_use_id") == message.parent_tool_use_id and t["task_id"] in children.children), None)
                    if task and isinstance(message, (AssistantMessage, UserMessage)) and isinstance(message.content, list):
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                tools[block.id] = block.name
                                summary, _ = _bounded_output(block.name + ": " + json.dumps(block.input, ensure_ascii=False), _ACTIVITY_CHAR_LIMIT)
                                activity = children.activity(task["task_id"], "tool_call", summary,
                                    identity=block.id, tool_name=block.name, tool_call_id=block.id)
                            elif isinstance(block, ToolResultBlock):
                                content = block.content if isinstance(block.content, str) else "\n".join(
                                    c.get("text", "") for c in (block.content or []) if isinstance(c, dict) and c.get("type") == "text")
                                content, _ = _bounded_output(content, _ACTIVITY_CHAR_LIMIT)
                                activity = children.activity(task["task_id"], "tool_result", content,
                                    identity=block.tool_use_id, tool_name=tools.get(block.tool_use_id),
                                    tool_call_id=block.tool_use_id, ok=False if block.is_error else None)
                            else:
                                continue
                            if activity:
                                yield self._chunk(request, activity)
                    continue
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    if message.data.get("session_id") != session.native_id:
                        raise ValueError("Claude returned a different session")
                    session.started = True
                    self._save_binding(session)
                elif isinstance(message, StreamEvent):
                    event = message.event
                    if event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                        yield self._chunk(request, {"event_type": "chat.delta", "content": event["delta"].get("text", "")})
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tools[block.id] = block.name
                            yield self._chunk(request, {"event_type": "chat.tool_call", "tool_call": {"id": block.id, "name": block.name, "arguments": block.input}})
                elif isinstance(message, UserMessage) and isinstance(message.content, list):
                    for block in message.content:
                        if not isinstance(block, ToolResultBlock):
                            continue
                        name = tools.get(block.tool_use_id, "tool")
                        # CLI tool errors can carry text despite the SDK annotation.
                        native = message.tool_use_result if isinstance(message.tool_use_result, dict) else {}
                        code = native.get("exit_code") if name == "Bash" else None
                        code = code if type(code) is int else None
                        success = not block.is_error if block.is_error is not None else None
                        if code is not None and not block.is_error:
                            success = code == 0
                        content = block.content if isinstance(block.content, str) else json.dumps(block.content, ensure_ascii=False)
                        content, projection = _bounded_output(content, _TOOL_OUTPUT_CHAR_LIMIT)
                        result = {"event_type": "chat.tool_result", "tool_call_id": block.tool_use_id, "tool_name": name,
                            "content": content, "result": content, "status": "error" if block.is_error else "completed", "invocation_status": "completed",
                            "provider": {"claude": {"is_error": block.is_error, **projection}}, "success": success, "task_acceptance": "unknown"}
                        if name == "Bash":
                            result.update(exit_code=code, command_success=code == 0 if code is not None else None)
                        yield self._chunk(request, result)
                elif isinstance(message, ResultMessage):
                    if message.session_id != session.native_id:
                        raise ValueError("Claude completed a different session")
                    session.started = True
                    self._save_binding(session)
                    if not input_accepted and not message.is_error:
                        logger.info("Claude pre-input result ignored request=%s native_session=%s", request.request_id, session.native_id)
                        continue
                    if input_accepted:
                        usage = session.usage.project(message.model_usage, session_id=sid, native_id=session.native_id,
                            crashed=message.subtype == "error_during_execution")
                        if usage is not None:
                            yield self._chunk(request, usage)
                    result_message = message
                    if message.is_error and not session.cancelled:
                        terminal = True
                        outcome = "error"
                        logger.warning("Claude terminal request=%s outcome=%s subtype=%s api_status=%s elapsed=%.3fs", request.request_id, outcome, message.subtype, getattr(message, "api_error_status", None), time.monotonic() - started)
                        yield self._chunk(request, {"event_type": "chat.error", "code": "claude_" + outcome, "error": "Claude execution cancelled" if session.cancelled else "Claude model request failed; check model service compatibility and authentication"}, complete=True, outcome=outcome)
                        return
                    if not tasks.state_events:
                        if tasks.tasks:
                            yield self._chunk(request, {"event_type": "chat.error", "code": "claude_lifecycle_unsupported", "error": "Claude CLI did not expose a session idle boundary for background tasks"}, complete=True, outcome="error")
                            return
                        break
            terminal = True
            if session.cancelled:
                yield self._chunk(request, {"event_type": "chat.error", "code": "claude_cancelled", "error": "Claude execution cancelled"}, complete=True, outcome="cancelled")
            else:
                payload = {"event_type": "chat.final", "content": result_message.result or "", "invocation_status": "completed", "task_acceptance": "unknown"}
                if tasks.tasks:
                    payload["provider"] = {"claude": {"tasks": list(tasks.tasks.values())}}
                yield self._chunk(request, payload, complete=True, outcome="completed")
        except StopAsyncIteration:
            yield self._chunk(request, {"event_type": "chat.error", "code": "claude_incomplete", "error": "Claude stream ended without a result"}, complete=True, outcome="error")
        except TimeoutError:
            logger.warning("Claude timeout request=%s phase=%s last_event=%s elapsed=%.3fs source=native_sdk", request.request_id, phase, last_event, time.monotonic() - started)
            yield self._chunk(request, {"event_type": "chat.error", "code": "claude_timeout", "error": "Claude native SDK operation timed out", "provider": {"claude": {"phase": phase, "timeout_source": "native_sdk"}}}, complete=True, outcome="error")
        except Exception as exc:
            logger.warning("Claude failure request=%s phase=%s last_event=%s elapsed=%.3fs error_type=%s", request.request_id, phase, last_event, time.monotonic() - started, type(exc).__name__)
            yield self._chunk(request, {"event_type": "chat.error", "code": "claude_runtime_failed", "error": "Claude SDK initialization or execution failed; check the configured CLI and model service"}, complete=True, outcome="error")
        finally:
            self._release_controls(session)
            if reader is not None:
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
            try:
                if stream is not None:
                    await stream.aclose()
            finally:
                if client is not None:
                    try:
                        await client.disconnect()
                    except BaseException as exc:
                        session.close_unconfirmed = True
                        logger.warning("Claude shutdown unconfirmed request=%s error_type=%s", request.request_id, type(exc).__name__)
                        raise
                    finally:
                        session.client = None
                        session.active = False
                        session.producer_done.set()
                else:
                    session.active = False
                    session.producer_done.set()
            # Cancellation ends the Turn, not the initialized SDK Session. Keep
            # its official transcript for resume; close/eviction still owns cleanup.
            if not terminal and not (session.cancelled and session.started):
                await self.cleanup_session_adapter(sid)

    async def deliver_control_input_impl(self, request, inputs):
        session = self._sessions.get(request.session_id or "default")
        identity = request.params.get("request_id")
        if request.params.get("source") != "permission_interrupt" or not session or not session.active or identity not in session.pending:
            raise ValueError("No matching active Claude approval")
        answers = request.params.get("answers", [])
        if len(answers) != 1:
            raise ValueError("Claude requires one approval answer")
        from jiuwenswarm.agents.harness.common.rails.interrupt.permission_options import resolve_permission_action
        selected = answers[0].get("selected_options", [])
        if not isinstance(selected, list) or len(selected) != 1:
            raise ValueError("Select one Claude approval option")
        action = resolve_permission_action(selected[0])
        if action not in {"allow_once", "reject"}:
            raise ValueError("Claude supports allow_once or reject")
        future, _, _ = session.pending[identity]
        if future.done():
            raise ValueError("Claude approval has already ended")
        del session.pending[identity]
        future.set_result(action == "allow_once")
        yield self._chunk(request, {"event_type": "runtime.accepted", "control_request_id": identity}, complete=True)

    async def process_interrupt(self, request):
        if request.params.get("intent", "cancel") != "cancel":
            raise ValueError("Claude supports cancel only")
        session = self._sessions.get(request.session_id or "default")
        if session and session.active:
            session.cancelled = True
            self._release_controls(session)
            if session.client:
                await asyncio.wait_for(session.client.interrupt(), 5)
                await self._stop_native_tasks(session)
                # Runtime cancels its producer after this control returns.
                # Let the SDK owner drain/close first; a second cancellation
                # during AnyIO teardown otherwise leaves shutdown unconfirmed.
                await asyncio.wait_for(session.producer_done.wait(), 20)
                if session.close_unconfirmed:
                    raise RuntimeError("Claude SDK shutdown is unconfirmed; retain execution ownership")
        return AgentResponse(request.request_id, request.channel_id, payload={"event_type": "chat.interrupt_result", "intent": "cancel", "success": True})

    @staticmethod
    async def _stop_native_tasks(session):
        # Only IDs observed from this producer's native session are owned here.
        tasks = session.native_tasks
        client = session.client
        if client is None:
            return
        for task_id in tuple(tasks.active - tasks.stop_requested):
            tasks.stop_requested.add(task_id)
            await asyncio.wait_for(client.stop_task(task_id), 5)

    async def cleanup_session_adapter(self, session_id):
        session = self._sessions.get(session_id)
        if session is None:
            return False
        if session.active:
            raise RuntimeError("Cancel and drain the Claude producer before closing")
        if session.close_unconfirmed:
            raise RuntimeError("Claude SDK shutdown is unconfirmed; retain execution ownership")
        self._release_controls(session)
        self._save_binding(session)
        if not session.started:
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
        return {"supported_profiles": list(self.permission_profiles), "update_timing": "idle", "desired_profile": desired,
                "effective_profile": effective, "state": "not_started" if effective is None else "applied" if effective == desired else "pending"}

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
        raise ValueError("Claude does not support Team")

    async def handle_goal_command_structured(self, params, session_id):
        action = params.get("action", "get")
        return {"result_type": "goal_snapshot", "action": action, "goal": None} if action == "get" else {"result_type": "goal_error", "action": action, "error_code": "provider_capability_unsupported", "error": "Claude does not support continuous goals"}

    async def handle_heartbeat(self, request):
        raise ValueError("Claude does not support heartbeat")
