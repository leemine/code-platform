"""Opt-in, operator-owned Docker security assembly; no resource lifecycle.

This module does not load kernel policies or claim a profile is safe. Deployment
must review and validate the pinned profiles on its exact kernel/runtime first.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat

POLICY_LABEL = "io.code-platform.runtime-security"
APPARMOR_PROFILES = Path("/sys/kernel/security/apparmor/profiles")
MAX_POLICY_BYTES = 256 * 1024


def pinned_file(path: Path, digest: str) -> bytes:
    """Read an operator-owned regular file and verify the exact approved bytes."""
    if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or not path.is_absolute() or path.resolve() != path):
        raise ValueError("invalid security policy path or digest")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o022 or info.st_nlink != 1 or info.st_size > MAX_POLICY_BYTES):
            raise ValueError("security policy must be an operator-owned immutable regular file")
        raw = stream.read(MAX_POLICY_BYTES + 1)
    if len(raw) > MAX_POLICY_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("security policy digest differs")
    return raw


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate security policy field")
        value[key] = item
    return value


class RuntimeSecurity:
    """Apply a fixed policy only within the existing private deployment scope."""

    def __init__(self, manifest: Path, digest: str, *, images, user, workspace_root):
        self.path, self.digest = manifest, digest
        self.raw = pinned_file(manifest, digest)
        value = json.loads(self.raw, object_pairs_hook=unique_object)
        fields = {"schema", "id", "images", "user", "workspace_root", "seccomp_file", "seccomp_sha256",
                  "apparmor_profile", "apparmor_file", "apparmor_sha256"}
        if not isinstance(value, dict) or set(value) != fields or type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError("unsupported security manifest schema")
        if (not isinstance(value["id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", value["id"])
                or not isinstance(value["images"], list) or not value["images"]
                or any(not isinstance(i, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", i) for i in value["images"])
                or set(value["images"]) != set(images) or value["user"] != user
                or value["workspace_root"] != str(workspace_root)):
            raise ValueError("security manifest differs from deployment scope")
        profile = value["apparmor_profile"]
        if (not isinstance(profile, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", profile)
                or profile in {"unconfined", "docker-default"}):
            raise ValueError("explicit dedicated AppArmor profile required")
        self.value = value
        self.seccomp_raw = pinned_file(Path(value["seccomp_file"]), value["seccomp_sha256"])
        seccomp = json.loads(self.seccomp_raw, object_pairs_hook=unique_object)
        if (not isinstance(seccomp, dict) or seccomp.get("defaultAction") != "SCMP_ACT_ERRNO"
                or seccomp.get("defaultErrnoRet", 1) != 1
                or not isinstance(seccomp.get("syscalls"), list) or not seccomp["syscalls"]):
            raise ValueError("default-deny seccomp profile required")
        # No built-in widening or fallback. Profile contents remain a separately
        # reviewed deployment artifact, not arbitrary fields from an API caller.
        self.seccomp = json.dumps(seccomp, separators=(",", ":"), sort_keys=True)
        self.check_files()

    def check_files(self):
        pinned_file(self.path, self.digest)
        pinned_file(Path(self.value["seccomp_file"]), self.value["seccomp_sha256"])
        pinned_file(Path(self.value["apparmor_file"]), self.value["apparmor_sha256"])
        expected = self.value["apparmor_profile"] + " (enforce)"
        if expected not in APPARMOR_PROFILES.read_text().splitlines():
            raise ValueError("dedicated AppArmor profile is not loaded in enforce mode")

    def rewrite(self, request: dict) -> dict:
        self.check_files()
        if request.get("Image") not in self.value["images"] or request.get("User") != self.value["user"]:
            raise ValueError("security image or user differs")
        value = copy.deepcopy(request)
        host = value.get("HostConfig")
        if not isinstance(host, dict):
            raise ValueError("explicit Docker host configuration required")
        # Fail instead of silently removing an explicitly requested privilege.
        forbidden = ("Privileged", "CapAdd", "Devices", "DeviceRequests", "DeviceCgroupRules", "VolumesFrom",
                     "SecurityOpt", "Sysctls", "StorageOpt", "GroupAdd")
        if any(host.get(key) for key in forbidden):
            raise ValueError("caller privileges conflict with fixed security policy")
        if (host.get("Runtime", "runc") not in ("", "runc")
                or host.get("NetworkMode") in {"host"} or str(host.get("NetworkMode", "")).startswith("container:")
                or any(host.get(key) not in (None, "", "private") for key in ("PidMode", "IpcMode", "UTSMode", "CgroupnsMode"))
                or host.get("UsernsMode") not in (None, "")
                or any(key in host for key in ("MaskedPaths", "ReadonlyPaths"))):
            raise ValueError("caller namespaces or kernel paths conflict with fixed security policy")
        labels = value.get("Labels") or {}
        if not isinstance(labels, dict) or POLICY_LABEL in labels:
            raise ValueError("reserved runtime security label")
        value["Labels"] = {**labels, POLICY_LABEL: self.digest}
        host["CapDrop"] = ["ALL"]
        host["SecurityOpt"] = ["no-new-privileges:true", "apparmor=" + self.value["apparmor_profile"],
                               "seccomp=" + self.seccomp]
        return value

    def verify_inspect(self, value: dict) -> dict:
        """Check actual Docker metadata without accepting the label as proof."""
        self.check_files()
        config, host = value.get("Config", {}), value.get("HostConfig", {})
        if (value.get("Image") not in self.value["images"] or config.get("User") != self.value["user"]
                or config.get("Labels", {}).get(POLICY_LABEL) != self.digest
                or value.get("AppArmorProfile") != self.value["apparmor_profile"]
                or host.get("CapDrop") != ["ALL"]):
            raise ValueError("actual runtime security identity differs")
        # Docker inspect returns the compact seccomp JSON stored in SecurityOpt.
        expected = ["no-new-privileges:true", "apparmor=" + self.value["apparmor_profile"], "seccomp=" + self.seccomp]
        if host.get("SecurityOpt") != expected:
            raise ValueError("actual runtime security options differ")
        original = copy.deepcopy(value.get("Config", {}))
        original["HostConfig"] = copy.deepcopy(host)
        original["Image"] = value["Image"]
        original["HostConfig"].pop("SecurityOpt", None)
        # Daemon-populated masked/readonly defaults must be present; their exact
        # OCI rules and live Seccomp/NoNewPrivs are checked by deployment probes.
        for key in ("MaskedPaths", "ReadonlyPaths"):
            if not original["HostConfig"].pop(key, None):
                raise ValueError("actual kernel path protection is missing")
        original["Labels"].pop(POLICY_LABEL)
        self.rewrite(original)
        return {"manifest_sha256": self.digest, "policy_id": self.value["id"], "metadata_verified": True}
