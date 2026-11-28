from types import SimpleNamespace

import pytest

from gateway.common.security import worker_permission
from jiuwenswarm.common.adapter_capabilities import AdapterCapabilities
from jiuwenswarm.server.runtime.agent_adapter.execution_input import ExecutionInputPolicy, prepare_execution_input
from jiuwenswarm.server.runtime.session import session_metadata


@pytest.fixture
def workers(monkeypatch, tmp_path):
    monkeypatch.delenv(worker_permission.WORKER_PERMISSION_KEY_FILE_ENV, raising=False)
    monkeypatch.setattr(worker_permission, "get_root_dir", lambda: tmp_path)
    facts = {"user_id": "alice", "project_id": "shared-code", "project_dir": str(tmp_path),
             "execution_provider": "opencode-direct"}
    records = {sid: dict(facts) for sid in ("worker", "ordinary")}
    monkeypatch.setattr(session_metadata, "get_session_metadata", lambda sid, **_: dict(records[sid]))

    def patch(sid, fields):
        records[sid].update(fields)
        return dict(records[sid])

    monkeypatch.setattr(session_metadata, "patch_session_metadata", patch)
    adapter = SimpleNamespace(
        capabilities=AdapterCapabilities(worker_permission_profile=True),
        execution_input_policy=lambda _: ExecutionInputPolicy(require_model=False),
        has_session_runtime=lambda _: True,
    )
    key = worker_permission.WORKER_PERMISSION_KEY
    signature = worker_permission.sign_full_access(
        "worker", "alice", "shared-code", "opencode-direct", turn=("1", "write once"),
    )
    return adapter, tmp_path, records, key, signature


def test_worker_policy_follows_its_platform_session(workers):
    adapter, project, records, key, signature = workers
    request = SimpleNamespace(request_id="1", session_id="worker", user_id="alice",
                              params={key: signature, "query": "write once"})
    execution = prepare_execution_input(adapter, request, {"project_dir": str(project)})
    assert execution.session.worker_permission_profile == "full_access"
    assert records["worker"][key] != signature
    request.request_id = "2"
    request.params[key] = worker_permission.sign_full_access(
        "worker", "alice", "shared-code", "opencode-direct", turn=("2", "write once"),
    )
    assert prepare_execution_input(adapter, request, {"project_dir": str(project)}).session.worker_permission_profile == "full_access"


def test_ordinary_session_cannot_copy_worker_policy(workers):
    adapter, project, records, key, signature = workers
    request = SimpleNamespace(request_id="2", session_id="ordinary", user_id="alice", params={})
    assert prepare_execution_input(adapter, request, {"project_dir": str(project)}).session.worker_permission_profile is None
    request.params = {key: signature, "query": "write once"}
    with pytest.raises(ValueError, match="Invalid application Worker permission grant"):
        prepare_execution_input(adapter, request, {"project_dir": str(project)})
    assert key not in records["ordinary"]


def test_worker_policy_rejects_a_changed_owner_or_provider(workers):
    adapter, project, records, key, signature = workers
    request = SimpleNamespace(request_id="1", session_id="worker", user_id="bob",
                              params={key: signature, "query": "write once"})
    with pytest.raises(ValueError, match="Invalid application Worker permission grant"):
        prepare_execution_input(adapter, request, {"project_dir": str(project)})
    request.user_id = "alice"
    records["worker"]["execution_provider"] = "codex-direct"
    with pytest.raises(ValueError, match="Invalid application Worker permission grant"):
        prepare_execution_input(adapter, request, {"project_dir": str(project)})


def test_provider_must_declare_the_worker_policy_capability(workers):
    adapter, project, records, key, signature = workers
    adapter.capabilities = AdapterCapabilities()
    request = SimpleNamespace(request_id="4", session_id="worker", user_id="alice", params={key: signature})
    with pytest.raises(ValueError, match="provider_capability_unsupported: worker_permission_profile"):
        prepare_execution_input(adapter, request, {"project_dir": str(project)})
    assert key not in records["worker"]


def test_worker_rejects_unsigned_and_replayed_turns(workers):
    adapter, project, records, key, signature = workers
    request = SimpleNamespace(request_id="1", session_id="worker", user_id="alice",
                              params={key: signature, "query": "write once"})
    prepare_execution_input(adapter, request, {"project_dir": str(project)})
    for invalid in ({}, {key: records["worker"][key]}, {key: signature, "query": "other input"}):
        request.params = {"query": "write once", **invalid}
        with pytest.raises(ValueError, match="Invalid application Worker permission grant"):
            prepare_execution_input(adapter, request, {"project_dir": str(project)})
    request.request_id = "different-request"
    request.params = {key: signature, "query": "write once"}
    with pytest.raises(ValueError, match="Invalid application Worker permission grant"):
        prepare_execution_input(adapter, request, {"project_dir": str(project)})


def test_web_file_projection_excludes_worker_key(workers, monkeypatch):
    from jiuwenswarm.channels.web.app_web import _SpaStaticHandler
    from jiuwenswarm.common.file_download_token import WebFileDownloadManager

    _, project, _, _, _ = workers
    monkeypatch.setattr(_SpaStaticHandler, "workspace_root", str(project))
    download = WebFileDownloadManager(secret="test-secret")
    ordinary_path = project / "readme.md"
    assert _SpaStaticHandler._is_path_under_allowed_root(ordinary_path)
    assert download.validate_token(download.generate_token(str(ordinary_path), "worker"))
    for name in (worker_permission.WORKER_PERMISSION_KEY_FILE, "custom-key"):
        key = project / name
        existing_token = download._sign_payload({"path": str(key), "sid": "worker"})
        if name == "custom-key":
            monkeypatch.setenv(worker_permission.WORKER_PERMISSION_KEY_FILE_ENV, str(key))
        assert not _SpaStaticHandler._is_path_under_allowed_root(key)
        with pytest.raises(ValueError, match="Worker signing key cannot be transferred"):
            download.generate_token(str(key), "worker")
        assert download.validate_token(existing_token) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ("opencode", "codex", "claude"))
async def test_provider_reload_preserves_only_the_worker_override(provider, tmp_path):
    if provider == "opencode":
        from jiuwenswarm.server.runtime.agent_adapter.providers.opencode import OpenCodeAdapter, _Session

        adapter = OpenCodeAdapter(mode="code")
        ordinary = _Session("normal", str(tmp_path), active=True)
        worker = _Session("worker", str(tmp_path), active=True, worker_permission_profile="full_access")
    elif provider == "codex":
        from jiuwenswarm.server.runtime.agent_adapter.providers.codex import CodexAdapter, Session

        adapter = CodexAdapter(mode="code")
        ordinary = Session(str(tmp_path), tmp_path)
        worker = Session(str(tmp_path), tmp_path, worker_permission_profile="full_access")
    else:
        from jiuwenswarm.server.runtime.agent_adapter.providers.claude import ClaudeAdapter, Session

        adapter = ClaudeAdapter(mode="code")
        ordinary = Session(str(tmp_path), tmp_path)
        worker = Session(str(tmp_path), tmp_path, worker_permission_profile="full_access")

    adapter._sessions.update(normal=ordinary, worker=worker)
    await adapter.reload_agent_config(config_base={"permissions": {"enabled": True}})
    assert ordinary.desired_permission == "default"
    assert worker.desired_permission == "full_access"
