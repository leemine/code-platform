import asyncio
import json
import socket
import subprocess
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
import uvicorn

from gateway.auth.accounts import AccountStore
from gateway.auth.account_authenticator import AccountAuthenticator
from gateway.channel_manager.base import RobotMessageRouter
from gateway.channel_manager.web.web_channel_app import build_web_channel_app
from gateway.channel_manager.web.web_connect import WebChannel, WebChannelConfig
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.cloud_workspace.extension import CloudWorkspacePlugin
from gateway.extensions.data_sync.extension import DataSyncPlugin
from gateway.extensions.data_sync.ui_extension import DirectoryUIPlugin
from gateway.services.cloud_environments import EnvironmentStore
from gateway.services.data_sync.store import DirectoryStore
from gateway.services.data_sync.ui import COOKIE
from jiuwenswarm.data_sync.contract import CAPABILITIES, SyncError, digest, inventory


def test_ui_catalog_is_account_scoped_paginated_and_rejects_mixed_revisions(tmp_path):
    store = DirectoryStore(tmp_path / "directory")
    source = store.register("account-a", "host", "local", "a" * 64, 1, sorted(CAPABILITIES))
    rows = inventory([{"native_id": str(i), "name": f"Project {i}", "work_mode": "code"} for i in range(105)])
    store.publish("account-a", source["id"], "a" * 64, 1, "publish", 0, rows, 105, digest(rows), True)
    first = store.catalog("account-a")
    assert len(first["items"]) == 100 and first["next_offset"] == 100
    assert len(store.catalog("account-a", 100, first["version"])["items"]) == 5
    assert store.catalog("account-b")["items"] == []
    store.revoke("account-a", source["id"])
    with pytest.raises(SyncError, match="SYNC_CATALOG_CHANGED"):
        store.catalog("account-a", 100, first["version"])
    with store._db() as db:
        assert db.execute("SELECT count(*) FROM acks").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0


@pytest_asyncio.fixture
async def ui_hosts(tmp_path, monkeypatch):
    monkeypatch.setenv("JIUWENSWARM_CONFIG_URL", "off")
    from jiuwenswarm.common import utils
    from jiuwenswarm.server.runtime.session import project_store
    monkeypatch.setattr(utils, "_workspace_base_dir", str(tmp_path / "local-data"))
    monkeypatch.setattr(project_store, "get_agent_root_dir", lambda: tmp_path / "local-data/agent")
    project = project_store.create_project("Local UI project", str(tmp_path / "source-files"), "code")
    (tmp_path / "source-files").mkdir()
    (tmp_path / "source-files/keep.txt").write_text("original content")
    accounts = AccountStore(tmp_path / "authority/accounts.db", "ui-test-authority")
    accounts.register("ui-user", "isolated-ui-password")
    accounts.register("other-user", "isolated-ui-password")
    auth = AccountAuthenticator(accounts)
    channel = WebChannel(WebChannelConfig(enabled=True), RobotMessageRouter())
    execution_connections = []
    channel.set_channel_event_reporter(lambda *event: execution_connections.append(event))
    async def authenticate(**values):
        return await auth.authenticate(AuthContext(channel_type="web", headers=dict(values["headers"])))
    channel.set_handshake_auth(authenticate)
    directory = DataSyncPlugin(DirectoryStore(tmp_path / "directory"))
    directory.bind_web_channel(channel, None)
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen(16)
    endpoint = f"https://127.0.0.1:{sock.getsockname()[1]}"
    cert, key = tmp_path / "ca.pem", tmp_path / "tls.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
                    "-out", str(cert), "-days", "1", "-subj", "/CN=127.0.0.1",
                    "-addext", "subjectAltName=IP:127.0.0.1", "-addext", "basicConstraints=critical,CA:TRUE"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    cloud = CloudWorkspacePlugin(SimpleNamespace(public_origin=endpoint, api_prefix="/api/v1/auth/organization",
                                                registration_enabled=False, authority=accounts.authority))
    cloud.accounts, cloud.authenticator = accounts, auth
    cloud.environments = SimpleNamespace(store=EnvironmentStore(tmp_path / "control/environments.db", accounts.authority,
        tmp_path / "workspaces", tmp_path / "role-auth", {}))
    cloud_ui = DirectoryUIPlugin(directory=directory, cloud=lambda: cloud)
    app = build_web_channel_app(channel)
    for plugin in (cloud, cloud_ui):
        for route in plugin.http_routes():
            app.add_api_route(route.path, route.endpoint, methods=list(route.methods))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off", ssl_certfile=str(cert), ssl_keyfile=str(key)))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    local = DirectoryUIPlugin(local_config={"public_origin": "http://127.0.0.1:12345", "cloud_origin": endpoint,
                                           "ca_file": str(cert), "installation_id": "ui-local-installation"})
    from fastapi import FastAPI
    local_app = FastAPI()
    for route in local.http_routes():
        local_app.add_api_route(route.path, route.endpoint, methods=list(route.methods))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done(): await task
                await asyncio.sleep(.01)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=local_app), base_url="http://127.0.0.1:12345",
                                     headers={"X-Jiuwen-Sync": "1", "Origin": "http://127.0.0.1:12345"}) as client:
            yield SimpleNamespace(client=client, local=local, directory=directory, accounts=accounts,
                                  project=project, root=tmp_path, cloud_ui=cloud_ui, endpoint=endpoint, app=app,
                                  execution_connections=execution_connections, cert=cert)
    finally:
        server.should_exit = True
        await channel.stop()
        await asyncio.wait_for(task, 5)
        sock.close(); project_store.invalidate_cache()


@pytest.mark.asyncio
async def test_ui_local_login_publish_refresh_withdraw_and_logout_over_real_tls(ui_hosts):
    host = ui_hosts; client = host.client
    async def post(action, params=None):
        result = await client.post("/api/v1/data-sync/" + action, json=params or {})
        assert result.status_code == 200, result.text
        return result
    assert (await client.get("/api/v1/data-sync/status")).json()["authenticated"] is False
    assert (await client.post("/api/v1/data-sync/choices", json={})).status_code == 401
    login = await post("login", {"username": "ui-user", "password": "isolated-ui-password"})
    assert "httponly" in login.headers["set-cookie"].lower() and "token" not in login.text
    assert (await client.get("/api/v1/data-sync/status")).json()["authenticated"] is True
    original = (host.root / "local-data/agent/projects.json").read_bytes()
    assert (await post("choices")).json()["projects"][0]["native_id"] == host.project.project_id
    await post("publish", {"project_ids": [host.project.project_id]})
    view = (await post("view")).json()
    assert len(view["items"]) == 1 and view["status"]["state"] == "current"
    assert view["items"][0]["project"]["name"] == "Local UI project"
    assert str(host.root) not in json.dumps(view)
    await post("refresh")
    await post("publish", {"project_ids": []})
    assert (await post("view")).json()["items"] == []
    await post("logout")
    assert not client.cookies.get(COOKIE)
    assert (await client.post("/api/v1/data-sync/view", json={})).status_code == 401
    assert (host.root / "local-data/agent/projects.json").read_bytes() == original
    assert (host.root / "source-files/keep.txt").read_text() == "original content"
    assert host.execution_connections == []


@pytest.mark.asyncio
async def test_directory_connection_cannot_execute_or_trigger_execution_lifecycle(ui_hosts):
    import ssl
    from websockets.legacy.client import connect
    host = ui_hosts
    token = host.accounts.login("ui-user", "isolated-ui-password")["token"]
    url = host.endpoint.replace("https://", "wss://") + "/ws"
    context = ssl.create_default_context(cafile=str(host.cert))
    headers = {"Authorization": "Bearer " + token, "X-Jiuwen-Connection-Scope": "data-sync"}
    async with connect(url, ssl=context, extra_headers=headers) as ws:
        for method in ["chat.send", "project.workspace.mkdir", "cloud.environment.ensure"]:
            await ws.send(json.dumps({"type": "req", "id": method, "method": method, "params": {}}))
            async with asyncio.timeout(5):
                while True:
                    value = json.loads(await ws.recv())
                    if value.get("id") == method:
                        assert value["ok"] is False and value["code"] == "FORBIDDEN"
                        break
    assert host.execution_connections == []
    async with connect(url, ssl=context, extra_headers={"Authorization": "Bearer " + token}) as ws:
        await ws.send(json.dumps({"type": "req", "id": "normal", "method": "data_sync.negotiate", "params": {}}))
        async with asyncio.timeout(5):
            while True:
                if json.loads(await ws.recv()).get("id") == "normal":
                    break
    async with asyncio.timeout(5):
        while len(host.execution_connections) < 2:
            await asyncio.sleep(.01)
    assert [event[0] for event in host.execution_connections] == ["connected", "disconnected"]


def test_handshake_cache_separates_execution_and_sync_connections():
    from gateway.extensions.auth.common import _handshake_cache_key
    headers = {"Authorization": "Bearer " + "a" * 64}
    assert _handshake_cache_key("/ws", headers) != _handshake_cache_key(
        "/ws", {**headers, "X-Jiuwen-Connection-Scope": "data-sync"})


@pytest.mark.asyncio
async def test_ui_rejects_cross_origin_host_selectors_and_cross_account_replica(ui_hosts):
    client = ui_hosts.client
    for headers in [{"Origin": "https://attacker.test"}, {"Host": "attacker.test"}, {"X-Jiuwen-Sync": ""}]:
        response = await client.post("/api/v1/data-sync/login", headers=headers,
                                    json={"username": "ui-user", "password": "isolated-ui-password"})
        assert response.status_code == 401
    await client.post("/api/v1/data-sync/login", json={"username": "ui-user", "password": "isolated-ui-password"})
    for selector in ["root", "user_id", "instance_id", "cloud_origin"]:
        response = await client.post("/api/v1/data-sync/publish", json={"project_ids": [], selector: "forged"})
        assert response.status_code == 400
    response = await client.post("/api/v1/data-sync/publish", json={"project_ids": [ui_hosts.project.project_id]})
    assert response.status_code == 200, response.text
    await client.post("/api/v1/data-sync/logout", json={})
    await client.post("/api/v1/data-sync/login", json={"username": "other-user", "password": "isolated-ui-password"})
    view = await client.post("/api/v1/data-sync/view", json={})
    assert view.status_code == 200 and view.json()["items"] == []
    assert (await client.post("/api/v1/data-sync/refresh", json={})).status_code == 200
    assert (await client.post("/api/v1/data-sync/view", json={})).json()["items"] == []


@pytest.mark.asyncio
async def test_cloud_ui_uses_original_account_and_never_requires_an_instance(ui_hosts):
    host = ui_hosts
    session = host.accounts.login("ui-user", "isolated-ui-password")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host.app), base_url=host.endpoint,
        headers={"Authorization": "Bearer " + session["token"], "X-Jiuwen-Sync": "1", "Origin": host.endpoint}) as client:
        response = await client.post("/api/v1/data-sync/view", json={})
        assert response.status_code == 200 and response.json()["items"] == []
        response = await client.post("/api/v1/data-sync/choices", json={})
        assert response.json()["code"] == "SOURCE_ROUTE_UNSUPPORTED"
        host.accounts.logout(session["token"])
        assert (await client.post("/api/v1/data-sync/view", json={})).status_code == 401


@pytest.mark.asyncio
async def test_local_ui_unknown_publish_recovers_original_receipt_and_own_revocation(ui_hosts, monkeypatch):
    host = ui_hosts; client = host.client
    await client.post("/api/v1/data-sync/login", json={"username": "ui-user", "password": "isolated-ui-password"})
    original = host.directory.dispatch
    failed = False
    def lose_reply(scope, action, params):
        nonlocal failed
        value = original(scope, action, params)
        if action == "inventory.publish" and not failed:
            failed = True
            raise ConnectionError("response lost after commit")
        return value
    monkeypatch.setattr(host.directory, "dispatch", lose_reply)
    body = {"project_ids": [host.project.project_id]}
    assert (await client.post("/api/v1/data-sync/publish", json=body)).status_code == 409
    assert (await client.post("/api/v1/data-sync/view", json={})).json()["pending"] is True
    assert (await client.post("/api/v1/data-sync/publish", json=body)).status_code == 200
    view = (await client.post("/api/v1/data-sync/view", json={})).json()
    assert view["sources"][0]["revision"] == 1 and len(view["items"]) == 1 and not view["pending"]
    source = view["sources"][0]["id"]
    assert (await client.post("/api/v1/data-sync/revoke", json={"source_id": source})).status_code == 200
    view = (await client.post("/api/v1/data-sync/view", json={})).json()
    assert view["status"]["state"] == "revoked" and view["items"] == []
    assert (await client.post("/api/v1/data-sync/publish", json=body)).json()["code"] == "SOURCE_UNAUTHORIZED"
    assert (host.root / "source-files/keep.txt").read_text() == "original content"
