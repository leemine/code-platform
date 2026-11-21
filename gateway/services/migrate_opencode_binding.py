"""Offline, compare-and-set image migration for an idle Provider binding."""

import argparse
import json
import re
from pathlib import Path

from gateway.common.opencode_runtime import runtime_source
from gateway.extensions.cloud_workspace.config import CloudConfig
from gateway.services.cloud_environments import EnvironmentStore, EnvironmentUnavailable


def migrate(store, storage: Path, binding_id: str, expected_image: str, image: str, shared_runtime: str | None,
            *, provider="opencode"):
    if provider not in ("opencode", "codex"):
        raise ValueError("unsupported Provider migration")
    label = "Codex" if provider == "codex" else "OpenCode"
    if not re.fullmatch(r"[a-f0-9]{32}", binding_id):
        raise ValueError(f"invalid {label} binding ID")
    if any(not re.fullmatch(r"sha256:[a-f0-9]{64}", value) for value in (expected_image, image)):
        raise ValueError(f"{label} image migration requires pinned image digests")
    if expected_image == image:
        raise ValueError(f"{label} migration requires a different image digest")
    runtime = runtime_source(shared_runtime) if shared_runtime is not None else None
    if provider == "codex" and runtime is None:
        raise ValueError("Codex migration requires a sealed shared runtime")

    if store._writer is not None:
        raise EnvironmentUnavailable("migration requires an offline environment store")
    store.acquire_writer()
    try:
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM provider_bindings WHERE binding_id=? AND provider=?",
                             (binding_id, provider)).fetchone()
            if row is None:
                raise ValueError(f"unknown {label} binding")
            profile = json.loads(row["profile_json"])
            if profile["image"] != expected_image:
                raise EnvironmentUnavailable(f"{label} binding image changed")
            if not profile.get("physical_verification"):
                raise EnvironmentUnavailable(f"{label} migration requires existing physical confirmation")
            # NEW after reclaim is the existing commit point for confirmed deletion.
            # A planned NEW generation may already have private files or a dispatch receipt.
            operation = storage / binding_id / row["operation_id"]
            if row["state"] != "NEW" or row["instance_id"] is not None or operation.exists() or operation.is_symlink():
                raise EnvironmentUnavailable(f"{label} binding must be reclaimed with an unused generation")
            changed = {**profile, "initial_image": profile.get("initial_image", expected_image), "image": image}
            changed.pop("shared_runtime", None)
            if runtime is not None:
                changed["shared_runtime"] = runtime
            if db.execute("""UPDATE provider_bindings SET profile_json=?
                    WHERE binding_id=? AND generation=? AND operation_id=? AND state='NEW' AND profile_json=?""",
                    (json.dumps(changed, sort_keys=True), binding_id, row["generation"], row["operation_id"],
                     row["profile_json"])).rowcount != 1:
                raise EnvironmentUnavailable(f"{label} binding changed during migration")
            return {"binding_id": binding_id, "generation": row["generation"], "image": image}
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Gateway deployment config for the target image")
    parser.add_argument("--binding-id", required=True)
    parser.add_argument("--expected-image", required=True)
    parser.add_argument("--provider", choices=("opencode", "codex"), default="opencode")
    args = parser.parse_args()
    config = CloudConfig.load(args.config)
    target = config.codex_provider if args.provider == "codex" else config.opencode_provider
    if target is None:
        parser.error("the target configuration must enable the selected Provider")
    database = config.state_root / "environments.db"
    if not database.is_file() or database.is_symlink():
        parser.error("the existing environment database must be mounted")
    store = EnvironmentStore(database, config.authority, config.workspace_root,
                             config.state_root / "instance-auth", config.runtime_profile())
    result = migrate(store, config.state_root / f"{args.provider}-providers", args.binding_id,
                     args.expected_image, target["image"], target.get("shared_runtime"), provider=args.provider)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
