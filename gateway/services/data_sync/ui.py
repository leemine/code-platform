"""UI adapters for the existing account API, directory connector and host stores."""
from __future__ import annotations

import asyncio
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
import stat
import threading
import time
from urllib.parse import urlsplit

from jiuwenswarm.data_sync.connector import DirectoryConnector, DirectoryReplica, register_source
from jiuwenswarm.data_sync.contract import SyncError, digest, encoded, identifier, project_selection
from jiuwenswarm.data_sync.transport import DirectoryRPC

LOCAL_CONFIG = "CODE_PLATFORM_LOCAL_SYNC_CONFIG"
COOKIE = "jiuwenswarm_sync"


def origin(value, *, local=False):
    parsed = urlsplit(value)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or (parsed.scheme != "https" and not
            (local and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}))):
        raise ValueError("trusted origin required")
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


class CloudAccountClient:
    """Fixed HTTPS destination; passwords/tokens are never persisted or redirected."""

    def __init__(self, config):
        self.config = config
        self.target = urlsplit(config["cloud_origin"])
        origin(config["cloud_origin"])
        self._pool = None
        self._pool_key = None
        self._pool_lock = threading.Lock()

    def close(self):
        with self._pool_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def connection_pool(self):
        from gateway.auth.account_transport import AccountHTTPPool, _trust_stamp
        key = (self.config["cloud_origin"], _trust_stamp(self.config.get("ca_file")), int(time.monotonic() // 300))
        with self._pool_lock:
            if self._pool is None or key != self._pool_key:
                if self._pool is not None:
                    self._pool.close()
                self._pool = AccountHTTPPool(self.config["cloud_origin"], self.config.get("ca_file"))
                self._pool_key = key
            return self._pool

    def call(self, action, token=None, body=None):
        if action not in {"login", "logout", "status", "environment", "environment/ensure"}:
            raise ValueError("account operation required")
        headers = {"Content-Type": "application/json", "X-Jiuwen-Auth": "1"}
        if token:
            headers["Authorization"] = "Bearer " + token
        status, raw, response_headers = self.connection_pool().request(
            "GET" if body is None else "POST", "/api/v1/auth/organization/" + action,
            None if body is None else encoded(body), headers, operation=action,
            retry_read=action in {"status", "environment"}, timeout=150 if action == "environment/ensure" else 10)
        if status in {401, 403}:
            raise PermissionError()
        if status != 200:
            raise SyncError("SYNC_ACCOUNT_UNAVAILABLE")
        value = json.loads(raw)
        if action == "login":
            cookies = SimpleCookie()
            for key, val in response_headers:
                if key.lower() == "set-cookie":
                    cookies.load(val)
            item = cookies.get("jiuwenswarm_organization")
            if item is None or not 32 <= len(item.value) <= 512:
                raise SyncError("SYNC_ACCOUNT_UNAVAILABLE")
            value["token"] = item.value
        if action == "status":
            if value.get("authenticated") is not True:
                raise PermissionError()
            if (value.get("auth_backend") != "builtin" or not value.get("authority")
                    or not value.get("actor_id")):
                raise SyncError("SYNC_ACCOUNT_UNAVAILABLE")
        return value


def load_local_config():
    path = Path(os.environ[LOCAL_CONFIG])
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("local sync configuration must be private")
    value = json.loads(path.read_text())
    if set(value) - {"public_origin", "cloud_origin", "ca_file", "installation_id"}:
        raise ValueError("unknown local sync configuration")
    if origin(value["public_origin"], local=True)[1] not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("local sync UI must use a loopback entry")
    origin(value["cloud_origin"])
    identifier(value["installation_id"])
    return value


def local_replica(identity, endpoint, installation):
    from jiuwenswarm.common.utils import get_user_workspace_dir
    scope = digest(["platform-data-sync-v1", identity["authority"], identity["actor_id"]])
    root = Path(get_user_workspace_dir()).resolve() / "data-sync" / digest([endpoint, scope, installation])
    replica = DirectoryReplica(root, [endpoint, scope, installation])
    path = root / "source-token"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_hex(32))
            stream.flush()
            os.fsync(stream.fileno())
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError()
        proof = stream.read(65)
    from jiuwenswarm.data_sync.contract import proof_digest
    proof_digest(proof)
    return replica, proof


class LocalDirectoryUI:
    def __init__(self, config):
        self.config = config
        self.accounts = CloudAccountClient(config)
        self.endpoint = "wss://" + urlsplit(config["cloud_origin"]).netloc + "/ws"
        self.lock = asyncio.Lock()
        from gateway.services.cloud_workspace_client import WorkspaceConnections
        self.workspaces = WorkspaceConnections(self)

    async def close(self):
        await self.workspaces.close()
        await asyncio.to_thread(self.accounts.close)

    async def identity(self, token):
        if not token:
            raise PermissionError()
        try:
            return await asyncio.to_thread(self.accounts.call, "status", token)
        except PermissionError:
            await self.workspaces.discard(token)
            raise

    async def run(self, identity, token, action, params):
        async with self.lock:
            replica, proof = await asyncio.to_thread(local_replica, identity, self.endpoint, self.config["installation_id"])
            if action == "view":
                revoked = (replica.get("status") or {}).get("state") == "revoked"
                return {"items": [] if revoked else replica.projects(),
                        "sources": [] if revoked else (replica.get("coverage") or {}).get("coverage", []),
                        "selection": replica.get("ui_selection") or [], "status": replica.get("status"),
                        "pending": replica.get("publish") is not None, "account_complete": False}
            if action == "choices":
                from jiuwenswarm.server.runtime.session.project_store import snapshot_projects_for_export
                rows = await asyncio.to_thread(snapshot_projects_for_export)
                return {"projects": [{"native_id": row.project_id, "name": row.name} for row in rows if row.work_mode == "code"]}
            async with DirectoryRPC(self.endpoint, token, ca_file=self.config.get("ca_file")) as rpc:
                source = await register_source(rpc.request, self.config["installation_id"], proof)
                connector = DirectoryConnector(rpc.request, source, proof, replica)
                if action == "publish":
                    selected = project_selection(params.get("project_ids"))
                    # Persist user intent before exporting. Unknown outcomes retain the frozen operation.
                    replica.set_selection(selected)
                    await connector.publish(selected)
                elif action == "revoke":
                    await rpc.request("data_sync.source.revoke", {"source_id": identifier(params.get("source_id"))})
                    replica.reset_snapshot()
                    if params["source_id"] == source["id"]:
                        replica.mark_status("revoked", "SOURCE_UNAUTHORIZED")
                        return {"updated": True, "source_revoked": True}
                elif action != "refresh":
                    raise SyncError("INVALID_REQUEST")
                try:
                    await connector.pull()
                except SyncError as exc:
                    if exc.code not in {"SYNC_SOURCE_CHANGED", "SYNC_CURSOR_EXPIRED", "SYNC_SNAPSHOT_EXPIRED"}:
                        raise
                    await connector.pull()
                return {"updated": True}


class CloudDirectoryUI:
    def __init__(self, plugin):
        self.plugin = plugin

    async def run(self, principal, action, params):
        identity = await principal.check()
        scope = digest(["platform-data-sync-v1", identity["authority"], identity["user_id"]])
        if action == "view":
            return await asyncio.to_thread(self.plugin.store.catalog, scope, params.get("offset", 0), params.get("version"))
        if action == "revoke":
            return await asyncio.to_thread(self.plugin.store.revoke, scope, identifier(params.get("source_id")))
        publisher = self.plugin.cloud_publisher
        if publisher is None:
            raise SyncError("SOURCE_ROUTE_UNSUPPORTED")
        if action == "publish":
            return await publisher.publish(principal, params)
        if action == "choices":
            return await publisher.choices(principal)
        if action == "refresh":
            return {"updated": True}  # Reading accepted metadata does not contact or start an instance.
        raise SyncError("INVALID_REQUEST")
