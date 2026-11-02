# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Front settings retain external CLI payloads without Runtime dependencies."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from jiuwenswarm.common import custom_agent_runtime
from jiuwenswarm.common.config_panel.external_cli_read import (
    flatten_external_cli_agents_for_config_panel,
)
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.control import config_service


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "custom-agents"
    root.mkdir()
    monkeypatch.setattr(custom_agent_runtime, "custom_agents_root", lambda: root)
    return root / "agents.json"


def test_external_cli_read_preserves_legacy_entries_and_custom_paths(registry: Path) -> None:
    raw = {
        "modes": {"team": {"jiuwen_team": {"external_cli_agents": [
            " claude ",
            {"cli_agent": "codex", "codex_bin": " /opt/codex "},
            {"cli_agent": "unknown", "cli_path": "/opt/unknown"},
            None,
        ]}}},
    }
    original = deepcopy(raw)

    flat = flatten_external_cli_agents_for_config_panel(raw)

    assert flat == {
        "external_cli_agent_claude_enabled": "true",
        "external_cli_agent_claude_use_builtin": "true",
        "external_cli_agent_claude_cli_path": "",
        "external_cli_agent_claude_path_histories": "[]",
        "external_cli_agent_codex_enabled": "true",
        "external_cli_agent_codex_use_builtin": "false",
        "external_cli_agent_codex_cli_path": "/opt/codex",
        "external_cli_agent_codex_path_histories": "[]",
    }
    assert raw == original


def test_external_cli_read_exposes_persisted_path_histories() -> None:
    raw = {
        "modes": {
            "team": {
                "jiuwen_team": {
                    "external_cli_agents": [{"cli_agent": "codex", "cli_path": "/opt/codex"}],
                    "external_cli_path_histories": {"codex": ["/old/codex", " ", "/old/codex"]},
                },
            },
        },
    }

    flat = flatten_external_cli_agents_for_config_panel(raw)

    assert flat["external_cli_agent_codex_path_histories"] == json.dumps(["/old/codex"])
    assert flat["external_cli_agent_claude_path_histories"] == "[]"


@pytest.mark.parametrize("raw", [{}, {"modes": None}, {"modes": {"team": []}}])
def test_external_cli_read_defaults_disabled_with_incomplete_config(registry: Path, raw: dict) -> None:
    flat = flatten_external_cli_agents_for_config_panel(raw)

    assert flat["external_cli_agent_claude_enabled"] == "false"
    assert flat["external_cli_agent_codex_enabled"] == "false"
    assert flat["external_cli_agent_claude_use_builtin"] == "false"
    assert flat["external_cli_agent_codex_cli_path"] == ""


@pytest.mark.asyncio
async def test_front_panel_observes_current_custom_agent_registry(
    registry: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    registry.write_text(json.dumps({
        "acme": {"version": "0.2", "summary": "测试提供方", "cli_path": "/uploaded/acme"},
        "provider_only": {"version": "1.0", "summary": "No CLI"},
    }), encoding="utf-8")
    raw = {"modes": {"team": {"jiuwen_team": {"external_cli_agents": [
        {"cli_agent": "acme", "cli_path": "/uploaded/acme"},
        {"cli_agent": "provider_only"},
    ]}}}}
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(config_service, "get_config_file", lambda: config_file)
    request = AgentRequest(request_id="panel", channel_id="web", req_method=ReqMethod.CONFIG_GET)

    response = await config_service.handle_config_request(request)

    assert response.ok is True
    assert response.request_id == "panel"
    payload = response.payload
    assert payload["external_cli_agent_acme_enabled"] == "true"
    assert payload["external_cli_agent_acme_use_builtin"] == "true"
    assert payload["external_cli_agent_acme_cli_path"] == ""
    assert payload["external_cli_agent_provider_only_use_builtin"] == "true"
    assert json.loads(payload["external_cli_custom_agents"]) == [
        {"name": "acme", "version": "0.2", "summary": "测试提供方", "has_cli": True},
        {"name": "provider_only", "version": "1.0", "summary": "No CLI", "has_cli": False},
    ]
    assert "测试提供方" in payload["external_cli_custom_agents"]

    raw["modes"]["team"]["jiuwen_team"]["external_cli_agents"][0]["cli_path"] = "/system/acme"
    config_file.write_text(yaml.safe_dump(raw), encoding="utf-8")
    changed = config_service.get_panel()
    assert changed["external_cli_agent_acme_use_builtin"] == "false"
    assert changed["external_cli_agent_acme_cli_path"] == "/system/acme"

    registry.write_text("{}", encoding="utf-8")
    removed = config_service.get_panel()
    assert removed["external_cli_custom_agents"] == "[]"
    assert "external_cli_agent_acme_enabled" not in removed


def test_front_config_payload_with_custom_agents_blocks_runtime_imports(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    custom_dir = tmp_path / "runtime" / "custom-agents"
    custom_dir.mkdir(parents=True)
    (custom_dir / "agents.json").write_text(json.dumps({
        "acme": {"version": "2.0", "summary": "Current registry", "cli_path": "/uploaded/acme"},
    }), encoding="utf-8")
    raw = {"modes": {"team": {"jiuwen_team": {"external_cli_agents": ["claude", "codex", "acme"]}}}}
    (config_dir / "config.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    code = '''
import importlib.abc
import json
import sys
prefixes = ("openjiuwen", "mcp", "jiuwenswarm.common.config",
            "jiuwenswarm.common.config_panel.config_set_handlers",
            "jiuwenswarm.server.runtime.agent_adapter", "jiuwenswarm.agents.harness")
class ImportBoundary(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
            raise AssertionError("Front attempted Runtime import: " + name)
sys.meta_path.insert(0, ImportBoundary())
from jiuwenswarm.server.control.config_service import get_panel
payload = get_panel()
catalog = {item["id"]: item for item in json.loads(payload["execution_provider_catalog"])}
assert catalog["opencode-direct"]["available"] is True
assert catalog["codex-direct"]["available"] is True
assert payload["external_cli_agent_claude_enabled"] == "true"
assert payload["external_cli_agent_acme_enabled"] == "true"
assert payload["external_cli_agent_acme_use_builtin"] == "true"
assert json.loads(payload["external_cli_custom_agents"]) == [
    {"name": "acme", "version": "2.0", "summary": "Current registry", "has_cli": True}]
loaded = [name for name in sys.modules
          if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)]
assert loaded == [], loaded
print(json.dumps({"forbidden": loaded, "custom_agent": "acme"}))
'''
    env = {
        **os.environ,
        "PYTHONPATH": str(root),
        "JIUWENSWARM_DATA_DIR": str(tmp_path),
        "PYTHONIOENCODING": "utf-8",
    }

    result = subprocess.run(
        [sys.executable, "-c", code], cwd=root, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["forbidden"] == []


def test_native_timeout_options_remain_provider_specific():
    from gateway.common.model_selection import ResolvedModel
    from jiuwenswarm.common import claude_adapter_config as cc, codex_adapter_config as cx
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode_models import provider_config
    raw = {'modes': {'team': {'jiuwen_team': {'external_cli_agents': [
        {'cli_agent':'claude', 'stream_first_byte_timeout_ms':90000, 'stream_idle_timeout_ms':600000},
        {'cli_agent':'codex', 'stream_idle_timeout_ms':45000},
    ]}}}}
    model = ResolvedModel(model_id='fixture', source='defaults', model_name='fixture', provider='OpenAI', api_base='https://example.invalid/v1', api_key='fixture', client_options={'timeout':1.25})
    env = cc.native_timeout_env(cc.config_snapshot(raw)['claude'], model)
    assert env == {'API_TIMEOUT_MS':'1250', 'CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS':'90000', 'CLAUDE_STREAM_IDLE_TIMEOUT_MS':'600000'}
    options = cx.model_overrides(model, cx.config_snapshot(raw)['codex'])
    assert 'model_providers.swarm.stream_idle_timeout_ms=45000' in options
    assert not any('1250' in x for x in options)  # Request time is not SSE idle time.
    oc = provider_config(model, {'header_timeout_ms':70000, 'chunk_timeout_ms':80000})['options']
    assert oc['timeout'] == 1250
    assert oc['headerTimeout'] == 70000
    assert oc['chunkTimeout'] == 80000


@pytest.mark.parametrize('value', [False, 0, -1, float('inf'), '5000'])
@pytest.mark.parametrize('provider', ['claude', 'codex'])
def test_invalid_native_timeout_never_disables_protection(provider, value):
    from jiuwenswarm.common import claude_adapter_config, codex_adapter_config
    raw = {'modes': {'team': {'jiuwen_team': {'external_cli_agents': [
        {'cli_agent':provider, 'stream_idle_timeout_ms':value},
    ]}}}}
    module = claude_adapter_config if provider == 'claude' else codex_adapter_config
    with pytest.raises(ValueError, match='positive integer'):
        module.config_snapshot(raw)


def test_saving_existing_agent_card_preserves_native_timeout_options(monkeypatch):
    from jiuwenswarm.common.config_panel import config_set_handlers as handlers
    raw = {'modes': {'team': {'jiuwen_team': {'external_cli_agents': [
        {'cli_agent':'claude', 'stream_first_byte_timeout_ms':60000, 'stream_idle_timeout_ms':300000},
        {'cli_agent':'codex', 'stream_idle_timeout_ms':90000},
    ]}}}}
    monkeypatch.setattr(handlers, '_uploaded_cli_path', lambda agent: '')
    entries = handlers.external_cli_agents_from_switches(raw, {
        'external_cli_agent_claude_enabled':'true', 'external_cli_agent_claude_use_builtin':'true',
        'external_cli_agent_codex_enabled':'true', 'external_cli_agent_codex_use_builtin':'true',
    })
    assert entries == raw['modes']['team']['jiuwen_team']['external_cli_agents']
