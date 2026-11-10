"""Thin account/environment entry points on the existing Gateway host."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import Request
from fastapi.responses import JSONResponse
from gateway.auth.accounts import AccountError, credential
from gateway.auth.account_authenticator import current_account
from gateway.auth.remote_accounts import AccountAuthorityUnavailable
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.cloud_workspace.config import CloudConfig, CONFIG_ENV
from gateway.services.cloud_environments import EnvironmentUnavailable
from gateway.extensions.sdk.application_plugin import ApplicationPluginExtension, HTTPRouteContribution

COOKIE = "jiuwenswarm_organization"

def public_environment(row):
    return {key: row[key] for key in ("environment_id", "operation_id", "state", "instance_id")}

def normalized_origin(value):
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("invalid origin")
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)

class CloudWorkspacePlugin(ApplicationPluginExtension):
    plugin_id = "cloud_workspace"

    def __init__(self, config):
        self.config = config
        self.accounts = self.environments = self.authenticator = None
        self._password_slots = asyncio.Semaphore(2)
        self.set_extension_dir(Path(__file__).parent)

    async def initialize(self, config=None):
        if self.config is not None:
            self.config.validate()

    async def configure_services(self, services):
        from gateway.services.cloud_workspace_assembly import assemble
        if self.config is None:
            self.config = CloudConfig.load()
        self.accounts, self.authenticator, self.environments = assemble(self.config, services.require_agent_client())

    def http_routes(self):
        return tuple(HTTPRouteContribution(self.config.api_prefix + path, self.http, methods) for path, methods in (
            ("/register", ("POST",)), ("/login", ("POST",)), ("/logout", ("POST",)),
            ("/status", ("GET",)), ("/environment", ("GET",)), ("/environment/ensure", ("POST",)),
        ))

    def bind_web_channel(self, channel, services):
        for method in ("cloud.environment.ensure", "cloud.environment.status"):
            def make_handler(name):
                async def handler(ws, req_id, params, session_id):
                    try:
                        principal = current_account()
                        if principal is None:
                            raise PermissionError("account login required")
                        identity = await principal.check()
                        if params:
                            raise ValueError("environment endpoint takes no selectors")
                        row = (await self.environments.ensure(identity) if name.endswith("ensure")
                               else self.environments.store.get(identity))
                        await principal.check()
                        await channel.send_response(ws, req_id, ok=True, payload=public_environment(row))
                    except PermissionError:
                        await channel.send_response(ws, req_id, ok=False, code="UNAUTHORIZED")
                    except ValueError:
                        await channel.send_response(ws, req_id, ok=False, code="INVALID_REQUEST")
                    except (EnvironmentUnavailable, AccountAuthorityUnavailable, TimeoutError, ConnectionError):
                        await channel.send_response(ws, req_id, ok=False, code="ENVIRONMENT_UNAVAILABLE")
                return handler
            channel.register_method(method, make_handler(method), local_only=True)

    async def _body(self, request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                raise AccountError("BODY_TOO_LARGE", "request body too large", 413)
        body = json.loads(raw or b"{}")
        if not isinstance(body, dict):
            raise ValueError("object required")
        return body

    async def http(self, request: Request):
        response = await self._http(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    async def _http(self, request):
        if self.accounts is None:
            return JSONResponse({"code": "SERVICES_UNAVAILABLE"}, status_code=503)
        token = credential(request.headers)
        op = request.url.path.removeprefix(self.config.api_prefix)
        try:
            if request.method == "POST":
                origin = request.headers.get("origin")
                if ((origin and normalized_origin(origin) != normalized_origin(self.config.public_origin))
                        or (not origin and request.headers.get("x-jiuwen-auth") != "1")):
                    raise PermissionError("origin denied")
                body = await self._body(request)
            else:
                body = {}
            if op in {"/register", "/login"}:
                if set(body) != {"username", "password"}:
                    raise ValueError("username and password required")
                if op == "/register":
                    if not self.config.registration_enabled:
                        return JSONResponse({"code": "REGISTRATION_DISABLED"}, status_code=403)
                    async with self._password_slots:
                        account, row = await self.environments.register(body["username"], body["password"])
                    return JSONResponse({**account, "environment": public_environment(row)}, status_code=201)
                async with self._password_slots:
                    session = await asyncio.to_thread(self.accounts.login, body["username"], body["password"])
                login_token = session.pop("token")
                response = JSONResponse({**session, "authenticated": True, "actor_id": session["user_id"]})
                response.set_cookie(COOKIE, login_token, max_age=self.accounts.ttl,
                                    secure=True, httponly=True, samesite="strict", path="/")
                return response
            result = await self.authenticator.authenticate(AuthContext(channel_type="http", headers=dict(request.headers)))
            if not result.success:
                if result.extensions.get("error_code") == "AUTHORITY_UNAVAILABLE":
                    raise AccountAuthorityUnavailable("account authority unavailable")
                if op == "/logout" and not body:
                    # Preserve the authority's idempotent logout contract.
                    await asyncio.to_thread(self.accounts.logout, token)
                    response = JSONResponse({"authenticated": False})
                    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
                    return response
                if op == "/status":
                    return JSONResponse({"enabled": True, "authenticated": False, "execution_mode": "user_instance",
                                         "authority": self.config.authority, "registration_enabled": self.config.registration_enabled,
                                         "auth_backend": "builtin"})
                raise PermissionError("account login required")
            principal = current_account()
            identity = await principal.check()
            if op == "/status":
                return JSONResponse({**identity, "authenticated": True, "enabled": True, "actor_id": identity["user_id"],
                                     "subject_id": identity["user_id"], "auth_backend": "builtin", "execution_mode": "user_instance"})
            if body:
                raise ValueError("no client-selectable identity or infrastructure")
            if op == "/logout":
                # Revoke the authority first, then fence the currently bound
                # epoch; a concurrent rebuild cannot escape the logout barrier.
                await asyncio.to_thread(self.accounts.logout, token)
                try:
                    await asyncio.to_thread(self.environments.store.revoke, identity, token)
                except EnvironmentUnavailable:
                    pass  # An account without a binding has no instance assertions.
                response = JSONResponse({"authenticated": False})
                response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
                return response
            row = (await self.environments.ensure(identity) if op == "/environment/ensure"
                   else self.environments.store.get(identity))
            await principal.check()
            return JSONResponse(public_environment(row))
        except AccountError as exc:
            return JSONResponse({"code": exc.code}, status_code=exc.status)
        except PermissionError:
            return JSONResponse({"code": "UNAUTHORIZED"}, status_code=401)
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"code": "INVALID_REQUEST"}, status_code=400)
        except AccountAuthorityUnavailable:
            return JSONResponse({"code": "AUTHORITY_UNAVAILABLE"}, status_code=503)
        except (EnvironmentUnavailable, TimeoutError, ConnectionError):
            return JSONResponse({"code": "ENVIRONMENT_UNAVAILABLE"}, status_code=503)

    async def shutdown(self):
        # The host owns Router shutdown and its writer lease.
        return None

async def register_extensions(registry):
    if not os.environ.get(CONFIG_ENV):
        return []
    plugin = CloudWorkspacePlugin(None)
    registry.register_application_plugin(plugin)
    return [plugin]
