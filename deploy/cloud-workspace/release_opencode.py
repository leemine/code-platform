"""Build and provision a digest-pinned managed OpenCode release."""
from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

from opencode_runtime_asset import asset_source, tree_digest

MANIFEST = "release.json"
IMAGES = "images.tar.gz"
RUNTIME = "runtime.tar.gz"
RUNTIME_ROOT = Path("/opt/code-platform/runtime-assets")
CODE = (Path(__file__).resolve(), Path(__file__).with_name("opencode_runtime_asset.py").resolve())
HEX = re.compile(r"[a-f0-9]{64}")
IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}")
SSH_TARGET = re.compile(r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9_.-]*")
REMOTE_STAGE = re.compile(r"/tmp/code-platform-opencode\.[A-Za-z0-9]{8}")


def digest(path: Path) -> str:
    """Hash an artifact without buffering it in memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_manifest(bundle: Path, expected: str | None = None) -> tuple[dict, str]:
    """Load the exact release manifest supplied by the publisher."""
    raw = (bundle / MANIFEST).read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    if expected is not None and fingerprint != expected:
        raise ValueError("OpenCode release manifest digest mismatch")
    release = json.loads(raw)
    if (not isinstance(release, dict)
            or set(release) != {"version", "image", "rollback_image", "runtime_sha256", "archives"}
            or type(release["version"]) is not int or release["version"] != 1):
        raise ValueError("Invalid OpenCode release manifest")
    validate_pins(release["image"], release["rollback_image"], release["runtime_sha256"])
    archives = release["archives"]
    if (not isinstance(archives, dict) or set(archives) != {IMAGES, RUNTIME}
            or any(not isinstance(value, str) or not HEX.fullmatch(value) for value in archives.values())):
        raise ValueError("Invalid OpenCode release archive digests")
    return release, fingerprint


def validate_pins(image: str, rollback: str, runtime: str) -> None:
    """Require immutable Docker image IDs and a separate runtime tree digest."""
    if (any(not isinstance(value, str) or not IMAGE_ID.fullmatch(value) for value in (image, rollback))
            or image == rollback or not isinstance(runtime, str) or not HEX.fullmatch(runtime)):
        raise ValueError("OpenCode release requires two distinct image IDs and a sealed runtime digest")


def docker(*arguments: str, **options) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "--host", "unix:///var/run/docker.sock", *arguments], **options)


def image_present(identifier: str) -> bool:
    result = docker("image", "inspect", "--format", "{{.Id}}", identifier,
                    capture_output=True, text=True, timeout=30)
    return result.returncode == 0 and result.stdout.strip() == identifier


def pack(output: Path, image: str, rollback: str, source: Path, runtime: str) -> str:
    """Export the two verified images and a sealed startup stack as one release."""
    validate_pins(image, rollback, runtime)
    if not all(map(image_present, (image, rollback))):
        raise ValueError("OpenCode release and rollback images must exist on the publishing host")
    if tree_digest(source) != runtime:
        raise ValueError("OpenCode publisher runtime tree digest mismatch")
    if output.exists() or output.is_symlink():
        raise ValueError("OpenCode release output already exists")
    with tempfile.TemporaryDirectory(prefix=".opencode-pack-", dir=output.parent) as scratch:
        stage = Path(scratch) / "bundle"
        stage.mkdir(mode=0o700)
        with (stage / IMAGES).open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=1) as out:
            with subprocess.Popen(["docker", "--host", "unix:///var/run/docker.sock",
                                   "image", "save", image, rollback], stdout=subprocess.PIPE) as save:
                shutil.copyfileobj(save.stdout, out)
                if save.wait() != 0:
                    raise ValueError("OpenCode Docker image export failed")
        with tarfile.open(stage / RUNTIME, "w:gz", compresslevel=1) as archive:
            archive.add(source, arcname="runtime")
        release = {"version": 1, "image": image, "rollback_image": rollback, "runtime_sha256": runtime,
                   "archives": {name: digest(stage / name) for name in (IMAGES, RUNTIME)}}
        (stage / MANIFEST).write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")
        # Verify the source stayed sealed while the archive was written.
        if tree_digest(source) != runtime:
            raise ValueError("OpenCode publisher runtime changed during export")
        stage.rename(output)
    return digest(output / MANIFEST)


def checked_archive(bundle: Path, release: dict, name: str) -> Path:
    path = bundle / name
    if not path.is_file() or path.is_symlink() or digest(path) != release["archives"][name]:
        raise ValueError(f"OpenCode release archive integrity check failed: {name}")
    return path


def unpack_runtime(path: Path, scratch: Path) -> Path:
    """Extract inside a private staging directory and retain sealed modes."""
    def runtime_member(member: tarfile.TarInfo, destination: str) -> tarfile.TarInfo:
        relative = Path(member.name)
        if (relative.is_absolute() or relative.parts[:1] != ("runtime",) or ".." in relative.parts
                or not (member.isdir() or member.isfile() or member.issym() or member.islnk())
                or member.uid != 0 or member.gid != 0):
            raise ValueError("Invalid member in the OpenCode runtime archive")
        if not member.issym() and (member.mode & 0o222 or member.mode & ~0o777):
            raise ValueError("Unsealed member in the OpenCode runtime archive")
        result = tarfile.data_filter(member, destination)
        result.mode = member.mode if not member.issym() else None
        return result

    with tarfile.open(path, "r:gz") as archive:
        archive.extractall(scratch, filter=runtime_member)
    return scratch / "runtime"


def trusted_root(path: Path, *, create: bool = False) -> Path:
    if path == Path("/") or not path.is_absolute() or path.resolve() != path or ".." in path.parts:
        raise ValueError("OpenCode runtime root must be a canonical absolute directory")
    for parent in (*reversed(path.parents), path):
        if create:
            parent.mkdir(mode=0o755, exist_ok=True)
        entry = parent.lstat()
        if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != 0 or entry.st_gid != 0 or entry.st_mode & 0o022:
            raise ValueError("OpenCode runtime root has an untrusted ancestor")
    return path


def node_receipt(release: dict, manifest_sha: str, runtime: Path) -> dict:
    """Verify the node-local tree and both runnable image IDs."""
    if tree_digest(runtime) != release["runtime_sha256"]:
        raise ValueError("OpenCode host runtime tree digest mismatch")
    if not all(map(image_present, (release["image"], release["rollback_image"]))):
        raise ValueError("OpenCode release or rollback image missing after provisioning")
    return {"manifest_sha256": manifest_sha, "image": release["image"],
            "rollback_image": release["rollback_image"], "runtime_sha256": release["runtime_sha256"],
            "shared_runtime": str(runtime)}


def retain_image(identifier: str) -> None:
    tag = "code-platform-opencode:sha256-" + identifier.split(":", 1)[1]
    result = docker("image", "inspect", "--format", "{{.Id}}", tag,
                    capture_output=True, text=True, timeout=30)
    if result.returncode == 0 and result.stdout.strip() != identifier:
        raise ValueError("OpenCode release retention tag already refers to a different image")
    if result.returncode != 0:
        docker("image", "tag", identifier, tag, check=True, timeout=30)


def apply_node(bundle: Path, root: Path, expected: str) -> dict:
    """Install without changing the live node boundary or existing asset versions."""
    release, manifest_sha = load_manifest(bundle, expected)
    root = trusted_root(root, create=True)
    runtime = asset_source(str(root / release["runtime_sha256"]))
    fd = os.open(root / ".opencode-release.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix=".opencode-install-", dir=root) as scratch:
            incoming = runtime
            if not runtime.exists() and not runtime.is_symlink():
                incoming = unpack_runtime(checked_archive(bundle, release, RUNTIME), Path(scratch))
            if tree_digest(incoming) != release["runtime_sha256"]:
                raise ValueError("OpenCode host runtime tree digest mismatch")
            images = (release["image"], release["rollback_image"])
            if not all(map(image_present, images)):
                images_archive = checked_archive(bundle, release, IMAGES)
                docker("image", "load", "--input", str(images_archive), stdout=subprocess.DEVNULL,
                       check=True, timeout=600)
            if not all(map(image_present, images)):
                raise ValueError("OpenCode release or rollback image missing after import")
            for identifier in images:
                retain_image(identifier)
            if incoming != runtime:
                incoming.rename(runtime)
        return node_receipt(release, manifest_sha, runtime)


def provision_host(host: str, bundle: Path, root: Path, manifest_sha: str, ssh_config: Path | None) -> dict:
    """Transfer a release to one explicitly selected, host-key-verified node."""
    options = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]
    if ssh_config is not None:
        options.extend(("-F", str(ssh_config)))
    ssh = ["ssh", *options, "--", host]
    remote = subprocess.check_output([*ssh, "mktemp -d /tmp/code-platform-opencode.XXXXXXXX"],
                                     text=True, timeout=30).strip()
    if not REMOTE_STAGE.fullmatch(remote):
        raise ValueError("OpenCode node returned an invalid staging path")
    paths = (*CODE, *(bundle / name for name in (MANIFEST, IMAGES, RUNTIME)))
    try:
        subprocess.run(["scp", *options, "--", *map(str, paths), f"{host}:{remote}/"], check=True, timeout=900)
        command = ["python3", "-B", remote + "/release_opencode.py", "apply-node", "--bundle", remote,
                   "--runtime-root", str(root), "--manifest-sha256", manifest_sha]
        return json.loads(subprocess.check_output([*ssh, shlex.join(command)], text=True, timeout=900))
    finally:
        # Remove only the files uploaded into this invocation's private staging directory.
        cleanup = ["rm", "-f", "--", *(remote + "/" + path.name for path in paths)]
        subprocess.run([*ssh, shlex.join(cleanup) + " && " + shlex.join(["rmdir", "--", remote])],
                       check=False, timeout=30)


def fleet(bundle: Path, root: Path, hosts: list[str], config: Path | None) -> dict:
    """Gate deployment on every selected host verifying the same release."""
    if not hosts or len(hosts) != len(set(hosts)) or any(not SSH_TARGET.fullmatch(host) for host in hosts):
        raise ValueError("Specify a nonempty unique list of SSH target aliases for the pool")
    release, fingerprint = load_manifest(bundle)
    runtime = asset_source(str(root / release["runtime_sha256"]))
    expected = {"manifest_sha256": fingerprint, "shared_runtime": str(runtime),
                **{key: release[key] for key in ("image", "rollback_image", "runtime_sha256")}}
    for host in hosts:
        try:
            receipt = provision_host(host, bundle, root, fingerprint, config)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            raise ValueError(f"OpenCode provisioning failed on {host}: {error}") from error
        if receipt != expected:
            raise ValueError(f"OpenCode release receipt differs on {host}")
        print(f"Verified OpenCode release on {host}", file=sys.stderr, flush=True)
    return {"manifest_sha256": fingerprint, "verified_nodes": hosts,
            "opencode_provider": {"image": release["image"], "shared_runtime": str(runtime)},
            "rollback_provider": {"image": release["rollback_image"]},
            "boundary_args": ["--opencode-provider-image", release["image"], "--opencode-provider-image",
                              release["rollback_image"], "--opencode-runtime-asset",
                              release["image"] + "=" + str(runtime)]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    export = command.add_parser("pack", help="export the Docker images and sealed runtime as a release")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--image", required=True)
    export.add_argument("--rollback-image", required=True)
    export.add_argument("--runtime-source", type=Path, required=True)
    export.add_argument("--runtime-sha256", required=True)
    for name in ("apply-node", "verify-node", "provision"):
        action = command.add_parser(name)
        action.add_argument("--bundle", type=Path, required=True)
        action.add_argument("--runtime-root", type=Path, default=RUNTIME_ROOT)
        if name == "provision":
            action.add_argument("--host", action="append", required=True)
            action.add_argument("--ssh-config", type=Path)
        else:
            action.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            sha = pack(args.output, args.image, args.rollback_image, args.runtime_source, args.runtime_sha256)
            result = {"manifest_sha256": sha}
        elif args.command == "provision":
            result = fleet(args.bundle, args.runtime_root, args.host, args.ssh_config)
        elif args.command == "apply-node":
            result = apply_node(args.bundle, args.runtime_root, args.manifest_sha256)
        else:
            release, sha = load_manifest(args.bundle, args.manifest_sha256)
            runtime = trusted_root(args.runtime_root) / release["runtime_sha256"]
            result = node_receipt(release, sha, asset_source(str(runtime)))
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"OpenCode release: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
