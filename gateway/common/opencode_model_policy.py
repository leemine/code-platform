"""Credential-free view of the models declared in a managed OpenCode server."""

import json
import os

MODEL_POLICY_ENV = "JIUWENSWARM_OPENCODE_MODEL_POLICY"
NATIVE_MODEL_PREFIX = "opencode:"


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
