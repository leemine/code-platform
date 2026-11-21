"""Account-scoped HTTP/SSE relay to managed OpenCode on YuanRong."""
from __future__ import annotations

from contextlib import AsyncExitStack
import json
import logging
import re
import time
from urllib.parse import urlsplit

from anyio import CancelScope
import httpx
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, StreamingResponse

from gateway.common.opencode_model_policy import account_models_revision, validate_account_providers
from gateway.common.security.opencode_relay_auth import HEADER, parse_assertion, verify_assertion
from gateway.extensions.yuanrong_frontend_client import YuanrongAgentApiError
from gateway.services.cloud_environments import EnvironmentUnavailable
from gateway.services.cloud_opencode_pool import OpenCodeConfigurationError, OpenCodeFault
from gateway.services.cloud_workspace_projects import project_directory as _project_directory

logger = logging.getLogger(__name__)
_NATIVE_ID = r"[A-Za-z0-9_-]{1,160}"
_NATIVE_ID_PATTERN = re.compile(_NATIVE_ID)
_GET = re.compile(rf"(?:global/health|event|provider|session(?:/(?:status|{_NATIVE_ID}(?:/message)?))?)\Z")
_POST = re.compile(rf"(?:session(?:/{_NATIVE_ID}/(?:abort|prompt_async))?|(?:permission|question)/{_NATIVE_ID}/reply)\Z")
_MAX_BODY = 8 * 1024 * 1024


def _event_session(event):
    props = event.get("properties")
    if not isinstance(props, dict):
        return None
    info, part = props.get("info"), props.get("part")
    candidates = [props.get("sessionID")]
    if isinstance(part, dict):
        candidates.append(part.get("sessionID"))
    if isinstance(info, dict):
        key = "id" if str(event.get("type", "")).startswith("session.") else "sessionID"
        candidates.append(info.get(key))
    identifiers = {value for value in candidates if isinstance(value, str) and _NATIVE_ID_PATTERN.fullmatch(value)}
    return next(iter(identifiers)) if len(identifiers) == 1 else None


class _RelayResponse(StreamingResponse):
    """Keep the remote request and its Provider hold for the ASGI response."""

    def __init__(self, upstream: httpx.Response, scope: AsyncExitStack, *, content=None):
        self._scope = scope
        super().__init__(content if content is not None else upstream.aiter_bytes(), status_code=upstream.status_code, headers={
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
        pool.fault_check = self._fault

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
            if result.status_code != 200:
                return False
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
            if not isinstance(states, dict) or not all(
                isinstance(state, dict) and state.get("type") == "idle" for state in states.values()
            ):
                return False
            for path in ("permission", "question"):
                url, query = self._route(lease, path)
                pending = await self._client.get(url, params=query, auth=("opencode", lease.password), timeout=5)
                pending.raise_for_status()
                if pending.json() != []:
                    return False
            return True
        except (httpx.HTTPError, ValueError):
            return False

    async def _fault(self, lease) -> OpenCodeFault | None:
        url, query = self._route(lease, "global/health")
        try:
            result = await self._client.get(url, params=query, auth=("opencode", lease.password), timeout=5)
        except httpx.RemoteProtocolError:
            # YuanRong can close the response without headers on a refused sandbox tunnel.
            # The pool also requires a refusal from the exact container's own port.
            return OpenCodeFault.LISTENER_UNAVAILABLE
        except httpx.ReadTimeout:
            return OpenCodeFault.HEALTH_STALLED
        except httpx.HTTPError:
            return None
        if result.status_code == 502 and result.content.strip() == b"failed to dial sandbox":
            return OpenCodeFault.LISTENER_UNAVAILABLE
        return None

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

    async def _shared_events(self, upstream, lease, project_id):
        owned = self.pool.project_sessions(lease, project_id)
        frame = bytearray()
        async for line in upstream.aiter_lines():
            if line.startswith("data:"):
                frame.extend(line[5:].removeprefix(" ").encode())
                frame.extend(b"\n")
                if len(frame) > _MAX_BODY:
                    raise ValueError("OpenCode SSE frame exceeds the relay limit")
            elif not line and frame:
                event = json.loads(frame)
                frame.clear()
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                if kind in ("server.connected", "server.heartbeat"):
                    yield b"data: " + json.dumps({"type": kind, "properties": {}}).encode() + b"\n\n"
                    continue
                native_id = _event_session(event)
                if native_id is None:
                    continue
                if native_id in owned or self.pool.owns_session(lease, project_id, native_id):
                    owned.add(native_id)
                    yield b"data: " + json.dumps(event, ensure_ascii=False).encode() + b"\n\n"

    async def _authorize_shared(self, lease, project_id, method, path, body):
        resource, _, tail = path.partition("/")
        native_id = tail.split("/", 1)[0]
        if resource == "session" and native_id and tail != "status":
            if not self.pool.owns_session(lease, project_id, native_id):
                return False
            if method == "POST" and tail.endswith("/prompt_async"):
                payload = json.loads(body)
                # Native message/part identifiers are global to the shared store.
                if not isinstance(payload, dict) or not isinstance(payload.get("parts"), list):
                    raise ValueError("Invalid shared OpenCode prompt")
                if "messageID" in payload or any(
                    not isinstance(part, dict) or "id" in part for part in payload["parts"]
                ):
                    raise ValueError("OpenCode message identifiers are assigned by the shared service")
        if resource == "session" and method == "POST" and not tail:
            payload = json.loads(body) if body else {}
            if not isinstance(payload, dict) or set(payload) - {"title", "parentID"}:
                raise ValueError("Invalid shared OpenCode session attributes")
            parent = payload.get("parentID")
            return parent is None or (
                isinstance(parent, str) and self.pool.owns_session(lease, project_id, parent)
            )
        if resource in ("permission", "question"):
            url, params = self._route(lease, resource)
            result = await self._client.get(url, params=params, auth=("opencode", lease.password), timeout=5)
            result.raise_for_status()
            pending = result.json()
            if not isinstance(pending, list):
                raise EnvironmentUnavailable("OpenCode pending controls are unavailable")
            return any(isinstance(item, dict) and item.get("id") == native_id
                       and isinstance(item.get("sessionID"), str)
                       and self.pool.owns_session(lease, project_id, item["sessionID"]) for item in pending)
        return True

    async def _shared_json(self, upstream, lease, project_id, method, path):
        data = json.loads(await upstream.aread())
        if method == "POST":
            native_id = data.get("id") if isinstance(data, dict) else None
            if (not isinstance(native_id, str) or not _NATIVE_ID_PATTERN.fullmatch(native_id)
                    or data.get("directory") != lease.directory):
                raise EnvironmentUnavailable("OpenCode returned a session outside its project")
            self.pool.register_session(lease, project_id, native_id)
        else:
            owned = self.pool.project_sessions(lease, project_id)
            if path == "session/status" and isinstance(data, dict):
                data = {native_id: status for native_id, status in data.items() if native_id in owned}
            elif path == "session" and isinstance(data, list):
                data = [item for item in data if isinstance(item, dict) and item.get("id") in owned]
            else:
                raise EnvironmentUnavailable("OpenCode returned an invalid session listing")
        return JSONResponse(data, status_code=upstream.status_code, headers={"Cache-Control": "no-store"})

    async def handle(self, request: Request):
        return await self._handle(request, shared=False)

    async def handle_shared(self, request: Request):
        return await self._handle(request, shared=True)

    async def _handle(self, request: Request, *, shared: bool):
        project_id, path = request.path_params["project_id"], request.path_params["path"]
        sync = request.method == "POST" and path == "account-models/sync"
        if not (sync or (request.method == "GET" and _GET.fullmatch(path))
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
            if sync:
                change = json.loads(body)
                providers = None
                if isinstance(change, dict) and set(change) == {"provider", "previous"}:
                    providers = change["provider"]
                    validate_account_providers(providers)
                    revision = account_models_revision(providers)
                elif (isinstance(change, dict) and set(change) == {"revision"}
                      and isinstance(change["revision"], str) and re.fullmatch(r"[0-9a-f]{64}", change["revision"])):
                    revision = change["revision"]
                else:
                    return JSONResponse({"code": "INVALID_REQUEST"}, status_code=400)
                current = await self.pool.sync_models(account, project_id, directory, revision,
                                                      shared=shared, models=providers, previous=change.get("previous"))
                return JSONResponse({"revision": current}, headers={"Cache-Control": "no-store"})
            hold = (self.pool.hold(account, project_id, directory, shared=True) if shared
                    else self.pool.hold(account, project_id, directory))
            lease = await scope.enter_async_context(hold)
            if shared and not await self._authorize_shared(lease, project_id, request.method, path, body):
                return JSONResponse({"code": "NOT_FOUND"}, status_code=404)
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

            if shared and upstream.is_success and path in ("session", "session/status"):
                return await self._shared_json(upstream, lease, project_id, request.method, path)
            events = self._shared_events(upstream, lease, project_id) if shared and path == "event" and upstream.is_success else None
            response = _RelayResponse(upstream, scope, content=events)
            handed_off = True
            return response
        except OpenCodeConfigurationError as exc:
            return JSONResponse({"code": str(exc)}, status_code=409)
        except (PermissionError, FileNotFoundError, KeyError, TypeError, ValueError):
            return JSONResponse({"code": "OPENCODE_FORBIDDEN"}, status_code=403)
        except (EnvironmentUnavailable, YuanrongAgentApiError, httpx.HTTPError, ClientDisconnect, OSError, TimeoutError) as exc:
            logger.warning("Managed OpenCode request failed (%s)", type(exc).__name__)
            return JSONResponse({"code": "OPENCODE_UNAVAILABLE"}, status_code=503)
        finally:
            if not handed_off:
                with CancelScope(shield=True):
                    await scope.aclose()
