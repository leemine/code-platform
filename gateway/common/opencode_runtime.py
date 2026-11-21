"""The placement contract for an operator-provisioned OpenCode runtime asset."""

import re
from pathlib import PurePosixPath

RUNTIME_TARGET = "/opt/yuanrong-python"


def runtime_source(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("OpenCode shared_runtime must be a versioned absolute directory")
    path = PurePosixPath(value)
    if (not path.is_absolute() or str(path) != value or ".." in path.parts
            or not re.fullmatch(r"[a-f0-9]{64}", path.name)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path.parts[1:])):
        raise ValueError("OpenCode shared_runtime must be a versioned absolute directory")
    return value
