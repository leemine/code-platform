"""Move the official Codex SDK's stdio over a private, signed Gateway stream."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import suppress
from urllib.parse import quote, urlsplit

from websockets.exceptions import ConnectionClosed, WebSocketException

from gateway.common.managed_codex import ASSERTION_HEADER, AUDIENCE, DIRECTORY_HEADER, MAX_FRAME_BYTES, RELAY_ENV
from gateway.common.security.provider_relay_auth import sign_assertion
from gateway.common.security.provider_relay_tls import relay_ssl_context
from gateway.common.security.service_auth import SERVICE_AUTH_ENV, ServiceAuthenticator

try:
    from websockets.asyncio.client import connect
    _HEADERS_OPTION = "additional_headers"
except ModuleNotFoundError:
    # websockets 12 exposes its asyncio client under the legacy namespace.
    from websockets.legacy.client import connect
    _HEADERS_OPTION = "extra_headers"


async def _relay_stdin(socket, reader):
    close_code = 1000
    try:
        while True:
            line = await reader.readuntil(b"\n")
            if len(line) > MAX_FRAME_BYTES:
                close_code = 1009
                break
            await socket.send(line[:-1].decode("utf-8"))
    except asyncio.IncompleteReadError as exc:
        if exc.partial:
            close_code = 1009
    except asyncio.LimitOverrunError:
        close_code = 1009
    except (ConnectionClosed, OSError, UnicodeError):
        pass
    finally:
        reason = "SDK frame exceeds limit" if close_code == 1009 else ""
        await socket.close(code=close_code, reason=reason)


async def _relay_stdio(socket):
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=MAX_FRAME_BYTES)
    input_transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    try:
        # Use pipe transports so a blocked SDK read or write can't stall the WSS loop.
        output_reader = asyncio.StreamReader()
        output_protocol = asyncio.StreamReaderProtocol(output_reader)
        output_transport, _ = await loop.connect_write_pipe(lambda: output_protocol, sys.stdout.buffer)
        writer = asyncio.StreamWriter(output_transport, output_protocol, None, loop)
        uplink = asyncio.create_task(_relay_stdin(socket, reader))
        try:
            async for frame in socket:
                if not isinstance(frame, str) or "\n" in frame or "\r" in frame:
                    raise RuntimeError("Invalid managed Codex frame")
                writer.write(frame.encode("utf-8") + b"\n")
                await writer.drain()
        finally:
            try:
                uplink.cancel()
                with suppress(asyncio.CancelledError):
                    await uplink
            finally:
                writer.close()
                await writer.wait_closed()
    finally:
        input_transport.close()


async def relay(url, auth_file, directory, model):
    parsed = urlsplit(url)
    if (parsed.scheme != "wss" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not parsed.path.startswith("/")):
        raise ValueError("Managed Codex requires its configured WSS relay")
    assertion = sign_assertion(
        ServiceAuthenticator(auth_file), audience=AUDIENCE, method="GET",
        path=parsed.path, directory=directory, body=b"",
    )
    headers = {_HEADERS_OPTION: {ASSERTION_HEADER: assertion, DIRECTORY_HEADER: quote(directory, safe="/")}}
    async with connect(url, ssl=relay_ssl_context(), open_timeout=20, close_timeout=3,
                       max_size=MAX_FRAME_BYTES, max_queue=4, **headers) as socket:
        await socket.send(json.dumps(model, ensure_ascii=False, allow_nan=False))
        async with asyncio.timeout(155):
            ready = await socket.recv()
        if json.loads(ready) != {"ready": True}:
            raise RuntimeError("Managed Codex did not confirm its allocation")
        await _relay_stdio(socket)


def main():
    try:
        asyncio.run(relay(
            os.environ[RELAY_ENV], os.environ[SERVICE_AUTH_ENV], os.environ["SWARM_CODEX_WORKSPACE"],
            json.loads(os.environ["SWARM_CODEX_MODEL_BINDING"]),
        ))
    except (KeyError, OSError, PermissionError, RuntimeError, ValueError, WebSocketException):
        print("Managed Codex connection closed or unavailable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
