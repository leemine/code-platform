"""Exercise directory operations through the registered AgentServer adapter."""
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.runtime.gateway_adapter import WorkspaceFileAdapter
from jiuwenswarm.server.runtime.gateway_adapter import project_workspace as workspace
from jiuwenswarm.server.runtime.session import project_store


@pytest.fixture
def roots(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(workspace, "get_agent_workspace_dir", lambda: root)
    monkeypatch.setattr(project_store, "get_agent_root_dir", lambda: tmp_path)
    project_store.invalidate_cache()
    yield root
    project_store.invalidate_cache()


async def call(operation, **params):
    return await WorkspaceFileAdapter().handle(AgentRequest(
        request_id="directory-test", channel_id="web", session_id="",
        req_method=ReqMethod.PATH_SELECT_DIRECTORY,
        params={"workspace_operation": operation, "work_mode": "code", **params},
    ))


@pytest.mark.asyncio
async def test_create_browse_open_real_project(roots):
    first = await call("list", path="")
    assert first.ok and first.payload["items"] == []
    created = await call("mkdir", path="", name="demo")
    assert created.ok and (roots / "code/demo").is_dir()
    listed = await call("list", path="")
    assert listed.payload["items"] == [{"name": "demo", "path": "demo"}]
    opened = await call("open", path="demo")
    assert opened.ok, opened.payload
    project = opened.payload["project"]
    assert project["project_dir"] == str(roots / "code/demo")
    assert project_store.get_project_by_id(project["project_id"], cache_bust=True).project_dir == project["project_dir"]
    repeated = await call("open", path="demo")
    assert repeated.payload["project"]["project_id"] == project["project_id"]
    duplicate = await call("mkdir", path="", name="demo")
    assert not duplicate.ok and duplicate.payload["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_boundaries_pagination_and_no_hidden_paths(roots, tmp_path):
    await call("list", path="")
    base = roots / "code"
    for i in range(105): (base / f"folder-{i:03}").mkdir()
    (base / ".private").mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    (base / "escape").symlink_to(outside, target_is_directory=True)
    page = await call("list", path="")
    assert page.ok and len(page.payload["items"]) == 100 and page.payload["next_offset"] == 100
    last = await call("list", path="", offset=100)
    assert last.ok and len(last.payload["items"]) == 5 and last.payload["next_offset"] is None
    for path in ["../outside", "/tmp", ".private", "escape", "a//b", "a\\b"]:
        result = await call("mkdir", path=path, name="bad")
        assert not result.ok, path
    assert not (outside / "bad").exists()
    assert not (await call("mkdir", path="", name="../bad")).ok
    assert not (await call("open", path="")).ok


@pytest.mark.asyncio
async def test_existing_project_subdirectory_cannot_create_second_project(roots):
    await call("mkdir", path="", name="demo")
    project = (await call("open", path="demo")).payload["project"]
    await call("mkdir", path="demo", name="nested")
    nested = await call("open", path="demo/nested")
    assert not nested.ok and nested.payload["code"] == "PROJECT_ROOT_REQUIRED"
    assert len([p for p in project_store.list_projects() if p.project_id == project["project_id"]]) == 1
