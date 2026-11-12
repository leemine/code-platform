"""Original cloud role, signed WS, Router and stores with controlled infrastructure."""
import asyncio
import json
import os
import socket
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import uvicorn
from websockets.legacy.server import serve

from gateway.auth.account_authenticator import AccountAuthenticator, current_account
from gateway.auth.request_scope import current_scope
from gateway.common.security.service_auth import ServiceAuthenticator, check_service_handshake
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.data_sync.extension import DataSyncPlugin
from gateway.extensions.sdk.application_plugin import ApplicationPluginServices
from gateway.routing.agent_client import WebSocketAgentServerClient
from gateway.channel_manager.base import RobotMessageRouter
from gateway.channel_manager.web.web_connect import WebChannel, WebChannelConfig
from gateway.channel_manager.web.web_channel_app import build_web_channel_app
from gateway.services.data_sync.cloud_source import CloudSourcePublisher
from gateway.services.data_sync.store import DirectoryStore
from jiuwenswarm.data_sync.contract import CAPABILITIES, SyncError, digest
from jiuwenswarm.server.front.protocol import parse_raw_message
from jiuwenswarm.server.front.router import MethodRouter
from jiuwenswarm.server.lifecycle import Readiness
from jiuwenswarm.server.runtime.session import project_store
from tests.unit_tests.cloud_workspace.test_cloud_workspace import config, service, Infrastructure, registered, isolated_scope


@pytest.fixture
async def cloud_host(config, tmp_path, monkeypatch):
    infra = Infrastructure()
    accounts, app = service(config, infra)
    actor = await registered(app)
    await app.instances.connect("")
    await app.ensure(actor)
    login = accounts.login("test-user", "long-test-password")
    await AccountAuthenticator(accounts).authenticate(AuthContext(headers={"Authorization": "Bearer " + login["token"]}))
    principal = current_account()
    clients, received = [], []
    admission = SimpleNamespace(dispatch=AsyncMock(side_effect=AssertionError("metadata entered execution")))
    router = MethodRouter(Readiness(), admission)
    async def handler(ws):
        await ws.send(json.dumps({"type": "event", "event": "connection.ack", "payload": {"status": "ready", "readiness": "AGENT_READY"}}))
        async for raw in ws:
            try:
                request = parse_raw_message(raw)
                received.append(request)
                await router.dispatch(ws, request, asyncio.Lock())
            except PermissionError:
                await ws.close(code=1008)
    async def handshake(path, headers):
        return check_service_handshake((path, headers))
    server = await serve(handler, "127.0.0.1", 0, process_request=handshake)
    original_ws = app.instances._get_ws_client
    async def bind_role():
        for old in clients:
            await old.disconnect()
        row = app.store.get(actor)
        # Emulate the /data mount with a private test directory on this host.
        path = Path(row["auth_file"])
        value = json.loads(path.read_text())
        value["workspace"] = str(Path(row["workspace"]) / "agent")
        path.write_text(json.dumps(value))
        monkeypatch.setenv("CODE_PLATFORM_ROLE", "account-instance")
        monkeypatch.setenv("JIUWENSWARM_DATA_DIR", row["workspace"])
        monkeypatch.setenv("JIUWENSWARM_INSTANCE_AUTH_FILE", str(path))
        from jiuwenswarm.common import utils
        monkeypatch.setattr(utils, "_workspace_base_dir", Path(row["workspace"]))
        client = WebSocketAgentServerClient()
        policy = app.instances._instance_lifecycle
        client.set_transport_auth(headers=lambda: policy.transport_headers(actor["user_id"]),
                                  sign=lambda wire: policy.sign_request(actor["user_id"], wire))
        await client.connect(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
        clients.append(client)
        monkeypatch.setattr(app.instances, "_get_ws_client", AsyncMock(return_value=client))
        return row
    row = await bind_role()
    project_store.invalidate_cache()
    project = project_store.create_project("Cloud project", str(Path(row["workspace"]) / "empty"), "code")
    registry = Path(row["workspace"]) / "agent/projects.json"
    directory = DirectoryStore(tmp_path / "directory")
    publisher = CloudSourcePublisher(directory, lambda: app.store, app.instances)
    scope = digest(["platform-data-sync-v1", actor["authority"], actor["user_id"]])
    context = SimpleNamespace(app=app, actor=actor, accounts=accounts, principal=principal,
        login=login, infra=infra, directory=directory, publisher=publisher, project=project,
        registry=registry, scope=scope, received=received, bind_role=bind_role, original_ws=original_ws)
    try:
        yield context
    finally:
        for client in clients:
            await client.disconnect()
        server.close()
        await server.wait_closed()
        await app.instances.disconnect()
        project_store.invalidate_cache()


async def publish(host, operation="cloud-1", selected=None):
    return await host.publisher.publish(host.principal, {"operation_id": operation,
        "project_ids": [host.project.project_id] if selected is None else selected})


@pytest.mark.asyncio
async def test_cloud_ui_choices_use_original_ready_role_without_publication(cloud_host):
    h = cloud_host
    created = h.infra.create_calls
    result = await h.publisher.choices(h.principal)
    assert result == {"projects": [{"native_id": h.project.project_id, "name": "Cloud project"}]}
    assert h.directory.catalog(h.scope)["items"] == []
    assert h.infra.create_calls == created and not h.infra.delete_calls


@pytest.mark.asyncio
async def test_signed_cloud_export_receipt_and_withdrawal_leave_original_files(cloud_host):
    h = cloud_host
    before = h.registry.read_bytes()
    created = h.infra.create_calls
    result = await publish(h)
    assert result["source"]["kind"] == "cloud" and result["total"] == 1
    assert result["environment_epoch"] == 1 and result["source"]["generation"] == 1
    assert await publish(h) == result and len(h.received) == 1
    with pytest.raises(SyncError, match="OPERATION_CONFLICT"):
        await publish(h, selected=[])
    assert (await publish(h, "withdraw", []))["total"] == 0
    assert h.registry.read_bytes() == before and not h.registry.parent.parent.joinpath("empty").exists()
    assert h.infra.create_calls == created and not h.infra.delete_calls
    assert h.received[0].user_id == h.actor["user_id"]
    assert "source_token" not in h.received[0].params


@pytest.mark.asyncio
async def test_cloud_rebuild_keeps_source_identity_and_advances_generation(cloud_host, monkeypatch):
    h = cloud_host
    first = await publish(h)
    consumer = h.directory.register(h.scope, "reader", "local", "b" * 64, 1, sorted(CAPABILITIES))
    snapshot = h.directory.snapshot(h.scope, consumer["id"], "b" * 64, 1)
    before = h.registry.read_bytes()
    await h.app.instances.delete_agent(h.actor["user_id"], "jiuwenswarm")
    monkeypatch.setattr(h.app.instances, "_get_ws_client", h.original_ws)
    await h.app.ensure(h.actor)
    await h.bind_role()
    second = await publish(h, "after-rebuild")
    assert second["source"]["id"] == first["source"]["id"]
    assert second["source"]["generation"] == 2 and second["environment_epoch"] == 2
    assert h.registry.read_bytes() == before and h.infra.create_calls == 2
    with pytest.raises(SyncError, match="SYNC_SOURCE_CHANGED"):
        h.directory.changes(h.scope, consumer["id"], "b" * 64, 1, snapshot["completion"])
    h.directory.revoke(h.scope, second["source"]["id"])
    count = len(h.received)
    with pytest.raises(SyncError, match="SOURCE_UNAUTHORIZED"):
        await publish(h, "revoked")
    assert len(h.received) == count


@pytest.mark.asyncio
async def test_cloud_corrupt_inventory_missing_route_and_logout_do_not_withdraw(cloud_host, monkeypatch):
    h = cloud_host
    first = await publish(h)
    h.registry.write_text('{"projects": [')
    with pytest.raises(SyncError, match="SOURCE_UNAVAILABLE"):
        await publish(h, "corrupt")
    assert h.directory.cloud_status(h.scope, h.app.store.get(h.actor)["environment_id"], "corrupt", [h.project.project_id])["revision"] == 1
    monkeypatch.setattr(h.app.instances._agent_manager, "get_agent", AsyncMock(return_value=None))
    created = h.infra.create_calls
    with pytest.raises(SyncError, match="SOURCE_UNAVAILABLE"):
        await publish(h, "offline")
    assert h.infra.create_calls == created and not h.infra.delete_calls
    assert await publish(h) == first  # Lost response recovery needs no live source.
    h.accounts.logout(h.login["token"])
    with pytest.raises(PermissionError):
        await publish(h, "logged-out")


@pytest.mark.asyncio
async def test_cloud_binding_change_while_exporting_fails_before_commit(cloud_host, monkeypatch):
    h = cloud_host
    send = h.app.instances.send_existing_request
    async def changed(*args, **kwargs):
        response = await send(*args, **kwargs)
        row = h.app.store.get(h.actor)
        h.app.store.transition(row, "DELETING", expected="ALLOCATED")
        return response
    monkeypatch.setattr(h.app.instances, "send_existing_request", changed)
    from gateway.services.cloud_environments import EnvironmentUnavailable
    with pytest.raises(EnvironmentUnavailable):
        await publish(h)
    with h.directory._db() as db:
        assert db.execute("SELECT count(*) FROM objects").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_original_plugin_assembly_rejects_cloud_selectors_and_source_claims(cloud_host):
    h = cloud_host
    methods, responses = {}, []
    async def respond(ws, rid, **kwargs):
        responses.append(kwargs)
    channel = SimpleNamespace(register_method=lambda name, method, **kwargs: methods.update({name: method}), send_response=respond)
    plugin = DataSyncPlugin(h.directory, lambda: h.app.store)
    plugin.bind_web_channel(channel, ApplicationPluginServices(agent_client=h.app.instances))
    base = {"operation_id": "plugin", "project_ids": [h.project.project_id]}
    for selector in ("authority", "user_id", "instance_id", "environment_id", "source_token", "root"):
        await methods["data_sync.cloud.publish"](None, "request", {**base, selector: "forged"}, "transport")
        assert responses[-1]["code"] == "INVALID_REQUEST"
    await methods["data_sync.cloud.publish"](None, "request", base, "transport")
    assert responses[-1]["ok"] and responses[-1]["payload"]["total"] == 1
    await methods["data_sync.source.register"](None, "request", {"kind": "cloud", "source_token": "a" * 64,
        "version": 1, "capabilities": sorted(CAPABILITIES)}, "transport")
    assert responses[-1]["code"] == "SOURCE_HOST_ONLY"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["owner", "epoch", "incomplete", "legacy", "revoked"])
async def test_late_or_unattested_export_cannot_replace_the_last_inventory(cloud_host, monkeypatch, failure):
    h = cloud_host
    first = await publish(h)
    send = h.app.instances.send_existing_request
    async def changed(*args, **kwargs):
        response = await send(*args, **kwargs)
        if failure == "owner":
            response.payload["binding"]["owner"]["actor_id"] = "another-account"
        elif failure == "epoch":
            response.payload["binding"]["epoch"] += 1
        elif failure == "incomplete":
            response.payload["complete"] = False
        elif failure == "legacy":
            response.payload.clear()
            response.payload["projects"] = []
        else:
            h.directory.revoke(h.scope, first["source"]["id"])
        return response
    monkeypatch.setattr(h.app.instances, "send_existing_request", changed)
    with pytest.raises(SyncError):
        await publish(h, "bad-export", [])
    with h.directory._db() as db:
        assert db.execute("SELECT count(*) FROM receipts WHERE operation='bad-export'").fetchone()[0] == 0
        if failure != "revoked":
            assert db.execute("SELECT count(*) FROM objects WHERE deleted=0").fetchone()[0] == 1
    assert h.infra.create_calls == 1 and not h.infra.delete_calls


@pytest.mark.asyncio
async def test_actual_data_root_must_match_the_attested_role(cloud_host, monkeypatch, tmp_path):
    h = cloud_host
    from jiuwenswarm.common import utils
    monkeypatch.setattr(utils, "_workspace_base_dir", tmp_path / "unrelated-root")
    with pytest.raises(SyncError, match="SOURCE_UNAVAILABLE"):
        await publish(h)
    with h.directory._db() as db:
        assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_read_existing_route_does_not_reclaim_on_network_failure(cloud_host, monkeypatch):
    h = cloud_host
    monkeypatch.setattr(h.app.instances, "_get_ws_client", AsyncMock(side_effect=ConnectionError("test transport offline")))
    with pytest.raises(SyncError, match="SOURCE_UNAVAILABLE"):
        await publish(h)
    assert h.infra.create_calls == 1 and not h.infra.delete_calls
    assert h.app.store.get(h.actor)["state"] == "ALLOCATED"


@pytest.mark.asyncio
async def test_environment_guard_prevents_epoch_change_during_commit(cloud_host):
    h = cloud_host
    row = h.app.store.get(h.actor)
    started, finished = threading.Event(), threading.Event()
    def transition():
        started.set()
        h.app.store.transition(row, "DELETING", expected="ALLOCATED")
        finished.set()
    with h.app.store.guard_binding(h.actor, row):
        task = asyncio.create_task(asyncio.to_thread(transition))
        await asyncio.to_thread(started.wait, 2)
        assert not await asyncio.to_thread(finished.wait, 0.1)
    await asyncio.wait_for(task, 3)
    assert finished.is_set() and h.app.store.get(h.actor)["state"] == "DELETING"


@pytest.mark.asyncio
async def test_cloud_cli_uses_gateway_and_original_signed_instance_chain(cloud_host, tmp_path):
    h = cloud_host
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    auth = AccountAuthenticator(h.accounts)
    async def authenticate(**values):
        return await auth.authenticate(AuthContext(channel_type="web", headers=dict(values["headers"])))
    channel.set_handshake_auth(authenticate)
    DataSyncPlugin(h.directory, lambda: h.app.store).bind_web_channel(channel, ApplicationPluginServices(agent_client=h.app.instances))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(build_web_channel_app(channel), log_level="error", lifespan="off"))
    running = asyncio.create_task(server.serve(sockets=[sock]))
    child = None
    before = h.registry.read_bytes()
    try:
        async with asyncio.timeout(30):
            while not server.started:
                if running.done():
                    await running
                await asyncio.sleep(0.01)
            env = {**os.environ, "CODE_PLATFORM_SYNC_ACCOUNT_TOKEN": h.login["token"],
                   "CODE_PLATFORM_SYNC_SOURCE_PROOF": "d" * 64, "JIUWENSWARM_DATA_DIR": str(tmp_path / "client-data")}
            env.pop("CODE_PLATFORM_ROLE", None)
            env.pop("JIUWENSWARM_INSTANCE_AUTH_FILE", None)
            child = await asyncio.create_subprocess_exec(sys.executable, "-P", "-m", "jiuwenswarm.data_sync",
                "--url", f"ws://127.0.0.1:{port}/ws", "--installation-id", "cloud-cli-reader",
                "--kind", "cloud", "--project", h.project.project_id, env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await child.communicate()
            assert child.returncode == 0, stderr.decode()
            result = json.loads(stdout.decode().splitlines()[-1])
            assert result["projects"] == 1 and result["status"]["state"] == "current"
            assert h.login["token"].encode() not in stdout + stderr
            with h.directory._db() as db:
                assert db.execute("SELECT count(*) FROM cloud_bindings").fetchone()[0] == 1
            assert h.registry.read_bytes() == before and h.infra.create_calls == 1 and not h.infra.delete_calls
    finally:
        if child is not None and child.returncode is None:
            child.kill()
            await child.wait()
        server.should_exit = True
        await channel.stop()
        await asyncio.wait_for(running, 5)
        sock.close()
