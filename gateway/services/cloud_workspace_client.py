"""Local UI access to the account's cloud workspace through the original host APIs."""
from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field

from gateway.auth.account_transport import _trust_stamp

from jiuwenswarm.data_sync.contract import SyncError
from jiuwenswarm.data_sync.transport import DirectoryRPC


class WorkspaceRPC(DirectoryRPC):
    """Reuse bounded WebChannel framing; execution methods remain inaccessible."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This explicit workspace operation requires the original instance route.
        # Never widen the data-sync connection's metadata-only permission scope.
        self._headers.pop("X-Jiuwen-Connection-Scope")

    async def request(self, method, params):
        if method not in {"project.workspace.list", "project.workspace.mkdir", "project.workspace.open"}:
            raise ValueError("workspace directory operation required")
        return await self._request(method, params)


@dataclass
class _Connection:
    rpc: WorkspaceRPC
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0
    timer: object = None


class WorkspaceConnections:
    """Bounded credential-scoped transports; never cache identity or replay requests."""

    def __init__(self, local):
        self.local = local
        self.entries = {}
        self.lock = asyncio.Lock()
        self.closed = False
        self.idle_seconds = 60
        self._cleanup = set()

    async def _remove(self, key, entry, *, idle_only=False):
        async with self.lock:
            if self.entries.get(key) is not entry or (idle_only and entry.users):
                return
            self.entries.pop(key)
            if entry.timer:
                entry.timer.cancel()
        await entry.rpc.__aexit__()

    def _expire(self, key, entry):
        task = asyncio.create_task(self._remove(key, entry, idle_only=True))
        self._cleanup.add(task)
        task.add_done_callback(self._cleanup.discard)

    async def discard(self, token):
        digest = hashlib.sha256((token or "").encode()).hexdigest()
        for key, entry in list(self.entries.items()):
            if key[0] == digest:
                await self._remove(key, entry)

    async def close(self):
        self.closed = True
        for key, entry in list(self.entries.items()):
            await self._remove(key, entry)
        if self._cleanup:
            await asyncio.gather(*self._cleanup)

    async def request(self, token, method, params):
        ca = self.local.config.get("ca_file")
        key = (hashlib.sha256(token.encode()).hexdigest(), self.local.endpoint, _trust_stamp(ca), int(time.monotonic() // 300))
        async with self.lock:
            if self.closed:
                raise ConnectionError("workspace transport closed")
            entry = self.entries.get(key)
            if entry is None:
                if len(self.entries) >= 4:
                    raise ConnectionError("workspace connection capacity exceeded")
                entry = _Connection(WorkspaceRPC(self.local.endpoint, token, ca_file=ca, timeout=150))
                self.entries[key] = entry
            entry.users += 1
            if entry.timer:
                entry.timer.cancel()
        try:
            async with asyncio.timeout(150), entry.lock:
                if self.entries.get(key) is not entry:
                    raise ConnectionError("workspace connection invalidated")
                if entry.rpc.closed:
                    await entry.rpc.__aexit__()
                    await entry.rpc.__aenter__()
                    if self.entries.get(key) is not entry:
                        await entry.rpc.__aexit__()
                        raise ConnectionError("workspace connection invalidated")
                return await entry.rpc.request(method, params)
        except BaseException:
            # Includes cancellation, timeout and unknown mutation outcomes. Never resend.
            await self._remove(key, entry)
            raise
        finally:
            async with self.lock:
                entry.users -= 1
                if not entry.users and self.entries.get(key) is entry:
                    entry.timer = asyncio.get_running_loop().call_later(self.idle_seconds, self._expire, key, entry)


async def workspace_request(local, token, params):
    operation = params.get("operation")
    fields = {"environment": set(), "ensure": set(), "list": {"path", "offset"},
              "mkdir": {"path", "name"}, "open": {"path"}}
    if operation not in fields or set(params) - ({"operation"} | fields[operation]):
        raise ValueError("workspace operation required")
    if operation in {"environment", "ensure"}:
        action = "environment/ensure" if operation == "ensure" else "environment"
        return await asyncio.to_thread(local.accounts.call, action, token, {} if operation == "ensure" else None)
    try:
        return await local.workspaces.request(token, "project.workspace." + operation,
            {key: value for key, value in {**params, "work_mode": "code"}.items() if key != "operation"})
    except SyncError as exc:
        if exc.code == "UNAUTHORIZED":
            raise PermissionError() from None
        raise
