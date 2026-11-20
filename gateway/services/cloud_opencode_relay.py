"""Account-scoped HTTP/SSE relay to managed OpenCode on YuanRong."""
from __future__ import annotations

from contextlib import AsyncExitStack, ExitStack
import json
import logging
import os
import re
import stat
import time
from urllib.parse import urlsplit

from anyio import CancelScope
import httpx
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, StreamingResponse

from gateway.common.security.opencode_relay_auth import HEADER, parse_assertion, verify_assertion
from gateway.extensions.yuanrong_frontend_client import YuanrongAgentApiError
from gateway.services.cloud_environments import EnvironmentUnavailable

logger = logging.getLogger(__name__)
_PROJECT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}\Z")
_NATIVE_ID = r"[A-Za-z0-9_-]{1,160}"
_GET = re.compile(rf"(?:global/health|event|provider|session(?:/(?:status|{_NATIVE_ID}(?:/message)?))?)\Z")
_POST = re.compile(rf"(?:session(?:/{_NATIVE_ID}/(?:abort|prompt_async))?|(?:permission|question)/{_NATIVE_ID}/reply)\Z")
_MAX_BODY = 8 * 1024 * 1024


def _project_directory(account: dict, project_id: str) -> str:
    if not _PROJECT.fullmatch(project_id):
        raise PermissionError("Invalid project identity")
    # ProjectStore replaces the file atomically. Read that snapshot through
    # directory descriptors so mutable account paths cannot follow symlinks.
    directory_flags = os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as scope:
        root_fd = os.open(account["workspace"], directory_flags)
        scope.callback(os.close, root_fd)
        agent_fd = os.open("agent", directory_flags, dir_fd=root_fd)
        scope.callback(os.close, agent_fd)
        projects_fd = os.open("projects.json", os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=agent_fd)
        projects = scope.enter_context(os.fdopen(projects_fd, "rb"))
        if not stat.S_ISREG(os.fstat(projects_fd).st_mode):
            raise PermissionError("Invalid account project store")
        snapshot = projects.read(_MAX_BODY + 1)
    if len(snapshot) > _MAX_BODY:
        raise PermissionError("Invalid account project store")
    rows = json.loads(snapshot)["projects"]
    if not isinstance(rows, list):
        raise PermissionError("Invalid account project store")
    matches = [row for row in rows if isinstance(row, dict)
               and row.get("project_id") == project_id and not row.get("hidden")]
    if len(matches) != 1:
        raise PermissionError("OpenCode requires a project owned by this account")
    directory = matches[0]["project_dir"]
    if not isinstance(directory, str) or not directory:
        raise PermissionError("OpenCode requires a project workspace")
    return directory


class _RelayResponse(StreamingResponse):
    """Keep the remote request and its Provider hold for the ASGI response."""

    def __init__(self, upstream: httpx.Response, scope: AsyncExitStack):
        self._scope = scope
        super().__init__(upstream.aiter_bytes(), status_code=upstream.status_code, headers={
            "Content-Type": upstream.headers.get("Content-Type", "application/json"),
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        })

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await self._scope.aclose()


class _OpenCodeQueryAuthTransport(httpx.AsyncBaseTransport):
    """Add OpenCode auth on the private hop without changing the logged URL."""

    def __init__(self, transport: httpx.AsyncBaseTransport):
        self._transport = transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        headers = request.headers.copy()
        authorization = headers.pop("Authorization", "")
        if not authorization.startswith("Basic ") or "auth_token" in request.url.params:
            raise httpx.RequestError("OpenCode upstream authentication is missing or ambiguous")
        private_request = httpx.Request(
            request.method, request.url.copy_add_param("auth_token", authorization[6:]),
            headers=headers, stream=request.stream, extensions=request.extensions,
        )
        return await self._transport.handle_async_request(private_request)

    async def aclose(self):
        await self._transport.aclose()


class CloudOpencodeRelay:
    def __init__(self, store, pool, *, auth_transport="basic"):
        self.store, self.pool = store, pool
        frontend = urlsplit(pool.yuanrong.frontend_endpoint)
        self.origin = f"{frontend.scheme}://{frontend.netloc}"
        self._replays: dict[str, int] = {}
        transport = None
        if auth_transport == "query":
            if frontend.hostname not in ("127.0.0.1", "::1"):
                raise ValueError("OpenCode query authentication requires a loopback YuanRong Frontend")
            # YuanRong rewrites the first HTTP request in a tunnel connection.
            transport = _OpenCodeQueryAuthTransport(httpx.AsyncHTTPTransport(
                limits=httpx.Limits(max_keepalive_connections=0), trust_env=False,
            ))
        self._client = httpx.AsyncClient(trust_env=False, follow_redirects=False,
                                         transport=transport, timeout=httpx.Timeout(15, read=75))
        pool.ready_check = self._ready
        pool.idle_check = self._idle
        pool.unavailable_check = self._unavailable

    async def close(self):
        await self._client.aclose()

    def _route(self, lease, path: str):
        return self.origin + "/serverless/v1/http/" + path, {
            "instance": lease.instance_id,
            "tenant_id": self.pool.yuanrong.agent_namespace,
            "port": "4096",
            "directory": lease.directory,
        }

    async def _ready(self, lease) -> bool:
        url, query = self._route(lease, "global/health")
        try:
            result = await self._client.get(url, params=query, auth=("opencode", lease.password), timeout=5)
            result.raise_for_status()
            health = result.json()
        except (httpx.HTTPError, ValueError):
            return False
        return isinstance(health, dict) and health.get("healthy") is True

    async def _idle(self, lease) -> bool:
        url, query = self._route(lease, "session/status")
        try:
            result = await self._client.get(url, params=query, auth=("opencode", lease.password), timeout=5)
            result.raise_for_status()
            states = result.json()
        except (httpx.HTTPError, ValueError):
            return False
        return isinstance(states, dict) and all(
            isinstance(state, dict) and state.get("type") == "idle" for state in states.values()
        )

    async def _unavailable(self, lease) -> bool:
        url, query = self._route(lease, "global/health")
        try:
            result = await self._client.get(url, params=query, auth=("opencode", lease.password), timeout=5)
        except httpx.RemoteProtocolError:
            # YuanRong can close the response without headers on a refused sandbox tunnel.
            # The pool also requires a refusal from the exact container's own port.
            return True
        except httpx.HTTPError:
            return False
        return result.status_code == 502 and result.content.strip() == b"failed to dial sandbox"

    def _account(self, request, body: bytes, supplied_dir: str):
        claims, signature = parse_assertion(request.headers.get(HEADER, ""))
        try:
            row = self.store.by_user(claims["actor"])
        except EnvironmentUnavailable as exc:
            raise PermissionError("Worker account is not allocated") from exc
        if (row["state"] != "ALLOCATED" or row["environment_id"] != claims["environment"]
                or row["epoch"] != claims["epoch"]):
            raise PermissionError("Worker epoch is no longer current")
        verify_assertion(row["auth_file"], claims, signature, method=request.method,
                         path=request.url.path, directory=supplied_dir, body=body)
        now = time.time()
        self._replays = {nonce: expiry for nonce, expiry in self._replays.items() if expiry > now}
        if len(self._replays) >= 10000 or signature in self._replays:
            raise PermissionError("Worker assertion was replayed or relay capacity exceeded")
        self._replays[signature] = claims["exp"]
        return row

    async def handle(self, request: Request):
        project_id, path = request.path_params["project_id"], request.path_params["path"]
        if not ((request.method == "GET" and _GET.fullmatch(path))
                or (request.method == "POST" and _POST.fullmatch(path))):
            return JSONResponse({"code": "NOT_FOUND"}, status_code=404)
        if not request.headers.get(HEADER):
            return JSONResponse({"code": "OPENCODE_FORBIDDEN"}, status_code=403)
        query = request.query_params.multi_items()
        if query and (len(query) != 1 or query[0][0] != "directory"):
            return JSONResponse({"code": "INVALID_REQUEST"}, status_code=400)
        supplied_dir = query[0][1] if query else ""
        raw = bytearray()
        scope = AsyncExitStack()
        handed_off = False
        try:
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > _MAX_BODY:
                    return JSONResponse({"code": "BODY_TOO_LARGE"}, status_code=413)
            body = bytes(raw)
            account = self._account(request, body, supplied_dir)
            directory = _project_directory(account, project_id)
            if supplied_dir and supplied_dir != directory:
                raise PermissionError("Project workspace differs")
            lease = await scope.enter_async_context(self.pool.hold(account, project_id, directory))
            with self.store.guard_binding(
                {"authority": account["authority"], "user_id": account["account_id"]}, account
            ):
                pass
            url, params = self._route(lease, path)
            upstream = await scope.enter_async_context(self._client.stream(
                request.method, url, params=params, auth=("opencode", lease.password),
                content=body, headers={"Content-Type": "application/json"} if body else None,
            ))
            if path == "provider" and upstream.is_success:
                models = json.loads(await upstream.aread())["all"]
                return JSONResponse({"all": [
                    {"id": item["id"], "models": dict.fromkeys(item["models"])}
                    for item in models
                ]}, headers={"Cache-Control": "no-store"})

            response = _RelayResponse(upstream, scope)
            handed_off = True
            return response
        except (PermissionError, FileNotFoundError, KeyError, TypeError, ValueError):
            return JSONResponse({"code": "OPENCODE_FORBIDDEN"}, status_code=403)
        except (EnvironmentUnavailable, YuanrongAgentApiError, httpx.HTTPError, ClientDisconnect, OSError, TimeoutError) as exc:
            logger.warning("Managed OpenCode request failed (%s)", type(exc).__name__)
            return JSONResponse({"code": "OPENCODE_UNAVAILABLE"}, status_code=503)
        finally:
            if not handed_off:
                with CancelScope(shield=True):
                    await scope.aclose()
