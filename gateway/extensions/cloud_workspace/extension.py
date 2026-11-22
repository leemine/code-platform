"""Thin account/environment entry points on the existing Gateway host."""
from __future__ import annotations
import asyncio
import hashlib
import logging
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import Request
from fastapi.responses import JSONResponse
from gateway.auth.accounts import AccountError, credential
from gateway.auth.account_authenticator import current_account
from gateway.auth.remote_accounts import AccountAuthorityUnavailable
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.cloud_workspace.config import (
    CloudConfig, CONFIG_ENV, OPENCODE_RELAY_PATH, OPENCODE_WORKER_RELAY_PATH,
    OPENCODE_MANAGED_RELAY_PATH, OPENCODE_MANAGED_WORKER_RELAY_PATH,
)
from gateway.services.cloud_environments import EnvironmentUnavailable
from gateway.common.managed_codex import (
    MODEL_UNAVAILABLE, PROFILE_ID as CODEX_PROFILE_ID, RELAY_PATH as CODEX_RELAY_PATH, validate_device_model_id,
)
from gateway.common.runtime_device import DEVICE_ID
from gateway.services.cloud_provider_allocation import RuntimeDeviceNameConflict
from gateway.extensions.sdk.application_plugin import (
    ApplicationPluginExtension,
    HTTPRouteContribution,
    WebSocketRouteContribution,
)
from gateway.services.cloud_opencode_pool import PROFILE_ID, OpenCodeConfigurationError

logger = logging.getLogger(__name__)
COOKIE = "jiuwenswarm_organization"
MODEL_REJECTION_PATH = "/observations/opencode-model-rejection"
MODEL_REJECTION_REASONS = frozenset({
    "opencode_model_not_registered",
    "opencode_shared_model_group_unsupported",
    "opencode_shared_model_options_unsupported",
    "opencode_shared_model_protocol_unsupported",
})

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
        self._opencode_reaper = None
        self._codex_reaper = None
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
        if self.environments.opencode_relay:
            self._opencode_reaper = asyncio.create_task(
                self._reap_provider(self.environments.opencode_relay.pool, "OpenCode"))
        if self.environments.codex_relay:
            self._codex_reaper = asyncio.create_task(
                self._reap_provider(self.environments.codex_relay.pool, "Codex"))

    @staticmethod
    async def _reap_provider(pool, provider):
        while True:
            await asyncio.sleep(max(1.0, min(30.0, pool.idle_seconds)))
            try:
                await pool.reclaim_idle()
            except Exception as exc:
                logger.warning("Managed %s idle sweep failed (%s)", provider, type(exc).__name__)

    def websocket_routes(self):
        relay = getattr(self.environments, "codex_relay", None)
        if relay is None:
            return ()
        return (WebSocketRouteContribution(self.config.api_prefix + CODEX_RELAY_PATH, relay.handle),)

    def http_routes(self):
        routes = tuple(HTTPRouteContribution(self.config.api_prefix + path, self.http, methods) for path, methods in (
            ("/register", ("POST",)), ("/login", ("POST",)), ("/logout", ("POST",)),
            ("/status", ("GET",)), ("/environment", ("GET",)), ("/environment/ensure", ("POST",)),
        ))
        if self.environments is not None and self.environments.opencode_relay:
            relay = self.environments.opencode_relay
            routes += (HTTPRouteContribution(self.config.api_prefix + MODEL_REJECTION_PATH, self.http, ("POST",)),)
            routes += tuple(HTTPRouteContribution(
                self.config.api_prefix + prefix + "/{project_id}/{path:path}", handler, ("GET", "POST"),
            ) for prefix, handler in (
                (OPENCODE_RELAY_PATH, relay.handle), (OPENCODE_WORKER_RELAY_PATH, relay.handle_shared),
                (OPENCODE_MANAGED_RELAY_PATH, relay.handle), (OPENCODE_MANAGED_WORKER_RELAY_PATH, relay.handle_shared),
            ))
            routes += tuple(HTTPRouteContribution(
                self.config.api_prefix + prefix + "-device/{runtime_id}/{project_id}/{path:path}",
                relay.handle_device, ("GET", "POST"),
            ) for prefix in (OPENCODE_RELAY_PATH, OPENCODE_MANAGED_RELAY_PATH))
        return routes

    def bind_web_channel(self, channel, services):
        from gateway.services.project_environments import ProjectEnvironments
        self.projects = ProjectEnvironments(channel, services.require_agent_client())
        self.projects.register()
        opencode = getattr(self.environments, "opencode_relay", None)
        codex = getattr(self.environments, "codex_relay", None)
        if opencode or codex:
            from functools import partial

            from gateway.routing.e2a_proxy import fetch_agent_unary
            from jiuwenswarm.common.schema.message import ReqMethod

            providers = {}
            if opencode:
                providers[PROFILE_ID] = ("opencode-direct", opencode.pool)
            if codex:
                providers[CODEX_PROFILE_ID] = ("codex-direct", codex.pool)

            def public_runtime(profile_id, status):
                payload = {"provider_id": providers[profile_id][0], "runtime_profile_id": profile_id, **status}
                if profile_id == PROFILE_ID and "display_name" not in status:
                    payload["display_name"] = self.config.opencode_provider.get("display_name")
                return payload

            async def codex_device_models(account, model_id=None):
                if not codex or not codex.pool.runtime_template(account)["available"]:
                    raise PermissionError("Codex device template unavailable")
                ok, catalog = await fetch_agent_unary(
                    agent_client=self.projects.client, req_method=ReqMethod.PROJECT_RUNTIME_PREPARE,
                    params={"provider_id": "codex-direct", "allowed_model_endpoints": sorted(codex.allowed_endpoints),
                            "model_id": model_id},
                    session_id=None, user_id=account["account_id"], channel_id=channel.channel_id,
                    label="cloud-runtime-models", timeout_seconds=30,
                )
                if not ok or not isinstance(catalog.get("model_ids"), list):
                    raise EnvironmentUnavailable("Codex device models are unavailable")
                ids = [validate_device_model_id(value) for value in catalog["model_ids"]]
                default_id = catalog.get("default_model_id")
                return {"model_ids": ids, "default_model_id": default_id if default_id in ids else None}

            async def runtime_request(method, ws, req_id, params, session_id):
                try:
                    principal = current_account()
                    if principal is None:
                        raise PermissionError("account login required")
                    if not isinstance(params, dict):
                        raise ValueError("invalid runtime request")
                    identity = await principal.check()
                    if method == "cloud.runtime.list":
                        if params:
                            raise ValueError("runtime list takes no selectors")
                        account = await asyncio.to_thread((opencode or codex).store.get, identity)
                        runtimes = (
                            [public_runtime(PROFILE_ID, await asyncio.to_thread(opencode.pool.account_runtime, account))]
                            if opencode else []
                        )
                        templates = []
                        for profile_id, (_, pool) in providers.items():
                            devices = await asyncio.to_thread(pool.account_devices, account)
                            runtimes.extend(public_runtime(profile_id, device) for device in devices)
                            templates.append(pool.runtime_template(account))
                        payload = {"runtimes": runtimes, "templates": templates}
                    elif method == "cloud.runtime.models":
                        if params:
                            raise ValueError("runtime model catalog takes no selectors")
                        account = await asyncio.to_thread(codex.store.get, identity)
                        payload = await codex_device_models(account)
                    elif method in {"cloud.runtime.create", "cloud.runtime.start"}:
                        create = method == "cloud.runtime.create"
                        fields = {"runtime_profile_id", "display_name", "create_token"} if create else {"runtime_id"}
                        explicit_model = create and "model_id" in params
                        if explicit_model:
                            fields.add("model_id")
                        if set(params) != fields:
                            raise ValueError("invalid managed device selector")
                        account = await asyncio.to_thread((opencode or codex).store.get, identity)
                        if create:
                            profile_id = params["runtime_profile_id"]
                            if not isinstance(profile_id, str) or profile_id not in providers:
                                raise ValueError("unknown managed device template")
                            _, pool = providers[profile_id]
                            if explicit_model:
                                if profile_id != CODEX_PROFILE_ID:
                                    raise ValueError("only the Codex template accepts a device model")
                                model_id = validate_device_model_id(params["model_id"])
                                models = await codex_device_models(account, model_id)
                                if model_id not in models["model_ids"]:
                                    await principal.check()
                                    await channel.send_response(ws, req_id, ok=False, code=MODEL_UNAVAILABLE)
                                    return
                                await principal.check()
                                status = await asyncio.to_thread(
                                    pool.register_device, account, params["display_name"], params["create_token"], model_id,
                                )
                            else:
                                status = await asyncio.to_thread(
                                    pool.register_device, account, params["display_name"], params["create_token"],
                                )
                        else:
                            runtime_id = params["runtime_id"]
                            if not isinstance(runtime_id, str) or not DEVICE_ID.fullmatch(runtime_id):
                                raise ValueError("invalid managed device identifier")
                            matches = []
                            for candidate, (_, pool) in providers.items():
                                devices = await asyncio.to_thread(pool.account_devices, account)
                                if any(device["runtime_id"] == runtime_id for device in devices):
                                    matches.append(candidate)
                            if len(matches) != 1:
                                raise PermissionError("unknown managed device")
                            profile_id = matches[0]
                            _, pool = providers[profile_id]
                            status = await asyncio.to_thread(pool.device_runtime, account, runtime_id)
                        runtime_id = status["runtime_id"]
                        await principal.check()
                        prepare = {"runtime_id": runtime_id}
                        if profile_id == CODEX_PROFILE_ID:
                            model_id = await asyncio.to_thread(pool.device_model_id, account, runtime_id)
                            prepare.update(provider_id="codex-direct", model_id=model_id)
                        ok, result = await fetch_agent_unary(
                            agent_client=self.projects.client, req_method=ReqMethod.PROJECT_RUNTIME_PREPARE,
                            params=prepare, session_id=None, user_id=identity["user_id"],
                            channel_id=channel.channel_id, label="cloud-runtime-device", timeout_seconds=150,
                        )
                        status = await asyncio.to_thread(pool.device_runtime, account, runtime_id)
                        payload = {**public_runtime(profile_id, status), "start_failed": not ok
                                   or result.get("ready") is not True or status["state"] != "ready"}
                        if not ok and result.get("code") == MODEL_UNAVAILABLE:
                            payload["start_error"] = MODEL_UNAVAILABLE
                    else:
                        ensure = method == "project.runtime.ensure"
                        fields = {"project_id", "provider_id"} if ensure else {"project_id"}
                        if (set(params) != fields or not isinstance(params["project_id"], str)
                                or ensure and params["provider_id"] != "opencode-direct"):
                            raise ValueError("invalid project runtime selector")
                        project_id = params["project_id"]
                        status = await asyncio.to_thread(opencode.project_runtime, identity, project_id)
                        if ensure and status["available"]:
                            await principal.check()
                            ok, result = await fetch_agent_unary(
                                agent_client=self.projects.client, req_method=ReqMethod.PROJECT_RUNTIME_PREPARE,
                                params={"project_id": project_id}, session_id=None,
                                user_id=identity["user_id"], channel_id=channel.channel_id,
                                label="cloud-runtime", timeout_seconds=150,
                            )
                            if not ok or result.get("ready") is not True:
                                if result.get("code") == "PROJECT_RUNTIME_FORBIDDEN":
                                    raise PermissionError("project prewarm denied")
                                raise EnvironmentUnavailable("project prewarm unavailable")
                            status = await asyncio.to_thread(opencode.project_runtime, identity, project_id)
                            if status["state"] != "ready":
                                raise EnvironmentUnavailable("project runtime is no longer ready")
                        payload = public_runtime(PROFILE_ID, status)
                    await principal.check()
                    await channel.send_response(ws, req_id, ok=True, payload=payload)
                except (OpenCodeConfigurationError, RuntimeDeviceNameConflict) as exc:
                    await channel.send_response(ws, req_id, ok=False, code=str(exc))
                except (PermissionError, FileNotFoundError):
                    await channel.send_response(ws, req_id, ok=False, code="PROJECT_RUNTIME_FORBIDDEN")
                except (EnvironmentUnavailable, AccountAuthorityUnavailable, OSError, KeyError, TypeError):
                    await channel.send_response(ws, req_id, ok=False, code="PROJECT_RUNTIME_UNAVAILABLE")
                except ValueError:
                    await channel.send_response(ws, req_id, ok=False, code="INVALID_REQUEST")

            methods = ("cloud.runtime.list", "cloud.runtime.create", "cloud.runtime.start")
            if opencode:
                methods += ("project.runtime.status", "project.runtime.ensure")
            if codex:
                methods += ("cloud.runtime.models",)
            for method in methods:
                channel.register_method(method, partial(runtime_request, method), local_only=True)
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
            if op == MODEL_REJECTION_PATH:
                reason = body.get("reason")
                if set(body) != {"reason"} or not isinstance(reason, str) or reason not in MODEL_REJECTION_REASONS:
                    raise ValueError("invalid model rejection observation")
                logger.info("opencode_web_model_rejected event_id=%s account_id=%s reason=%s",
                            secrets.token_hex(12), identity["user_id"], reason)
                return JSONResponse({"recorded": True})
            if op == "/status":
                return JSONResponse({**identity, "authenticated": True, "enabled": True, "actor_id": identity["user_id"],
                                     "subject_id": identity["user_id"], "auth_backend": "builtin", "execution_mode": "user_instance",
                                     "session_revision": hashlib.sha256(token.encode()).hexdigest()[:24]})
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
        if self._opencode_reaper is not None:
            self._opencode_reaper.cancel()
            await asyncio.gather(self._opencode_reaper, return_exceptions=True)
            await self.environments.opencode_relay.close()
        if self._codex_reaper is not None:
            self._codex_reaper.cancel()
            await asyncio.gather(self._codex_reaper, return_exceptions=True)
            await self.environments.codex_relay.pool.close()
        if hasattr(self, "projects"):
            await self.projects.close()

async def register_extensions(registry):
    if not os.environ.get(CONFIG_ENV):
        return []
    plugin = CloudWorkspacePlugin(None)
    registry.register_application_plugin(plugin)
    return [plugin]
