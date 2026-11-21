"""Node-local admission for digest-pinned OpenCode runtime trees."""

import argparse
import hashlib
import re
import stat
from pathlib import Path

RUNTIME_TARGET = "/opt/yuanrong-python"
_IMAGE_DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
_TREE_VERSION = re.compile(r"[a-f0-9]{64}")


def asset_source(value: str) -> Path:
    path = Path(value)
    if (not path.is_absolute() or str(path) != value or ".." in path.parts
            or not _TREE_VERSION.fullmatch(path.name)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path.parts[1:])):
        raise ValueError("OpenCode runtime asset needs a versioned absolute source directory")
    return path


def asset_rules(values, provider_images):
    rules = {}
    for value in values:
        image, separator, source = value.partition("=")
        if not separator or not _IMAGE_DIGEST.fullmatch(image) or image not in provider_images or image in rules:
            raise ValueError("OpenCode runtime asset needs one rule for an allowlisted image digest")
        rules[image] = asset_source(source)
    return rules


def runtime_identity(path: Path) -> tuple[int, int]:
    if path.resolve(strict=True) != path:
        raise ValueError("OpenCode runtime asset path must be canonical")
    entry = path.lstat()
    if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != 0 or entry.st_gid != 0 or entry.st_mode & 0o222:
        raise ValueError("OpenCode runtime asset must be an immutable root-owned directory")
    for parent in path.parents:
        entry = parent.lstat()
        if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != 0 or entry.st_mode & 0o022:
            raise ValueError("OpenCode runtime asset ancestor is writable or untrusted")
    entry = path.lstat()
    return entry.st_dev, entry.st_ino


def tree_digest(path: Path) -> str:
    runtime_identity(path)
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        if Path(line.split()[4]).is_relative_to(path):
            raise ValueError("OpenCode runtime asset cannot contain mount points")
    digest = hashlib.sha256()
    for item in (path, *sorted(path.rglob("*"))):
        entry = item.lstat()
        if entry.st_uid != 0 or entry.st_gid != 0:
            raise ValueError("OpenCode runtime asset entry is not root owned")
        digest.update(f"{item.relative_to(path).as_posix()}\0{entry.st_mode}\0".encode())
        if stat.S_ISLNK(entry.st_mode):
            if not item.resolve(strict=True).is_relative_to(path):
                raise ValueError("OpenCode runtime asset symlink leaves its tree")
            digest.update(str(item.readlink()).encode())
        elif stat.S_ISREG(entry.st_mode):
            if entry.st_mode & 0o222:
                raise ValueError("OpenCode runtime asset file is writable")
            with item.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest())
        elif not stat.S_ISDIR(entry.st_mode) or entry.st_mode & 0o222:
            raise ValueError("OpenCode runtime asset entry is not immutable")
        digest.update(b"\0")
    return digest.hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute the digest of a sealed OpenCode runtime tree")
    parser.add_argument("path", type=Path)
    print(tree_digest(parser.parse_args().path))
