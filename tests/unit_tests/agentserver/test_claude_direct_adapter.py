"""Exercise the existing Facade, permissions and history with a public SDK fake."""
import asyncio
import json
from types import SimpleNamespace
from pathlib import Path

import pytest
import claude_agent_sdk as sdk
from gateway.common.model_selection import ResolvedModel
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.runtime.agent_adapter import interface
from jiuwenswarm.server.runtime.agent_adapter.providers import claude
from jiuwenswarm.server.runtime.session import session_history


class FakeClient:
    def __init__(self, options):
        self.options = options
        self.queue = asyncio.Queue()
        self.closed = False
        self.decision = None
        self.interrupted = False
        self.exit_code = None
        self.metadata = None
        self.tool_error = False
        self.tool_name = "Bash"
        self.ask = False
        self.eof = False
        self.worker = None

    async def __aenter__(self):
        self.owner = asyncio.current_task()
        return self

    async def __aexit__(self, *args):
        assert self.owner is asyncio.current_task()
        self.closed = True
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)

    async def connect(self):
        await self.__aenter__()

    async def disconnect(self):
        await self.__aexit__()

    async def set_permission_mode(self, mode):
        self.mode = mode

    async def query(self, prompt, session_id):
        self.sid = session_id
        messages = [item async for item in prompt]
        await self.queue.put(sdk.UserMessage(messages[0]['message']['content'], uuid=messages[0]['uuid']))
        await self.queue.put(sdk.SystemMessage('init', {'session_id': session_id}))
        self.worker = asyncio.create_task(self.execute())

    async def execute(self):
        await self.queue.put(sdk.AssistantMessage([sdk.ToolUseBlock('cmd', self.tool_name, {'command': 'fixture'})], 'shared'))
        if self.ask:
            self.decision = await self.options.can_use_tool('Bash', {'command': 'fixture'}, sdk.ToolPermissionContext(tool_use_id='cmd'))
        denied = isinstance(self.decision, sdk.PermissionResultDeny)
        await self.queue.put(sdk.UserMessage([sdk.ToolResultBlock('cmd', 'output', True if denied else self.tool_error)], tool_use_result=self.metadata if self.metadata is not None else {'exit_code': self.exit_code}))
        if not self.eof:
            await self.queue.put(sdk.ResultMessage('success', 1, 1, self.interrupted, 1, self.sid, result='reply'))
        await self.queue.put(None)

    async def receive_response(self):
        async for item in self.receive_messages():
            yield item
            if isinstance(item, sdk.ResultMessage):
                return

    async def receive_messages(self):
        while True:
            item = await self.queue.get()
            if item is None:
                return
            yield item

    async def interrupt(self):
        self.interrupted = True


@pytest.fixture
def host(monkeypatch, tmp_path):
    from jiuwenswarm.common import utils, config
    clients = []
    settings = {'exit_code': None, 'ask': False, 'eof': False}
    def factory(options):
        client = FakeClient(options)
        for key, value in settings.items():
            setattr(client, key, value)
        clients.append(client)
        return client
    monkeypatch.setattr(sdk, 'ClaudeSDKClient', factory)
    monkeypatch.setattr(interface, 'resolve_sdk_choice', lambda: 'claude-direct')
    monkeypatch.setattr(interface, 'get_config', lambda: {'preferred_language': 'en'})
    monkeypatch.setattr(config, 'get_config', lambda: {})
    monkeypatch.setattr(session_history, 'get_agent_sessions_dir', lambda: tmp_path / 'sessions')
    monkeypatch.setattr(utils, 'get_agent_sessions_dir', lambda: tmp_path / 'sessions')
    monkeypatch.setattr(utils, 'get_default_project_session_workspace_dir', lambda: tmp_path)
    model = ResolvedModel(model_id='shared', source='defaults', model_name='shared', provider='Anthropic', api_base='http://127.0.0.1:1234', api_key='private-fixture-key')
    monkeypatch.setattr(claude, 'resolve_model', lambda req: model)
    return interface.JiuWenSwarm(), {'claude': {'enabled': True}, 'permissions': {'enabled': True}}, clients, tmp_path, settings


def request(sid='one', method=ReqMethod.CHAT_SEND, **params):
    return AgentRequest(request_id='request', session_id=sid, channel_id='web', req_method=method, is_stream=True, params={'query': 'hello', 'mode': 'agent.code.normal', **params})


@pytest.mark.asyncio
@pytest.mark.parametrize('base,hostname', [
    ('http://127.0.0.1:1234', '127.0.0.1'),
    ('http://localhost:1234', 'localhost'),
    ('http://[::1]:1234', '::1'),
    ('https://models.example.invalid', None),
])
async def test_local_model_bypasses_inherited_proxy_without_changing_remote_policy(host, monkeypatch, base, hostname):
    app, config, _, root, _ = host
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:7897')
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:7897')
    monkeypatch.setenv('NO_PROXY', 'existing.example')
    monkeypatch.setenv('no_proxy', 'other.example')
    inherited = [__import__('os').environ.get('NO_PROXY', ''), __import__('os').environ.get('no_proxy', '')]
    await app.create_instance(config)
    try:
        await app._adapter.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(root))
        model = claude.resolve_model(request()).model_copy(update={'api_base': base})
        options = app._adapter._options(app._adapter._sessions['one'], model)
        if hostname:
            assert options.env['NO_PROXY'] == options.env['no_proxy']
            assert options.env['NO_PROXY'].split(',') == [*filter(None, inherited), hostname]
        else:
            assert 'NO_PROXY' not in options.env and 'no_proxy' not in options.env
        assert 'HTTP_PROXY' not in options.env and 'HTTPS_PROXY' not in options.env
        assert __import__('os').environ['NO_PROXY'] == inherited[0]
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('code,success', [(0, True), (7, False), (None, None), (True, None)])
async def test_facade_native_results_history_and_resume(host, code, success):
    app, config, clients, root, options = host
    options['exit_code'] = code
    await app.create_instance(config)
    try:
        chunks = [item.payload async for item in app.process_message_stream(request())]
        result = next(p for p in chunks if p.get('event_type') == 'chat.tool_result')
        assert result['command_success'] is success
        assert result['exit_code'] == (code if type(code) is int else None)
        assert result['task_acceptance'] == 'unknown'
        assert clients[0].closed and clients[0].options.setting_sources == []
        _ = [item async for item in app.process_message_stream(request())]
        assert clients[1].options.resume == clients[0].sid
        assert clients[1].options.session_id is None
        assert clients[1].options.env['CLAUDE_CONFIG_DIR'] == clients[0].options.env['CLAUDE_CONFIG_DIR']
        history = session_history.read_session_history_records('one')
        assert any(p.get('event_type') == 'chat.final' and p.get('content') == 'reply' for p in history)
        assert all('private-fixture-key' not in str(p) for p in history)
    finally:
        await app.cleanup()
    assert all(c.closed for c in clients)
    from jiuwenswarm.server.runtime.agent_adapter.providers import session_recovery
    binding = session_recovery.load('claude', 'one', str(root))
    assert binding['native_id'] == clients[0].sid
    assert Path(binding['root']) == Path(clients[0].options.env['CLAUDE_CONFIG_DIR']).parent
    assert Path(binding['root']).is_dir()


@pytest.mark.asyncio
async def test_new_facade_resumes_original_session_and_transcript_home(host):
    first, config, clients, _, _ = host
    await first.create_instance(config)
    try:
        _ = [chunk async for chunk in first.process_message_stream(request())]
        original_session = clients[0].sid
        original_home = clients[0].options.env['CLAUDE_CONFIG_DIR']
    finally:
        await first.cleanup()
    assert clients[0].closed
    second = interface.JiuWenSwarm()
    await second.create_instance(config)
    try:
        chunks = [chunk.payload async for chunk in second.process_message_stream(request())]
        assert any(chunk.get('event_type') == 'chat.final' for chunk in chunks)
        assert len(clients) == 2
        assert clients[1].options.resume == original_session
        assert clients[1].options.session_id is None
        assert clients[1].options.env['CLAUDE_CONFIG_DIR'] == original_home
    finally:
        await second.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['allow_once', 'reject'])
async def test_facade_permission_response_uses_active_original_producer(host, action):
    app, config, clients, root, options = host
    options['ask'] = True
    await app.create_instance(config)
    try:
        chunks = []
        async for item in app.process_message_stream(request()):
            p = item.payload
            chunks.append(p)
            if p.get('event_type') == 'chat.ask_user_question':
                reply = request(method=ReqMethod.CHAT_ANSWER, request_id=p['request_id'], source=p['source'], answers=[{'selected_options': [action]}])
                result = [x.payload async for x in app.deliver_control_input(reply)]
                assert any(x.get('event_type') == 'runtime.accepted' for x in result)
        assert len(clients) == 1
        assert isinstance(clients[0].decision, sdk.PermissionResultAllow if action == 'allow_once' else sdk.PermissionResultDeny)
        assert any(x.get('event_type') == 'chat.final' for x in chunks)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_facade_eof_is_not_completion_and_closes_owned_session(host):
    app, config, clients, root, options = host
    options['eof'] = True
    await app.create_instance(config)
    try:
        result = [x.payload async for x in app.process_message_stream(request())]
        assert any(x.get('code') == 'claude_incomplete' for x in result)
        assert not any(x.get('event_type') == 'chat.final' for x in result)
        assert clients[0].closed
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_facade_two_sessions_have_distinct_native_and_config_binding(host):
    app, config, clients, root, options = host
    await app.create_instance(config)
    try:
        for sid in ['one', 'two', 'one']:
            _ = [x async for x in app.process_message_stream(request(sid))]
        assert clients[0].sid != clients[1].sid
        assert clients[0].sid == clients[2].sid
        assert clients[0].options.env['CLAUDE_CONFIG_DIR'] != clients[1].options.env['CLAUDE_CONFIG_DIR']
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_full_access_uses_explicit_official_mode(host):
    app, config, clients, root, options = host
    config['permissions'] = {'enabled': False}
    await app.create_instance(config)
    try:
        _ = [x async for x in app.process_message_stream(request())]
        assert clients[0].mode == 'bypassPermissions'
        assert clients[0].options.permission_mode == 'bypassPermissions'
    finally:
        await app.cleanup()


def test_claude_discovery_uses_existing_settings_without_sdk_version_allowlist(monkeypatch):
    from jiuwenswarm.common.claude_adapter_config import config_snapshot, availability
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, 'version', lambda name: 'future')
    settings = {'modes': {'team': {'jiuwen_team': {'external_cli_agents': [{'cli_agent': 'claude', 'cli_path': '/explicit/claude'}]}}}}
    assert config_snapshot(settings) == {'claude': {'enabled': True, 'cli_path': '/explicit/claude'}}
    assert availability(settings) is None
    assert availability({}) == 'disabled'


@pytest.mark.asyncio
@pytest.mark.parametrize('metadata', ['InputValidationError: invalid Bash argument', [], 7, {'exit_code': '7'}])
async def test_facade_unstructured_tool_failure_preserves_unknown_exit_and_continues(host, metadata):
    app, config, clients, root, options = host
    options.update(metadata=metadata, tool_error=True)
    await app.create_instance(config)
    try:
        chunks = [item.payload async for item in app.process_message_stream(request())]
        result = next(p for p in chunks if p.get('event_type') == 'chat.tool_result')
        assert result['status'] == 'error'
        assert result['content'] == 'output'
        assert result['exit_code'] is None and result['command_success'] is None
        assert result['task_acceptance'] == 'unknown'
        assert any(p.get('event_type') == 'chat.final' for p in chunks)
        assert not any(p.get('event_type') == 'chat.error' for p in chunks)
        history = session_history.read_session_history_records('one')
        assert any(p.get('event_type') == 'chat.tool_result' for p in history)
    finally:
        await app.cleanup()

@pytest.mark.asyncio
async def test_facade_cancel_drains_producer_then_resumes_native_session(host):
    app, config, clients, root, options = host
    options['ask'] = True
    await app.create_instance(config)
    waiting = asyncio.Event()
    async def consume():
        async for item in app.process_message_stream(request()):
            if item.payload.get('event_type') == 'chat.ask_user_question':
                waiting.set()
    producer = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(waiting.wait(), 5)
        await app.process_message(request(method=ReqMethod.CHAT_CANCEL, intent='cancel'))
        # Runtime cancels and drains its producer after the adapter interrupt.
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
        assert clients[0].closed
        options['ask'] = False
        result = [x.payload async for x in app.process_message_stream(request())]
        assert any(x.get('event_type') == 'chat.final' for x in result)
        assert clients[1].options.resume == clients[0].sid
        assert clients[1].options.env['CLAUDE_CONFIG_DIR'] == clients[0].options.env['CLAUDE_CONFIG_DIR']
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
        await app.cleanup()
    from jiuwenswarm.server.runtime.agent_adapter.providers import session_recovery
    binding = session_recovery.load('claude', 'one', str(root))
    assert binding['native_id'] == clients[0].sid
    assert Path(binding['root']).is_dir()


@pytest.mark.asyncio
@pytest.mark.parametrize('tool_name,is_error', [('Bash', False), ('Read', None), ('Read', True)])
async def test_facade_native_result_without_exit_code_keeps_tool_facts(host, tool_name, is_error):
    app, config, clients, root, options = host
    options.update(tool_name=tool_name, tool_error=is_error, metadata={'stdout': 'output', 'interrupted': False})
    await app.create_instance(config)
    try:
        chunks = [item.payload async for item in app.process_message_stream(request())]
        result = next(p for p in chunks if p.get('event_type') == 'chat.tool_result')
        assert result['content'] == 'output'
        assert result['status'] == ('error' if is_error else 'completed')
        assert result['provider']['claude']['is_error'] is is_error
        assert result['task_acceptance'] == 'unknown'
        if tool_name == 'Bash':
            assert result['success'] is True
            assert result['exit_code'] is None and result['command_success'] is None
        else:
            assert 'exit_code' not in result and 'command_success' not in result
        history = session_history.read_session_history_records('one')
        saved = next(p for p in history if p.get('event_type') == 'chat.tool_result')
        assert saved['provider']['claude']['is_error'] is is_error
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_facade_explicit_tool_error_is_not_overridden_by_zero_exit(host):
    app, config, clients, root, options = host
    options.update(metadata={'exit_code': 0}, tool_error=True)
    await app.create_instance(config)
    try:
        chunks = [item.payload async for item in app.process_message_stream(request())]
        result = next(p for p in chunks if p.get('event_type') == 'chat.tool_result')
        assert result['provider']['claude']['is_error'] is True and result['success'] is False
        assert result['exit_code'] == 0 and result['command_success'] is True
        assert result['status'] == 'error'
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_model_transport_timeout_does_not_limit_whole_turn(host, monkeypatch):
    app, config, clients, _, _ = host
    original = claude.resolve_model
    model = original(request()).model_copy(update={'client_options': {'timeout': 0.01}})
    monkeypatch.setattr(claude, 'resolve_model', lambda req: model)
    execute = FakeClient.execute
    async def slow_tool(self):
        await asyncio.sleep(0.04)
        await execute(self)
    monkeypatch.setattr(FakeClient, 'execute', slow_tool)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        assert clients[0].options.env['API_TIMEOUT_MS'] == '10'
        assert any(x.get('event_type') == 'chat.final' for x in chunks)
        assert not any(x.get('event_type') == 'chat.error' for x in chunks)
        assert any(x.get('status') == 'success' for x in session_history.read_session_history_records('one'))
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_native_sdk_timeout_has_honest_source_and_closes_client(host, monkeypatch):
    app, config, clients, _, _ = host
    async def timeout_query(self, *args, **kwargs):
        raise TimeoutError('must-not-expose-native-secret')
    monkeypatch.setattr(FakeClient, 'query', timeout_query)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        error = next(x for x in chunks if x.get('event_type') == 'chat.error')
        assert error['code'] == 'claude_timeout'
        assert error['provider']['claude']['timeout_source'] == 'native_sdk'
        assert error['provider']['claude']['phase'] == 'query_submit'
        assert 'must-not-expose-native-secret' not in str(chunks)
        assert clients[0].closed
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_unconfirmed_sdk_close_fences_session(host, monkeypatch):
    app, config, clients, _, _ = host
    await app.create_instance(config)
    disconnect = FakeClient.disconnect
    async def broken_close(self):
        await disconnect(self)
        raise RuntimeError('fixture shutdown failed')
    monkeypatch.setattr(FakeClient, 'disconnect', broken_close)
    _ = [x async for x in app.process_message_stream(request())]
    with pytest.raises(RuntimeError, match='shutdown is unconfirmed'):
        await anext(app._adapter.process_message_stream_impl(request(), {'query':'unsafe resume'}))
    # A local fixture exception is not proof of native shutdown. Keep ownership.
    with pytest.raises(RuntimeError, match='shutdown is unconfirmed'):
        await app.cleanup()


def native_system(client, subtype, **data):
    return sdk.SystemMessage(subtype, {'session_id': client.sid, **data})


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal_event', ['task_notification', 'task_updated'])
async def test_background_explorers_wait_for_native_idle_and_last_summary(host, monkeypatch, terminal_event):
    app, config, clients, _, _ = host
    async def execute(client):
        async def emit(item):
            await client.queue.put(item)
        await emit(native_system(client, 'session_state_changed', state='running'))
        for i in range(4):
            await emit(sdk.AssistantMessage([sdk.ToolUseBlock(f'launch-{i}', 'Agent', {'description': f'explore-{i}'})], 'shared'))
            await emit(native_system(client, 'task_started', task_id=f'agent-{i}', tool_use_id=f'launch-{i}', task_type='local_agent'))
        await emit(sdk.ResultMessage('success', 1, 1, False, 1, client.sid, result='WAITING'))
        for i in range(4):
            data = {'patch': {'status': 'completed'}} if terminal_event == 'task_updated' else {'status': 'completed', 'summary': f'CHILD-{i}'}
            await emit(native_system(client, terminal_event, task_id=f'agent-{i}', **data))
        # Real CLI can clear all tasks before several follow-up results arrive.
        await emit(sdk.ResultMessage('success', 1, 1, False, 1, client.sid, result='Still waiting'))
        await emit(sdk.ResultMessage('success', 1, 1, False, 0, client.sid, result=''))
        await emit(sdk.ResultMessage('success', 1, 1, False, 1, client.sid, result='ALL FOUR SUMMARIZED'))
        await emit(native_system(client, 'session_state_changed', state='idle'))
        await emit(None)
    monkeypatch.setattr(FakeClient, 'execute', execute)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        finals = [x for x in chunks if x.get('event_type') == 'chat.final']
        assert finals[-1]['content'] == 'ALL FOUR SUMMARIZED'
        assert not any(x.get('event_type') == 'chat.error' for x in chunks)
        tasks = finals[-1]['provider']['claude']['tasks']
        assert len(tasks) == 4 and all(t['status'] == 'completed' for t in tasks)
        history = session_history.read_session_history_records('one')
        assert any(x.get('content') == 'ALL FOUR SUMMARIZED' for x in history)
        roster = [x for x in history if x.get('event_type') == 'chat.subtask_update']
        assert {x['subagent_id'] for x in roster} == {f'claude-agent-{i}' for i in range(4)}
        assert len([x for x in roster if x['status'] == 'closed']) == 4
        assert all(x['can_send_input'] is False for x in roster)
        assert clients[0].closed
        assert clients[0].options.env['CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS'] == '1'
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_background_snapshot_empty_is_not_a_terminal_task_result(host, monkeypatch):
    app, config, clients, _, _ = host
    async def execute(client):
        for message in [native_system(client, 'session_state_changed', state='running'),
                        native_system(client, 'background_tasks_changed', tasks=[{'task_id':'a','task_type':'local_agent'}]),
                        sdk.ResultMessage('success',1,1,False,1,client.sid,result='WAITING'),
                        native_system(client, 'background_tasks_changed', tasks=[]),
                        None]:
            await client.queue.put(message)
    monkeypatch.setattr(FakeClient, 'execute', execute)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        assert any(x.get('code') == 'claude_incomplete' for x in chunks)
        assert not any(x.get('event_type') == 'chat.final' for x in chunks)
        assert clients[0].closed
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_native_idle_ignores_nested_tools_and_foreign_lifecycle(host, monkeypatch):
    app, config, _, _, _ = host
    async def execute(client):
        for msg in [native_system(client, 'session_state_changed', state='running'),
                    native_system(client, 'task_started', task_id='nested', owned_by_subagent=True, task_type='local_bash'),
                    sdk.SystemMessage('task_started', {'session_id':'other','task_id':'foreign'}),
                    sdk.ResultMessage('success',1,1,False,1,client.sid,result='DONE'),
                    native_system(client, 'session_state_changed', state='idle'), None]:
            await client.queue.put(msg)
    monkeypatch.setattr(FakeClient, 'execute', execute)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        assert next(x for x in chunks if x.get('event_type') == 'chat.final')['content'] == 'DONE'
        assert not any(x.get('event_type') == 'chat.error' for x in chunks)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['failed', 'stopped', 'killed'])
async def test_background_terminal_status_is_preserved_without_claiming_acceptance(host, monkeypatch, status):
    app, config, _, _, _ = host
    async def execute(client):
        for msg in [native_system(client, 'session_state_changed', state='running'),
                    native_system(client, 'task_started', task_id='child', task_type='local_agent'),
                    native_system(client, 'task_updated', task_id='child', patch={'status':status}),
                    sdk.ResultMessage('success',1,1,False,1,client.sid,result='Child did not complete successfully'),
                    native_system(client, 'session_state_changed', state='idle'), None]:
            await client.queue.put(msg)
    monkeypatch.setattr(FakeClient, 'execute', execute)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        final = next(x for x in chunks if x.get('event_type') == 'chat.final')
        assert final['provider']['claude']['tasks'][0]['status'] == status
        assert final['task_acceptance'] == 'unknown'
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_background_without_native_idle_capability_fails_explicitly(host, monkeypatch):
    app, config, _, _, _ = host
    async def execute(client):
        await client.queue.put(native_system(client, 'task_started', task_id='child', task_type='local_agent'))
        await client.queue.put(sdk.ResultMessage('success',1,1,False,1,client.sid,result='WAITING'))
        await client.queue.put(None)
    monkeypatch.setattr(FakeClient, 'execute', execute)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        assert any(x.get('code') == 'claude_lifecycle_unsupported' for x in chunks)
        assert not any(x.get('event_type') == 'chat.final' for x in chunks)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_cancel_stops_only_observed_tasks_and_waits_for_idle(host, monkeypatch):
    app, config, clients, _, _ = host
    waiting = asyncio.Event()
    stopped = []
    execute_original = FakeClient.execute
    async def execute(client):
        await client.queue.put(native_system(client, 'session_state_changed', state='running'))
        for task_id in ('child-1','child-2'):
            await client.queue.put(native_system(client, 'task_started', task_id=task_id, task_type='local_agent'))
        await client.queue.put(sdk.ResultMessage('success',1,1,False,1,client.sid,result='WAITING'))
        waiting.set()
    async def stop_task(client, task_id):
        stopped.append(task_id)
        await client.queue.put(native_system(client, 'task_updated', task_id=task_id, patch={'status':'killed'}))
        if len(stopped)==2:
            await client.queue.put(sdk.ResultMessage('success',1,1,True,0,client.sid,result=''))
            await client.queue.put(native_system(client, 'session_state_changed', state='idle'))
    monkeypatch.setattr(FakeClient, 'execute', execute)
    monkeypatch.setattr(FakeClient, 'stop_task', stop_task, raising=False)
    await app.create_instance(config)
    chunks=[]
    async def consume():
        async for item in app.process_message_stream(request()):chunks.append(item.payload)
    producer=asyncio.create_task(consume())
    try:
        await asyncio.wait_for(waiting.wait(),5)
        # Give the original single reader its queued starts, without a second consumer.
        while len(app._adapter._sessions['one'].native_tasks.active)!=2:
            await asyncio.sleep(0)
        assert not clients[0].closed
        await app._adapter.process_interrupt(request(method=ReqMethod.CHAT_CANCEL,intent='cancel'))
        await asyncio.wait_for(producer,5)
        assert set(stopped)=={'child-1','child-2'} and len(stopped)==2
        assert clients[0].closed
        assert any(x.get('code')=='claude_cancelled' for x in chunks)
        assert not any(x.get('event_type')=='chat.final' for x in chunks)
        monkeypatch.setattr(FakeClient,'execute',execute_original)
        resumed=[x.payload async for x in app.process_message_stream(request())]
        assert any(x.get('content')=='reply' for x in resumed)
        assert clients[1].options.resume==clients[0].sid
    finally:
        producer.cancel();await asyncio.gather(producer,return_exceptions=True)
        await app.cleanup()



@pytest.mark.asyncio
async def test_resume_ignores_orphan_result_and_idle_before_exact_input_echo(host, monkeypatch):
    app, config, _, _, _ = host
    async def query(client, prompt, session_id):
        client.sid = session_id
        messages=[m async for m in prompt]
        for m in [native_system(client,'task_notification',task_id='orphan',status='stopped'),
                  native_system(client,'session_state_changed',state='running'),
                  sdk.ResultMessage('success',1,1,False,0,session_id,result=''),
                  native_system(client,'session_state_changed',state='idle'),
                  sdk.UserMessage('unrelated echo',uuid='not-this-input'),
                  sdk.UserMessage(messages[0]['message']['content'],uuid=messages[0]['uuid']),
                  native_system(client,'session_state_changed',state='running'),
                  sdk.ResultMessage('success',1,1,False,1,session_id,result='CURRENT INPUT ANSWER'),
                  native_system(client,'session_state_changed',state='idle'),None]:
            await client.queue.put(m)
    monkeypatch.setattr(FakeClient,'query',query)
    await app.create_instance(config)
    try:
        chunks=[x.payload async for x in app.process_message_stream(request())]
        finals=[x for x in chunks if x.get('event_type')=='chat.final']
        assert len(finals)==1 and finals[0]['content']=='CURRENT INPUT ANSWER'
        assert not any(x.get('event_type')=='chat.subtask_update' for x in chunks)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_cancel_control_waits_for_same_owner_sdk_close(host, monkeypatch):
    app, config, clients, _, options = host
    options['ask'] = True
    waiting, closing, allow_close = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_disconnect = FakeClient.disconnect
    async def disconnect(client):
        closing.set()
        await allow_close.wait()
        await original_disconnect(client)
    monkeypatch.setattr(FakeClient, 'disconnect', disconnect)
    await app.create_instance(config)
    async def consume():
        async for x in app.process_message_stream(request()):
            if x.payload.get('event_type') == 'chat.ask_user_question':waiting.set()
    producer=asyncio.create_task(consume());control=None
    try:
        await asyncio.wait_for(waiting.wait(),5)
        control=asyncio.create_task(app._adapter.process_interrupt(request(method=ReqMethod.CHAT_CANCEL,intent='cancel')))
        await asyncio.wait_for(closing.wait(),5)
        assert not control.done() and not clients[0].closed
        allow_close.set()
        await asyncio.wait_for(control,5)
        await asyncio.wait_for(producer,5)
        assert clients[0].closed and not app._adapter._sessions['one'].close_unconfirmed
    finally:
        allow_close.set();producer.cancel()
        await asyncio.gather(producer,*([] if control is None else [control]),return_exceptions=True)
        await app.cleanup()


@pytest.mark.asyncio
async def test_child_activity_and_summary_restore_through_existing_history(host, monkeypatch):
    app, config, _, _, _ = host
    async def execute(client):
        frames = [native_system(client, 'session_state_changed', state='running'),
            native_system(client, 'task_started', task_id='child', task_type='local_agent', tool_use_id='launch', description='Inspect architecture'),
            native_system(client, 'task_progress', task_id='child', description='Reading entrypoint', last_tool_name='Read', uuid='progress'),
            native_system(client, 'task_progress', task_id='child', description='Reading entrypoint', last_tool_name='Read', uuid='progress'),
            sdk.AssistantMessage([sdk.ToolUseBlock('read-1','Read',{'file_path':'entry.py'})], 'shared', parent_tool_use_id='launch'),
            sdk.UserMessage([sdk.ToolResultBlock('read-1','CHILD TOOL OUTPUT',False)], parent_tool_use_id='launch'),
            sdk.UserMessage([sdk.ToolResultBlock('foreign','FOREIGN SECRET',False)], parent_tool_use_id='unrelated'),
            native_system(client,'task_notification',task_id='child',status='completed',summary='CHILD SUMMARY'),
            sdk.ResultMessage('success',1,1,False,1,client.sid,result='PARENT SUMMARY'),
            native_system(client,'session_state_changed',state='idle'),None]
        for frame in frames:await client.queue.put(frame)
    monkeypatch.setattr(FakeClient,'execute',execute)
    await app.create_instance(config)
    try:
        chunks=[x.payload async for x in app.process_message_stream(request())]
        activities=[x for x in chunks if x.get('event_type')=='chat.subagent_activity']
        assert any(x.get('summary')=='CHILD TOOL OUTPUT' for x in activities)
        paired=[x for x in activities if x.get('tool_call_id')=='read-1']
        assert {x['kind']for x in paired}=={'tool_call','tool_result'}
        assert len({x['activity_id']for x in paired})==2
        assert len([x for x in activities if x.get('summary')=='Reading entrypoint'])==1
        assert next(x for x in activities if x.get('summary')=='Reading entrypoint')['kind']=='thinking'
        assert not any('FOREIGN SECRET' in str(x) for x in chunks)
        assert next(x for x in chunks if x.get('event_type')=='chat.final')['content']=='PARENT SUMMARY'
        from jiuwenswarm.server.control.history_service import load_history_page
        session_history.flush_history_writes()
        page=load_history_page('one',1,subagent_id='claude-child')
        assert any(x.get('content')=='CHILD SUMMARY' for x in page['messages'])
        assert any(x.get('event_type')=='chat.subagent_activity' for x in page['messages'])
        assert 'claude-child' in session_history.list_session_subagent_ids('one')
    finally:await app.cleanup()
