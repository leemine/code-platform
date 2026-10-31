"""No-Core model settings keep the existing RPC, persistence and probe boundaries."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from gateway.common import model_vendor_registry
from jiuwenswarm.common import config, native_integration
from jiuwenswarm.common.config_panel import models_handlers
from jiuwenswarm.common.config_panel.model_resource_handlers import model_resource_handler


@pytest.fixture
def external(monkeypatch, tmp_path):
    monkeypatch.setattr(native_integration, "native_available", lambda: False)
    monkeypatch.setattr(model_vendor_registry, "native_available", lambda: False)
    monkeypatch.setattr(models_handlers, "native_available", lambda: False)
    path = tmp_path / "config.yaml"
    path.write_text("models:\n  defaults: []\n  groups: []\n", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_YAML_PATH", path)
    monkeypatch.setattr(config, "get_config_file", lambda: path)
    return path


def test_presets_remain_available_without_core(external):
    payload = model_vendor_registry.to_frontend_payload()
    assert payload["reasoning_available"] is False
    assert payload["reasoning"] is None
    assert payload["custom_api"]
    assert all(p["reasoning_capabilities"] == {} for p in payload["custom_api"])
    assert all(p["reasoning_rules"] == [] for p in payload["custom_api"])


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,base,path", [
    ("OpenAI", "https://model.invalid/v1", "/v1/chat/completions"),
    ("Anthropic", "https://model.invalid/anthropic", "/anthropic/v1/messages"),
    ("Anthropic", "https://model.invalid/v1/", "/v1/messages"),
])
async def test_connection_rpc_then_resource_save_edit_and_reload(external, monkeypatch, provider, base, path):
    seen = []
    async def post(client, url, *, headers, json):
        request = httpx.Request("POST", url, headers=headers, json=json)
        seen.append(request)
        assert request.url.path == path
        if provider == "Anthropic":
            assert request.headers["x-api-key"] == "fixture-key"
            assert request.headers["anthropic-version"] == "2023-06-01"
            body = {"content": [{"type": "text", "text": "Hello"}], "usage": {"output_tokens": 1}}
        else:
            assert request.headers["authorization"] == "Bearer fixture-key"
            body = {"choices": [{"message": {"content": "Hello"}}]}
        return httpx.Response(200, json=body, request=request)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    channel = SimpleNamespace(send_response=AsyncMock())
    await models_handlers.config_validate_model_handler(channel, None, "probe", {
        "model_provider": provider, "model": "shared", "api_base": base, "api_key": "fixture-key",
    })
    assert channel.send_response.call_args.kwargs["ok"]
    assert len(seen) == 1
    entry = {"model_client_config": {
        "client_provider": provider, "model_name": "shared", "api_base": base,
        "api_key": "fixture-key", "verify_ssl": True,
    }, "model_config_obj": {}, "alias": "before", "is_default": True}
    await model_resource_handler(channel, None, "save", {"model": entry}, "", operation="models.upsert")
    saved = channel.send_response.call_args.kwargs
    assert saved["ok"], saved
    model_id = saved["payload"]["model"]["model_id"]
    await model_resource_handler(channel, None, "edit", {"model": {"model_id": model_id, "alias": "after"}}, "", operation="models.upsert")
    assert channel.send_response.call_args.kwargs["ok"]
    await model_resource_handler(channel, None, "reload", {"model_id": model_id}, "", operation="models.get")
    loaded = channel.send_response.call_args.kwargs["payload"]["model"]
    assert loaded["alias"] == "after"
    assert loaded["model_client_config"]["api_key"] == "fixture-key"
    assert loaded["model_client_config"]["client_provider"] == provider
    assert loaded["is_default"]
    assert config.get_config_raw()["models"]["defaults"][0]["model_id"] == model_id


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "empty"])
async def test_connection_failure_is_not_success_and_does_not_expose_credentials(external, monkeypatch, failure):
    async def post(client, url, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(401 if failure == "http" else 200,
                              json={"error": "fixture-secret", "content": [], "usage": {"output_tokens": 0}},
                              request=request)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    channel = SimpleNamespace(send_response=AsyncMock())
    await models_handlers.config_validate_model_handler(channel, None, "probe", {
        "model_provider": "Anthropic", "model": "shared", "api_base": "https://model.invalid", "api_key": "fixture-secret",
    })
    reply = channel.send_response.call_args.kwargs
    assert not reply["ok"]
    assert "fixture-secret" not in str(reply)
    assert not config.get_config_raw()["models"]["defaults"]


def test_legacy_save_default_passes_explicit_reasoning_rejected_without_mutation(external):
    base = {"model_name": "shared", "model_provider": "Anthropic", "api_base": "https://model.invalid",
            "api_key": "fixture-key", "vendor_key": "custom", "plan": "custom_api"}
    assert models_handlers.build_models_defaults_from_frontend([base])
    before = external.read_bytes()
    with pytest.raises(ValueError, match="Explicit reasoning"):
        models_handlers.build_models_defaults_from_frontend([{**base, "reasoning_level": "high"}])
    assert external.read_bytes() == before
