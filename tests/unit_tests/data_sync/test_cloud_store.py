import pytest

from gateway.services.data_sync.store import DirectoryStore
from jiuwenswarm.data_sync.connector import DirectoryConnector, DirectoryReplica
from jiuwenswarm.data_sync.contract import CAPABILITIES, SyncError, negotiate


PROJECT = {"native_id": "original", "name": "Cloud project", "work_mode": "code"}


def test_cloud_source_created_after_local_snapshot_keeps_cloud_identity_on_delta(tmp_path):
    store = DirectoryStore(tmp_path / "broker")
    consumer = store.register("account", "local", "local", "a" * 64, 1, sorted(CAPABILITIES))
    replica = DirectoryReplica(tmp_path / "replica", "reader")
    first = store.snapshot("account", consumer["id"], "a" * 64, 1)
    replica.accept_snapshot(first)
    cloud = publish(store)
    delta = store.changes("account", consumer["id"], "a" * 64, 1, first["completion"])
    replica.accept_changes(delta)
    item = replica.projects()[0]
    source = next(row for row in replica.get("coverage")["coverage"] if row["id"] == item["source_id"])
    assert source == cloud["source"] and source["kind"] == "cloud" and source["revision"] == 1
    publish(store, operation="unchanged", revision=1)
    delta = store.changes("account", consumer["id"], "a" * 64, 1, delta["completion"])
    assert delta["items"] == []
    replica.accept_changes(delta)
    assert next(row for row in replica.get("coverage")["coverage"] if row["id"] == source["id"])["revision"] == 2


def publish(store, epoch=1, workspace="workspace-hash", operation="first", revision=0):
    return store.publish_cloud("account", "logical-environment", epoch, workspace,
                               operation, [PROJECT["native_id"]], revision, [PROJECT])


def test_cloud_source_rejects_legacy_self_claimed_identity(tmp_path):
    store = DirectoryStore(tmp_path / "broker")
    legacy = store.register("account", "logical-environment", "cloud", "a" * 64, 1, sorted(CAPABILITIES))
    with pytest.raises(SyncError, match="SOURCE_REPAIR_REQUIRED"):
        publish(store)
    with pytest.raises(SyncError, match="SOURCE_HOST_ONLY"):
        store.snapshot("account", legacy["id"], "a" * 64, 1)


def test_cloud_receipts_survive_restart_and_reject_changed_root_or_old_epoch(tmp_path):
    root = tmp_path / "broker"
    store = DirectoryStore(root)
    first = publish(store)
    store = DirectoryStore(root)
    assert publish(store) == first
    with pytest.raises(SyncError, match="SOURCE_BINDING_CHANGED"):
        publish(store, epoch=2, workspace="other-root", operation="changed", revision=1)
    second = publish(store, epoch=2, operation="rebuild", revision=1)
    assert second["source"]["id"] == first["source"]["id"] and second["source"]["generation"] == 2
    with pytest.raises(SyncError, match="SOURCE_BINDING_CHANGED"):
        publish(store, operation="old-epoch", revision=2)


def test_failed_cloud_commit_rolls_back_identity_generation_and_inventory(tmp_path, monkeypatch):
    store = DirectoryStore(tmp_path / "broker")
    first = publish(store)
    def fail(*args):
        raise OSError("injected disk failure")
    monkeypatch.setattr(store, "_save_receipt", fail)
    with pytest.raises(OSError):
        publish(store, epoch=2, operation="failed", revision=1)
    with store._db() as db:
        assert db.execute("SELECT generation FROM sources").fetchone()[0] == 1
        assert db.execute("SELECT environment_epoch FROM cloud_bindings").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1
        assert db.execute("SELECT epoch FROM scopes").fetchone()[0] == 0
    assert first["source"]["generation"] == 1


@pytest.mark.asyncio
async def test_cloud_connector_keeps_same_operation_after_response_loss(tmp_path):
    store = DirectoryStore(tmp_path / "broker")
    replica = DirectoryReplica(tmp_path / "replica", "cloud-consumer")
    operations, lost = [], [True]
    async def request(method, params):
        if method.endswith("negotiate"):
            return negotiate(params["version"], params["capabilities"])
        operations.append(params["operation_id"])
        known = store.cloud_status("account", "logical-environment", params["operation_id"], params["project_ids"])
        result = known["receipt"] or store.publish_cloud("account", "logical-environment", 1, "workspace-hash",
            params["operation_id"], params["project_ids"], known["revision"], [PROJECT])
        if lost[0]:
            lost[0] = False
            raise ConnectionError("reply lost after commit")
        return result
    connector = DirectoryConnector(request, {}, "", replica)
    with pytest.raises(ConnectionError):
        await connector.publish_cloud([PROJECT["native_id"]])
    connector = DirectoryConnector(request, {}, "", DirectoryReplica(tmp_path / "replica", "cloud-consumer"))
    receipt = await connector.publish_cloud([PROJECT["native_id"]])
    assert operations[0] == operations[1] and receipt["revision"] == 1
    assert connector.replica.get("cloud_publish") is None


@pytest.mark.asyncio
async def test_old_gateway_cannot_silently_accept_cloud_export(tmp_path):
    async def request(method, params):
        assert method == "data_sync.negotiate"
        return {"version": 1, "capabilities": sorted(CAPABILITIES)}
    replica = DirectoryReplica(tmp_path / "replica", "old-host")
    with pytest.raises(SyncError, match="SOURCE_EXPORT_UNSUPPORTED"):
        await DirectoryConnector(request, {}, "", replica).publish_cloud([PROJECT["native_id"]])
    assert replica.get("cloud_publish") is None
