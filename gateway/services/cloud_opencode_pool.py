"""Durable YuanRong allocation for a project's independent OpenCode service."""
from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import tempfile
import time

import httpx

from gateway.extensions.yuanrong_frontend_client import YuanrongAgentApiError
from gateway.services.cloud_environments import EnvironmentUnavailable, _private_directory


logger = logging.getLogger(__name__)
PROVIDER = "opencode"
PORT = 4096
READY_RETRY_SECONDS = 0.25
WORKER_ROOT = PurePosixPath("/data/agent/workspace")
FAULT_GRACE_SECONDS = 30.0
STALL_GRACE_SECONDS = 60.0
_INFRASTRUCTURE_ERRORS = (YuanrongAgentApiError, OSError, TimeoutError)
_RECLAIM_ERRORS = (*_INFRASTRUCTURE_ERRORS, EnvironmentUnavailable, httpx.HTTPError, ValueError)


@dataclass(frozen=True)
class OpenCodeLease:
    instance_id: str
    directory: str
    password: str = field(repr=False)
    binding_id: str


class OpenCodeFault(Enum):
    LISTENER_UNAVAILABLE = "listener_unavailable"
    HEALTH_STALLED = "health_stalled"


def _initial_file(path: Path, content: bytes) -> bytes:
    """Write private configuration once, without replacing files on restart."""
    if not path.exists() and not path.is_symlink():
        fd, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("OpenCode Provider configuration must be private")
    return path.read_bytes()


class CloudOpencodePool:
    """One lease per use of a stable account and workspace binding.

    The enclosing cloud lifecycle owns the EnvironmentStore writer lease.
    Per-binding locks serialize create and reclaim within that Gateway.
    """

    def __init__(self, store, yuanrong, config, *, resources=None):
        self.store, self.yuanrong, self.resources = store, yuanrong, resources
        self.options = dict(config.opencode_provider)
        self.storage = Path(config.state_root) / "opencode-providers"
        self.runtime, self.namespace = config.runtime, config.namespace
        self.ready_timeout = config.ready_timeout
        self.idle_seconds = float(self.options.get("idle_seconds", 300))
        self.ready_check: Callable[[OpenCodeLease], Awaitable[bool]] | None = None
        self.idle_check: Callable[[OpenCodeLease], Awaitable[bool]] | None = None
        self.fault_check: Callable[[OpenCodeLease], Awaitable[OpenCodeFault | None]] | None = None
        self._locks = defaultdict(asyncio.Lock)
        self._holds = Counter()
        self._ready_operations: set[str] = set()
        self._fault_since: dict[str, tuple[OpenCodeFault, float]] = {}
        _private_directory(self.storage)
        with self.store.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS provider_bindings (
                    account_id TEXT NOT NULL, project_id TEXT NOT NULL, provider TEXT NOT NULL,
                    binding_id TEXT NOT NULL UNIQUE, directory TEXT NOT NULL, project_source TEXT NOT NULL,
                    profile_json TEXT NOT NULL, generation INTEGER NOT NULL, operation_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL, instance_id TEXT, used_at REAL NOT NULL,
                    PRIMARY KEY (account_id, project_id, provider)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS opencode_session_owners (
                    binding_id TEXT NOT NULL, native_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, directory TEXT NOT NULL,
                    PRIMARY KEY (binding_id, native_id)
                )
            """)

    def register_session(self, lease: OpenCodeLease, project_id: str, native_id: str):
        with self.store.connect() as db:
            if db.execute("INSERT OR IGNORE INTO opencode_session_owners VALUES (?, ?, ?, ?)",
                          (lease.binding_id, native_id, project_id, lease.directory)).rowcount != 1:
                raise EnvironmentUnavailable("OpenCode returned an already registered session")

    def project_sessions(self, lease: OpenCodeLease, project_id: str) -> set[str]:
        with self.store.connect() as db:
            return {row[0] for row in db.execute("""
                SELECT native_id FROM opencode_session_owners
                WHERE binding_id=? AND project_id=? AND directory=?
            """, (lease.binding_id, project_id, lease.directory))}

    def owns_session(self, lease: OpenCodeLease, project_id: str, native_id: str) -> bool:
        with self.store.connect() as db:
            return db.execute("""
                SELECT 1 FROM opencode_session_owners
                WHERE binding_id=? AND native_id=? AND project_id=? AND directory=?
            """, (lease.binding_id, native_id, project_id, lease.directory)).fetchone() is not None

    @staticmethod
    def _key(row):
        return row["account_id"], row["project_id"], row["provider"]

    def _get(self, key):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM provider_bindings WHERE account_id=? AND project_id=? AND provider=?", key).fetchone()
            return dict(row) if row else None

    def _check_account(self, account):
        current = self.store.by_user(account["account_id"])
        if current["state"] != "ALLOCATED" or any(current[name] != account[name] for name in (
            "environment_id", "epoch", "workspace", "instance_id",
        )):
            raise PermissionError("OpenCode Provider request does not own the current Worker")
        return current

    @staticmethod
    def _project_source(account, directory):
        path = PurePosixPath(directory)
        if str(path) != directory or not path.is_relative_to(WORKER_ROOT) or ".." in path.parts:
            raise PermissionError("OpenCode workspace is outside the account project root")
        if path == WORKER_ROOT:
            raise PermissionError("OpenCode requires an individual project workspace")
        path = path.relative_to(PurePosixPath("/data"))
        source = Path(account["workspace"]).joinpath(*path.parts)
        if not source.is_dir() or source.resolve(strict=True) != source:
            raise PermissionError("OpenCode workspace must be an existing canonical project directory")
        return str(source)

    def _binding(self, key, directory, source, account):
        row = self._get(key)
        if row is None:
            profile = {
                "image": self.options["image"], "runtime": self.runtime, "user": account["profile"]["runtime_user"],
                "account_workspace": account["workspace"], "physical_verification": self.resources is not None,
                "cpu": int(self.options.get("cpu", 1000)), "memory": int(self.options.get("memory", 1024)),
            }
            with self.store.connect() as db:
                db.execute("""INSERT INTO provider_bindings VALUES
                    (?, ?, ?, ?, ?, ?, ?, 1, ?, 'NEW', NULL, ?)""",
                    (*key, secrets.token_hex(16), directory, source, json.dumps(profile),
                     secrets.token_hex(16), time.time()),
                )
            row = self._get(key)
        if (row["directory"], row["project_source"]) != (directory, source):
            raise PermissionError("OpenCode workspace differs from its persistent binding")
        return row

    def _transition(self, row, state, *, instance_id=None, recycled=False):
        generation = row["generation"] + int(recycled)
        operation = secrets.token_hex(16) if recycled else row["operation_id"]
        with self.store.connect() as db:
            result = db.execute("""UPDATE provider_bindings SET state=?, instance_id=?, generation=?,
                operation_id=?, used_at=? WHERE binding_id=? AND generation=? AND state=?""",
                (state, instance_id, generation, operation, time.time(), row["binding_id"],
                 row["generation"], row["state"]),
            )
            if result.rowcount != 1:
                raise EnvironmentUnavailable("OpenCode Provider allocation changed")
        return self._get(self._key(row))

    def _recycle(self, row):
        updated = self._transition(row, "NEW", recycled=True)
        self._ready_operations.discard(row["operation_id"])
        self._fault_since.pop(row["operation_id"], None)
        try:
            shutil.rmtree(self.storage / row["binding_id"] / row["operation_id"])
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("OpenCode Provider generation cleanup deferred: %s", type(exc).__name__)
        return updated

    def _plan(self, row):
        profile = json.loads(row["profile_json"])
        if profile.get("physical_verification", False) != (self.resources is not None):
            raise EnvironmentUnavailable("OpenCode Provider physical boundary changed")
        root = self.storage / row["binding_id"]
        state = root / "state"
        config = root / row["operation_id"]
        for path in (root, state, config):
            _private_directory(path)
        if self.resources is not None:
            manifest = {
                "version": 2 if row["directory"] == str(WORKER_ROOT) else 1,
                "account_workspace": profile["account_workspace"],
                "project_source": row["project_source"], "project_target": row["directory"],
                "binding_id": row["binding_id"], "image": profile["image"], "user": profile["user"],
            }
            encoded = json.dumps(manifest, sort_keys=True).encode()
            if _initial_file(root / "scope.json", encoded) != encoded:
                raise EnvironmentUnavailable("OpenCode Provider physical scope changed")
        model_path = root / "opencode.json"
        if not model_path.exists():
            model_config = json.loads(Path(self.options["model_config"]).read_text())
            if not isinstance(model_config, dict):
                raise ValueError("OpenCode Provider model configuration must be an object")
            model_config.setdefault("permission", {"*": "ask", "question": "allow", "task": "deny"})
            model_config.update(autoupdate=False, share="disabled")
            _initial_file(model_path, json.dumps(model_config).encode())
        model = _initial_file(model_path, b"")
        password = _initial_file(root / "password", secrets.token_hex(24).encode())
        _initial_file(config / "opencode.json", model)
        _initial_file(config / "password", password)
        mounts = [
            {"source": row["project_source"], "target": row["directory"], "readonly": False},
            {"source": str(state), "target": "/state", "readonly": False},
            {"source": str(config), "target": "/run/opencode", "readonly": True},
        ]
        spec = {
            "sandbox_type": "docker", "runtime": profile["runtime"],
            "rootfs": {"imageurl": profile["image"], "user": profile["user"], "ports": [str(PORT)]},
            "cpu": profile["cpu"], "memory": profile["memory"],
            "cmds": [["sh", "-ec", 'export OPENCODE_SERVER_PASSWORD="$(cat /run/opencode/password)"; '
                       f'exec opencode serve --hostname 0.0.0.0 --port {PORT} --pure']],
        }
        return f'opencode-{row["operation_id"]}', str(state), spec, mounts, password.decode()

    @staticmethod
    def _matches(plan, info):
        name, workspace, spec, mounts, _ = plan
        root = info.get("rootfs") or {}
        user = spec["rootfs"]["user"]
        if (not isinstance(root, dict) or (info.get("name") and info["name"] != name)
                or root.get("imageurl") != spec["rootfs"]["imageurl"]
                or root.get("user", info.get("host_user")) != user
                or info.get("host_user", user) != user or not isinstance(root.get("mounts"), list)):
            return False
        actual = {}
        for mount in root["mounts"]:
            if not isinstance(mount, dict):
                return False
            target, readonly = mount.get("target"), mount.get("readonly", False)
            if not isinstance(target, str) or target in actual or type(readonly) is not bool:
                return False
            actual[target] = (mount.get("source"), readonly)

        # YuanRong 0.10.0 reports host_user and a workspace home bind in GET.
        home_target = f"/home/{user}"
        has_workspace_alias = actual.get(home_target) == (workspace, False)
        if has_workspace_alias:
            del actual[home_target]
        expected = {mount["target"]: (mount["source"], mount["readonly"]) for mount in mounts}
        workspace_matches = (root["workspace"] == workspace if "workspace" in root else has_workspace_alias)
        return workspace_matches and actual == expected

    async def _allocate(self, row, plan):
        if row["state"] in {"CREATING", "UNKNOWN"}:
            matching = []
            for item in await self.yuanrong.list_agent_instances():
                if self._matches(plan, await self.yuanrong.get_agent_info(item["instance_id"])):
                    matching.append(item["instance_id"])
            if len(matching) != 1:
                raise EnvironmentUnavailable("OpenCode Provider creation outcome remains unknown")
            return self._transition(row, "ALLOCATED", instance_id=matching[0])

        name, workspace, spec, mounts, _ = plan
        row = self._transition(row, "CREATING")
        try:
            instance = await self.yuanrong.create_sandbox(
                namespace=self.namespace, name=name, workspace=workspace, runtime_spec=spec, mounts=mounts,
                env_vars={"HOME": "/state", "XDG_CONFIG_HOME": "/state/config", "XDG_DATA_HOME": "/state/data",
                          "XDG_CACHE_HOME": "/state/cache", "XDG_STATE_HOME": "/state/runtime",
                          "OPENCODE_CONFIG": "/run/opencode/opencode.json", "OPENCODE_DISABLE_AUTOUPDATE": "1",
                          "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
                          "OPENCODE_DISABLE_MODELS_FETCH": "1", "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
                          "OPENCODE_DISABLE_LSP_DOWNLOAD": "1"},
            )
        except BaseException:
            self._transition(row, "UNKNOWN")
            raise
        return self._transition(row, "ALLOCATED", instance_id=instance.sandbox_id)

    @staticmethod
    def _physical_claim(row, plan):
        _, workspace, spec, mounts, _ = plan
        identity = next(mount["source"] for mount in mounts if mount["target"] == "/run/opencode")
        return {"workspace": workspace, "identity": identity, "image": spec["rootfs"]["imageurl"],
                "user": spec["rootfs"]["user"], "instance_id": row["instance_id"]}

    async def _confirm_retired(self, row, plan):
        if self.resources is not None:
            try:
                await self.resources.confirm_deleted(**self._physical_claim(row, plan))
            except RuntimeError as exc:
                raise EnvironmentUnavailable("OpenCode Provider physical deletion remains unconfirmed") from exc

    async def _confirmed_fault(self, row, plan):
        operation = row["operation_id"]
        if self.resources is None or self.fault_check is None:
            return False
        fault = await self.fault_check(self._lease(row, plan))
        if fault is None:
            self._fault_since.pop(operation, None)
            return False
        stalled = fault is OpenCodeFault.HEALTH_STALLED
        try:
            # A slow upstream alone cannot accumulate stall time. The same
            # running container must also stop answering local HTTP on each observation.
            if stalled and not await self.resources.confirm_opencode_stalled(**self._physical_claim(row, plan)):
                self._fault_since.pop(operation, None)
                return False
            now = time.monotonic()
            previous, first = self._fault_since.get(operation, (None, now))
            if previous is not fault:
                self._fault_since[operation] = fault, now
                return False
            grace = STALL_GRACE_SECONDS if stalled else FAULT_GRACE_SECONDS
            if now - first < max(grace, self.ready_timeout):
                return False
            self._fault_since.pop(operation, None)
            if stalled:
                return True
            return await self.resources.confirm_opencode_unavailable(**self._physical_claim(row, plan))
        except RuntimeError as exc:
            self._fault_since.pop(operation, None)
            raise EnvironmentUnavailable("OpenCode Provider physical fault remains unconfirmed") from exc

    @staticmethod
    def _lease(row, plan, directory=None):
        return OpenCodeLease(row["instance_id"], directory or row["directory"], plan[-1], row["binding_id"])

    async def _idle(self, row, plan):
        if self.idle_check is None:
            return False
        if row["directory"] != str(WORKER_ROOT):
            return await self.idle_check(self._lease(row, plan))
        with self.store.connect() as db:
            directories = [entry[0] for entry in db.execute(
                "SELECT DISTINCT directory FROM opencode_session_owners WHERE binding_id=?", (row["binding_id"],),
            )]
        for directory in directories or [row["directory"]]:
            if not await self.idle_check(self._lease(row, plan, directory)):
                return False
        return True

    async def _wait_until_ready(self, row, plan):
        ready_check = self.ready_check
        lease = self._lease(row, plan)
        operation = row["operation_id"]

        async def probe():
            if await ready_check(lease):
                self._ready_operations.add(operation)
                return True
            return False

        async def confirm_unreported_ready(info):
            return self._matches(plan, info) and await probe()

        async with asyncio.timeout(self.ready_timeout):
            if ready_check is None:
                info = await self.yuanrong.wait_until_running(lease.instance_id)
            else:
                info = await self.yuanrong.wait_until_running(
                    lease.instance_id, confirm_unreported_ready=confirm_unreported_ready,
                )
            if not self._matches(plan, info):
                raise EnvironmentUnavailable("OpenCode Provider ownership could not be verified")
            # YuanRong can report RUNNING before OpenCode can answer through its relay.
            if ready_check is not None and operation not in self._ready_operations:
                while not await probe():
                    await asyncio.sleep(READY_RETRY_SECONDS)

    @asynccontextmanager
    async def hold(self, account: dict, project_id: str, directory: str, *, shared: bool = False):
        current = self._check_account(account)
        if not isinstance(project_id, str) or not project_id or project_id.startswith("@") or len(project_id) > 200:
            raise ValueError("OpenCode requires a valid project ID")
        source = self._project_source(current, directory)
        # Existing project rows keep their original key. '@' is outside the
        # project ID alphabet and reserves one allocation per Worker environment.
        placement = "@" + current["environment_id"] if shared else project_id
        key = current["account_id"], placement, PROVIDER
        mount_target = str(WORKER_ROOT) if shared else directory
        mount_source = str(Path(current["workspace"]) / "agent/workspace") if shared else source
        try:
            async with self._locks[key]:
                current = self._check_account(account)
                row = self._binding(key, mount_target, mount_source, current)
                plan = self._plan(row)
                if row["state"] == "DELETING":
                    if not await self.yuanrong.instance_absent(row["instance_id"]):
                        raise EnvironmentUnavailable("OpenCode Provider deletion is pending")
                    await self._confirm_retired(row, plan)
                    row = self._recycle(row)
                    plan = self._plan(row)
                if row["state"] != "ALLOCATED":
                    row = await self._allocate(row, plan)

                await self._wait_until_ready(row, plan)
                self._check_account(account)
                self._holds[key] += 1
        except PermissionError:
            raise
        except _INFRASTRUCTURE_ERRORS as exc:
            raise EnvironmentUnavailable("OpenCode Provider allocation unavailable") from exc
        try:
            yield self._lease(row, plan, directory)
        finally:
            async with self._locks[key]:
                self._holds[key] -= 1
                if not self._holds[key]:
                    del self._holds[key]
                with self.store.connect() as db:
                    db.execute("UPDATE provider_bindings SET used_at=? WHERE binding_id=? AND generation=?",
                               (time.time(), row["binding_id"], row["generation"]))

    async def reclaim_idle(self) -> int:
        observe_faults = self.resources is not None and self.fault_check is not None
        with self.store.connect() as db:
            keys = [tuple(row) for row in db.execute("""SELECT account_id, project_id, provider FROM provider_bindings
                WHERE state='DELETING' OR (state='ALLOCATED' AND (? OR used_at<=?))""",
                (observe_faults, time.time() - self.idle_seconds))]
        reclaimed = 0
        for key in keys:
            try:
                async with self._locks[key]:
                    reclaimed += await self._reclaim(key)
            except _RECLAIM_ERRORS as exc:
                logger.warning("OpenCode Provider reclaim deferred: %s", type(exc).__name__)
        return reclaimed

    async def _reclaim(self, key):
        row = self._get(key)
        if row is None or row["state"] not in {"ALLOCATED", "DELETING"}:
            return 0
        if self._holds[key]:
            self._fault_since.pop(row["operation_id"], None)
            return 0
        idle_due = row["used_at"] <= time.time() - self.idle_seconds
        instance = row["instance_id"]
        plan = self._plan(row)
        absent = await self.yuanrong.instance_absent(instance)
        if not absent:
            if not self._matches(plan, await self.yuanrong.get_agent_info(instance)):
                self._fault_since.pop(row["operation_id"], None)
                raise EnvironmentUnavailable("OpenCode Provider ownership changed before deletion")
            if row["state"] == "ALLOCATED":
                idle = idle_due and await self._idle(row, plan)
                if not idle and not await self._confirmed_fault(row, plan):
                    return 0
                row = self._transition(row, "DELETING", instance_id=instance)
            await self.yuanrong.delete_sandbox(instance)
            if not await self.yuanrong.instance_absent(instance):
                return 0
        # A Frontend 404 did not initiate a delete. If physical confirmation
        # fails, keep ALLOCATED so a returning instance still needs an idle check.
        await self._confirm_retired(row, plan)
        self._recycle(row)
        return 1
