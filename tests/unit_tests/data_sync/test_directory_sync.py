import asyncio
import json
import secrets
import sqlite3

import pytest

from gateway.services.data_sync.store import DirectoryStore
from jiuwenswarm.data_sync.contract import CAPABILITIES, RETENTION, SyncError, digest, inventory
from jiuwenswarm.data_sync.connector import DirectoryConnector, DirectoryReplica
from jiuwenswarm.data_sync.project_source import inventory_payload, selected_inventory

PROOF = "a" * 64
OTHER_PROOF = "b" * 64


def register(store, name="device", scope="account", proof=PROOF):
    return store.register(scope, name, "local", proof, 1, sorted(CAPABILITIES))


def project(number, name=None):
    return {"native_id": f"p{number:04}", "name": name or f"Project {number}", "work_mode": "code"}


def publish(store, source, items, base=0, operation=None, scope="account"):
    values = inventory_payload(inventory(items), operation or secrets.token_hex(8), base)
    return store.publish(scope, source["id"], PROOF, source["generation"], values["operation_id"],
                         base, values["items"], values["total"], values["inventory_digest"], True)


def test_frozen_pages_concurrent_changes_and_tombstones(tmp_path):
    store = DirectoryStore(tmp_path / "broker")
    source = register(store)
    consumer = register(store, "consumer", proof=OTHER_PROOF)
    publish(store, source, [project(n) for n in range(105)])
    first = store.snapshot("account", consumer["id"], OTHER_PROOF, 1)
    assert len(first["items"]) == 100 and first["completion"] is None
    publish(store, source, [project(n, "renamed" if n == 1 else None) for n in range(1, 106)], base=1)
    second = store.snapshot("account", consumer["id"], OTHER_PROOF, 1, first["next_cursor"])
    original = first["items"] + second["items"]
    assert digest(original) == first["digest"] == second["digest"]
    assert len(original) == 105 and original == sorted(original, key=lambda row: row["id"])
    assert {row["native_id"] for row in original} == {project(n)["native_id"] for n in range(105)}
    changes = store.changes("account", consumer["id"], OTHER_PROOF, 1, second["completion"])
    assert len(changes["items"]) == 3
    assert any(row["deleted"] and row["native_id"] == "p0000" for row in changes["items"])
    assert any(row["project"]["name"] == "renamed" for row in changes["items"])
    assert first["coverage"][1 if first["coverage"][0]["id"] == consumer["id"] else 0]["inventory_complete"]


def test_durable_idempotency_ack_loss_and_revision_conflict(tmp_path):
    root = tmp_path / "broker"
    store = DirectoryStore(root)
    source = register(store)
    first = publish(store, source, [project(0)], operation="publish-1")
    store = DirectoryStore(root)
    assert publish(store, source, [project(0)], operation="publish-1") == first
    with pytest.raises(SyncError, match="OPERATION_CONFLICT"):
        publish(store, source, [project(1)], operation="publish-1")
    with pytest.raises(SyncError, match="REVISION_CONFLICT"):
        publish(store, source, [project(1)])
    page = store.snapshot("account", source["id"], PROOF, 1)
    ack = store.acknowledge("account", source["id"], PROOF, 1, "ack-1", page["completion"])
    store = DirectoryStore(root)
    assert store.acknowledge("account", source["id"], PROOF, 1, "ack-1", page["completion"]) == ack
    assert store.receipt("account", source["id"], PROOF, 1, "ack-1")["receipt"] == ack


def test_cross_account_proof_revocation_and_old_capabilities(tmp_path):
    store = DirectoryStore(tmp_path / "broker")
    source = register(store)
    other = register(store, scope="other")
    consumer = register(store, "consumer")
    publish(store, source, [project(1)])
    page = store.snapshot("account", consumer["id"], PROOF, 1)
    assert store.snapshot("other", other["id"], PROOF, 1)["items"] == []
    for scope, sid, proof, generation in [("other", source["id"], PROOF, 1), ("account", source["id"], OTHER_PROOF, 1), ("account", source["id"], PROOF, 2)]:
        with pytest.raises(SyncError, match="SOURCE_UNAUTHORIZED"):
            store.snapshot(scope, sid, proof, generation)
    with pytest.raises(SyncError, match="INVALID_CURSOR"):
        store.changes("other", other["id"], PROOF, 1, page["completion"])
    with pytest.raises(SyncError, match="SYNC_UNSUPPORTED"):
        store.register("account", "old", "local", PROOF, 0, [])
    store.revoke("account", source["id"])
    with pytest.raises(SyncError, match="SOURCE_UNAUTHORIZED"):
        publish(store, source, [project(2)], base=1)
    with pytest.raises(SyncError, match="SOURCE_UNAUTHORIZED"):
        register(store)
    with pytest.raises(SyncError, match="SYNC_SOURCE_CHANGED"):
        store.changes("account", consumer["id"], PROOF, 1, page["completion"])
    assert store.snapshot("account", consumer["id"], PROOF, 1)["items"] == []


def test_failed_inventory_and_commit_never_withdraw_projects(tmp_path, monkeypatch):
    store = DirectoryStore(tmp_path / "broker")
    source = register(store)
    publish(store, source, [project(1)])
    for total, expected_digest, complete in [(1, digest([]), True), (0, "wrong", True), (0, digest([]), False)]:
        with pytest.raises(SyncError, match="INCOMPLETE_INVENTORY"):
            store.publish("account", source["id"], PROOF, 1, "bad", 1, [], total, expected_digest, complete)
    def fail(*args):
        raise OSError("injected receipt failure")
    monkeypatch.setattr(store, "_save_receipt", fail)
    with pytest.raises(OSError):
        publish(store, source, [], base=1)
    page = store.snapshot("account", source["id"], PROOF, 1)
    assert len(page["items"]) == 1 and page["watermark"] == 1


def test_cursor_tampering_expiry_and_no_early_ack(tmp_path):
    now = [1000.0]
    store = DirectoryStore(tmp_path / "broker", clock=lambda: now[0])
    source = register(store)
    publish(store, source, [project(n) for n in range(101)])
    page = store.snapshot("account", source["id"], PROOF, 1)
    with pytest.raises(SyncError, match="INVALID_CURSOR"):
        store.acknowledge("account", source["id"], PROOF, 1, "early", page["next_cursor"])
    with pytest.raises(SyncError, match="INVALID_CURSOR"):
        store.snapshot("account", source["id"], PROOF, 1, page["next_cursor"] + "=")
    now[0] += 3601
    with pytest.raises(SyncError, match="SYNC_SNAPSHOT_EXPIRED"):
        store.snapshot("account", source["id"], PROOF, 1, page["next_cursor"])
    page = store.snapshot("account", source["id"], PROOF, 1)
    now[0] += RETENTION
    with pytest.raises(SyncError, match="SYNC_CURSOR_EXPIRED"):
        store.snapshot("account", source["id"], PROOF, 1, page["next_cursor"])


def test_source_export_keeps_empty_projects_and_rejects_corrupt_registry(tmp_path, monkeypatch):
    from jiuwenswarm.server.runtime.session import project_store
    monkeypatch.setattr(project_store, "get_agent_root_dir", lambda: tmp_path / "agent")
    root = tmp_path / "empty-project"
    root.mkdir()
    original = project_store.create_project("Empty project", str(root), "code")
    design = project_store.create_project("Existing design", str(tmp_path / "design"), "design")
    path = tmp_path / "agent/projects.json"
    before = path.read_bytes()
    assert selected_inventory([original.project_id]) == [{"native_id": original.project_id, "name": "Empty project", "work_mode": "code"}]
    with pytest.raises(SyncError, match="INVALID_PROJECT"):
        selected_inventory([design.project_id])
    assert list(root.iterdir()) == [] and path.read_bytes() == before
    path.write_text('{"projects": [')
    with pytest.raises(ValueError):
        selected_inventory([original.project_id])
    path.unlink()
    with pytest.raises(FileNotFoundError):
        selected_inventory([original.project_id])
    assert selected_inventory([]) == []
    path.symlink_to(root)
    with pytest.raises(OSError):
        selected_inventory([original.project_id])
    project_store.invalidate_cache()


@pytest.mark.asyncio
async def test_real_source_connector_replica_restart_and_ack_order(tmp_path, monkeypatch):
    from gateway.extensions.data_sync.extension import DataSyncPlugin
    from jiuwenswarm.server.runtime.session import project_store
    monkeypatch.setattr(project_store, "get_agent_root_dir", lambda: tmp_path / "agent")
    original = project_store.create_project("Empty project", str(tmp_path / "project"), "code")
    source_bytes = (tmp_path / "agent/projects.json").read_bytes()
    store = DirectoryStore(tmp_path / "broker")
    source = register(store)
    consumer = register(store, "consumer")
    plugin = DataSyncPlugin(store, lambda identity: "logical-cloud")
    lost = [True]
    replica = DirectoryReplica(tmp_path / "replicas", ["cloud", source["id"]])
    async def publish_rpc(method, params):
        result = plugin.dispatch("account", method.removeprefix("data_sync."), params)
        if method.endswith("inventory.publish") and lost[0]:
            lost[0] = False
            raise ConnectionError("publish response lost after commit")
        return result
    connector = DirectoryConnector(publish_rpc, source, PROOF, replica)
    with pytest.raises(ConnectionError):
        await connector.publish([original.project_id])
    assert replica.get("publish") is not None
    restarted = DirectoryReplica(tmp_path / "replicas", ["cloud", source["id"]])
    connector = DirectoryConnector(publish_rpc, register(store), PROOF, restarted)
    receipt = await connector.publish([original.project_id])
    assert receipt["revision"] == 1 and restarted.get("publish") is None
    replica = DirectoryReplica(tmp_path / "consumer", ["cloud", consumer["id"]])
    lost_ack = [True]
    async def read_rpc(method, params):
        if method.endswith("ack"):
            assert len(DirectoryReplica(tmp_path / "consumer", ["cloud", consumer["id"]]).projects()) == 1
        result = plugin.dispatch("account", method.removeprefix("data_sync."), params)
        if method.endswith("ack") and lost_ack[0]:
            lost_ack[0] = False
            raise ConnectionError("ACK response lost after commit")
        return result
    reader = DirectoryConnector(read_rpc, consumer, PROOF, replica)
    with pytest.raises(ConnectionError):
        await reader.pull()
    assert replica.get("ack") is not None
    reader = DirectoryConnector(read_rpc, consumer, PROOF, DirectoryReplica(tmp_path / "consumer", ["cloud", consumer["id"]]))
    assert len(await reader.pull()) == 1 and reader.replica.get("ack") is None
    assert (tmp_path / "agent/projects.json").read_bytes() == source_bytes
    assert not (tmp_path / "project").exists()
    project_store.invalidate_cache()


def test_replica_does_not_publish_a_partial_or_corrupt_snapshot(tmp_path):
    store = DirectoryStore(tmp_path / "broker")
    source = register(store)
    publish(store, source, [project(n) for n in range(101)])
    replica = DirectoryReplica(tmp_path / "replica", source["id"])
    first = store.snapshot("account", source["id"], PROOF, 1)
    assert not replica.accept_snapshot(first)
    assert replica.projects() == [] and replica.get("ack") is None
    second = store.snapshot("account", source["id"], PROOF, 1, first["next_cursor"])
    second["items"][0]["project"]["name"] = "tampered"
    with pytest.raises(SyncError, match="INCOMPLETE_SNAPSHOT"):
        replica.accept_snapshot(second)
    assert replica.projects() == [] and replica.get("ack") is None


@pytest.mark.asyncio
async def test_pending_publish_recovers_before_new_selection_and_rechecks_unchanged_source(tmp_path, monkeypatch):
    from gateway.extensions.data_sync.extension import DataSyncPlugin
    from jiuwenswarm.server.runtime.session import project_store
    monkeypatch.setattr(project_store, "get_agent_root_dir", lambda: tmp_path / "original")
    first = project_store.create_project("First", str(tmp_path / "first"), "code")
    second = project_store.create_project("Second", str(tmp_path / "second"), "code")
    store = DirectoryStore(tmp_path / "broker")
    source = register(store)
    replica = DirectoryReplica(tmp_path / "replica", source["id"])
    replica.prepare_publish(selected_inventory([first.project_id]), 0)
    plugin = DataSyncPlugin(store, lambda identity: None)
    async def request(method, params):
        return plugin.dispatch("account", method.removeprefix("data_sync."), params)
    connector = DirectoryConnector(request, source, PROOF, replica)
    result = await connector.publish([second.project_id])
    assert result["revision"] == 2 and replica.get("publish") is None
    assert [row["native_id"] for row in store.snapshot("account", source["id"], PROOF, 1)["items"]] == [second.project_id]
    store.revoke("account", source["id"])
    with pytest.raises(SyncError, match="SOURCE_UNAUTHORIZED"):
        await connector.publish([second.project_id])
    project_store.invalidate_cache()


def test_two_writers_cannot_commit_the_same_source_revision(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store = DirectoryStore(tmp_path / "broker")
    source = register(store)
    def attempt(number):
        try:
            return publish(store, source, [project(number)])
        except SyncError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [1, 2]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count("REVISION_CONFLICT") == 1
    assert len(store.snapshot("account", source["id"], PROOF, 1)["items"]) == 1
