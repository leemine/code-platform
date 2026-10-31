"""Codex settings projected from existing Third-party Agents and model services."""
from __future__ import annotations

import importlib.metadata
import json
from urllib.parse import urlparse


def config_snapshot(config: dict) -> dict:
    entries = config.get("modes", {}).get("team", {}).get("jiuwen_team", {}).get("external_cli_agents", [])
    matches = [item for item in entries if item == "codex" or isinstance(item, dict) and item.get("cli_agent") == "codex"]
    if len(matches) > 1:
        raise ValueError("Duplicate Codex configuration")
    entry = matches[0] if matches else None
    values = dict(entry) if isinstance(entry, dict) else {}
    cli_path = values.get("cli_path") or values.get("codex_bin") or ""
    if not isinstance(cli_path, str):
        raise ValueError("Codex CLI path must be a string")
    return {"codex": {"enabled": entry is not None, "cli_path": cli_path.strip() or None}}


def availability(config: dict) -> str | None:
    if not config_snapshot(config)["codex"]["enabled"]:
        return "disabled"
    try:
        # The official SDK owns CLI discovery and compatibility. A tested lock
        # is not a runtime allowlist, and an explicit CLI need not be bundled.
        importlib.metadata.version("openai-codex")
    except importlib.metadata.PackageNotFoundError:
        return "sdk_not_installed"
    return None


def resolve_model(request):
    from gateway.common.model_selection import ModelSelection, ResolvedModel
    from jiuwenswarm.common.model_routing_registry import ModelExecutionContext, ModelSelectionResolver
    from jiuwenswarm.common.reasoning_injector import inject_reasoning_params
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_metadata

    def defaults(*, model_client_config, model_config_obj, model_name):
        result = inject_reasoning_params(model_client_config={**model_client_config, "model_name": model_name},
                                        model_config_obj=model_config_obj)
        for key in ("model", "model_name", "_source", "context_window"):
            result.pop(key, None)
        return result

    saved = get_session_metadata(request.session_id or "", enable_writeback=False)
    params = request.params or {}
    raw = params.get("model_selection") or saved.get("model_selection")
    model = ModelSelectionResolver(request_config_builder=defaults).resolve(
        ModelSelection.model_validate(raw) if raw else None,
        ModelExecutionContext(legacy_model_name=params.get("model_name") or saved.get("model")),
    )
    if not isinstance(model, ResolvedModel):
        raise ValueError("Codex requires a single model from Swarm model services")
    parsed = urlparse(model.api_base)
    if model.provider.lower() != "openai" or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Codex requires an OpenAI Responses-compatible model endpoint")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote Codex model endpoints require HTTPS")
    unsupported = set(model.client_options) - {"verify_ssl", "timeout"}
    if unsupported or model.request_defaults:
        raise ValueError("Codex does not support the selected model's request options")
    if model.client_options.get("verify_ssl") is False:
        raise ValueError("Codex requires TLS verification")
    return model


def model_overrides(model) -> tuple[str, ...]:
    values = [
        'model_provider="swarm"',
        'model_providers.swarm.name="Swarm model service"',
        'model_providers.swarm.wire_api="responses"',
        'model_providers.swarm.requires_openai_auth=false',
        "model_providers.swarm.base_url=" + json.dumps(model.api_base),
    ]
    if model.api_key:
        values.append('model_providers.swarm.env_key="SWARM_CODEX_MODEL_KEY"')
    return tuple(values)
