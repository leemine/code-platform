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
import uuid

import httpx

from gateway.common.opencode_model_policy import account_models_revision, base_permission_rules, deployment_model_policy
from gateway.common.opencode_runtime import DEVICE_CONTEXT, DEVICE_ID, RUNTIME_TARGET, WORKER_ROOT, runtime_source
from gateway.extensions.yuanrong_frontend_client import YuanrongAgentApiError
from gateway.services.cloud_environments import EnvironmentUnavailable, _private_directory
from gateway.common.runtime_device import device_prefix, validate_registration
from gateway.services.cloud_provider_allocation import (
    allocate_provider, ensure_bindings_table, matches_allocation, read_binding,
    register_named_binding, RuntimeDeviceNameConflict,
)


logger = logging.getLogger(__name__)
PROVIDER = "opencode"
PORT = 4096
READY_RETRY_SECONDS = 0.25
PROFILE_ID = "opencode-cloud"
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
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass  # Another planner already pinned the snapshot.
        finally:
            Path(temporary).unlink(missing_ok=True)
    return _read_private_file(path)


def _read_private_file(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("OpenCode Provider configuration must be private")
    return path.read_bytes()


class OpenCodeConfigurationError(ValueError):
    """Safe public rejection for the affected managed Provider binding."""


class CloudOpencodePool:
    """One lease per use of a stable account and workspace binding.

    The enclosing cloud lifecycle owns the EnvironmentStore writer lease.
    Per-binding locks serialize create and reclaim within that Gateway.
    """

    def __init__(self, store, yuanrong, config, *, resources=None):
        self.store, self.yuanrong, self.resources = store, yuanrong, resources
        self.options = dict(config.opencode_provider)

        model_file = self.options.get("model_config")
        self.model_config = json.loads(Path(model_file).read_text()) if model_file else {}
        if not isinstance(self.model_config, dict):
            raise ValueError("OpenCode Provider model configuration must be an object")
        deployment_model_policy(self.model_config)
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
        ensure_bindings_table(self.store)
        with self.store.connect() as db:
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
        return read_binding(self.store, key)

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

    @staticmethod
    def _new_binding_id(key):
        # Resolve the first shared snapshot before the Worker starts. A catalog
        # read never allocates an instance or inserts a Provider binding.
        if key[1].startswith("@"):
            return uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(key)).hex
        return secrets.token_hex(16)

    def _binding_config(self, root):
        path = root / "opencode.json"
        content = {**self.model_config, "autoupdate": False, "share": "disabled"}
        content.setdefault("permission", base_permission_rules("ask"))
        return _initial_file(path, json.dumps(content).encode())

    def _effective_config(self, root):
        config = json.loads(self._binding_config(root))
        overlay = root / "account-models.json"
        if overlay.exists() or overlay.is_symlink():
            models = json.loads(_read_private_file(overlay))["provider"]
            if models:
                config["provider"] = {**models, **config.get("provider", {})}
        return config

    @staticmethod
    def _checked_policy(config):
        if not isinstance(config, dict):
            raise OpenCodeConfigurationError("opencode_model_snapshot_stale")
        permission = config.get("permission")
        if (permission != base_permission_rules("ask") or next(iter(permission)) != "*"
                or config.get("tools")):
            raise OpenCodeConfigurationError("opencode_approval_policy_conflict")
        for section in ("agent", "mode"):
            settings = config.get(section, {})
            if not isinstance(settings, dict) or any(
                not isinstance(agent, dict) or "permission" in agent or "tools" in agent
                for agent in settings.values()
            ):
                raise OpenCodeConfigurationError("opencode_approval_policy_conflict")
        try:
            return deployment_model_policy(config)
        except (ValueError, AttributeError, TypeError) as exc:
            raise OpenCodeConfigurationError("opencode_model_snapshot_stale") from exc

    def _bound_model_policy(self, root, row):
        _private_directory(root)
        if row and (row["state"] != "NEW" or row["generation"] > 1) and not (root / "opencode.json").is_file():
            raise OpenCodeConfigurationError("opencode_model_snapshot_stale")
        snapshot = self._effective_config(root)
        policy = self._checked_policy(snapshot)
        if row:
            mounted = root / row["operation_id"] / "opencode.json"
            if mounted.exists() or mounted.is_symlink():
                active = json.loads(_read_private_file(mounted))
                self._checked_policy(active)
                # The CLI may add its editor schema hint when reading a configuration.
                active.pop("$schema", None)
                snapshot.pop("$schema", None)
                if active != snapshot:
                    raise OpenCodeConfigurationError("opencode_model_snapshot_stale")
            elif row["state"] != "NEW":
                raise OpenCodeConfigurationError("opencode_model_snapshot_stale")
        return policy

    def worker_model_policy(self, account):
        key = account["account_id"], "@" + account["environment_id"], PROVIDER
        row = self._get(key)
        # Switch-based deployments provision the relay even with intake closed.
        # The allocation gate can then change while the Worker stays running.
        if ("admit_new_bindings" not in self.options and row is None
                and not self._admits_new_binding(account["account_id"])):
            # Existing project-scoped bindings also need their relay after a Worker restart.
            with self.store.connect() as db:
                inherited = db.execute(
                    """SELECT 1 FROM provider_bindings
                       WHERE account_id=? AND provider=?
                         AND (substr(project_id, 1, 1)<>'@' OR project_id LIKE ?) LIMIT 1""",
                    (account["account_id"], PROVIDER, device_prefix(account) + "%"),
                ).fetchone()
            if inherited is None:
                return None
        root = self.storage / (row["binding_id"] if row else self._new_binding_id(key))
        try:
            self._bound_model_policy(root, row)
            return {**self._checked_policy(json.loads(self._binding_config(root))), "account_model_sync": True}
        except (ValueError, OSError) as exc:
            # Keep unrelated execution providers available on this Worker.
            logger.warning("Managed OpenCode configuration unavailable for this binding")
            reason = str(exc) if isinstance(exc, OpenCodeConfigurationError) else "opencode_model_snapshot_stale"
            return {"default": None, "models": {}, "error": reason}

    def _admits_new_binding(self, account_id):
        if "admit_new_bindings" in self.options:
            return self.options["admit_new_bindings"]
        allowlist = self.options.get("account_allowlist")
        return allowlist is None or account_id in allowlist

    def _public_runtime(self, key, row):
        available = row is not None or self._admits_new_binding(key[0])
        lock = self._locks.get(key)
        if row and row["state"] == "DELETING":
            state = "reconciling"
        elif row and row["state"] == "ALLOCATED" and row["operation_id"] in self._ready_operations:
            state = "ready"
        elif lock is not None and lock.locked():
            state = "starting"
        elif row and (row["state"] == "ALLOCATED" or row["display_name"] is not None and row["state"] != "NEW"):
            state = "unknown"
        elif row and row["generation"] > 1:
            state = "idle"
        elif row and row["display_name"] is not None and row["state"] == "NEW":
            state = "not_started"
        else:
            state = "not_created"
        return {"available": available, "reason": None if available else "managed_admission_closed", "state": state}

    def account_runtime(self, account: dict) -> dict:
        key = account["account_id"], "@" + account["environment_id"], PROVIDER
        return self._public_runtime(key, self._get(key))

    def _device_key(self, account, runtime_id):
        if not isinstance(runtime_id, str) or not DEVICE_ID.fullmatch(runtime_id):
            raise ValueError("Invalid managed device ID")
        return account["account_id"], device_prefix(account) + runtime_id, PROVIDER

    def _device_runtime(self, row):
        return {
            "runtime_id": row["binding_id"], "display_name": row["display_name"],
            **self._public_runtime(self._key(row), row),
        }

    def runtime_template(self, account):
        return {"runtime_profile_id": PROFILE_ID, "cpu": int(self.options.get("cpu", 1000)),
                "memory": int(self.options.get("memory", 1024)),
                "available": account["state"] == "ALLOCATED" and self._admits_new_binding(account["account_id"])}

    def account_devices(self, account):
        prefix = device_prefix(account)
        with self.store.connect() as db:
            rows = db.execute("""SELECT * FROM provider_bindings
                WHERE account_id=? AND provider=? AND substr(project_id, 1, ?)=? AND display_name IS NOT NULL
                ORDER BY display_name""", (account["account_id"], PROVIDER, len(prefix), prefix)).fetchall()
        return [self._device_runtime(row) for row in rows]

    def device_runtime(self, account, runtime_id, project_id=DEVICE_CONTEXT, directory=str(WORKER_ROOT)):
        current = self._check_account(account)
        key, target, source = self._binding_scope(current, project_id, directory, True, runtime_id)
        return self._device_runtime(self._binding(key, target, source, current))

    def register_device(self, account, name, create_token):
        validate_registration(name, create_token)
        runtime_id = self._new_binding_id((account["account_id"], device_prefix(account) + create_token, PROVIDER))
        key = self._device_key(account, runtime_id)

        def insert(db):
            if not self._admits_new_binding(account["account_id"]):
                raise PermissionError("Account is not admitted for a new managed OpenCode binding")
            self._insert_binding(db, key, runtime_id, str(WORKER_ROOT), self._shared_source(account), account, name)

        try:
            row = register_named_binding(self.store, account, key, runtime_id, name, insert)
        except RuntimeDeviceNameConflict as exc:
            raise OpenCodeConfigurationError(str(exc)) from exc
        return self._device_runtime(row)

    def _insert_binding(self, db, key, binding_id, directory, source, account, display_name=None):
        profile = {
            "image": self.options["image"], "runtime": self.runtime, "user": account["profile"]["runtime_user"],
            "account_workspace": account["workspace"], "physical_verification": self.resources is not None,
            "cpu": int(self.options.get("cpu", 1000)), "memory": int(self.options.get("memory", 1024)),
        }
        if "shared_runtime" in self.options:
            profile["shared_runtime"] = runtime_source(self.options["shared_runtime"])
        db.execute("""INSERT INTO provider_bindings
            (account_id, project_id, provider, binding_id, directory, project_source, profile_json,
             generation, operation_id, state, instance_id, used_at, display_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 'NEW', NULL, ?, ?)""",
            (*key, binding_id, directory, source, json.dumps(profile), secrets.token_hex(16), time.time(), display_name),
        )

    def project_runtime(self, account: dict, project_id: str, directory: str) -> dict:
        current = self._check_account(account)
        key, target, source = self._binding_scope(current, project_id, directory, shared=True)
        row = self._get(key)
        if row is not None and (row["directory"], row["project_source"]) != (target, source):
            raise PermissionError("OpenCode workspace differs from its persistent binding")
        return self._public_runtime(key, row)

    def _binding(self, key, directory, source, account):
        row = self._get(key)
        if row is None:
            if key[1].startswith(device_prefix(account)):
                raise PermissionError("Managed device is not registered for this account")
            if not self._admits_new_binding(account["account_id"]):
                raise PermissionError("Account is not admitted for a new managed OpenCode binding")
            with self.store.connect() as db:
                self._insert_binding(db, key, self._new_binding_id(key), directory, source, account)
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
                "binding_id": row["binding_id"], "image": profile.get("initial_image", profile["image"]),
                "user": profile["user"],
            }
            encoded = json.dumps(manifest, sort_keys=True).encode()
            if _initial_file(root / "scope.json", encoded) != encoded:
                raise EnvironmentUnavailable("OpenCode Provider physical scope changed")
            if profile["image"] != manifest["image"] or "shared_runtime" in profile:
                generation = {**manifest, "image": profile["image"]}
                if "shared_runtime" in profile:
                    generation["shared_runtime"] = runtime_source(profile["shared_runtime"])
                encoded_generation = json.dumps(generation, sort_keys=True).encode()
                if _initial_file(config / "scope.json", encoded_generation) != encoded_generation:
                    raise EnvironmentUnavailable("OpenCode Provider generation scope changed")
        model = json.dumps(self._effective_config(root)).encode()
        password = _initial_file(root / "password", secrets.token_hex(24).encode())
        _initial_file(config / "opencode.json", model)
        _initial_file(config / "password", password)
        mounts = [
            {"source": row["project_source"], "target": row["directory"], "readonly": False},
            {"source": str(state), "target": "/state", "readonly": False},
            {"source": str(config), "target": "/run/opencode", "readonly": True},
        ]
        if "shared_runtime" in profile:
            if self.resources is None:
                raise EnvironmentUnavailable("OpenCode shared runtime requires physical admission")
            mounts.append({"source": runtime_source(profile["shared_runtime"]), "target": RUNTIME_TARGET,
                           "readonly": True})
        spec = {
            "sandbox_type": "docker", "runtime": profile["runtime"],
            "rootfs": {"imageurl": profile["image"], "user": profile["user"], "ports": [str(PORT)]},
            "cpu": profile["cpu"], "memory": profile["memory"],
            "cmds": [["sh", "-ec", 'export OPENCODE_SERVER_PASSWORD="$(cat /run/opencode/password)"; '
                       f'exec opencode serve --hostname 0.0.0.0 --port {PORT} --pure']],
        }
        return f'opencode-{row["operation_id"]}', str(state), spec, mounts, password.decode()

    _matches = staticmethod(matches_allocation)

    async def _allocate(self, row, plan):
        return await allocate_provider(
            self.yuanrong, self.namespace, row, plan, self._transition, provider_name="OpenCode",
            env_vars={"HOME": "/state", "XDG_CONFIG_HOME": "/state/config", "XDG_DATA_HOME": "/state/data",
                      "XDG_CACHE_HOME": "/state/cache", "XDG_STATE_HOME": "/state/runtime",
                      "OPENCODE_CONFIG": "/run/opencode/opencode.json", "OPENCODE_DISABLE_AUTOUPDATE": "1",
                      "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
                      "OPENCODE_DISABLE_MODELS_FETCH": "1", "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
                      "OPENCODE_DISABLE_LSP_DOWNLOAD": "1"},
        )

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
        initial = operation not in self._ready_operations
        health_confirmed = not initial
        started = time.monotonic()
        stage = "yuanrong_running"
        outcome = "failed"
        attempts = 0

        async def probe():
            nonlocal attempts, health_confirmed
            attempts += 1
            if await ready_check(lease):
                health_confirmed = True
                return True
            return False

        async def confirm_unreported_ready(info):
            nonlocal stage
            if not self._matches(plan, info):
                return False
            stage = "authenticated_health"
            if await probe():
                return True
            stage = "yuanrong_running"
            return False

        try:
            async with asyncio.timeout(self.ready_timeout):
                if ready_check is None:
                    info = await self.yuanrong.wait_until_running(lease.instance_id)
                else:
                    info = await self.yuanrong.wait_until_running(
                        lease.instance_id, confirm_unreported_ready=confirm_unreported_ready,
                    )
                if not self._matches(plan, info):
                    raise EnvironmentUnavailable("OpenCode Provider ownership could not be verified")
                # YuanRong can report RUNNING before OpenCode answers its authenticated probe.
                if ready_check is not None:
                    stage = "authenticated_health"
                    while not health_confirmed and not await probe():
                        await asyncio.sleep(READY_RETRY_SECONDS)
            self._ready_operations.add(operation)
            outcome = "ready"
        except TimeoutError:
            outcome = "timeout"
            raise
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            if initial or outcome != "ready":
                logger.log(
                    logging.WARNING if outcome in {"timeout", "failed"} else logging.INFO,
                    "opencode_provider_readiness event_id=%s account_id=%s binding_id=%s operation_id=%s "
                    "generation=%d attempt=%s stage=%s outcome=%s elapsed_ms=%d timeout_ms=%d health_attempts=%d",
                    secrets.token_hex(12), row["account_id"], row["binding_id"], operation, row["generation"],
                    "initial" if initial else "recheck", stage, outcome,
                    round((time.monotonic() - started) * 1000), round(self.ready_timeout * 1000), attempts,
                )

    @staticmethod
    def _shared_source(account):
        source = Path(account["workspace"]) / "agent/workspace"
        if not source.is_dir() or source.resolve(strict=True) != source:
            raise PermissionError("OpenCode requires the canonical account workspace")
        return str(source)

    def _binding_scope(self, account, project_id, directory, shared, runtime_id=None):
        if not isinstance(project_id, str) or not project_id or project_id.startswith("@") or len(project_id) > 200:
            raise ValueError("OpenCode requires a valid project ID")
        if runtime_id is not None and project_id == DEVICE_CONTEXT:
            if directory != str(WORKER_ROOT):
                raise PermissionError("Invalid managed device directory")
            source = None
        else:
            source = self._project_source(account, directory)
        if runtime_id is not None:
            return self._device_key(account, runtime_id), str(WORKER_ROOT), self._shared_source(account)
        # Existing project rows keep their original key. '@' is outside the
        # project ID alphabet and reserves one allocation per Worker environment.
        placement = "@" + account["environment_id"] if shared else project_id
        key = account["account_id"], placement, PROVIDER
        mount_target = str(WORKER_ROOT) if shared else directory
        mount_source = self._shared_source(account) if shared else source
        return key, mount_target, mount_source

    @asynccontextmanager
    async def hold(self, account: dict, project_id: str, directory: str, *, shared: bool = False, runtime_id=None):
        current = self._check_account(account)
        key, mount_target, mount_source = self._binding_scope(current, project_id, directory, shared, runtime_id)
        try:
            async with self._locks[key]:
                current = self._check_account(account)
                row = self._binding(key, mount_target, mount_source, current)
                self._bound_model_policy(self.storage / row["binding_id"], row)
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

    async def sync_models(self, account, project_id, directory, revision, *, shared, models=None, previous=None, runtime_id=None):
        """Install a Worker-generated private fragment at an idle generation boundary."""
        current = self._check_account(account)
        key, mount_target, mount_source = self._binding_scope(current, project_id, directory, shared, runtime_id)
        async with self._locks[key]:
            current = self._check_account(account)
            row = self._binding(key, mount_target, mount_source, current)
            root = self.storage / row["binding_id"]
            self._bound_model_policy(root, row)
            base = json.loads(self._binding_config(root)).get("provider", {})
            path = root / "account-models.json"
            saved = (json.loads(_read_private_file(path)) if path.exists()
                     else {"revision": account_models_revision({}), "provider": {}})
            if saved["revision"] == revision:
                return revision
            if self._holds[key]:
                raise OpenCodeConfigurationError("opencode_model_sync_busy")
            if models is None:
                return saved["revision"]
            if previous != saved["revision"]:
                raise OpenCodeConfigurationError("opencode_model_sync_changed")
            desired = {k: v for k, v in models.items() if k not in base}
            if desired != saved["provider"]:
                if row["state"] in {"UNKNOWN", "CREATING"}:
                    row = await self._allocate(row, self._plan(row))
                if row["state"] == "NEW" and (root / row["operation_id"]).exists():
                    self._recycle(row)
                elif row["state"] != "NEW" and not await self._reclaim(key, refresh=True):
                    raise OpenCodeConfigurationError("opencode_model_sync_busy")
            self._check_account(account)
            fd, temporary = tempfile.mkstemp(dir=root)
            try:
                with os.fdopen(fd, "w") as out:
                    json.dump({"revision": revision, "provider": desired}, out)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return revision

    async def reclaim_idle(self) -> int:
        observe_faults = self.resources is not None and self.fault_check is not None
        with self.store.connect() as db:
            keys = [tuple(row) for row in db.execute("""SELECT account_id, project_id, provider FROM provider_bindings
                WHERE provider=? AND (state='DELETING' OR (state='ALLOCATED' AND (? OR used_at<=?)))""",
                (PROVIDER, observe_faults, time.time() - self.idle_seconds))]
        reclaimed = 0
        for key in keys:
            try:
                async with self._locks[key]:
                    reclaimed += await self._reclaim(key)
            except _RECLAIM_ERRORS as exc:
                logger.warning("OpenCode Provider reclaim deferred: %s", type(exc).__name__)
        return reclaimed

    async def _reclaim(self, key, *, refresh=False):
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
                idle = (refresh or idle_due) and await self._idle(row, plan)
                if not idle and (refresh or not await self._confirmed_fault(row, plan)):
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
