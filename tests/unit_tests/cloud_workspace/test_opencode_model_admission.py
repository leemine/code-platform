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
    assert public["default_account_id"] == "registered"
    assert public_managed_model_policy({"models": {"defaults": []}}, policy)["default_account_id"] is None
    assert public["reasons"] == {
        "unsupported": "opencode_shared_model_options_unsupported",
        "unregistered": "opencode_model_not_registered",
    }
    assert "private-token" not in json.dumps(public)
    assert "example.invalid" not in json.dumps(public)
    catalog = ModelCatalog(config)
    assert managed_model_binding(policy, ModelSelection(type="model", id=f"opencode:{selector}")) == (
        managed_model_binding(policy, ModelSelection(type="model", id="registered"), catalog=catalog)
    )
    with pytest.raises(ValueError, match="opencode_model_not_registered"):
        managed_model_binding(policy, ModelSelection(type="model", id="opencode:other/other"))
    with pytest.raises(ValueError, match="must be declared"):
        deployment_model_policy({"model": "other/not-declared", "provider": {}})

    # A sync-capable Worker admits configured compatible models without an operator entry.
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode_models import account_model_providers
    sync = {"models": {}, "default": None, "account_model_sync": True}
    projected = public_managed_model_policy(config, sync)
    assert projected["default_account_id"] == "registered"
    assert managed_model_binding(sync, ModelSelection(type="model", id=projected["default"]["id"]), catalog=catalog) == (
        managed_model_binding(sync, ModelSelection(type="model", id="registered"), catalog=catalog)
    )
    assert projected["reasons"] == {"unsupported": "opencode_shared_model_options_unsupported"}
    fragment = account_model_providers(catalog)
    assert fragment == build_server_model_config(config)[0]["provider"]
    assert managed_model_binding(sync, ModelSelection(type="model", id="unregistered"), catalog=catalog)["providerID"] in fragment
    assert "private-token" not in json.dumps(projected)


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

@pytest.mark.parametrize("field", ["module", "permission", "file", "endpoint", "model"])
def test_sync_validates_only_generated_account_model_fields(field):
    from gateway.common.opencode_model_policy import validate_account_providers
    key = "swarm-" + "a" * 24
    entry = {"npm": "@ai-sdk/openai-compatible", "name": "Swarm configured model",
             "options": {"baseURL": "https://example.invalid", "apiKey": "fixture"},
             "models": {"m": {"name": "m"}}}
    if field == "module":
        entry["npm"] = "other-module"
    elif field == "permission":
        entry["permission"] = {}
    elif field == "file":
        entry["options"]["apiKey"] = "{file:example}"
    elif field == "endpoint":
        entry["options"]["baseURL"] = "file:///example"
    else:
        entry["models"]["m"]["extra"] = "invalid"
    with pytest.raises(ValueError):
        validate_account_providers({key: entry})


@pytest.mark.parametrize("auth_path, previous_path", [
    ("/provider/managed/opencode", "/provider/opencode"),
    ("/provider/opencode", "/provider/managed/opencode"),
])
def test_managed_session_settings_allow_only_same_gateway_route_alias(auth_path, previous_path):
    from jiuwenswarm.server.runtime.agent_adapter.providers import session_recovery
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode import OpenCodeAdapter

    origin = "https://gateway.example.invalid/api/organization"
    adapter = OpenCodeAdapter()
    adapter._relay_url = origin + auth_path
    adapter._recovery_settings = {"relay_url": adapter._relay_url, "relay_owner": {"actor_id": "first"}}
    settings = adapter._session_recovery_settings("project", True)
    previous = {**settings, "relay_url": origin + previous_path}
    binding = {"version": 2, "settings_revision": session_recovery.settings_revision(previous)}
    adapter._require_recovery_settings(binding, "project", True)
    with pytest.raises(ValueError, match="Provider configuration changed"):
        adapter._require_recovery_settings(binding, "different-project", True)
    other_origin = {**previous, "relay_url": "https://different.example.invalid/api/organization" + previous_path}
    binding["settings_revision"] = session_recovery.settings_revision(other_origin)
    with pytest.raises(ValueError, match="Provider configuration changed"):
        adapter._require_recovery_settings(binding, "project", True)
