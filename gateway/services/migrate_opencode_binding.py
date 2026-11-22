"""Offline, compare-and-set image migration for an idle Provider binding."""

import argparse
import json
import re
from pathlib import Path

from gateway.common.opencode_runtime import runtime_source
from gateway.common.runtime_device import DEVICE_ID, device_prefix
from gateway.extensions.cloud_workspace.config import CloudConfig
from gateway.services.cloud_environments import EnvironmentStore, EnvironmentUnavailable


def _migrate_row(db, storage, row, expected_image, image, runtime, session_models):
    label = "Codex" if row["provider"] == "codex" else "OpenCode"
    binding_id = row["binding_id"]
    profile = json.loads(row["profile_json"])
    if profile["image"] != expected_image:
        raise EnvironmentUnavailable(f"{label} binding image changed")
    if not profile.get("physical_verification"):
        raise EnvironmentUnavailable(f"{label} migration requires existing physical confirmation")
    # Reclaim commits NEW with a fresh operation only after confirming physical deletion.
    operation = storage / binding_id / row["operation_id"]
    if row["state"] != "NEW" or row["instance_id"] is not None or operation.exists() or operation.is_symlink():
        raise EnvironmentUnavailable(f"{label} binding must be reclaimed with an unused generation")
    changed = {**profile, "initial_image": profile.get("initial_image", expected_image), "image": image}
    changed.pop("shared_runtime", None)
    if runtime is not None:
        changed["shared_runtime"] = runtime
    if session_models:
        changed["session_models"] = True
        for field in ("requested_model_id", "model_id", "model_revision", "model_name", "context_window"):
            changed.pop(field, None)
    if db.execute("""UPDATE provider_bindings SET profile_json=?
            WHERE binding_id=? AND generation=? AND operation_id=? AND state='NEW' AND profile_json=?""",
            (json.dumps(changed, sort_keys=True), binding_id, row["generation"], row["operation_id"],
             row["profile_json"])).rowcount != 1:
        raise EnvironmentUnavailable(f"{label} binding changed during migration")
    return {"binding_id": binding_id, "generation": row["generation"], "image": image}


def migrate_codex_account(store, config, account_id, expected_images):
    """Move all fixed Codex bindings of one admitted canary account in one offline transaction."""
    options = config.codex_provider
    canary = options.get("session_model_canary") if options else None
    if not canary or account_id not in canary["accounts"] or account_id not in options["account_allowlist"]:
        raise PermissionError("Codex account is not in the session model canary")
    image = canary["image"]
    if (not expected_images or any(not DEVICE_ID.fullmatch(binding_id)
            for binding_id in expected_images) or any(not re.fullmatch(r"sha256:[a-f0-9]{64}", value)
            for value in (image, *expected_images.values()))):
        raise ValueError("Codex migration requires explicit binding IDs and pinned image digests")
    runtime = runtime_source(options["shared_runtime"])
    storage = config.state_root / "codex-providers"
    if store._writer is not None:
        raise EnvironmentUnavailable("migration requires an offline environment store")
    store.acquire_writer()
    try:
        account = store.by_user(account_id)
        default_key = "@" + account["environment_id"]
        prefix = device_prefix(account)
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("""SELECT * FROM provider_bindings WHERE account_id=? AND provider='codex'
                AND (project_id=? OR substr(project_id, 1, ?)=?)""",
                (account_id, default_key, len(prefix), prefix)).fetchall()
            fixed = [row for row in rows if json.loads(row["profile_json"]).get("session_models") is not True]
            if {row["binding_id"] for row in fixed} != set(expected_images):
                raise EnvironmentUnavailable("Codex fixed bindings differ from the migration plan")
            return [_migrate_row(db, storage, row, expected_images[row["binding_id"]], image, runtime, True)
                    for row in fixed]
    finally:
        store.close()


def migrate(store, storage: Path, binding_id: str, expected_image: str, image: str, shared_runtime: str | None,
            *, provider="opencode", session_models=False):
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
    if session_models and provider != "codex":
        raise ValueError("Session model migration requires a named Codex device")

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
            if session_models and row["display_name"] is None:
                raise ValueError("Session model migration requires a named Codex device")
            return _migrate_row(db, storage, row, expected_image, image, runtime, session_models)
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Gateway deployment config for the target image")
    parser.add_argument("--binding-id", required=True)
    parser.add_argument("--expected-image", required=True)
    parser.add_argument("--provider", choices=("opencode", "codex"), default="opencode")
    parser.add_argument("--session-models", action="store_true", help="Use the new named Codex image's session model routing")
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
                     args.expected_image, target["image"], target.get("shared_runtime"), provider=args.provider,
                     session_models=args.session_models)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
