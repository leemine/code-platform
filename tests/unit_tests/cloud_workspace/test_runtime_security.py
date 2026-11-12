"""Pinned deployment policy tests; fake Docker is not a kernel sandbox test."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.unit_tests.cloud_workspace.test_docker_log_boundary import boundary, module
from tests.unit_tests.cloud_workspace.test_physical_resources import stack, call, create

spec = importlib.util.spec_from_file_location("runtime_security", Path(module.__file__).with_name("runtime_security.py"))
security_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security_module)


@pytest.fixture
def policy(boundary, tmp_path, monkeypatch):
    gate, request, actor, shared = boundary
    gate.images = frozenset(["sha256:" + "a" * 64])
    request["Image"] = next(iter(gate.images))
    seccomp = tmp_path / "seccomp.json"
    seccomp.write_text(json.dumps({"defaultAction": "SCMP_ACT_ERRNO", "defaultErrnoRet": 1,
        "syscalls": [{"names": ["read", "write"], "action": "SCMP_ACT_ALLOW"}]}))
    apparmor = tmp_path / "profile"
    apparmor.write_text("profile test-codex { }\n")
    seccomp.chmod(0o600)
    apparmor.chmod(0o600)
    profiles = tmp_path / "loaded-profiles"
    profiles.write_text("test-codex (enforce)\n")
    monkeypatch.setattr(security_module, "APPARMOR_PROFILES", profiles)
    manifest = tmp_path / "manifest.json"
    value = {"schema": 1, "id": "test-only", "images": list(gate.images), "user": gate.user,
             "workspace_root": str(gate.workspace_root), "seccomp_file": str(seccomp),
             "seccomp_sha256": hashlib.sha256(seccomp.read_bytes()).hexdigest(),
             "apparmor_profile": "test-codex", "apparmor_file": str(apparmor),
             "apparmor_sha256": hashlib.sha256(apparmor.read_bytes()).hexdigest()}
    def load(update=None):
        if update:
            value.update(update)
        manifest.write_text(json.dumps(value))
        manifest.chmod(0o600)
        return security_module.RuntimeSecurity(manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(),
            images=gate.images, user=gate.user, workspace_root=gate.workspace_root)
    return load, request, value, profiles, manifest


def test_pinned_policy_sends_json_not_cli_path_and_preserves_execution(policy):
    load, request, value, profiles, manifest = policy
    before = copy.deepcopy(request)
    security = load()
    result = security.rewrite(request)
    assert request == before
    assert result["Cmd"] == before["Cmd"] and result["Env"] == before["Env"]
    assert result["HostConfig"]["Mounts"] == before["HostConfig"]["Mounts"]
    assert result["HostConfig"]["CapDrop"] == ["ALL"]
    opts = result["HostConfig"]["SecurityOpt"]
    assert opts[:2] == ["no-new-privileges:true", "apparmor=test-codex"]
    assert json.loads(opts[2].removeprefix("seccomp="))["defaultAction"] == "SCMP_ACT_ERRNO"
    assert value["seccomp_file"] not in opts[2]
    assert result["Labels"][security_module.POLICY_LABEL] == security.digest


@pytest.mark.parametrize("field,value", [
    ("Privileged", True), ("CapAdd", ["SYS_ADMIN"]), ("SecurityOpt", ["seccomp=unconfined"]),
    ("Devices", [{"PathOnHost": "/dev/kvm"}]), ("DeviceRequests", [{"Count": -1}]),
    ("DeviceCgroupRules", ["a *:* rwm"]), ("VolumesFrom", ["another"]),
    ("NetworkMode", "host"), ("NetworkMode", "container:another"), ("PidMode", "host"),
    ("IpcMode", "host"), ("UTSMode", "host"), ("UsernsMode", "host"),
    ("CgroupnsMode", "host"), ("Runtime", "other"), ("MaskedPaths", []),
    ("ReadonlyPaths", []), ("Sysctls", {"kernel.foo": "1"}), ("GroupAdd", ["0"]),
])
def test_rejects_conflicting_privileges(policy, field, value):
    load, request, *_ = policy
    security = load()
    request["HostConfig"][field] = value
    with pytest.raises(ValueError):
        security.rewrite(request)


@pytest.mark.parametrize("which", ["manifest", "seccomp", "apparmor", "unloaded", "complain"])
def test_policy_drift_or_missing_enforcement_fails_before_dispatch(policy, which):
    load, request, value, profiles, manifest = policy
    security = load()
    if which == "manifest": manifest.write_text("{}")
    elif which in {"seccomp", "apparmor"}: Path(value[which + "_file"]).write_text("changed")
    else: profiles.write_text("" if which == "unloaded" else "test-codex (complain)\n")
    with pytest.raises(ValueError): security.rewrite(request)


@pytest.mark.parametrize("change", ["digest", "linked", "writable", "allow", "schema", "image", "workspace", "profile"])
def test_rejects_invalid_manifest_and_policy(policy, change):
    load, request, value, profiles, manifest = policy
    if change == "digest": value["seccomp_sha256"] = "0" * 64
    elif change == "linked":
        path = Path(value["seccomp_file"]); link = path.with_suffix(".link"); link.symlink_to(path)
        value["seccomp_file"] = str(link)
    elif change == "writable": Path(value["seccomp_file"]).chmod(0o666)
    elif change == "allow":
        path = Path(value["seccomp_file"]); path.write_text('{"defaultAction":"SCMP_ACT_ALLOW","syscalls":[]}')
        value["seccomp_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif change == "schema": value["schema"] = True
    elif change == "image": value["images"] = ["mutable:latest"]
    elif change == "workspace": value["workspace_root"] = "/"
    else: value["apparmor_profile"] = "unconfined"
    with pytest.raises(ValueError): load()


def test_caller_cannot_supply_policy_attestation(policy):
    load, request, *_ = policy
    security = load()
    request["Labels"] = {security_module.POLICY_LABEL: security.digest}
    with pytest.raises(ValueError): security.rewrite(request)


def test_inspect_verification_requires_actual_options_not_just_label(policy):
    load, request, *_ = policy
    security = load()
    result = security.rewrite(request)
    host = copy.deepcopy(result["HostConfig"])
    host.update(MaskedPaths=["/proc/kcore"], ReadonlyPaths=["/proc/sys"])
    actual = {"Image": result["Image"], "Config": result, "HostConfig": host, "AppArmorProfile": "test-codex"}
    assert security.verify_inspect(actual)["metadata_verified"]
    actual["HostConfig"]["SecurityOpt"] = ["seccomp=unconfined"]
    with pytest.raises(ValueError): security.verify_inspect(actual)


def test_original_http_dispatch_keeps_one_receipt_and_recovers_lost_response(policy, stack, monkeypatch):
    load, request, value, profiles, manifest = policy
    resources, request, state, proxy, restricted, payload = stack
    request["Image"] = value["images"][0]
    payload["image"] = request["Image"]
    security = load()
    # Same production HTTP handler and persistent physical dispatch mechanism.
    monkeypatch.setattr(module.Server, "runtime_security", security, raising=False)
    state["drop"] = True
    import http.client
    with pytest.raises(http.client.RemoteDisconnected): create(stack)
    assert state["creates"] == 1
    container = next(iter(state["containers"].values()))
    assert container["Config"]["HostConfig"]["CapDrop"] == ["ALL"]
    receipts = list(resources.root.glob("*/*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["runtime_security_sha256"] == security.digest
    assert create(stack) == 502 and state["creates"] == 1
    assert resources.confirm_deleted(payload)["absent"]
    assert not state["containers"]
    assert create(stack) == 502
    # Restore the same policy from disk, then advance only the original epoch.
    monkeypatch.setattr(module.Server, "runtime_security", load())
    identity = Path(payload["identity"]).with_name("epoch-2"); identity.mkdir(mode=0o700)
    if os.getuid() == 0: os.chown(identity, resources.boundary.uid, resources.boundary.uid)
    request["HostConfig"]["Mounts"][-1]["Source"] = str(identity)
    assert create(stack) == 201 and state["creates"] == 2


def test_drift_rejected_by_http_without_upstream_create(policy, stack, monkeypatch):
    load, request, value, profiles, manifest = policy
    security = load()
    stack[1]["Image"] = value["images"][0]
    monkeypatch.setattr(module.Server, "runtime_security", security, raising=False)
    Path(value["seccomp_file"]).write_text("changed")
    assert create(stack) == 502
    assert state_empty(stack)


def state_empty(stack):
    return stack[2]["creates"] == 0 and not list(stack[0].root.glob("*/*.json"))


def test_cli_refuses_partial_security_configuration():
    result = subprocess.run([sys.executable, str(module.__file__), "--listen", "/unused/b.sock",
        "--workspace-root", "/unused/work", "--workspace-name-pattern", "test-.*",
        "--private-log-root", "/unused/log", "--shared-log-dir", "/unused/shared", "--image", "test",
        "--user", "pilot", "--uid", "1000", "--runtime-security-manifest", "/unused/manifest"],
        capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert "requires both manifest and pinned SHA256" in result.stderr
