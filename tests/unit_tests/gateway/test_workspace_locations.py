"""Location discovery and original Gateway-to-Agent directory chain."""
from types import SimpleNamespace

import pytest
from gateway.routing.agent_client import WebSocketAgentServerClient
from gateway.routing.workspace_locations import catalog, entry_url
from gateway.channel_manager.web.app_web_handlers import WebHandlersBindParams, _register_web_handlers
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.runtime.gateway_adapter import WorkspaceFileAdapter
from jiuwenswarm.server.runtime.gateway_adapter import project_workspace
from jiuwenswarm.server.runtime.session import project_store


class Channel:
    channel_id = "web"
    def __init__(self):
        self.methods = {}; self.responses = []
    def register_method(self, name, handler): self.methods[name] = handler
    def on_connect(self, handler): pass
    def on_disconnect(self, handler): pass
    async def send_response(self, ws, req_id, **result): self.responses.append(result)


class LocalClient(WebSocketAgentServerClient):
    def __init__(self): self.requests = []
    @property
    def server_ready(self): return True
    async def send_request(self, env, timeout=None):
        self.requests.append(env)
        return await WorkspaceFileAdapter().handle(AgentRequest(
            request_id=env.request_id, channel_id=env.channel, session_id=env.session_id,
            req_method=ReqMethod(env.method), params=env.params, user_id=env.user_id,
        ))


def test_catalog_is_server_owned(monkeypatch):
    monkeypatch.setenv("CODE_PLATFORM_CLOUD_ENTRY_URL", "https://cloud.example.test")
    result = catalog(LocalClient())
    assert result["kind"] == "local"
    assert result["entries"][1]["url"] == "https://cloud.example.test/"
    with pytest.raises(ValueError): catalog(SimpleNamespace())
    for url in ["http://untrusted.test", "javascript:alert(1)", "https://user:pass@cloud.test", "https://cloud.test/chat/a", "https://cloud.test/?token=a"]:
        monkeypatch.setenv("CODE_PLATFORM_CLOUD_ENTRY_URL", url)
        with pytest.raises(ValueError): entry_url("cloud")
    monkeypatch.setenv("CODE_PLATFORM_LOCAL_ENTRY_URL", "http://127.0.0.1:18080")
    assert entry_url("local") == "http://127.0.0.1:18080/"


@pytest.mark.asyncio
async def test_registered_gateway_directory_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(project_workspace, "get_agent_workspace_dir", lambda: tmp_path / "workspace")
    monkeypatch.setattr(project_store, "get_agent_root_dir", lambda: tmp_path)
    project_store.invalidate_cache()
    client = LocalClient(); channel = Channel()
    _register_web_handlers(WebHandlersBindParams(channel=channel, agent_client=client))
    async def call(name, params, session="web-transport-correlation"):
        await channel.methods[name](None, "request-1", params, session, user_id="owner")
        return channel.responses[-1]
    assert (await call("workspace.locations", {}))["payload"]["kind"] == "local"
    assert (await call("project.workspace.list", {"path": ""}))["ok"]
    assert (await call("project.workspace.mkdir", {"path": "", "name": "project-a"}))["ok"]
    assert (tmp_path / "workspace/code/project-a").is_dir()
    opened = await call("project.workspace.open", {"path": "project-a"})
    assert opened["ok"], opened
    project = opened["payload"]["project"]
    assert project_store.get_project_by_id(project["project_id"], cache_bust=True).project_dir == project["project_dir"]
    assert client.requests[-1].user_id == "owner"
    count = len(client.requests)
    for params, session in [({"work_mode": "work"}, None), ({"path": "", "execution_target": "other"}, None), ({"path": "", "user_id": "other"}, None), ({"path": "", "session_id": "existing-session"}, "existing-session")]:
        assert not (await call("project.workspace.list", params, session))["ok"]
    assert len(client.requests) == count
    project_store.invalidate_cache()
