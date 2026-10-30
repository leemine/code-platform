"""Immutable session adapter selection on the existing metadata boundary."""
from gateway.common.mode_matrix import deprecate_mode, NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL
from jiuwenswarm.server.runtime.agent_adapter.agent_adapters import resolve_sdk_choice
from jiuwenswarm.server.runtime.session.session_metadata import get_session_metadata, update_session_metadata


def select_session_provider(session_id, requested=None, *, default="harness", mode="agent", bind=False):
    if requested is not None and (not isinstance(requested, str) or not requested.strip()):
        raise ValueError("execution_provider must be a nonempty string")
    metadata = get_session_metadata(session_id, cache_bust=True, enable_writeback=False) if session_id else {}
    stored = metadata.get("execution_provider")
    # Legacy conversations with recorded work belong to the existing Native path.
    if not stored and (metadata.get("message_count", 0) or metadata.get("session_runtime_binding")):
        stored = "harness"
    selected = resolve_sdk_choice(stored or requested or default)
    if requested is not None and resolve_sdk_choice(requested) != selected:
        raise ValueError("execution_provider_locked:new_session_required")
    if selected != "harness" and deprecate_mode(mode) not in {NEW_AGENT_WORK_NORMAL, NEW_AGENT_CODE_NORMAL}:
        raise ValueError("execution_provider_requires_single_agent")
    if bind and session_id and not metadata.get("execution_provider"):
        update_session_metadata(session_id=session_id, execution_provider=selected, sync_write=True,
                                touch_last_message_at=False)
        current = get_session_metadata(session_id, cache_bust=True, enable_writeback=False)
        if current.get("execution_provider") != selected:
            raise ValueError("execution_provider_locked:new_session_required")
    return selected
