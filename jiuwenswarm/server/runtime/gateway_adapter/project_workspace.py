"""Code directory browsing on the original AgentServer project/file boundary.

Uses the descriptor walk from workspace_file_io and the original ProjectStore.
No Gateway filesystem access, caller-supplied roots, or extra project database.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from jiuwenswarm.common.utils import get_agent_workspace_dir
from jiuwenswarm.server.runtime.gateway_adapter import workspace_file_io as io
from jiuwenswarm.server.runtime.gateway_adapter.project_adapter import _create_project
from jiuwenswarm.server.runtime.session import project_store
from jiuwenswarm.server.control.store.project_queries import project_info_payload


def _relative(value):
    if not isinstance(value, str) or len(value) > 2048 or "\\" in value or "\x00" in value:
        raise io.WorkspaceFileError("invalid directory", "BAD_REQUEST")
    parts = value.split("/") if value else []
    if any(not part or part.startswith(".") for part in parts):
        raise io.WorkspaceFileError("invalid directory", "BAD_REQUEST")
    return tuple(parts)


def execute(params, channel_id):
    operation = params.get("workspace_operation")
    if operation not in {"list", "mkdir", "open"} or params.get("work_mode") != "code":
        raise io.WorkspaceFileError("unsupported workspace operation", "BAD_REQUEST")
    if set(params) - {"workspace_operation", "work_mode", "path", "name", "offset"}:
        raise io.WorkspaceFileError("unexpected workspace selectors", "BAD_REQUEST")
    parts = _relative(params.get("path", ""))
    root = get_agent_workspace_dir() / "code"
    try:
        with io._directory(io._parts(str(root)), create=True) as root_fd:
            with io._directory(parts, parent_fd=root_fd) as fd:
                if operation == "list":
                    offset = io._integer(params, "offset", 0, maximum=10000)
                    names = []
                    with os.scandir(fd) as entries:
                        for entry in entries:
                            if not entry.name.startswith(".") and stat.S_ISDIR(entry.stat(follow_symlinks=False).st_mode):
                                names.append(entry.name)
                            if len(names) > 10000:
                                raise io.WorkspaceFileError("directory too large", "BAD_REQUEST")
                    names.sort()
                    page = names[offset:offset + 100]
                    return {"path": "/".join(parts), "work_mode": "code",
                            "items": [{"name": name, "path": "/".join((*parts, name))} for name in page],
                            "next_offset": offset + 100 if offset + 100 < len(names) else None}
                if operation == "mkdir":
                    name = params.get("name", "")
                    if len(_relative(name)) != 1:
                        raise io.WorkspaceFileError("single folder name required", "BAD_REQUEST")
                    project_store.validate_project_dir_name(name)
                    try:
                        os.mkdir(name, 0o755, dir_fd=fd)
                    except FileExistsError as exc:
                        raise io.WorkspaceFileError("folder already exists", "CONFLICT") from exc
                    os.fsync(fd)
                    return {"path": "/".join((*parts, name)), "created": True}
                if not parts:
                    raise io.WorkspaceFileError("select a project directory", "BAD_REQUEST")
                path = root.joinpath(*parts)
                # Existing projects remain authoritative; do not silently register
                # a nested project with a different lifecycle or mode.
                for project in project_store.list_projects(include_hidden=True, cache_bust=True):
                    existing = Path(project.project_dir)
                    if path == existing:
                        if project.hidden or project.work_mode != "code":
                            raise io.WorkspaceFileError("project unavailable", "FORBIDDEN")
                        return {"project": project_info_payload(project), "path": "/".join(parts)}
                    if existing in path.parents:
                        raise io.WorkspaceFileError("select the registered project root", "PROJECT_ROOT_REQUIRED")
                    if path in existing.parents:
                        raise io.WorkspaceFileError("directory contains a registered project", "PROJECT_ROOT_REQUIRED")
                # Check the name still resolves to the directory we inspected.
                with io._directory(parts, parent_fd=root_fd) as current:
                    if (os.fstat(current).st_dev, os.fstat(current).st_ino) != (os.fstat(fd).st_dev, os.fstat(fd).st_ino):
                        raise io.WorkspaceFileError("directory changed", "CONFLICT")
                result, error, code = _create_project({"name": parts[-1], "project_dir": str(path), "work_mode": "code"}, channel_id)
                if error:
                    raise io.WorkspaceFileError(error, code)
                return {"project": result["project"], "path": "/".join(parts)}
    except FileNotFoundError as exc:
        raise io.WorkspaceFileError("directory missing", "NOT_FOUND") from exc
    except OSError as exc:
        raise io.WorkspaceFileError("directory unavailable", "FORBIDDEN") from exc
