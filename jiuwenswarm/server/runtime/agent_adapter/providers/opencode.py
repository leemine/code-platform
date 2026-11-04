"""OpenCode AgentAdapter using the official HTTP/SSE API, without agent-core.

The host owns scheduling, history and stream consumption. This adapter owns CLI
services or borrows an explicitly configured server without disposing that server.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import os
import sys

from jiuwenswarm.common.external_adapter_factories import create_opencode
from . import opencode_transport as transport
from .cli import resolve_cli
from .opencode_usage import OpenCodeUsage
from . import session_recovery as recovery

from jiuwenswarm.common.schema.agent import AgentResponse, AgentResponseChunk
from jiuwenswarm.common.schema.message import ReqMethod


_TOOL_OUTPUT_CHAR_LIMIT = 60000
logger = logging.getLogger(__name__)


def _bounded_output(text: str, limit: int) -> tuple[str, dict]:
    """Bound the Swarm projection, leaving the native tool/model context intact."""
    if len(text) <= limit:
        return text, {}
    received_bytes = len(text.encode("utf-8"))
    marker = (f"\n[Output truncated by Swarm; Provider returned {len(text)} characters / "
              f"{received_bytes} UTF-8 bytes.]")
    displayed = text[:limit - len(marker)] + marker
    return displayed, {
        "output_truncated": True,
        "received_output_chars": len(text),
        "received_output_bytes": received_bytes,
        "displayed_output_chars": len(displayed),
        "displayed_output_bytes": len(displayed.encode("utf-8")),
    }


def _bounded_metadata(metadata: dict) -> tuple[dict, dict]:
    """Keep normal native metadata; omit oversized fields without cutting paths."""
    serialized = json.dumps(metadata, ensure_ascii=False)
    if len(serialized) <= _TOOL_OUTPUT_CHAR_LIMIT:
        return metadata, {}
    projected = {}
    remaining = _TOOL_OUTPUT_CHAR_LIMIT - 2
    # Preserve native command evidence and spill references before optional data.
    for key in dict.fromkeys(["exit", "truncated", "outputPath", *metadata]):
        if key not in metadata:
            continue
        entry_size = len(json.dumps({key: metadata[key]}, ensure_ascii=False)) - 2
        cost = entry_size + (2 if projected else 0)
        if cost <= remaining:
            projected[key] = metadata[key]
            remaining -= cost
    return projected, {
        "metadata_truncated": True,
        "omitted_metadata_fields": len(metadata) - len(projected),
        "received_metadata_bytes": len(serialized.encode("utf-8")),
        "displayed_metadata_bytes": len(json.dumps(projected, ensure_ascii=False).encode("utf-8")),
    }


def cli_candidates():
    """OpenCode installation hints, evaluated for the current desktop user."""
    home = Path.home()
    binary = "opencode.exe" if sys.platform == "win32" else "opencode"
    paths = [home / ".opencode/bin" / binary, home / ".local/bin" / binary]
    if sys.platform == "darwin":
        paths.extend([Path("/opt/homebrew/bin/opencode"), Path("/usr/local/bin/opencode")])
    elif sys.platform == "win32":
        paths.append(Path(os.environ.get("SCOOP") or home / "scoop") / "shims/opencode.exe")
        if os.environ.get("LOCALAPPDATA"):
            paths.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft/WinGet/Links/opencode.exe")
        # npm's public command is a script shim. Its postinstall selects the
        # native binary, so use that result rather than choosing CPU variants.
        prefixes = [Path(p) for p in os.get_exec_path() if p and Path(p).is_absolute()]
        configured = os.environ.get("NPM_CONFIG_PREFIX") or os.environ.get("npm_config_prefix")
        if configured:
            prefixes.append(Path(configured).expanduser())
        if os.environ.get("APPDATA"):
            prefixes.append(Path(os.environ["APPDATA"]) / "npm")
        paths.extend(
            prefix / "node_modules/opencode-ai/bin/opencode.exe"
            for prefix in prefixes if prefix.is_absolute()
        )
    return list(dict.fromkeys(path for path in paths if path.is_absolute()))


@dataclass
class _Session:
    native_id: str
    directory: str
    swarm_id: str = ""
    model_revision: str = ""
    restored: bool = False
    active: bool = False
    abort_failed: bool = False
    cancelled: bool = False
    permission_denied: bool = False
    pending: dict[str, str] = field(default_factory=dict)
    control_replied: asyncio.Event = field(default_factory=asyncio.Event)
    service: Any = None
    equipment: Any = None
    equipment_error: bool = False
    desired_permission: str = "default"
    effective_permission: str | None = None
    permission_error: bool = False
    configuration_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    usage: OpenCodeUsage = field(default_factory=OpenCodeUsage)
    usage_loaded: bool = False


def tool_payload(part: dict[str, Any]) -> dict[str, Any]:
    """Preserve native command evidence; a completed invocation is not exit 0."""
    state = part.get("state", {})
    code = state.get("metadata", {}).get("exit")
    code = code if type(code) is int else None
    is_command = part.get("tool") in {"bash", "shell"}
    output, projection = _bounded_output(state.get("output", state.get("error", "")) or "", _TOOL_OUTPUT_CHAR_LIMIT)
    metadata, metadata_projection = _bounded_metadata(state.get("metadata", {}))
    result = {
        "event_type": "chat.tool_result", "tool_call_id": part["callID"],
        "tool_name": part["tool"], "content": output, "result": output,
        "invocation_status": state.get("status"), "status": state.get("status"), "exit_code": code,
        "command_success": (code == 0) if code is not None else None,
        "task_acceptance": "unknown",
        "provider": {"opencode": {"part_id": part["id"], "metadata": metadata, **projection, **metadata_projection}},
    }
    # Consumers must not infer success from the invocation's completed status.
    result["success"] = result["command_success"] if is_command else state.get("status") == "completed"
    if state.get("status") == "error":
        result["success"] = False
    if not is_command:
        result.pop("command_success")
        result.pop("exit_code")
    return result


class OpenCodeAdapter:
    capabilities = create_opencode.capabilities
    permission_profiles = ("default", "full_access")
    supports_native_model_forks = False
    supports_native_plan_state = False
    def __init__(self, *, mode="agent"):
        from gateway.common.mode_matrix import deprecate_mode, NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL
        if deprecate_mode(mode) not in {NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL}:
            raise ValueError("OpenCode adapter supports single Agent/code only")
        self._client = None
        self._sessions: dict[str, _Session] = {}
        self._model: dict[str, str] = {}
        self._directory = ""
        self._timeout = None
        self._session_init_timeout = 120.0
        self._executable = None
        self._configured = False
        self._permission_profile = "default"
        self._recovery_settings = {}

    async def create_instance(self, config=None, *, mode="agent", sub_mode=None):
        if mode not in {"agent", "code"} or sub_mode not in {None, "normal"}:
            raise ValueError("OpenCode adapter does not support this mode")
        if self._configured:
            raise ValueError("OpenCode adapter is already configured")
        from jiuwenswarm.common.config import get_config
        config = config if config is not None else get_config()
        self._permission_profile = self._read_permission_profile(
            config if "permissions" in config else get_config()
        )
        if config.get("run_permissions_enabled"):
            raise ValueError("Native run permissions are not supported by OpenCode adapter")
        settings = (config.get("opencode") if "opencode" in config else get_config().get("opencode", {})) or {}
        self._recovery_settings = dict(settings)
        executable = settings.get("cli_path")
        url = str(settings.get("url") or "").strip()
        if executable or not url:
            self._executable = resolve_cli("opencode", explicit=str(executable) if executable else None,
                                           candidates=cli_candidates())
            if not self._executable:
                raise ValueError("OpenCode CLI was not found. Install OpenCode for this user, set opencode.cli_path, or configure opencode.url")
        parsed = urlparse(url)
        if not self._executable and (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password):
            raise ValueError("OpenCode server URL must be explicit and contain no credentials")
        if not self._executable and parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Remote OpenCode servers require HTTPS")
        model = settings.get("model", {})
        if model and (set(model) != {"providerID", "modelID"} or not all(isinstance(x, str) and x for x in model.values())):
            raise ValueError("OpenCode requires an explicit providerID/modelID")
        directory = settings.get("directory")
        if not directory and self._executable:
            from jiuwenswarm.common.utils import get_default_project_session_workspace_dir
            directory = get_default_project_session_workspace_dir()
        directory = Path(directory or "").expanduser()
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError("OpenCode requires an existing absolute workspace directory")
        self._directory, self._model = str(directory.resolve()), dict(model)
        raw_timeout = settings.get("turn_timeout")
        self._timeout = float(raw_timeout) if raw_timeout is not None else None
        if raw_timeout is not None and (isinstance(raw_timeout, bool) or not math.isfinite(self._timeout) or self._timeout <= 0):
            raise ValueError("turn_timeout must be positive and finite or null")
        self._session_init_timeout = float(settings.get("session_init_timeout", 120))
        if not math.isfinite(self._session_init_timeout) or not 0 < self._session_init_timeout <= 600:
            raise ValueError("session_init_timeout must be finite and between 0 and 600 seconds")
        if self._executable:
            self._configured = True
            return
        client = transport.create_client(url, username=settings.get("username", "opencode"), password=settings.get("password"))
        try:
            if not await transport.healthy(client):
                raise RuntimeError("OpenCode server is unhealthy")
        except transport.TransportError as exc:
            await client.aclose()
            raise RuntimeError(f"OpenCode health check failed ({type(exc).__name__})") from None
        except BaseException:
            await client.aclose()
            raise
        self._client = client
        self._configured = True

    async def _call(self, method, path, *, directory=None, body=None, session=None):
        client = session.service.client if session and session.service else self._client
        if client is None:
            raise RuntimeError("OpenCode adapter is not configured")
        initializing = method == "POST" and path == "/session"
        return await transport.request_json(client, method, path,
            directory=directory or (session.directory if session else self._directory), body=body,
            timeout=self._session_init_timeout if initializing else 15,
            operation="session initialization" if initializing else "API request")

    def build_query(self, request, turn):
        if request.params.get("answers"):
            # Controls are delivered separately to the existing producer, never as a new prompt.
            return "", turn
        if not isinstance(turn.text, str):
            raise ValueError("OpenCode pilot accepts text input only")
        unsupported = ("files", "team", "run", "cron", "moa_enabled")
        if any(request.params.get(k) for k in unsupported):
            raise ValueError("OpenCode pilot does not support Native equipment, Team or scheduled execution")
        rendered = turn.render()
        # Use the original UserTurn slash/chip parser, not a second prompt parser.
        if isinstance(rendered, str):
            try:
                selected = json.loads(rendered).get("skills_to_use", [])
            except (ValueError, AttributeError):
                selected = []
            if selected and not request.params.get("skills"):
                request.params["skills"] = selected
        return rendered, turn

    def _resolve_session_directory(self, session_id, project_dir=None):
        current = self._sessions.get(session_id)
        path = Path(project_dir).expanduser() if project_dir else Path(current.directory if current else self._directory)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("OpenCode session requires an existing absolute workspace directory")
        directory = str(path.resolve())
        if current and directory != current.directory:
            raise ValueError("OpenCode session workspace cannot change after binding")
        if not self._executable and directory != self._directory:
            raise ValueError("OpenCode session workspace must match its configured binding")
        return directory

    def execution_input_policy(self, request):
        from ..execution_input import ExecutionInputPolicy
        session = self._sessions.get(request.session_id or "default")
        return ExecutionInputPolicy(
            require_model=not self._model or bool(request.params.get("model_name") or request.params.get("model_selection")),
            include_model_catalog=bool(self._executable), strip_agentos_max_tokens=True, catalog_settings_key="opencode",
            bound_directory=session.directory if session else self._directory or None,
        )

    @staticmethod
    def _set_service_models(session, execution):
        if session.service and execution is not None:
            from .opencode_models import build_server_model_config
            session.service.model_config, _ = build_server_model_config(
                models=execution.models, settings=execution.model_settings)

    async def prepare_session(self, *, session_id, channel_id, mode, project_dir=None, facts=None, execution=None):
        from gateway.common.mode_matrix import deprecate_mode, NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL
        if deprecate_mode(mode) not in {NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL}:
            raise ValueError("OpenCode adapter supports single Agent/code only")
        directory = self._resolve_session_directory(session_id, project_dir)
        if session_id not in self._sessions:
            from ..execution_input import session_facts
            facts = facts or session_facts(session_id)
            binding = recovery.load("opencode", session_id, directory)
            if binding:
                if not self._executable:
                    raise ValueError("OpenCode recovery requires its original session-owned service")
                recovery.require_settings(binding, self._recovery_settings)
            elif facts.has_assistant_history:
                raise ValueError("OpenCode cannot restore a released session without a recovery binding; its original native session cannot be identified")
            from .opencode_equipment import Equipment
            session = _Session(binding["native_id"] if binding else "", directory, swarm_id=session_id,
                model_revision=binding["model_revision"] if binding else "", restored=bool(binding), equipment=Equipment(),
                usage=OpenCodeUsage(complete=not bool(binding)),
                desired_permission=binding["permission"] if binding else self._permission_profile)
            if self._executable:
                from .opencode_service import SessionService
                if binding:
                    session.service = SessionService(self._executable, directory, root=Path(binding["root"]))
                else:
                    session.service = SessionService(self._executable, directory)
            try:
                if session.service:
                    self._set_service_models(session, execution)
                    await session.service.configure(session.equipment, permission_profile=session.desired_permission)
                if binding:
                    native = await self._call("GET", f"/session/{session.native_id}", session=session)
                    if native.get("id") != session.native_id or native.get("directory") != directory:
                        raise ValueError("OpenCode recovery returned another session or workspace")
                    statuses = await self._call("GET", "/session/status", session=session)
                    if statuses.get(session.native_id, {}).get("type", "idle") != "idle":
                        raise ValueError("OpenCode native session is still active; recovery was not started")
                else:
                    native = await self._call("POST", "/session", body={"title": "Swarm single Agent"}, session=session)
                session.native_id = native["id"]
                self._sessions[session_id] = session
                async with session.configuration_lock:
                    if not binding:
                        session.desired_permission = self._permission_profile
                    await self._apply_permissions(session)
                    self._save_binding(session)
            except BaseException:
                self._sessions.pop(session_id, None)
                if session.service:
                    await session.service.close()
                raise

    def _save_binding(self, session):
        if session.swarm_id and session.native_id and session.service:
            recovery.save("opencode", session.swarm_id, root=session.service.root, directory=session.directory,
                native_id=session.native_id, model_revision=session.model_revision,
                settings_revision=recovery.settings_revision(self._recovery_settings),
                permission=session.desired_permission)
            session.service.retain_data = True

    async def reconcile_session_mcp(self, session_id, needed, *, execution_request=None):
        """Compatibility entry; the host retains snapshot commit ownership."""
        if execution_request is None:
            raise ValueError("OpenCode equipment requires the original request")
        from ..equipment import reconcile_equipment
        await reconcile_equipment(self, session_id, execution_request)

    def equipment_input_policy(self, session_id, request, *, execution=None):
        from ..equipment import EquipmentPolicy
        current = self._sessions.get(session_id)
        if current and (current.active or current.abort_failed):
            raise ValueError("OpenCode equipment cannot change during an active turn")
        directory = self._resolve_session_directory(session_id, execution.directory if execution else
            request.params.get("workspace_dir") or request.params.get("project_dir") or request.params.get("cwd"))
        return EquipmentPolicy(directory, include_global_skills=bool(self._executable))

    async def apply_equipment(self, sid, request, assets, *, directory, execution=None, ensure_current):
        from .opencode_equipment import convert_equipment
        equipment = convert_equipment(assets, directory=directory)
        if (equipment.skills or equipment.mcps) and not self._executable:
            raise ValueError("OpenCode equipment Skill/MCP requires a session-owned CLI (automatic discovery or opencode.cli_path)")
        ensure_current()
        await self.prepare_session(session_id=sid, channel_id=request.channel_id,
                                   mode=request.params.get("mode", "agent"), project_dir=directory,
                                   facts=execution.session if execution else None, execution=execution)
        session = self._sessions[sid]
        async with session.configuration_lock:
            if session.active or session.abort_failed:
                raise ValueError("OpenCode equipment cannot change during an active turn")
            session.equipment_error = True
            try:
                ensure_current()
                self._set_service_models(session, execution)
                if session.service:
                    session.effective_permission = None
                    await session.service.configure(equipment, permission_profile=session.desired_permission)
                    ensure_current()
                    if equipment.skills:
                        skills = await self._call("GET", "/skill", session=session)
                        if set(equipment.skills) - {x.get("name") for x in skills}:
                            raise ValueError("OpenCode did not load the requested equipment Skills")
                    if equipment.mcps:
                        statuses = await self._call("GET", "/mcp", session=session)
                        if any(statuses.get(name, {}).get("status") != "connected" for name in equipment.mcps):
                            raise ValueError("OpenCode equipment MCP connection failed")
                ensure_current()
                session.equipment = equipment
                await self._apply_permissions(session)
                ensure_current()
            except BaseException:
                # Partial native effects must not be used by a direct caller.
                session.effective_permission = None
                raise
            else:
                session.equipment_error = False

    def has_session_runtime(self, session_id=None):
        return session_id in self._sessions if session_id else bool(self._sessions)

    def is_external_harness_session(self, session_id):
        return session_id in self._sessions

    def _chunk(self, request, payload, *, complete=False, outcome=None):
        return AgentResponseChunk(request_id=request.request_id, channel_id=request.channel_id,
                                  payload=payload, is_complete=complete, runtime_completion=outcome)

    async def process_message_stream_impl(self, request, inputs):
        if request.req_method not in {None, ReqMethod.CHAT_SEND} or request.params.get("answers"):
            raise ValueError("Use the control input channel for active OpenCode interactions")
        from ..execution_input import prepared_input
        execution = prepared_input(request, inputs)
        sid = request.session_id or "default"
        await self.prepare_session(session_id=sid, channel_id=request.channel_id,
                                   mode=request.params.get("mode", "agent"),
                                   project_dir=execution.directory if execution else inputs.get("workspace_dir") or inputs.get("project_dir") or inputs.get("cwd"),
                                   facts=execution.session if execution else None, execution=execution)
        session = self._sessions[sid]
        selected_model = self._model
        if not selected_model or request.params.get("model_name") or request.params.get("model_selection"):
            from .opencode_models import resolve_request_model, validate_request_model
            _, selected_model = validate_request_model(execution.model) if execution else resolve_request_model(request)
            registered = await self._call("GET", "/provider", session=session)
            providers = registered.get("all", [])
            if not any(p.get("id") == selected_model["providerID"] and selected_model["modelID"] in p.get("models", {}) for p in providers):
                raise ValueError("opencode_model_snapshot_stale: refresh the plugin service from Swarm model configuration")
        async with session.configuration_lock:
            if session.equipment_error:
                raise RuntimeError("OpenCode equipment update was not confirmed; reconcile before executing")
            if session.active:
                raise RuntimeError("Session already has an active producer; use Runtime scheduling")
            model_revision = recovery.revision(selected_model)
            if session.restored and session.model_revision and session.model_revision != model_revision:
                raise ValueError("OpenCode model configuration changed; restore the original configuration before resuming")
            await self._apply_permissions(session)
            session.model_revision = model_revision
            self._save_binding(session)
            session.restored = False
            session.active, session.cancelled, session.permission_denied = True, False, False
        terminal = False
        text_parts: dict[str, str] = {}
        part_types: dict[str, str] = {}
        tool_calls, tool_results = set(), set()
        assistant_complete = False
        assistant_messages = set()
        try:
            if not session.usage_loaded:
                if session.usage.complete:
                    session.usage_loaded = True
                else:
                    # Restore only the native counters, not tool bodies or a
                    # second durable ledger. Observation failure cannot fail execution.
                    try:
                        async with asyncio.timeout(5):
                            rows = await self._call("GET", f"/session/{session.native_id}/message", session=session)
                        session.usage.restore(rows, native_id=session.native_id)
                        session.usage_loaded = session.usage.complete
                    except Exception as exc:
                        logger.info("OpenCode usage restore unavailable error_type=%s", type(exc).__name__)
            async with asyncio.timeout(self._timeout) as turn_budget:
                async with transport.subscribe(session.service.client if session.service else self._client, session.directory) as events:
                    # Establish the sole event subscription before accepting the prompt.
                    await self._call("POST", f"/session/{session.native_id}/prompt_async", body={
                        "model": selected_model, "parts": [{"type": "text", "text": inputs["query"]}],
                        "system": (
                            execution.main_agent_role.instructions if execution and execution.main_agent_role
                            else session.equipment.system if session.equipment else ""
                        ),
                    }, session=session)
                    commit_role = inputs.get("_commit_role_selection")
                    if commit_role is not None:
                        commit_role()
                    async for event in events:
                        props = event.get("properties", {})
                        part = props.get("part", {})
                        info = props.get("info", {})
                        event_sid = props.get("sessionID") or part.get("sessionID") or info.get("sessionID")
                        if event_sid != session.native_id:
                            continue
                        kind = event.get("type")
                        if kind == "message.updated" and info.get("role") == "assistant":
                            session.usage.observe(info, native_id=session.native_id)
                            usage = session.usage.project(session_id=sid, native_id=session.native_id)
                            if usage is not None:
                                yield self._chunk(request, usage)
                        native_error = props.get("error", {}) if kind == "session.error" else info.get("error", {})
                        if native_error.get("name") == "MessageAbortedError" or (kind == "session.idle" and session.cancelled):
                            terminal = True
                            yield self._chunk(request, {"event_type":"chat.error", "code":"cancelled", "error":"Execution cancelled"}, complete=True, outcome="cancelled")
                            return
                        if kind == "session.error":
                            terminal = True
                            yield self._chunk(request, provider_error_payload(native_error, "session"), complete=True, outcome="error")
                            return
                        if kind == "message.updated" and info.get("role") == "assistant":
                            assistant_messages.add(info["id"])
                            if info.get("error"):
                                terminal = True
                                yield self._chunk(request, provider_error_payload(native_error, "message"), complete=True, outcome="error")
                                return
                            assistant_complete = bool(info.get("time", {}).get("completed")) and info.get("finish") not in {"tool-calls", "unknown", None}
                        elif kind == "message.part.updated":
                            pid = part.get("id", "")
                            part_types[pid] = part.get("type", "")
                            if part.get("type") == "text" and part.get("messageID") in assistant_messages:
                                text_parts[pid] = part.get("text", "")
                            if part.get("type") == "tool":
                                call = part["callID"]; state = part.get("state", {})
                                if call not in tool_calls and state.get("status") != "pending":
                                    tool_calls.add(call)
                                    yield self._chunk(request, {"event_type":"chat.tool_call", "tool_call":{"id":call,"name":part["tool"],"arguments":state.get("input", {})}})
                                if state.get("status") in {"completed", "error"} and call not in tool_results:
                                    tool_results.add(call)
                                    yield self._chunk(request, tool_payload(part))
                        elif kind == "message.part.delta" and props.get("field") == "text":
                            pid = props["partID"]
                            if part_types.get(pid) == "text" and props.get("messageID") in assistant_messages:
                                delta = props.get("delta", "")
                                text_parts[pid] = text_parts.get(pid, "") + delta
                                yield self._chunk(request, {"event_type":"chat.delta", "content":delta})
                        elif kind == "permission.asked":
                            identity = props["id"]
                            session.pending[identity] = "permission"
                            session.control_replied.clear()
                            yield self._chunk(request, {
                                "event_type":"chat.ask_user_question", "request_id":identity, "source":"permission_interrupt",
                                "questions":[{"question":f"OpenCode {props['permission']}: " + ', '.join(props.get('patterns', [])),
                                    "options":[{"label":"允许一次","value":"allow_once"},{"label":"拒绝","value":"reject"}], "multiSelect":False}],
                            })
                            # The host owns one interaction gate per producer.
                            # Backpressure the sole SSE reader instead of letting
                            # parallel native tool approvals replace that gate.
                            await session.control_replied.wait()
                        elif kind == "question.asked":
                            identity = props["id"]; session.pending[identity] = "question"
                            session.control_replied.clear()
                            yield self._chunk(request, {"event_type":"chat.ask_user_question", "request_id":identity,
                                "source":"ask_user_interrupt", "questions":props.get("questions", [])})
                            await session.control_replied.wait()
                        elif kind == "session.idle":
                            if not assistant_complete:
                                if session.permission_denied:
                                    terminal = True
                                    yield self._chunk(request, {"event_type":"chat.error", "code":"permission_denied", "error":"Tool permission rejected"}, complete=True, outcome="error")
                                    return
                                raise RuntimeError("OpenCode became idle without a completed assistant message")
                            terminal = True
                            yield self._chunk(request, {"event_type":"chat.final", "content":"".join(text_parts.values()),
                                "invocation_status":"completed", "task_acceptance":"unknown"}, complete=True, outcome="completed")
                            return
                    raise RuntimeError("OpenCode event stream closed without a terminal event")
        except TimeoutError:
            # Only our explicitly configured budget can claim a Turn deadline.
            if not turn_budget.expired():
                raise RuntimeError("OpenCode native operation timed out") from None
            await self._abort_and_check(session)
            terminal = True
            # Reuse the existing successful-abort lifecycle projection to close
            # permission UI; timeout still ends the request as an error, not success.
            yield self._chunk(request, {"event_type":"chat.interrupt_result", "intent":"cancel",
                                       "success":True, "reason":"provider_timeout"})
            yield self._chunk(request, {"event_type":"chat.error", "code":"provider_timeout",
                "error":"OpenCode turn timed out while executing or waiting for approval"},
                complete=True, outcome="error")
        finally:
            if not terminal:
                # Keep the active owner if abort fails: do not allow another turn
                # to reuse a native session whose execution might still be running.
                try:
                    await self._abort_and_check(session)
                except BaseException:
                    session.abort_failed = True
                    raise
            session.active = False
            session.pending.clear()
            async with session.configuration_lock:
                try:
                    await self._apply_permissions(session)
                except Exception:
                    # Keep the completed turn intact; the next turn is fenced and
                    # the existing runtime snapshot reports the failed update.
                    session.permission_error = True

    async def _abort_and_check(self, session):
        """An abort RPC reply alone cannot release native execution ownership."""
        try:
            await self._call("POST", f"/session/{session.native_id}/abort", session=session)
            statuses = await self._call("GET", "/session/status", session=session)
            if not isinstance(statuses, dict):
                raise RuntimeError("OpenCode did not return native session status")
            # Official status.list omits idle sessions; this native identity
            # was already established by POST /session for this owner.
            status = statuses.get(session.native_id)
            if status is not None and status.get("type") != "idle":
                raise RuntimeError("OpenCode execution stop is unconfirmed")
        except BaseException:
            session.abort_failed = True
            raise
        session.abort_failed = False

    async def deliver_control_input_impl(self, request, inputs):
        session = self._sessions.get(request.session_id or "default")
        identity = request.params.get("request_id", "")
        if session is None or not session.active or identity not in session.pending:
            raise ValueError("No matching active OpenCode interaction")
        kind = session.pending[identity]
        answers = request.params.get("answers", [])
        if kind == "permission":
            if len(answers) != 1:
                raise ValueError("One permission answer is required")
            from jiuwenswarm.agents.harness.common.rails.interrupt.permission_options import resolve_permission_action
            selected = answers[0].get("selected_options", [])
            if selected and (not isinstance(selected, list) or len(selected) != 1):
                raise ValueError("One selected permission option is required")
            value = selected[0] if selected else answers[0].get("value") or answers[0].get("answer")
            value = resolve_permission_action(value)
            response = {"allow_once":"once", "reject":"reject"}.get(value)
            if response is None:
                raise ValueError("Only allow_once or reject is supported")
            body = {"reply":response}
        else:
            body = {"answers":[a.get("selected_options") or ([a["custom_input"]] if a.get("custom_input") else a.get("answers") or [a.get("answer", "")]) for a in answers]}
        # Claim the response before awaiting I/O so duplicate submissions cannot race.
        del session.pending[identity]
        if kind == "permission" and response == "reject":
            session.permission_denied = True
        await self._call("POST", f"/{kind}/{identity}/reply", body=body, session=session)
        yield self._chunk(request, {"event_type":"runtime.accepted", "control_request_id":identity}, complete=True)
        session.control_replied.set()

    async def process_message_impl(self, request, inputs):
        payloads = [chunk.payload async for chunk in self.process_message_stream_impl(request, inputs)]
        return AgentResponse(request.request_id, request.channel_id,
                             ok=not any(p.get("event_type") == "chat.error" for p in payloads),
                             payload={"content":next((p.get("content", "") for p in reversed(payloads) if p.get("event_type") == "chat.final"), ""), "chunks":payloads})

    async def process_interrupt(self, request):
        if request.params.get("intent", "cancel") != "cancel":
            raise ValueError("OpenCode pilot supports cancel, not pause/resume/supplement")
        session = self._sessions.get(request.session_id or "default")
        if session and session.active:
            await self._call("POST", f"/session/{session.native_id}/abort", session=session)
            session.cancelled = True
            session.control_replied.set()
        return AgentResponse(request.request_id, request.channel_id, payload={"event_type":"chat.interrupt_result", "intent":"cancel", "success":True})

    async def cleanup_session_adapter(self, session_id):
        session = self._sessions.get(session_id)
        if session is None:
            return False
        async with session.configuration_lock:
            if self._sessions.get(session_id) is not session:
                return False
            if session.active and session.abort_failed:
                await self._call("POST", f"/session/{session.native_id}/abort", session=session)
                session.active, session.abort_failed = False, False
            if session.active:
                raise RuntimeError("Cancel and drain the producer before disposing its session")
            if session.service:
                try:
                    self._save_binding(session)
                finally:
                    await session.service.close()
                    del self._sessions[session_id]
            else:
                await self._call("DELETE", f"/session/{session.native_id}", session=session)
                del self._sessions[session_id]
            return True

    async def cleanup(self):
        for sid in list(self._sessions):
            await self.cleanup_session_adapter(sid)
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._configured = False
        self._executable = None

    @staticmethod
    def _read_permission_profile(config):
        permissions = config.get("permissions") or {}
        if permissions.get("enabled") is False:
            return "full_access"
        return "automatic" if permissions.get("mode") == "auto" else "default"

    def runtime_permission_status(self, session_id):
        session = self._sessions.get(session_id)
        desired = session.desired_permission if session else self._permission_profile
        effective = session.effective_permission if session else None
        supported = list(self.permission_profiles) if self._executable else []
        state = "not_started"
        if desired not in supported:
            state = "unsupported"
        elif session:
            state = "failed" if session.permission_error else "applied" if effective == desired else "pending"
        return {"supported_profiles": supported, "update_timing": "idle",
                "desired_profile": desired, "effective_profile": effective, "state": state}

    async def _apply_permissions(self, session):
        if not session.service:
            if session.desired_permission != "default":
                raise ValueError("Borrowed OpenCode servers do not support permission profile updates")
            return  # Existing borrowed-server policy is unknown, never claim it applied.
        if session.desired_permission not in self.permission_profiles:
            session.permission_error = True
            raise ValueError("OpenCode does not support Automatic permissions; select Default or Full Access")
        if session.effective_permission == session.desired_permission and not session.permission_error:
            return
        if session.active or session.abort_failed:
            return
        profile = session.desired_permission
        session.effective_permission = None
        try:
            from .opencode_service import permission_config
            # A private service restart also clears native in-memory remembered
            # grants. Its database and session identity remain unchanged.
            await session.service.configure(session.equipment, permission_profile=profile)
            before = await self._call("GET", f"/session/{session.native_id}", session=session)
            previous = before.get("permission", [])
            if before.get("id") != session.native_id or not isinstance(previous, list):
                raise ValueError("OpenCode permission readback is invalid")
            rules = []
            for permission, value in permission_config(session.equipment, profile).items():
                for pattern, action in (value.items() if isinstance(value, dict) else [("*", value)]):
                    rules.append({"permission": permission, "pattern": pattern, "action": action})
            # Official 1.18.18 appends rules, with the last matching rule winning.
            if len(previous) + len(rules) > 4096:
                raise ValueError("OpenCode permission history limit reached; create a new session")
            expected = previous
            if previous[-len(rules):] != rules:
                expected = previous + rules
                await self._call("PATCH", f"/session/{session.native_id}", body={"permission": rules}, session=session)
            after = await self._call("GET", f"/session/{session.native_id}", session=session)
            if after.get("id") != session.native_id or after.get("permission") != expected:
                raise ValueError("OpenCode did not confirm the requested permissions")
            session.effective_permission = profile
            session.permission_error = False
        except BaseException:
            session.permission_error = True
            raise

    async def reload_agent_config(self, config_base=None, env_overrides=None,
                                  target_session_id=None, reload_scopes=None):
        if reload_scopes and "permissions" not in reload_scopes:
            return  # Equipment/model snapshots are reconciled at the existing turn boundary.
        from jiuwenswarm.common.config import get_config
        profile = self._read_permission_profile(config_base if config_base is not None else get_config())
        if target_session_id is None:
            self._permission_profile = profile
        sessions = [(sid, session) for sid, session in self._sessions.items()
                    if target_session_id is None or sid == target_session_id]
        # Publish intent to every owned session before I/O. One failure must not
        # leave another session able to start with a silently stale policy.
        for _, session in sessions:
            session.desired_permission = profile
            self._save_binding(session)
        for sid, session in sessions:
            async with session.configuration_lock:
                if self._sessions.get(sid) is not session:
                    continue
                if not session.active and not session.abort_failed:
                    try:
                        await self._apply_permissions(session)
                    except Exception:
                        session.permission_error = True


    async def handle_user_answer(self, request):
        raise ValueError("Use the active session control input channel")

    async def handle_swarmflow_reply(self, request):
        raise ValueError("OpenCode pilot does not support Team")

    async def handle_heartbeat(self, request):
        raise ValueError("OpenCode pilot does not support heartbeat")


def provider_error_payload(error, scope):
    """Expose a fixed diagnostic category, never the native body or stack.

    A TLS verification error can also represent a transient handshake failure.
    It is not evidence of an expired certificate and must not trigger retries
    or a verification bypass in the adapter.
    """
    payload = {"event_type": "chat.error", "error": f"OpenCode reported a {scope} error",
               "provider_error_type": safe_error_type(error)}
    data = error.get("data") if isinstance(error, dict) else None
    message = data.get("message") if isinstance(data, dict) else None
    message = message.strip().lower().removeprefix("error: ") if isinstance(message, str) else None
    tls_messages = {
        "unable to verify the first certificate",
        "unable to get local issuer certificate", "self signed certificate",
        "self-signed certificate", "self signed certificate in certificate chain",
        "certificate has expired", "certificate is not yet valid",
    }
    if message == "unknown certificate verification error":
        payload.update(code="provider_tls_connection_failed", error=(
            "OpenCode model TLS connection failed during handshake or certificate verification. "
            "Check network/proxy connectivity and certificate trust; verification remains enabled."
        ))
    elif message in tls_messages:
        payload.update(code="provider_tls_verification_failed", error=(
            "OpenCode could not verify the model connection's TLS certificate. "
            "Check the certificate chain and network trust configuration; verification remains enabled."
        ))
    return payload


def safe_error_type(error):
    # Official discriminants only; never expose model error bodies or credentials.
    name = error.get("name") if isinstance(error, dict) else None
    return name if name in {"APIError", "ProviderAuthError", "UnknownError", "MessageOutputLengthError", "ContextOverflowError", "StructuredOutputError"} else "unknown"


# Preserve the existing import while discovery uses a lightweight entry point.
from jiuwenswarm.common.external_adapter_factories import create_opencode as create
