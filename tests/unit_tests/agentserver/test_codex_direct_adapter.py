"""Public Facade/control/history regressions; SDK fake is not real acceptance."""
import asyncio
import queue
from types import SimpleNamespace

import pytest
from gateway.common.model_selection import ResolvedModel
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.runtime.agent_adapter import interface
from jiuwenswarm.server.runtime.agent_adapter.providers import codex
from jiuwenswarm.server.runtime.session import session_history


class Payload(dict):
    def model_dump(self, **kwargs):
        return dict(self)


class FakeClient:
    def __init__(self, config, approval_handler):
        self.config, self.approval_handler = config, approval_handler
        self.events = queue.Queue()
        self.thread_id = 'thread-' + str(id(self))
        self.turns = 0
        self.closed = False
        self.approval = False
        self.exit_code = 7
        self.interrupt_error = False
        self.decisions = []
        self.messages = [(None, "reply")]

    def start(self):
        pass

    def initialize(self):
        pass

    def thread_start(self, options):
        self.options = options
        return self._policy()

    def thread_resume(self, thread_id, options):
        assert thread_id == self.thread_id
        self.options = options
        return self._policy()

    def _policy(self):
        response = SimpleNamespace(thread=SimpleNamespace(id=self.thread_id))
        response.model_dump = lambda **kw: {**self.options, 'sandbox': {'type': 'dangerFullAccess' if self.options['sandbox'] == 'danger-full-access' else 'workspaceWrite'}}
        return response

    def emit(self, method, **payload):
        self.events.put(SimpleNamespace(method=method, payload=Payload(payload)))

    def turn_start(self, thread_id, prompt):
        assert thread_id == self.thread_id
        self.turns += 1
        self.turn_id = str(self.turns)
        if self.approval:
            self.events.put('approval')
        else:
            self.finish()
        return SimpleNamespace(turn=SimpleNamespace(id=self.turn_id))

    def finish(self, status='completed'):
        self.emit('item/completed', item={'id': 'command', 'type': 'commandExecution', 'status': 'completed', 'exitCode': self.exit_code, 'aggregatedOutput': 'output'})
        for index, (phase, text) in enumerate(self.messages):
            self.emit('item/agentMessage/delta', delta=text)
            self.emit('item/completed', item={'id': f'text-{index}', 'type': 'agentMessage', 'text': text, 'phase': phase})
        self.emit('turn/completed', turn={'status': status})

    def next_turn_notification(self, turn_id):
        events = self.events
        event = events.get(timeout=5)
        if event == 'approval':
            decision = self.approval_handler('item/commandExecution/requestApproval', {'threadId': self.thread_id, 'turnId': self.turn_id, 'command': 'fixture command'})
            self.decisions.append(decision)
            self.finish('interrupted' if decision['decision'] == 'cancel' else 'completed')
            event = events.get(timeout=5)
        if isinstance(event, Exception):
            raise event
        return event

    def turn_interrupt(self, thread_id, turn_id):
        if self.interrupt_error:
            raise RuntimeError('interruption failed')

    def unregister_turn_notifications(self, turn_id):
        # Official SDK closes the turn subscription and wakes its reader.
        self.events.put(RuntimeError('Turn subscription closed'))
        self.events = queue.Queue()

    def close(self):
        self.closed = True
        self.events.put(RuntimeError('Transport closed'))


@pytest.fixture
def host(monkeypatch, tmp_path):
    from jiuwenswarm.common import utils, config
    import openai_codex.client
    clients = []
    def factory(*args, **kwargs):
        client = FakeClient(*args, **kwargs)
        clients.append(client)
        return client
    monkeypatch.setattr(openai_codex.client, 'CodexClient', factory)
    monkeypatch.setattr(interface, 'resolve_sdk_choice', lambda: 'codex-direct')
    monkeypatch.setattr(interface, 'get_config', lambda: {'preferred_language': 'en'})
    monkeypatch.setattr(config, 'get_config', lambda: {})
    monkeypatch.setattr(session_history, 'get_agent_sessions_dir', lambda: tmp_path / 'sessions')
    monkeypatch.setattr(utils, 'get_agent_sessions_dir', lambda: tmp_path / 'sessions')
    monkeypatch.setattr(utils, 'get_default_project_session_workspace_dir', lambda: tmp_path)
    model = ResolvedModel(model_id='shared', source='defaults', model_name='shared-model', provider='OpenAI', api_base='http://127.0.0.1:1234/v1', api_key='private-test-key')
    monkeypatch.setattr(codex, 'resolve_model', lambda req: model)
    return interface.JiuWenSwarm(), {'codex': {'enabled': True}, 'permissions': {'enabled': True}}, clients, tmp_path, model


def request(sid='one', method=ReqMethod.CHAT_SEND, **params):
    return AgentRequest(request_id='request', channel_id='web', session_id=sid, req_method=method, is_stream=True, params={'mode': 'agent', 'query': 'test', **params})


@pytest.mark.asyncio
@pytest.mark.parametrize('exit_code,success', [(0, True), (7, False), (None, None), (True, None)])
async def test_facade_history_exit_and_shared_model(host, exit_code, success):
    app, config, clients, root, _ = host
    await app.create_instance(config)
    try:
        # First turn allocates the client; the next turn tests the result and continuity.
        _ = [item async for item in app.process_message_stream(request())]
        clients[0].exit_code = exit_code
        result = [item.payload async for item in app.process_message_stream(request())]
        command = next(item for item in result if item.get('event_type') == 'chat.tool_result')
        assert command['success'] is success
        assert command['task_acceptance'] == 'unknown'
        assert command['exit_code'] == (exit_code if type(exit_code) is int else None)
        assert clients[0].turns == 2
        assert len(clients) == 1
        assert clients[0].options['model'] == 'shared-model'
        assert clients[0].config.env['SWARM_CODEX_MODEL_KEY'] == 'private-test-key'
        assert not any('private-test-key' in arg for arg in clients[0].config.config_overrides)
        history = session_history.read_session_history_records('one')
        assert any(row.get('event_type') == 'chat.final' and row.get('content') == 'reply' for row in history)
    finally:
        await app.cleanup()
    assert clients[0].closed
    assert not list((root / 'sessions/.codex-direct').iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize('answer,decision', [('allow_once', 'accept'), ('reject', 'decline')])
async def test_facade_original_control_path(host, answer, decision):
    app, config, clients, _, _ = host
    await app.create_instance(config)
    try:
        _ = [c async for c in app.process_message_stream(request())]
        clients[0].approval = True
        questions = []
        async for chunk in app.process_message_stream(request()):
            p = chunk.payload or {}
            if p.get('event_type') == 'chat.ask_user_question':
                questions.append(p)
                params = {'request_id': p['request_id'], 'source': p['source'], 'answers': [{'selected_options': [answer]}]}
                control = request(method=ReqMethod.CHAT_ANSWER, **params)
                _ = [c async for c in app.deliver_control_input(control)]
                with pytest.raises(ValueError, match='matching active'):
                    _ = [c async for c in app.deliver_control_input(control)]
        assert len(questions) == 1
        assert clients[0].decisions == [{'decision': decision}]
        assert clients[0].turns == 2
        assert any(row.get('event_type') == 'chat.ask_user_question' for row in session_history.read_session_history_records('one'))
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_cancel_pending_releases_sdk_reader(host):
    app, config, clients, _, _ = host
    await app.create_instance(config)
    try:
        _ = [c async for c in app.process_message_stream(request())]
        clients[0].approval = True
        async with asyncio.timeout(5):
            async for chunk in app.process_message_stream(request()):
                if (chunk.payload or {}).get('event_type') == 'chat.ask_user_question':
                    await app.process_message(request(method=ReqMethod.CHAT_CANCEL, intent='cancel'))
        assert clients[0].decisions == [{'decision': 'cancel'}]
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_requested', [False, True])
async def test_stream_close_cleans_even_interrupt_fails(host, cancel_requested):
    app, config, clients, root, _ = host
    await app.create_instance(config)
    try:
        _ = [c async for c in app.process_message_stream(request())]
        clients[0].approval = True
        clients[0].interrupt_error = True
        producer = app._adapter.process_message_stream_impl(request(), {'query': 'test'})
        chunk = await anext(producer)
        assert chunk.payload['event_type'] == 'chat.ask_user_question'
        if cancel_requested:
            with pytest.raises(RuntimeError, match='interruption failed'):
                await app.process_message(request(method=ReqMethod.CHAT_CANCEL, intent='cancel'))
        await producer.aclose()
        assert clients[0].closed
        assert not app.has_session_runtime('one')
    finally:
        await app.cleanup()


def test_installed_catalog_and_config_snapshot():
    import json
    from jiuwenswarm.common.config_panel.execution_provider_settings import public_fields
    from jiuwenswarm.server.runtime.agent_adapter.agent_adapters import adapter_config_snapshot
    config = {'modes': {'team': {'jiuwen_team': {'external_cli_agents': ['codex']}}}}
    catalog = json.loads(public_fields(config)['execution_provider_catalog'])
    assert next(row for row in catalog if row['id'] == 'codex-direct')['available']
    assert adapter_config_snapshot('codex-direct', config) == {'codex': {'enabled': True, 'cli_path': None}}
    catalog = json.loads(public_fields({})['execution_provider_catalog'])
    assert next(row for row in catalog if row['id'] == 'codex-direct')['reason'] == 'disabled'


@pytest.mark.asyncio
async def test_two_sessions_and_cross_session_control_rejected(host):
    app, config, clients, _, _ = host
    await app.create_instance(config)
    try:
        await asyncio.gather(*[consume(app.process_message_stream(request(sid))) for sid in ('a', 'b')])
        assert len(clients) == 2
        assert clients[0].thread_id != clients[1].thread_id
        assert clients[0].config.env['CODEX_HOME'] != clients[1].config.env['CODEX_HOME']
        for client in clients:
            client.approval = True
        async for chunk in app.process_message_stream(request('a')):
            p = chunk.payload or {}
            if p.get('event_type') == 'chat.ask_user_question':
                control = {'request_id': p['request_id'], 'source': p['source'], 'answers': [{'selected_options': ['reject']}]}
                with pytest.raises(ValueError, match='matching active'):
                    await consume(app.deliver_control_input(request('b', ReqMethod.CHAT_ANSWER, **control)))
                await consume(app.deliver_control_input(request('a', ReqMethod.CHAT_ANSWER, **control)))
        assert sum(len(c.decisions) for c in clients) == 1
    finally:
        await app.cleanup()


async def consume(stream):
    return [item async for item in stream]


@pytest.mark.asyncio
async def test_permission_update_preserves_thread_and_waits_for_next_turn(host):
    app, config, clients, _, _ = host
    await app.create_instance(config)
    try:
        await consume(app.process_message_stream(request()))
        original = clients[0].thread_id
        await app.reload_agent_config(config_base={'permissions': {'enabled': False}}, target_session_id='one', reload_scopes=['permissions'])
        assert clients[0].options['approvalPolicy'] == 'on-request'
        await consume(app.process_message_stream(request()))
        assert clients[0].thread_id == original
        assert clients[0].options['approvalPolicy'] == 'never'
        assert app.runtime_permission_status('one')['effective_profile'] == 'full_access'
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_unsupported_equipment_and_workspace_change_are_rejected(host):
    app, config, clients, root, _ = host
    await app.create_instance(config)
    try:
        with pytest.raises(ValueError, match='equipment'):
            await consume(app.process_message_stream(request(skills=['unmapped'])))
        assert not clients
        await consume(app.process_message_stream(request()))
        other = root / 'other'; other.mkdir()
        rejected = await consume(app.process_message_stream(request(project_dir=str(other))))
        assert any((c.payload or {}).get('event_type') == 'chat.error' and 'workspace cannot change' in str(c.payload) for c in rejected)
        assert clients[0].turns == 1
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_sdk_startup_error_is_safe_and_closes_owned_client(host, monkeypatch):
    app, config, clients, root, _ = host
    def fail(self):
        raise RuntimeError('credential=PRIVATE_SECRET https://private.invalid')
    monkeypatch.setattr(FakeClient, 'initialize', fail)
    await app.create_instance(config)
    try:
        chunks = await consume(app.process_message_stream(request()))
        assert any((c.payload or {}).get('event_type') == 'chat.error' for c in chunks)
        assert 'PRIVATE_SECRET' not in str(chunks)
        assert clients[0].closed
    finally:
        await app.cleanup()


def test_no_core_model_catalog_refresh_without_team_catalog(monkeypatch):
    from jiuwenswarm.common import external_cli_catalog as catalog
    monkeypatch.setattr(catalog, 'get_config', lambda: {'modes': {'team': {'jiuwen_team': {'external_cli_agents': ['codex']}}}})
    assert catalog.refresh_external_cli_builtin_models() == []


def test_declined_command_is_not_ui_success_or_invented_exit():
    result = codex.command_result({'id': 'declined', 'status': 'declined'})
    assert result['status'] == 'error'
    assert result['invocation_status'] == 'declined'
    assert result['command_success'] is None
    assert result['success'] is None
    assert result['exit_code'] is None
    assert 'permission declined' in result['content']


@pytest.mark.asyncio
async def test_bad_explicit_cli_never_falls_back_to_sdk(host):
    app, config, clients, root, _ = host
    config['codex']['cli_path'] = str(root / 'missing-codex')
    with pytest.raises(ValueError, match='Configured CLI is unavailable'):
        await app.create_instance(config)
    assert not clients
    await app.cleanup()


@pytest.mark.asyncio
async def test_goal_poll_is_empty_and_mutation_is_explicitly_unsupported(host):
    app, config, clients, root, _ = host
    await app.create_instance(config)
    try:
        for action in ('get', 'set'):
            req = request()
            req.req_method = ReqMethod.COMMAND_GOAL
            req.params['action'] = action
            response = await app.process_message(req)
            assert response.ok is (action == 'get')
            assert response.payload['goal'] is None
            if action == 'set':
                assert response.payload['code'] == 'provider_capability_unsupported'
        assert not clients
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('messages,expected', [
    ([('commentary', 'working'), ('final_answer', 'answer')], 'answer'),
    ([(None, 'working'), (None, 'answer')], 'answer'),
    ([('final_answer', 'answer'), ('commentary', 'trailing observation')], 'answer'),
])
async def test_facade_final_uses_native_message_phase_without_repeating_commentary(host, messages, expected):
    app, config, clients, root, _ = host
    await app.create_instance(config)
    try:
        _ = [item async for item in app.process_message_stream(request())]
        clients[0].messages = messages
        chunks = [item.payload async for item in app.process_message_stream(request())]
        assert [item['content'] for item in chunks if item.get('event_type') == 'chat.final'] == [expected]
        history = session_history.read_session_history_records('one')
        assert [item['content'] for item in history if item.get('event_type') == 'chat.final'][-1] == expected
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("sdk_version", ["0.144.4", "0.999.0"])
async def test_facade_does_not_gate_sdk_or_require_bundled_cli_by_version(host, monkeypatch, sdk_version):
    import importlib.metadata
    from jiuwenswarm.common import codex_adapter_config
    app, config, clients, root, _ = host
    checked = []
    def version(name):
        checked.append(name)
        if name != "openai-codex":
            raise importlib.metadata.PackageNotFoundError(name)
        return sdk_version
    monkeypatch.setattr(importlib.metadata, "version", version)
    enabled = {"modes": {"team": {"jiuwen_team": {"external_cli_agents": ["codex"]}}}}
    assert codex_adapter_config.availability(enabled) is None
    await app.create_instance(config)
    try:
        chunks = [item.payload async for item in app.process_message_stream(request())]
        assert any(item.get("event_type") == "chat.final" for item in chunks)
        assert clients[0].options["approvalPolicy"] == "on-request"
        assert clients[0].options["sandbox"] == "workspace-write"
        assert set(checked) == {"openai-codex"}
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_missing_sdk_is_reported_at_catalog_and_facade(host, monkeypatch):
    import importlib.metadata
    from jiuwenswarm.common import codex_adapter_config
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(importlib.metadata, "version", missing)
    enabled = {"modes": {"team": {"jiuwen_team": {"external_cli_agents": ["codex"]}}}}
    assert codex_adapter_config.availability(enabled) == "sdk_not_installed"
    app, config, clients, root, _ = host
    with pytest.raises(ValueError, match="official Codex SDK"):
        await app.create_instance(config)
    assert not clients
    await app.cleanup()


@pytest.mark.asyncio
async def test_sdk_without_approval_interface_fails_without_fallback(host, monkeypatch):
    import openai_codex.client
    def legacy_client(config):
        pytest.fail("must not retry without the approval handler")
    monkeypatch.setattr(openai_codex.client, "CodexClient", legacy_client)
    app, config, clients, root, _ = host
    await app.create_instance(config)
    try:
        chunks = [item.payload async for item in app.process_message_stream(request())]
        assert any("required client/approval interface" in str(item) for item in chunks)
        assert not any(item.get("event_type") == "chat.final" for item in chunks)
        assert not clients
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['approval', 'running'])
async def test_runtime_cancel_preserves_thread_for_next_turn(host, monkeypatch, stage):
    from jiuwenswarm.runtime import AgentRuntime
    from jiuwenswarm.common import config as config_module
    from jiuwenswarm.server.runtime.session import session_metadata

    _, _, clients, root, _ = host
    settings = {'preferred_language': 'en', 'permissions': {'enabled': True},
                'modes': {'team': {'jiuwen_team': {'external_cli_agents': ['codex']}}}}
    monkeypatch.setenv('JIUWENSWARM_AGENT_SDK', 'codex-direct')
    monkeypatch.setenv('JIUWENSWARM_DATA_DIR', str(root))
    monkeypatch.setattr(config_module, 'get_config', lambda: settings)
    monkeypatch.setattr(interface, 'get_config', lambda: settings)
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: root / 'sessions')
    runtime = AgentRuntime()
    def req(method=ReqMethod.CHAT_SEND):
        return request('resume-' + stage, method, project_dir=str(root),
                       execution_provider='codex-direct', intent='cancel', work_mode='work')
    async def drain():
        return [item async for item in runtime.stream(req())]
    producer = None
    try:
        assert any((x.payload or {}).get('event_type') == 'chat.final' for x in await drain())
        client = clients[0]
        original_thread = client.thread_id
        waiting = asyncio.Event()
        interrupts = []
        def interrupt_once(thread_id, turn_id):
            interrupts.append((thread_id, turn_id))
            if len(interrupts) > 1:
                raise RuntimeError('Turn already interrupted')
        monkeypatch.setattr(client, 'turn_interrupt', interrupt_once)
        # Keep the native terminal event pending while Runtime drains its producer.
        # The SDK fake has no alternate scheduler; only its transport is controlled.
        if stage == 'approval':
            client.approval = True
            monkeypatch.setattr(client, 'finish', lambda *args: None)
        else:
            def start(thread_id, prompt):
                assert thread_id == original_thread
                client.turns += 1
                client.turn_id = str(client.turns)
                client.emit('item/started', item={'id': 'running', 'type': 'commandExecution', 'command': 'sleep 30'})
                return SimpleNamespace(turn=SimpleNamespace(id=client.turn_id))
            monkeypatch.setattr(client, 'turn_start', start)
        async def consume():
            async for item in runtime.stream(req()):
                expected = 'chat.ask_user_question' if stage == 'approval' else 'chat.tool_call'
                if (item.payload or {}).get('event_type') == expected:
                    waiting.set()
        producer = asyncio.create_task(consume())
        await asyncio.wait_for(waiting.wait(), 5)
        reply = await runtime.cancel_request(req(ReqMethod.CHAT_CANCEL))
        assert reply.ok
        await asyncio.wait_for(asyncio.gather(producer, return_exceptions=True), 5)
        assert not client.closed
        assert interrupts == [(original_thread, '2')]
        client.approval = False
        monkeypatch.setattr(client, 'finish', FakeClient.finish.__get__(client))
        monkeypatch.setattr(client, 'turn_start', FakeClient.turn_start.__get__(client))
        client.messages = [(None, 'SAME_THREAD_CONTEXT')]
        result = await drain()
        assert any((x.payload or {}).get('content') == 'SAME_THREAD_CONTEXT' for x in result)
        assert len(clients) == 1 and client.thread_id == original_thread
    finally:
        if producer:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
        await runtime.close()
    assert clients[0].closed
    assert not list((root / 'sessions/.codex-direct').iterdir())


@pytest.mark.asyncio
async def test_stream_close_without_user_cancel_disposes_session(host):
    app, config, clients, _, _ = host
    await app.create_instance(config)
    try:
        _ = [item async for item in app.process_message_stream(request())]
        clients[0].approval = True
        producer = app._adapter.process_message_stream_impl(request(), {'query': 'test'})
        assert (await anext(producer)).payload['event_type'] == 'chat.ask_user_question'
        await producer.aclose()
        assert clients[0].closed
        assert not app.has_session_runtime('one')
    finally:
        await app.cleanup()
