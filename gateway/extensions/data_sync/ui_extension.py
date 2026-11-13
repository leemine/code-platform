"""Same-origin UI composition; original cloud accounts remain the authority."""
import asyncio
import http.client
import json
import logging
import sqlite3
import time
from pathlib import Path

from websockets.exceptions import WebSocketException

from fastapi import Request
from fastapi.responses import JSONResponse

from gateway.auth.account_authenticator import current_account
from gateway.auth.remote_accounts import AccountAuthorityUnavailable
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.sdk.application_plugin import ApplicationPluginExtension, HTTPRouteContribution, WebSocketRouteContribution
from gateway.services.cloud_environments import EnvironmentUnavailable
from gateway.services.data_sync.ui import COOKIE, CloudDirectoryUI, LocalDirectoryUI, origin
from jiuwenswarm.data_sync.contract import SyncError

PREFIX = "/api/v1/data-sync"
logger = logging.getLogger(__name__)
FIELDS = {"status": set(), "login": {"username", "password"}, "logout": set(),
          "view": {"offset", "version"}, "choices": set(), "publish": {"operation_id", "project_ids"},
          "refresh": set(), "revoke": {"source_id"},
          "workspace": {"operation", "path", "name", "offset", "address_version"}}


class DirectoryUIPlugin(ApplicationPluginExtension):
    plugin_id = "data_sync_ui"

    def __init__(self, *, local_config=None, directory=None, cloud=None):
        self.local = LocalDirectoryUI(local_config) if local_config else None
        self.directory, self.cloud = directory, cloud
        self.slots = directory._slots if directory is not None else asyncio.Semaphore(4)
        self.set_extension_dir(Path(__file__).parent)

    async def initialize(self, config=None):
        return None

    async def shutdown(self):
        if self.local:
            await self.local.close()

    async def configure_services(self, services):
        if self.local:
            from gateway.routing.e2a_proxy import is_legacy_shared_directory_client
            if not is_legacy_shared_directory_client(services.agent_client):
                raise ValueError("local sync requires the original shared-directory local client")

    def http_routes(self):
        return tuple(HTTPRouteContribution(PREFIX + "/" + action, self.http,
                     ("GET",) if action == "status" else ("POST",)) for action in FIELDS)

    def websocket_routes(self):
        from gateway.services.cloud_execution_bridge import PATH
        return (WebSocketRouteContribution(PATH, self.local.execution.serve),) if self.local else ()

    async def http(self, request: Request):
        started = time.monotonic()
        request.state.cloud_stage = "admission"
        try:
            async with asyncio.timeout(150), self.slots:
                response = await self._http(request)
        except PermissionError:
            response = JSONResponse({"code": "UNAUTHORIZED"}, status_code=401)
        except SyncError as exc:
            response = JSONResponse({"code": exc.code}, status_code=409)
        except (EnvironmentUnavailable, AccountAuthorityUnavailable, TimeoutError, ConnectionError,
                OSError, sqlite3.Error, http.client.HTTPException, WebSocketException) as exc:
            logger.warning("Cloud UI unavailable stage=%s kind=%s elapsed_ms=%.1f",
                           request.state.cloud_stage, type(exc).__name__, (time.monotonic() - started) * 1000)
            response = JSONResponse({"code": "SYNC_UNAVAILABLE"}, status_code=503)
        except (ValueError, KeyError, TypeError):
            response = JSONResponse({"code": "INVALID_REQUEST"}, status_code=400)
        if self.local and request.url.path.endswith('/workspace'):
            logger.info("Cloud workspace response stage=%s status=%s elapsed_ms=%.1f",
                        request.state.cloud_stage, response.status_code, (time.monotonic() - started) * 1000)
        response.headers["Server-Timing"] = f'cloud;dur={(time.monotonic() - started) * 1000:.1f}'
        response.headers["Cache-Control"] = "no-store"
        return response

    async def _http(self, request):
        config = self.local.config if self.local else {"public_origin": self.cloud().config.public_origin}
        expected = origin(config["public_origin"], local=bool(self.local))
        # Host and Origin are checked independently, including the loopback bridge.
        scheme = expected[0]
        try:
            if origin(scheme + "://" + request.headers.get("host", ""), local=bool(self.local)) != expected:
                raise PermissionError()
            supplied = request.headers.get("origin")
            if supplied and origin(supplied, local=bool(self.local)) != expected:
                raise PermissionError()
        except ValueError:
            raise PermissionError() from None
        action = request.url.path.removeprefix(PREFIX + "/")
        if action not in FIELDS:
            raise ValueError()
        params = {}
        if request.method == "POST":
            if request.headers.get("x-jiuwen-sync") != "1":
                raise PermissionError()
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 1024 * 1024:
                    raise ValueError()
            params = json.loads(raw or b"{}")
            if not isinstance(params, dict) or set(params) - FIELDS[action]:
                raise ValueError()
        if self.local:
            token = request.cookies.get(COOKIE)
            if action == "login":
                if set(params) != FIELDS["login"] or any(not isinstance(v, str) or len(v) > 512 for v in params.values()):
                    raise ValueError()
                value = await asyncio.to_thread(self.local.accounts.call, "login", None, params)
                await self.local.workspaces.discard(token)
                await self.local.execution.discard(token)
                response = JSONResponse({"authenticated": True})
                response.set_cookie(COOKIE, value["token"], secure=expected[0] == "https", httponly=True,
                                    samesite="strict", path=PREFIX)
                return response
            if action == "logout":
                if token:
                    try:
                        await asyncio.to_thread(self.local.accounts.call, "logout", token, {})
                    finally:
                        await self.local.workspaces.discard(token)
                        await self.local.execution.discard(token)
                response = JSONResponse({"authenticated": False})
                response.delete_cookie(COOKIE, path=PREFIX, secure=expected[0] == "https", httponly=True, samesite="strict")
                return response
            try:
                request.state.cloud_stage = "identity_before"
                identity = await self.local.identity(token)
            except PermissionError:
                if action == "status":
                    return JSONResponse({"enabled": True, "kind": "local", "authenticated": False,
                                         "cloud_origin": self.local.config["cloud_origin"]})
                raise
            if action == "status":
                return JSONResponse({"enabled": True, "authenticated": True, "kind": "local",
                                     "username": identity.get("username", ""),
                                     "scope": [identity["authority"], identity["actor_id"]],
                                     "cloud_origin": self.local.config["cloud_origin"]})
            if action == "workspace":
                from gateway.services.cloud_workspace_client import workspace_request
                address_version = params.pop("address_version", None)
                if address_version is not None and (type(address_version) is not int or address_version != 1 or params.get("operation") != "open"):
                    raise ValueError("unsupported cloud address version")
                request.state.cloud_stage = "workspace_" + str(params.get("operation") if params.get("operation") in {"environment", "ensure", "list", "mkdir", "open"} else "invalid")
                value = await workspace_request(self.local, token, params)
                if address_version == 1:
                    from gateway.services.cloud_resource_address import CloudAddresses
                    value = CloudAddresses(self.local.endpoint, identity).result(value)
            else:
                value = await self.local.run(identity, token, action, params)
            request.state.cloud_stage = "identity_after"
            latest = await self.local.identity(token)
            if (latest["authority"], latest["actor_id"]) != (identity["authority"], identity["actor_id"]):
                await self.local.workspaces.discard(token)
                raise PermissionError()
        else:
            if action in {"login", "logout", "workspace"}:
                raise ValueError()  # The existing cloud account UI owns its session.
            cloud = self.cloud()
            result = await cloud.authenticator.authenticate(AuthContext(channel_type="http", headers=dict(request.headers)))
            if not result.success:
                if result.extensions.get("error_code") == "AUTHORITY_UNAVAILABLE":
                    raise AccountAuthorityUnavailable()
                raise PermissionError()
            principal = current_account()
            identity = await principal.check()
            if action == "status":
                return JSONResponse({"enabled": True, "authenticated": True, "kind": "cloud",
                                     "username": identity.get("username", ""),
                                     "scope": [identity["authority"], identity["user_id"]]})
            value = await CloudDirectoryUI(self.directory).run(principal, action, params)
            await principal.check()
        return JSONResponse(value)
