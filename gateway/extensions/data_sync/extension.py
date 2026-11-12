"""Thin authenticated RPC adapter; no instance creation or execution routing."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sqlite3

from gateway.auth.account_authenticator import current_account
from gateway.auth.remote_accounts import AccountAuthorityUnavailable
from gateway.extensions.sdk.application_plugin import ApplicationPluginExtension
from jiuwenswarm.data_sync.contract import SyncError, digest, encoded, MAX_BYTES, negotiate
from gateway.services.data_sync.store import DirectoryStore
from gateway.services.cloud_environments import EnvironmentUnavailable
from gateway.services.data_sync.cloud_source import CloudSourcePublisher

SCHEMAS = {
    "negotiate": {"version", "capabilities"},
    "source.register": {"kind", "installation_id", "source_token", "version", "capabilities"},
    "source.revoke": {"source_id"},
    "inventory.publish": {"source_id", "source_token", "generation", "operation_id", "base_revision", "items", "total", "inventory_digest", "complete"},
    "snapshot": {"source_id", "source_token", "generation", "cursor"},
    "changes": {"source_id", "source_token", "generation", "cursor"},
    "ack": {"source_id", "source_token", "generation", "operation_id", "completion"},
    "receipt": {"source_id", "source_token", "generation", "operation_id"},
    "cloud.publish": {"operation_id", "project_ids"},
    "catalog": {"offset", "version"},
}


class DataSyncPlugin(ApplicationPluginExtension):
    plugin_id = "data_sync"

    def __init__(self, store, environment_store=None):
        self.store, self.environment_store = store, environment_store
        self.cloud_publisher = None
        self._slots = asyncio.Semaphore(4)
        self.set_extension_dir(Path(__file__).parent)

    async def initialize(self, config=None):
        return None

    async def shutdown(self):
        # Connections are transaction-scoped; the host owns request lifetimes.
        return None

    def bind_web_channel(self, channel, services):
        if self.environment_store is not None and services is not None:
            self.cloud_publisher = CloudSourcePublisher(self.store, self.environment_store, services.agent_client)
        for action in SCHEMAS:
            def bind(name):
                async def handler(ws, req_id, params, session_id):
                    try:
                        principal = current_account()
                        if principal is None:
                            raise PermissionError()
                        identity = await principal.check()
                        if not isinstance(params, dict) or set(params) - SCHEMAS[name] or len(encoded(params)) > MAX_BYTES + 4096:
                            raise SyncError("INVALID_REQUEST")
                        scope = digest(["platform-data-sync-v1", identity["authority"], identity["user_id"]])
                        async with self._slots:
                            # Recheck after waiting for capacity, then at delivery.
                            await principal.check()
                            if name == "cloud.publish":
                                if self.cloud_publisher is None:
                                    raise SyncError("SOURCE_ROUTE_UNSUPPORTED")
                                result = await self.cloud_publisher.publish(principal, params)
                            else:
                                result = await asyncio.to_thread(self.dispatch, scope, name, params)
                        await principal.check()
                        await channel.send_response(ws, req_id, ok=True, payload=result)
                    except PermissionError:
                        await channel.send_response(ws, req_id, ok=False, code="UNAUTHORIZED")
                    except SyncError as exc:
                        await channel.send_response(ws, req_id, ok=False, code=exc.code)
                    except AccountAuthorityUnavailable:
                        await channel.send_response(ws, req_id, ok=False, code="AUTHORITY_UNAVAILABLE")
                    except EnvironmentUnavailable:
                        await channel.send_response(ws, req_id, ok=False, code="SOURCE_BINDING_CHANGED")
                    except (TimeoutError, ConnectionError):
                        await channel.send_response(ws, req_id, ok=False, code="SOURCE_UNAVAILABLE")
                    except (OSError, sqlite3.Error):
                        await channel.send_response(ws, req_id, ok=False, code="SYNC_UNAVAILABLE")
                    except (ValueError, TypeError, KeyError):
                        await channel.send_response(ws, req_id, ok=False, code="INVALID_REQUEST")
                return handler
            channel.register_method("data_sync." + action, bind(action), local_only=True)

    def dispatch(self, scope, action, params):
        if action == "catalog":
            return self.store.catalog(scope, params.get("offset", 0), params.get("version"))
        if action == "negotiate":
            return negotiate(params.get("version"), params.get("capabilities"))
        if action == "source.register":
            kind = params.get("kind")
            if kind == "cloud":
                raise SyncError("SOURCE_HOST_ONLY")
            binding = params.get("installation_id")
            return self.store.register(scope, binding, kind, params.get("source_token"), params.get("version"), params.get("capabilities"))
        source = params.get("source_id")
        if action == "source.revoke":
            return self.store.revoke(scope, source)
        proof, generation = params.get("source_token"), params.get("generation")
        if action == "inventory.publish":
            return self.store.publish(scope, source, proof, generation, params.get("operation_id"), params.get("base_revision"),
                                      params.get("items"), params.get("total"), params.get("inventory_digest"), params.get("complete"))
        if action == "snapshot":
            return self.store.snapshot(scope, source, proof, generation, params.get("cursor"))
        if action == "changes":
            return self.store.changes(scope, source, proof, generation, params.get("cursor"))
        if action == "ack":
            return self.store.acknowledge(scope, source, proof, generation, params.get("operation_id"), params.get("completion"))
        if action == "receipt":
            return self.store.receipt(scope, source, proof, generation, params.get("operation_id"))
        raise SyncError("SYNC_UNSUPPORTED")


async def register_extensions(registry):
    from gateway.services.data_sync.ui import LOCAL_CONFIG, load_local_config
    from gateway.extensions.data_sync.ui_extension import DirectoryUIPlugin
    root = os.environ.get("CODE_PLATFORM_DATA_SYNC_ROOT")
    if os.environ.get(LOCAL_CONFIG):
        if root or os.environ.get("CODE_PLATFORM_CLOUD_CONFIG"):
            raise ValueError("local and cloud sync roles must not overlap")
        plugin = DirectoryUIPlugin(local_config=load_local_config())
        registry.register_application_plugin(plugin)
        return [plugin]
    if not root:
        return []
    if not os.environ.get("CODE_PLATFORM_CLOUD_CONFIG"):
        raise RuntimeError("data sync requires the original cloud account authority")

    def environment_store():
        plugin = registry.get_application_plugin("cloud_workspace")
        if plugin is None or plugin.environments is None:
            raise SyncError("SOURCE_UNAVAILABLE")
        return plugin.environments.store

    plugin = DataSyncPlugin(DirectoryStore(Path(root)), environment_store)
    registry.register_application_plugin(plugin)
    ui = DirectoryUIPlugin(directory=plugin, cloud=lambda: registry.get_application_plugin("cloud_workspace"))
    registry.register_application_plugin(ui)
    return [plugin, ui]
