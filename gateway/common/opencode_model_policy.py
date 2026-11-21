"""Credential-free view of the models declared in a managed OpenCode server."""

import hashlib
import json
import os
import re
from urllib.parse import urlsplit

MODEL_POLICY_ENV = "JIUWENSWARM_OPENCODE_MODEL_POLICY"
NATIVE_MODEL_PREFIX = "opencode:"


def base_permission_rules(action: str) -> dict[str, str]:
    return {"*": action, "task": "deny", "question": "allow"}


def deployment_model_policy(config: dict) -> dict:
    models = {
        f"{provider_id}/{model_id}": str(definition.get("name") or model_id)
        for provider_id, provider in config.get("provider", {}).items()
        for model_id, definition in provider.get("models", {}).items()
    }
    default = config.get("model")
    if default is not None and (not isinstance(default, str) or default not in models):
        raise ValueError("Managed OpenCode default model must be declared in the Provider model configuration")
    return {"default": default, "models": models}


def worker_model_policy() -> dict | None:
    value = os.environ.get(MODEL_POLICY_ENV)
    return json.loads(value) if value else None


def native_model_reference(selection) -> str | None:
    if selection is not None and selection.type == "model" and selection.id.startswith(NATIVE_MODEL_PREFIX):
        return selection.id[len(NATIVE_MODEL_PREFIX):]
    return None


def native_model_binding(reference: str, policy: dict) -> dict[str, str]:
    if reference not in policy["models"]:
        raise ValueError("opencode_model_not_registered")
    provider, _, model = reference.partition("/")
    return {"providerID": provider, "modelID": model}


def account_models_revision(providers: dict) -> str:
    return hashlib.sha256(json.dumps(providers, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_account_providers(providers: dict) -> None:
    """Accept only literal OpenAI-compatible model entries emitted by the account projector."""
    if not isinstance(providers, dict):
        raise ValueError("opencode_shared_model_options_unsupported")
    for key, entry in providers.items():
        if (not re.fullmatch(r"swarm-[0-9a-f]{24}", key) or not isinstance(entry, dict)
                or set(entry) != {"npm", "name", "options", "models"}
                or entry["npm"] != "@ai-sdk/openai-compatible" or entry["name"] != "Swarm configured model"):
            raise ValueError("opencode_shared_model_options_unsupported")
        options, models = entry["options"], entry["models"]
        if (not isinstance(options, dict) or not {"baseURL", "apiKey"} <= options.keys()
                or options.keys() - {"baseURL", "apiKey", "timeout", "headerTimeout", "chunkTimeout"}
                or not isinstance(models, dict) or len(models) != 1):
            raise ValueError("opencode_shared_model_options_unsupported")
        model = next(iter(models))
        if (not model or models[model] != {"name": model}
                or any(not isinstance(v, str) or "{env:" in v or "{file:" in v
                       for v in (model, options["baseURL"], options["apiKey"]))
                or any(type(v) is not int or v <= 0 for k, v in options.items() if k not in {"baseURL", "apiKey"})):
            raise ValueError("opencode_shared_model_options_unsupported")
        url = urlsplit(options["baseURL"])
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ValueError("opencode_shared_model_protocol_unsupported")
