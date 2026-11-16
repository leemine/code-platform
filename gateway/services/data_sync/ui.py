"""UI adapters for the existing account API, directory connector and host stores."""
from __future__ import annotations

import asyncio
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

import portalocker

from jiuwenswarm.data_sync.connector import DirectoryConnector, DirectoryReplica, register_source
from jiuwenswarm.data_sync.contract import SyncError, digest, encoded, identifier, project_selection
from jiuwenswarm.data_sync.transport import DirectoryRPC

LOCAL_CONFIG = "CODE_PLATFORM_LOCAL_SYNC_CONFIG"
DESKTOP_CONFIG_NAME = "cloud-account.json"
WINDOWS_DESKTOP_CLOUD_ORIGIN = "https://113.207.105.228:28953"
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
                # Keep the authority socket through directory browsing pauses.
                # The pool still checks EOF and sends a fresh request each time.
                self._pool.idle_seconds = 60
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


def _windows_config_is_private(stream):
    import msvcrt

    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    descriptor = win32security.GetSecurityInfo(
        msvcrt.get_osfhandle(stream.fileno()),
        win32security.SE_FILE_OBJECT,
        win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
    )
    acl = descriptor.GetSecurityDescriptorDacl()
    if descriptor.GetSecurityDescriptorOwner() != owner or acl is None:
        return False
    trusted = (
        owner,
        win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None),
        win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid, None),
    )
    for index in range(acl.GetAceCount()):
        ace = acl.GetAce(index)
        ace_type = ace[0][0]
        if ace_type == win32security.ACCESS_DENIED_ACE_TYPE:
            continue
        if ace_type != win32security.ACCESS_ALLOWED_ACE_TYPE or ace[-1] not in trusted:
            return False
    return True


def windows_desktop_origin() -> str | None:
    if os.name != "nt" or not getattr(sys, "frozen", False) or os.environ.get("JIUWENSWARM_ELECTRON") != "1":
        return None
    port = int(os.environ["FRONTEND_PORT"])
    if not 1 <= port <= 65535:
        raise ValueError("invalid desktop frontend port")
    return f"http://127.0.0.1:{port}"


def windows_desktop_cloud_ca() -> Path:
    return Path(__file__).resolve().parents[2] / "extensions" / "data_sync" / "windows-cloud-root.crt"


def load_windows_desktop_cloud_config(config_dir: Path, public_origin: str) -> dict:
    try:
        return load_local_config(config_dir / DESKTOP_CONFIG_NAME, public_origin=public_origin)
    except FileNotFoundError:
        pass
    ca_file = windows_desktop_cloud_ca()
    if not ca_file.is_file():
        raise FileNotFoundError("Windows cloud account CA is missing from the desktop package")
    config_dir.mkdir(parents=True, exist_ok=True)
    with portalocker.Lock(config_dir / "cloud-installation-id", mode="a+", encoding="utf-8", timeout=5) as stream:
        stream.seek(0)
        installation_id = stream.read().strip()
        if not installation_id:
            installation_id = uuid4().hex
            stream.write(installation_id + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        identifier(installation_id)
    return {
        "public_origin": public_origin,
        "cloud_origin": WINDOWS_DESKTOP_CLOUD_ORIGIN,
        "ca_file": str(ca_file),
        "installation_id": installation_id,
    }


def load_local_config(path: Path | None = None, *, public_origin: str | None = None):
    if path is None:
        path = Path(os.environ[LOCAL_CONFIG])
    before_open = path.lstat()
    if not stat.S_ISREG(before_open.st_mode) or (
        getattr(before_open, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise ValueError("local sync configuration must be private")
    with path.open(encoding="utf-8-sig") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not os.path.samestat(before_open, info):
            raise ValueError("local sync configuration changed while opening")
        private = (_windows_config_is_private(stream) if os.name == "nt"
                   else info.st_uid == os.getuid() and not info.st_mode & 0o077)
        if not private:
            raise ValueError("local sync configuration must be private")
        value = json.load(stream)
    if set(value) - {"public_origin", "cloud_origin", "ca_file", "installation_id"}:
        raise ValueError("unknown local sync configuration")
    if public_origin is not None:
        value["public_origin"] = public_origin
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
        from gateway.services.cloud_execution_bridge import CloudExecutionBridge
        self.execution = CloudExecutionBridge(self)

    async def close(self):
        await self.execution.close()
        await self.workspaces.close()
        await asyncio.to_thread(self.accounts.close)

    async def identity(self, token):
        if not token:
            raise PermissionError()
        try:
            return await asyncio.to_thread(self.accounts.call, "status", token)
        except PermissionError:
            await self.workspaces.discard(token)
            await self.execution.discard(token)
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
