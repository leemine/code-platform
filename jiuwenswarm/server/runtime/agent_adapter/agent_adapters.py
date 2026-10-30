# Copyright (c) Huawei Technologies, Co., Ltd. 2025. All rights reserved.

"""Unified adapter protocol for JiuWenSwarm SDK backends.

Defines the minimal interface every SDK adapter must implement so that
the Facade (interface.py) can drive any backend without knowing its
internal structure.
"""

from __future__ import annotations

import logging
import os
from importlib.metadata import entry_points
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponse, AgentResponseChunk
from jiuwenswarm.server.runtime.agent_adapter.user_turn import UserTurn

logger = logging.getLogger(__name__)

_SDK_ENV_VAR = "JIUWENSWARM_AGENT_SDK"
_DEFAULT_SDK = "harness"
_ADAPTER_ENTRY_POINT_GROUP = "jiuwenswarm.agent_adapters"


def _installed_adapter_factory(sdk: str):
    """Resolve an explicitly selected installed adapter, without loading others."""
    matches = tuple(entry_points(group=_ADAPTER_ENTRY_POINT_GROUP, name=sdk))
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous installed AgentAdapter: {sdk}")
    if not matches:
        return None
    return matches[0]


@runtime_checkable
class AgentAdapter(Protocol):
    """Minimal capability set every SDK adapter must satisfy.

    The Facade (JiuWenSwarm) depends only on this interface; individual
    adapter modules implement it without any coupling to each other.
    """

    def build_query(self, request: AgentRequest, turn: UserTurn) -> tuple[Any, UserTurn]:
        """Return the provider query and effective UserTurn; never fall back to Native."""
        ...

    def deliver_control_input_impl(
        self, request: AgentRequest, inputs: dict[str, Any]
    ) -> AsyncIterator[AgentResponseChunk]:
        """Answer an active interaction without starting another execution."""
        ...

    async def prepare_session(self, *, session_id: str, channel_id: str,
                              mode: str, project_dir: str | None = None) -> None:
        """Bind session resources without sending a prompt."""
        ...

    def has_session_runtime(self, session_id: str | None = None) -> bool:
        """Report only already-owned resources, without creating a session."""
        ...

    async def cleanup_session_adapter(self, session_id: str) -> bool:
        """Release session resources after the host drains its producer."""
        ...

    async def cleanup(self) -> None:
        """Release all adapter-owned resources; failure remains retryable."""
        ...

    async def create_instance(self, config: dict[str, Any] | None = None, *,
                              mode: str = "claw", sub_mode: str = None) -> None:
        """Initialise the underlying SDK agent from config.

        Called once on startup and again after skill install/uninstall.
        """
        ...

    async def reload_agent_config(
        self,
        config_base: dict[str, Any] | None = None,
        env_overrides: dict[str, Any] | None = None,
        target_session_id: str | None = None,
        reload_scopes: set[str] | None = None,
    ) -> None:
        """Hot-reload configuration without restarting the process.

        Args:
            config_base: Optional complete config snapshot; if provided, use it instead of reading local config.yaml.
            env_overrides: Optional environment variable overrides; only override keys present in the request.
            target_session_id: Optional session id to limit session-scoped reload fan-out.
            reload_scopes: Optional exact configuration scopes for targeted reloads.
        """
        ...

    async def process_message_impl(
            self, request: AgentRequest, inputs: dict[str, Any]
    ) -> AgentResponse:
        """Execute a single non-streaming request and return the response.

        Args:
            request: AgentRequest object.
            inputs: Pre-built inputs dict with conversation_id and query.
        """
        ...

    async def process_message_stream_impl(
            self, request: AgentRequest, inputs: dict[str, Any]
    ) -> AsyncIterator[AgentResponseChunk]:
        """Execute a streaming request; yield response chunks.

        Args:
            request: AgentRequest object.
            inputs: Pre-built inputs dict with conversation_id and query.
        """
        ...

    async def process_interrupt(self, request: AgentRequest) -> AgentResponse:
        """Handle interrupt requests (pause/resume/cancel/supplement)."""
        ...

    async def handle_user_answer(self, request: AgentRequest) -> AgentResponse:
        """Handle user answer for evolution approval or permission approval."""
        ...

    async def handle_swarmflow_reply(self, request: AgentRequest) -> AgentResponse:
        """Handle a person's reply to a pending swarmflow human-session turn.

        Builds a HumanAgentMessage(target="swarmflow:<run_id>:<corr>") and
        delivers it via team_manager.interact (the agent-core thin route).
        """
        ...

    async def handle_heartbeat(self, request: AgentRequest) -> AgentResponse:
        """Handle heartbeat requests."""


@runtime_checkable
class PermissionAwareAdapter(Protocol):
    """Optional read-only projection; config/reload remains the policy authority.

    Report supported_profiles, update_timing, desired_profile, effective_profile
    (None until confirmed), and state (not_started/pending/applied/failed/unsupported).
    Provider-native rules and enforcement stay inside the adapter.
    """

    def runtime_permission_status(self, session_id: str) -> dict[str, Any]:
        ...


def resolve_sdk_choice(value: str | None = None) -> str:
    """Resolve SDK choice from environment variable.

    Returns:
        SDK name: 'harness', or 'pi' (reserved).

    Behavior:
        - If env var is unset or empty: return 'harness' (default).
        - If env var is 'pi': return 'pi' (not yet implemented).
        - An explicit unknown backend is rejected; never switch execution engines.
    """
    raw = (os.getenv(_SDK_ENV_VAR, "") if value is None else value).strip().lower()
    if not raw:
        logger.debug("[SDK] %s not set, using default: %s", _SDK_ENV_VAR, _DEFAULT_SDK)
        return _DEFAULT_SDK

    valid_sdks = {"harness", "pi"}
    if raw in valid_sdks:
        logger.info("[SDK] Resolved SDK: %s", raw)
        return raw

    if _installed_adapter_factory(raw) is not None:
        return raw

    raise RuntimeError(f"Unknown SDK: {raw}")


def create_adapter(sdk: str | None = None, *, mode: str = "agent") -> AgentAdapter:
    """Factory function to create SDK adapter instance.

    Args:
        sdk: SDK name, if None will resolve from environment.
        mode: Instance mode, "agent" (default) or "code".

    Returns:
        AgentAdapter instance for the specified SDK and mode.

    Raises:
        NotImplementedError: If SDK is 'pi' (not yet implemented).
        RuntimeError: If SDK is unknown.
    """
    sdk_name = sdk or resolve_sdk_choice()

    if sdk_name == "harness":
        if mode == "code":
            from jiuwenswarm.server.runtime.agent_adapter.interface_code import JiuwenSwarmCodeAdapter
            return JiuwenSwarmCodeAdapter()
        from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter
        return JiuWenSwarmDeepAdapter()

    if sdk_name == "pi":
        raise NotImplementedError(
            f"SDK '{sdk_name}' is not yet implemented. "
            f"Currently supported: harness"
        )

    entry_point = _installed_adapter_factory(sdk_name)
    if entry_point is not None:
        factory = entry_point.load()
        adapter = factory(mode=mode)
        if not isinstance(adapter, AgentAdapter):
            raise TypeError(f"Installed adapter does not implement AgentAdapter: {sdk_name}")
        return adapter

    raise RuntimeError(
        f"Unknown SDK '{sdk_name}'. Supported: harness, pi (reserved)"
    )
