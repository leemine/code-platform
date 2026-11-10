import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from aiohttp import web
from fastapi import FastAPI
from websockets.legacy.server import serve
from gateway.auth.account_http import create_app as authority_app
from gateway.services.cloud_environments import EnvironmentUnavailable
from gateway.auth.accounts import AccountStore
from gateway.auth.account_authenticator import AccountAuthenticator, current_account
from gateway.auth.request_scope import current_scope
from gateway.common.security.service_auth import ServiceAuthenticator, check_service_handshake, configured_service_auth
from gateway.extensions.auth.common import apply_auth_result_to_ws, _handshake_cache_key
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.cloud_workspace.extension import CloudWorkspacePlugin
from gateway.extensions.registry import ExtensionRegistry
from gateway.extensions.application_host import mount_application_plugin_http_routes
from gateway.routing.agent_client import WebSocketAgentServerClient
from gateway.message_handler.message_handler import MessageHandler
from gateway.channel_manager.base import RobotMessageRouter
from gateway.channel_manager.web.web_connect import WebChannel, WebChannelConfig
from jiuwenswarm.common.e2a.models import E2AEnvelope
from jiuwenswarm.common.schema.agent import AgentResponse
from jiuwenswarm.server.front.protocol import parse_raw_message, encode_response
from tests.unit_tests.cloud_workspace.test_cloud_workspace import config, service, Infrastructure, registered, isolated_scope, Ws
from tests.unit_tests.extensions.test_agentos_router import _router_client

@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["revoked", "tampered", "missing_assertion", "broken_revocation_file"])
async def test_real_front_closes_rejected_instance_request(config, monkeypatch, failure):
    from websockets.legacy.client import connect
    from websockets.exceptions import ConnectionClosed
    from jiuwenswarm.server.front.connection import ConnectionHandler

    accounts, app = service(config, Infrastructure())
    actor = await registered(app)
    row = app.store.prepare(actor["user_id"])
    token = accounts.login("test-user", "long-test-password")["token"]
    auth = ServiceAuthenticator(row["auth_file"])
    wire = auth.sign_wire(E2AEnvelope(request_id="rejected", channel="web", user_id=actor["user_id"],
                                     method="config.get", params={}).to_dict(), actor, token)
    if failure == "revoked":
        app.store.revoke(actor, token)
    elif failure == "tampered":
        wire["method"] = "models.list"
    elif failure == "missing_assertion":
        wire.pop("_organization_assertion")
    else:
        Path(row["auth_file"]).with_name("revocations.json").write_text("invalid json")
    monkeypatch.setenv("JIUWENSWARM_INSTANCE_AUTH_FILE", row["auth_file"])
    router = SimpleNamespace(dispatch=AsyncMock())
    handler = ConnectionHandler(None, router, None)

    async def serve_request(ws):
        await handler._handle_raw(ws, await ws.recv(), asyncio.Lock())

    async with serve(serve_request, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        async with connect(f"ws://127.0.0.1:{port}") as client:
            await client.send(json.dumps(wire))
            with pytest.raises(ConnectionClosed) as closed:
                await asyncio.wait_for(client.recv(), 2)
            assert closed.value.code == 1008
    router.dispatch.assert_not_awaited()

@pytest.mark.asyncio
async def test_real_account_http_original_host_composition_and_revocation(config, tmp_path):
    accounts = AccountStore(tmp_path / "authority-store" / "accounts.db", config.authority)
    runner = web.AppRunner(authority_app(accounts)); await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
    port = site._server.sockets[0].getsockname()[1]
    Path(config.account_backend_config).write_text(json.dumps({"url": f"http://127.0.0.1:{port}"}))
    infra = Infrastructure(); router = _router_client(infra, ws_client_factory=lambda: Ws(infra), sandbox_idle_timeout_seconds=0)
    plugin = CloudWorkspacePlugin(config)
    registry = ExtensionRegistry(None, {}, None); registry.register_application_plugin(plugin)
    await plugin.initialize(); await registry.configure_application_plugins(router); await router.connect("")
    app = FastAPI(); mount_application_plugin_http_routes(app, registry)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=config.public_origin) as browser:
            prefix = config.api_prefix; headers = {"Origin": config.public_origin}
            credentials = {"username": "real-account", "password": "long-test-password"}
            account = (await browser.post(prefix + "/register", json=credentials, headers=headers)).json()
            response = await browser.post(prefix + "/login", json=credentials, headers=headers)
            assert response.status_code == 200
            ready = await browser.post(prefix + "/environment/ensure", json={}, headers=headers)
            assert ready.json()["state"] == "READY" and infra.create_calls == 1
            cookie = response.headers["set-cookie"].split(";", 1)[0]
            identity = await router.authenticate_http(path="/ws", headers={"Cookie": cookie, **headers}, channel="web")
            assert identity.user_id == account["user_id"]
            assert not (config.state_root / "accounts.db").exists()
            assert (await browser.post(prefix + "/logout", json={}, headers=headers)).status_code == 200
            assert not (await router.authenticate_http(path="/ws", headers={"Cookie": cookie, **headers}, channel="web")).success
    finally:
        await router.disconnect(); await runner.cleanup()

@pytest.mark.asyncio
async def test_real_signed_socket_uses_original_client_and_front_protocol(config, monkeypatch):
    accounts, app = service(config, Infrastructure()); actor = await registered(app)
    row = app.store.prepare(actor["user_id"])
    monkeypatch.setenv("JIUWENSWARM_INSTANCE_AUTH_FILE", row["auth_file"])
    token = accounts.login("test-user", "long-test-password")["token"]
    auth = AccountAuthenticator(accounts)
    await auth.authenticate(AuthContext(headers={"Authorization": "Bearer " + token}))
    policy = app.instances._instance_lifecycle
    received = []
    async def handler(ws):
        await ws.send(json.dumps({"type": "event", "event": "connection.ack", "payload": {"status": "ready", "readiness": "AGENT_READY"}}))
        async for raw in ws:
            request = parse_raw_message(raw); received.append(request)
            response = AgentResponse(request_id=request.request_id, channel_id=request.channel_id, ok=True, payload={"owner": request.user_id})
            await ws.send(json.dumps(encode_response(response, response_id=request.request_id)))
    async def handshake(path, headers):
        return check_service_handshake((path, headers))
    server = await serve(handler, "127.0.0.1", 0, process_request=handshake)
    client = WebSocketAgentServerClient()
    client.set_transport_auth(headers=lambda: policy.transport_headers(actor["user_id"]), sign=lambda wire: policy.sign_request(actor["user_id"], wire))
    try:
        await client.connect(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
        assert client.agent_ready
        result = await client.send_request(E2AEnvelope(request_id="signed-one", channel="web", user_id=actor["user_id"], method="config.get", params={}), timeout=2)
        assert result.payload["owner"] == actor["user_id"]
        accounts.logout(token)
        with pytest.raises(PermissionError):
            await client.send_request(E2AEnvelope(request_id="revoked", channel="web", user_id=actor["user_id"], method="config.get", params={}), timeout=2)
        assert len(received) == 1
    finally:
        await client.disconnect(); server.close(); await server.wait_closed()

@pytest.mark.asyncio
async def test_existing_queue_restores_authorization_and_never_serializes_token(config):
    accounts, app = service(config, Infrastructure()); actor = await registered(app)
    token = accounts.login("test-user", "long-test-password")["token"]
    await AccountAuthenticator(accounts).authenticate(AuthContext(headers={"Authorization": "Bearer " + token}))
    principal = current_account()
    handler = object.__new__(MessageHandler); handler._user_messages = asyncio.Queue()
    msg = SimpleNamespace(id="message", user_id=actor["user_id"], metadata={})
    await handler.publish_user_messages(msg)
    current_scope.set(None)
    assert await handler.consume_user_messages() is msg
    assert current_account() is principal and not msg.metadata
    task = asyncio.create_task(principal.check())
    assert (await task)["user_id"] == actor["user_id"]
    current_scope.set(None); await handler.publish_user_messages(SimpleNamespace(id="local"))
    current_scope.set(principal); await handler.consume_user_messages()
    assert current_account() is None

@pytest.mark.asyncio
async def test_original_web_ingress_and_writer_stop_after_logout(config):
    accounts, app = service(config, Infrastructure()); await registered(app)
    token = accounts.login("test-user", "long-test-password")["token"]
    result = await AccountAuthenticator(accounts).authenticate(AuthContext(headers={"Authorization": "Bearer " + token}))
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    ws = SimpleNamespace(closed=False, send=AsyncMock(), close=AsyncMock(), _jiuwen_ws_id="test")
    apply_auth_result_to_ws(ws, result)
    accounts.logout(token)
    await channel._handle_raw_message(ws, '{"type":"req","id":"x","method":"config.get","params":{}}', {})
    ws.close.assert_awaited_once(); ws.send.assert_not_awaited()
    channel._send_queues["test"] = asyncio.Queue(); channel._send_queues["test"].put_nowait({"sensitive": "output"})
    await channel._writer_loop(ws, "test")
    assert ws.close.await_count == 2; ws.send.assert_not_awaited()

def test_cookie_handshake_identities_do_not_collide():
    assert _handshake_cache_key("/ws", {"Cookie": "jiuwenswarm_organization=a"}) != _handshake_cache_key("/ws", {"Cookie": "jiuwenswarm_organization=b"})

def test_cloud_role_missing_binding_fails_but_local_is_unchanged(monkeypatch):
    monkeypatch.delenv("JIUWENSWARM_INSTANCE_AUTH_FILE", raising=False)
    monkeypatch.setenv("CODE_PLATFORM_ROLE", "account-instance")
    with pytest.raises(PermissionError): configured_service_auth()
    monkeypatch.delenv("CODE_PLATFORM_ROLE")
    assert configured_service_auth() is None

@pytest.mark.asyncio
async def test_maintenance_purpose_cannot_be_reused_for_execution(config):
    _, app = service(config, Infrastructure()); actor = await registered(app)
    row = app.store.prepare(actor["user_id"]); auth = ServiceAuthenticator(row["auth_file"])
    wire = auth.sign_wire({"method": "models.list"}, service=True)
    assert auth.verify_wire(wire)["actor_id"] == actor["user_id"]
    with pytest.raises(PermissionError): auth.sign_wire({"method": "chat.send", "channel": "web"}, service=True)
    with pytest.raises(PermissionError): auth.sign_wire({"method": "config.set"}, service=True)

@pytest.mark.asyncio
async def test_import_preserves_original_instance_image_key_and_workspace(config, tmp_path):
    from dataclasses import replace
    infra = Infrastructure(); _, old = service(config, infra); actor = await registered(old)
    await old.instances.connect(""); row = await old.ensure(actor); await old.instances.disconnect()
    key_before = Path(row["auth_file"]).read_bytes()
    marker = Path(row["workspace"]) / "history.txt"; marker.write_text("original")
    _, imported = service(replace(config, state_root=tmp_path / "imported", workspace_root=tmp_path / "import-users", image="sha256:" + "b" * 64), infra)
    imported.store.adopt_existing(actor, instance_id=row["instance_id"], profile=row["profile"], workspace=row["workspace"], auth_file=row["auth_file"])
    await imported.instances.connect("")
    recovered = await imported.ensure(actor)
    assert recovered["instance_id"] == row["instance_id"] and recovered["profile"] == row["profile"]
    assert Path(row["auth_file"]).read_bytes() == key_before and marker.read_text() == "original"
    assert infra.create_calls == 1
    with pytest.raises(PermissionError):
        imported.store.adopt_existing(actor, instance_id="replacement", profile=row["profile"], workspace=row["workspace"], auth_file=row["auth_file"])
    await imported.instances.disconnect()

def test_relative_and_symlink_directory_escape_is_rejected(tmp_path):
    from jiuwenswarm.server.runtime.gateway_adapter.workspace_file_adapter import _resolve_within_workspace
    workspace = tmp_path / "workspace"; workspace.mkdir()
    (workspace / "outside").symlink_to(tmp_path)
    assert _resolve_within_workspace("..", workspace) is None
    assert _resolve_within_workspace("outside", workspace) is None
    assert _resolve_within_workspace("inside", workspace) == workspace / "inside"

@pytest.mark.asyncio
async def test_invalid_cloud_config_cannot_be_swallowed_by_optional_loader(tmp_path, monkeypatch):
    from gateway.extensions.loader import ExtensionLoader
    from gateway.extensions.cloud_workspace.config import CONFIG_ENV
    import gateway.extensions.cloud_workspace as package
    config_path = tmp_path / "invalid-config.json"; config_path.write_text("{}")
    monkeypatch.setenv(CONFIG_ENV, str(config_path))
    registry = ExtensionRegistry(None, {}, None)
    await ExtensionLoader(registry).load_extension(Path(package.__file__).parent)
    assert registry.get_application_plugin("cloud_workspace") is not None
    with pytest.raises((TypeError, KeyError)):
        await registry.configure_application_plugins(_router_client(Infrastructure()))

@pytest.mark.asyncio
async def test_file_response_guard_blocks_revoked_output():
    from tests.unit_tests.test_agentos_file_api_iam import _make_router, _enable_auth, _file_api_app
    from gateway.extensions.auth.credential_authenticator import AuthResult
    router = _make_router()
    async def revoked():
        raise PermissionError("revoked")
    _enable_auth(router, AuthResult(success=True, user_id="user-1", extensions={"delivery_guard": revoked}))
    router.list_container_files = AsyncMock(return_value={"files": ["sensitive"]})
    app = _file_api_app(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/file-api/list-files?user_id=user-1&session_id=sess-1")
    assert response.status_code == 401 and "sensitive" not in response.text

@pytest.mark.asyncio
async def test_runtime_ack_missing_is_not_application_ready(config):
    infra = Infrastructure(); _, app = service(config, infra); actor = await registered(app)
    class NotReady(Ws):
        agent_ready = False
    app.instances._ws_client_factory = lambda: NotReady(infra)
    app.instances._instance_lifecycle.ready_timeout = .01
    await app.instances.connect("")
    try:
        with pytest.raises(EnvironmentUnavailable):
            await app.ensure(actor)
        assert app.store.get(actor)["state"] == "ALLOCATED"
        assert infra.create_calls == 1
        app.instances._ws_client_factory = lambda: Ws(infra)
        assert (await app.ensure(actor))["state"] == "READY"
        assert infra.create_calls == 1
    finally:
        await app.instances.disconnect()

@pytest.mark.asyncio
async def test_unknown_receipt_survives_router_restart(config):
    infra = Infrastructure(); infra.lose_reply = True
    _, first = service(config, infra); actor = await registered(first)
    await first.instances.connect("")
    with pytest.raises(EnvironmentUnavailable): await first.ensure(actor)
    await first.instances.disconnect()
    _, second = service(config, infra); await second.instances.connect("")
    try:
        assert (await second.ensure(actor))["instance_id"] == "sbx-1"
        assert infra.create_calls == 1
    finally:
        await second.instances.disconnect()

@pytest.mark.asyncio
async def test_original_startup_cleanup_protects_durable_and_legacy_accounts(config):
    from tests.unit_tests.extensions.test_agentos_stale_cleanup import _CleanupRegistry, _record
    from gateway.extensions.agentos.agentos_router.stale_cleanup import cleanup_stale_sandboxes
    infra = Infrastructure(); _, app = service(config, infra); actor = await registered(app)
    registry = _CleanupRegistry([_record(user=actor["user_id"], framework="jiuwenswarm", instance_id="bound"),
                                 _record(user="legacy-subject", framework="jiuwenswarm", instance_id="old")])
    count = await cleanup_stale_sandboxes(yuanrong=infra, registry=registry,
        agent_manager=app.instances._agent_manager, protect=app.instances._instance_lifecycle.protect)
    assert count == 0 and infra.delete_calls == [] and registry.unregistered == []

@pytest.mark.asyncio
async def test_late_manager_delete_cannot_remove_new_instance(config):
    from gateway.extensions.agentos.agentos_router.models import AgentInfo, AgentStatus
    from gateway.extensions.agentos.agentos_router.agent_manager import AgentManager
    manager = AgentManager()
    async def created(info):
        info.sandbox_id = "new-instance"; info.status = AgentStatus.READY
        return info
    await manager.get_or_create_agent("account", "jiuwenswarm", creator=created)
    await manager.delete_agent("account", "jiuwenswarm", expected_instance_id="old-instance")
    assert (await manager.get_agent("account", "jiuwenswarm")).info.sandbox_id == "new-instance"

@pytest.mark.asyncio
async def test_account_outage_is_not_reported_as_logout_and_logout_is_idempotent(config):
    from gateway.auth.remote_accounts import AccountAuthorityUnavailable
    accounts, service_ = service(config, Infrastructure())
    plugin = CloudWorkspacePlugin(config); plugin.accounts = accounts; plugin.environments = service_
    plugin.authenticator = AccountAuthenticator(accounts)
    registry = ExtensionRegistry(None, {}, None); registry.register_application_plugin(plugin)
    app = FastAPI(); mount_application_plugin_http_routes(app, registry)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=config.public_origin) as client:
        prefix = config.api_prefix
        for _ in range(2):
            response = await client.post(prefix + "/logout", json={}, headers={"Origin": config.public_origin})
            assert response.status_code == 200 and response.json()["authenticated"] is False
        class Down:
            def session(self, token): raise AccountAuthorityUnavailable("offline")
        plugin.authenticator = AccountAuthenticator(Down())
        response = await client.get(prefix + "/status")
        assert response.status_code == 503 and response.json()["code"] == "AUTHORITY_UNAVAILABLE"
