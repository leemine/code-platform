"""Public Facade/control/history regressions; SDK fake is not real acceptance."""
import asyncio
import io
import json
import queue
from types import SimpleNamespace
from pathlib import Path

import pytest
from gateway.common.model_selection import ResolvedModel
from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponseChunk
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
        self.native_threads = {}
        self.turns = 0
        self.closed = False
        self.approval = False
        self.exit_code = 7
        self.interrupt_error = False
        self.decisions = []
        self.messages = [(None, "reply")]
        self.terminals = []
        self.terminated = []

    def request(self, method, params, *, response_model):
        assert params['threadId'] == self.thread_id
        if method == 'thread/backgroundTerminals/list':
            offset = int(params.get('cursor', 0))
            next_cursor = str(offset + 1) if offset + 1 < len(self.terminals) else None
            return response_model.model_validate({'data': self.terminals[offset:offset + 1], 'nextCursor': next_cursor})
        assert method == 'thread/backgroundTerminals/terminate'
        self.terminated.append(params['processId'])
        self.terminals = [t for t in self.terminals if t['processId'] != params['processId']]
        return response_model.model_validate({'terminated': True})

    def start(self):
        pass

    def initialize(self):
        pass

    def thread_start(self, options):
        self.options = options
        self.native_threads[self.thread_id] = self.config.env['CODEX_HOME']
        return self._policy()

    def thread_resume(self, thread_id, options):
        assert self.native_threads[thread_id] == self.config.env['CODEX_HOME']
        self.thread_id = thread_id
        self.options = options
        return self._policy()

    def _policy(self):
        response = SimpleNamespace(thread=SimpleNamespace(id=self.thread_id))
        response.thread.model_dump = lambda **kw: {'cwd': self.config.cwd, 'status': {'type': 'idle'}}
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
    native_threads = {}
    def factory(*args, **kwargs):
        client = FakeClient(*args, **kwargs)
        client.native_threads = native_threads
        clients.append(client)
        return client
    monkeypatch.setattr(openai_codex.client, 'CodexClient', factory)
    monkeypatch.setattr(interface, 'resolve_sdk_choice', lambda: 'codex-direct')
    monkeypatch.setattr(interface, 'get_config', lambda: {'preferred_language': 'en'})
    monkeypatch.setattr(config, 'get_config', lambda: {})
    monkeypatch.setattr(session_history, 'get_agent_sessions_dir', lambda: tmp_path / 'sessions')
    monkeypatch.setattr(utils, 'get_agent_sessions_dir', lambda: tmp_path / 'sessions')
    monkeypatch.setattr(utils, 'get_default_project_session_workspace_dir', lambda: tmp_path)
    model = ResolvedModel(model_id='shared', source='defaults', model_name='shared-model', fallback_tag='shared-model', provider='OpenAI', api_base='http://127.0.0.1:1234/v1', api_key='private-test-key')
    monkeypatch.setattr(codex, 'resolve_model', lambda req: model)
    # Stub only the SDK transport; model selection now uses the real host path.
    monkeypatch.setattr(interface, 'get_config', lambda: {'preferred_language': 'en', 'models': {'defaults': [{
        'model_id': model.model_id, 'model_client_config': {
            'client_provider': model.provider, 'model_name': model.model_name,
            'api_base': model.api_base, 'api_key': model.api_key,
            **model.client_options, **model.request_defaults,
        }}]}})
    return interface.JiuWenSwarm(), {'codex': {'enabled': True}, 'permissions': {'enabled': True}}, clients, tmp_path, model


def request(sid='one', method=ReqMethod.CHAT_SEND, **params):
    return AgentRequest(request_id='request', channel_id='web', session_id=sid, req_method=method, is_stream=True, params={'mode': 'agent', 'query': 'test', **params})


@pytest.mark.asyncio
@pytest.mark.parametrize('wrong_thread',[False,True])
@pytest.mark.parametrize('child_failed',[False,True])
@pytest.mark.parametrize('large_output',[False,True,None], ids=['short','long','not-returned'])
async def test_official_collab_child_snapshot_uses_original_history_and_parent_boundary(host, monkeypatch,wrong_thread,child_failed,large_output):
    from openai_codex.generated.v2_all import CollabAgentToolCallThreadItem
    app, config, clients, _, _ = host
    reads=[]
    child_output = None if large_output is None else '子工具输出🙂' * 20000 if large_output else 'CHILD TOOL OUTPUT'
    def finish(client, status='completed'):
        for tool, states in [('spawnAgent',{'child':{'status':'running','message':None}}),
                             ('wait',{'child':{'status':'errored' if child_failed else 'completed','message':'CHILD FAILURE' if child_failed else 'CHILD SUMMARY'},'stranger':{'status':'completed','message':'FOREIGN SECRET'}})]:
            for method, state in [('item/started','inProgress'),('item/completed','completed')]:
                item=CollabAgentToolCallThreadItem.model_validate({'id':tool,'type':'collabAgentToolCall',
                    'tool':tool,'status':state,'senderThreadId':client.thread_id,
                    'receiverThreadIds':['child'] if tool=='spawnAgent' else ['child','stranger'],
                    'agentsStates':states,'prompt':'Inspect architecture'})
                client.emit(method,item=item.model_dump(mode='json',by_alias=True))
        client.emit('item/completed',item={'id':'foreign','type':'collabAgentToolCall','tool':'spawnAgent','senderThreadId':'another-parent','receiverThreadIds':['foreign-child']})
        client.emit('item/completed',item={'id':'text','type':'agentMessage','text':'PARENT SUMMARY','phase':'final_answer'})
        client.emit('turn/completed',turn={'status':status})
    def thread_read(client, native_id, include_turns=False):
        reads.append(native_id)
        assert native_id=='child' and include_turns
        return Payload(thread={'id':'stranger' if wrong_thread else 'child','turns':[{'id':'child-turn','status':'failed' if child_failed else 'completed','items':[
            {'id':'child-command','type':'commandExecution','status':'failed' if child_failed else 'completed','exitCode':0 if child_failed else None,'aggregatedOutput':child_output},
            {'id':'child-final','type':'agentMessage','text':'CHILD SUMMARY','phase':'final_answer'}]}]})
    monkeypatch.setattr(FakeClient,'finish',finish)
    monkeypatch.setattr(FakeClient,'thread_read',thread_read,raising=False)
    await app.create_instance(config)
    try:
        chunks=[x.payload async for x in app.process_message_stream(request())]
        assert reads==['child','child']
        assert not any('FOREIGN SECRET' in str(x) for x in chunks)
        activities=[x for x in chunks if x.get('event_type')=='chat.subagent_activity']
        output=[x for x in activities if x.get('tool_call_id')=='child-command']
        assert len(output)==(0 if wrong_thread else 1)
        if output:
            assert output[0].get('ok') is (False if child_failed else None)
            assert len(output[0]['summary']) <= 2000
            if large_output:
                assert 'Output truncated' in output[0]['summary']
                assert child_output.startswith(output[0]['summary'].split('\n[Output truncated')[0])
            else:
                assert output[0]['summary'] == (child_output or '')
        assert next(x for x in chunks if x.get('event_type')=='chat.final')['content']=='PARENT SUMMARY'
        from jiuwenswarm.server.control.history_service import load_history_page
        session_history.flush_history_writes()
        page=load_history_page('one',1,subagent_id='codex-child')
        assert any(x.get('content')==('CHILD FAILURE' if child_failed else 'CHILD SUMMARY') for x in page['messages'])
        assert [x for x in chunks if x.get('event_type')=='chat.subtask_update'][-1]['turn_outcome']==('failed' if child_failed else 'completed')
        assert any(x.get('subagent_activity',{}).get('task_id')=='child-turn' for x in page['messages']) is not wrong_thread
        if output:
            saved = next(x for x in page['messages'] if x.get('subagent_activity',{}).get('tool_call_id')=='child-command')
            assert saved['content'] == output[0]['summary']
        assert 'codex-child' in session_history.list_session_subagent_ids('one')
        assert 'codex-foreign-child' not in session_history.list_session_subagent_ids('one')
    finally:await app.cleanup()


@pytest.mark.parametrize('size', [0, 59999, 60000, 60001])
def test_command_output_boundary_preserves_short_text_and_native_facts(size):
    text = 'x' * size
    native = {'id': 'limit', 'status': 'completed', 'exitCode': 0, 'aggregatedOutput': text}
    result = codex.command_result(native)
    assert result['content'] == result['result']
    assert len(result['result']) <= 60000
    assert native['aggregatedOutput'] == text
    assert result['exit_code'] == 0 and result['success'] is True
    assert result['task_acceptance'] == 'unknown'
    assert 'rendered_result' not in result
    if size <= 60000:
        assert result['result'] == text and 'provider' not in result
    else:
        assert 'Output truncated' in result['result']
        assert result['provider']['codex']['received_output_chars'] == size


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['\x00' * 1048610, '汉字🙂' * 350000, '\\"\n' * 350000], ids=['escaped-controls', 'unicode', 'quotes-newlines'])
@pytest.mark.parametrize('exit_code', [0, 7, None])
async def test_large_command_through_facade_history_wire_and_cli(host, monkeypatch, text, exit_code):
    from gateway.common.ws_limits import AGENT_WS_SEND_BUDGET_BYTES
    from jiuwenswarm.common.e2a.wire_codec import encode_agent_chunk_for_wire, parse_agent_server_wire_chunk
    from jiuwenswarm.channels.process_cli.render import EventRenderer
    from jiuwenswarm.runtime.events import RuntimeEvent
    from jiuwenswarm.server.ws_send import send_wire_payload
    from jiuwenswarm.server.control.history_service import load_history_page
    app, config, clients, _, _ = host
    native = {'id': 'large-command', 'type': 'commandExecution', 'status': 'completed',
              'exitCode': exit_code, 'aggregatedOutput': text}
    def finish(client, status='completed'):
        client.emit('item/completed', item=native)
        client.emit('item/completed', item={'id': 'answer', 'type': 'agentMessage', 'text': 'done', 'phase': 'final_answer'})
        client.emit('turn/completed', turn={'status': status})
    monkeypatch.setattr(FakeClient, 'finish', finish)
    class WebSocket:
        sent = None
        async def send(self, payload):
            self.sent = payload
    await app.create_instance(config)
    try:
        chunks = [chunk async for chunk in app.process_message_stream(request())]
        assert not any(x.payload.get('event_type') == 'chat.error' for x in chunks)
        chunk = next(x for x in chunks if x.payload.get('event_type') == 'chat.tool_result')
        result = chunk.payload
        assert len(result['content']) <= 60000
        assert result['content'] == result['result']
        assert 'Output truncated' in result['result']
        assert result['invocation_status'] == 'completed'
        assert result['exit_code'] == exit_code
        assert result['success'] is (None if exit_code is None else exit_code == 0)
        assert result['command_success'] is result['success']
        assert result['task_acceptance'] == 'unknown'
        assert 'rendered_result' not in result
        assert result['provider']['codex'] == {
            'output_truncated': True,
            'received_output_chars': len(text), 'received_output_bytes': len(text.encode('utf-8')),
            'displayed_output_chars': len(result['result']),
            'displayed_output_bytes': len(result['result'].encode('utf-8')),
        }
        assert native['aggregatedOutput'] == text
        ws = WebSocket()
        if text[0] == '\x00':
            # Reproduce JSON escaping plus both legacy aliases against the real guard.
            legacy = AgentResponseChunk(request_id=chunk.request_id, channel_id=chunk.channel_id,
                                        payload={**result, 'content': text, 'result': text})
            oversized = encode_agent_chunk_for_wire(legacy, response_id='unbounded', sequence=1)
            assert not await send_wire_payload(ws, oversized)
            fallback = parse_agent_server_wire_chunk(json.loads(ws.sent))
            assert fallback.payload['code'] == 'response_too_large'
        wire = encode_agent_chunk_for_wire(chunk, response_id='bounded', sequence=1)
        assert await send_wire_payload(ws, wire)
        assert len(ws.sent.encode('utf-8')) < AGENT_WS_SEND_BUDGET_BYTES
        restored = parse_agent_server_wire_chunk(json.loads(ws.sent))
        assert restored.payload == result
        session_history.flush_history_writes()
        page = load_history_page('one', 1)
        saved = next(x for x in page['messages'] if x.get('tool_call_id') == 'large-command')
        assert saved['content'] == saved['result'] == result['result']
        assert saved['provider'] == result['provider'] and saved['exit_code'] == exit_code
        stream = io.StringIO()
        EventRenderer('jsonl', stdout=stream).render(RuntimeEvent(
            request_id='cli', session_id='one', channel_id='tui', payload=restored.payload))
        assert json.loads(stream.getvalue())['payload']['result'] == result['result']
        human = io.StringIO()
        EventRenderer('human', stdout=human, stderr=human, show_tools=True).render(RuntimeEvent(
            request_id='cli', session_id='one', channel_id='tui', payload=restored.payload))
        assert 'Output truncated' in human.getvalue()
        assert next(x.payload for x in chunks if x.payload.get('event_type') == 'chat.final')['content'] == 'done'
        _ = [chunk async for chunk in app.process_message_stream(request())]
        assert len(clients) == 1 and clients[0].turns == 2
    finally:
        await app.cleanup()


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
    from jiuwenswarm.server.runtime.agent_adapter.providers import session_recovery
    binding = session_recovery.load('codex', 'one', str(root))
    assert binding['native_id'] == clients[0].thread_id
    assert Path(binding['root']) == Path(clients[0].config.env['CODEX_HOME']).parent
    assert Path(binding['root']).is_dir()


@pytest.mark.asyncio
async def test_new_facade_resumes_original_thread_and_private_home(host):
    first, config, clients, _, _ = host
    await first.create_instance(config)
    try:
        _ = [chunk async for chunk in first.process_message_stream(request())]
        original_thread = clients[0].thread_id
        original_home = clients[0].config.env['CODEX_HOME']
    finally:
        await first.cleanup()
    assert clients[0].closed
    second = interface.JiuWenSwarm()
    await second.create_instance(config)
    try:
        chunks = [chunk.payload async for chunk in second.process_message_stream(request())]
        assert any(chunk.get('event_type') == 'chat.final' for chunk in chunks)
        assert len(clients) == 2
        assert clients[1].thread_id == original_thread
        assert clients[1].config.env['CODEX_HOME'] == original_home
    finally:
        await second.cleanup()


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
async def test_stream_close_fences_unconfirmed_stop_with_or_without_user_cancel(host, cancel_requested):
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
            with pytest.raises(RuntimeError, match='could not be confirmed'):
                await app.process_message(request(method=ReqMethod.CHAT_CANCEL, intent='cancel'))
        await producer.aclose()
        assert not clients[0].closed
        assert app.has_session_runtime('one')
        with pytest.raises(RuntimeError, match='cancellation is not confirmed'):
            await anext(app._adapter.process_message_stream_impl(request(), {'query': 'unsafe resume'}))
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
@pytest.mark.parametrize('stage', ['approval', 'running', 'startup'])
@pytest.mark.parametrize('failure', [None, 'unsupported', 'still_running', 'missing_terminal', 'closed_stream'])
async def test_runtime_cancel_preserves_thread_for_next_turn(host, monkeypatch, stage, failure):
    from jiuwenswarm.runtime import AgentRuntime
    from jiuwenswarm.common import config as config_module
    from jiuwenswarm.server.runtime.session import session_metadata

    _, _, clients, root, _ = host
    settings = {'preferred_language': 'en', 'permissions': {'enabled': True},
                'models': interface.get_config()['models'],
                'modes': {'team': {'jiuwen_team': {'external_cli_agents': ['codex']}}}}
    monkeypatch.setenv('JIUWENSWARM_AGENT_SDK', 'codex-direct')
    monkeypatch.setenv('JIUWENSWARM_DATA_DIR', str(root))
    monkeypatch.setattr(config_module, 'get_config', lambda: settings)
    monkeypatch.setattr(interface, 'get_config', lambda: settings)
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: root / 'sessions')
    runtime = AgentRuntime()
    sid = f'resume-{stage}-{failure or "normal"}'
    def req(method=ReqMethod.CHAT_SEND):
        return request(sid, method, project_dir=str(root),
                       execution_provider='codex-direct', intent='cancel', work_mode='work')
    async def drain():
        return [item async for item in runtime.stream(req())]
    producer = None
    import threading
    startup_release = threading.Event()
    try:
        assert any((x.payload or {}).get('event_type') == 'chat.final' for x in await drain())
        client = clients[0]
        original_thread = client.thread_id
        waiting = asyncio.Event()
        interrupts = []
        loop = asyncio.get_running_loop()
        def interrupt_once(thread_id, turn_id):
            interrupts.append((thread_id, turn_id))
            if len(interrupts) > 1:
                raise RuntimeError('Turn already interrupted')
            if failure == 'closed_stream':
                client.events.put(RuntimeError('Connection lost before native terminal'))
            elif failure != 'missing_terminal':
                # ACK comes first; the only producer receives terminal later.
                loop.call_soon_threadsafe(loop.call_later, .03,
                    lambda: client.emit('turn/completed', turn={'status': 'interrupted'}))
        monkeypatch.setattr(client, 'turn_interrupt', interrupt_once)
        # ACK must not drain the producer before its delayed native terminal.
        # The SDK fake has no alternate scheduler; only its transport is controlled.
        if stage == 'approval':
            client.approval = True
            monkeypatch.setattr(client, 'finish', lambda *args: None)
        else:
            client.terminals = [{'itemId': 'older-turn', 'processId': 'old'},
                                {'itemId': 'running', 'processId': 'current'}]
            def start(thread_id, prompt):
                assert thread_id == original_thread
                client.turns += 1
                client.turn_id = str(client.turns)
                if stage == 'startup':
                    loop.call_soon_threadsafe(waiting.set)
                    assert startup_release.wait(5)
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
        if failure == 'missing_terminal':
            monkeypatch.setattr(codex, '_CANCEL_TIMEOUT', .15)
        original_rpc = client.request
        def failing_rpc(method, params, *, response_model):
            if failure == 'unsupported':
                raise RuntimeError('unsupported official API')
            if method.endswith('/terminate'):
                return response_model.model_validate({'terminated': False})
            return original_rpc(method, params, response_model=response_model)
        if stage != 'approval' and failure in {'unsupported', 'still_running'}:
            monkeypatch.setattr(client, 'request', failing_rpc)
        if stage == 'startup':
            loop.call_later(.03, startup_release.set)
        should_fail = failure in {'missing_terminal', 'closed_stream'} or (failure is not None and stage != 'approval')
        if should_fail:
            with pytest.raises(RuntimeError, match='could not be confirmed'):
                await runtime.cancel_request(req(ReqMethod.CHAT_CANCEL))
            assert client.turns == 2 and not client.closed
            if failure == 'missing_terminal':
                client.emit('turn/completed', turn={'status': 'interrupted'})
                await asyncio.wait_for(producer, 5)
                monkeypatch.setattr(codex, '_CANCEL_TIMEOUT', 5)
            rejected = await drain()
            assert not any((x.payload or {}).get('event_type') == 'chat.final' for x in rejected)
            assert client.turns == 2
            if failure == 'closed_stream':
                with pytest.raises(RuntimeError, match='could not be confirmed'):
                    await runtime.cancel_request(req(ReqMethod.CHAT_CANCEL))
                assert client.turns == 2 and not client.closed
                return
            monkeypatch.setattr(client, 'request', original_rpc)
        # Duplicate controls serialize locally; neither interrupts nor terminates twice.
        reply, duplicate = await asyncio.gather(runtime.cancel_request(req(ReqMethod.CHAT_CANCEL)),
                                                runtime.cancel_request(req(ReqMethod.CHAT_CANCEL)))
        assert reply.ok
        assert duplicate.ok
        await asyncio.wait_for(asyncio.gather(producer, return_exceptions=True), 5)
        assert not client.closed
        assert interrupts == [(original_thread, '2')]
        if stage != 'approval':
            assert client.terminated == ['current']
            assert client.terminals == [{'itemId': 'older-turn', 'processId': 'old'}]
        client.approval = False
        monkeypatch.setattr(client, 'finish', FakeClient.finish.__get__(client))
        monkeypatch.setattr(client, 'turn_start', FakeClient.turn_start.__get__(client))
        client.messages = [(None, 'SAME_THREAD_CONTEXT')]
        result = await drain()
        assert any((x.payload or {}).get('content') == 'SAME_THREAD_CONTEXT' for x in result)
        assert len(clients) == 1 and client.thread_id == original_thread
    finally:
        startup_release.set()
        if producer:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
        await runtime.close()
    assert clients[0].closed
    from jiuwenswarm.server.runtime.agent_adapter.providers import session_recovery
    binding = session_recovery.load('codex', sid, str(root))
    assert binding['native_id'] == original_thread
    assert Path(binding['root']).is_dir()


@pytest.mark.asyncio
async def test_stream_close_without_native_terminal_keeps_stop_fence(host):
    app, config, clients, _, _ = host
    await app.create_instance(config)
    try:
        _ = [item async for item in app.process_message_stream(request())]
        clients[0].approval = True
        producer = app._adapter.process_message_stream_impl(request(), {'query': 'test'})
        assert (await anext(producer)).payload['event_type'] == 'chat.ask_user_question'
        await producer.aclose()
        assert not clients[0].closed
        assert app.has_session_runtime('one')
        with pytest.raises(RuntimeError, match='cancellation is not confirmed'):
            await anext(app._adapter.process_message_stream_impl(request(), {'query': 'unsafe resume'}))
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('verify_ssl', [True, False, None])
async def test_facade_model_client_tls_flag_does_not_override_codex_transport(host, monkeypatch, verify_ssl):
    from jiuwenswarm.common import codex_adapter_config, model_catalog
    app, config, clients, root, model = host
    client_options = {'client_provider': 'OpenAI', 'model_name': 'shared-model',
                      'api_base': 'https://example.invalid/v1', 'api_key': 'private-test-key'}
    if verify_ssl is not None:
        client_options['verify_ssl'] = verify_ssl
    saved = {'models': {'defaults': [{'model_id': 'tls-model', 'model_client_config': client_options}]}}
    monkeypatch.setattr(model_catalog, 'get_config', lambda: saved)
    monkeypatch.setattr(interface, 'get_config', lambda: saved)
    monkeypatch.setattr(codex, 'resolve_model', codex_adapter_config.resolve_model)
    await app.create_instance(config)
    try:
        chunks = [p.payload async for p in app.process_message_stream(request(model_selection={'type': 'model', 'id': 'tls-model'}))]
        assert any(p.get('event_type') == 'chat.final' for p in chunks)
        assert not any(p.get('event_type') == 'chat.error' for p in chunks)
        options = clients[0].config
        assert not any('verify_ssl' in value or 'insecure' in value for value in options.config_overrides)
        assert options.env['SWARM_CODEX_MODEL_KEY'] == 'private-test-key'
        assert not any('CERT' in key or 'TLS' in key or 'SSL' in key for key in options.env)
        actual = saved['models']['defaults'][0]['model_client_config']
        if verify_ssl is None:
            assert 'verify_ssl' not in actual
        else:
            assert actual['verify_ssl'] is verify_ssl
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_model_timeout_is_not_a_turn_deadline_and_native_idle_is_projected(host, monkeypatch):
    import time
    app, config, clients, _, model = host
    model.client_options['timeout'] = 0.01
    config['codex']['stream_idle_timeout_ms'] = 42000
    receive = FakeClient.next_turn_notification
    def delayed_tool(self, turn_id):
        time.sleep(0.02)
        return receive(self, turn_id)
    monkeypatch.setattr(FakeClient, 'next_turn_notification', delayed_tool)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        assert 'model_providers.swarm.stream_idle_timeout_ms=42000' in clients[0].config.config_overrides
        assert any(x.get('event_type') == 'chat.final' for x in chunks)
        assert not any(x.get('event_type') == 'chat.error' for x in chunks)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_facade_prepared_input_is_not_reresolved_by_provider(host, monkeypatch):
    app, config, clients, root, _ = host
    await app.create_instance(config)
    original = app._build_inputs
    prepared = []
    def build(req):
        inputs, memory, turn = original(req)
        execution = inputs['_host_execution']
        prepared.append(execution)
        assert 'private-' not in repr(execution)
        # Neither the Provider's compatibility resolver nor later configuration
        # reads may replace the model already chosen by the original Facade.
        def unexpected(*args, **kwargs):
            raise AssertionError('Provider reinterpreted host model configuration')
        monkeypatch.setattr(codex, 'resolve_model', unexpected)
        return inputs, memory, turn
    monkeypatch.setattr(app, '_build_inputs', build)
    try:
        chunks = [item.payload async for item in app.process_message_stream(request(project_dir=str(root), _host_execution={'model': 'FORGED_CLIENT_INPUT'}))]
        assert len(prepared) == 1 and prepared[0].directory == str(root)
        assert any(p.get('event_type') == 'chat.final' for p in chunks)
        assert not any(p.get('event_type') == 'chat.error' for p in chunks)
        assert clients
        assert 'FORGED_CLIENT_INPUT' not in str(chunks)
        assert prepared[0].model.model_id == 'shared'
        from jiuwenswarm.server.runtime.agent_adapter.execution_input import prepared_input
        with pytest.raises(ValueError, match='does not belong'):
            prepared_input(request('another-session'), {'_host_execution': prepared[0]})
    finally:
        await app.cleanup()


def emit_native_usage(client, total, *, last=None, window=200000, thread=None, turn=None):
    from openai_codex.generated.v2_all import ThreadTokenUsageUpdatedNotification
    native = ThreadTokenUsageUpdatedNotification.model_validate({
        'threadId': thread or client.thread_id, 'turnId': turn or client.turn_id,
        'tokenUsage': {'total': total, 'last': last or total, 'modelContextWindow': window},
    })
    client.events.put(SimpleNamespace(method='thread/tokenUsage/updated', payload=native))


@pytest.mark.asyncio
async def test_native_usage_updates_existing_facade_wire_history_without_summing_snapshots(host, monkeypatch):
    from dataclasses import replace
    from jiuwenswarm.common.e2a.wire_codec import encode_agent_chunk_for_wire, parse_agent_server_wire_chunk
    from jiuwenswarm.server.control.history_service import load_history_page
    app, config, clients, _, _ = host
    original = FakeClient.finish
    def finish(client, status='completed'):
        base = (client.turns - 1) * 210
        for count in [100, 100, 210]:
            usage = {'inputTokens': base + count, 'outputTokens': client.turns * 28,
                     'totalTokens': base + count + client.turns * 28,
                     'cachedInputTokens': 0, 'reasoningOutputTokens': 3}
            emit_native_usage(client, usage)
        # Foreign and stale events must not contaminate the bound root totals.
        emit_native_usage(client, usage, thread='foreign')
        emit_native_usage(client, usage, turn='stale-turn')
        original(client, status)
    monkeypatch.setattr(FakeClient, 'finish', finish)
    await app.create_instance(config)
    try:
        previous_revision = 0
        for index in [1, 2]:
            frames = [chunk async for chunk in app.process_message_stream(replace(request(), request_id=f'usage-{index}'))]
            chunks = [x.payload for x in frames]
            updates = [x for x in chunks if x.get('event_type') == 'chat.usage_summary']
            assert len(updates) == 2
            assert updates[-1]['usage']['input_tokens'] == 210
            assert updates[-1]['usage']['output_tokens'] == 28
            total = updates[-1]['session_usage']
            assert total['main']['input_tokens'] == index * 210
            assert total['main']['output_tokens'] == index * 28
            assert total['main']['total_tokens'] == index * 238
            assert total['main']['cached_input_tokens'] == 0
            assert 'cache_write_input_tokens' not in total['main']
            assert all(total['main'][key] is None for key in ['input_calls', 'output_calls', 'calls_total'])
            assert all(value is None for value in total['others'].values())
            assert total['revision'] > previous_revision
            previous_revision = total['revision']
            context = next(x for x in chunks if x.get('event_type') == 'context.usage')
            assert context['request_id'] == f'usage-{index}'
            assert context['context_window'] == {'limit_tokens': 200000, 'input_tokens': None, 'occupancy_rate': None}
            assert context['session_kv_cache_hit_rate'] is None
            assert any(x.get('content') == 'reply' for x in chunks)
            assert not any(x.get('event_type') == 'chat.error' for x in chunks)
            wire = [parse_agent_server_wire_chunk(encode_agent_chunk_for_wire(c, response_id=f'wire-{index}', sequence=i)).payload for i, c in enumerate(frames, 1)]
            assert [x['session_usage'] for x in wire if x.get('event_type') == 'chat.usage_summary'][-1] == total
        session_history.flush_history_writes()
        page = load_history_page('one', 1)
        saved = [x for x in page['messages'] if x.get('event_type') == 'chat.usage_summary']
        assert len(saved) == 4
        assert max(saved, key=lambda x: x['session_usage']['revision'])['session_usage']['main']['input_tokens'] == 420
        assert len(clients) == 1 and clients[0].turns == 2
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['completed', 'interrupted', 'failed'])
async def test_usage_native_terminal_does_not_change_outcome_or_invent_recovery_baseline(host, monkeypatch, status):
    app, config, clients, _, _ = host
    original = FakeClient.finish
    def finish(client, ignored='completed'):
        count = client.turns * 100
        emit_native_usage(client, {'inputTokens': count, 'outputTokens': count // 5,
                                  'totalTokens': count + count // 5,
                                  'cachedInputTokens': 0, 'reasoningOutputTokens': 0}, window=None)
        original(client, status if client.turns == 1 else 'completed')
    monkeypatch.setattr(FakeClient, 'finish', finish)
    await app.create_instance(config)
    try:
        first = [x.payload async for x in app.process_message_stream(request())]
        assert any(x.get('event_type') == 'chat.usage_summary' for x in first)
        assert not any(x.get('event_type') == 'context.usage' for x in first)
        assert any(x.get('event_type') == 'chat.error' for x in first) is (status != 'completed')
        if status == 'completed':
            assert any(x.get('content') == 'reply' for x in first)
        second = [x.payload async for x in app.process_message_stream(request())]
        update = next(x for x in second if x.get('event_type') == 'chat.usage_summary')
        assert update['session_usage']['main']['input_tokens'] == 200
        assert ('usage' in update) is (status == 'completed')
    finally:
        await app.cleanup()
    # New Facade resumes the same native thread but has no proven turn baseline.
    restored = interface.JiuWenSwarm()
    await restored.create_instance(config)
    try:
        chunks = [x.payload async for x in restored.process_message_stream(request())]
        update = next(x for x in chunks if x.get('event_type') == 'chat.usage_summary')
        assert 'usage' not in update
        session_history.flush_history_writes()
        text = (Path(session_history.get_agent_sessions_dir()) / 'one/history.jsonl').read_text()
        assert 'session_usage' in text
    finally:
        await restored.cleanup()


@pytest.mark.asyncio
async def test_missing_partial_and_reset_usage_are_observation_only(host, monkeypatch):
    app, config, _, _, _ = host
    original = FakeClient.finish
    def finish(client, status='completed'):
        for usage in [None, {}, {'total': {'inputTokens': True, 'outputTokens': -1, 'totalTokens': '123'}},
                      {'total': {'inputTokens': 70}}, {'total': {'inputTokens': 3}},
                      {'total': {'inputTokens': 3, 'outputTokens': 0}}]:
            client.emit('thread/tokenUsage/updated', threadId=client.thread_id, turnId=client.turn_id, tokenUsage=usage)
        original(client, status)
    monkeypatch.setattr(FakeClient, 'finish', finish)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        updates = [x for x in chunks if x.get('event_type') == 'chat.usage_summary']
        assert len(updates) == 3
        assert updates[0]['usage'] == {'input_tokens': 70}
        assert updates[-1]['session_usage']['main']['input_tokens'] is None
        assert updates[-1]['session_usage']['main']['output_tokens'] is None
        assert updates[-1]['provider']['codex']['total']['outputTokens'] == 0
        # A decrease invalidates the baseline, rather than reporting a negative turn.
        assert 'usage' not in updates[-1]
        assert any(x.get('content') == 'reply' for x in chunks)
        assert not any(x.get('event_type') == 'chat.error' for x in chunks)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_later_missing_window_clears_previous_capacity_in_original_stream(host, monkeypatch):
    app, config, _, _, _ = host
    original = FakeClient.finish
    def finish(client, status='completed'):
        for value, window in [(100, 200000), (200, None)]:
            emit_native_usage(client, {'inputTokens': value, 'outputTokens': 0,
                'totalTokens': value, 'cachedInputTokens': 0, 'reasoningOutputTokens': 0}, window=window)
        original(client, status)
    monkeypatch.setattr(FakeClient, 'finish', finish)
    await app.create_instance(config)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        contexts = [x for x in chunks if x.get('event_type') == 'context.usage']
        assert [x['context_window']['limit_tokens'] for x in contexts] == [200000, None]
        assert contexts[-1]['context_window']['occupancy_rate'] is None
        assert any(x.get('content') == 'reply' for x in chunks)
    finally:
        await app.cleanup()
