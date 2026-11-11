"""Codex settings projected from existing Third-party Agents and model services."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
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
    settings = {"enabled": entry is not None, "cli_path": cli_path.strip() or None}
    catalog = values.get("model_catalog_json")
    if catalog is not None:
        if not isinstance(catalog, str) or not Path(catalog).is_absolute():
            raise ValueError("Codex model_catalog_json must be an absolute file path")
        settings["model_catalog_json"] = catalog
    idle = values.get("stream_idle_timeout_ms")
    if idle is not None:
        if type(idle) is not int or idle <= 0:
            raise ValueError("Codex stream_idle_timeout_ms must be a positive integer")
        settings["stream_idle_timeout_ms"] = idle
    return {"codex": settings}


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
    from jiuwenswarm.server.runtime.agent_adapter.execution_input import resolve_model as resolve_host_model
    return validate_model(resolve_host_model(request))


def validate_model(model):
    from gateway.common.model_selection import ResolvedModel
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
    # Swarm HTTP-client options do not control the official CLI transport.
    # Leave TLS verification and CA trust to Codex; never project an insecure override.
    return model


def model_overrides(model, settings=None) -> tuple[str, ...]:
    values = [
        'model_provider="swarm"',
        'model_providers.swarm.name="Swarm model service"',
        'model_providers.swarm.wire_api="responses"',
        'model_providers.swarm.requires_openai_auth=false',
        "model_providers.swarm.base_url=" + json.dumps(model.api_base),
    ]
    if model.context_window is not None:
        values.append(f"model_context_window={model.context_window}")
    if model.api_key:
        values.append('model_providers.swarm.env_key="SWARM_CODEX_MODEL_KEY"')
    idle = (settings or {}).get("stream_idle_timeout_ms")
    if idle is not None:
        if type(idle) is not int or idle <= 0:
            raise ValueError("Codex stream_idle_timeout_ms must be a positive integer")
        values.append(f"model_providers.swarm.stream_idle_timeout_ms={idle}")
    return tuple(values)
