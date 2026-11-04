"""Translate the existing Swarm model catalog to official OpenCode configuration.

The service owner consumes this snapshot at normal startup. Chat requests never
write a borrowed server's config or credentials. No second model catalog is kept.
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
            providers[model_binding(model)['providerID']] = provider_config(model, settings)
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
