"""Connect an admitted Worker to its authenticated Codex App Server."""
from __future__ import annotations

import asyncio
from ipaddress import IPv4Address
import json
import logging
import time
from urllib.parse import unquote

from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from gateway.common.managed_codex import ASSERTION_HEADER, AUDIENCE, DIRECTORY_HEADER, MAX_FRAME_BYTES, NATIVE_PORT
from gateway.common.security.provider_relay_auth import parse_assertion, verify_assertion
from gateway.extensions.yuanrong_frontend_client import YuanrongAgentApiError
from gateway.services.cloud_environments import EnvironmentUnavailable
from gateway.services.cloud_workspace_projects import project_snapshot
from gateway.services.managed_codex_models import ManagedModel, model_endpoint


logger = logging.getLogger(__name__)


def _native(lease):
    address = IPv4Address(lease.address)
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ValueError("Codex address must be a verified private container address")
    return connect(f"ws://{address}:{NATIVE_PORT}/", proxy=None, open_timeout=4, close_timeout=2,
                   additional_headers={"Authorization": "Bearer " + lease.capability},
                   max_size=MAX_FRAME_BYTES, max_queue=8)


async def _rpc(connection, identifier, method, params):
    await connection.send(json.dumps({"id": identifier, "method": method, "params": params}))
    async with asyncio.timeout(5):
        async for packet in connection:
            value = json.loads(packet)
            if value.get("id") == identifier:
                if not isinstance(value.get("result"), dict):
                    raise RuntimeError("Managed Codex rejected a readiness request")
                return value["result"]
    raise RuntimeError("Managed Codex closed before a readiness response")


async def _initialize(connection):
    value = await _rpc(connection, 0, "initialize", {"clientInfo": {"name": "platform_probe", "version": "1"}})
    if not value.get("userAgent"):
        raise RuntimeError("Managed Codex app server identity is absent")
    await connection.send('{"method":"initialized"}')


class CloudCodexRelay:
    def __init__(self, pool):
        self.pool = pool
        self.store = pool.store
        self._replays = {}
        self.allowed_endpoints = frozenset(model_endpoint(url) for url in pool.options["model_endpoints"])
        pool.ready_check = self.ready
        pool.idle_check = self.idle

    @staticmethod
    async def ready(lease):
        try:
            async with _native(lease) as server:
                await _initialize(server)
            return True
        except (OSError, TimeoutError, RuntimeError, ValueError, WebSocketException):
            return False

    @staticmethod
    async def idle(lease):
        try:
            async with _native(lease) as server, asyncio.timeout(10):
                await _initialize(server)
                active = await _rpc(server, 1, "thread/loaded/list", {"limit": 100})
                identifiers = active.get("data")
                if not isinstance(identifiers, list) or active.get("nextCursor"):
                    return False
                for index, identifier in enumerate(identifiers, 2):
                    result = await _rpc(server, index, "thread/read", {"threadId": identifier})
                    if result["thread"]["status"]["type"] not in ("idle", "notLoaded"):
                        return False
            return True
        except (KeyError, TypeError, OSError, TimeoutError, RuntimeError, ValueError, WebSocketException):
            return False

    def _account(self, websocket, directory):
        claims, signature = parse_assertion(websocket.headers.get(ASSERTION_HEADER, ""), audience=AUDIENCE)
        row = self.store.by_user(claims["actor"])
        if (row["state"] != "ALLOCATED" or not self.pool.admits(row) or row["environment_id"] != claims["environment"]
                or row["epoch"] != claims["epoch"]):
            raise PermissionError("Codex request does not own the current Worker")
        verify_assertion(row["auth_file"], claims, signature, method="GET",
                         path=websocket.url.path, directory=directory, body=b"")
        now = time.time()
        self._replays = {key: expiry for key, expiry in self._replays.items() if expiry > now}
        if len(self._replays) >= 10000 or signature in self._replays:
            raise PermissionError("Codex assertion was replayed")
        self._replays[signature] = claims["exp"]
        projects = project_snapshot(row)
        if sum(isinstance(item, dict) and not item.get("hidden") and item.get("project_dir") == directory
               for item in projects) != 1:
            raise PermissionError("Codex requires a project owned by this account")
        return row

    async def handle(self, websocket):
        close_code = 1011
        tasks = []
        try:
            directory = unquote(websocket.headers.get(DIRECTORY_HEADER, ""), errors="strict")
            if not directory or len(directory) > 4096 or websocket.query_params:
                raise PermissionError("Invalid Codex route")
            account = self._account(websocket, directory)
            await websocket.accept()
            async with asyncio.timeout(15):
                opening = await websocket.receive_text()
                if len(opening.encode("utf-8")) > 16 * 1024:
                    raise ValueError("Codex model configuration exceeds bounds")
                data = json.loads(opening)
                if not isinstance(data, dict) or set(data) != {"session_id", "model", "base_url", "api_key"}:
                    raise ValueError("Codex handshake fields differ")
                session_id = data.pop("session_id")
                model = ManagedModel.parse(data, self.allowed_endpoints)
            async with self.pool.hold(account, session_id, directory, model) as lease, _native(lease) as server:
                await websocket.send_json({"ready": True})

                async def send_to_native():
                    async for packet in websocket.iter_text():
                        if len(packet.encode("utf-8")) > MAX_FRAME_BYTES:
                            raise ValueError("Codex request exceeds bounds")
                        self.pool._current(account)
                        await server.send(packet)

                async def send_to_worker():
                    async for packet in server:
                        if not isinstance(packet, str):
                            raise ValueError("Codex text frame required")
                        self.pool._current(account)
                        await websocket.send_text(packet)

                tasks = [asyncio.create_task(send_to_native()), asyncio.create_task(send_to_worker())]
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    close_code = 1000
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except (PermissionError, KeyError, TypeError, ValueError):
            close_code = 1008
        except (WebSocketDisconnect, WebSocketException, YuanrongAgentApiError,
                EnvironmentUnavailable, OSError, TimeoutError, RuntimeError) as exc:
            logger.info("Managed Codex relay closed: %s", type(exc).__name__)
        finally:
            try:
                await websocket.close(code=close_code)
            except (RuntimeError, WebSocketDisconnect):
                pass
