"""Same-origin transport for the original cloud WebChannel, never an executor."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import ssl
import time

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from websockets.exceptions import WebSocketException

from jiuwenswarm.data_sync.contract import MAX_BYTES, SyncError
from gateway.auth.remote_accounts import AccountAuthorityUnavailable
from jiuwenswarm.data_sync.transport import _FixedEndpointConnect
from gateway.services.cloud_resource_address import CloudAddresses

logger = logging.getLogger(__name__)
PATH = "/api/v1/data-sync/ws"
_READ_GLOBAL = {"config.get", "models.list", "commands.list", "skills.list", "project.list", "session.list"}


class CloudExecutionBridge:
    def __init__(self, local):
        self.local = local
        self.connections = {}

    async def discard(self, token):
        digest = hashlib.sha256((token or "").encode()).hexdigest()
        for ws, owner in list(self.connections.items()):
            if owner == digest and ws.application_state != WebSocketState.DISCONNECTED:
                await ws.close(code=1008, reason="cloud account changed")

    async def close(self):
        for ws in list(self.connections):
            if ws.application_state == WebSocketState.DISCONNECTED:
                continue
            await ws.close(code=1001, reason="local host shutdown")

    async def serve(self, ws: WebSocket):
        from gateway.services.data_sync.ui import COOKIE, origin
        expected = origin(self.local.config["public_origin"], local=True)
        token = ws.cookies.get(COOKIE)
        try:
            if (ws.query_params or origin(ws.headers.get("origin", ""), local=True) != expected
                    or origin(expected[0] + "://" + ws.headers.get("host", ""), local=True) != expected or not token):
                raise PermissionError()
            if len(self.connections) >= 16:
                await ws.close(code=1013, reason="cloud connection capacity")
                return
        except (PermissionError, ValueError, OSError, SyncError, AccountAuthorityUnavailable):
            await ws.close(code=1008, reason="cloud authentication required")
            return
        self.connections[ws] = hashlib.sha256(token.encode()).hexdigest()
        tasks = []
        stage = "identity"
        close_code = 1011
        started = time.monotonic()
        pending_timings = {}
        try:
            # Upgrade is transport admission only. Cloud data and requests stay
            # blocked until fresh authorization and the upstream connection finish.
            # Waiting here before accept would exceed the server's 10s handshake.
            await ws.accept()
            identity = await self.local.identity(token)
            addresses = CloudAddresses(self.local.endpoint, identity)
            stage = "connect"
            ca = self.local.config.get("ca_file")
            async with _FixedEndpointConnect(self.local.endpoint,
                    extra_headers={"Authorization": "Bearer " + token},
                    ssl=ssl.create_default_context(cafile=ca), max_size=MAX_BYTES + 65536,
                    max_queue=4, open_timeout=150, close_timeout=5) as cloud:
                if await self.local.identity(token) != identity:
                    raise PermissionError()
                await ws.send_json({"type": "event", "event": "connection.ack",
                                    "payload": {"transport": "cloud-bridge"}})
                logger.info("Cloud bridge timing phase=ready total_ms=%.1f", (time.monotonic() - started) * 1000)

                async def upstream():
                    nonlocal stage
                    async for raw in ws.iter_text():
                        if len(raw.encode()) > MAX_BYTES:
                            raise ValueError("cloud frame budget exceeded")
                        data = json.loads(raw)
                        if (not isinstance(data, dict) or data.get("type") != "req"
                                or not isinstance(data.get("id"), str) or len(data["id"]) > 200
                                or not isinstance(data.get("params"), dict)):
                            raise ValueError("cloud request envelope required")
                        method = data.get("method")
                        if not isinstance(method, str) or not re.fullmatch(r"[a-z][a-z0-9_.]{0,100}", method):
                            raise ValueError("cloud operation not supported")
                        # Method dispatch remains owned by the original WebChannel, including
                        # its registered extension methods (for example command.goal).
                        stage = "address_" + method
                        params = addresses.params(data["params"])
                        if method not in _READ_GLOBAL | {"session.create"} and not any(
                                params.get(key) for key in ("session_id", "project_id", "session_ids", "project_ids")):
                            raise ValueError("cloud resource selector required")
                        if method == "session.create" and not params.get("project_id"):
                            raise ValueError("selected cloud project required")
                        # ProjectStore is authoritative for the root. Do not import a local absolute cwd.
                        params.pop("project_dir", None)
                        stage = "identity_" + method
                        checking = time.monotonic()
                        if await self.local.identity(token) != identity:
                            raise PermissionError()
                        stage = "relay_" + method
                        if len(pending_timings) >= 64:
                            pending_timings.pop(next(iter(pending_timings)))
                        pending_timings[data["id"]] = (method, time.monotonic())
                        logger.info("Cloud bridge timing phase=authorize method=%s total_ms=%.1f",
                                    method, (time.monotonic() - checking) * 1000)
                        await cloud.send(json.dumps({**data, "params": params}, ensure_ascii=False))

                async def downstream():
                    # One receiver only. The original cloud channel performs fresh request and
                    # delivery authorization; logout also closes this local transport immediately.
                    async for raw in cloud:
                        data = json.loads(raw)
                        if not isinstance(data, dict) or data.get("type") not in {"res", "event"}:
                            raise ValueError("invalid cloud response")
                        timing = pending_timings.pop(data.get("id"), None) if data.get("type") == "res" else None
                        if timing:
                            logger.info("Cloud bridge timing phase=response method=%s total_ms=%.1f",
                                        timing[0], (time.monotonic() - timing[1]) * 1000)
                        await ws.send_json(addresses.frame(data))

                stage = "relay"
                tasks = [asyncio.create_task(upstream()), asyncio.create_task(downstream())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        except (PermissionError, ValueError, OSError, SyncError, AccountAuthorityUnavailable, WebSocketException, WebSocketDisconnect) as exc:
            if isinstance(exc, (PermissionError, ValueError, SyncError)):
                close_code = 1008
            logger.warning("Cloud execution bridge failed stage=%s kind=%s", stage, type(exc).__name__)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.connections.pop(ws, None)
            try:
                await ws.close(code=close_code, reason="cloud connection ended")
            except RuntimeError:
                pass
