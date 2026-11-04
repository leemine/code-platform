"""Claude settings use the existing Third-party Agents and model catalog."""
import importlib.metadata
import math
from urllib.parse import urlparse


def config_snapshot(config):
    entries = config.get("modes", {}).get("team", {}).get("jiuwen_team", {}).get("external_cli_agents", [])
    matches = [item for item in entries if item == "claude" or isinstance(item, dict) and item.get("cli_agent") == "claude"]
    if len(matches) > 1:
        raise ValueError("Duplicate Claude configuration")
    values = matches[0] if matches and isinstance(matches[0], dict) else {}
    path = values.get("cli_path") or ""
    if not isinstance(path, str):
        raise ValueError("Claude CLI path must be a string")
    settings = {"enabled": bool(matches), "cli_path": path.strip() or None}
    for key in ("stream_first_byte_timeout_ms", "stream_idle_timeout_ms"):
        value = values.get(key)
        if value is not None:
            if type(value) is not int or value <= 0:
                raise ValueError(f"Claude {key} must be a positive integer")
            settings[key] = value
    return {"claude": settings}


def native_timeout_env(settings, model):
    """Configure native model transport, never the lifetime of a tool Turn."""
    env = {}
    timeout = model.client_options.get("timeout")
    if timeout is not None:
        if isinstance(timeout, bool):
            raise ValueError("Claude model timeout must be positive and finite")
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0 or timeout * 1000 > 2147483647:
            raise ValueError("Claude model timeout must be positive and within the native range")
        env["API_TIMEOUT_MS"] = str(math.ceil(timeout * 1000))
    for key, name in (("stream_first_byte_timeout_ms", "CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS"),
                      ("stream_idle_timeout_ms", "CLAUDE_STREAM_IDLE_TIMEOUT_MS")):
        value = settings.get(key)
        if value is not None:
            if type(value) is not int or value <= 0:
                raise ValueError(f"Claude {key} must be a positive integer")
            env[name] = str(value)
    return env


def availability(config):
    if not config_snapshot(config)["claude"]["enabled"]:
        return "disabled"
    try:
        importlib.metadata.version("claude-agent-sdk")
    except importlib.metadata.PackageNotFoundError:
        return "sdk_not_installed"
    return None


def resolve_model(request):
    from jiuwenswarm.server.runtime.agent_adapter.execution_input import resolve_model as resolve_host_model
    return validate_model(resolve_host_model(request))


def validate_model(model):
    from gateway.common.model_selection import ResolvedModel
    if not isinstance(model, ResolvedModel):
        raise ValueError("Claude requires a single model from Swarm model services")
    parsed = urlparse(model.api_base)
    if model.provider.lower() != "anthropic" or parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Claude requires an Anthropic Messages-compatible model endpoint in Swarm settings")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote Claude model endpoints require HTTPS")
    if set(model.client_options) - {"verify_ssl", "timeout"} or model.request_defaults:
        raise ValueError("Claude does not support the selected model's request options")
    if model.client_options.get("verify_ssl") is False:
        raise ValueError("Claude requires TLS verification")
    if not model.api_key:
        raise ValueError("Configure Claude model authentication in Swarm model services")
    return model
