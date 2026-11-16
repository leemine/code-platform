"""Bounded directory calls over the original WebChannel JSON RPC envelope."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import ssl
from urllib.parse import urlsplit

from websockets.legacy.client import connect

from .contract import MAX_BYTES, SyncError, encoded


class _FixedEndpointConnect(connect):
    def handle_redirect(self, uri):
        # An account token is authorized only for the explicitly selected endpoint.
        raise SyncError("SYNC_REDIRECT_DENIED")


logger = logging.getLogger(__name__)


class DirectoryRPC:
    """One authenticated connection, with no execution or routing lifecycle."""

    ping_timeout = 20

    def __init__(self, url, token, *, ca_file=None, timeout=30):
        target = urlsplit(url)
        if (target.scheme not in {"ws", "wss"} or not target.hostname or target.username
                or target.password or target.query or target.fragment
                or (target.scheme == "ws" and target.hostname not in {"127.0.0.1", "::1"})):
            raise ValueError("use wss (or numeric loopback ws), without URL credentials or selectors")
        if not isinstance(token, str) or not 32 <= len(token) <= 512:
            raise ValueError("original account session token required")
        self.url, self.timeout = url, timeout
        self._headers = {"Authorization": "Bearer " + token, "X-Jiuwen-Connection-Scope": "data-sync"}
        self._ssl = ssl.create_default_context(cafile=ca_file) if target.scheme == "wss" else None
        self._lock = asyncio.Lock()
        self._ws = None
        self._reader = None
        self._pending = {}

    async def __aenter__(self):
        self._ws = await _FixedEndpointConnect(self.url, extra_headers=self._headers, ssl=self._ssl,
                                 max_size=MAX_BYTES + 65536, open_timeout=self.timeout,
                                 close_timeout=1, max_queue=4, ping_timeout=self.ping_timeout)
        self._reader = asyncio.create_task(self._receive())
        return self

    async def __aexit__(self, *args):
        if self._ws is not None:
            await self._ws.close()
        if self._reader is not None:
            await self._reader
        self._ws = None

    @property
    def closed(self):
        return self._ws is None or not self._ws.open or self._reader.done()

    async def _receive(self):
        # Exactly one consumer drains responses and unrelated events, including while idle.
        error = ConnectionError("directory connection closed")
        try:
            async for raw in self._ws:
                frame = json.loads(raw)
                future = self._pending.get(frame.get("id")) if frame.get("type") == "res" else None
                if future is not None and not future.done():
                    future.set_result(frame)
        except Exception as exc:
            # Never log peer reason text, payloads or credentials. Close codes
            # distinguish policy rejection from heartbeat/transport failure.
            logger.info("Directory transport ended kind=%s received_code=%s sent_code=%s",
                        type(exc).__name__, getattr(getattr(exc, "rcvd", None), "code", None),
                        getattr(getattr(exc, "sent", None), "code", None))
            error = exc
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)

    async def request(self, method, params):
        if not method.startswith("data_sync."):
            raise ValueError("directory RPC only")
        return await self._request(method, params)

    async def _request(self, method, params):
        async with self._lock, asyncio.timeout(self.timeout):
            if self.closed:
                raise ConnectionError("directory connection closed")
            request_id = secrets.token_hex(16)
            future = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future
            try:
                await self._ws.send(encoded({"type": "req", "id": request_id, "method": method, "params": params}).decode())
                frame = await future
                if frame.get("ok") is not True:
                    raise SyncError(frame.get("code") or "SYNC_RPC_FAILED")
                return frame["payload"]
            finally:
                self._pending.pop(request_id, None)
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()
