"""Use the existing signed Codex relay for named device control."""

import asyncio
import json
import os

from websockets.exceptions import WebSocketException

from gateway.common.managed_codex import MODEL_UNAVAILABLE, RELAY_ENV, ManagedModel, validate_device_model_id
from gateway.common.model_selection import ModelSelection
from gateway.common.runtime_device import DEVICE_ID, WORKER_ROOT
from gateway.common.security.service_auth import configured_service_auth
from jiuwenswarm.common.codex_adapter_config import validate_model
from jiuwenswarm.common.model_errors import ModelSelectionError
from .codex_managed_stdio import connection


class CodexDeviceModelUnavailable(ValueError):
    """The account model cannot be used for this device."""


def model_payload(model):
    data = {"model": model.model_name, "base_url": model.api_base, "api_key": model.api_key}
    if model.context_window is not None:
        data["context_window"] = model.context_window
    return data


async def _request(runtime_id, directory, user_id, data, timeout):
    url = os.environ.get(RELAY_ENV, "").strip()
    auth = configured_service_auth()
    if (not isinstance(runtime_id, str) or not DEVICE_ID.fullmatch(runtime_id) or not url
            or auth is None or auth.public_binding()["owner"]["actor_id"] != user_id):
        raise PermissionError("Managed Codex requires a current account Worker and device")
    async with asyncio.timeout(timeout):
        async with connection(url, str(auth.path), directory) as socket:
            await socket.send(json.dumps({**data, "runtime_id": runtime_id}, ensure_ascii=False, allow_nan=False))
            return json.loads(await socket.recv())


async def validate_device(runtime_id, directory, user_id):
    try:
        reply = await _request(runtime_id, directory, user_id, {"op": "check"}, 15)
        if reply.get("runtime_id") != runtime_id or not isinstance(reply.get("model_id"), str):
            raise ValueError("Codex device has no usable model")
        return reply["model_id"]
    except (ValueError, KeyError, AttributeError, OSError, TimeoutError, WebSocketException) as exc:
        raise ValueError("Managed Codex device is unavailable for this session") from exc


def account_device_models(request):
    from jiuwenswarm.common.model_catalog import ModelCatalog
    from jiuwenswarm.common.model_routing_registry import ModelExecutionContext
    from ..execution_input import model_resolver

    params = request.params
    if (request.is_stream or request.session_id or not isinstance(params, dict)
            or set(params) != {"provider_id", "allowed_model_endpoints", "model_id"}
            or params["provider_id"] != "codex-direct"):
        raise ValueError("Invalid Codex device model catalog request")
    auth = configured_service_auth()
    if not os.environ.get(RELAY_ENV) or auth is None or auth.public_binding()["owner"]["actor_id"] != request.user_id:
        raise PermissionError("Managed Codex requires a current account Worker")
    endpoints = params["allowed_model_endpoints"]
    if not isinstance(endpoints, list) or not all(isinstance(endpoint, str) for endpoint in endpoints):
        raise ValueError("Invalid Codex model endpoints")
    selected = params["model_id"]
    catalog = ModelCatalog()
    resolve = model_resolver(catalog)
    ids = ([validate_device_model_id(selected)] if selected is not None
           else [entry["model_id"] for entry in catalog.list_public_models()])
    compatible = []
    for model_id in ids:
        try:
            model = validate_model(resolve.resolve(ModelSelection(type="model", id=model_id)))
            ManagedModel.parse(model_payload(model), endpoints)
        except (ValueError, ModelSelectionError):
            continue
        compatible.append(model_id)
    default_id = None
    if selected is None and compatible:
        default = resolve.choose(None, ModelExecutionContext())
        if default.type == "model" and default.id in compatible:
            default_id = default.id
    return {"model_ids": compatible, "default_model_id": default_id}


async def prepare_device(request):
    from ..execution_input import model_resolver

    params = request.params
    if (request.is_stream or request.session_id or not isinstance(params, dict)
            or set(params) != {"provider_id", "runtime_id", "model_id"}
            or params["provider_id"] != "codex-direct"):
        raise ValueError("Invalid Codex device preparation request")
    model_id = params["model_id"]
    if model_id is not None:
        validate_device_model_id(model_id)
    try:
        selection = ModelSelection(type="model", id=model_id) if model_id is not None else None
        model = validate_model(model_resolver().resolve(selection))
    except (ValueError, ModelSelectionError) as exc:
        raise CodexDeviceModelUnavailable("Codex device needs a supported account model") from exc
    reply = await _request(params["runtime_id"], str(WORKER_ROOT), request.user_id,
                           {"op": "prepare", "model_id": model.model_id, **model_payload(model)}, 140)
    if reply == {"code": MODEL_UNAVAILABLE}:
        raise CodexDeviceModelUnavailable("Codex device needs a supported account model")
    return reply == {"ready": True}
