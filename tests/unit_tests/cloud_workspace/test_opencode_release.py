"""Release asset integrity and rollout gate checks."""
import json
from pathlib import Path
import sys
import tarfile

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "deploy/cloud-workspace"
sys.path.insert(0, str(DEPLOY))
try:
    import release_opencode as release
finally:
    sys.path.remove(str(DEPLOY))

IMAGE = "sha256:" + "a" * 64
ROLLBACK = "sha256:" + "b" * 64
TREE = "c" * 64


@pytest.fixture
def bundle(tmp_path):
    manifest = {
        "version": 1, "image": IMAGE, "rollback_image": ROLLBACK, "runtime_sha256": TREE,
        "archives": {release.IMAGES: "d" * 64, release.RUNTIME: "e" * 64},
    }
    (tmp_path / release.MANIFEST).write_text(json.dumps(manifest))
    return tmp_path


def test_release_requires_distinct_pinned_images_and_matching_manifest(bundle):
    document, fingerprint = release.load_manifest(bundle)
    assert (document["image"], document["rollback_image"], document["runtime_sha256"]) == (IMAGE, ROLLBACK, TREE)
    assert release.load_manifest(bundle, fingerprint)[0] == document
    with pytest.raises(ValueError, match="manifest digest mismatch"):
        release.load_manifest(bundle, "0" * 64)
    with pytest.raises(ValueError, match="distinct image IDs"):
        release.validate_pins(IMAGE, IMAGE, TREE)
    with pytest.raises(ValueError, match="distinct image IDs"):
        release.validate_pins("opencode:latest", ROLLBACK, TREE)


def test_corrupt_archive_cannot_reach_the_unpacker(bundle):
    document, _ = release.load_manifest(bundle)
    (bundle / release.RUNTIME).write_bytes(b"corrupt transfer")
    with pytest.raises(ValueError, match="archive integrity"):
        release.checked_archive(bundle, document, release.RUNTIME)


def test_runtime_extraction_preserves_sealed_modes(tmp_path):
    src = tmp_path / "runtime.tar.gz"
    with tarfile.open(src, "w:gz") as archive:
        root = tarfile.TarInfo("runtime")
        root.type = tarfile.DIRTYPE
        root.mode = 0o555
        archive.addfile(root)
        link = tarfile.TarInfo("runtime/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "."
        archive.addfile(link)
    dest = release.unpack_runtime(src, tmp_path / "staging")
    assert dest.stat().st_mode & 0o777 == 0o555
    assert (dest / "link").readlink() == Path(".")


def test_runtime_archive_rejects_traversal(tmp_path):
    path = tmp_path / "runtime.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(tarfile.TarInfo("runtime/../../unauthorized"))
    with pytest.raises(ValueError, match="Invalid member"):
        release.unpack_runtime(path, tmp_path / "staging")
    assert not (tmp_path / "unauthorized").exists()


def test_all_nodes_confirm_same_release_before_switch(bundle, monkeypatch):
    root = Path("/opt/code-platform/runtime-assets")
    _, fingerprint = release.load_manifest(bundle)
    receipt = {
        "manifest_sha256": fingerprint, "image": IMAGE, "rollback_image": ROLLBACK,
        "runtime_sha256": TREE, "shared_runtime": str(root / TREE),
    }

    def dispatch(host, *_args):
        return receipt if host == "original" else {**receipt, "runtime_sha256": "f" * 64}

    monkeypatch.setattr(release, "provision_host", dispatch)
    with pytest.raises(ValueError, match="receipt differs on new-node"):
        release.fleet(bundle, root, ["original", "new-node"], None)
    monkeypatch.setattr(release, "provision_host", lambda *_: receipt)
    plan = release.fleet(bundle, root, ["original", "new-node"], None)
    assert plan["verified_nodes"] == ["original", "new-node"]
    assert plan["opencode_provider"] == {"image": IMAGE, "shared_runtime": str(root / TREE)}
    assert plan["rollback_provider"] == {"image": ROLLBACK}
    assert plan["boundary_args"].count("--opencode-provider-image") == 2
    assert plan["boundary_args"][-1] == f"{IMAGE}={root / TREE}"
    with pytest.raises(ValueError, match="unique list"):
        release.fleet(bundle, root, ["original", "original"], None)


def test_existing_bad_version_is_preserved_without_loading_images(bundle, tmp_path, monkeypatch):
    version = tmp_path / TREE
    version.mkdir()
    marker = version / "damaged"
    marker.write_text("preserve for diagnosis")
    _, fingerprint = release.load_manifest(bundle)
    monkeypatch.setattr(release, "trusted_root", lambda root, **_: root)
    monkeypatch.setattr(release, "tree_digest", lambda path: "0" * 64)
    monkeypatch.setattr(release, "docker", lambda *_args, **_kw: pytest.fail("unexpected Docker mutation"))
    with pytest.raises(ValueError, match="host runtime tree digest mismatch"):
        release.apply_node(bundle, tmp_path, fingerprint)
    assert marker.read_text() == "preserve for diagnosis"
    assert not tuple(tmp_path.glob(".opencode-install-*"))
