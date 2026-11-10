"""Durable environment policy. Physical work belongs to the original Router."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import time
import threading

from websockets.exceptions import WebSocketException

from gateway.auth.accounts import AccountStore


class EnvironmentUnavailable(RuntimeError):
    pass


def _private_directory(path: Path):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise PermissionError("environment path cannot contain symlinks")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode) or (os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
        raise PermissionError("environment directory must be private")


class EnvironmentStore:
    def __init__(self, path: Path, authority: str, workspace_root: Path, auth_root: Path, default_profile: dict):
        self.path, self.authority = Path(path), authority
        self.workspace_root, self.auth_root = Path(workspace_root), Path(auth_root)
        self.default_profile = dict(default_profile)
        for root in (self.path.parent, self.workspace_root, self.auth_root):
            _private_directory(root)
        if self.path.is_symlink():
            raise PermissionError("environment database cannot be a symlink")
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(fd)
        if self.path.stat().st_mode & 0o077:
            raise PermissionError("environment database must be private")
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS control_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS registration_intents (
                    username TEXT PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL, profile_json TEXT NOT NULL,
                    account_id TEXT, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS environment_bindings (
                    account_id TEXT PRIMARY KEY, environment_id TEXT UNIQUE NOT NULL,
                    profile_json TEXT NOT NULL, workspace TEXT NOT NULL,
                    epoch INTEGER NOT NULL, operation_id TEXT UNIQUE NOT NULL,
                    state TEXT NOT NULL, instance_id TEXT, updated REAL NOT NULL, auth_override TEXT, imported INTEGER NOT NULL DEFAULT 0);
            """)
            db.execute("INSERT OR IGNORE INTO control_settings VALUES ('authority', ?)", (authority,))
            if db.execute("SELECT value FROM control_settings WHERE key='authority'").fetchone()[0] != authority:
                raise PermissionError("environment authority changed")
        self._writer = None
        self._revocation_lock = threading.Lock()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def acquire_writer(self):
        # The first release supports one control-plane writer, not a distributed lease.
        if self._writer is not None:
            return
        from filelock import FileLock, Timeout
        lock = FileLock(str(self.path) + ".writer.lock")
        try:
            lock.acquire(timeout=0)
        except Timeout as exc:
            raise EnvironmentUnavailable("another Gateway owns this environment store") from exc
        self._writer = lock

    def close(self):
        if self._writer is not None:
            self._writer.release()
            self._writer = None

    def registration(self, username, password):
        username = AccountStore.validate(username, password)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO registration_intents VALUES (?,?,?,NULL,?)",
                       (username, secrets.token_hex(16), json.dumps(self.default_profile, sort_keys=True), time.time()))
            intent = dict(db.execute("SELECT * FROM registration_intents WHERE username=?", (username,)).fetchone())
            self._check_placement(json.loads(intent["profile_json"]))
            return intent

    def _check_placement(self, profile):
        # Pool names are routing bindings, never proof of infrastructure isolation.
        expected = self.default_profile.get("placement")
        actual = profile.get("placement")
        if profile.get("physical_verification", False) != self.default_profile.get("physical_verification", False):
            raise EnvironmentUnavailable("physical verification binding differs; explicit reconciliation required")
        if actual != expected:
            raise EnvironmentUnavailable("execution pool binding differs; explicit reconciliation required")

    def bind_registration(self, intent, principal):
        self._identity(principal)
        if principal.get("username") != intent["username"]:
            raise PermissionError("registration receipt differs")
        env_id = "env_" + secrets.token_hex(16)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM registration_intents WHERE operation_id=?", (intent["operation_id"],)).fetchone()
            if row is None or row["account_id"] not in (None, principal["user_id"]):
                raise PermissionError("registration intent differs")
            self._check_placement(json.loads(row["profile_json"]))
            db.execute("INSERT OR IGNORE INTO environment_bindings (account_id,environment_id,profile_json,workspace,epoch,operation_id,state,instance_id,updated) VALUES (?,?,?,?,1,?,'NEW',NULL,?)",
                       (principal["user_id"], env_id, row["profile_json"], str(self.workspace_root / env_id), secrets.token_hex(16), time.time()))
            db.execute("UPDATE registration_intents SET account_id=? WHERE operation_id=?", (principal["user_id"], intent["operation_id"]))
        return self.get(principal)

    def _validate_import_credential(self, path, user_id, environment_id=None, epoch=None):
        from gateway.common.security.service_auth import ServiceAuthenticator
        auth = ServiceAuthenticator(path)
        cfg = auth._config()
        if (cfg["login_owner"] != {"actor_id": user_id, "authority": self.authority}
                or cfg.get("revocations_file") != "revocations.json"
                or cfg["workspace"] != "/data/agent"
                or (environment_id is not None and cfg["instance_id"] != environment_id)
                or (epoch is not None and cfg["epoch"] != epoch)):
            raise PermissionError("existing instance binding requires compatible owner/epoch/revocation configuration")
        auth._check_revocation(cfg, "")
        return cfg

    def adopt_existing(self, principal, *, instance_id, profile, workspace, auth_file):
        """Operator-only import; preserve the reviewed image, paths and key bytes."""
        self._identity(principal)
        self._check_placement(profile)
        import re
        if not instance_id or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(profile.get("image_digest"))):
            raise ValueError("explicit instance and immutable image required")
        workspace = Path(workspace)
        if not workspace.is_absolute() or not workspace.is_dir():
            raise PermissionError("existing private workspace required")
        _private_directory(workspace)
        cfg = self._validate_import_credential(auth_file, principal["user_id"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM environment_bindings WHERE account_id=?", (principal["user_id"],)).fetchone()
            if existing is not None:
                if (existing["instance_id"] != instance_id or existing["workspace"] != str(workspace)
                        or existing["auth_override"] != str(auth_file) or json.loads(existing["profile_json"]) != profile):
                    raise PermissionError("existing binding cannot be overwritten")
            else:
                db.execute("INSERT INTO environment_bindings VALUES (?,?,?,?,?,?,'ALLOCATED',?,?,?,1)",
                           (principal["user_id"], cfg["instance_id"], json.dumps(profile, sort_keys=True), str(workspace),
                            cfg["epoch"], secrets.token_hex(16), instance_id, time.time(), str(auth_file)))
        return self.get(principal)

    def _identity(self, principal):
        if principal.get("authority") != self.authority or not principal.get("user_id"):
            raise PermissionError("environment identity differs")

    def get(self, principal):
        self._identity(principal)
        return self.by_user(principal["user_id"])

    def by_user(self, user_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM environment_bindings WHERE account_id=?", (user_id,)).fetchone()
        if row is None:
            raise EnvironmentUnavailable("existing account binding requires reconciliation")
        value = dict(row)
        value["authority"] = self.authority
        value["profile"] = json.loads(value.pop("profile_json"))
        self._check_placement(value["profile"])
        value["auth_file"] = value["auth_override"] or str(self.auth_root / value["environment_id"] / str(value["epoch"]) / "instance-auth.json")
        value["name"] = value["environment_id"] + "-" + value["operation_id"]
        return value

    def rows(self):
        with self.connect() as db:
            users = [r[0] for r in db.execute("SELECT account_id FROM environment_bindings")]
        return [self.by_user(u) for u in users]

    def prepare(self, user_id):
        row = self.by_user(user_id)
        if row["state"] == "DELETING":
            raise EnvironmentUnavailable("delete outcome requires reconciliation")
        if row["state"] == "DELETED":
            with self.connect() as db:
                db.execute("UPDATE environment_bindings SET epoch=epoch+1,operation_id=?,state='NEW',instance_id=NULL,auth_override=NULL,updated=? WHERE account_id=? AND epoch=? AND state='DELETED'",
                           (secrets.token_hex(16), time.time(), user_id, row["epoch"]))
            row = self.by_user(user_id)
        workspace = Path(row["workspace"])
        if not row["imported"] and workspace.resolve().parent != self.workspace_root.resolve():
            raise PermissionError("workspace outside private account root")
        _private_directory(workspace)
        if row["auth_override"]:
            self._validate_import_credential(row["auth_file"], user_id, row["environment_id"], row["epoch"])
            return row
        # The /data bind hides image directories, including HOME=/data/home.
        # Prepare it before the infrastructure bootstrap imports native SDKs.
        for leaf in ("agent", "config", "home"):
            _private_directory(workspace / leaf)
        target = Path(row["auth_file"])
        _private_directory(target.parent)
        revocations = target.parent / "revocations.json"
        try:
            fd = os.open(revocations, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            if revocations.is_symlink():
                raise PermissionError("invalid revocation file")
        else:
            with os.fdopen(fd, "w") as stream:
                stream.write("{}"); stream.flush(); os.fsync(stream.fileno())
        cfg = {"mode": "user_instance", "instance_id": row["environment_id"], "epoch": row["epoch"],
               "workspace": "/data/agent", "login_owner": {"actor_id": user_id, "authority": self.authority},
               "signing_key": secrets.token_hex(32), "revocations_file": "revocations.json"}
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except FileExistsError:
            from gateway.common.security.service_auth import ServiceAuthenticator
            existing = ServiceAuthenticator(target)._config()
            if any(existing[k] != cfg[k] for k in ("instance_id", "epoch", "login_owner", "workspace")):
                raise PermissionError("instance credential differs")
        else:
            with os.fdopen(fd, "w") as stream:
                json.dump(cfg, stream); stream.flush(); os.fsync(stream.fileno())
        return row

    def transition(self, row, state, *, instance_id=None, expected=None):
        with self.connect() as db:
            query = "UPDATE environment_bindings SET state=?,instance_id=COALESCE(?,instance_id),updated=? WHERE account_id=? AND epoch=? AND operation_id=?"
            args = [state, instance_id, time.time(), row["account_id"], row["epoch"], row["operation_id"]]
            if expected:
                query += " AND state=?"; args.append(expected)
            if db.execute(query, args).rowcount != 1:
                raise EnvironmentUnavailable("stale environment operation")

    def revoke(self, principal, token):
        with self._revocation_lock:
            self._revoke(principal, token)

    def _revoke(self, principal, token):
        row = self.get(principal)
        directory = Path(row["auth_file"]).parent
        if not directory.exists():
            return
        path = directory / "revocations.json"
        records = json.loads(path.read_text()) if path.exists() else {}
        now = time.time()
        records = {key: value for key, value in records.items() if value is True or float(value) > now}
        records[hashlib.sha256(token.encode()).hexdigest()] = now + 20
        temporary = directory / (".revocations-" + secrets.token_hex(8))
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(records, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)


class EnvironmentService:
    def __init__(self, store: EnvironmentStore, accounts, instances):
        self.store, self.accounts, self.instances = store, accounts, instances

    async def register(self, username, password):
        intent = await asyncio.to_thread(self.store.registration, username, password)
        principal = await asyncio.to_thread(self.accounts.register, username, password, operation_id=intent["operation_id"])
        row = await asyncio.to_thread(self.store.bind_registration, intent, principal)
        return principal, row

    async def ensure(self, principal):
        row = self.store.get(principal)
        try:
            runtime = await self.instances.ensure_instance(principal["user_id"])
        except (RuntimeError, TimeoutError, ConnectionError, WebSocketException) as exc:
            raise EnvironmentUnavailable("instance preparation requires recovery") from exc
        row = self.store.get(principal)
        return {**row, "state": "READY", "instance_id": runtime.info.sandbox_id}
