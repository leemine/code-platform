import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from gateway.services.cloud_environments import EnvironmentStore, EnvironmentUnavailable
from gateway.services.cloud_opencode_pool import CloudOpencodePool


PROJECT_DIR = "/data/agent/workspace/code/sample"


class Frontend:
    def __init__(self):
        self.instances = {}
        self.created = []
        self.deleted = []
        self.lose_response = False
        self.visible = True
        self.pending_delete = False

    async def create_sandbox(self, **request):
        self.created.append(request)
        await asyncio.sleep(0)
        instance_id = f"provider-{len(self.created)}"
        self.instances[instance_id] = {
            "instance_id": instance_id,
            "name": request["name"],
            "status": "running",
            "rootfs": {**request["runtime_spec"]["rootfs"], "workspace": request["workspace"],
                       "mounts": request["mounts"]},
        }
        if self.lose_response:
            raise TimeoutError("uncertain creation response")
        return SimpleNamespace(sandbox_id=instance_id)

    async def list_agent_instances(self):
        return list(self.instances.values()) if self.visible else []

    async def get_agent_info(self, instance_id):
        return self.instances[instance_id]

    async def wait_until_running(self, instance_id):
        return await self.get_agent_info(instance_id)

    async def delete_sandbox(self, instance_id):
        self.deleted.append(instance_id)
        if not self.pending_delete:
            del self.instances[instance_id]

    async def instance_absent(self, instance_id):
        return instance_id not in self.instances


@pytest.fixture
def sandbox(tmp_path):
    model = tmp_path / "openai.json"
    model.write_text('{"provider":{}}')
    config = SimpleNamespace(
        opencode_provider={"image": "sha256:" + "b" * 64, "model_config": str(model), "idle_seconds": 0},
        state_root=tmp_path / "control", runtime="python3.11", namespace="isolated", ready_timeout=1,
    )
    store = EnvironmentStore(config.state_root / "environments.db", "test", tmp_path / "accounts",
                             config.state_root / "worker-auth", {"runtime_user": "agentos"})
    store.acquire_writer()

    def account(name):
        intent = store.registration(name, "isolated-test-password")
        row = store.bind_registration(intent, {"authority": "test", "user_id": name, "username": name})
        row = store.prepare(row["account_id"])
        store.transition(row, "ALLOCATED", instance_id=f"worker-{name}", expected="NEW")
        row = store.by_user(name)
        Path(row["workspace"], "agent", "workspace", "code", "sample").mkdir(parents=True)
        return row

    try:
        frontend = Frontend()
        yield CloudOpencodePool(store, frontend, config), frontend, account, config
    finally:
        store.close()


@pytest.mark.asyncio
async def test_concurrent_project_requests_and_gateway_restart_reuse_one_instance(sandbox):
    pool, frontend, account, config = sandbox
    owner = account("tenant-one")

    async def acquire(current_pool):
        async with current_pool.hold(owner, "project", PROJECT_DIR) as lease:
            return lease

    leases = await asyncio.gather(*(acquire(pool) for _ in range(12)))
    assert len(set(leases)) == 1
    original = leases[0]
    assert len(frontend.created) == 1
    restarted = CloudOpencodePool(pool.store, frontend, config)
    assert await acquire(restarted) == original
    assert len(frontend.created) == 1
    mount = frontend.created[0]["mounts"]
    assert mount[0] == {"source": str(Path(owner["workspace"], *Path(PROJECT_DIR).parts[2:])),
                        "target": PROJECT_DIR, "readonly": False}
    assert mount[1]["target"] == "/state"
    assert mount[2]["target"] == "/run/opencode" and mount[2]["readonly"]
    assert original.password not in str(frontend.created[0])
    assert original.password not in repr(original)


@pytest.mark.asyncio
async def test_account_scope_isolated_and_stale_worker_or_symlink_denied(sandbox):
    pool, frontend, account, _ = sandbox
    first = account("tenant-one")
    second = account("tenant-two")
    async with (pool.hold(first, "project", PROJECT_DIR) as left,
                pool.hold(second, "project", PROJECT_DIR) as right):
        assert left.instance_id != right.instance_id
        assert left.binding_id != right.binding_id
        assert left.password != right.password
    assert frontend.created[0]["workspace"] != frontend.created[1]["workspace"]
    assert frontend.created[0]["mounts"][0]["source"] != frontend.created[1]["mounts"][0]["source"]

    Path(first["workspace"], "agent/workspace/code/other").mkdir()
    other_directory = "/data/agent/workspace/code/other"
    async with pool.hold(first, "other-project", other_directory) as other:
        assert other.instance_id not in {left.instance_id, right.instance_id}
        assert other.binding_id != left.binding_id
    alias = Path(first["workspace"]) / "agent/workspace/code/alias"
    alias.symlink_to(Path(second["workspace"]) / "agent/workspace/code/sample")
    without_owner = {**first, "workspace": second["workspace"]}
    for owner, directory in ((without_owner, PROJECT_DIR), ({**first, "epoch": 0}, PROJECT_DIR),
                             (first, "/data/agent/workspace/code/alias"), (first, "/data/config"),
                             (first, other_directory)):
        with pytest.raises(PermissionError):
            async with pool.hold(owner, "project", directory):
                pytest.fail("Unauthorized lease")
    assert len(frontend.created) == 3


@pytest.mark.asyncio
async def test_creation_lost_response_never_reposts_and_can_reconcile(sandbox):
    pool, frontend, account, config = sandbox
    owner = account("tenant-one")
    frontend.lose_response = True
    with pytest.raises(EnvironmentUnavailable, match="allocation unavailable"):
        async with pool.hold(owner, "project", PROJECT_DIR):
            pytest.fail("Lost response must not produce a lease")
    frontend.visible = False
    restarted = CloudOpencodePool(pool.store, frontend, config)
    with pytest.raises(EnvironmentUnavailable, match="outcome remains unknown"):
        async with restarted.hold(owner, "project", PROJECT_DIR):
            pytest.fail("An empty list is not proof of allocation absence")
    assert len(frontend.created) == 1
    frontend.visible = True
    async with restarted.hold(owner, "project", PROJECT_DIR) as lease:
        assert lease.instance_id == "provider-1"
    assert len(frontend.created) == 1


@pytest.mark.asyncio
async def test_reclaim_waits_for_idle_and_absence_and_retains_native_state(sandbox):
    pool, frontend, account, _ = sandbox
    owner = account("tenant-one")
    native_idle = False

    async def idle_check(lease):
        assert lease.instance_id == "provider-1"
        return native_idle

    pool.idle_check = idle_check
    async with pool.hold(owner, "project", PROJECT_DIR) as first:
        state = Path(frontend.created[0]["workspace"])
        marker = state / "native-session"
        marker.write_text("original-native-id")
        assert await pool.reclaim_idle() == 0
    assert await pool.reclaim_idle() == 0
    assert not frontend.deleted

    native_idle = True
    frontend.pending_delete = True
    assert await pool.reclaim_idle() == 0
    with pytest.raises(EnvironmentUnavailable, match="deletion is pending"):
        async with pool.hold(owner, "project", PROJECT_DIR):
            pytest.fail("Provider is still present")
    assert len(frontend.created) == 1
    frontend.pending_delete = False
    assert await pool.reclaim_idle() == 1
    assert frontend.deleted == [first.instance_id, first.instance_id]
    assert first.instance_id not in frontend.instances
    async with pool.hold(owner, "project", PROJECT_DIR) as second:
        assert second.instance_id != first.instance_id
        assert second.binding_id == first.binding_id
        assert second.password == first.password
        assert frontend.created[1]["workspace"] == str(state)
        assert frontend.created[1]["mounts"][2] != frontend.created[0]["mounts"][2]
        assert marker.read_text() == "original-native-id"


@pytest.mark.asyncio
async def test_mismatched_instance_rejected_before_use_or_reclaim(sandbox):
    pool, frontend, account, _ = sandbox
    owner = account("tenant-one")
    async with pool.hold(owner, "project", PROJECT_DIR) as lease:
        frontend.instances[lease.instance_id]["rootfs"]["mounts"] = []
    with pytest.raises(EnvironmentUnavailable, match="ownership could not be verified"):
        async with pool.hold(owner, "project", PROJECT_DIR):
            pytest.fail("Instance mounts differ")
    assert await pool.reclaim_idle() == 0
    assert not frontend.deleted
    assert len(frontend.created) == 1
