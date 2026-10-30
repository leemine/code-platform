"""Session provider identity and settings behavior at production boundaries."""
import json
from uuid import uuid4
from types import SimpleNamespace

import pytest

from jiuwenswarm.server.runtime.agent_adapter import agent_adapters
from jiuwenswarm.server.runtime.agent_adapter.provider_selection import select_session_provider
from jiuwenswarm.server.runtime.session import session_metadata as metadata
from jiuwenswarm.common.config_panel import execution_provider_settings as settings


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setattr(agent_adapters, 'entry_points', lambda **kw: (SimpleNamespace(),) if kw['name'] == 'opencode-direct' else ())


def test_binding_survives_defaults_and_stale_metadata_updates(registered):
    sid = 'provider-' + uuid4().hex
    assert select_session_provider(sid, 'opencode-direct', bind=True) == 'opencode-direct'
    assert select_session_provider(sid, default='harness') == 'opencode-direct'
    with pytest.raises(ValueError, match='new_session_required'):
        select_session_provider(sid, 'harness', bind=True)
    metadata.update_session_metadata(session_id=sid, execution_provider='harness', title='Renamed', sync_write=True)
    saved = metadata.get_session_metadata(sid, cache_bust=True)
    assert saved['execution_provider'] == 'opencode-direct'
    assert saved['title'] == 'Renamed'


def test_legacy_native_history_cannot_be_rebound(registered):
    sid = 'legacy-' + uuid4().hex
    metadata.init_session_metadata(session_id=sid, channel_id='web', mode='agent')
    metadata.update_session_metadata(session_id=sid, increment_message_count=True, sync_write=True)
    with pytest.raises(ValueError, match='new_session_required'):
        select_session_provider(sid, 'opencode-direct', bind=True)
    assert select_session_provider(sid, default='opencode-direct') == 'harness'


def test_missing_plugin_and_team_fail_before_binding(registered):
    sid = 'unbound-' + uuid4().hex
    with pytest.raises(RuntimeError, match='Unknown SDK'):
        select_session_provider(sid, 'missing', bind=True)
    with pytest.raises(ValueError, match='single_agent'):
        select_session_provider(sid, 'opencode-direct', mode='team', bind=True)
    assert not metadata.get_session_metadata(sid, enable_writeback=False).get('execution_provider')


@pytest.mark.parametrize("native_installed", [True, False])
def test_settings_only_expose_adapter_availability(monkeypatch, native_installed):
    monkeypatch.setattr(settings, "native_available", lambda: native_installed)
    monkeypatch.setattr(settings, 'entry_points', lambda **kw: (SimpleNamespace(name="opencode-direct", load=lambda: SimpleNamespace(display_name="OpenCode", supported_modes=("agent", "code"), permission_profiles=("default", "full_access"))),))
    fields = settings.public_fields({'opencode': {'password': 'secret'}})
    assert fields['opencode_adapter_available'] == 'true'
    expected = [{'id': 'opencode-direct', 'label': 'OpenCode', 'available': True, 'modes': ['agent', 'code'], 'reason': None}]
    if native_installed:
        expected.insert(0, {'id': 'harness', 'label': 'Deepagent', 'available': True, 'modes': ['agent', 'code', 'team'], 'reason': None})
    assert json.loads(fields['execution_provider_catalog']) == expected
    assert 'secret' not in str(fields)


@pytest.mark.asyncio
async def test_manager_cache_separates_provider_and_connection_revision(monkeypatch, registered):
    from jiuwenswarm.server.runtime.agent_manager import AgentManager
    from jiuwenswarm.server.runtime.agent_adapter import interface
    from jiuwenswarm.common import config
    monkeypatch.delenv('JIUWENSWARM_AGENT_SDK', raising=False)
    current = {'opencode': {'url': 'http://127.0.0.1:1234'}}
    monkeypatch.setattr(config, 'get_config', lambda: current)
    class Facade:
        def __init__(self, *, sdk_name): self._sdk_name = sdk_name
        def set_heartbeat_service(self, value): pass
        def set_permissions_changed_notifier(self, value): pass
        def set_permissions_external_input_context_builder(self, value): pass
        async def create_instance(self, config, **kw): self.config = config
    monkeypatch.setattr(interface, 'JiuWenSwarm', Facade)
    manager = AgentManager()
    from jiuwenswarm.common.native_integration import native_available
    native = None
    if native_available():
        native = await manager.get_agent(channel_id='web')
        assert native._sdk_name == 'harness'
    else:
        with pytest.raises(RuntimeError, match='native_provider_unavailable'):
            await manager.get_agent(channel_id='web')
    first = await manager.get_agent(channel_id='web', execution_provider='opencode-direct')
    assert native is not first and first._sdk_name == 'opencode-direct'
    assert await manager.get_agent(channel_id='web', execution_provider='opencode-direct') is first
    current['opencode'] = {'url': 'http://127.0.0.1:5678'}
    second = await manager.get_agent(channel_id='web', execution_provider='opencode-direct')
    assert second is not first
    assert first.config['opencode']['url'].endswith('1234')
    assert second.config['opencode']['url'].endswith('5678')


@pytest.mark.asyncio
async def test_actual_front_config_request_exposes_provider_availability(monkeypatch):
    from jiuwenswarm.server.control import config_service
    from jiuwenswarm.common.schema.agent import AgentRequest
    from jiuwenswarm.common.schema.message import ReqMethod
    monkeypatch.setattr(config_service, '_read_raw_config', lambda: {'opencode': {'password': 'PRIVATE'}})
    for plugins, expected in [((), 'false'), ((SimpleNamespace(name="opencode-direct", load=lambda: SimpleNamespace(display_name="OpenCode", supported_modes=("agent", "code"), permission_profiles=("default", "full_access"))),), 'true')]:
        monkeypatch.setattr(settings, 'entry_points', lambda **kw: plugins)
        response = await config_service.handle_config_request(AgentRequest(
            request_id='front-config', channel_id='web', req_method=ReqMethod.CONFIG_GET,
        ))
        assert response.ok and response.payload['opencode_adapter_available'] == expected
        assert 'PRIVATE' not in str(response.payload)


@pytest.mark.parametrize('mode', ['agent', 'code', 'code.normal', 'agent.work.normal', 'agent.code.normal'])
def test_provider_binding_accepts_actual_swarm_single_modes(registered, mode):
    assert select_session_provider('', 'opencode-direct', mode=mode) == 'opencode-direct'


@pytest.mark.asyncio
async def test_config_catalog_supports_new_plugins_and_rejects_broken_or_duplicate(monkeypatch):
    from jiuwenswarm.server.control import config_service
    from jiuwenswarm.common.schema.agent import AgentRequest
    from jiuwenswarm.common.schema.message import ReqMethod
    def fail():
        raise RuntimeError("PRIVATE import path /credential")
    def factory():
        return SimpleNamespace(display_name="Example engine", supported_modes=("code",), permission_profiles=())
    entries = [SimpleNamespace(name="example", load=factory),
               SimpleNamespace(name="broken", load=fail),
               SimpleNamespace(name="duplicate", load=factory),
               SimpleNamespace(name="duplicate", load=factory),
               SimpleNamespace(name="probe-only", load=lambda: SimpleNamespace())]
    monkeypatch.setattr(settings, 'entry_points', lambda **kw: entries)
    monkeypatch.setattr(config_service, '_read_raw_config', lambda: {})
    response = await config_service.handle_config_request(AgentRequest(
        request_id='catalog', channel_id='web', req_method=ReqMethod.CONFIG_GET,
    ))
    assert response.ok
    rows = {row['id']: row for row in json.loads(response.payload['execution_provider_catalog'])}
    assert rows['example']['label'] == 'Example engine'
    assert rows['example']['available'] and rows['example']['modes'] == ['code']
    assert not rows['broken']['available']
    assert rows['duplicate']['reason'] == 'ambiguous'
    assert 'probe-only' not in rows
    assert 'PRIVATE' not in str(response.payload)
