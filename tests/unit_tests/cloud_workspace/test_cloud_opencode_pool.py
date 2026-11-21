import asyncio
from copy import deepcopy
import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import Mock, call

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from gateway.common.security.opencode_relay_auth import OpenCodeRelayAuth
from gateway.services.cloud_environments import EnvironmentStore, EnvironmentUnavailable
from gateway.services import cloud_opencode_pool
from gateway.services.cloud_opencode_pool import CloudOpencodePool, OpenCodeFault
from gateway.services.cloud_opencode_relay import CloudOpencodeRelay


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

    async def wait_until_running(self, instance_id, *, confirm_unreported_ready=None):
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
async def test_pool_switch_controls_new_bindings_without_disconnecting_existing_workers(sandbox):
    initial, frontend, account, config = sandbox
    pilot = account("existing-account")
    other = account("other-account")
    config.opencode_provider["admit_new_bindings"] = False
    closed = CloudOpencodePool(initial.store, frontend, config)
    assert closed.worker_model_policy(pilot)["account_model_sync"]
    with pytest.raises(PermissionError):
        await closed.sync_models(pilot, "project", PROJECT_DIR, "0" * 64, shared=True)
    assert not frontend.created

    config.opencode_provider["admit_new_bindings"] = True
    admitted = CloudOpencodePool(initial.store, frontend, config)
    async with admitted.hold(pilot, "project", PROJECT_DIR, shared=True) as original:
        admitted.register_session(original, "project", "original-native-id")

    config.opencode_provider["admit_new_bindings"] = False
    closed = CloudOpencodePool(initial.store, frontend, config)

    async def idle(_lease):
        return True

    closed.idle_check = idle
    assert await closed.reclaim_idle() == 1
    with pytest.raises(PermissionError):
        async with closed.hold(other, "project", PROJECT_DIR, shared=True):
            pytest.fail("Closed pool created a new binding")
    async with closed.hold(pilot, "project", PROJECT_DIR, shared=True) as resumed:
        assert resumed.binding_id == original.binding_id
        assert resumed.instance_id != original.instance_id
        assert closed.owns_session(resumed, "project", "original-native-id")
    assert len(frontend.created) == 2
    assert frontend.created[0]["workspace"] == frontend.created[1]["workspace"]


@pytest.mark.asyncio
async def test_allowlist_blocks_new_bindings_and_preserves_an_idle_shared_binding(sandbox):
    initial, frontend, account, config = sandbox
    pilot = account("pilot-account")
    other = account("ordinary-account")
    config.opencode_provider["account_allowlist"] = [pilot["account_id"]]
    pool = CloudOpencodePool(initial.store, frontend, config)

    assert pool.worker_model_policy(other) is None
    with pytest.raises(PermissionError):
        await pool.sync_models(other, "project", PROJECT_DIR, "0" * 64, shared=True)
    with pytest.raises(PermissionError):
        async with pool.hold(other, "project", PROJECT_DIR, shared=True):
            pytest.fail("Unlisted account received a Provider")
    assert not frontend.created and not list(pool.storage.iterdir())

    assert pool.worker_model_policy(pilot)["account_model_sync"]
    async with pool.hold(pilot, "project", PROJECT_DIR, shared=True) as first:
        pool.register_session(first, "project", "original-native-id")

    async def idle(_lease):
        return True

    pool.idle_check = idle
    assert await pool.reclaim_idle() == 1

    config.opencode_provider["account_allowlist"] = []
    closed = CloudOpencodePool(pool.store, frontend, config)
    assert closed.worker_model_policy(pilot)["account_model_sync"]
    assert closed.worker_model_policy(other) is None
    async with closed.hold(pilot, "project", PROJECT_DIR, shared=True) as resumed:
        assert resumed.binding_id == first.binding_id and resumed.instance_id != first.instance_id
        assert closed.owns_session(resumed, "project", "original-native-id")
    assert frontend.created[0]["workspace"] == frontend.created[1]["workspace"]
    with pytest.raises(PermissionError):
        async with closed.hold(pilot, "project", PROJECT_DIR):
            pytest.fail("Previously admitted account received a new project-scoped binding")
    assert len(frontend.created) == 2


@pytest.mark.asyncio
async def test_allowlist_keeps_an_existing_project_scoped_relay_after_restart(sandbox):
    pool, frontend, account, config = sandbox
    owner = account("legacy-account")
    async with pool.hold(owner, "project", PROJECT_DIR) as original:
        pass
    config.opencode_provider["account_allowlist"] = []
    closed = CloudOpencodePool(pool.store, frontend, config)
    assert closed.worker_model_policy(owner)["account_model_sync"]
    async with closed.hold(owner, "project", PROJECT_DIR) as resumed:
        assert resumed.binding_id == original.binding_id
    with pytest.raises(PermissionError):
        async with closed.hold(owner, "project", PROJECT_DIR, shared=True):
            pytest.fail("Existing project admission enabled a new shared binding")
    assert len(frontend.created) == 1


@pytest.mark.asyncio
async def test_signed_worker_cannot_create_a_binding_outside_the_allowlist(sandbox):
    original, frontend, account, config = sandbox
    ordinary = account("ordinary-account")
    Path(ordinary["workspace"], "agent/projects.json").write_text(json.dumps({
        "projects": [{"project_id": "project", "project_dir": PROJECT_DIR}],
    }))
    config.opencode_provider["account_allowlist"] = []
    frontend.frontend_endpoint = "https://yuanrong.test"
    pool = CloudOpencodePool(original.store, frontend, config)
    admission = Mock(wraps=pool._admits_new_binding)
    pool._admits_new_binding = admission
    relay = CloudOpencodeRelay(pool.store, pool)
    app = Starlette(routes=[
        Route("/scoped/{project_id}/{path:path}", relay.handle, methods=["POST"]),
        Route("/shared/{project_id}/{path:path}", relay.handle_shared, methods=["POST"]),
    ])
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://gateway.test",
                                     auth=OpenCodeRelayAuth(ordinary["auth_file"])) as worker:
            for route in ("/scoped/project", "/shared/project"):
                for path, body in (("/session", {}), ("/account-models/sync", {"revision": "0" * 64})):
                    response = await worker.post(route + path, json=body)
                    assert response.status_code == 403 and response.json()["code"] == "OPENCODE_FORBIDDEN"
        assert admission.call_args_list == [call(ordinary["account_id"])] * 4
        with pool.store.connect() as db:
            assert db.execute("SELECT count(*) FROM provider_bindings").fetchone()[0] == 0
        assert not frontend.created and not list(pool.storage.iterdir())
    finally:
        await relay.close()


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
async def test_legacy_frontend_checks_exact_mounts_before_open_code_readiness(sandbox, monkeypatch):
    pool, frontend, account, _ = sandbox
    owner = account("tenant-one")
    async with pool.hold(owner, "project", PROJECT_DIR) as original:
        pass
    instance = frontend.instances[original.instance_id]
    instance.pop("status")
    root = instance["rootfs"]
    instance["host_user"] = root.pop("user")
    home = {"source": root.pop("workspace"), "target": "/home/agentos"}
    root["mounts"] = [home] + [
        {key: value for key, value in mount.items() if key != "readonly" or value}
        for mount in root["mounts"]
    ]
    probes = []

    async def healthy(lease):
        probes.append(lease)
        return True

    async def wait(instance_id, *, confirm_unreported_ready):
        info = await frontend.get_agent_info(instance_id)
        if await confirm_unreported_ready(info):
            return info
        raise TimeoutError("Ready state was not confirmed")

    pool.ready_check = healthy
    monkeypatch.setattr(frontend, "wait_until_running", wait)
    async with pool.hold(owner, "project", PROJECT_DIR) as lease:
        assert lease == original
    assert probes == [original]

    mismatched = deepcopy(instance)
    mismatched["rootfs"]["mounts"][0]["source"] = "/different-workspace"
    frontend.instances[original.instance_id] = mismatched
    with pytest.raises(EnvironmentUnavailable, match="allocation unavailable"):
        async with pool.hold(owner, "project", PROJECT_DIR):
            pytest.fail("An instance with a different workspace must not produce a lease")
    assert probes == [original]
    assert len(frontend.created) == 1


@pytest.mark.asyncio
async def test_running_shared_provider_retries_health_before_dispatch_once_per_generation(sandbox, monkeypatch):
    pool, frontend, account, _ = sandbox
    owner = account("tenant-one")
    other = "/data/agent/workspace/code/other"
    Path(owner["workspace"], "agent/workspace/code/other").mkdir()
    probes = []
    dispatched = []

    async def healthy(lease):
        probes.append(lease.instance_id)
        assert not dispatched or lease.instance_id != dispatched[-1]
        return probes.count(lease.instance_id) == 2

    async def acquire(project, directory):
        async with pool.hold(owner, project, directory, shared=True) as lease:
            dispatched.append(lease.instance_id)

    async def idle(lease):
        return True

    monkeypatch.setattr(cloud_opencode_pool, "READY_RETRY_SECONDS", 0)
    pool.ready_check = healthy
    pool.idle_check = idle
    for generation in (1, 2):
        await asyncio.gather(acquire("one", PROJECT_DIR), acquire("two", other))
        instances = [f"provider-{index}" for index in range(1, generation + 1) for _ in range(2)]
        assert probes == dispatched == instances
        assert len(frontend.created) == generation
        assert await pool.reclaim_idle() == 1


@pytest.mark.asyncio
async def test_running_provider_health_deadline_leaves_allocation_available_for_retry(sandbox, monkeypatch, caplog):
    pool, frontend, account, _ = sandbox
    owner = account("tenant-one")
    probes = []
    ready = False

    async def healthy(lease):
        probes.append(lease.instance_id)
        return ready

    monkeypatch.setattr(cloud_opencode_pool, "READY_RETRY_SECONDS", 0.001)
    pool.ready_timeout = 0.04
    pool.ready_check = healthy
    caplog.set_level("INFO", logger=cloud_opencode_pool.__name__)
    monkeypatch.setattr(cloud_opencode_pool.logger, "handlers", [caplog.handler])
    with pytest.raises(EnvironmentUnavailable, match="allocation unavailable"):
        async with pool.hold(owner, "project", PROJECT_DIR):
            pytest.fail("A failed health check must withhold the lease")
    assert set(probes) == {"provider-1"}
    ready = True
    pool.ready_timeout = 1
    async with pool.hold(owner, "project", PROJECT_DIR) as lease:
        assert lease.instance_id == probes[-1] == "provider-1"
    assert len(frontend.created) == 1
    assert not frontend.deleted
    events = [record.getMessage() for record in caplog.records if record.msg.startswith("opencode_provider_readiness")]
    assert len(events) == 2
    assert "account_id=tenant-one" in events[0] and "generation=1 attempt=initial" in events[0]
    assert "stage=authenticated_health outcome=timeout" in events[0]
    assert "stage=authenticated_health outcome=ready" in events[1]
    assert len({line.split()[1] for line in events}) == 2
    async with pool.hold(owner, "project", PROJECT_DIR):
        pass
    assert len([record for record in caplog.records if record.msg.startswith("opencode_provider_readiness")]) == 2


@pytest.mark.asyncio
async def test_readiness_timeout_identifies_yuanrong_running_stage(sandbox, monkeypatch, caplog):
    pool, frontend, account, _ = sandbox
    owner = account("tenant-one")
    monkeypatch.setattr(cloud_opencode_pool.logger, "handlers", [caplog.handler])

    async def waiting(*args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(frontend, "wait_until_running", waiting)
    pool.ready_timeout = 0.01
    with pytest.raises(EnvironmentUnavailable, match="allocation unavailable"):
        async with pool.hold(owner, "project", PROJECT_DIR):
            pytest.fail("A pending YuanRong instance must withhold the lease")
    assert "stage=yuanrong_running outcome=timeout" in caplog.text


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


@pytest.mark.asyncio
async def test_frontend_absence_does_not_recycle_without_physical_confirmation(sandbox):
    original, frontend, account, config = sandbox
    owner = account("tenant-one")

    class Confirmation:
        def __init__(self):
            self.allowed = False
            self.calls = []

        async def confirm_deleted(self, **claim):
            assert claim["instance_id"] not in frontend.instances
            assert Path(claim["identity"]).is_dir()
            self.calls.append(claim)
            if not self.allowed:
                raise RuntimeError("physical deletion remains unconfirmed")

    resources = Confirmation()
    pool = CloudOpencodePool(original.store, frontend, config, resources=resources)

    async def idle(_lease):
        return True

    pool.idle_check = idle
    async with pool.hold(owner, "project", PROJECT_DIR) as first:
        state = Path(frontend.created[0]["workspace"])
        identity = Path(frontend.created[0]["mounts"][2]["source"])
        marker = state / "native-db"
        marker.write_text("original")
        scope = (state.parent / "scope.json").read_text()
        assert owner["workspace"] in scope and first.binding_id in scope
        assert first.password not in scope

    assert await pool.reclaim_idle() == 0
    assert frontend.deleted == [first.instance_id] and len(frontend.created) == 1
    assert identity.exists()
    key = (owner["account_id"], "project", "opencode")
    assert pool._get(key)["state"] == "DELETING" and pool._get(key)["generation"] == 1

    with pytest.raises(EnvironmentUnavailable, match="physical deletion remains unconfirmed"):
        async with pool.hold(owner, "project", PROJECT_DIR):
            pytest.fail("Frontend absence alone cannot release the physical slot")
    assert len(frontend.created) == 1 and identity.exists()

    resources.allowed = True
    async with pool.hold(owner, "project", PROJECT_DIR) as second:
        assert second.binding_id == first.binding_id and second.instance_id != first.instance_id
        assert not identity.exists() and marker.read_text() == "original"
        assert pool._get(key)["generation"] == 2
    assert resources.calls == [{"workspace": str(state), "identity": str(identity),
                                "image": config.opencode_provider["image"], "user": "agentos",
                                "instance_id": first.instance_id}] * 3


@pytest.mark.asyncio
async def test_missing_frontend_metadata_cannot_trigger_a_later_busy_delete(sandbox):
    original, frontend, account, config = sandbox
    owner = account("tenant-one")

    async def refuse(**_):
        raise RuntimeError("old physical container still running")

    pool = CloudOpencodePool(original.store, frontend, config, resources=SimpleNamespace(confirm_deleted=refuse))
    async with pool.hold(owner, "project", PROJECT_DIR) as lease:
        identity = Path(frontend.created[0]["mounts"][2]["source"])

    hidden = frontend.instances.pop(lease.instance_id)
    assert await pool.reclaim_idle() == 0
    assert not frontend.deleted and identity.is_dir()
    key = (owner["account_id"], "project", "opencode")
    assert pool._get(key)["state"] == "ALLOCATED"

    async def busy(_lease):
        return False

    frontend.instances[lease.instance_id] = hidden
    pool.idle_check = busy
    assert await pool.reclaim_idle() == 0
    assert not frontend.deleted


@pytest.mark.asyncio
async def test_fresh_fault_reclaim_waits_for_grace_and_scoped_physical_proofs(sandbox, monkeypatch):
    original, frontend, account, config = sandbox
    owner = account("tenant-one")
    now = 0
    monkeypatch.setattr(cloud_opencode_pool, "time", SimpleNamespace(time=time.time, monotonic=lambda: now))
    fault, physical_fault, deletion_confirmed = True, False, False
    physical_checks = []

    async def unavailable(_lease):
        return OpenCodeFault.LISTENER_UNAVAILABLE if fault else None

    async def confirm_fault(**claim):
        physical_checks.append(claim)
        return physical_fault

    async def confirm_deleted(**claim):
        assert claim == physical_checks[-1]
        if not deletion_confirmed:
            raise RuntimeError("physical deletion not confirmed")

    pool = CloudOpencodePool(original.store, frontend, config, resources=SimpleNamespace(
        confirm_opencode_unavailable=confirm_fault, confirm_deleted=confirm_deleted,
    ))
    pool.idle_seconds = 300
    pool.fault_check = unavailable
    key = (owner["account_id"], "project", "opencode")
    async with pool.hold(owner, "project", PROJECT_DIR) as first:
        state = Path(frontend.created[0]["workspace"])
        marker = state / "native-session-id"
        marker.write_text("original")
        assert await pool.reclaim_idle() == 0
    assert await pool.reclaim_idle() == 0
    now = 29
    assert await pool.reclaim_idle() == 0
    fault = False
    assert await pool.reclaim_idle() == 0
    now = 30
    fault = True
    assert await pool.reclaim_idle() == 0 and physical_checks == []
    now = 60
    assert await pool.reclaim_idle() == 0 and len(physical_checks) == 1
    assert frontend.deleted == [] and pool._get(key)["state"] == "ALLOCATED"

    now = 61
    physical_fault = True
    assert await pool.reclaim_idle() == 0
    now = 91
    assert await pool.reclaim_idle() == 0 and len(physical_checks) == 2
    assert frontend.deleted == [first.instance_id]
    assert pool._get(key)["state"] == "DELETING" and pool._get(key)["generation"] == 1
    with pytest.raises(EnvironmentUnavailable, match="physical deletion remains unconfirmed"):
        async with pool.hold(owner, "project", PROJECT_DIR):
            pytest.fail("The original physical generation has not been removed")
    assert len(frontend.created) == 1

    deletion_confirmed = True
    assert await pool.reclaim_idle() == 1
    async with pool.hold(owner, "project", PROJECT_DIR) as second:
        assert second.instance_id != first.instance_id and second.binding_id == first.binding_id
    assert pool._get(key)["generation"] == 2
    assert frontend.created[1]["workspace"] == str(state) and marker.read_text() == "original"


@pytest.mark.asyncio
async def test_stall_grace_requires_repeated_scoped_http_timeouts(sandbox, monkeypatch):
    original, frontend, account, config = sandbox
    owner = account("tenant-one")
    now = 0
    local_stall = False
    fault = OpenCodeFault.HEALTH_STALLED
    claims = []
    monkeypatch.setattr(cloud_opencode_pool, "time", SimpleNamespace(time=time.time, monotonic=lambda: now))

    async def fault_check(_lease):
        return fault

    async def confirm_stall(**claim):
        claims.append(claim)
        return local_stall

    async def confirm_deleted(**claim):
        assert claim == claims[-1]
        assert await frontend.instance_absent(claim["instance_id"])

    pool = CloudOpencodePool(original.store, frontend, config, resources=SimpleNamespace(
        confirm_opencode_stalled=confirm_stall, confirm_deleted=confirm_deleted,
    ))
    pool.idle_seconds = 300
    pool.fault_check = fault_check
    async with pool.hold(owner, "project", PROJECT_DIR) as first:
        assert await pool.reclaim_idle() == 0 and not claims

    assert await pool.reclaim_idle() == 0 and len(claims) == 1
    now = 70
    local_stall = True
    assert await pool.reclaim_idle() == 0
    now = 100
    assert await pool.reclaim_idle() == 0
    fault = None
    assert await pool.reclaim_idle() == 0

    now = 130
    fault = OpenCodeFault.HEALTH_STALLED
    assert await pool.reclaim_idle() == 0
    now = 190
    fault = OpenCodeFault.LISTENER_UNAVAILABLE
    assert await pool.reclaim_idle() == 0

    now = 200
    fault = OpenCodeFault.HEALTH_STALLED
    assert await pool.reclaim_idle() == 0
    now = 260
    local_stall = False
    assert await pool.reclaim_idle() == 0

    now = 270
    local_stall = True
    assert await pool.reclaim_idle() == 0
    now = 329.99
    assert await pool.reclaim_idle() == 0 and frontend.deleted == []
    now = 330
    assert await pool.reclaim_idle() == 1
    assert frontend.deleted == [first.instance_id] and all(claim == claims[0] for claim in claims)


@pytest.mark.asyncio
async def test_shared_binding_checks_every_project_and_retains_session_ownership_on_recycle(sandbox):
    pool, frontend, account, _ = sandbox
    first, second = account("first"), account("second")
    other_dir = "/data/agent/workspace/code/other"
    Path(first["workspace"], "agent/workspace/code/other").mkdir()

    async def acquire(owner, project, directory, *, shared=True):
        async with pool.hold(owner, project, directory, shared=shared) as lease:
            return lease

    a, b = await asyncio.gather(
        acquire(first, "project", PROJECT_DIR), acquire(first, "other", other_dir),
    )
    assert len(frontend.created) == 1
    assert a.instance_id == b.instance_id and a.binding_id == b.binding_id
    assert (a.directory, b.directory) == (PROJECT_DIR, other_dir)
    assert frontend.created[0]["mounts"][0] == {
        "source": str(Path(first["workspace"], "agent/workspace")),
        "target": "/data/agent/workspace", "readonly": False,
    }
    legacy = await acquire(first, "project", PROJECT_DIR, shared=False)
    unrelated = await acquire(second, "project", PROJECT_DIR)
    assert len({a.binding_id, legacy.binding_id, unrelated.binding_id}) == 3

    pool.register_session(a, "project", "ses_a")
    pool.register_session(b, "other", "ses_b")
    with pytest.raises(EnvironmentUnavailable, match="already registered"):
        pool.register_session(a, "project", "ses_b")
    assert not pool.owns_session(a, "other", "ses_a")
    assert not pool.owns_session(unrelated, "project", "ses_a")
    pool.idle_seconds = 300
    with pool.store.connect() as db:
        db.execute("UPDATE provider_bindings SET used_at=0 WHERE binding_id=?", (a.binding_id,))
    busy = other_dir

    async def idle(lease):
        return lease.directory != busy

    pool.idle_check = idle
    assert await pool.reclaim_idle() == 0
    busy = None
    assert await pool.reclaim_idle() == 1
    assert frontend.deleted == [a.instance_id]
    restored = await acquire(first, "project", PROJECT_DIR)
    assert restored.binding_id == a.binding_id and restored.instance_id != a.instance_id
    assert pool.owns_session(restored, "project", "ses_a")
    assert not pool.owns_session(restored, "project", "ses_b")
    assert frontend.created[-1]["workspace"] == frontend.created[0]["workspace"]


@pytest.mark.asyncio
async def test_worker_and_provider_share_first_snapshot_across_gateway_restart(sandbox):
    import json

    pool, frontend, account, config = sandbox
    owner = account("old")
    other = account("new")
    model_file = Path(config.opencode_provider["model_config"])

    def restart(model):
        model_file.write_text(json.dumps({"model": f"test/{model}", "provider": {
            "test": {"models": {model: {}}}
        }}))
        return CloudOpencodePool(pool.store, frontend, config)

    old = restart("a")
    assert old.worker_model_policy(owner)["default"] == "test/a"
    assert not frontend.created
    with pool.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM provider_bindings").fetchone()[0] == 0
    new = restart("b")
    assert new.worker_model_policy(owner)["default"] == "test/a"
    assert new.worker_model_policy(other)["default"] == "test/b"
    async with new.hold(owner, "project", PROJECT_DIR, shared=True):
        mounted = Path(frontend.created[0]["mounts"][-1]["source"]) / "opencode.json"
        data = json.loads(mounted.read_bytes())
        assert data["model"] == "test/a"
    data["$schema"] = "https://opencode.ai/config.json"
    mounted.write_text(json.dumps(data))
    assert new.worker_model_policy(owner)["default"] == "test/a"
    data["provider"]["test"]["options"] = {"baseURL": "https://changed.invalid"}
    mounted.write_text(json.dumps(data))
    assert new.worker_model_policy(owner)["error"] == "opencode_model_snapshot_stale"
    del data["provider"]["test"]["options"]
    data["permission"]["*"] = "deny"
    mounted.write_text(json.dumps(data))
    assert new.worker_model_policy(owner)["models"] == {}
    with pytest.raises(ValueError, match="opencode_approval_policy_conflict"):
        async with new.hold(owner, "project", PROJECT_DIR, shared=True):
            pytest.fail("Conflicting active configuration must block dispatch")
    assert new.worker_model_policy(other)["default"] == "test/b"


@pytest.mark.asyncio
async def test_account_models_refresh_only_an_idle_owned_generation(sandbox):
    from gateway.common.opencode_model_policy import account_models_revision
    from gateway.services.cloud_opencode_pool import OpenCodeConfigurationError

    pool, frontend, account, _ = sandbox
    owner, other = account("owner"), account("other")
    models = {"swarm-" + "a" * 24: {
        "npm": "@ai-sdk/openai-compatible", "name": "Swarm configured model",
        "options": {"baseURL": "https://example.invalid", "apiKey": "fixture"},
        "models": {"a": {"name": "a"}},
    }}
    empty, first = account_models_revision({}), account_models_revision(models)

    async def sync(actor, revision, **changes):
        return await pool.sync_models(actor, "project", PROJECT_DIR, revision, shared=True, **changes)

    assert await sync(owner, first) == empty
    assert await sync(owner, first, models=models, previous=empty) == first
    assert await sync(other, first) == empty
    assert not frontend.created
    async with pool.hold(owner, "project", PROJECT_DIR, shared=True) as original:
        assert await sync(owner, first) == first
        with pytest.raises(OpenCodeConfigurationError, match="busy"):
            await sync(owner, empty, models={}, previous=first)
    with pytest.raises(OpenCodeConfigurationError, match="changed"):
        await sync(owner, empty, models={}, previous="obsolete")
    assert not frontend.deleted

    async def idle(_lease):
        return True

    pool.idle_check = idle
    assert await sync(owner, empty, models={}, previous=first) == empty
    async with pool.hold(owner, "project", PROJECT_DIR, shared=True) as after:
        assert after.binding_id == original.binding_id and after.instance_id != original.instance_id
    assert frontend.deleted == [original.instance_id]
    assert frontend.created[0]["workspace"] == frontend.created[1]["workspace"]
