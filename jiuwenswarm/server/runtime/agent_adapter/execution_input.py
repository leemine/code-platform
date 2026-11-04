"""Host-owned facts for an existing Facade execution, never a wire payload.

Native keeps its existing input path. External adapters opt in with a policy;
their native protocol checks and session/resource ownership remain local.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from gateway.common.model_selection import ModelSelection, ResolvedModel


@dataclass(frozen=True)
class AdapterCapabilities:
    """Implemented integration capabilities, not the native SDK's full feature set."""
    equipment: frozenset[str] = frozenset()
    main_instructions: bool = False
    user_questions: bool = False
    native_resume: bool = False
    context_usage: bool = False
    manual_compaction: bool = False


def require_capability(adapter, name: str) -> None:
    capabilities = getattr(adapter, "capabilities", None)
    if isinstance(capabilities, AdapterCapabilities) and not getattr(capabilities, name):
        raise ValueError(f"provider_capability_unsupported: {name}")


def admit_equipment(adapter, params) -> None:
    capabilities = getattr(adapter, "capabilities", None)
    if isinstance(capabilities, AdapterCapabilities):
        selected = {name for name in ("agent_template_name", "plugin_names", "skills", "mcp") if params.get(name)}
        if selected - capabilities.equipment:
            raise ValueError("Provider does not support this equipment yet")


@dataclass(frozen=True)
class ExecutionInputPolicy:
    require_model: bool = True
    include_model_catalog: bool = False
    strip_agentos_max_tokens: bool = False
    catalog_settings_key: str | None = None
    bound_directory: str | None = None


@dataclass(frozen=True)
class SessionFacts:
    storage_dir: Path
    has_assistant_history: bool


@dataclass(frozen=True)
class ExecutionInput:
    request_id: str
    session_id: str
    directory: str | None
    session: SessionFacts
    model: ResolvedModel | None = field(repr=False)
    models: tuple[ResolvedModel, ...] = field(default=(), repr=False)
    model_settings: dict = field(default_factory=dict, repr=False)


def session_facts(session_id: str, *, active: bool = False) -> SessionFacts:
    from jiuwenswarm.common.utils import get_agent_sessions_dir
    from jiuwenswarm.server.runtime.session.session_history import read_session_history_records
    history = False if active else any(
        row.get("role") == "assistant" and row.get("event_type") != "chat.request_completed"
        for row in read_session_history_records(session_id)
    )
    return SessionFacts(get_agent_sessions_dir(), history)


def request_defaults(*, model_client_config, model_config_obj, model_name,
                     strip_agentos_max_tokens=False):
    from jiuwenswarm.common.reasoning_injector import inject_reasoning_params
    values = inject_reasoning_params(
        model_client_config={**model_client_config, "model_name": model_name},
        model_config_obj=model_config_obj,
    )
    if strip_agentos_max_tokens and values.get("_source") == "agentos":
        values.pop("max_tokens", None)
    for key in ("model", "model_name", "_source", "context_window"):
        values.pop(key, None)
    return values


def model_resolver(catalog=None, *, strip_agentos_max_tokens=False):
    from functools import partial
    from jiuwenswarm.common.model_routing_registry import ModelSelectionResolver
    return ModelSelectionResolver(catalog, request_config_builder=partial(
        request_defaults, strip_agentos_max_tokens=strip_agentos_max_tokens))


def resolve_model(request, *, strip_agentos_max_tokens=False, catalog=None):
    from jiuwenswarm.common.model_routing_registry import ModelExecutionContext
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_metadata
    saved = get_session_metadata(request.session_id or "", enable_writeback=False)
    params = request.params or {}
    raw = params.get("model_selection") or saved.get("model_selection")
    return model_resolver(catalog, strip_agentos_max_tokens=strip_agentos_max_tokens).resolve(
        ModelSelection.model_validate(raw) if raw else None,
        ModelExecutionContext(legacy_model_name=params.get("model_name") or saved.get("model")),
    )


def prepare_execution_input(adapter, request, inputs, *, config=None) -> ExecutionInput:
    from copy import deepcopy
    from jiuwenswarm.common.model_catalog import ModelCatalog
    policy = adapter.execution_input_policy(request)
    sid = request.session_id or "default"
    directory = inputs.get("workspace_dir") or inputs.get("project_dir") or inputs.get("cwd") or policy.bound_directory
    if not directory:
        from jiuwenswarm.common.utils import get_default_project_session_workspace_dir
        directory = get_default_project_session_workspace_dir()
    path = Path(directory).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("Execution requires an existing absolute project directory")
    # One catalog instance pins resolution and the owned service's configuration.
    catalog = ModelCatalog(config) if policy.require_model or policy.include_model_catalog else None
    model = resolve_model(request, catalog=catalog,
                          strip_agentos_max_tokens=policy.strip_agentos_max_tokens) if policy.require_model else None
    models = ()
    settings = {}
    if policy.include_model_catalog:
        resolver = model_resolver(catalog, strip_agentos_max_tokens=policy.strip_agentos_max_tokens)
        models = tuple(resolver.resolve(ModelSelection(type="model", id=item["model_id"]))
                       for item in catalog.list_public_models())
        settings = deepcopy(catalog.config.get(policy.catalog_settings_key, {})) if policy.catalog_settings_key else {}
    return ExecutionInput(
        request.request_id, sid,
        str(path.resolve()),
        session_facts(sid, active=adapter.has_session_runtime(sid)),
        model.model_copy(deep=True) if isinstance(model, ResolvedModel) else model,
        tuple(item.model_copy(deep=True) for item in models), settings,
    )


def prepared_input(request, inputs) -> ExecutionInput | None:
    value = inputs.get("_host_execution")
    if value is None:  # Compatibility for direct AgentAdapter users.
        return None
    if (not isinstance(value, ExecutionInput) or value.request_id != request.request_id
            or value.session_id != (request.session_id or "default")):
        raise ValueError("Execution input does not belong to this request")
    return value
