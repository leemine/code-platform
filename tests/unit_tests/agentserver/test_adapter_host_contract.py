"""Default Core assembly and explicit host/adapter boundary regressions."""
import json
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.runtime import AgentRuntime
from jiuwenswarm.server.runtime.agent_manager import AgentManager
from jiuwenswarm.server.runtime.agent_adapter import agent_adapters, interface
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter
from jiuwenswarm.server.runtime.agent_adapter.interface_code import JiuwenSwarmCodeAdapter
from openjiuwen.core.session.interaction.interactive_input import InteractiveInput


@pytest.mark.parametrize('mode,expected', [('agent', JiuWenSwarmDeepAdapter), ('code', JiuwenSwarmCodeAdapter)])
def test_unconfigured_factory_still_uses_core(monkeypatch, mode, expected):
    monkeypatch.delenv('JIUWENSWARM_AGENT_SDK', raising=False)
    adapter = agent_adapters.create_adapter(mode=mode)
    assert type(adapter) is expected
    assert isinstance(adapter, agent_adapters.AgentAdapter)


@pytest.mark.asyncio
async def test_manager_runtime_facade_share_default_after_environment_changes(monkeypatch):
    monkeypatch.delenv('JIUWENSWARM_AGENT_SDK', raising=False)
    manager = AgentManager()
    # An unrelated environment reload must not change the cached backend or Core startup.
    monkeypatch.setenv('JIUWENSWARM_AGENT_SDK', 'invalid-late-backend')
    runtime = AgentRuntime(agent_manager=manager)
    assert runtime._manage_runner and runtime._initialize_extensions
    captured = []
    async def initialize(self, config=None, **kwargs):
        captured.append(type(self))
    monkeypatch.setattr(JiuWenSwarmDeepAdapter, 'create_instance', initialize)
    monkeypatch.setattr(interface.JiuWenSwarm, '_prepare_skill_library', lambda self: None)
    agent = await manager.get_agent(channel_id='web', mode='agent')
    assert agent._sdk_name == manager.sdk_name == 'harness'
    assert captured == [JiuWenSwarmDeepAdapter]
    await runtime.close()


@pytest.mark.parametrize('source,value,expected', [
    ('permission_interrupt', 'allow_once', {'approved': True, 'auto_confirm': False, 'feedback': ''}),
    ('permission_interrupt', 'reject', {'approved': False, 'auto_confirm': False, 'feedback': '用户拒绝'}),
    ('ask_user_interrupt', 'A', {'answers': {'Choice?': 'A'}}),
])
def test_default_facade_retains_native_answer_codec(monkeypatch, source, value, expected):
    monkeypatch.delenv('JIUWENSWARM_AGENT_SDK', raising=False)
    monkeypatch.setattr(interface.JiuWenSwarm, '_prepare_skill_library', lambda self: None)
    facade = interface.JiuWenSwarm()
    request = AgentRequest(request_id='answer', session_id='native-codec', channel_id='web', params={
        'mode': 'agent', 'query': '', 'request_id': 'original', 'source': source,
        'answers': [{'question': 'Choice?', 'selected_options': [value]}],
    })
    inputs, _, turn = facade.build_inputs(request)
    assert isinstance(inputs['query'], InteractiveInput)
    assert turn.text is inputs['query']
    assert inputs['query'].user_inputs['original'] == expected


@pytest.mark.asyncio
async def test_native_control_delegates_and_closes_original_stream(monkeypatch):
    adapter = agent_adapters.create_adapter('harness')
    closed = []
    async def stream(request, inputs):
        try:
            yield inputs
            yield 'unused'
        finally:
            closed.append(True)
    monkeypatch.setattr(adapter, 'process_message_stream_impl', stream)
    control = adapter.deliver_control_input_impl(None, {'resume': True})
    assert await anext(control) == {'resume': True}
    await control.aclose()
    assert closed == [True]


def test_plugin_without_input_contract_is_rejected(monkeypatch):
    # An adapter that omits the input codec must not inherit Core conversion.
    adapter = SimpleNamespace(**{name: lambda *a, **kw: None for name in (
        'prepare_session', 'has_session_runtime', 'cleanup_session_adapter', 'cleanup',
        'create_instance', 'reload_agent_config', 'process_message_impl',
        'process_message_stream_impl', 'process_interrupt', 'handle_user_answer',
        'handle_swarmflow_reply', 'handle_heartbeat', 'deliver_control_input_impl',
    )})
    entry = SimpleNamespace(load=lambda: lambda **kw: adapter)
    monkeypatch.setattr(agent_adapters, 'entry_points', lambda **kw: (entry,))
    with pytest.raises(TypeError, match='does not implement AgentAdapter'):
        agent_adapters.create_adapter('missing-input')
