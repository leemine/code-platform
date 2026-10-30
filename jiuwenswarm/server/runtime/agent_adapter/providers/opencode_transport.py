"""Official OpenCode HTTP/SSE wire boundary; no session or Turn state here.

Keep raw native dictionaries and subscribe before prompting. A future compatible
official SDK can replace this module without moving Runtime policy into it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

import httpx

TransportError = httpx.TransportError
logger = logging.getLogger(__name__)


def create_client(url, *, username="opencode", password=None):
    auth = httpx.BasicAuth(username, password) if password else None
    return httpx.AsyncClient(base_url=url, auth=auth, timeout=15, trust_env=False)


async def request_json(client, method, path, *, directory=None, body=None,
                       timeout=15, operation="API request"):
    started = time.monotonic()
    try:
        # Bound the entire operation, including responses that keep dripping data.
        # Never retry mutations: a lost response does not prove the request failed.
        async with asyncio.timeout(timeout):
            response = await client.request(method, path,
                params={"directory": directory} if directory else None, json=body, timeout=timeout)
            response.raise_for_status()
            return response.json() if response.content else None
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        error_type = type(exc).__name__
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning("OpenCode operation=%s error_type=%s status=%s elapsed=%.3fs",
                       operation, error_type, status, time.monotonic() - started)
        detail = f"HTTP {status}" if status is not None else error_type
        hint = " Check project plugin dependencies and network connectivity." if operation == "session initialization" else ""
        # Native exception text/URLs/bodies can contain credentials; expose categories only.
        raise RuntimeError(f"OpenCode {operation} failed ({detail}).{hint}") from None


async def healthy(client, *, timeout=15):
    response = await client.get("/global/health", timeout=timeout)
    response.raise_for_status()
    result = response.json()
    return isinstance(result, dict) and result.get("healthy") is True


async def _events(response):
    data = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
        elif not line and data:
            event = json.loads("\n".join(data))
            data.clear()
            if not isinstance(event, dict):
                raise ValueError("Invalid OpenCode event envelope")
            yield event
    # An unterminated frame at EOF is incomplete, not a successful Turn.


@asynccontextmanager
async def subscribe(client, directory):
    async with client.stream("GET", "/event", params={"directory": directory}, timeout=None) as response:
        response.raise_for_status()
        yield _events(response)
