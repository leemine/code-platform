"""Real filesystem regression of the original HTTP/E2A workspace boundary."""
import base64
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from jiuwenswarm.server.runtime.gateway_adapter import workspace_file_io as io


@pytest.fixture
def roots(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"private-marker")
    monkeypatch.setenv("JIUWENSWARM_CONTAINER_FILE_ROOT", str(root))
    return root, outside


def call(root, op, path="", **kw):
    return io.execute(op, {"path": str(root / path), **kw})


def test_file_roundtrip_and_list_contract(roots):
    root, _ = roots
    assert call(root, "mkdir", "docs/deep", recursive=True)["created"]
    assert not call(root, "mkdir", "docs/deep", recursive=True)["created"]
    call(root, "write", "docs/a.md", data_base64=base64.b64encode(b"one").decode())
    call(root, "write", "docs/a.md", offset=3, data_base64=base64.b64encode(b"two").decode())
    result = call(root, "read", "docs/a.md", offset=2, limit=3)
    assert base64.b64decode(result["data_base64"]) == b"etw"
    assert not result["eof"] and result["size"] == 6
    items = call(root, "list", recursive=True)["items"]
    assert any(x["is_directory"] and x["name"] == "deep" for x in items)
    assert any(x["type"] == ".md" and x["size"] == 6 for x in items)
    call(root, "write", "empty.txt", data_base64="")
    assert call(root, "read", "empty.txt")["eof"]


@pytest.mark.parametrize("op,tail", [("read", "secret.txt"), ("write", "secret.txt"), ("list", ""), ("mkdir", "new")])
def test_parent_symlink_denied_without_outside_side_effect(roots, op, tail):
    root, outside = roots
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(io.WorkspaceFileError):
        call(root, op, str(Path("link") / tail), data_base64="eA==", recursive=True)
    assert (outside / "secret.txt").read_bytes() == b"private-marker"
    assert not (outside / "new").exists()


@pytest.mark.parametrize("op", ["read", "write", "mkdir", "list"])
def test_final_symlink_denied(roots, op):
    root, outside = roots
    (root / "link").symlink_to(outside / "secret.txt")
    with pytest.raises(io.WorkspaceFileError):
        call(root, op, "link", data_base64="eA==")
    assert (outside / "secret.txt").read_bytes() == b"private-marker"
    assert call(root, "list")["items"] == []


@pytest.mark.parametrize("op", ["read", "write"])
@pytest.mark.parametrize("kind", ["fifo", "hardlink"])
def test_special_and_hardlinked_files_denied(roots, op, kind):
    root, outside = roots
    if kind == "fifo":
        os.mkfifo(root / "target")
    else:
        os.link(outside / "secret.txt", root / "target")
    with pytest.raises(io.WorkspaceFileError):
        call(root, op, "target", data_base64="eA==")
    assert (outside / "secret.txt").read_bytes() == b"private-marker"


@pytest.mark.parametrize("op", ["read", "write", "list", "mkdir"])
def test_directory_replacement_race_pins_original_fd(roots, monkeypatch, op):
    root, outside = roots
    (root / "nested").mkdir()
    (root / "nested/secret.txt").write_bytes(b"safe")
    original = os.open
    switched = False

    def swap_after_open(path, flags, *args, **kw):
        nonlocal switched
        fd = original(path, flags, *args, **kw)
        if path == "nested" and not switched:
            switched = True
            (root / "nested").rename(root / "saved")
            (root / "nested").symlink_to(outside, target_is_directory=True)
        return fd
    monkeypatch.setattr(io.os, "open", swap_after_open)
    tail = "" if op == "list" else ("new" if op == "mkdir" else "secret.txt")
    result = call(root, op, str(Path("nested") / tail), data_base64="eA==")
    if op == "read":
        assert base64.b64decode(result["data_base64"]) == b"safe"
    assert (outside / "secret.txt").read_bytes() == b"private-marker"
    assert not (outside / "new").exists()


@pytest.mark.parametrize("path", ["../private/secret.txt", "a/../../private", "a\x00b"])
def test_lexical_traversal_denied(roots, path):
    root, _ = roots
    with pytest.raises(io.WorkspaceFileError):
        call(root, "read", path)


def test_missing_scope_is_fail_closed(monkeypatch):
    monkeypatch.delenv("JIUWENSWARM_CONTAINER_FILE_ROOT", raising=False)
    with pytest.raises(io.WorkspaceFileError, match="not configured"):
        io.execute("read", {"path": "/etc/passwd"})


@pytest.mark.asyncio
async def test_real_adapter_bridge_chunks_and_denial(roots, monkeypatch):
    from jiuwenswarm.common.schema.agent import AgentRequest
    from jiuwenswarm.server.runtime.gateway_adapter.workspace_file_adapter import WorkspaceFileAdapter
    from gateway.routing import e2a_proxy
    from gateway.routing.workspace_files import workspace_file_request
    from gateway.routing.container_files import AgentOSFileTransferError
    root, outside = roots
    adapter = WorkspaceFileAdapter()

    async def forward(**kw):
        result = await adapter.handle(AgentRequest(request_id="file-test", channel_id=kw["channel_id"],
            session_id=kw["session_id"], req_method=kw["req_method"], params=kw["params"], user_id=kw["user_id"]))
        return result.ok, result.payload
    monkeypatch.setattr(e2a_proxy, "fetch_agent_unary", forward)
    content = b"abcdef" * 100000
    await workspace_file_request(None, "write", user_id="owner", path=str(root / "large.bin"), content=content)
    assert (root / "large.bin").read_bytes() == content
    chunk = await workspace_file_request(None, "read", user_id="owner", path=str(root / "large.bin"), limit=32)
    assert chunk.data == content[:32]
    (root / "secret").symlink_to(outside / "secret.txt")
    with pytest.raises(AgentOSFileTransferError):
        await workspace_file_request(None, "read", user_id="owner", path=str(root / "secret"))
    with pytest.raises(AgentOSFileTransferError):
        await workspace_file_request(None, "read", user_id="owner", instance_id="other", path=str(root / "large.bin"))


@pytest.mark.asyncio
async def test_router_cloud_files_never_fall_back(monkeypatch):
    from gateway.extensions.agentos.agentos_router.router_client import AgentOSRouterClient
    from gateway.routing import workspace_files
    from gateway.routing.container_files import AgentOSFileTransferError
    client = object.__new__(AgentOSRouterClient)
    client._instance_lifecycle = object()
    rpc = AsyncMock(side_effect=AgentOSFileTransferError("unavailable", code="SERVICE_UNAVAILABLE"))
    monkeypatch.setattr(workspace_files, "workspace_file_request", rpc)
    for method, params in [("download_container_file", {"path": "/home/agentos/a"}),
                           ("upload_container_file", {"path": "a", "content": b"x"}),
                           ("list_container_files", {"dir_path": "/home/agentos"}),
                           ("mkdir_container_dir", {"path": "/home/agentos/a"})]:
        with pytest.raises(AgentOSFileTransferError):
            await getattr(client, method)(user_id="owner", **params)
    assert rpc.await_count == 4


def test_mkdir_restrictive_final_mode_preserves_success(roots):
    root, _ = roots
    result = call(root, "mkdir", "private/closed", recursive=True, mode="000")
    assert result["created"] is True
    assert (root / "private/closed").stat().st_mode & 0o777 == 0
    assert (root / "private").stat().st_mode & 0o700 == 0o700
    (root / "private/closed").chmod(0o700)
