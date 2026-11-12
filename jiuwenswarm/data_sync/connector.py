"""Explicit source publishing and durable, read-only directory replication."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from .contract import CAPABILITIES, CLOUD_EXPORT_CAPABILITY, MAX_PROJECTS, SyncError, digest, encoded, inventory, project_selection
from .project_source import inventory_payload, selected_inventory


class DirectoryReplica:
    """Private projection index; never writes ProjectStore or active workspaces."""

    def __init__(self, root, namespace):
        root = Path(root)
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError("replica root must be canonical")
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
        if os.name != "posix" or root.stat().st_mode & 0o077 or root.stat().st_uid != os.getuid():
            raise ValueError("replica root must be private")
        self.path = root / (digest(namespace) + ".db")
        if self.path.is_symlink():
            raise ValueError("linked replica database")
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        self.path.chmod(0o600)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _get(db, key):
        row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _put(db, key, value):
        db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (key, encoded(value).decode()))

    def get(self, key):
        with self._db() as db:
            return self._get(db, key)

    def set_selection(self, values):
        with self._db() as db:
            self._put(db, "ui_selection", project_selection(values))

    def mark_status(self, state, error=None):
        with self._db() as db:
            self._put(db, "status", {"state": state, "error": error, "checked_at": time.time()})

    def prepare_cloud_publish(self, selected):
        with self._db() as db:
            pending = self._get(db, "cloud_publish")
            if pending is None:
                pending = {"operation_id": secrets.token_hex(16), "project_ids": project_selection(selected)}
                self._put(db, "cloud_publish", pending)
            return pending

    def cloud_published(self, result):
        with self._db() as db:
            pending = self._get(db, "cloud_publish")
            if pending is None or pending["operation_id"] != result.get("operation_id"):
                raise SyncError("INVALID_RECEIPT")
            self._put(db, "cloud_published", result)
            db.execute("DELETE FROM state WHERE key='cloud_publish'")

    def prepare_publish(self, items, revision):
        with self._db() as db:
            pending = self._get(db, "publish")
            if pending is None:
                pending = inventory_payload(items, secrets.token_hex(16), revision)
                self._put(db, "publish", pending)
            return pending

    def published(self, receipt):
        with self._db() as db:
            pending = self._get(db, "publish")
            if pending and pending["operation_id"] == receipt["operation_id"]:
                if pending["inventory_digest"] != receipt["inventory_digest"] or pending["total"] != receipt["total"]:
                    raise SyncError("INVALID_RECEIPT")
                db.execute("DELETE FROM state WHERE key='publish'")
                self._put(db, "published", receipt)

    @staticmethod
    def _validate_objects(items, watermark):
        if not isinstance(items, list) or len(items) > 100 or type(watermark) is not int or watermark < 0:
            raise SyncError("INVALID_DIRECTORY")
        for item in items:
            if (not isinstance(item, dict) or set(item) != {"id", "source_id", "native_id", "revision", "deleted", "project", "watermark"}
                    or not isinstance(item["id"], str) or len(item["id"]) != 64
                    or type(item["revision"]) is not int or item["revision"] < 1
                    or type(item["deleted"]) is not bool or type(item["watermark"]) is not int
                    or not 0 < item["watermark"] <= watermark):
                raise SyncError("INVALID_DIRECTORY")
            inventory([item["project"]])
            if item["native_id"] != item["project"]["native_id"]:
                raise SyncError("INVALID_DIRECTORY")

    def accept_snapshot(self, page):
        self._validate_objects(page["items"], page["watermark"])
        with self._db() as db:
            staging = self._get(db, "snapshot")
            header = {key: page[key] for key in ("snapshot_id", "total", "digest", "watermark", "coverage", "account_complete")}
            if page["account_complete"] is not False or type(page["total"]) is not int or not 0 <= page["total"] <= MAX_PROJECTS:
                raise SyncError("INVALID_DIRECTORY")
            if staging is None:
                staging = {"header": header, "items": []}
            if staging["header"] != header:
                raise SyncError("SNAPSHOT_CHANGED")
            items = staging["items"] + page["items"]
            if len({item["id"] for item in items}) != len(items) or len(items) > page["total"] or any(item["deleted"] for item in items):
                raise SyncError("INVALID_DIRECTORY")
            if page["next_cursor"] is not None:
                if not isinstance(page["next_cursor"], str) or page.get("completion") is not None or not page["items"]:
                    raise SyncError("INVALID_DIRECTORY")
                self._put(db, "snapshot", {"header": header, "items": items, "cursor": page["next_cursor"]})
                return False
            if len(items) != page["total"] or digest(items) != page["digest"] or not isinstance(page.get("completion"), str):
                raise SyncError("INCOMPLETE_SNAPSHOT")
            db.execute("DELETE FROM objects")
            db.executemany("INSERT INTO objects VALUES(?,?)", [(item["id"], encoded(item).decode()) for item in items])
            db.execute("DELETE FROM state WHERE key='snapshot'")
            self._put(db, "coverage", header)
            self._checkpoint(db, page["completion"], page["watermark"])
            return True

    def _checkpoint(self, db, completion, watermark):
        self._put(db, "completion", completion)
        self._put(db, "watermark", watermark)
        self._put(db, "ack", {"operation_id": secrets.token_hex(16), "completion": completion})

    def accept_changes(self, page):
        self._validate_objects(page["items"], page["watermark"])
        with self._db() as db:
            watermark = self._get(db, "watermark")
            if watermark is None or page["watermark"] < watermark or not isinstance(page.get("completion"), str):
                raise SyncError("INVALID_DIRECTORY")
            for item in page["items"]:
                if item["watermark"] != watermark + 1:
                    raise SyncError("CHANGE_GAP")
                watermark = item["watermark"]
                if item["deleted"]:
                    db.execute("DELETE FROM objects WHERE id=?", (item["id"],))
                else:
                    db.execute("INSERT OR REPLACE INTO objects VALUES(?,?)", (item["id"], encoded(item).decode()))
            if watermark != page["watermark"]:
                raise SyncError("CHANGE_GAP")
            if "coverage" in page:
                sources = page["coverage"]
                if (not isinstance(sources, list) or len(sources) > 32
                        or any(not isinstance(source, dict) or not isinstance(source.get("id"), str)
                               or source.get("kind") not in {"local", "cloud"}
                               or type(source.get("revision")) is not int or source["revision"] < 0
                               or type(source.get("generation")) is not int or source["generation"] < 1
                               for source in sources)
                        or len({source["id"] for source in sources}) != len(sources)):
                    raise SyncError("INVALID_DIRECTORY")
                header = self._get(db, "coverage") or {}
                self._put(db, "coverage", {**header, "coverage": sources})
            self._checkpoint(db, page["completion"], watermark)

    def acknowledged(self, operation):
        with self._db() as db:
            pending = self._get(db, "ack")
            if pending and pending["operation_id"] == operation:
                db.execute("DELETE FROM state WHERE key='ack'")

    def reset_snapshot(self):
        with self._db() as db:
            # Keep the last published view, but never ACK a now-invalid cursor.
            db.execute("DELETE FROM state WHERE key IN ('snapshot','completion','ack','watermark')")

    def projects(self):
        with self._db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM objects ORDER BY id")]


class DirectoryConnector:
    def __init__(self, request, source, proof, replica):
        self.request, self.source, self.proof, self.replica = request, source, proof, replica

    async def _call(self, action, params):
        return await self.request("data_sync." + action, {"source_id": self.source["id"], "source_token": self.proof,
                                                        "generation": self.source["generation"], **params})

    async def publish_cloud(self, selected_ids):
        capabilities = await self.request("data_sync.negotiate", {"version": 1, "capabilities": sorted(CAPABILITIES)})
        if CLOUD_EXPORT_CAPABILITY not in capabilities.get("capabilities", []):
            raise SyncError("SOURCE_EXPORT_UNSUPPORTED")
        selected = project_selection(selected_ids)
        pending = self.replica.prepare_cloud_publish(selected)
        result = await self.request("data_sync.cloud.publish", pending)
        self.replica.cloud_published(result)
        if pending["project_ids"] != selected:
            return await self.publish_cloud(selected)
        return result

    async def publish(self, selected_ids):
        pending = self.replica.get("publish")
        if pending is not None:
            await self._publish_pending(pending)
        # Recover the frozen previous intent before reading the new selection.
        items = selected_inventory(selected_ids)
        previous = self.replica.get("published")
        if previous and previous["inventory_digest"] == digest(items) and previous["revision"] == self.source["revision"]:
            # Even unchanged metadata must revalidate the session and source.
            known = await self._call("receipt", {"operation_id": previous["operation_id"]})
            if known["state"] == "committed":
                return known["receipt"]
        return await self._publish_pending(self.replica.prepare_publish(items, self.source["revision"]))

    async def _publish_pending(self, pending):
        old = await self._call("receipt", {"operation_id": pending["operation_id"]})
        receipt = old["receipt"] if old["state"] == "committed" else await self._call("inventory.publish", pending)
        self.replica.published(receipt)
        self.source["revision"] = receipt["revision"]
        return receipt

    async def _ack(self):
        pending = self.replica.get("ack")
        if pending:
            result = await self._call("ack", pending)
            if result["operation_id"] != pending["operation_id"] or result["acknowledged"] != self.replica.get("watermark"):
                raise SyncError("INVALID_RECEIPT")
            self.replica.acknowledged(pending["operation_id"])

    async def pull(self):
        self.replica.mark_status("refreshing")
        try:
            await self._ack()
            if self.replica.get("completion") is None:
                for _ in range(MAX_PROJECTS // 100 + 1):
                    staging = self.replica.get("snapshot")
                    page = await self._call("snapshot", {"cursor": staging["cursor"] if staging else None})
                    if self.replica.accept_snapshot(page):
                        break
                else:
                    raise SyncError("SYNC_PAGE_BUDGET")
            else:
                for _ in range(100):
                    page = await self._call("changes", {"cursor": self.replica.get("completion")})
                    self.replica.accept_changes(page)
                    await self._ack()
                    if len(page["items"]) < 100:
                        break
                else:
                    raise SyncError("SYNC_PAGE_BUDGET")
            await self._ack()
        except BaseException as exc:
            code = exc.code if isinstance(exc, SyncError) else "SYNC_INTERRUPTED"
            if code in {"SYNC_CURSOR_EXPIRED", "SYNC_SNAPSHOT_EXPIRED", "SYNC_SOURCE_CHANGED"}:
                self.replica.reset_snapshot()
            self.replica.mark_status("stale", code)
            raise
        self.replica.mark_status("current")
        return self.replica.projects()


async def register_source(request, installation_id, proof, kind="local"):
    values = {"version": 1, "capabilities": sorted(CAPABILITIES)}
    await request("data_sync.negotiate", values)
    params = {**values, "kind": kind, "source_token": proof}
    if kind == "local":
        params["installation_id"] = installation_id
    return await request("data_sync.source.register", params)
