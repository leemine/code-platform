import json

import pytest

from gateway.common.model_selection import ModelSelection
from gateway.common.opencode_model_policy import deployment_model_policy
from jiuwenswarm.server.runtime.agent_adapter.providers.opencode_models import (
    build_server_model_config,
    managed_model_binding,
    public_managed_model_policy,
)
from jiuwenswarm.common.model_catalog import ModelCatalog


def test_managed_model_projection_uses_the_native_default_and_hides_credentials():
    entry = {
        "model_id": "registered",
        "is_default": True,
        "model_client_config": {
            "api_key": "private-token",
            "api_base": "https://example.invalid/v1",
            "model_name": "example-model",
            "client_provider": "OpenAI",
        },
    }
    config = {"models": {"defaults": [
        entry,
        {"model_id": "unsupported", "model_client_config": dict(
            entry["model_client_config"], model_name="unsupported-model", stream_idle_timeout=15)},
        {"model_id": "unregistered", "model_client_config": dict(
            entry["model_client_config"], model_name="unregistered-model")},
    ]}}
    registered, _ = build_server_model_config({"models": {"defaults": [entry]}})
    selector = next(iter(registered["provider"])) + "/example-model"
    registered["model"] = selector
    policy = deployment_model_policy(registered)
    public = public_managed_model_policy(config, policy)
    assert public["default"]["id"] == f"opencode:{selector}"
    assert public["reasons"] == {
        "unsupported": "opencode_shared_model_options_unsupported",
        "unregistered": "opencode_model_not_registered",
    }
    assert "private-token" not in json.dumps(public)
    assert "example.invalid" not in json.dumps(public)
    catalog = ModelCatalog(config)
    assert managed_model_binding(policy, ModelSelection(type="model", id=public["default"]["id"])) == (
        managed_model_binding(policy, ModelSelection(type="model", id="registered"), catalog=catalog)
    )
    with pytest.raises(ValueError, match="opencode_model_not_registered"):
        managed_model_binding(policy, ModelSelection(type="model", id="opencode:other/other"))
    with pytest.raises(ValueError, match="must be declared"):
        deployment_model_policy({"model": "other/not-declared", "provider": {}})


@pytest.mark.asyncio
async def test_managed_worker_inherits_approval_without_changing_account_settings(monkeypatch):
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode import OpenCodeAdapter

    monkeypatch.setenv("JIUWENSWARM_OPENCODE_RELAY_URL", "https://gateway.example.invalid/provider/opencode")
    monkeypatch.setattr(OpenCodeAdapter, "_configure_relay", lambda *args: None)
    adapter = OpenCodeAdapter()
    config = {"permissions": {"enabled": False}, "opencode": {}}
    await adapter.create_instance(config)
    assert config["permissions"]["enabled"] is False
    await adapter.reload_agent_config({"permissions": {"mode": "auto"}})
    status = adapter.runtime_permission_status("new")
    assert status["desired_profile"] == "default"
    assert status["supported_profiles"] == ["default"]
