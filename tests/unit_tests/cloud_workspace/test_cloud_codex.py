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
async def test_codex_allocation_releases_then_reuses_original_volume(account_and_store, context_window):
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
    try:
        async with pool.hold(account, "web_session", DIRECTORY, model) as first:
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
            async with pool.hold(account, "another_session", OTHER_DIRECTORY, model) as another:
                assert another == first
                assert len(requests) == 1
                await pool.reclaim_idle()
                assert len(instances) == 1
        with pytest.raises(PermissionError, match="another project"):
            async with pool.hold(account, "web_session", OTHER_DIRECTORY, model):
                pytest.fail("changed project acquired a Codex transport")
        changed = ManagedModel(model.name, model.endpoint, model.key, 4096)
        with pytest.raises(PermissionError, match="persistent Worker binding"):
            async with pool.hold(account, "web_session", DIRECTORY, changed):
                pytest.fail("changed context acquired a Codex transport")
        with store.connect() as db:
            keys = db.execute("SELECT account_id,project_id,provider FROM provider_bindings").fetchall()
        assert [tuple(item) for item in keys] == [("canary", "@" + account["environment_id"], "codex")]
        await pool.reclaim_idle()
        resources.confirm_deleted.assert_awaited_once()
        assert not instances
        assert not first_catalog.exists()
        await pool.close()
        pool = CloudCodexPool(store, yuanrong, config, resources)
        pool.ready_check = pool.idle_check = AsyncMock(return_value=True)
        async with pool.hold(account, "web_session", DIRECTORY, model) as second:
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
