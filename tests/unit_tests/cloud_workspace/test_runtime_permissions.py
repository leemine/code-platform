"""Deployment defaults must reach the original panel and Codex host unchanged."""
from pathlib import Path

import pytest
import yaml

from tests.unit_tests.agentserver.test_codex_direct_adapter import host, request, consume


@pytest.mark.asyncio
async def test_deployment_default_preserves_explicit_selection_and_restore(host, monkeypatch):
    from jiuwenswarm.server.control import config_service

    fragment = Path(__file__).resolve().parents[3] / "deploy/cloud-workspace/runtime-permissions.yaml.example"
    settings = yaml.safe_load(fragment.read_text())
    monkeypatch.setattr(config_service, "_read_raw_config", lambda: settings)
    assert config_service.get_panel()["permissions_enabled"] == "true"
    app, config, clients, _, _ = host
    config.update(settings)
    await app.create_instance(config)
    try:
        await consume(app.process_message_stream(request()))
        thread = clients[-1].thread_id
        assert clients[-1].options["sandbox"] == "workspace-write"
        assert clients[-1].options["approvalPolicy"] == "on-request"
        assert app.runtime_permission_status("one")["effective_profile"] == "default"
        # Only the existing explicit user choice may broaden a later turn.
        await app.reload_agent_config(config_base={"permissions": {"enabled": False, "mode": "manual"}},
                                      target_session_id="one", reload_scopes=["permissions"])
        assert clients[-1].options["sandbox"] == "workspace-write"
        await consume(app.process_message_stream(request()))
        assert clients[-1].thread_id == thread
        assert clients[-1].options["sandbox"] == "danger-full-access"
        # Returning to the deployment profile restores the same conversation.
        await app.reload_agent_config(config_base=settings, target_session_id="one", reload_scopes=["permissions"])
        await consume(app.process_message_stream(request()))
        assert clients[-1].thread_id == thread
        assert clients[-1].options["sandbox"] == "workspace-write"
        assert clients[-1].options["approvalPolicy"] == "on-request"
    finally:
        await app.cleanup()
