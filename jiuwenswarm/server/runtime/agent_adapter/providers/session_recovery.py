"""Private Provider bindings; Runtime remains the sole execution owner.

Keep native data across adapter disposal. Never replay rendered Swarm history
as native context, guess a native ID, or fall back to creating another session.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import tempfile
from pathlib import Path


NAMESPACES = {"opencode": ".opencode", "codex": ".codex-direct", "claude": ".claude-direct"}


def revision(value: dict) -> str:
    """Fingerprint settings without persisting credentials in the binding."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _file(provider: str, session_id: str) -> Path:
    from jiuwenswarm.common.utils import get_agent_sessions_dir
    if provider not in NAMESPACES or not isinstance(session_id, str) or not session_id:
        raise ValueError("Invalid Provider session binding identity")
    key = hashlib.sha256(f"{provider}\0{session_id}".encode("utf-8")).hexdigest()
    return get_agent_sessions_dir() / ".provider-bindings" / f"{key}.json"


def _root(provider: str, value: str) -> Path:
    from jiuwenswarm.common.utils import get_agent_sessions_dir
    parent = (get_agent_sessions_dir() / NAMESPACES[provider]).resolve()
    path = Path(value)
    if (not path.is_absolute() or path.is_symlink() or not path.is_dir()
            or path.resolve().parent != parent):
        raise ValueError("Provider recovery data is missing or outside its private namespace")
    return path.resolve()


def load(provider: str, session_id: str, directory: str) -> dict | None:
    file = _file(provider, session_id)
    if not file.exists():
        return None
    try:
        if file.is_symlink() or file.stat().st_size > 65536:
            raise ValueError("Invalid binding file")
        data = json.loads(file.read_text(encoding="utf-8"))
        if (data["version"] != 1 or data["provider"] != provider
                or data["session_id"] != session_id or data["principal"] != getpass.getuser()
                or data["directory"] != str(Path(directory).resolve())
                or data["permission"] not in {"default", "full_access"}
                or not isinstance(data["native_id"], str) or not data["native_id"]
                or not isinstance(data["model_revision"], str)
                or not isinstance(data["settings_revision"], str)):
            raise ValueError("Binding identity mismatch")
        data["root"] = str(_root(provider, data["root"]))
        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("Provider recovery binding is invalid, missing data, or belongs to another workspace/user") from None


def save(provider: str, session_id: str, *, root: Path, directory: str,
         native_id: str, model_revision: str, settings_revision: str,
         permission: str) -> None:
    file = _file(provider, session_id)
    data = {"version": 1, "provider": provider, "session_id": session_id,
            "principal": getpass.getuser(), "root": str(_root(provider, str(root))),
            "directory": str(Path(directory).resolve()), "native_id": native_id,
            "model_revision": model_revision, "settings_revision": settings_revision,
            "permission": permission}
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix="binding-", suffix=".tmp", dir=file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, file)
    finally:
        Path(temporary).unlink(missing_ok=True)


def settings_revision(settings: dict) -> str:
    # Installed executable locations may change during upgrade. The actual
    # Provider configuration must not silently change for an existing session.
    return revision({key: value for key, value in settings.items() if key not in {"cli_path", "enabled"}})


def require_settings(binding: dict, settings: dict) -> None:
    if binding["settings_revision"] != settings_revision(settings):
        raise ValueError("Provider configuration changed; restore the original settings before resuming")
