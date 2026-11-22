"""Stable Codex volumes and leases through the existing YuanRong client."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import time
import uuid

from gateway.common.managed_codex import IDENTITY_TARGET, NATIVE_PORT, PROFILE_ID, validate_device_model_id
from gateway.common.runtime_device import DEVICE_ID, WORKER_ROOT as PROJECT_ROOT, device_prefix, validate_registration
from gateway.common.opencode_runtime import RUNTIME_TARGET
from gateway.extensions.yuanrong_frontend_client import YuanrongAgentApiError
from gateway.services.cloud_environments import EnvironmentUnavailable, _private_directory
from gateway.services.cloud_provider_allocation import (
    allocate_provider,
    ensure_bindings_table,
    matches_allocation,
    private_initial_file,
    read_binding,
    read_private_file,
    register_named_binding,
    RuntimeDeviceNameConflict,
)
from gateway.services.managed_codex_models import CATALOG_FILENAME, CodexModelBroker, native_model_catalog


logger = logging.getLogger(__name__)
PROVIDER = "codex"
_MODEL_BRIDGE = "python3.11 -B /opt/codex-candidate/model_bridge.py --socket /run/codex/model.sock"
_STDIO_BRIDGE = " --port 17543 & exec python3.11 -B /opt/codex-candidate/stdio_bridge.py"
_COMMAND = _MODEL_BRIDGE + ' --model "$CODEX_SELECTED_MODEL"' + _STDIO_BRIDGE
_SESSION_MODEL_COMMAND = _MODEL_BRIDGE + _STDIO_BRIDGE


class CodexRuntimeModelMismatch(PermissionError):
    """The request differs from the model fixed to a Codex binding."""


@dataclass(frozen=True)
class CodexLease:
    address: str
    capability: str = field(repr=False)
    session_models: bool = False
    model_route: str | None = field(default=None, repr=False)
    use_catalog: bool = False


class CloudCodexPool:
    def __init__(self, store, yuanrong, config, resources):
        self.store, self.yuanrong, self.resources = store, yuanrong, resources
        self.options = dict(config.codex_provider)
        self.storage = Path(config.state_root) / "codex-providers"
        self.namespace, self.runtime = config.namespace, config.runtime
        self.ready_timeout = config.ready_timeout
        self.idle_seconds = float(self.options.get("idle_seconds", 300))
        self._locks = defaultdict(asyncio.Lock)
        self._holds: dict[tuple[str, str, str], dict[str, asyncio.Event]] = {}
        self._brokers = {}
        self._ready_operations: set[str] = set()
        self.ready_check = None
        self.idle_check = None
        _private_directory(self.storage)
        ensure_bindings_table(store)
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS codex_session_owners (
                       binding_id TEXT NOT NULL, session_id TEXT NOT NULL, directory TEXT NOT NULL,
                       PRIMARY KEY (binding_id, session_id))""")

    def admits(self, account):
        return account["account_id"] in self.options["account_allowlist"]

    def uses_session_models(self, account):
        canary = self.options.get("session_model_canary")
        return canary is None or account["account_id"] in canary["accounts"]

    def _current(self, account):
        row = self.store.by_user(account["account_id"])
        if (not self.admits(row) or row["state"] != "ALLOCATED"
                or any(row[key] != account[key] for key in ("environment_id", "epoch", "workspace", "instance_id"))):
            raise PermissionError("Codex request is outside the admitted Worker")
        return row

    @staticmethod
    def _key(row):
        return row["account_id"], row["project_id"], row["provider"]

    @staticmethod
    def _default_key(account):
        return account["account_id"], "@" + account["environment_id"], PROVIDER

    @staticmethod
    def _device_key(account, runtime_id):
        if not isinstance(runtime_id, str) or not DEVICE_ID.fullmatch(runtime_id):
            raise ValueError("Invalid Codex device ID")
        return account["account_id"], device_prefix(account) + runtime_id, PROVIDER

    def _profile(self, account):
        profile = {
            "image": self.options["image"], "runtime": self.runtime, "user": account["profile"]["runtime_user"],
            "account_workspace": account["workspace"], "shared_runtime": self.options["shared_runtime"],
            "cpu": self.options.get("cpu", 1000), "memory": self.options.get("memory", 1024),
            "physical_verification": True,
        }
        if self.uses_session_models(account):
            profile["session_models"] = True
            if canary := self.options.get("session_model_canary"):
                profile["image"] = canary["image"]
        return profile

    @staticmethod
    def _source(account):
        source = Path(account["workspace"]) / "agent/workspace"
        if not source.is_dir() or source.resolve(strict=True) != source:
            raise PermissionError("Codex account workspace is unavailable")
        return source

    def _project(self, account, directory):
        path = PurePosixPath(directory)
        if str(path) != directory or path == PROJECT_ROOT or not path.is_relative_to(PROJECT_ROOT) or ".." in path.parts:
            raise PermissionError("Codex needs an authorized project workspace")
        source = self._source(account)
        project = source.joinpath(*path.relative_to(PROJECT_ROOT).parts)
        if not project.is_dir() or project.resolve(strict=True) != project:
            raise PermissionError("Codex project workspace is unavailable")
        return source

    @staticmethod
    def _insert(db, key, binding_id, source, profile, name=None):
        db.execute("""INSERT INTO provider_bindings
            (account_id, project_id, provider, binding_id, directory, project_source, profile_json,
             generation, operation_id, state, instance_id, used_at, display_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, 'NEW', NULL, ?, ?)""",
            (*key, binding_id, str(PROJECT_ROOT), str(source), json.dumps(profile),
             secrets.token_hex(16), time.time(), name))

    def runtime_template(self, account):
        template = {"runtime_profile_id": PROFILE_ID, "cpu": self.options.get("cpu", 1000),
                    "memory": self.options.get("memory", 1024),
                    "available": account["state"] == "ALLOCATED" and self.admits(account)}
        if not self.uses_session_models(account):
            template["supports_model_selection"] = True
        elif template["available"]:
            row = read_binding(self.store, self._default_key(account))
            template["default_session_models"] = row is None or json.loads(row["profile_json"]).get("session_models") is True
        return template

    def _public_device(self, row):
        profile = json.loads(row["profile_json"])
        lock = self._locks.get(self._key(row))
        if row["state"] in {"DELETING", "RETIRING_UNDISPATCHED"}:
            state = "reconciling"
        elif lock is not None and lock.locked():
            state = "starting"
        elif row["state"] == "ALLOCATED":
            state = "ready" if row["operation_id"] in self._ready_operations else "unknown"
        elif row["state"] == "NEW":
            state = "idle" if row["generation"] > 1 else "not_started"
        else:
            state = "unknown"
        return {
            "runtime_id": row["binding_id"], "display_name": row["display_name"], "state": state,
            "available": self.admits(row), "model_id": profile.get("model_id"),
            "session_models": profile.get("session_models") is True,
        }

    def account_devices(self, account):
        if not self.admits(account):
            return []
        prefix = device_prefix(account)
        with self.store.connect() as db:
            rows = db.execute("""SELECT * FROM provider_bindings
                WHERE account_id=? AND provider=? AND substr(project_id, 1, ?)=? AND display_name IS NOT NULL
                ORDER BY display_name""", (account["account_id"], PROVIDER, len(prefix), prefix)).fetchall()
        return [self._public_device(row) for row in rows]

    def register_device(self, account, name, create_token, model_id=None):
        current = self._current(account)
        validate_registration(name, create_token)
        session_models = self.uses_session_models(current)
        if model_id is not None:
            if session_models:
                raise ValueError("Codex device initialization takes no model")
            validate_device_model_id(model_id)
        prefix = device_prefix(current)
        runtime_id = uuid.uuid5(uuid.NAMESPACE_URL, json.dumps((current["account_id"], prefix, PROVIDER, create_token))).hex
        key = self._device_key(current, runtime_id)

        def insert(db):
            profile = self._profile(current)
            if model_id is not None:
                profile["requested_model_id"] = model_id
            self._insert(db, key, runtime_id, self._source(current), profile, name)

        row = register_named_binding(self.store, current, key, runtime_id, name, insert)
        if not session_models and json.loads(row["profile_json"]).get("requested_model_id") != model_id:
            raise RuntimeDeviceNameConflict("RUNTIME_DEVICE_NAME_CONFLICT")
        return self._public_device(row)

    def _named_binding(self, account, runtime_id):
        row = read_binding(self.store, self._device_key(account, runtime_id))
        if (row is None or row["binding_id"] != runtime_id or row["display_name"] is None
                or row["project_source"] != str(self._source(account)) or row["directory"] != str(PROJECT_ROOT)):
            raise PermissionError("Codex device does not belong to this account environment")
        return row

    def device_runtime(self, account, runtime_id):
        return self._public_device(self._named_binding(self._current(account), runtime_id))

    def device_model_id(self, account, runtime_id):
        row = self._named_binding(self._current(account), runtime_id)
        profile = json.loads(row["profile_json"])
        return profile.get("model_id", profile.get("requested_model_id"))

    @staticmethod
    def _model_profile(model):
        profile = {"model_name": model.name, "model_revision": model.revision}
        if model.context_window is not None:
            profile["context_window"] = model.context_window
        return profile

    @staticmethod
    def _require_model(row, model):
        profile = json.loads(row["profile_json"])
        if (profile.get("model_revision") != model.revision
                or profile.get("context_window") != model.context_window):
            raise CodexRuntimeModelMismatch("Codex workspace or model differs from its persistent Worker binding")

    def _binding(self, key, account, directory, model):
        source = self._project(account, directory)
        row = read_binding(self.store, key)
        if row is None:
            with self.store.connect() as db:
                profile = self._profile(account)
                if not profile.get("session_models"):
                    profile.update(self._model_profile(model))
                self._insert(db, key, secrets.token_hex(16), source, profile)
            row = read_binding(self.store, key)
        if (row["directory"], row["project_source"]) != (str(PROJECT_ROOT), str(source)):
            raise PermissionError("Codex workspace or model differs from its persistent Worker binding")
        if not json.loads(row["profile_json"]).get("session_models"):
            self._require_model(row, model)
        return row

    async def prepare_device(self, account, runtime_id, model=None, model_id=None):
        key = self._device_key(account, runtime_id)
        async with self._locks[key]:
            current = self._current(account)
            row = self._named_binding(current, runtime_id)
            profile = json.loads(row["profile_json"])
            if profile.get("session_models"):
                if model is not None or model_id is not None:
                    raise CodexRuntimeModelMismatch("Codex device starts without a session model")
            else:
                row = self._prepare_legacy_device(current, row, profile, model, model_id)
            row, _ = await self._ensure_lease(row, model)
            self._current(account)
            self._touch(row)

    def _prepare_legacy_device(self, account, row, profile, model, model_id):
        if model is None or not model_id or profile.get("requested_model_id", model_id) != model_id:
            raise CodexRuntimeModelMismatch("Codex device model selection differs")
        if "model_id" not in profile:
            profile |= self._model_profile(model) | {"model_id": model_id}
            with self.store.guard_binding({"authority": account["authority"], "user_id": row["account_id"]}, account) as db:
                updated = db.execute("""UPDATE provider_bindings SET profile_json=?
                    WHERE binding_id=? AND state='NEW' AND operation_id=? AND profile_json=?""",
                    (json.dumps(profile), row["binding_id"], row["operation_id"], row["profile_json"]))
                if updated.rowcount != 1:
                    raise EnvironmentUnavailable("Codex device model configuration changed")
            row = read_binding(self.store, self._key(row))
        if profile["model_id"] != model_id:
            raise CodexRuntimeModelMismatch("Codex device model selection differs")
        self._require_model(row, model)
        return row

    def _bind_session(self, row, session_id, directory):
        key = row["binding_id"], session_id
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("""SELECT 1 FROM codex_session_owners AS owner
                JOIN provider_bindings AS binding ON owner.binding_id=binding.binding_id
                WHERE binding.account_id=? AND binding.provider=? AND owner.session_id=? AND owner.binding_id<>?""",
                (row["account_id"], PROVIDER, session_id, row["binding_id"])).fetchone():
                raise PermissionError("Codex session belongs to another runtime device")
            db.execute("INSERT OR IGNORE INTO codex_session_owners VALUES (?, ?, ?)", (*key, directory))
            saved = db.execute("SELECT directory FROM codex_session_owners WHERE binding_id=? AND session_id=?",
                               key).fetchone()
            if saved[0] != directory:
                raise PermissionError("Codex session belongs to another project")

    def _transition(self, row, state, *, instance_id=None, recycled=False):
        with self.store.connect() as db:
            result = db.execute("""UPDATE provider_bindings SET state=?, instance_id=?, generation=?,
                operation_id=?, used_at=? WHERE binding_id=? AND generation=? AND state=?""",
                (state, instance_id, row["generation"] + int(recycled),
                 secrets.token_hex(16) if recycled else row["operation_id"], time.time(),
                 row["binding_id"], row["generation"], row["state"]))
            if result.rowcount != 1:
                raise EnvironmentUnavailable("Codex allocation changed")
        return read_binding(self.store, self._key(row))

    def _generation(self, row):
        return self.storage / row["binding_id"] / row["operation_id"]

    def _plan(self, row):
        profile = json.loads(row["profile_json"])
        generation = self._generation(row)
        state, private = generation.parent / "state", generation.parent / "private"
        # YuanRong's native Python initializes before executing our command.
        for path in (generation.parent, state, state / "home", private, generation):
            _private_directory(path)
        capability_file = private / row["operation_id"]
        capability = (private_initial_file(capability_file, secrets.token_urlsafe(32).encode())
                      if row["state"] == "NEW" else read_private_file(capability_file))
        definition = {
            "version": 2, "binding_id": row["binding_id"], "image": profile["image"], "user": profile["user"],
            "account_workspace": profile["account_workspace"], "project_source": row["project_source"],
            "project_target": row["directory"],
        }
        anchor = {**definition, "image": profile.get("initial_image", profile["image"])}
        for path, document in ((generation.parent / "scope.json", anchor),
                               (generation / "scope.json", {**definition, "shared_runtime": profile["shared_runtime"]})):
            encoded = json.dumps(document, sort_keys=True).encode()
            if private_initial_file(path, encoded) != encoded:
                raise EnvironmentUnavailable("Codex physical scope changed")
        if profile.get("context_window") is not None:
            catalog = native_model_catalog(profile["model_name"], profile["context_window"])
            if private_initial_file(generation / CATALOG_FILENAME, catalog) != catalog:
                raise EnvironmentUnavailable("Codex native model catalog changed")
        mounts = [
            {"source": row["project_source"], "target": row["directory"], "readonly": False},
            {"source": str(state), "target": "/state", "readonly": False},
            {"source": str(generation), "target": IDENTITY_TARGET, "readonly": True},
            {"source": profile["shared_runtime"], "target": RUNTIME_TARGET, "readonly": True},
        ]
        spec = {
            "sandbox_type": "docker", "runtime": profile["runtime"], "cpu": profile["cpu"], "memory": profile["memory"],
            "rootfs": {"imageurl": profile["image"], "user": profile["user"], "ports": [str(NATIVE_PORT)]},
            "cmds": [["/bin/sh", "-ec", _SESSION_MODEL_COMMAND if profile.get("session_models") else _COMMAND]],
        }
        return "codex-" + row["operation_id"], str(state), spec, mounts, capability

    def _claim(self, row, plan):
        _, workspace, spec, _, _ = plan
        return {"workspace": workspace, "identity": str(self._generation(row)),
                "image": spec["rootfs"]["imageurl"], "user": spec["rootfs"]["user"], "instance_id": row["instance_id"]}

    async def _ready(self, row, plan):
        async def reachable():
            try:
                host = await self.resources.confirm_codex_address(**self._claim(row, plan))
                session_models = json.loads(row["profile_json"]).get("session_models") is True
                lease = CodexLease(host, plan[-1].decode("ascii"), session_models=session_models)
                return lease if await self.ready_check(lease) else None
            except RuntimeError:
                return None

        async def confirm_unreported(info):
            return matches_allocation(plan, info) and bool(await reachable())

        async with asyncio.timeout(self.ready_timeout):
            info = await self.yuanrong.wait_until_running(row["instance_id"], confirm_unreported_ready=confirm_unreported)
            if not matches_allocation(plan, info):
                raise EnvironmentUnavailable("Codex allocation ownership differs")
            while not (lease := await reachable()):
                await asyncio.sleep(0.25)
            return lease

    async def _fence_unready(self, row, plan):
        instance = row["instance_id"]
        if (not await self.yuanrong.instance_absent(instance)
                and not matches_allocation(plan, await self.yuanrong.get_agent_info(instance))):
            raise EnvironmentUnavailable("Codex allocation ownership changed before fencing")
        if not await self.resources.fence_undispatched_codex(**self._claim(row, plan)):
            return row
        return self._transition(row, "RETIRING_UNDISPATCHED", instance_id=instance)

    async def _retire_undispatched(self, row, plan):
        instance = row["instance_id"]
        # Revalidate the physical fence when resuming after a Gateway restart.
        if not await self.resources.fence_undispatched_codex(**self._claim(row, plan)):
            raise EnvironmentUnavailable("Codex undispatched allocation fence is missing")
        if not await self.yuanrong.instance_absent(instance):
            if not matches_allocation(plan, await self.yuanrong.get_agent_info(instance)):
                raise EnvironmentUnavailable("Codex allocation ownership changed before retirement")
            if not await self.yuanrong.retire_undispatched_codex(instance):
                logger.warning("Codex kill accepted with frontend cleanup pending: instance_id=%s", instance)
            elif not await self.yuanrong.instance_absent(instance):
                raise EnvironmentUnavailable("Codex undispatched allocation deletion is pending")
        return await self._advance_generation(row)

    async def _finish_retirement(self, row, plan):
        await self.resources.confirm_deleted(**self._claim(row, plan))
        return await self._advance_generation(row)

    async def _advance_generation(self, row):
        self._ready_operations.discard(row["operation_id"])
        broker = self._brokers.pop(row["operation_id"], None)
        if broker:
            await asyncio.to_thread(broker.close)
        previous = self._generation(row)
        updated = self._transition(row, "NEW", recycled=True)
        try:
            (previous.parent / "private" / row["operation_id"]).unlink(missing_ok=True)
            shutil.rmtree(previous)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Codex generation cleanup deferred: %s", type(exc).__name__)
        return updated

    def _touch(self, row):
        with self.store.connect() as db:
            db.execute("UPDATE provider_bindings SET used_at=? WHERE binding_id=? AND generation=?",
                       (time.time(), row["binding_id"], row["generation"]))

    async def _ensure_lease(self, row, model):
        key = self._key(row)
        plan = self._plan(row)
        if row["state"] == "RETIRING_UNDISPATCHED":
            row = await self._retire_undispatched(row, plan)
            plan = self._plan(row)
        if row["state"] == "DELETING":
            if not await self.yuanrong.instance_absent(row["instance_id"]):
                raise EnvironmentUnavailable("Codex deletion is pending")
            row = await self._finish_retirement(row, plan)
            plan = self._plan(row)
        generation = row["operation_id"]
        session_models = json.loads(row["profile_json"]).get("session_models") is True
        if generation not in self._brokers:
            self._brokers[generation] = CodexModelBroker(self._generation(row), None if session_models else model)
        if row["state"] != "ALLOCATED":
            env = {"HOME": "/state/home", "CODEX_CAPABILITY_DIGEST": hashlib.sha256(plan[-1]).hexdigest()}
            if session_models:
                env["CODEX_SESSION_MODELS"] = "1"
            else:
                env["CODEX_SELECTED_MODEL"] = model.name
            row = await allocate_provider(self.yuanrong, self.namespace, row, plan, self._transition,
                                          env_vars=env, provider_name="Codex")
        self._ready_operations.discard(row["operation_id"])
        try:
            lease = await self._ready(row, plan)
        except (TimeoutError, YuanrongAgentApiError):
            if not self._holds.get(key):
                try:
                    await self._fence_unready(row, plan)
                except (EnvironmentUnavailable, YuanrongAgentApiError, OSError, RuntimeError, ValueError) as exc:
                    logger.warning("Codex failed allocation fencing deferred: %s", type(exc).__name__)
            raise
        self._ready_operations.add(row["operation_id"])
        return row, lease

    @asynccontextmanager
    async def hold(self, account, session_id, directory, model, *, runtime_id=None):
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", session_id):
            raise ValueError("Invalid Codex session")
        key = self._device_key(account, runtime_id) if runtime_id is not None else self._default_key(account)
        prior = self._holds.get(key, {}).get(session_id)
        if prior is not None:
            async with asyncio.timeout(5):
                await prior.wait()
        async with self._locks[key]:
            if session_id in self._holds.get(key, {}):
                raise EnvironmentUnavailable("Codex session already has a transport")
            current = self._current(account)
            if runtime_id is None:
                row = self._binding(key, current, directory, model)
            else:
                self._project(current, directory)
                row = self._named_binding(current, runtime_id)
                if not json.loads(row["profile_json"]).get("session_models"):
                    self._require_model(row, model)
            self._bind_session(row, session_id, directory)
            row, lease = await self._ensure_lease(row, model)
            self._current(account)
            if lease.session_models:
                route = secrets.token_hex(16)
                use_catalog = model.context_window is not None
                if use_catalog:
                    private_initial_file(self._generation(row) / f"catalog-{route}.json",
                                         native_model_catalog(model.name, model.context_window))
                self._brokers[row["operation_id"]].register_route(route, model)
                lease = replace(lease, model_route=route, use_catalog=use_catalog)
            self._holds.setdefault(key, {})[session_id] = asyncio.Event()
        try:
            yield lease
        finally:
            async with self._locks[key]:
                if lease.model_route:
                    self._brokers[row["operation_id"]].unregister_route(lease.model_route)
                    if lease.use_catalog:
                        try:
                            (self._generation(row) / f"catalog-{lease.model_route}.json").unlink(missing_ok=True)
                        except OSError as exc:
                            logger.warning("Codex session catalog cleanup deferred: %s", type(exc).__name__)
                live = self._holds[key]
                live.pop(session_id).set()
                if not live:
                    del self._holds[key]
                self._touch(row)

    async def reclaim_idle(self):
        cutoff = time.time() - self.idle_seconds
        with self.store.connect() as db:
            keys = [tuple(row) for row in db.execute("""SELECT account_id, project_id, provider FROM provider_bindings
                WHERE provider=? AND (state IN ('DELETING', 'RETIRING_UNDISPATCHED')
                                  OR (state='ALLOCATED' AND used_at<=?))""", (PROVIDER, cutoff))]
        for key in keys:
            try:
                async with self._locks[key]:
                    row = read_binding(self.store, key)
                    if (row is None or key in self._holds
                            or row["state"] not in ("DELETING", "ALLOCATED", "RETIRING_UNDISPATCHED")):
                        continue
                    if row["state"] == "ALLOCATED" and row["used_at"] > cutoff:
                        continue
                    plan = self._plan(row)
                    if row["state"] == "RETIRING_UNDISPATCHED":
                        await self._retire_undispatched(row, plan)
                        continue
                    instance = row["instance_id"]
                    absent = await self.yuanrong.instance_absent(instance)
                    if row["state"] == "ALLOCATED":
                        if absent:
                            address = None
                        else:
                            try:
                                address = await self.resources.confirm_codex_address(**self._claim(row, plan))
                            except RuntimeError:
                                address = None
                        if address is None and row["used_at"] <= time.time() - self.ready_timeout:
                            row = await self._fence_unready(row, plan)
                            if row["state"] == "RETIRING_UNDISPATCHED":
                                await self._retire_undispatched(row, plan)
                                continue
                        if address is None and not absent:
                            continue
                    if not absent:
                        if not matches_allocation(plan, await self.yuanrong.get_agent_info(instance)):
                            raise EnvironmentUnavailable("Codex allocation ownership changed before deletion")
                        if row["state"] == "ALLOCATED":
                            if not await self.idle_check(CodexLease(address, plan[-1].decode("ascii"))):
                                continue
                            row = self._transition(row, "DELETING", instance_id=instance)
                        await self.yuanrong.delete_sandbox(instance)
                        if not await self.yuanrong.instance_absent(instance):
                            continue
                    await self._finish_retirement(row, plan)
            except (EnvironmentUnavailable, YuanrongAgentApiError, OSError, RuntimeError, ValueError) as exc:
                logger.warning("Codex idle reclaim deferred: %s", type(exc).__name__)

    async def close(self):
        for broker in self._brokers.values():
            await asyncio.to_thread(broker.close)
        self._brokers.clear()
        self._ready_operations.clear()
