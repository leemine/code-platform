"""Authenticate a Gateway application's permission grant for one Worker session."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile

from filelock import FileLock

from gateway.common.paths import get_root_dir

WORKER_PERMISSION_KEY = "_application_worker_permission"
WORKER_PERMISSION_KEY_FILE_ENV = "JIUWENSWARM_APPLICATION_WORKER_KEY_FILE"
WORKER_PERMISSION_KEY_FILE = ".application-worker-permission.key"


def is_worker_permission_key_path(path: Path) -> bool:
    configured = os.getenv(WORKER_PERMISSION_KEY_FILE_ENV, "").strip()
    return path.name.casefold().startswith(WORKER_PERMISSION_KEY_FILE) or (
        bool(configured) and path == Path(configured).resolve()
    )


def _read_key(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or (
            os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077)
        ):
            raise PermissionError("Worker permission signing key must be private")
        key = stream.read(33)
    if len(key) != 32:
        raise PermissionError("Invalid Worker permission signing key")
    return key


def _key(*, create: bool = False) -> bytes:
    configured = os.getenv(WORKER_PERMISSION_KEY_FILE_ENV, "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            raise PermissionError("The Worker permission key path must be absolute")
        return _read_key(path)
    path = get_root_dir() / WORKER_PERMISSION_KEY_FILE
    try:
        return _read_key(path)
    except FileNotFoundError:
        if not create:
            raise
    with FileLock(str(path) + ".lock", timeout=5):
        if not path.exists():
            pending = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as stream:
                    pending = Path(stream.name)
                    stream.write(secrets.token_bytes(32))
                pending.replace(path)
            finally:
                if pending is not None:
                    pending.unlink(missing_ok=True)
        return _read_key(path)


def _message(session_id: str, user_id: str, project_id: str, provider: str,
             turn: tuple[str, str] | None) -> bytes:
    return json.dumps(
        ["workswarm.application-worker.full-access.v2", session_id, user_id, project_id, provider, turn],
        separators=(",", ":"),
    ).encode()


def sign_full_access(session_id: str, user_id: str, project_id: str, provider: str,
                     *, turn: tuple[str, str] | None = None) -> str:
    """Sign a dispatch or its durable binding. The two signatures are distinct."""
    message = _message(session_id, user_id, project_id, provider, turn)
    return hmac.new(_key(create=turn is not None), message, hashlib.sha256).hexdigest()


def verifies_full_access(signature: object, session_id: str, user_id: str, project_id: str, provider: str,
                         *, turn: tuple[str, str] | None = None) -> bool:
    if not isinstance(signature, str) or len(signature) != 64 or not signature.isascii():
        return False
    try:
        expected = hmac.new(_key(), _message(session_id, user_id, project_id, provider, turn), hashlib.sha256).hexdigest()
    except OSError:
        return False
    return hmac.compare_digest(signature, expected)
