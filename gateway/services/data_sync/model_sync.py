"""Synchronize selected local model resources under the original cloud account."""
from __future__ import annotations

import asyncio

from jiuwenswarm.data_sync.contract import SyncError, digest
from jiuwenswarm.data_sync.transport import DirectoryRPC

_SYNC_PREFERENCES = "cloud_model_sync"


class _ModelRPC(DirectoryRPC):
    """Send only an authenticated model upsert through the existing WebChannel."""

    def __init__(self, endpoint, token, *, ca_file):
        super().__init__(endpoint, token, ca_file=ca_file, timeout=120)
        self._headers.pop("X-Jiuwen-Connection-Scope")

    async def upsert(self, model):
        return await self._request("models.upsert", {"model": model})


def _enabled_models(config, scope) -> set[str]:
    preferences = config.get(_SYNC_PREFERENCES)
    ids = preferences.get(scope) if isinstance(preferences, dict) else None
    return {model_id for model_id in ids if isinstance(model_id, str)} if isinstance(ids, list) else set()


def _model_snapshot(scope, model_id):
    from jiuwenswarm.common.auth.model_catalog import is_login_model
    from jiuwenswarm.common.config import load_models_config

    record = load_models_config()["by_id"].get(model_id)
    if not record or record["source"] != "defaults" or is_login_model(record["entry"]):
        raise SyncError("MODEL_SYNC_NOT_EDITABLE")
    entry = record["entry"]
    client = {"api_key": "", **entry["model_client_config"]}
    return {
        # Retry updates the same cloud copy and cannot replace an ordinary cloud model.
        "model_id": "mdl_" + digest(["cloud-model-copy-v1", scope, model_id])[:32],
        "alias": entry.get("alias", ""),
        "model_client_config": client,
        "model_config_obj": entry["model_config_obj"],
    }


def _save_preference(scope, model_id, enabled):
    from jiuwenswarm.common.config import update_config

    def mutate(config):
        selected = _enabled_models(config, scope)
        if enabled:
            selected.add(model_id)
        else:
            selected.discard(model_id)
        preferences = config.get(_SYNC_PREFERENCES)
        if not isinstance(preferences, dict):
            preferences = config[_SYNC_PREFERENCES] = {}
        if selected:
            preferences[scope] = sorted(selected)
        else:
            preferences.pop(scope, None)
        return config

    update_config(mutate)


class LocalModelSync:
    def __init__(self, local):
        self.local = local
        self.lock = asyncio.Lock()

    def _scope(self, identity):
        return digest(["cloud-model-sync-v1", self.local.endpoint, self.local.config["installation_id"],
                       identity["authority"], identity["actor_id"]])

    @staticmethod
    def _status(scope):
        from jiuwenswarm.common.config import get_config_raw

        return {"scope": scope, "enabled_ids": sorted(_enabled_models(get_config_raw(), scope))}

    async def run(self, identity, token, params):
        scope = self._scope(identity)
        if not params:
            return await asyncio.to_thread(self._status, scope)

        operation = params.get("operation")
        model_id = params.get("model_id")
        enabled = params.get("enabled")
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 200:
            raise ValueError("model ID required")
        if (operation == "set" and type(enabled) is not bool or operation == "refresh" and "enabled" in params
                or operation not in {"set", "refresh"}):
            raise ValueError("invalid model sync operation")
        if params.get("scope") != scope:
            raise SyncError("MODEL_SYNC_ACCOUNT_CHANGED")

        async with self.lock:
            if self._scope(await self.local.identity(token)) != scope:
                raise PermissionError()
            if operation == "set" and not enabled:
                await asyncio.to_thread(_save_preference, scope, model_id, False)
                return await asyncio.to_thread(self._status, scope)
            if operation == "refresh":
                status = await asyncio.to_thread(self._status, scope)
                if model_id not in status["enabled_ids"]:
                    return status
            model = await asyncio.to_thread(_model_snapshot, scope, model_id)
            async with _ModelRPC(self.local.endpoint, token, ca_file=self.local.config.get("ca_file")) as rpc:
                result = await rpc.upsert(model)
            returned_model = result.get("model") if isinstance(result, dict) else None
            if not isinstance(returned_model, dict) or returned_model.get("model_id") != model["model_id"]:
                raise SyncError("MODEL_SYNC_INVALID_RESPONSE")
            if self._scope(await self.local.identity(token)) != scope:
                raise PermissionError()
            if operation == "set":
                await asyncio.to_thread(_save_preference, scope, model_id, True)
            status = await asyncio.to_thread(self._status, scope)
            return {**status, "applied_without_restart": result.get("applied_without_restart") is True}
