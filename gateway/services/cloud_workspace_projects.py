"""Read an account's canonical project directory from its original ProjectStore."""
from contextlib import ExitStack
import json
import os
import re
import stat


_PROJECT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}\Z")
_MAX_BODY = 8 * 1024 * 1024


def project_snapshot(account: dict) -> list[dict]:
    # ProjectStore replaces the file atomically. Read that snapshot through
    # directory descriptors so mutable account paths cannot follow symlinks.
    directory_flags = os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as scope:
        root_fd = os.open(account["workspace"], directory_flags)
        scope.callback(os.close, root_fd)
        agent_fd = os.open("agent", directory_flags, dir_fd=root_fd)
        scope.callback(os.close, agent_fd)
        projects_fd = os.open("projects.json", os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=agent_fd)
        projects = scope.enter_context(os.fdopen(projects_fd, "rb"))
        if not stat.S_ISREG(os.fstat(projects_fd).st_mode):
            raise PermissionError("Invalid account project store")
        snapshot = projects.read(_MAX_BODY + 1)
    if len(snapshot) > _MAX_BODY:
        raise PermissionError("Invalid account project store")
    rows = json.loads(snapshot)["projects"]
    if not isinstance(rows, list):
        raise PermissionError("Invalid account project store")
    return rows


def project_directory(account: dict, project_id: str) -> str:
    if not _PROJECT.fullmatch(project_id):
        raise PermissionError("Invalid project identity")
    rows = project_snapshot(account)
    matches = [row for row in rows if isinstance(row, dict)
               and row.get("project_id") == project_id and not row.get("hidden")]
    if len(matches) != 1:
        raise PermissionError("OpenCode requires a project owned by this account")
    directory = matches[0]["project_dir"]
    if not isinstance(directory, str) or not directory:
        raise PermissionError("OpenCode requires a project workspace")
    return directory
