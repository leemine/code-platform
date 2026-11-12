"""Durable directory ledger with frozen pages and account-scoped receipts.

Algorithms follow codeswarm sync_store; account/node/Runtime mixins are not
imported. The caller supplies an already authenticated opaque account scope.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from jiuwenswarm.data_sync.contract import (CAPABILITIES, MAX_PROJECTS, PAGE_SIZE, RETENTION, SNAPSHOT_TTL,
                       SyncError, digest, encoded, identifier, inventory, negotiate, proof_digest)


class DirectoryStore:
    def __init__(self, root, clock=time.time):
        root = Path(root)
        if not root.is_absolute() or root.resolve() != root:
            raise ValueError("sync root must be a canonical operator-owned path")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "posix" or root.stat().st_mode & 0o077 or root.stat().st_uid != os.getuid():
            raise ValueError("sync root must be private to its operator")
        self.path, self.clock = root / "directory.db", clock
        if self.path.is_symlink():
            raise ValueError("linked sync database")
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scopes (scope TEXT PRIMARY KEY, seq INTEGER NOT NULL DEFAULT 0,
                    epoch INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, scope TEXT NOT NULL,
                    binding TEXT NOT NULL, kind TEXT NOT NULL, proof TEXT NOT NULL,
                    generation INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 0,
                    revoked INTEGER NOT NULL DEFAULT 0, UNIQUE(scope,binding));
                CREATE TABLE IF NOT EXISTS objects (scope TEXT NOT NULL, id TEXT NOT NULL,
                    source TEXT NOT NULL, body TEXT NOT NULL, deleted INTEGER NOT NULL, revision INTEGER NOT NULL,
                    PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS changes (scope TEXT NOT NULL, seq INTEGER NOT NULL,
                    body TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(scope,seq));
                CREATE TABLE IF NOT EXISTS receipts (scope TEXT NOT NULL, source TEXT NOT NULL,
                    operation TEXT NOT NULL, digest TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(scope,source,operation));
                CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, scope TEXT NOT NULL,
                    consumer TEXT NOT NULL, watermark INTEGER NOT NULL, epoch INTEGER NOT NULL,
                    body TEXT NOT NULL, coverage TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS acks (scope TEXT NOT NULL, source TEXT NOT NULL,
                    watermark INTEGER NOT NULL, PRIMARY KEY(scope,source));
                CREATE TABLE IF NOT EXISTS cloud_bindings (source TEXT PRIMARY KEY,
                    environment_epoch INTEGER NOT NULL, workspace_digest TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES('schema','1')")
            if db.execute("SELECT value FROM settings WHERE key='schema'").fetchone()[0] != "1":
                raise SyncError("SYNC_SCHEMA_UNSUPPORTED")
            db.execute("INSERT OR IGNORE INTO settings VALUES('cursor_key',?)", (secrets.token_hex(32),))
        self.path.chmod(0o600)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            if db.in_transaction:
                db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _source(db, scope, source, proof, generation):
        row = db.execute("SELECT * FROM sources WHERE scope=? AND id=?", (scope, source)).fetchone()
        if row is not None and row["kind"] == "cloud":
            raise SyncError("SOURCE_HOST_ONLY")
        if (row is None or row["revoked"] or type(generation) is not int
                or generation != row["generation"] or not hmac.compare_digest(row["proof"], proof_digest(proof))):
            raise SyncError("SOURCE_UNAUTHORIZED")
        return row

    @staticmethod
    def _public(row):
        return {**{key: row[key] for key in ("id", "kind", "generation", "revision")}, "inventory_complete": row["revision"] > 0}

    def register(self, scope, binding, kind, proof, version, capabilities):
        negotiate(version, capabilities)
        identifier(binding)
        if kind not in {"local", "cloud"}:
            raise SyncError("INVALID_SOURCE_KIND")
        secret = proof_digest(proof)
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO scopes(scope) VALUES(?)", (scope,))
            row = db.execute("SELECT * FROM sources WHERE scope=? AND binding=?", (scope, kind + ":" + binding)).fetchone()
            if row is not None:
                if row["revoked"] or not hmac.compare_digest(row["proof"], secret):
                    raise SyncError("SOURCE_UNAUTHORIZED")
                return self._public(row)
            if db.execute("SELECT count(*) FROM sources WHERE scope=?", (scope,)).fetchone()[0] >= 32:
                raise SyncError("SYNC_QUOTA")
            source = "src_" + secrets.token_hex(16)
            db.execute("INSERT INTO sources(id,scope,binding,kind,proof) VALUES(?,?,?,?,?)",
                       (source, scope, kind + ":" + binding, kind, secret))
            return self._public(db.execute("SELECT * FROM sources WHERE id=?", (source,)).fetchone())

    @staticmethod
    def _receipt(db, scope, source, operation, payload_digest):
        identifier(operation)
        row = db.execute("SELECT * FROM receipts WHERE scope=? AND source=? AND operation=?",
                         (scope, source, operation)).fetchone()
        if row:
            if not hmac.compare_digest(row["digest"], payload_digest):
                raise SyncError("OPERATION_CONFLICT")
            return json.loads(row["body"])
        if db.execute("SELECT count(*) FROM receipts WHERE scope=?", (scope,)).fetchone()[0] >= 100000:
            raise SyncError("SYNC_QUOTA")
        return None

    @staticmethod
    def _save_receipt(db, scope, source, operation, payload_digest, result):
        db.execute("INSERT INTO receipts VALUES(?,?,?,?,?)", (scope, source, operation, payload_digest, encoded(result).decode()))
        return result

    def receipt(self, scope, source, proof, generation, operation):
        with self._db() as db:
            self._source(db, scope, source, proof, generation)
            row = db.execute("SELECT body FROM receipts WHERE scope=? AND source=? AND operation=?",
                             (scope, source, identifier(operation))).fetchone()
            return {"state": "committed", "receipt": json.loads(row[0])} if row else {"state": "unknown"}

    def _change(self, db, scope, source, native_id, project, deleted):
        object_id = digest([scope, source, native_id])
        previous = db.execute("SELECT * FROM objects WHERE scope=? AND id=?", (scope, object_id)).fetchone()
        if previous and previous["deleted"] == deleted and json.loads(previous["body"])["project"] == project:
            return
        revision = previous["revision"] + 1 if previous else 1
        db.execute("UPDATE scopes SET seq=seq+1 WHERE scope=?", (scope,))
        seq = db.execute("SELECT seq FROM scopes WHERE scope=?", (scope,)).fetchone()[0]
        value = {"id": object_id, "source_id": source, "native_id": native_id, "revision": revision,
                 "deleted": bool(deleted), "project": project, "watermark": seq}
        body = encoded(value).decode()
        db.execute("INSERT OR REPLACE INTO objects VALUES(?,?,?,?,?,?)", (scope, object_id, source, body, deleted, revision))
        db.execute("INSERT INTO changes VALUES(?,?,?,?)", (scope, seq, body, self.clock()))

    def publish(self, scope, source, proof, generation, operation, base_revision, items, total, inventory_digest, complete):
        items = inventory(items)
        if complete is not True or type(total) is not int or total != len(items) or inventory_digest != digest(items):
            raise SyncError("INCOMPLETE_INVENTORY")
        if type(base_revision) is not int or base_revision < 0:
            raise SyncError("INVALID_REVISION")
        payload_digest = digest(["publish", generation, base_revision, items])
        with self._db() as db:
            row = self._source(db, scope, source, proof, generation)
            result = self._receipt(db, scope, source, operation, payload_digest)
            if result is not None:
                return result
            if row["revision"] != base_revision:
                raise SyncError("REVISION_CONFLICT")
            result = self._apply_inventory(db, scope, row, items, operation)
            return self._save_receipt(db, scope, source, operation, payload_digest, result)

    def _apply_inventory(self, db, scope, row, items, operation):
        source = row["id"]
        if db.execute("SELECT count(*) FROM changes WHERE scope=?", (scope,)).fetchone()[0] + len(items) + MAX_PROJECTS > 100000:
            raise SyncError("SYNC_QUOTA")
        previous = db.execute("SELECT * FROM objects WHERE scope=? AND source=? AND deleted=0", (scope, source)).fetchall()
        other = db.execute("SELECT count(*) FROM objects WHERE scope=? AND source!=? AND deleted=0", (scope, source)).fetchone()[0]
        if other + len(items) > MAX_PROJECTS:
            raise SyncError("SYNC_QUOTA")
        current = {item["native_id"] for item in items}
        for item in items:
            self._change(db, scope, source, item["native_id"], item, False)
        for old in previous:
            value = json.loads(old["body"])
            if value["native_id"] not in current:
                self._change(db, scope, source, value["native_id"], value["project"], True)
        db.execute("UPDATE sources SET revision=revision+1 WHERE id=?", (source,))
        watermark = db.execute("SELECT seq FROM scopes WHERE scope=?", (scope,)).fetchone()[0]
        return {"operation_id": operation, "revision": row["revision"] + 1,
                "watermark": watermark, "inventory_digest": digest(items), "total": len(items)}

    @staticmethod
    def _cloud_source(db, scope, environment):
        row = db.execute("SELECT * FROM sources WHERE scope=? AND binding=?", (scope, "cloud:" + identifier(environment))).fetchone()
        if row is not None:
            if row["revoked"]:
                raise SyncError("SOURCE_UNAUTHORIZED")
            if db.execute("SELECT 1 FROM cloud_bindings WHERE source=?", (row["id"],)).fetchone() is None:
                raise SyncError("SOURCE_REPAIR_REQUIRED")
        return row

    def cloud_status(self, scope, environment, operation, selection):
        """Resolve a frozen request before contacting the original instance."""
        request_digest = digest(["cloud.publish", selection])
        with self._db() as db:
            row = self._cloud_source(db, scope, environment)
            result = self._receipt(db, scope, row["id"], operation, request_digest) if row else None
            return {"revision": row["revision"] if row else 0, "receipt": result}

    def catalog(self, scope, offset=0, version=None):
        """Read the accepted directory for UI, without registering a consumer/ACK."""
        if type(offset) is not int or not 0 <= offset <= MAX_PROJECTS:
            raise SyncError("INVALID_REQUEST")
        with self._db() as db:
            state = db.execute("SELECT seq,epoch FROM scopes WHERE scope=?", (scope,)).fetchone()
            sources = [self._public(row) for row in db.execute(
                "SELECT * FROM sources WHERE scope=? AND revoked=0 ORDER BY id", (scope,))]
            current = digest([scope, list(state) if state else [0, 0], sources])
            if offset and version != current:
                raise SyncError("SYNC_CATALOG_CHANGED")
            total = db.execute("SELECT count(*) FROM objects WHERE scope=? AND deleted=0", (scope,)).fetchone()[0]
            items = [json.loads(row[0]) for row in db.execute(
                "SELECT body FROM objects WHERE scope=? AND deleted=0 ORDER BY id LIMIT ? OFFSET ?",
                (scope, PAGE_SIZE, offset))]
            return {"items": items, "sources": sources, "total": total, "version": current,
                    "next_offset": offset + len(items) if offset + len(items) < total else None,
                    "watermark": state[0] if state else 0, "account_complete": False}

    def publish_cloud(self, scope, environment, epoch, workspace_digest, operation, selection, base_revision, items):
        """Accept only host-attested exports; caller holds the environment guard."""
        items = inventory(items)
        if type(epoch) is not int or epoch < 1:
            raise SyncError("SOURCE_BINDING_CHANGED")
        request_digest = digest(["cloud.publish", selection])
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO scopes(scope) VALUES(?)", (scope,))
            row = self._cloud_source(db, scope, environment)
            if row is None:
                if db.execute("SELECT count(*) FROM sources WHERE scope=?", (scope,)).fetchone()[0] >= 32:
                    raise SyncError("SYNC_QUOTA")
                source = "src_" + secrets.token_hex(16)
                # The random publisher credential never leaves this control plane.
                db.execute("INSERT INTO sources(id,scope,binding,kind,proof) VALUES(?,?,?,'cloud',?)",
                           (source, scope, "cloud:" + environment, proof_digest(secrets.token_hex(32))))
                db.execute("INSERT INTO cloud_bindings VALUES(?,?,?)", (source, epoch, workspace_digest))
                row = db.execute("SELECT * FROM sources WHERE id=?", (source,)).fetchone()
            old = self._receipt(db, scope, row["id"], operation, request_digest)
            if old is not None:
                return old
            if row["revision"] != base_revision:
                raise SyncError("REVISION_CONFLICT")
            binding = db.execute("SELECT * FROM cloud_bindings WHERE source=?", (row["id"],)).fetchone()
            if binding["workspace_digest"] != workspace_digest or epoch < binding["environment_epoch"]:
                raise SyncError("SOURCE_BINDING_CHANGED")
            if epoch > binding["environment_epoch"]:
                db.execute("UPDATE sources SET generation=generation+1 WHERE id=?", (row["id"],))
                db.execute("UPDATE cloud_bindings SET environment_epoch=? WHERE source=?", (epoch, row["id"]))
                db.execute("UPDATE scopes SET epoch=epoch+1 WHERE scope=?", (scope,))
                row = db.execute("SELECT * FROM sources WHERE id=?", (row["id"],)).fetchone()
            result = self._apply_inventory(db, scope, row, items, operation)
            updated = db.execute("SELECT * FROM sources WHERE id=?", (row["id"],)).fetchone()
            result.update(source=self._public(updated), environment_epoch=epoch)
            return self._save_receipt(db, scope, row["id"], operation, request_digest, result)

    def revoke(self, scope, source):
        with self._db() as db:
            row = db.execute("SELECT * FROM sources WHERE scope=? AND id=?", (scope, source)).fetchone()
            if row is None:
                raise SyncError("SOURCE_UNAUTHORIZED")
            if not row["revoked"]:
                for old in db.execute("SELECT body FROM objects WHERE scope=? AND source=? AND deleted=0", (scope, source)).fetchall():
                    value = json.loads(old[0])
                    self._change(db, scope, source, value["native_id"], value["project"], True)
                db.execute("UPDATE sources SET revoked=1,generation=generation+1 WHERE id=?", (source,))
                db.execute("UPDATE scopes SET epoch=epoch+1 WHERE scope=?", (scope,))
            return {"source_id": source, "revoked": True}

    def _sign(self, db, scope, consumer, kind, values):
        body = encoded({"scope": scope, "consumer": consumer, "kind": kind, "issued": self.clock(), **values})
        key = bytes.fromhex(db.execute("SELECT value FROM settings WHERE key='cursor_key'").fetchone()[0])
        return base64.urlsafe_b64encode(body + hmac.digest(key, body, "sha256")).decode().rstrip("=")

    def _verify(self, db, scope, consumer, token, kind):
        if not isinstance(token, str) or not 1 <= len(token) <= 4096:
            raise SyncError("INVALID_CURSOR")
        try:
            raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
            body, signature = raw[:-32], raw[-32:]
            key = bytes.fromhex(db.execute("SELECT value FROM settings WHERE key='cursor_key'").fetchone()[0])
            if (base64.urlsafe_b64encode(raw).decode().rstrip("=") != token
                    or not hmac.compare_digest(signature, hmac.digest(key, body, "sha256"))):
                raise ValueError()
            value = json.loads(body)
            if value["scope"] != scope or value["consumer"] != consumer or value["kind"] != kind:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise SyncError("INVALID_CURSOR") from None
        if not 0 <= self.clock() - value["issued"] < RETENTION:
            raise SyncError("SYNC_CURSOR_EXPIRED")
        if value["epoch"] != db.execute("SELECT epoch FROM scopes WHERE scope=?", (scope,)).fetchone()[0]:
            raise SyncError("SYNC_SOURCE_CHANGED")
        return value

    def snapshot(self, scope, source, proof, generation, cursor=None):
        with self._db() as db:
            self._source(db, scope, source, proof, generation)
            if cursor is None:
                db.execute("DELETE FROM snapshots WHERE expires<=?", (self.clock(),))
                if db.execute("SELECT count(*) FROM snapshots WHERE scope=? AND consumer=?", (scope, source)).fetchone()[0] >= 5:
                    raise SyncError("SYNC_QUOTA")
                state = db.execute("SELECT * FROM scopes WHERE scope=?", (scope,)).fetchone()
                items = [json.loads(row[0]) for row in db.execute("SELECT body FROM objects WHERE scope=? AND deleted=0 ORDER BY id", (scope,))]
                coverage = [self._public(row) for row in db.execute("SELECT * FROM sources WHERE scope=? AND revoked=0 ORDER BY id", (scope,))]
                snap = "snap_" + secrets.token_hex(16)
                db.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?)", (snap, scope, source, state["seq"], state["epoch"], encoded(items).decode(), encoded(coverage).decode(), self.clock() + SNAPSHOT_TTL))
                offset = 0
            else:
                value = self._verify(db, scope, source, cursor, "snapshot")
                snap, offset = value["snapshot"], value["offset"]
            row = db.execute("SELECT * FROM snapshots WHERE id=? AND scope=? AND consumer=?", (snap, scope, source)).fetchone()
            if row is None or row["expires"] <= self.clock():
                raise SyncError("SYNC_SNAPSHOT_EXPIRED")
            items = json.loads(row["body"])
            end = min(offset + PAGE_SIZE, len(items))
            boundary = {"watermark": row["watermark"], "epoch": row["epoch"]}
            more = end < len(items)
            return {"items": items[offset:end], "total": len(items), "snapshot_id": snap,
                    "watermark": row["watermark"], "digest": digest(items), "coverage": json.loads(row["coverage"]),
                    "account_complete": False, "next_cursor": self._sign(db, scope, source, "snapshot", {**boundary, "snapshot": snap, "offset": end}) if more else None,
                    "completion": None if more else self._sign(db, scope, source, "complete", boundary)}

    def changes(self, scope, source, proof, generation, cursor):
        with self._db() as db:
            self._source(db, scope, source, proof, generation)
            value = self._verify(db, scope, source, cursor, "complete")
            rows = db.execute("SELECT seq,body FROM changes WHERE scope=? AND seq>? ORDER BY seq LIMIT ?", (scope, value["watermark"], PAGE_SIZE)).fetchall()
            end = rows[-1]["seq"] if rows else value["watermark"]
            return {"items": [json.loads(row["body"]) for row in rows], "watermark": end,
                    "coverage": [self._public(row) for row in db.execute("SELECT * FROM sources WHERE scope=? AND revoked=0 ORDER BY id", (scope,))],
                    "completion": self._sign(db, scope, source, "complete", {"watermark": end, "epoch": value["epoch"]})}

    def acknowledge(self, scope, source, proof, generation, operation, completion):
        with self._db() as db:
            self._source(db, scope, source, proof, generation)
            value = self._verify(db, scope, source, completion, "complete")
            payload_digest = digest(["ack", value["watermark"], value["epoch"]])
            old = self._receipt(db, scope, source, operation, payload_digest)
            if old is not None:
                return old
            db.execute("INSERT INTO acks VALUES(?,?,?) ON CONFLICT(scope,source) DO UPDATE SET watermark=max(watermark,excluded.watermark)", (scope, source, value["watermark"]))
            return self._save_receipt(db, scope, source, operation, payload_digest,
                                     {"operation_id": operation, "acknowledged": value["watermark"]})
