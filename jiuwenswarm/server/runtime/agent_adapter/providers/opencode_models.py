"""Translate the existing Swarm model catalog to official OpenCode configuration.

Owned services consume the projection at startup. Managed Workers reconcile it
through the account-authenticated Gateway. Fixed-URL services remain operator-managed.
"""
from __future__ import annotations

import hashlib
import math

from gateway.common.model_selection import ModelSelection, ResolvedModel
from jiuwenswarm.common.model_catalog import ModelCatalog


def _resolver(catalog=None):
    from ..execution_input import model_resolver
    return model_resolver(catalog, strip_agentos_max_tokens=True)


def model_binding(model: ResolvedModel) -> dict[str, str]:
    # Include connection/config revision so stale server snapshots fail explicitly.
    revision = hashlib.sha256(model.model_dump_json().encode()).hexdigest()[:24]
    return {"providerID": f"swarm-{revision}", "modelID": model.model_name}


def provider_config(model: ResolvedModel, settings=None) -> dict:
    if model.provider.lower() != 'openai' or not model.api_base:
        raise ValueError('opencode_shared_model_protocol_unsupported')
    unsupported = set(model.client_options) - {'timeout', 'verify_ssl'}
    if unsupported or model.request_defaults:
        raise ValueError('opencode_shared_model_options_unsupported')
    # TLS verification remains enabled; never translate verify_ssl=False to a bypass.
    options = {"baseURL": model.api_base, "apiKey": model.api_key}
    if model.client_options.get('timeout') is not None:
        raw = model.client_options['timeout']
        value = float(raw)
        if isinstance(raw, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError('OpenCode model timeout must be positive and finite')
        options['timeout'] = math.ceil(value * 1000)
    for key, native in (('header_timeout_ms', 'headerTimeout'), ('chunk_timeout_ms', 'chunkTimeout')):
        value = (settings or {}).get(key)
        if value is not None:
            if type(value) is not int or value <= 0:
                raise ValueError(f'OpenCode {key} must be a positive integer')
            options[native] = value
    return {
        "npm": "@ai-sdk/openai-compatible", "name": "Swarm configured model",
        "options": options, "models": {model.model_name: {"name": model.model_name}},
    }


def _provider_entry(model, settings):
    if not isinstance(model, ResolvedModel):
        raise ValueError("opencode_shared_model_group_unsupported")
    binding = model_binding(model)
    return binding, {binding["providerID"]: provider_config(model, settings)}


def build_server_model_config(config: dict | None = None, *, models=None, settings=None) -> tuple[dict, list[str]]:
    """Return a private official config fragment and unsupported catalog IDs.

    This fragment contains credentials: pass via normal private configuration,
    never send it to the UI, logs or a shared service configuration endpoint.
    """
    if models is None:
        catalog = ModelCatalog(config)
        resolver = _resolver(catalog)
        models = [resolver.resolve(ModelSelection(type='model', id=item['model_id']))
                  for item in catalog.list_public_models()]
        settings = catalog.config.get('opencode', {})
    providers, unsupported = {}, []
    for model in models:
        try:
            _, entry = _provider_entry(model, settings)
            providers.update(entry)
        except ValueError as exc:
            if str(exc) not in {'opencode_shared_model_protocol_unsupported', 'opencode_shared_model_options_unsupported'}:
                raise
            unsupported.append(model.model_id)
    return {"provider": providers}, unsupported


def resolve_request_model(request) -> tuple[ResolvedModel, dict[str, str]]:
    from ..execution_input import resolve_model
    return validate_request_model(resolve_model(request, strip_agentos_max_tokens=True))


def validate_request_model(model) -> tuple[ResolvedModel, dict[str, str]]:
    if not isinstance(model, ResolvedModel):
        raise ValueError('opencode_shared_model_group_unsupported')
    provider_config(model)
    return model, model_binding(model)


def _managed_entry(model, catalog):
    from gateway.common.opencode_model_policy import validate_account_providers

    binding, entry = _provider_entry(model, catalog.config.get("opencode", {}))
    validate_account_providers(entry)
    return binding, entry


def account_model_providers(catalog):
    """Project eligible account entries independently, so an unsupported entry cannot block its peers."""
    from jiuwenswarm.common.model_errors import ModelSelectionError

    providers = {}
    resolver = _resolver(catalog)
    for entry in catalog.list_public_models():
        try:
            selection = ModelSelection(type="model", id=entry["model_id"])
            model = resolver.resolve(selection)
            _, entry_config = _managed_entry(model, catalog)
            providers.update(entry_config)
        except (ValueError, ModelSelectionError):
            continue
    return providers


def managed_model_binding(policy, selection=None, *, model_name=None, catalog=None):
    from gateway.common.opencode_model_policy import deployment_model_policy, native_model_binding, native_model_reference
    from jiuwenswarm.common.model_routing_registry import ModelExecutionContext

    if policy.get("error"):
        raise ValueError(policy["error"])
    reference = native_model_reference(selection)
    if reference is not None:
        if policy.get("account_model_sync") and reference not in policy["models"]:
            # Older clients send the native default ID returned by config.get.
            entries = account_model_providers(catalog or ModelCatalog())
            return native_model_binding(reference, deployment_model_policy({"provider": entries}))
        return native_model_binding(reference, policy)
    catalog = catalog or ModelCatalog()
    resolved = _resolver(catalog).resolve(selection, ModelExecutionContext(legacy_model_name=model_name))
    if policy.get("account_model_sync"):
        binding, _ = _managed_entry(resolved, catalog)
        return binding
    _, binding = validate_request_model(resolved)
    return native_model_binding(f"{binding['providerID']}/{binding['modelID']}", policy)


def public_managed_model_policy(config, policy):
    from gateway.common.opencode_model_policy import NATIVE_MODEL_PREFIX
    from jiuwenswarm.common.model_errors import ModelSelectionError

    catalog = ModelCatalog(config)
    default = policy["default"]
    default_account_id = None
    registered = dict.fromkeys(policy["models"])
    fallback = None
    reasons = {}
    for entry in sorted(catalog.list_public_models(), key=lambda model: not model["is_default"]):
        model_id = entry["model_id"]
        try:
            binding = managed_model_binding(policy, ModelSelection(type="model", id=model_id), catalog=catalog)
            reference = f"{binding['providerID']}/{binding['modelID']}"
            registered[reference] = None
            if policy.get("account_model_sync") and not default and fallback is None:
                fallback = (model_id, reference, entry["model_name"])
            if default_account_id is None and default == reference:
                default_account_id = model_id
        except (ValueError, ModelSelectionError) as error:
            reason = str(error)
            reasons[model_id] = reason if reason in {
                "opencode_shared_model_protocol_unsupported", "opencode_shared_model_options_unsupported",
                "opencode_model_not_registered",
            } else "opencode_model_unavailable"
    label = policy["models"].get(default)
    if fallback:
        default_account_id, default, label = fallback
    return {
        "registered": list(registered),
        "error": policy.get("error"),
        "default_account_id": default_account_id,
        "default": ({"id": NATIVE_MODEL_PREFIX + default, "label": label} if default else None),
        "reasons": reasons,
    }
