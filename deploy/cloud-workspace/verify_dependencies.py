"""Fail a candidate build on version/source drift; emit an inspectable inventory."""
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path
import sys
import tomllib
from packaging.utils import canonicalize_name

root = Path(__file__).parent
lock_bytes = (root / "uv.lock").read_bytes()
lock = tomllib.loads(lock_bytes.decode())
candidate = json.loads((root / "candidate.json").read_text())
assert hashlib.sha256(lock_bytes).hexdigest() == candidate["lock_sha256"]
packages = {}
for package in lock["package"]:
    packages.setdefault(canonicalize_name(package["name"]), []).append(package)
inventory = {}
for dist in metadata.distributions():
    name = canonicalize_name(dist.metadata["Name"])
    matches = [p for p in packages.get(name, []) if p["version"] == dist.version]
    assert matches, f"unlocked distribution: {name}=={dist.version}"
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    assert not direct.get("dir_info", {}).get("editable"), f"editable: {name}"
    git_sources = [p["source"]["git"] for p in matches if "git" in p["source"]]
    if git_sources:
        commit = direct.get("vcs_info", {}).get("commit_id")
        url = direct.get("url")
        assert any(s.rsplit("#", 1)[-1] == commit and s.split("?", 1)[0].removeprefix("git+") == url for s in git_sources), f"VCS source mismatch: {name}"
    if name == "workswarm":
        # uv's local-wheel direct_url may omit archive hashes. The Docker build
        # checks the archive before installation; verify installed source too.
        assert direct.get("url", "").startswith("file:///candidate/")
        for filename, digest in candidate["source_sha256"].items():
            assert hashlib.sha256(Path(dist.locate_file(filename)).read_bytes()).hexdigest() == digest, filename
    inventory[name] = {"version": dist.version, "location": str(dist.locate_file("")), "source": direct}
for name in ("workswarm", "openjiuwen", "openjiuwen-protocol"):
    assert name in inventory, f"missing required distribution: {name}"
imports = {}
for name in ("gateway", "jiuwenswarm", "openjiuwen", "openjiuwen_protocol"):
    spec = importlib.util.find_spec(name)
    assert spec and spec.origin and Path(spec.origin).is_relative_to(sys.prefix), f"unexpected import: {name}"
    imports[name] = spec.origin
print(json.dumps({"python": sys.version, "prefix": sys.prefix, "lock_sha256": candidate["lock_sha256"], "imports": imports, "packages": inventory}, indent=2))
