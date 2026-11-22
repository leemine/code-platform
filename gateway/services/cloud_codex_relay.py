"""Connect an admitted Worker to its authenticated Codex App Server."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from ipaddress import IPv4Address
import json
import logging
import time
from urllib.parse import unquote

from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import WebSocketException

from gateway.common.managed_codex import (
    ASSERTION_HEADER, AUDIENCE, DIRECTORY_HEADER, MAX_FRAME_BYTES, MODEL_UNAVAILABLE, NATIVE_PORT, validate_device_model_id,
)
from gateway.common.runtime_device import WORKER_ROOT
from gateway.common.security.provider_relay_auth import parse_assertion, verify_assertion
from gateway.extensions.yuanrong_frontend_client import YuanrongAgentApiError
from gateway.services.cloud_codex_pool import CodexRuntimeModelMismatch
from gateway.services.cloud_environments import EnvironmentUnavailable
from gateway.services.cloud_workspace_projects import project_snapshot
from gateway.services.managed_codex_models import ManagedModel, model_endpoint


logger = logging.getLogger(__name__)


class _StdioStream:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer

    async def send(self, packet):
        payload = packet.encode("utf-8")
        if len(payload) > MAX_FRAME_BYTES or b"\n" in payload or b"\r" in payload:
            raise ValueError("Codex expected one JSONL message")
        self.writer.write(payload + b"\n")
        await self.writer.drain()

    def __aiter__(self):
        return self

    async def __anext__(self):
        packet = await self.reader.readline()
        if not packet:
            raise StopAsyncIteration
        if len(packet) > MAX_FRAME_BYTES + 1 or not packet.endswith(b"\n"):
            raise ValueError("Incomplete Codex stdio message")
        return packet[:-1].decode("utf-8")


@asynccontextmanager
async def _native(lease, op, *, session_id=None, directory=None):
    address = IPv4Address(lease.address)
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ValueError("Codex address must be a verified private container address")
    async with asyncio.timeout(4):
        reader, writer = await asyncio.open_connection(str(address), NATIVE_PORT, limit=MAX_FRAME_BYTES + 1)
    stream = _StdioStream(reader, writer)
    try:
        async with asyncio.timeout(4):
            handshake = {"op": op, "capability": lease.capability}
            if op == "stream":
                handshake.update(session=session_id, directory=directory)
                if lease.model_route is not None:
                    handshake.update(model_route=lease.model_route, use_catalog=lease.use_catalog)
            await stream.send(json.dumps(handshake))
            try:
                reply = json.loads(await anext(stream))
            except StopAsyncIteration:
                raise RuntimeError("Codex stdio bridge closed during handshake") from None
        if op == "idle":
            yield reply == {"idle": True}
        elif reply != {"ready": True}:
            raise RuntimeError("Codex stdio bridge rejected the handshake")
        else:
            yield stream
    finally:
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()


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
            async with _native(lease, "probe-session-models" if lease.session_models else "probe") as server:
                await _initialize(server)
            return True
        except (OSError, TimeoutError, RuntimeError, ValueError, WebSocketException):
            return False

    @staticmethod
    async def idle(lease):
        try:
            async with _native(lease, "idle") as idle:
                return idle
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
        return row

    @staticmethod
    def _require_project(account, directory):
        projects = project_snapshot(account)
        if sum(isinstance(item, dict) and not item.get("hidden") and item.get("project_dir") == directory
               for item in projects) != 1:
            raise PermissionError("Codex requires a project owned by this account")

    async def _prepare(self, websocket, account, opening):
        runtime_id = opening.pop("runtime_id")
        status = self.pool.device_runtime(account, runtime_id)
        try:
            if status.get("session_models"):
                if opening:
                    raise ValueError("Codex Provider preparation only accepts a device ID")
                await self.pool.prepare_device(account, runtime_id)
            else:
                model_id = validate_device_model_id(opening.pop("model_id", None))
                model = ManagedModel.parse(opening, self.allowed_endpoints)
                await self.pool.prepare_device(account, runtime_id, model, model_id)
        except (CodexRuntimeModelMismatch, ValueError):
            await websocket.send_json({"code": MODEL_UNAVAILABLE})
            return
        await websocket.send_json({"ready": True})

    async def handle(self, websocket):
        close_code = 1011
        tasks = []
        try:
            directory = unquote(websocket.headers.get(DIRECTORY_HEADER, ""), errors="strict")
            if not directory or len(directory) > 4096 or websocket.query_params:
                raise PermissionError("Invalid Codex route")
            account = self._account(websocket, directory)
            if directory != str(WORKER_ROOT):
                self._require_project(account, directory)
            await websocket.accept()
            async with asyncio.timeout(15):
                opening = await websocket.receive_text()
                if len(opening.encode("utf-8")) > 16 * 1024:
                    raise ValueError("Codex model configuration exceeds bounds")
                data = json.loads(opening)
                if not isinstance(data, dict):
                    raise ValueError("Codex handshake fields differ")
            operation = data.pop("op", "stream")
            if operation == "prepare":
                if directory != str(WORKER_ROOT):
                    raise PermissionError("Invalid Codex device preparation scope")
                await self._prepare(websocket, account, data)
                close_code = 1000
                return
            if directory == str(WORKER_ROOT):
                raise PermissionError("Codex requires an authorized project")
            if operation == "check" and set(data) == {"runtime_id"}:
                status = self.pool.device_runtime(account, data["runtime_id"])
                reply = {"runtime_id": status["runtime_id"], "model_id": status["model_id"]}
                if status.get("session_models"):
                    reply["session_models"] = True
                await websocket.send_json(reply)
                close_code = 1000
                return
            if operation != "stream" or "session_id" not in data:
                raise ValueError("Codex handshake fields differ")
            session_id = data.pop("session_id")
            runtime_id = data.pop("runtime_id", None)
            model = ManagedModel.parse(data, self.allowed_endpoints)
            async with self.pool.hold(account, session_id, directory, model, runtime_id=runtime_id) as lease, _native(
                    lease, "stream", session_id=session_id, directory=directory) as server:
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
