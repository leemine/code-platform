"""Small executable lookup shared by CLI-backed plugins, without shell startup.

Providers supply their own installation locations. SDK-backed plugins can keep
using their SDK's discovery; this module does not register or install Providers.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_cli(command: str, *, explicit: str | None = None, candidates=()) -> str | None:
    """Resolve explicit selection, otherwise PATH then provider-owned locations.

    Never fall back after an invalid explicit selection. Implicit lookup ignores
    relative PATH entries, so a project-local executable cannot shadow the CLI.
    """
    def executable(path, *, explicit_selection=False):
        found = shutil.which(str(path))
        if found and Path(found).is_file():
            if os.name == "nt" and Path(found).suffix.lower() in {".cmd", ".bat", ".ps1"}:
                if explicit_selection:
                    raise ValueError("CLI script launchers require an explicit native executable path")
                return None
            # Preserve symlink/shim identity; some launchers resolve resources via argv[0].
            return os.path.abspath(found)
        return None

    paths = [Path(p) for p in os.get_exec_path() if p and Path(p).is_absolute()]
    if explicit is not None:
        value = Path(explicit.strip()).expanduser()
        if value.is_absolute():
            found = executable(value, explicit_selection=True)
        elif explicit.strip() == value.name and value.name not in {".", ".."}:
            found = None
            for parent in paths:
                found = executable(parent / value, explicit_selection=True)
                if found:
                    break
        else:
            found = None
        if not found:
            raise ValueError("Configured CLI is unavailable; use an absolute executable path or a command on PATH")
        return found
    for path in [*(parent / command for parent in paths), *candidates]:
        if Path(path).is_absolute():
            found = executable(path)
            if found:
                return found
    return None
