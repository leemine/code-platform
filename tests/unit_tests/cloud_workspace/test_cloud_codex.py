import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.common.managed_codex import AUDIENCE
from gateway.common.security.provider_relay_auth import parse_assertion, sign_assertion, verify_assertion
from gateway.common.security.service_auth import ServiceAuthenticator
from gateway.services.cloud_codex_pool import CloudCodexPool
from gateway.services.cloud_environments import EnvironmentStore
from gateway.services.managed_codex_models import ManagedModel


DIRECTORY = "/data/agent/workspace/code/demo"
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
        Path(row["workspace"], "agent", "workspace", "code", "demo").mkdir(parents=True)
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
    for origin in ("http://127.0.0.1/v1", "https://another.example.test/v1", MODEL_URL + "?key=fixture"):
        with pytest.raises(ValueError):
            ManagedModel.parse({**value, "base_url": origin}, {MODEL_URL})


@pytest.mark.asyncio
async def test_codex_allocation_releases_then_reuses_original_volume(account_and_store):
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
    model = ManagedModel("only-model", MODEL_URL, "synthetic-private-model-key")
    try:
        async with pool.hold(account, "web_session", DIRECTORY, model) as first:
            description = requests[0]
            assert hashlib.sha256(first.capability.encode()).hexdigest() == description["env_vars"]["CODEX_CAPABILITY_DIGEST"]
            assert all(value not in repr(description) for value in (first.capability, model.key, account["auth_file"]))
            assert {mount["target"] for mount in description["mounts"]} == {
                DIRECTORY, "/state", "/run/codex", "/opt/yuanrong-python",
            }
            await pool.reclaim_idle()
            assert instances
        await pool.reclaim_idle()
        resources.confirm_deleted.assert_awaited_once()
        assert not instances
        async with pool.hold(account, "web_session", DIRECTORY, model) as second:
            assert requests[0]["workspace"] == requests[1]["workspace"]
            assert requests[0]["name"] != requests[1]["name"]
            assert first.capability != second.capability
    finally:
        await pool.close()
