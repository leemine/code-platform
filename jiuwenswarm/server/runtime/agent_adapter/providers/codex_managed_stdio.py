"""Move the official Codex SDK's stdio over a private, signed Gateway stream."""
from __future__ import annotations

import json
import os
import sys
from threading import Thread
from urllib.parse import quote, urlsplit

from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.sync.client import connect

from gateway.common.managed_codex import ASSERTION_HEADER, AUDIENCE, DIRECTORY_HEADER, MAX_FRAME_BYTES, RELAY_ENV
from gateway.common.security.provider_relay_auth import sign_assertion
from gateway.common.security.provider_relay_tls import relay_ssl_context
from gateway.common.security.service_auth import SERVICE_AUTH_ENV, ServiceAuthenticator


def _relay_stdin(socket):
    try:
        while line := sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1):
            if len(line) > MAX_FRAME_BYTES or not line.endswith(b"\n"):
                socket.close(code=1009, reason="SDK frame exceeds limit")
                return
            socket.send(line[:-1].decode("utf-8"))
    except (ConnectionClosed, OSError, UnicodeError):
        pass
    finally:
        socket.close()


def relay(url, auth_file, directory, model):
    parsed = urlsplit(url)
    if (parsed.scheme != "wss" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not parsed.path.startswith("/")):
        raise ValueError("Managed Codex requires its configured WSS relay")
    assertion = sign_assertion(
        ServiceAuthenticator(auth_file), audience=AUDIENCE, method="GET",
        path=parsed.path, directory=directory, body=b"",
    )
    headers = {ASSERTION_HEADER: assertion, DIRECTORY_HEADER: quote(directory, safe="/")}
    with connect(url, ssl=relay_ssl_context(), additional_headers=headers, open_timeout=20, close_timeout=3,
                 max_size=MAX_FRAME_BYTES, max_queue=4) as socket:
        socket.send(json.dumps(model, ensure_ascii=False, allow_nan=False))
        if json.loads(socket.recv(timeout=155)) != {"ready": True}:
            raise RuntimeError("Managed Codex did not confirm its allocation")
        uplink = Thread(target=_relay_stdin, args=(socket,), name="codex-sdk-stdin", daemon=True)
        uplink.start()
        for frame in socket:
            if not isinstance(frame, str) or "\n" in frame or "\r" in frame:
                raise RuntimeError("Invalid managed Codex frame")
            sys.stdout.buffer.write(frame.encode("utf-8") + b"\n")
            sys.stdout.buffer.flush()


def main():
    try:
        relay(os.environ[RELAY_ENV], os.environ[SERVICE_AUTH_ENV], os.environ["SWARM_CODEX_WORKSPACE"],
              json.loads(os.environ["SWARM_CODEX_MODEL_BINDING"]))
    except (KeyError, OSError, PermissionError, RuntimeError, ValueError, WebSocketException):
        print("Managed Codex connection closed or unavailable", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
