"""Descriptor-confined IO for WorkspaceFileAdapter, never a second file service.

The directory walk follows codeswarm's workspace_download/bound_workspace_files
pattern. The injected root is deployment authority, never a request parameter.
No resolve-then-open, symlink traversal, special files or hard-linked files.
"""
from __future__ import annotations

import base64
import errno
import mimetypes
import os
import stat
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import PurePosixPath

CHUNK_BYTES = 512 * 1024
_LIST_LIMIT = 10000
_MAX_DEPTH = 64


class WorkspaceFileError(ValueError):
    def __init__(self, message="workspace path denied", code="FORBIDDEN"):
        super().__init__(message)
        self.code = code


def _parts(raw):
    if not isinstance(raw, str) or not raw.startswith("/") or len(raw) > 4096 or "\x00" in raw or "\\" in raw:
        raise WorkspaceFileError()
    parts = PurePosixPath(raw).parts
    if ".." in parts or parts[0] != "/":
        raise WorkspaceFileError()
    return parts[1:]


def _flags():
    if os.name != "posix" or any(not hasattr(os, n) for n in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "pread")):
        raise WorkspaceFileError("confined workspace IO unavailable", "SERVICE_UNAVAILABLE")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


@contextmanager
def _directory(parts, *, parent_fd=None, create=False, mode=0o755):
    flags = _flags()
    fd = os.open("/", flags) if parent_fd is None else os.dup(parent_fd)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _regular(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise WorkspaceFileError()
    return info


def _integer(params, name, default, *, minimum=0, maximum=None):
    value = params.get(name, default)
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise WorkspaceFileError(f"invalid {name}", "BAD_REQUEST")
    return value


def _read(root_fd, parts, path, params):
    if not parts:
        raise WorkspaceFileError("file required", "BAD_REQUEST")
    offset = _integer(params, "offset", 0)
    limit = _integer(params, "limit", 65536, minimum=1, maximum=CHUNK_BYTES)
    with _directory(parts[:-1], parent_fd=root_fd) as parent:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = _regular(fd)
            data = os.pread(fd, limit, offset)
            after = _regular(fd)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise WorkspaceFileError("file changed during read", "CONFLICT")
            return {"path": path, "data_base64": base64.b64encode(data).decode("ascii"),
                    "offset": offset, "chunk_size": len(data), "size": after.st_size,
                    "content_type": mimetypes.guess_type(path)[0] or "application/octet-stream",
                    "eof": offset + len(data) >= after.st_size}
        finally:
            os.close(fd)


def _write(root_fd, parts, path, params):
    if not parts:
        raise WorkspaceFileError("file required", "BAD_REQUEST")
    raw = params.get("data_base64")
    if not isinstance(raw, str) or len(raw) > (CHUNK_BYTES + 2) // 3 * 4:
        raise WorkspaceFileError("invalid chunk", "BAD_REQUEST")
    try:
        data = base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise WorkspaceFileError("invalid chunk", "BAD_REQUEST") from exc
    offset = _integer(params, "offset", 0)
    with _directory(parts[:-1], parent_fd=root_fd, create=True) as parent:
        # Validate type/link count before truncation. Never open with O_TRUNC.
        fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        try:
            info = _regular(fd)
            if offset == 0:
                os.ftruncate(fd, 0)
            elif info.st_size != offset:
                raise WorkspaceFileError("upload offset changed", "CONFLICT")
            os.lseek(fd, offset, os.SEEK_SET)
            remaining = memoryview(data)
            while remaining:
                remaining = remaining[os.write(fd, remaining):]
            return {"success": True, "path": path, "size": os.fstat(fd).st_size}
        finally:
            os.close(fd)


def _list(root_fd, parts, path, params):
    recursive = params.get("recursive", False)
    if type(recursive) is not bool:
        raise WorkspaceFileError("invalid recursive", "BAD_REQUEST")
    depth = _integer(params, "max_depth", 0, maximum=_MAX_DEPTH) or _MAX_DEPTH
    items = []

    def visit(fd, prefix, level):
        with os.scandir(fd) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                is_dir = stat.S_ISDIR(info.st_mode)
                if not is_dir and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    continue
                current = str(PurePosixPath(prefix) / entry.name)
                items.append({"name": entry.name, "path": current, "is_directory": is_dir,
                              "size": 0 if is_dir else info.st_size,
                              "modified_time": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                              "type": None if is_dir else PurePosixPath(entry.name).suffix})
                if len(items) > _LIST_LIMIT:
                    raise WorkspaceFileError("directory too large", "BAD_REQUEST")
                if is_dir and recursive and level < depth:
                    with _directory((entry.name,), parent_fd=fd) as child:
                        visit(child, current, level + 1)
    with _directory(parts, parent_fd=root_fd) as target:
        visit(target, path, 1)
    return {"items": items}


def _mkdir(root_fd, parts, path, params):
    raw_mode = params.get("mode")
    try:
        mode = int(raw_mode, 8) if isinstance(raw_mode, str) and raw_mode else 0o755
    except ValueError as exc:
        raise WorkspaceFileError("invalid mode", "BAD_REQUEST") from exc
    if not 0 <= mode <= 0o777:
        raise WorkspaceFileError("invalid mode", "BAD_REQUEST")
    recursive = params.get("recursive", False)
    if type(recursive) is not bool:
        raise WorkspaceFileError("invalid recursive", "BAD_REQUEST")
    if not parts:
        return {"success": True, "path": path, "created": False}
    with _directory(parts[:-1], parent_fd=root_fd, create=recursive) as parent:
        created = True
        try:
            os.mkdir(parts[-1], mode, dir_fd=parent)
        except FileExistsError:
            created = False
            # Only existing paths need validation. A freshly created directory
            # may intentionally have mode 000 and cannot be reopened for read.
            with _directory((parts[-1],), parent_fd=parent):
                pass
    return {"success": True, "path": path, "created": created}


def execute(operation, params):
    root = os.environ.get("JIUWENSWARM_CONTAINER_FILE_ROOT", "")
    if not root:
        raise WorkspaceFileError("confined workspace IO not configured", "SERVICE_UNAVAILABLE")
    if not isinstance(params, dict):
        raise WorkspaceFileError("invalid params", "BAD_REQUEST")
    root_parts = _parts(root)
    if not root_parts:
        raise WorkspaceFileError("invalid workspace root", "SERVICE_UNAVAILABLE")
    path = params.get("path")
    target = _parts(path)
    if target[:len(root_parts)] != root_parts:
        raise WorkspaceFileError()
    operations = {"read": _read, "write": _write, "list": _list, "mkdir": _mkdir}
    if operation not in operations:
        raise WorkspaceFileError("invalid operation", "BAD_REQUEST")
    try:
        with _directory(root_parts) as root_fd:
            return operations[operation](root_fd, target[len(root_parts):], path, params)
    except OSError as exc:
        code = "NOT_FOUND" if exc.errno == errno.ENOENT else "FORBIDDEN"
        raise WorkspaceFileError("workspace path unavailable", code) from exc
