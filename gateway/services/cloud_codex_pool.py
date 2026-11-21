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
from gateway.services.managed_codex_models import CodexModelBroker


logger = logging.getLogger(__name__)
PROVIDER = "codex"
PROJECT_ROOT = PurePosixPath("/data/agent/workspace")
_COMMAND = (
    "mkdir -m 700 -p /state/codex /state/home; "
    "python3.11 -B /opt/codex-candidate/model_bridge.py --socket /run/codex/model.sock "
    '--model "$CODEX_SELECTED_MODEL" --port 17543 & '
    "exec /opt/codex/bin/codex "
    "-c 'model_provider=\"swarm\"' "
    "-c 'model_providers.swarm.name=\"Swarm model service\"' "
    "-c 'model_providers.swarm.base_url=\"http://127.0.0.1:17543/v1\"' "
    "-c 'model_providers.swarm.wire_api=\"responses\"' "
    "-c 'model_providers.swarm.requires_openai_auth=false' "
    "app-server --listen ws://0.0.0.0:18768 --ws-auth capability-token "
    '--ws-token-sha256 "$CODEX_CAPABILITY_DIGEST"'
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
        self._holds: dict[tuple[str, str, str], asyncio.Event] = {}
        self._brokers = {}
        self.ready_check = None
        self.idle_check = None
        _private_directory(self.storage)
        ensure_bindings_table(store)

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
        source = Path(account["workspace"]).joinpath(*path.relative_to("/data").parts)
        if not source.is_dir() or source.resolve(strict=True) != source:
            raise PermissionError("Codex project workspace is unavailable")
        row = read_binding(self.store, key)
        if row is None:
            profile = {
                "image": self.options["image"], "runtime": self.runtime, "user": account["profile"]["runtime_user"],
                "account_workspace": account["workspace"], "shared_runtime": self.options["shared_runtime"],
                "cpu": self.options.get("cpu", 1000), "memory": self.options.get("memory", 1024),
                "model_name": model.name, "model_revision": model.revision, "physical_verification": True,
            }
            with self.store.connect() as db:
                db.execute("""INSERT INTO provider_bindings VALUES
                    (?, ?, ?, ?, ?, ?, ?, 1, ?, 'NEW', NULL, ?)""",
                    (*key, secrets.token_hex(16), directory, str(source), json.dumps(profile),
                     secrets.token_hex(16), time.time()))
            row = read_binding(self.store, key)
        if ((row["directory"], row["project_source"]) != (directory, str(source))
                or json.loads(row["profile_json"])["model_revision"] != model.revision):
            raise PermissionError("Codex workspace or model differs from its persistent binding")
        return row

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
        for path in (generation.parent, state, state / "home", state / "codex", private, generation):
            _private_directory(path)
        capability_file = private / row["operation_id"]
        capability = (private_initial_file(capability_file, secrets.token_urlsafe(32).encode())
                      if row["state"] == "NEW" else read_private_file(capability_file))
        definition = {
            "version": 1, "binding_id": row["binding_id"], "image": profile["image"], "user": profile["user"],
            "account_workspace": profile["account_workspace"], "project_source": row["project_source"],
            "project_target": row["directory"],
        }
        anchor = {**definition, "image": profile.get("initial_image", profile["image"])}
        for path, document in ((generation.parent / "scope.json", anchor),
                               (generation / "scope.json", {**definition, "shared_runtime": profile["shared_runtime"]})):
            encoded = json.dumps(document, sort_keys=True).encode()
            if private_initial_file(path, encoded) != encoded:
                raise EnvironmentUnavailable("Codex physical scope changed")
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

    async def _finish_retirement(self, row, plan):
        await self.resources.confirm_deleted(**self._claim(row, plan))
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
        key = account["account_id"], session_id, PROVIDER
        prior = self._holds.get(key)
        if prior is not None:
            async with asyncio.timeout(5):
                await prior.wait()
        async with self._locks[key]:
            if key in self._holds:
                raise EnvironmentUnavailable("Codex session already has a transport")
            row = self._binding(key, self._current(account), directory, model)
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
                env = {"HOME": "/state/home", "CODEX_HOME": "/state/codex", "CODEX_SELECTED_MODEL": model.name,
                       "CODEX_CAPABILITY_DIGEST": hashlib.sha256(plan[-1]).hexdigest()}
                row = await allocate_provider(self.yuanrong, self.namespace, row, plan, self._transition,
                                              env_vars=env, provider_name="Codex")
            lease = await self._ready(row, plan)
            self._current(account)
            self._holds[key] = asyncio.Event()
        try:
            yield lease
        finally:
            async with self._locks[key]:
                self._holds.pop(key).set()
                with self.store.connect() as db:
                    db.execute("UPDATE provider_bindings SET used_at=? WHERE binding_id=? AND generation=?",
                               (time.time(), row["binding_id"], row["generation"]))

    async def reclaim_idle(self):
        cutoff = time.time() - self.idle_seconds
        with self.store.connect() as db:
            keys = [tuple(row) for row in db.execute("""SELECT account_id, project_id, provider FROM provider_bindings
                WHERE provider=? AND (state='DELETING' OR (state='ALLOCATED' AND used_at<=?))""", (PROVIDER, cutoff))]
        for key in keys:
            try:
                async with self._locks[key]:
                    row = read_binding(self.store, key)
                    if row is None or key in self._holds or row["state"] not in ("DELETING", "ALLOCATED"):
                        continue
                    if row["state"] == "ALLOCATED" and row["used_at"] > cutoff:
                        continue
                    plan = self._plan(row)
                    instance = row["instance_id"]
                    absent = await self.yuanrong.instance_absent(instance)
                    if not absent:
                        if not matches_allocation(plan, await self.yuanrong.get_agent_info(instance)):
                            raise EnvironmentUnavailable("Codex allocation ownership changed before deletion")
                        if row["state"] == "ALLOCATED":
                            address = await self.resources.confirm_codex_address(**self._claim(row, plan))
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
