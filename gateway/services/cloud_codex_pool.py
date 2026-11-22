"""Stable Codex volumes and leases through the existing YuanRong client."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import time

from gateway.common.managed_codex import IDENTITY_TARGET, NATIVE_PORT
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
)
from gateway.services.managed_codex_models import CATALOG_FILENAME, CodexModelBroker, native_model_catalog


logger = logging.getLogger(__name__)
PROVIDER = "codex"
PROJECT_ROOT = PurePosixPath("/data/agent/workspace")
_COMMAND = (
    "python3.11 -B /opt/codex-candidate/model_bridge.py --socket /run/codex/model.sock "
    '--model "$CODEX_SELECTED_MODEL" --port 17543 & '
    "exec python3.11 -B /opt/codex-candidate/stdio_bridge.py"
)


@dataclass(frozen=True)
class CodexLease:
    address: str
    capability: str = field(repr=False)


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

    def _current(self, account):
        row = self.store.by_user(account["account_id"])
        if (not self.admits(row) or row["state"] != "ALLOCATED"
                or any(row[key] != account[key] for key in ("environment_id", "epoch", "workspace", "instance_id"))):
            raise PermissionError("Codex request is outside the admitted Worker")
        return row

    @staticmethod
    def _key(row):
        return row["account_id"], row["project_id"], row["provider"]

    def _binding(self, key, account, directory, model):
        path = PurePosixPath(directory)
        if str(path) != directory or path == PROJECT_ROOT or not path.is_relative_to(PROJECT_ROOT) or ".." in path.parts:
            raise PermissionError("Codex needs an authorized project workspace")
        source = Path(account["workspace"]) / "agent/workspace"
        project = source.joinpath(*path.relative_to(PROJECT_ROOT).parts)
        if not project.is_dir() or project.resolve(strict=True) != project:
            raise PermissionError("Codex project workspace is unavailable")
        row = read_binding(self.store, key)
        if row is None:
            profile = {
                "image": self.options["image"], "runtime": self.runtime, "user": account["profile"]["runtime_user"],
                "account_workspace": account["workspace"], "shared_runtime": self.options["shared_runtime"],
                "cpu": self.options.get("cpu", 1000), "memory": self.options.get("memory", 1024),
                "model_name": model.name, "model_revision": model.revision, "physical_verification": True,
            }
            if model.context_window is not None:
                profile["context_window"] = model.context_window
            with self.store.connect() as db:
                db.execute("""INSERT INTO provider_bindings VALUES
                    (?, ?, ?, ?, ?, ?, ?, 1, ?, 'NEW', NULL, ?)""",
                    (*key, secrets.token_hex(16), str(PROJECT_ROOT), str(source), json.dumps(profile),
                     secrets.token_hex(16), time.time()))
            row = read_binding(self.store, key)
        profile = json.loads(row["profile_json"])
        if ((row["directory"], row["project_source"]) != (str(PROJECT_ROOT), str(source))
                or profile["model_revision"] != model.revision
                or profile.get("context_window") != model.context_window):
            raise PermissionError("Codex workspace or model differs from its persistent Worker binding")
        return row

    def _bind_session(self, row, session_id, directory):
        key = row["binding_id"], session_id
        with self.store.connect() as db:
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
            "cmds": [["/bin/sh", "-ec", _COMMAND]],
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
                lease = CodexLease(host, plan[-1].decode("ascii"))
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

    @asynccontextmanager
    async def hold(self, account, session_id, directory, model):
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", session_id):
            raise ValueError("Invalid Codex session")
        key = account["account_id"], "@" + account["environment_id"], PROVIDER
        prior = self._holds.get(key, {}).get(session_id)
        if prior is not None:
            async with asyncio.timeout(5):
                await prior.wait()
        async with self._locks[key]:
            if session_id in self._holds.get(key, {}):
                raise EnvironmentUnavailable("Codex session already has a transport")
            row = self._binding(key, self._current(account), directory, model)
            self._bind_session(row, session_id, directory)
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
            if generation not in self._brokers:
                self._brokers[generation] = CodexModelBroker(self._generation(row), model)
            if row["state"] != "ALLOCATED":
                env = {"HOME": "/state/home", "CODEX_SELECTED_MODEL": model.name,
                       "CODEX_CAPABILITY_DIGEST": hashlib.sha256(plan[-1]).hexdigest()}
                row = await allocate_provider(self.yuanrong, self.namespace, row, plan, self._transition,
                                              env_vars=env, provider_name="Codex")
            try:
                lease = await self._ready(row, plan)
            except (TimeoutError, YuanrongAgentApiError):
                if not self._holds.get(key):
                    try:
                        await self._fence_unready(row, plan)
                    except (EnvironmentUnavailable, YuanrongAgentApiError, OSError, RuntimeError, ValueError) as exc:
                        logger.warning("Codex failed allocation fencing deferred: %s", type(exc).__name__)
                raise
            self._current(account)
            self._holds.setdefault(key, {})[session_id] = asyncio.Event()
        try:
            yield lease
        finally:
            async with self._locks[key]:
                live = self._holds[key]
                live.pop(session_id).set()
                if not live:
                    del self._holds[key]
                with self.store.connect() as db:
                    db.execute("UPDATE provider_bindings SET used_at=? WHERE binding_id=? AND generation=?",
                               (time.time(), row["binding_id"], row["generation"]))

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
