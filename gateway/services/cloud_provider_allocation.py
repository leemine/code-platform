"""YuanRong allocation and ownership checks used by managed Providers."""
import os
import stat
import tempfile
from pathlib import Path

from gateway.services.cloud_environments import EnvironmentUnavailable


def read_private_file(path: Path) -> bytes:
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError("Provider configuration must be private")
        return stream.read()


def private_initial_file(path: Path, content: bytes) -> bytes:
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
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    return read_private_file(path)


def ensure_bindings_table(store):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            CREATE TABLE IF NOT EXISTS provider_bindings (
                account_id TEXT NOT NULL, project_id TEXT NOT NULL, provider TEXT NOT NULL,
                binding_id TEXT NOT NULL UNIQUE, directory TEXT NOT NULL, project_source TEXT NOT NULL,
                profile_json TEXT NOT NULL, generation INTEGER NOT NULL, operation_id TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL, instance_id TEXT, used_at REAL NOT NULL, display_name TEXT,
                PRIMARY KEY (account_id, project_id, provider)
            )
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(provider_bindings)")}
        if "display_name" not in columns:
            db.execute("ALTER TABLE provider_bindings ADD COLUMN display_name TEXT")
        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS named_opencode_device
            ON provider_bindings(account_id, display_name)
            WHERE provider = 'opencode' AND display_name IS NOT NULL
        """)

        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS named_codex_device
            ON provider_bindings(account_id, display_name)
            WHERE provider = 'codex' AND display_name IS NOT NULL
        """)


class RuntimeDeviceNameConflict(ValueError):
    """A device name is already registered for the same Provider."""


def register_named_binding(store, account, key, binding_id, name, insert):
    with store.guard_binding({"authority": account["authority"], "user_id": account["account_id"]}, account) as db:
        row = db.execute("SELECT * FROM provider_bindings WHERE binding_id=?", (binding_id,)).fetchone()
        if row is not None and tuple(row[field] for field in ("account_id", "project_id", "provider")) == key and row["display_name"] == name:
            return dict(row)
        if row is not None or db.execute(
            "SELECT 1 FROM provider_bindings WHERE account_id=? AND provider=? AND display_name=?",
            (key[0], key[2], name),
        ).fetchone():
            raise RuntimeDeviceNameConflict("RUNTIME_DEVICE_NAME_CONFLICT")
        insert(db)
    return read_binding(store, key)


def read_binding(store, key):
    with store.connect() as db:
        row = db.execute("SELECT * FROM provider_bindings WHERE account_id=? AND project_id=? AND provider=?",
                         key).fetchone()
        return dict(row) if row else None


def matches_allocation(plan, info):
    """Confirm the reported instance owns exactly the scheduled image and mounts."""
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

async def allocate_provider(yuanrong, namespace, row, plan, transition, *, env_vars, provider_name):
    """Create once or recover an ambiguous allocation by its physical scope."""
    if row["state"] in {"CREATING", "UNKNOWN"}:
        matching = []
        for item in await yuanrong.list_agent_instances():
            if matches_allocation(plan, await yuanrong.get_agent_info(item["instance_id"])):
                matching.append(item["instance_id"])
        if len(matching) != 1:
            raise EnvironmentUnavailable(f"{provider_name} Provider creation outcome remains unknown")
        return transition(row, "ALLOCATED", instance_id=matching[0])

    name, workspace, spec, mounts, _ = plan
    row = transition(row, "CREATING")
    try:
        instance = await yuanrong.create_sandbox(
            namespace=namespace, name=name, workspace=workspace, runtime_spec=spec,
            mounts=mounts, env_vars=env_vars,
        )
    except BaseException:
        transition(row, "UNKNOWN")
        raise
    return transition(row, "ALLOCATED", instance_id=instance.sandbox_id)
