"""Bounded keep-alive transport to the configured account authority.

Only TCP/TLS connections are reused. Every operation sends a fresh request and
credential and consumes a fresh authority response. Identity, permissions and
revocation are never cached. Mutating requests are never automatically replayed.
"""

from __future__ import annotations

import atexit
import hashlib
import http.client
import json
import logging
from pathlib import Path
import queue
import select
import ssl
import threading
import time
from urllib.parse import urlsplit

MAX_RESPONSE = 65536
TIMEOUT = 5.0
CONNECTIONS = 8
MAX_POOLS = 16
_POOLS = {}
_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)


class AccountHTTPPool:
    def __init__(self, url, ca):
        self.url = urlsplit(url)
        self.context = (ssl.create_default_context(cafile=ca)
                        if self.url.scheme == "https" else None)
        self.idle = queue.LifoQueue(CONNECTIONS)
        self.closed = False
        self.idle_seconds = 30.0
        for _ in range(CONNECTIONS):
            self.idle.put(None)

    def close(self):
        self.closed = True
        while True:
            try:
                connection = self.idle.get_nowait()
            except queue.Empty:
                break
            if connection is not None:
                connection.close()

    def post(self, method, body, headers):
        status, value, _ = self.request("POST", self.url.path.rstrip("/") + "/accounts/" + method,
                                        body, headers, operation=method, retry_read=method == "session")
        return status, value

    def request(self, verb, path, body, headers, *, operation, retry_read=False, timeout=TIMEOUT):
        started = time.monotonic()
        try:
            connection = self.idle.get(timeout=timeout)
        except queue.Empty as exc:
            raise OSError("account connection capacity exceeded") from exc
        slot_acquired = time.monotonic()
        connect_ms = 0.0
        response_ms = 0.0
        reused = False
        retired = "none"
        try:
            if connection is not None and connection.sock is not None:
                expired = slot_acquired - getattr(connection, "_account_idle_since", started) >= self.idle_seconds
                # All response bytes were consumed before pooling. Readable idle
                # sockets may contain EOF/TLS close-notify; discard before sending
                # any new request, including non-replayable login/ensure calls.
                try:
                    readable = bool(select.select([connection.sock], [], [], 0)[0])
                except (OSError, ValueError):
                    readable = True
                if expired or readable:
                    retired = "expired" if expired else "readable"
                    connection.close()
                    connection = None
            for attempt in range(2 if retry_read else 1):
                remaining = timeout - (time.monotonic() - started)
                if self.closed:
                    raise OSError("account transport configuration changed")
                if remaining <= 0:
                    raise OSError("account request deadline waiting for transport slot")
                if connection is None:
                    args = (self.url.hostname, self.url.port)
                    if self.url.scheme == "https":
                        connection = http.client.HTTPSConnection(
                            *args, context=self.context, timeout=remaining
                        )
                    else:
                        connection = http.client.HTTPConnection(
                            *args, timeout=remaining
                        )
                connection.timeout = remaining
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                try:
                    reused = connection.sock is not None
                    if not reused:
                        connecting = time.monotonic()
                        try:
                            connection.connect()
                        finally:
                            connect_ms += (time.monotonic() - connecting) * 1000
                    responding = time.monotonic()
                    try:
                        connection.request(verb, path, body, headers)
                        response = connection.getresponse()
                        value = response.read(MAX_RESPONSE + 1)
                    finally:
                        response_ms += (time.monotonic() - responding) * 1000
                    if len(value) > MAX_RESPONSE:
                        raise ValueError("account response budget exceeded")
                    return response.status, value, response.getheaders()
                except (http.client.HTTPException, OSError) as exc:
                    # EOF is a transport loss, including a peer closing a pooled
                    # TLS socket. Retry only reads within the original budget;
                    # certificate/hostname/protocol failures remain fail-closed.
                    if isinstance(exc, ssl.SSLError) and not isinstance(exc, (ssl.SSLEOFError, ssl.SSLZeroReturnError)):
                        raise
                    connection.close()
                    connection = None
                    if attempt != 0 or not retry_read:
                        raise
            raise OSError("account request unavailable")
        except BaseException:
            if connection is not None:
                connection.close()
                connection = None
            raise
        finally:
            elapsed = time.monotonic() - started
            if elapsed >= 0.5:
                # Only bounded operation names and timings; no URL, principal,
                # token, response, or raw exception enters diagnostics.
                _LOGGER.info("Account authority timing operation=%s queue_ms=%.1f connect_ms=%.1f response_ms=%.1f reused=%s retired=%s total_ms=%.1f",
                             operation, (slot_acquired - started) * 1000, connect_ms, response_ms, reused, retired, elapsed * 1000)
            if self.closed:
                if connection is not None:
                    connection.close()
            else:
                if connection is not None:
                    connection._account_idle_since = time.monotonic()
                self.idle.put_nowait(connection)


def _trust_stamp(ca):
    def stamp(path):
        value = Path(path)
        info = value.stat()
        return (
            str(value.resolve()),
            info.st_dev,
            info.st_ino,
            info.st_mtime_ns,
            info.st_ctime_ns,
            info.st_size,
        )

    if ca:
        return (stamp(ca),)
    defaults = ssl.get_default_verify_paths()
    return tuple(
        stamp(path)
        for path in (defaults.cafile, defaults.capath)
        if path and Path(path).exists()
    )


def authority_post(config_path, config, method, values, token):
    if method not in {"session", "login", "logout", "register", "members"}:
        raise ValueError("unknown account operation")
    url = config["url"]
    parsed = urlsplit(url)
    if not parsed.hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError("invalid account authority URL")
    # Config/CA changes and a bounded context lifetime invalidate keep-alive
    # reuse. A removed CA never falls through to a previously trusted socket.
    key = (
        str(config_path),
        hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        _trust_stamp(config.get("ca")) if parsed.scheme == "https" else (),
        int(time.monotonic() // 300),
    )
    with _LOCK:
        pool = _POOLS.get(key)
        if pool is None:
            pool = AccountHTTPPool(url, config.get("ca"))
            for previous in list(_POOLS):
                if previous[0] == key[0] or len(_POOLS) >= MAX_POOLS:
                    _POOLS.pop(previous).close()
            _POOLS[key] = pool
    headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        return pool.post(method, json.dumps(values or {}).encode(), headers)
    except http.client.HTTPException as exc:
        raise OSError("account authority protocol unavailable") from exc


def clear_connections():
    """Close idle authority sockets at shutdown or an explicit test boundary."""
    with _LOCK:
        for pool in _POOLS.values():
            pool.close()
        _POOLS.clear()


atexit.register(clear_connections)
