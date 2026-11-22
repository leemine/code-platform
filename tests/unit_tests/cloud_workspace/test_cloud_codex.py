import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.common.managed_codex import AUDIENCE
from gateway.common.security.provider_relay_auth import parse_assertion, sign_assertion, verify_assertion
from gateway.common.security.service_auth import ServiceAuthenticator
from gateway.services.cloud_codex_pool import CloudCodexPool, PROJECT_ROOT
from gateway.services.cloud_provider_allocation import RuntimeDeviceNameConflict
from gateway.services.cloud_environments import EnvironmentStore
from gateway.services.managed_codex_models import CATALOG_FILENAME, ManagedModel


DIRECTORY = "/data/agent/workspace/code/demo"
OTHER_DIRECTORY = "/data/agent/workspace/code/another"
MODEL_URL = "https://models.example.test/v1"


@pytest.fixture
def account_and_store(tmp_path):
    state = tmp_path / "gateway"
    store = EnvironmentStore(state / "environments.db", "isolated", tmp_path / "accounts",
                             state / "worker-auth", {"runtime_user": "agentos"})
    store.acquire_writer()
    try:
        intent = store.registration("canary", "isolated-password")
        row = store.bind_registration(intent, {"authority": "isolated", "user_id": "canary", "username": "canary"})
        row = store.prepare(row["account_id"])
        store.transition(row, "ALLOCATED", instance_id="worker-canary", expected="NEW")
        row = store.by_user("canary")
        for directory in ("demo", "another"):
            Path(row["workspace"], "agent", "workspace", "code", directory).mkdir(parents=True)
        yield row, store, state
    finally:
        store.close()


def test_worker_assertion_has_distinct_codex_audience_and_route(account_and_store):
    account, _, _ = account_and_store
    path = "/api/v1/auth/organization/provider/managed/codex"
    credential = ServiceAuthenticator(account["auth_file"])
    signed = sign_assertion(credential, audience=AUDIENCE, method="GET", path=path, directory=DIRECTORY, body=b"")
    claims, signature = parse_assertion(signed, audience=AUDIENCE)
    verify_assertion(account["auth_file"], claims, signature, method="GET", path=path, directory=DIRECTORY, body=b"")
    with pytest.raises(PermissionError):
        parse_assertion(signed, audience="jiuwenswarm-managed-opencode")
    with pytest.raises(PermissionError):
        verify_assertion(account["auth_file"], claims, signature, method="GET", path=path,
                         directory=DIRECTORY + "-another", body=b"")


def test_models_cannot_change_the_network_origin_or_expose_credentials():
    value = {"model": "isolated", "base_url": MODEL_URL, "api_key": "fixture-key"}
    model = ManagedModel.parse(value, {MODEL_URL})
    assert "fixture-key" not in repr(model)
    configured = ManagedModel.parse({**value, "context_window": 1048576}, {MODEL_URL})
    assert configured.context_window == 1048576
    assert configured.revision == model.revision
    for origin in ("http://127.0.0.1/v1", "https://another.example.test/v1", MODEL_URL + "?key=fixture"):
        with pytest.raises(ValueError):
            ManagedModel.parse({**value, "base_url": origin}, {MODEL_URL})


@pytest.mark.parametrize("value", [True, 0, -1, "1048576", 1048576.0, None, 2**63])
def test_managed_codex_rejects_invalid_model_catalog_context(value):
    with pytest.raises(ValueError, match="context window"):
        ManagedModel.parse({"model": "isolated", "base_url": MODEL_URL, "api_key": "fixture-key",
                            "context_window": value}, {MODEL_URL})


@pytest.mark.asyncio
@pytest.mark.parametrize("context_window", [None, 1048576])
@pytest.mark.parametrize("named", [False, True])
async def test_codex_allocation_releases_then_reuses_original_volume(account_and_store, context_window, named):
    account, store, state = account_and_store
    config = SimpleNamespace(codex_provider={"image": "sha256:" + "a" * 64, "account_allowlist": ["canary"],
                             "shared_runtime": "/opt/runtime/" + "b" * 64, "idle_seconds": 0},
                             state_root=state, runtime="python3.11", namespace="isolated", ready_timeout=2)
    requests, instances = [], {}

    async def create(**request):
        requests.append(request)
        identifier = f"runtime-{len(requests)}"
        instances[identifier] = {"name": request["name"], "rootfs": {
            **request["runtime_spec"]["rootfs"], "workspace": request["workspace"], "mounts": request["mounts"],
        }}
        return SimpleNamespace(sandbox_id=identifier)

    async def delete(identifier):
        del instances[identifier]

    yuanrong = SimpleNamespace(create_sandbox=create, delete_sandbox=delete,
                               wait_until_running=AsyncMock(side_effect=lambda identifier, **_: instances[identifier]),
                               get_agent_info=AsyncMock(side_effect=lambda identifier: instances[identifier]),
                               instance_absent=AsyncMock(side_effect=lambda identifier: identifier not in instances))
    resources = SimpleNamespace(confirm_deleted=AsyncMock(), confirm_codex_address=AsyncMock(return_value="10.0.0.1"))
    pool = CloudCodexPool(store, yuanrong, config, resources)
    pool.ready_check = pool.idle_check = AsyncMock(return_value=True)
    model = ManagedModel("only-model", MODEL_URL, "synthetic-private-model-key", context_window)
    runtime_id = None
    try:
        if named:
            name, token = "Dev sandbox", "a" * 32
            device = pool.register_device(account, name, token, "account-selected")
            runtime_id = device["runtime_id"]
            assert device["state"] == "not_started" and device["model_id"] is None
            assert pool.register_device(account, name, token, "account-selected") == device
            assert pool.device_model_id(account, runtime_id) == "account-selected"
            with pytest.raises(RuntimeDeviceNameConflict):
                pool.register_device(account, name, token, "different-model")
            with pytest.raises(RuntimeDeviceNameConflict):
                pool.register_device(account, name, "b" * 32)
            with pytest.raises(PermissionError, match="model selection differs"):
                await pool.prepare_device(account, runtime_id, model, "account-default")
            with pytest.raises(PermissionError):
                async with pool.hold(account, "unprepared", DIRECTORY, model, runtime_id=runtime_id):
                    pytest.fail("An unprepared named device started without its account model")
            assert not requests
            await pool.prepare_device(account, runtime_id, model, "account-selected")
            assert pool.device_runtime(account, runtime_id)["state"] == "ready"
            assert pool.device_runtime(account, runtime_id)["model_id"] == "account-selected"
            with store.connect() as db:
                assert db.execute("SELECT count(*) FROM codex_session_owners").fetchone()[0] == 0
            with pytest.raises(PermissionError, match="model selection differs"):
                await pool.prepare_device(account, runtime_id, model, "changed-default")
        async with pool.hold(account, "web_session", DIRECTORY, model, runtime_id=runtime_id) as first:
            description = requests[0]
            assert hashlib.sha256(first.capability.encode()).hexdigest() == description["env_vars"]["CODEX_CAPABILITY_DIGEST"]
            assert all(value not in repr(description) for value in (first.capability, model.key, account["auth_file"]))
            assert {mount["target"] for mount in description["mounts"]} == {
                str(PROJECT_ROOT), "/state", "/run/codex", "/opt/yuanrong-python",
            }
            identity = next(mount for mount in description["mounts"] if mount["target"] == "/run/codex")
            assert identity["readonly"]
            first_catalog = Path(identity["source"]) / CATALOG_FILENAME
            if context_window is None:
                assert not first_catalog.exists()
            else:
                encoded_catalog = first_catalog.read_bytes()
                assert model.key.encode() not in encoded_catalog and model.endpoint.encode() not in encoded_catalog
                [catalog] = json.loads(encoded_catalog)["models"]
                assert catalog["slug"] == model.name
                assert catalog["context_window"] == catalog["max_context_window"] == context_window
                assert catalog["effective_context_window_percent"] == 95
            async with pool.hold(account, "another_session", OTHER_DIRECTORY, model, runtime_id=runtime_id) as another:
                assert another == first
                assert len(requests) == 1
                await pool.reclaim_idle()
                assert len(instances) == 1
        with pytest.raises(PermissionError, match="another project"):
            async with pool.hold(account, "web_session", OTHER_DIRECTORY, model, runtime_id=runtime_id):
                pytest.fail("changed project acquired a Codex transport")
        changed = ManagedModel(model.name, model.endpoint, model.key, 4096)
        with pytest.raises(PermissionError, match="persistent Worker binding"):
            async with pool.hold(account, "web_session", DIRECTORY, changed, runtime_id=runtime_id):
                pytest.fail("changed context acquired a Codex transport")
        with store.connect() as db:
            keys = db.execute("SELECT account_id,project_id,provider FROM provider_bindings").fetchall()
        scope = f"@device:{account['environment_id']}:{runtime_id}" if named else "@" + account["environment_id"]
        assert [tuple(item) for item in keys] == [("canary", scope, "codex")]
        await pool.reclaim_idle()
        resources.confirm_deleted.assert_awaited_once()
        assert not instances
        if named:
            assert pool.device_runtime(account, runtime_id)["state"] == "idle"
            assert pool.account_devices(account)[0]["runtime_id"] == runtime_id
        assert not first_catalog.exists()
        await pool.close()
        pool = CloudCodexPool(store, yuanrong, config, resources)
        pool.ready_check = pool.idle_check = AsyncMock(return_value=True)
        async with pool.hold(account, "web_session", DIRECTORY, model, runtime_id=runtime_id) as second:
            assert requests[0]["workspace"] == requests[1]["workspace"]
            assert requests[0]["name"] != requests[1]["name"]
            assert first.capability != second.capability
            second_identity = next(mount for mount in requests[1]["mounts"] if mount["target"] == "/run/codex")
            second_catalog = Path(second_identity["source"]) / CATALOG_FILENAME
            if context_window is None:
                assert not second_catalog.exists()
            else:
                assert second_catalog.read_bytes() == encoded_catalog
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_stdio_reconnect_waits_until_same_session_has_released_state(tmp_path, monkeypatch):
    import asyncio
    import importlib.util
    import json
    from unittest.mock import Mock

    path = Path(__file__).resolve().parents[3] / "deploy/cloud-workspace/codex_stdio_bridge.py"
    spec = importlib.util.spec_from_file_location("codex_stdio_bridge", path)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    project_root, state = tmp_path / "work", tmp_path / "state"
    cwd = project_root / "repo"
    cwd.mkdir(parents=True)
    state.mkdir()
    monkeypatch.setattr(app, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(app, "STATE_ROOT", state)
    capability = "fixture"
    bridge = app.StdioBridge(hashlib.sha256(capability.encode()).hexdigest())
    entered, release, second_authorized = (asyncio.Event() for _ in range(3))

    async def first_transport(*args, **kwargs):
        entered.set()
        await release.wait()

    relay_probe = AsyncMock(side_effect=[first_transport, None])

    async def relay(*args, **kwargs):
        if await relay_probe(*args, **kwargs) is first_transport:
            await first_transport()

    def fresh():
        request = {"capability": capability, "op": "stream", "session": "sid", "directory": str(cwd)}
        reader = SimpleNamespace(readline=AsyncMock(return_value=json.dumps(request).encode() + b"\n"))
        writer = SimpleNamespace(close=Mock(), wait_closed=AsyncMock())
        return reader, writer

    authorize = bridge.authorize
    handshakes = []

    def observe_handshake(raw):
        result = authorize(raw)
        handshakes.append(result)
        if len(handshakes) == 2:
            second_authorized.set()
        return result

    monkeypatch.setattr(bridge, "authorize", observe_handshake)
    monkeypatch.setattr(bridge, "relay", relay)
    first = asyncio.create_task(bridge.handle(*fresh()))
    await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(bridge.handle(*fresh()))
    try:
        await asyncio.wait_for(second_authorized.wait(), 1)
        assert relay_probe.await_count == 1
        assert not second.done()
    finally:
        release.set()
        await asyncio.gather(first, second)
    assert relay_probe.await_count == 2
    assert not bridge.active


@pytest.mark.asyncio
async def test_codex_retirement_recovers_after_restart_and_retries_once(account_and_store):
    import asyncio

    from gateway.extensions.yuanrong_frontend_client import YuanrongAgentApiError
    from gateway.services.cloud_provider_allocation import read_binding

    account, store, state = account_and_store
    config = SimpleNamespace(codex_provider={"image": "sha256:" + "a" * 64, "account_allowlist": ["canary"],
                             "shared_runtime": "/opt/runtime/" + "b" * 64, "idle_seconds": 0},
                             state_root=state, runtime="python3.11", namespace="isolated", ready_timeout=2)
    requests, instances = [], {}

    async def create(**request):
        requests.append(request)
        identifier = f"runtime-{len(requests)}"
        instances[identifier] = {"name": request["name"], "rootfs": {
            **request["runtime_spec"]["rootfs"], "workspace": request["workspace"], "mounts": request["mounts"],
        }}
        return SimpleNamespace(sandbox_id=identifier)

    async def wait(identifier, **_):
        if identifier == "runtime-1":
            raise TimeoutError("capacity")
        return instances[identifier]

    yuanrong = SimpleNamespace(create_sandbox=create, wait_until_running=wait,
                               get_agent_info=AsyncMock(side_effect=lambda identifier: instances[identifier]),
                               instance_absent=AsyncMock(return_value=False),
                               retire_undispatched_codex=AsyncMock(side_effect=[
                                   YuanrongAgentApiError("unconfirmed error"), False]))
    resources = SimpleNamespace(confirm_deleted=AsyncMock(), confirm_codex_address=AsyncMock(return_value="10.0.0.1"),
                                fence_undispatched_codex=AsyncMock(return_value=True))
    key = ("canary", "@" + account["environment_id"], "codex")
    model = ManagedModel("only-model", MODEL_URL, "synthetic")
    pool = CloudCodexPool(store, yuanrong, config, resources)
    try:
        with pytest.raises(TimeoutError):
            async with pool.hold(account, "first", DIRECTORY, model):
                pytest.fail("exhausted allocation was admitted")
        pending = read_binding(store, key)
        assert pending["state"] == "RETIRING_UNDISPATCHED"
        await pool.reclaim_idle()
        assert read_binding(store, key) == pending
        assert len(requests) == 1
    finally:
        await pool.close()
    pool = CloudCodexPool(store, yuanrong, config, resources)
    pool.ready_check = AsyncMock(return_value=True)
    try:
        async def retry(session, directory):
            async with pool.hold(account, session, directory, model) as lease:
                return lease

        first, second = await asyncio.gather(retry("first", DIRECTORY), retry("second", OTHER_DIRECTORY))
        updated = read_binding(store, key)
        assert first == second
        assert updated["binding_id"] == pending["binding_id"]
        assert updated["generation"] == pending["generation"] + 1
        assert requests[0]["workspace"] == requests[1]["workspace"]
        assert len(requests) == 2
        assert updated["instance_id"] == "runtime-2"
        resources.confirm_deleted.assert_not_called()
    finally:
        await pool.close()


def test_named_codex_control_reuses_signed_websocket_without_starting_a_thread(account_and_store):
    from urllib.parse import quote

    from fastapi import FastAPI, WebSocket
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from gateway.common.managed_codex import ASSERTION_HEADER, DIRECTORY_HEADER, MODEL_UNAVAILABLE
    from gateway.services.cloud_codex_relay import CloudCodexRelay

    account, store, state = account_and_store
    config = SimpleNamespace(
        codex_provider={"image": "sha256:" + "a" * 64, "account_allowlist": ["canary"],
                        "shared_runtime": "/opt/runtime/" + "b" * 64, "model_endpoints": [MODEL_URL]},
        state_root=state, runtime="python3.11", namespace="isolated", ready_timeout=2,
    )
    pool = CloudCodexPool(store, None, config, None)
    device = pool.register_device(account, "Development", "c" * 32)
    runtime_id = device["runtime_id"]
    pool.prepare_device = AsyncMock()
    relay = CloudCodexRelay(pool)
    route = "/api/v1/auth/organization/provider/managed/codex"
    app = FastAPI()

    @app.websocket(route)
    async def signed_handler(websocket: WebSocket):
        await relay.handle(websocket)

    path = route
    credential = ServiceAuthenticator(account["auth_file"])

    def headers(directory):
        signature = sign_assertion(credential, audience=AUDIENCE, method="GET", path=path, directory=directory, body=b"")
        return {ASSERTION_HEADER: signature, DIRECTORY_HEADER: quote(directory, safe="/")}

    request = {"op": "prepare", "runtime_id": runtime_id, "model_id": "account-default",
               "model": "fixture", "base_url": MODEL_URL, "api_key": "fixture-key"}
    with TestClient(app) as client:
        with client.websocket_connect(path, headers=headers(str(PROJECT_ROOT))) as ws:
            ws.send_json({**request, "base_url": "https://unadmitted.example.test/v1"})
            assert ws.receive_json() == {"code": MODEL_UNAVAILABLE}
        pool.prepare_device.assert_not_awaited()
        with client.websocket_connect(path, headers=headers(str(PROJECT_ROOT))) as ws:
            ws.send_json(request)
            assert ws.receive_json() == {"ready": True}
        pool.prepare_device.assert_awaited_once()
        prepared_account, prepared_id, model, model_id = pool.prepare_device.await_args.args
        assert prepared_account["account_id"] == account["account_id"]
        assert (prepared_id, model.name, model_id) == (runtime_id, "fixture", "account-default")
        with client.websocket_connect(path, headers=headers(str(PROJECT_ROOT))) as ws:
            ws.send_json({"op": "check", "runtime_id": runtime_id})
            with pytest.raises(WebSocketDisconnect) as failure:
                ws.receive_json()
            assert failure.value.code == 1008
        Path(account["workspace"], "agent", "projects.json").write_text(json.dumps({
            "projects": [{"project_id": "demo", "project_dir": DIRECTORY}],
        }))
        with client.websocket_connect(path, headers=headers(DIRECTORY)) as ws:
            ws.send_json({"op": "check", "runtime_id": runtime_id})
            assert ws.receive_json() == {"runtime_id": runtime_id, "model_id": None}
        with client.websocket_connect(path, headers=headers(DIRECTORY)) as ws:
            ws.send_json({"op": "check", "runtime_id": "f" * 32})
            with pytest.raises(WebSocketDisconnect) as failure:
                ws.receive_json()
            assert failure.value.code == 1008
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM codex_session_owners").fetchone()[0] == 0



def test_codex_device_model_catalog_filters_the_account_models(monkeypatch):
    from jiuwenswarm.common.model_catalog import ModelCatalog
    from jiuwenswarm.server.runtime.agent_adapter.providers import codex_device

    def entry(model_id, provider, endpoint, is_default=False):
        return {"model_id": model_id, "is_default": is_default,
                "model_client_config": {"model_name": model_id, "client_provider": provider,
                                        "api_base": endpoint, "api_key": "fixture-key"}}

    catalog = ModelCatalog({"models": {"defaults": [
        entry("account-default", "openai", MODEL_URL, True),
        entry("account-alternate", "openai", MODEL_URL),
        entry("unadmitted-endpoint", "openai", "https://unadmitted.example.test"),
        entry("other-protocol", "anthropic", MODEL_URL),
    ]}})
    monkeypatch.setattr("jiuwenswarm.common.model_catalog.ModelCatalog", lambda: catalog)
    monkeypatch.setattr(codex_device, "configured_service_auth", lambda: SimpleNamespace(
        public_binding=lambda: {"owner": {"actor_id": "owner"}},
    ))
    monkeypatch.setenv(codex_device.RELAY_ENV, "wss://relay.example.test")
    params = {"provider_id": "codex-direct", "allowed_model_endpoints": [MODEL_URL], "model_id": None}
    request = SimpleNamespace(params=params, user_id="owner", is_stream=False, session_id=None)
    assert codex_device.account_device_models(request) == {
        "model_ids": ["account-default", "account-alternate"], "default_model_id": "account-default",
    }
    params["model_id"] = "unadmitted-endpoint"
    assert codex_device.account_device_models(request) == {"model_ids": [], "default_model_id": None}
    params["model_id"] = "account-alternate"
    assert codex_device.account_device_models(request) == {"model_ids": ["account-alternate"], "default_model_id": None}
