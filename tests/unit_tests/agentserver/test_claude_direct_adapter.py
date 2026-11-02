"""Exercise the existing Facade, permissions and history with a public SDK fake."""
import asyncio
import json
from types import SimpleNamespace

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
        while True:
            item = await self.queue.get()
            if item is None:
                return
            yield item
            if isinstance(item, sdk.ResultMessage):
                return

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
    assert not list((root / 'sessions/.claude-direct').iterdir())


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
    assert not list((root / 'sessions/.claude-direct').iterdir())


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
