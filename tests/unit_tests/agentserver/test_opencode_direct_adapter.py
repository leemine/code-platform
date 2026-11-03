"""Public Facade regression with a simulated official HTTP service.

These tests prove host/adapter behavior, not real Provider acceptance.
"""
import json
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.runtime.agent_adapter import interface
from jiuwenswarm.server.runtime.agent_adapter.providers.opencode import OpenCodeAdapter, tool_payload
from jiuwenswarm.server.runtime.session import session_history


def installed_cli(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return str(path)


@pytest.mark.asyncio
async def test_desktop_discovery_enters_original_facade_and_history(owned_permissions, monkeypatch, tmp_path):
    app, config, services = owned_permissions
    config['opencode'].pop('cli_path')
    config['opencode'].pop('url', None)
    config['opencode'].pop('directory', None)
    home = tmp_path / 'another user'
    executable = installed_cli(home / '.opencode/bin/opencode')
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    monkeypatch.setenv('PATH', '/nonexistent-desktop-path')
    from jiuwenswarm.common import utils
    monkeypatch.setattr(utils, 'get_default_project_session_workspace_dir', lambda: tmp_path)
    await app.create_instance(config)
    try:
        assert app._adapter._executable == executable
        chunks = [chunk.payload async for chunk in app.process_message_stream(request('one'))]
        assert any(item.get('event_type') == 'chat.final' for item in chunks)
        assert any(row.get('event_type') == 'chat.final' for row in session_history.read_session_history_records('one'))
        assert app.runtime_permission_status('one')['effective_profile'] == 'default'
    finally:
        await app.cleanup()
    assert services[0].client.is_closed


@pytest.mark.asyncio
async def test_explicit_url_does_not_discover_or_launch_cli(host, monkeypatch):
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode
    def forbidden(*args, **kwargs):
        pytest.fail('An explicit server binding must never auto-select a CLI')
    monkeypatch.setattr(opencode, 'resolve_cli', forbidden)
    app, config, calls, _, _ = host
    await app.create_instance(config)
    try:
        assert any(call[1] == '/global/health' for call in calls)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_bad_explicit_cli_does_not_fall_back_to_url_or_discovery(host):
    app, config, calls, _, root = host
    config['opencode']['cli_path'] = str(root / 'missing-cli')
    with pytest.raises(ValueError, match='Configured CLI is unavailable'):
        await app.create_instance(config)
    assert not calls


@pytest.mark.asyncio
async def test_missing_cli_reports_installation_not_url_syntax(host, monkeypatch, tmp_path):
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode
    monkeypatch.setenv('PATH', str(tmp_path))
    monkeypatch.setattr(opencode, 'cli_candidates', lambda: [])
    app, config, calls, _, _ = host
    config['opencode'].pop('url')
    with pytest.raises(ValueError, match='OpenCode CLI was not found'):
        await app.create_instance(config)
    assert not calls


def test_cli_precedence_and_no_project_path_lookup(tmp_path, monkeypatch):
    from jiuwenswarm.server.runtime.agent_adapter.providers.cli import resolve_cli
    path_cli = installed_cli(tmp_path / 'path/opencode')
    home_cli = installed_cli(tmp_path / 'home/opencode')
    local_cli = installed_cli(tmp_path / 'project/opencode')
    monkeypatch.chdir(Path(local_cli).parent)
    monkeypatch.setenv('PATH', '.::' + str(Path(path_cli).parent))
    assert resolve_cli('opencode', candidates=[home_cli]) == path_cli
    assert resolve_cli('opencode', explicit=home_cli) == home_cli
    monkeypatch.setenv('PATH', '.:')
    assert resolve_cli('opencode', candidates=[home_cli]) == home_cli
    assert resolve_cli('opencode') is None
    with pytest.raises(ValueError, match='Configured CLI'):
        resolve_cli('opencode', explicit='./opencode', candidates=[home_cli])


@pytest.fixture
def windows_cli_lookup(monkeypatch):
    """Model PATHEXT lookup over real temporary files; no Windows process is run."""
    from jiuwenswarm.server.runtime.agent_adapter.providers import cli, opencode
    original = cli.shutil.which

    def which(path):
        if not Path(path).suffix:
            for suffix in ('.exe', '.cmd'):
                found = original(str(path) + suffix)
                if found:
                    return found
        return original(path)

    monkeypatch.setattr(cli, 'os', SimpleNamespace(name='nt', path=os.path, get_exec_path=os.get_exec_path))
    monkeypatch.setattr(cli, 'shutil', SimpleNamespace(which=which))
    monkeypatch.setattr(opencode, 'sys', SimpleNamespace(platform='win32'))


@pytest.mark.asyncio
@pytest.mark.parametrize('location', ['path', 'appdata', 'prefix'])
async def test_windows_npm_discovery_enters_original_facade(
    owned_permissions, windows_cli_lookup, monkeypatch, tmp_path, location,
):
    from jiuwenswarm.common import utils
    app, config, services = owned_permissions
    config['opencode'].pop('cli_path')
    config['opencode'].pop('url', None)
    config['opencode'].pop('directory', None)
    home = tmp_path / 'another user'
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    monkeypatch.setattr(utils, 'get_default_project_session_workspace_dir', lambda: tmp_path)
    monkeypatch.setenv('APPDATA', str(home / 'AppData/Roaming'))
    monkeypatch.delenv('NPM_CONFIG_PREFIX', raising=False)
    monkeypatch.delenv('npm_config_prefix', raising=False)
    prefix = home / 'custom npm' if location != 'appdata' else home / 'AppData/Roaming/npm'
    installed_cli(prefix / 'opencode.cmd')
    executable = installed_cli(prefix / 'node_modules/opencode-ai/bin/opencode.exe')
    monkeypatch.setenv('PATH', str(prefix) if location == 'path' else '')
    if location == 'prefix':
        monkeypatch.setenv('NPM_CONFIG_PREFIX', str(prefix))
    await app.create_instance(config)
    try:
        assert app._adapter._executable == executable
        chunks = [chunk.payload async for chunk in app.process_message_stream(request('windows-npm'))]
        assert any(item.get('content') == 'PUBLIC_REPLY' for item in chunks)
        assert any(row.get('event_type') == 'chat.final' for row in session_history.read_session_history_records('windows-npm'))
        assert app.runtime_permission_status('windows-npm')['effective_profile'] == 'default'
    finally:
        await app.cleanup()
    assert services[0].client.is_closed


@pytest.mark.parametrize('suffix', ['.cmd', '.bat', '.ps1'])
def test_windows_implicit_launcher_does_not_hide_native_candidate(
    windows_cli_lookup, monkeypatch, tmp_path, suffix,
):
    from jiuwenswarm.server.runtime.agent_adapter.providers import cli
    launcher = installed_cli(tmp_path / ('opencode' + suffix))
    executable = installed_cli(tmp_path / 'native/opencode.exe')
    monkeypatch.setenv('PATH', str(tmp_path))
    original = cli.shutil.which
    monkeypatch.setattr(cli, 'shutil', SimpleNamespace(which=lambda p: launcher if p == str(tmp_path / 'opencode') else original(p)))
    assert cli.resolve_cli('opencode', candidates=[executable]) == executable
    with pytest.raises(ValueError, match='native executable'):
        cli.resolve_cli('opencode', explicit=launcher, candidates=[executable])


def test_windows_native_path_precedes_npm_fallback(windows_cli_lookup, monkeypatch, tmp_path):
    from jiuwenswarm.server.runtime.agent_adapter.providers import cli, opencode
    prefix = tmp_path / 'npm prefix'
    installed_cli(prefix / 'opencode.cmd')
    installed_cli(prefix / 'node_modules/opencode-ai/bin/opencode.exe')
    native = installed_cli(tmp_path / 'native/opencode.exe')
    monkeypatch.setenv('PATH', os.pathsep.join([str(prefix), str(Path(native).parent)]))
    assert cli.resolve_cli('opencode', candidates=opencode.cli_candidates()) == native


@pytest.mark.asyncio
async def test_windows_npm_missing_native_reports_installation(host, windows_cli_lookup, monkeypatch, tmp_path):
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode
    installed_cli(tmp_path / 'opencode.cmd')
    monkeypatch.setenv('PATH', str(tmp_path))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path / 'empty home'))
    monkeypatch.setenv('APPDATA', str(tmp_path / 'empty appdata'))
    monkeypatch.delenv('NPM_CONFIG_PREFIX', raising=False)
    monkeypatch.delenv('npm_config_prefix', raising=False)
    app, config, calls, _, _ = host
    config['opencode'].pop('url')
    with pytest.raises(ValueError, match='OpenCode CLI was not found'):
        await app.create_instance(config)
    assert not calls


def test_windows_npm_relative_prefix_is_not_discovered(windows_cli_lookup, monkeypatch, tmp_path):
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PATH', '.')
    monkeypatch.setenv('APPDATA', 'relative-appdata')
    monkeypatch.setenv('NPM_CONFIG_PREFIX', 'relative-prefix')
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path / 'empty home'))
    installed_cli(tmp_path / 'node_modules/opencode-ai/bin/opencode.exe')
    assert all(candidate.is_absolute() for candidate in opencode.cli_candidates())
    assert tmp_path / 'node_modules/opencode-ai/bin/opencode.exe' not in opencode.cli_candidates()


@pytest.mark.parametrize('platform,tail', [
    ('linux', '.opencode/bin/opencode'),
    ('darwin', '.opencode/bin/opencode'),
    ('win32', '.opencode/bin/opencode.exe'),
])
def test_platform_candidate_locations_use_current_user(monkeypatch, tmp_path, platform, tail):
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode
    monkeypatch.setattr(opencode.sys, 'platform', platform)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    candidates = opencode.cli_candidates()
    assert tmp_path / tail in candidates
    if platform == 'darwin':
        assert Path('/opt/homebrew/bin/opencode') in candidates


@pytest.mark.asyncio
async def test_multiline_sse_keeps_native_frames_through_facade(host, monkeypatch):
    async def multiline(self):
        for item in self.events:
            frame = ': keepalive\r\nevent: message\r\n'
            frame += ''.join('data: ' + line + '\r\n' for line in json.dumps(item, indent=2).splitlines())
            yield (frame + '\r\n').encode()
    monkeypatch.setattr(Events, '__aiter__', multiline)
    app, config, calls, _, _ = host
    await app.create_instance(config)
    try:
        chunks = [c.payload async for c in app.process_message_stream(request())]
        assert [x['content'] for x in chunks if x.get('event_type') == 'chat.final'] == ['PUBLIC_REPLY']
        assert sum(call[1] == '/event' for call in calls) == 1
    finally:
        await app.cleanup()


class Events(httpx.AsyncByteStream):
    def __init__(self, events, reply):
        self.events = events
        self.reply = reply

    async def __aiter__(self):
        for event in self.events:
            yield ('data: '+json.dumps(event)+'\n\n').encode()
            if event['type']=='permission.asked':
                await asyncio.wait_for(self.reply.wait(), 3)


def event(kind, **props):
    return {"type":kind, "properties":{"sessionID":"ses_test", **props}}


def completed_events():
    return [
        event("message.updated", info={"id":"msg_user", "sessionID":"ses_test", "role":"user"}),
        event("message.part.updated", part={"id":"p_user","sessionID":"ses_test","messageID":"msg_user","type":"text","text":"SECRET_USER_PROMPT"}),
        event("message.updated", info={"id":"msg_agent", "sessionID":"ses_test", "role":"assistant"}),
        event("message.part.updated", part={"id":"p_reply","sessionID":"ses_test","messageID":"msg_agent","type":"text","text":""}),
        event("message.part.delta", messageID="msg_agent", partID="p_reply", field="text", delta="PUBLIC_REPLY"),
        event("message.updated", info={"id":"msg_agent", "sessionID":"ses_test", "role":"assistant", "time":{"completed":1}, "finish":"stop"}),
        event("session.idle"),
    ]


@pytest.fixture
def host(tmp_path, monkeypatch):
    calls=[]; events=completed_events(); reply=asyncio.Event()
    original=httpx.AsyncClient
    native_permissions = []
    def handle(req):
        calls.append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        if req.url.path == '/global/health':return httpx.Response(200,json={"healthy":True})
        if req.url.path == '/session/ses_test':
            if req.method == 'PATCH': native_permissions.extend(json.loads(req.content)['permission'])
            return httpx.Response(200,json={"id":"ses_test","permission":list(native_permissions)})
        if req.url.path == '/session':return httpx.Response(200,json={"id":"ses_test"})
        if req.url.path == '/session/status':return httpx.Response(200,json={})
        if req.url.path == '/event':return httpx.Response(200,stream=Events(events,reply),headers={'content-type':'text/event-stream'})
        if req.url.path.endswith('/reply'):reply.set()
        return httpx.Response(200,json=True)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handle),**kw))
    monkeypatch.setattr(interface, 'resolve_sdk_choice', lambda:'opencode-direct')
    monkeypatch.setattr(interface, 'create_adapter', lambda sdk,mode:OpenCodeAdapter(mode=mode))
    monkeypatch.setattr(interface, 'get_config', lambda:{'preferred_language':'en'})
    monkeypatch.setattr(session_history,'get_agent_sessions_dir',lambda:tmp_path/'sessions')
    app=interface.JiuWenSwarm()
    config={'permissions':{'enabled':True,'mode':'manual'},'opencode':{'url':'http://127.0.0.1:12345','directory':str(tmp_path),'model':{'providerID':'test','modelID':'test'}}}
    return app,config,calls,events,tmp_path


def request(sid='test-session', **params):
    return AgentRequest(request_id='test-request',channel_id='web',session_id=sid,req_method=ReqMethod.CHAT_SEND,params={'mode':'agent','query':'test',**params},is_stream=True)


@pytest.mark.asyncio
async def test_real_facade_preserves_history_and_closes_borrowed_sessions(host):
    app,config,calls,_,root=host
    await app.create_instance(config)
    try:
        chunks=[c async for c in app.process_message_stream(request())]
        finals=[c.payload for c in chunks if (c.payload or {}).get('event_type')=='chat.final']
        assert [x['content'] for x in finals]==['PUBLIC_REPLY']
        records=session_history.read_session_history_records('test-session')
        assert any(r.get('content')=='PUBLIC_REPLY' and r.get('event_type')=='chat.final' for r in records)
        assert not any('SECRET_USER_PROMPT' in str(r.get('content')) for r in records)
        assert calls.index(('GET','/event',None)) < next(i for i,c in enumerate(calls) if c[1].endswith('/prompt_async'))
        assert await app.cleanup_session_runtime('test-session')
        assert not app.has_session_runtime('test-session')
    finally:
        await app.cleanup()
    assert any(c[:2]==('DELETE','/session/ses_test') for c in calls)
    assert not any(c[1]=='/instance/dispose' for c in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('idle', [False,True])
async def test_incomplete_native_stream_cannot_be_success(host,idle):
    app,config,calls,events,_=host
    events[:]=[event('session.idle')] if idle else []
    await app.create_instance(config)
    try:
        chunks=[c async for c in app.process_message_stream(request())]
        assert not any((c.payload or {}).get('event_type')=='chat.final' for c in chunks)
        assert any((c.payload or {}).get('event_type')=='chat.error' for c in chunks)
        assert any(c[1].endswith('/abort') for c in calls)
    finally:await app.cleanup()


@pytest.mark.parametrize('code,expected',[(0,True),(7,False),(None,None),(True,None)])
def test_tool_exit_is_native_evidence_only(code,expected):
    result=tool_payload({'id':'p','callID':'c','tool':'bash','state':{'status':'completed','output':'x','metadata':{'exit':code}}})
    assert result['success'] is expected
    assert result['command_success'] is expected
    assert result['task_acceptance']=='unknown'


@pytest.mark.asyncio
async def test_wrong_session_events_are_not_delivered(host):
    app,config,_,events,_=host
    events.insert(0,{'type':'message.part.delta','properties':{'sessionID':'ses_other','partID':'p_reply','messageID':'msg_agent','field':'text','delta':'OTHER_SESSION_SECRET'}})
    await app.create_instance(config)
    try:
        chunks=[c.payload async for c in app.process_message_stream(request())]
        assert 'OTHER_SESSION_SECRET' not in str(chunks)
    finally:await app.cleanup()


@pytest.mark.asyncio
async def test_unsupported_equipment_fails_before_prompt(host):
    app,config,calls,_,_=host
    await app.create_instance(config)
    try:
        with pytest.raises(ValueError, match='equipment'):
            _=[c async for c in app.process_message_stream(request(mcp=['not-supported']))]
        assert not any(c[1].endswith('/prompt_async') for c in calls)
    finally:await app.cleanup()


@pytest.mark.asyncio
async def test_foreign_control_fails_without_answering_provider(host):
    app,config,calls,_,_=host
    await app.create_instance(config)
    try:
        req=request(request_id='per_other',source='permission_interrupt',answers=[{'answer':'allow_once'}])
        with pytest.raises(ValueError,match='matching active'):
            _=[c async for c in app.deliver_control_input(req)]
        assert not any(c[1].endswith('/reply') for c in calls)
    finally:await app.cleanup()


@pytest.mark.asyncio
async def test_runtime_direct_transport_does_not_create_websocket_server(monkeypatch):
    from jiuwenswarm.server.gateway_push import transport
    monkeypatch.setattr(transport,'_websocket_push_sender',None)
    assert await transport.WebSocketGatewayPushTransport().send_push({'payload':{}}) is False
    sent=[]
    async def send(message):sent.append(message);return True
    transport.set_websocket_push_sender(send)
    try:
        assert await transport.WebSocketGatewayPushTransport().send_push({'x':1})
        assert sent==[{'x':1}]
    finally:transport.set_websocket_push_sender(None)


@pytest.mark.asyncio
async def test_native_cancel_keeps_history_cancelled(host):
    app,config,_,events,_=host
    events[:]=[event('session.error',error={'name':'MessageAbortedError'})]
    await app.create_instance(config)
    chunks=[c async for c in app.process_message_stream(request())]
    await app.cleanup()
    assert any(c.runtime_completion=='cancelled' for c in chunks)
    records=session_history.read_session_history_records('test-session')
    assert any(r.get('status')=='cancelled' for r in records if r.get('feedback_only'))
    assert not any(r.get('status')=='success' for r in records if r.get('feedback_only'))


@pytest.mark.asyncio
async def test_released_history_is_not_silently_restarted(host):
    app,config,calls,_,_=host
    await app.create_instance(config)
    try:
        _=[c async for c in app.process_message_stream(request())]
        await app.cleanup_session_runtime('test-session')
        before=len([c for c in calls if c[:2]==('POST','/session')])
        with pytest.raises(ValueError,match='cannot restore'):
            await app._adapter.prepare_session(session_id='test-session',channel_id='web',mode='agent')
        assert len([c for c in calls if c[:2]==('POST','/session')])==before
    finally:await app.cleanup()


@pytest.mark.asyncio
async def test_cleanup_failure_retains_adapter_for_retry(host,monkeypatch):
    app,config,_,_,_=host
    await app.create_instance(config)
    _=[c async for c in app.process_message_stream(request())]
    adapter=app._adapter;original=adapter._call
    async def fail_delete(method,path,**kw):
        if method=='DELETE':raise RuntimeError('temporary delete failure')
        return await original(method,path,**kw)
    monkeypatch.setattr(adapter,'_call',fail_delete)
    with pytest.raises(RuntimeError,match='temporary delete'):
        await app.cleanup()
    assert app._adapter is adapter and adapter.has_session_runtime('test-session')
    monkeypatch.setattr(adapter,'_call',original)
    await app.cleanup()
    assert app._adapter is None


@pytest.mark.asyncio
async def test_failed_abort_keeps_owner_and_cleanup_retries(host,monkeypatch):
    app,config,calls,events,_=host
    events.clear()
    await app.create_instance(config)
    adapter=app._adapter;original=adapter._call
    async def fail_abort(method,path,**kw):
        if path.endswith('/abort'):raise RuntimeError('temporary abort failure')
        return await original(method,path,**kw)
    monkeypatch.setattr(adapter,'_call',fail_abort)
    chunks=[c async for c in app.process_message_stream(request())]
    assert any((c.payload or {}).get('event_type')=='chat.error' for c in chunks)
    with pytest.raises(RuntimeError,match='temporary abort'):
        await app.cleanup()
    assert app._adapter is adapter
    monkeypatch.setattr(adapter,'_call',original)
    await app.cleanup()
    assert any(c[1].endswith('/abort') for c in calls)
    assert any(c[:2]==('DELETE','/session/ses_test') for c in calls)


@pytest.mark.asyncio
async def test_external_runtime_honors_installed_request_hook(monkeypatch):
    from gateway.extensions.registry import ExtensionRegistry
    from jiuwenswarm.runtime import AgentRuntime
    from jiuwenswarm.server.runtime.agent_adapter import agent_adapters
    from types import SimpleNamespace
    seen=[]
    async def deny(name,context):
        seen.append(context.request_id)
        raise PermissionError('host hook denied')
    monkeypatch.setattr(agent_adapters,'resolve_sdk_choice',lambda value=None:value or 'opencode-direct')
    monkeypatch.setattr(ExtensionRegistry,'get_instance',lambda:SimpleNamespace(trigger=deny))
    runtime=AgentRuntime()
    try:
        with pytest.raises(PermissionError,match='host hook denied'):
            await runtime._trigger_before_chat_request_hook(request())
        assert seen==['test-request']
    finally:await runtime.close()


@pytest.mark.asyncio
async def test_web_permission_answer_is_delivered_once_to_original_producer(host):
    app,config,calls,events,_=host
    events.insert(0,event('permission.asked',id='per_test',permission='bash',patterns=['example']))
    await app.create_instance(config)
    try:
        async for chunk in app.process_message_stream(request()):
            if (chunk.payload or {}).get('event_type')!='chat.ask_user_question':continue
            answer=request(request_id='per_test',source='permission_interrupt',answers=[{'selected_options':['allow_once']}])
            ack=[c async for c in app.deliver_control_input(answer)]
            assert any((c.payload or {}).get('event_type')=='runtime.accepted' for c in ack)
            with pytest.raises(ValueError,match='matching active'):
                _=[c async for c in app.deliver_control_input(answer)]
        assert [c for c in calls if c[1]=='/permission/per_test/reply']==[('POST','/permission/per_test/reply',{'reply':'once'})]
        assert len([c for c in calls if c[1]=='/event'])==1
        assert len([c for c in calls if c[1].endswith('/prompt_async')])==1
    finally:await app.cleanup()


@pytest.mark.asyncio
async def test_approval_timeout_is_an_error_and_late_answer_cannot_resume(host):
    app, config, calls, events, _ = host
    config['opencode']['turn_timeout'] = 0.05
    events[:] = [event('permission.asked', id='per_test', permission='read', patterns=['fixture'])]
    await app.create_instance(config)
    try:
        chunks = [c async for c in app.process_message_stream(request())]
        errors = [c.payload for c in chunks if (c.payload or {}).get('event_type') == 'chat.error']
        assert errors and 'timed out' in str(errors)
        assert errors[0]['code'] == 'provider_timeout'
        assert any((c.payload or {}).get('event_type') == 'chat.interrupt_result'
                   and c.payload['success'] is True for c in chunks)
        assert not any((c.payload or {}).get('event_type') == 'chat.final' for c in chunks)
        assert any(c[1].endswith('/abort') for c in calls)
        with pytest.raises(ValueError, match='matching active'):
            _ = [c async for c in app.deliver_control_input(request(request_id='per_test',
                source='permission_interrupt', answers=[{'selected_options':['allow_once']}]))]
        events[:] = completed_events()
        app._adapter._timeout = 5
        continued = [c async for c in app.process_message_stream(request())]
        assert any((c.payload or {}).get('event_type') == 'chat.final' for c in continued)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_parallel_native_approvals_do_not_overwrite_host_gate(host, monkeypatch):
    app, config, calls, events, _ = host
    events[:0] = [event('permission.asked', id=identity, permission='read', patterns=['fixture'])
                  for identity in ['per_one', 'per_two']]
    async def burst(self):
        for item in self.events:
            yield ('data: ' + json.dumps(item) + '\n\n').encode()
    monkeypatch.setattr(Events, '__aiter__', burst)
    await app.create_instance(config)
    received = asyncio.Queue()
    async def consume():
        async for chunk in app.process_message_stream(request()):
            await received.put(chunk.payload or {})
    task = asyncio.create_task(consume())
    try:
        for identity in ['per_one', 'per_two']:
            prompt = await asyncio.wait_for(received.get(), 2)
            assert prompt['request_id'] == identity
            await asyncio.sleep(0.03)
            assert received.empty(), 'A later native approval replaced the current host interaction'
            _ = [c async for c in app.deliver_control_input(request(request_id=identity,
                source='permission_interrupt', answers=[{'selected_options':['allow_once']}]))]
        await asyncio.wait_for(task, 2)
        assert len([c for c in calls if c[1].endswith('/reply')]) == 2
        assert len([c for c in calls if c[1] == '/event']) == 1
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await app.cleanup()


@pytest.mark.asyncio
async def test_external_manager_selection_survives_environment_change(host, monkeypatch):
    from jiuwenswarm.runtime import AgentRuntime
    from jiuwenswarm.server.runtime.agent_manager import AgentManager
    monkeypatch.setenv('JIUWENSWARM_AGENT_SDK', 'opencode-direct')
    manager = AgentManager()
    monkeypatch.setenv('JIUWENSWARM_AGENT_SDK', 'missing-late-provider')
    runtime = AgentRuntime(agent_manager=manager)
    assert not runtime._manage_runner and not runtime._initialize_extensions
    _, config, calls, _, _ = host
    try:
        from jiuwenswarm.common import config as config_module
        monkeypatch.setattr(config_module, 'get_config', lambda: config)
        app = await manager.get_agent(channel_id='web', mode='agent')
        assert app._sdk_name == manager.sdk_name == 'opencode-direct'
        chunks = [chunk async for chunk in app.process_message_stream(request('fixed-provider'))]
        assert any((chunk.payload or {}).get('content') == 'PUBLIC_REPLY' for chunk in chunks)
    finally:
        await runtime.close()
    assert any(call[:2] == ('DELETE', '/session/ses_test') for call in calls)


@pytest.mark.asyncio
async def test_shared_model_selection_uses_real_swarm_resolver_and_official_prompt(host, monkeypatch):
    from jiuwenswarm.common import model_catalog
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode_models import build_server_model_config
    app, config, calls, events, root = host
    shared = {'models': {'defaults': [
        {'model_id': 'alpha', 'is_default': True, 'model_client_config': {'client_provider': 'OpenAI', 'model_name': 'model-a', 'api_base': 'https://example.invalid/v1', 'api_key': 'private-a'}},
        {'model_id': 'beta', 'model_client_config': {'client_provider': 'OpenAI', 'model_name': 'model-b', 'api_base': 'https://example.invalid/v1', 'api_key': 'private-b'}},
    ]}}
    monkeypatch.setattr(model_catalog, 'get_config', lambda: shared)
    fragment, unsupported = build_server_model_config(shared)
    assert not unsupported and len(fragment['provider']) == 2
    config['opencode'].pop('model')
    await app.create_instance(config)
    original = app._adapter._call
    async def provider_read(method, path, **kw):
        if path == '/provider':
            return {'all': [{'id': key, 'models': value['models']} for key, value in fragment['provider'].items()]}
        return await original(method, path, **kw)
    monkeypatch.setattr(app._adapter, '_call', provider_read)
    try:
        for model_id, expected in [('alpha', 'model-a'), ('beta', 'model-b')]:
            chunks = [c async for c in app.process_message_stream(request(model_id, mode='agent.work.normal', model_selection={'type': 'model', 'id': model_id}))]
            assert any((c.payload or {}).get('content') == 'PUBLIC_REPLY' for c in chunks)
            prompt = [c[2] for c in calls if c[1].endswith('/prompt_async')][-1]
            assert prompt['model']['modelID'] == expected
            assert 'private-' not in json.dumps(prompt)
        # Rotated configuration must not silently continue with a stale service snapshot.
        shared['models']['defaults'][0]['model_client_config']['api_key'] = 'rotated-a'
        chunks = [c async for c in app.process_message_stream(request('stale', model_selection={'type': 'model', 'id': 'alpha'}))]
        assert any((c.payload or {}).get('event_type') == 'chat.error' for c in chunks)
        assert len([c for c in calls if c[1].endswith('/prompt_async')]) == 2
        assert not any(c[0] in {'PATCH', 'PUT'} for c in calls)
    finally:
        await app.cleanup()


@pytest.fixture
def equipment_assets(tmp_path, monkeypatch):
    from jiuwenswarm.server.runtime import extension_package_manager as packages
    from jiuwenswarm.server.runtime.session import session_metadata
    monkeypatch.setattr(packages, 'get_agent_workspace_dir', lambda: tmp_path / 'workspace')
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: tmp_path / 'sessions')
    def template(name, **extra):
        directory = tmp_path / 'workspace' / 'plugins' / 'agent_templates' / 'local' / name
        (directory / 'persona').mkdir(parents=True, exist_ok=True)
        (directory / 'persona/rules.md').write_text('Rule: ' + name)
        (directory / 'manifest.json').write_text(json.dumps({
            'package_type': 'agent_template', 'name': name, 'persona': {'dir': 'persona'}, **extra,
        }))
        packages.upsert_agent_template_marketplace_entry(name, installed=True)
        return directory
    return template


@pytest.mark.asyncio
async def test_template_rules_reach_native_system_and_clear_via_original_facade(host, equipment_assets):
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_equipment
    app, config, calls, _, _ = host
    equipment_assets('expert-a')
    await app.create_instance(config)
    try:
        for params, expected in [({'agent_template_name': 'expert-a'}, 'Rule: expert-a'), ({}, 'Rule: expert-a'),
                                 ({'agent_template_name': ''}, '')]:
            chunks = [c async for c in app.process_message_stream(request(**params))]
            assert any(c.payload.get('event_type') == 'chat.final' for c in chunks)
            body = next(c[2] for c in reversed(calls) if c[1].endswith('/prompt_async'))
            assert body['system'] == expected
            assert 'Rule:' not in body['parts'][0]['text']
        assert get_session_equipment('test-session')['agent_template_name'] == ''
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('extra,reason', [
    ({'runtime': {'provider_name': 'codex'}}, 'provider_conflict'),
    ({'runtime': {'provider_name': 'opencode', 'config': {'permission': 'allow'}}}, 'not portable'),
    ({'tools': [{'file': 'tool.py'}]}, 'unsupported equipment'),
])
async def test_template_rejection_prevents_execution_and_metadata_changes(host, equipment_assets, extra, reason):
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_equipment
    app, config, calls, _, _ = host
    equipment_assets('incompatible', **extra)
    await app.create_instance(config)
    try:
        with pytest.raises(ValueError, match=reason):
            _ = [c async for c in app.process_message_stream(request(agent_template_name='incompatible'))]
        assert not any(c[1].endswith('/prompt_async') for c in calls)
        assert not get_session_equipment('test-session').get('agent_template_name')
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_uninstalled_template_cannot_bypass_original_asset_gate(host):
    app, config, calls, _, _ = host
    await app.create_instance(config)
    try:
        with pytest.raises(ValueError, match='not installed'):
            _ = [c async for c in app.process_message_stream(request(agent_template_name='uninstalled'))]
        assert not any(c[1] == '/session' for c in calls)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_normal_code_does_not_construct_native_plan_state(host, monkeypatch):
    from jiuwenswarm.runtime.plan import PlanModeController
    app, config, _, _, _ = host
    await app.create_instance(config, mode='code', sub_mode='normal')
    controller = PlanModeController()
    async def forbidden(*args):
        raise AssertionError('Native Plan state must not be opened')
    monkeypatch.setattr(controller, 'open_state_session', forbidden)
    try:
        result = await controller.ensure_state(request(mode='agent.code.normal'), 'code', 'normal', app)
        assert result.events == []
        with pytest.raises(ValueError, match='Native plan'):
            await controller.ensure_state(request(mode='agent.code.plan'), 'code', 'plan', app)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_borrowed_server_equipment_never_writes_server_config(host, equipment_assets):
    app, config, calls, _, _ = host
    directory = equipment_assets('skills-template', skills=[{'dir': 'skills/demo'}])
    skill = directory / 'skills/demo'; skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: demo\ndescription: Demo resource\n---\nRead resource.txt')
    (skill / 'resource.txt').write_text('preserved resource')
    await app.create_instance(config)
    try:
        with pytest.raises(ValueError, match='session-owned CLI'):
            _ = [c async for c in app.process_message_stream(request(agent_template_name='skills-template'))]
        assert not any(c[1] in {'/config', '/mcp', '/instance/dispose', '/session'} for c in calls)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_template_symlink_rejected_before_native_prompt(host, equipment_assets, tmp_path):
    app, config, calls, _, _ = host
    directory = equipment_assets('linked')
    outside = tmp_path / 'outside.md'; outside.write_text('outside')
    (directory / 'persona/rules.md').unlink()
    (directory / 'persona/rules.md').symlink_to(outside)
    await app.create_instance(config)
    try:
        with pytest.raises(ValueError, match='outside'):
            _ = [c async for c in app.process_message_stream(request(agent_template_name='linked'))]
        assert not any(c[1].endswith('/prompt_async') for c in calls)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_skill_chip_is_not_a_persistent_allowlist_and_disabled_skill_fails(host, monkeypatch, tmp_path):
    from jiuwenswarm.server.runtime.skill import skill_manager
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode_service
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_equipment
    directory = tmp_path / 'global/skills/demo'; directory.mkdir(parents=True)
    (directory / 'SKILL.md').write_text('---\nname: demo\ndescription: Demo: legacy header\n---\nRead resource.txt')
    (directory / 'resource.txt').write_text('distinct fixture resource')
    manager = skill_manager.SkillManager(workspace_dir=str(tmp_path / 'global'))
    monkeypatch.setattr(skill_manager, '_get_agent_root_dir', lambda: tmp_path / 'global')
    monkeypatch.setattr(skill_manager, 'get_agent_skills_dir', lambda: tmp_path / 'global/skills')
    monkeypatch.setattr(skill_manager, '_get_marketplace_dir', lambda: tmp_path / 'global/skills/_marketplace')
    monkeypatch.setattr(skill_manager, '_get_state_file', lambda: tmp_path / 'global/skills/skills_state.json')
    snapshots = []
    original = httpx.AsyncClient
    class Service:
        def __init__(self, executable, directory):
            self.client = original(base_url='http://127.0.0.1:12345')
        async def configure(self, equipment, *, permission_profile="default"):
            snapshots.append({name: (path / 'resource.txt').read_text() for name,path in equipment.skills.items()})
            if equipment.skills:
                import yaml
                document = equipment.skill_documents['demo']
                assert yaml.safe_load(document.split('---')[1])['name'] == 'demo'
                assert document.endswith('Read resource.txt')
        async def close(self):
            await self.client.aclose()
    monkeypatch.setattr(opencode_service, 'SessionService', Service)
    # Keep the original simulated transport but return native resource discovery.
    app, config, calls, _, _ = host
    config['opencode']['cli_path'] = __import__('sys').executable
    await app.create_instance(config)
    with pytest.raises(ValueError, match='already configured'):
        await app.create_instance(config)
    original_call = app._adapter._call
    async def call(method, path, **kw):
        if path == '/skill': return [{'name': 'demo'}]
        return await original_call(method, path, **kw)
    monkeypatch.setattr(app._adapter, '_call', call)
    try:
        for params in [{'skills': ['demo']}, {}]:
            _ = [c async for c in app.process_message_stream(request(**params))]
            assert snapshots[-1] == {'demo': 'distinct fixture resource'}
        body = next(c[2] for c in reversed(calls) if c[1].endswith('/prompt_async'))
        assert 'skills_to_use' not in body['parts'][0]['text']
        assert 'skills' not in get_session_equipment('test-session')
        await manager.handle_skills_toggle({'name': 'demo', 'enabled': False})
        count = len(calls)
        with pytest.raises(ValueError, match='unavailable or disabled'):
            _ = [c async for c in app.process_message_stream(request(skills=['demo']))]
        assert not any(c[1].endswith('/prompt_async') for c in calls[count:])
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_mcp_uses_existing_credentials_and_failed_mount_does_not_replace_saved_equipment(host, monkeypatch):
    from jiuwenswarm.common import config as config_module
    from jiuwenswarm.server.runtime import extension_package_manager as packages
    from jiuwenswarm.server.runtime.mcp import credential
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode_service
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_equipment
    app, config, calls, _, _ = host
    monkeypatch.setattr(packages, 'get_mcp_record', lambda name: {'state': 'connected'})
    monkeypatch.setattr(config_module, 'get_mcp_server_config', lambda name: {
        'name': name, 'transport': 'streamable-http', 'url': 'https://fixture.invalid/mcp',
        'headers': {'Authorization': 'Bearer ${TOKEN}'},
    })
    monkeypatch.setattr(credential.CredentialStore, 'get_all', lambda self, name: {'TOKEN': 'fixture-secret'})
    configured = []; status = {'probe': {'status': 'connected'}}
    original = httpx.AsyncClient
    class Service:
        def __init__(self, executable, directory):
            self.client = original(base_url='http://127.0.0.1:12345')
        async def configure(self, equipment, *, permission_profile="default"): configured.append(equipment.mcps)
        async def close(self): await self.client.aclose()
    monkeypatch.setattr(opencode_service, 'SessionService', Service)
    config['opencode']['cli_path'] = __import__('sys').executable
    await app.create_instance(config)
    original_call = app._adapter._call
    async def call(method, path, **kw):
        if path == '/mcp': return status
        return await original_call(method, path, **kw)
    monkeypatch.setattr(app._adapter, '_call', call)
    try:
        chunks = [c async for c in app.process_message_stream(request(mcp=['probe']))]
        assert configured[-1]['probe']['headers'] == {'Authorization': 'Bearer fixture-secret'}
        assert 'fixture-secret' not in str([c.payload for c in chunks])
        assert get_session_equipment('test-session')['mcp'] == ['probe']
        _ = [c async for c in app.process_message_stream(request())]
        assert configured[-1].keys() == {'probe'}
        status.clear(); count = len(calls)
        with pytest.raises(ValueError, match='connection failed'):
            _ = [c async for c in app.process_message_stream(request(mcp=['bad']))]
        assert get_session_equipment('test-session')['mcp'] == ['probe']
        assert not any(c[1].endswith('/prompt_async') for c in calls[count:])
        _ = [c async for c in app.process_message_stream(request(mcp=[]))]
        assert configured[-1] == {} and get_session_equipment('test-session')['mcp'] == []
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome,state', [
    ('error', 'failed'),
    ('cancelled', 'cancelled'),
    ('completed', 'succeeded'),
])
async def test_explicit_stream_terminal_releases_unanswered_control(outcome, state):
    from jiuwenswarm.runtime.events import RuntimeEvent
    from jiuwenswarm.runtime.session import RuntimeSessionCoordinator, SessionPersistencePolicy, SessionWorkKind
    from jiuwenswarm.runtime.session.model import SessionExecutionState
    coordinator = RuntimeSessionCoordinator()
    await coordinator.register_session('session-a', 'process', SessionPersistencePolicy.PERSISTENT)
    async def operation():
        yield RuntimeEvent(request_id='turn', channel_id='web', session_id='session-a',
                           payload={'event_type':'chat.ask_user_question', 'request_id':'approval'})
        yield RuntimeEvent(request_id='turn', channel_id='web', session_id='session-a',
                           payload={'event_type':'chat.error' if outcome == 'error' else 'chat.final'},
                           runtime_completion=outcome, is_complete=True)
    try:
        events = [x async for x in coordinator.run_stream('session-a', 'turn',
            SessionWorkKind.CHAT_STREAM, operation,
            suspension_key=lambda x: 'approval' if x.payload['event_type']=='chat.ask_user_question' else None)]
        assert len(events) == 2
        snapshot = coordinator.snapshot_session('session-a')
        assert snapshot.executions[0].state is SessionExecutionState(state)
        assert not coordinator.has_control_target('session-a', 'approval')
        assert await coordinator.run_unary('session-a', 'next', SessionWorkKind.CHAT_UNARY,
                                          lambda: asyncio.sleep(0, result='continued')) == 'continued'
    finally:
        await coordinator.close()



@pytest.mark.asyncio
async def test_owned_sessions_bind_ui_projects_across_equipment_http_and_cleanup(host, monkeypatch):
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode_service, opencode_equipment
    app, config, calls, _, root = host
    projects = [root / 'project-a', root / 'project-b']
    for project in projects:
        project.mkdir()
    transports, equipment_dirs, services = [], [], []
    class Service:
        def __init__(self, executable, directory):
            self.directory = directory
            self.closed = False
            async def observe(req):
                transports.append((directory, req.method, req.url.path, req.url.params.get('directory')))
            self.client = httpx.AsyncClient(base_url='http://127.0.0.1:12345', event_hooks={'request': [observe]})
            services.append(self)
        async def configure(self, equipment, *, permission_profile="default"):
            pass
        async def close(self):
            self.closed = True
            await self.client.aclose()
    async def resolve(params, *, directory, include_global_skills):
        equipment_dirs.append(directory)
        return opencode_equipment.Equipment()
    monkeypatch.setattr(opencode_service, 'SessionService', Service)
    monkeypatch.setattr(opencode_equipment, 'resolve_equipment', resolve)
    config['opencode']['cli_path'] = __import__('sys').executable
    await app.create_instance(config, mode='code', sub_mode='normal')
    try:
        # Same Facade, two projects, then an omitted directory resumes A's binding.
        for sid, project in [('a', projects[0]), ('b', projects[1]), ('a', None)]:
            params = {'mode': 'agent.code.normal'}
            if project:
                params['project_dir'] = str(project)
            chunks = [c async for c in app.process_message_stream(request(sid, **params))]
            assert any(c.payload.get('event_type') == 'chat.final' for c in chunks)
        assert equipment_dirs == [str(projects[0]), str(projects[1]), str(projects[0])]
        assert [s.directory for s in services] == list(map(str, projects))
        before = len(transports)
        with pytest.raises(ValueError, match='cannot change after binding'):
            _ = [c async for c in app.process_message_stream(request('a', mode='agent.code.normal', project_dir=str(projects[1])))]
        assert len(transports) == before
        assert app._adapter._sessions['a'].directory == str(projects[0])
    finally:
        await app.cleanup()
    assert all(s.closed for s in services)
    assert transports and all(owner == sent for owner, _, _, sent in transports)
    assert sum(method == 'DELETE' and path == '/session/ses_test' for _, method, path, _ in transports) == 2
    assert not any(path in {'/config', '/instance/dispose'} for _, _, path, _ in transports)


@pytest.mark.asyncio
async def test_borrowed_session_rejects_other_project_before_http(host):
    app, config, calls, _, root = host
    other = root / 'other'; other.mkdir()
    await app.create_instance(config)
    count = len(calls)
    try:
        with pytest.raises(ValueError, match='configured binding'):
            await app.prepare_session(session_id='other', channel_id='web', mode='agent.code.normal', project_dir=str(other))
        assert len(calls) == count
        assert not app.has_session_runtime('other')
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['relative', 'missing', 'file'])
async def test_owned_session_invalid_project_rejected_before_service(host, kind):
    app, config, calls, _, root = host
    file = root / 'not-directory'; file.write_text('fixture')
    project = {'relative': '.', 'missing': str(root / 'missing'), 'file': str(file)}[kind]
    config['opencode']['cli_path'] = __import__('sys').executable
    await app.create_instance(config)
    try:
        with pytest.raises(ValueError, match='existing absolute workspace'):
            await app.prepare_session(session_id='invalid', channel_id='web', mode='agent.code.normal', project_dir=project)
        assert not calls
        assert not app.has_session_runtime('invalid')
    finally:
        await app.cleanup()


@pytest.fixture
def owned_permissions(host, monkeypatch):
    """Simulated independent native services, including append/readback semantics."""
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode_service
    services = []
    class Service:
        def __init__(self, executable, directory):
            self.rules = []
            self.fail_readback = False
            self.events = completed_events()
            self.reply = asyncio.Event()
            self.calls = []
            self.profiles = []
            def handle(req):
                body = json.loads(req.content) if req.content else None
                self.calls.append((req.method, req.url.path, body))
                if req.url.path == '/session': return httpx.Response(200, json={'id':'ses_test'})
                if req.url.path == '/session/ses_test':
                    if req.method == 'PATCH': self.rules.extend(body['permission'])
                    return httpx.Response(200, json={'id':'ses_test','permission':[] if self.fail_readback else list(self.rules)})
                if req.url.path == '/event': return httpx.Response(200, stream=Events(self.events,self.reply))
                if req.url.path.endswith('/reply'): self.reply.set()
                return httpx.Response(200,json=True)
            self.client = httpx._client.AsyncClient(base_url='http://localhost',transport=httpx.MockTransport(handle))
            services.append(self)
        async def configure(self, equipment, *, permission_profile='default'):
            self.profiles.append(permission_profile)
        async def close(self): await self.client.aclose()
    monkeypatch.setattr(opencode_service,'SessionService',Service)
    app, config, _, _, _ = host
    config['opencode']['cli_path'] = __import__('sys').executable
    config['permissions'] = {'enabled':True,'mode':'manual'}
    return app,config,services


@pytest.mark.asyncio
async def test_permissions_reload_facade_two_sessions_and_equipment(owned_permissions):
    app,config,services=owned_permissions
    await app.create_instance(config)
    try:
        for sid in ['one','two']:
            _=[c async for c in app.process_message_stream(request(sid))]
            assert app.runtime_permission_status(sid)['effective_profile']=='default'
        await app.reload_agent_config({'permissions':{'enabled':False}},reload_scopes={'permissions'})
        for sid,service in zip(['one','two'],services):
            assert app.runtime_permission_status(sid)['state']=='applied'
            assert app.runtime_permission_status(sid)['effective_profile']=='full_access'
            # Original equipment reconciliation must retain the effective policy.
            _=[c async for c in app.process_message_stream(request(sid))]
            assert service.profiles[-1]=='full_access'
            assert service.rules[-4:]==[
                {'permission':'*','pattern':'*','action':'allow'},
                {'permission':'task','pattern':'*','action':'deny'},
                {'permission':'question','pattern':'*','action':'allow'},
                {'permission':'skill','pattern':'*','action':'deny'},
            ]
        await app.reload_agent_config({'permissions':{'enabled':True}},reload_scopes={'permissions'})
        assert all(app.runtime_permission_status(s)['effective_profile']=='default' for s in ['one','two'])
        assert all(service.rules[-4]['action']=='ask' for service in services)
    finally: await app.cleanup()


@pytest.mark.asyncio
async def test_permission_change_during_approval_keeps_original_control(owned_permissions):
    app,config,services=owned_permissions
    await app.create_instance(config)
    await app.prepare_session(session_id='one',channel_id='web',mode='agent')
    services[0].events.insert(0,event('permission.asked',id='per_pending',permission='read',patterns=['fixture']))
    try:
        async for chunk in app.process_message_stream(request('one')):
            if chunk.payload.get('event_type')=='chat.ask_user_question':
                await app.reload_agent_config({'permissions':{'enabled':False}},reload_scopes={'permissions'})
                status=app.runtime_permission_status('one')
                assert status['state']=='pending' and status['effective_profile']=='default'
                assert not any(c[1]=='/permission/per_pending/reply' for c in services[0].calls)
                answer=request('one',request_id='per_pending',source='permission_interrupt',answers=[{'selected_options':['allow_once']}])
                _=[c async for c in app.deliver_control_input(answer)]
        assert app.runtime_permission_status('one')['effective_profile']=='full_access'
        assert [c[2] for c in services[0].calls if c[1].endswith('/reply')]==[{'reply':'once'}]
    finally: await app.cleanup()


@pytest.mark.asyncio
async def test_failed_permission_readback_fences_next_production_prompt(owned_permissions):
    app,config,services=owned_permissions
    await app.create_instance(config)
    await app.prepare_session(session_id='one',channel_id='web',mode='agent')
    services[0].fail_readback=True
    try:
        await app.reload_agent_config({'permissions':{'enabled':False}},reload_scopes={'permissions'})
        status=app.runtime_permission_status('one')
        assert status['state']=='failed' and status['effective_profile'] is None
        with pytest.raises(ValueError,match='confirm'):
            _=[c async for c in app.process_message_stream(request('one'))]
        assert not any(c[1].endswith('/prompt_async') for c in services[0].calls)
        services[0].fail_readback=False
        await app.reload_agent_config({'permissions':{'enabled':True}},reload_scopes={'permissions'})
        _=[c async for c in app.process_message_stream(request('one'))]
        assert app.runtime_permission_status('one')['effective_profile']=='default'
    finally: await app.cleanup()


@pytest.mark.asyncio
async def test_automatic_never_becomes_full_access_or_manual_silently(owned_permissions):
    app,config,services=owned_permissions
    await app.create_instance(config)
    await app.prepare_session(session_id='one',channel_id='web',mode='agent')
    try:
        await app.reload_agent_config({'permissions':{'enabled':True,'mode':'auto'}},reload_scopes={'permissions'})
        assert app.runtime_permission_status('one')['state']=='unsupported'
        with pytest.raises(ValueError,match='Unsupported|Automatic'):
            _=[c async for c in app.process_message_stream(request('one'))]
        assert not any(c[1].endswith('/prompt_async') for c in services[0].calls)
    finally: await app.cleanup()


def test_full_access_keeps_skill_install_gate_and_user_questions(tmp_path):
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode_service import permission_config
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode_equipment import Equipment
    config=permission_config(Equipment(skills={'installed':tmp_path}),'full_access')
    assert config['skill']=={'*':'deny','installed':'allow'}
    assert config['question']=='allow' and config['task']=='deny'


@pytest.mark.asyncio
async def test_full_access_preserves_user_question_channel(owned_permissions):
    app,config,services=owned_permissions
    config['permissions']={'enabled':False}
    await app.create_instance(config)
    await app.prepare_session(session_id='one',channel_id='web',mode='agent')
    services[0].events.insert(0,event('question.asked',id='q_user',questions=[{'question':'Choose a fixture','options':[{'label':'A'}]}]))
    try:
        async for chunk in app.process_message_stream(request('one')):
            if chunk.payload.get('event_type')=='chat.ask_user_question':
                assert chunk.payload['source']=='ask_user_interrupt'
                answer=request('one',request_id='q_user',source='ask_user_interrupt',answers=[{'selected_options':['A']}])
                _=[c async for c in app.deliver_control_input(answer)]
        assert ('POST','/question/q_user/reply',{'answers':[['A']]}) in services[0].calls
    finally: await app.cleanup()


@pytest.mark.asyncio
async def test_partial_host_create_config_inherits_saved_permission_profile(owned_permissions, monkeypatch):
    from jiuwenswarm.common import config as common_config
    app,config,services=owned_permissions
    config.pop('permissions')
    monkeypatch.setattr(common_config,'get_config',lambda:{'permissions':{'enabled':False}})
    await app.create_instance(config)
    try:
        _=[c async for c in app.process_message_stream(request('one'))]
        assert app.runtime_permission_status('one')['effective_profile']=='full_access'
        assert services[0].rules[0]['action']=='allow'
    finally: await app.cleanup()


@pytest.mark.asyncio
async def test_global_permission_change_during_session_creation_is_not_lost(owned_permissions, monkeypatch):
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode_service
    app,config,services=owned_permissions
    entered,release=asyncio.Event(),asyncio.Event()
    original=opencode_service.SessionService.configure
    async def delayed(self,equipment,*,permission_profile='default'):
        if not self.profiles:
            entered.set()
            await release.wait()
        await original(self,equipment,permission_profile=permission_profile)
    monkeypatch.setattr(opencode_service.SessionService,'configure',delayed)
    await app.create_instance(config)
    preparing=asyncio.create_task(app.prepare_session(session_id='one',channel_id='web',mode='agent'))
    try:
        await asyncio.wait_for(entered.wait(),2)
        await app.reload_agent_config({'permissions':{'enabled':False}},reload_scopes={'permissions'})
        release.set()
        await preparing
        assert app.runtime_permission_status('one')['effective_profile']=='full_access'
    finally:
        release.set()
        await preparing
        await app.cleanup()


@pytest.mark.asyncio
async def test_cleanup_waits_for_owned_permission_update(owned_permissions, monkeypatch):
    app,config,services=owned_permissions
    await app.create_instance(config)
    await app.prepare_session(session_id='one',channel_id='web',mode='agent')
    entered,release=asyncio.Event(),asyncio.Event()
    original=services[0].configure
    async def delayed(equipment,*,permission_profile='default'):
        entered.set()
        await release.wait()
        await original(equipment,permission_profile=permission_profile)
    monkeypatch.setattr(services[0],'configure',delayed)
    reload=asyncio.create_task(app.reload_agent_config({'permissions':{'enabled':False}},reload_scopes={'permissions'}))
    await asyncio.wait_for(entered.wait(),2)
    cleanup=asyncio.create_task(app.cleanup_session_runtime('one'))
    release.set()
    await reload
    assert await cleanup
    assert services[0].client.is_closed and not app.has_session_runtime('one')
    await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["session.error", "message.updated"])
@pytest.mark.parametrize("native_message,expected_code", [
    ("unknown certificate verification error", "provider_tls_connection_failed"),
    (" Error: UNKNOWN CERTIFICATE VERIFICATION ERROR ", "provider_tls_connection_failed"),
    ("Error: unable to verify the first certificate", "provider_tls_verification_failed"),
    ("self signed certificate", "provider_tls_verification_failed"),
    ("unknown certificate verification error https://user:secret@example.invalid/?key=SECRET", None),
    ("Authorization: Bearer SECRET", None),
])
async def test_native_error_category_reaches_history_without_secrets(host, kind, native_message, expected_code):
    app, config, calls, events, _ = host
    error = {"name": "UnknownError", "data": {"message": native_message,
             "headers": {"authorization": "Bearer SECRET"}}, "stack": "SECRET_STACK"}
    props = {"error": error} if kind == "session.error" else {
        "info": {"id": "msg_error", "sessionID": "ses_test", "role": "assistant", "error": error}}
    events[:] = [event(kind, **props)]
    await app.create_instance(config)
    try:
        chunks = [c async for c in app.process_message_stream(request())]
        failures = [c for c in chunks if (c.payload or {}).get("event_type") == "chat.error"]
        assert len(failures) == 1
        payload = failures[0].payload
        assert payload["provider_error_type"] == "UnknownError"
        assert payload.get("code") == expected_code
        if expected_code == "provider_tls_connection_failed":
            assert "handshake or certificate verification" in payload["error"]
            assert "could not verify" not in payload["error"]
        elif expected_code == "provider_tls_verification_failed":
            assert "could not verify" in payload["error"]
        assert failures[0].runtime_completion == "error"
        assert not any((c.payload or {}).get("event_type") == "chat.final" for c in chunks)
        records = session_history.read_session_history_records("test-session")
        saved = [r for r in records if r.get("event_type") == "chat.error"]
        assert len(saved) == 1 and saved[0]["content"] == payload["error"]
        assert "SECRET" not in json.dumps(records) + json.dumps(payload)
        assert len([c for c in calls if c[1].endswith("/prompt_async")]) == 1
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['timeout', 'http', 'deadline', 'cancel'])
async def test_session_initialization_failure_is_bounded_and_not_retried(owned_permissions, monkeypatch, caplog, failure):
    app, config, services = owned_permissions
    config['opencode']['session_init_timeout'] = 0.03
    await app.create_instance(config)
    started = asyncio.Event()
    calls = []
    original_configure = __import__('jiuwenswarm.server.runtime.agent_adapter.providers.opencode_service', fromlist=['SessionService']).SessionService.configure

    async def configure(service, *args, **kwargs):
        await original_configure(service, *args, **kwargs)
        await service.client.aclose()
        async def handle(req):
            calls.append(req.url.path)
            started.set()
            if failure == 'timeout':
                raise httpx.ReadTimeout('', request=req)
            if failure == 'http':
                return httpx.Response(500, text='SECRET_RESPONSE')
            await asyncio.Event().wait()
        service.client = httpx._client.AsyncClient(base_url='http://localhost', transport=httpx.MockTransport(handle))
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode_service
    monkeypatch.setattr(opencode_service.SessionService, 'configure', configure)
    pending = asyncio.create_task(app.prepare_session(session_id='failed', channel_id='web', mode='agent'))
    try:
        if failure == 'cancel':
            await started.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            expected = {'timeout':'ReadTimeout', 'http':'HTTP 500', 'deadline':'TimeoutError'}[failure]
            with pytest.raises(RuntimeError, match='session initialization failed') as caught:
                await pending
            assert expected in str(caught.value)
            assert 'SECRET' not in str(caught.value) + caplog.text
        assert calls == ['/session']
        assert not app.has_session_runtime('failed')
        assert services[0].client.is_closed
    finally:
        await app.cleanup()


@pytest.mark.asyncio
async def test_slow_session_initialization_keeps_original_facade_history(host):
    app, config, calls, _, _ = host
    config['opencode']['session_init_timeout'] = 0.5
    await app.create_instance(config)
    client = app._adapter._client
    original_request = client.request
    observed = []
    async def delayed(method, path, **kwargs):
        if method == 'POST' and path == '/session':
            observed.append(kwargs['timeout'])
            await asyncio.sleep(0.04)
        return await original_request(method, path, **kwargs)
    client.request = delayed
    try:
        chunks = [c.payload async for c in app.process_message_stream(request('slow'))]
        assert any(c.get('event_type') == 'chat.final' for c in chunks)
        assert any(r.get('event_type') == 'chat.final' for r in session_history.read_session_history_records('slow'))
        assert observed == [0.5]
        assert sum(c[:2] == ('POST', '/session') for c in calls) == 1
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [0, -1, float('inf'), float('nan'), 601])
async def test_invalid_session_init_budget_is_rejected(host, value):
    app, config, calls, _, _ = host
    config['opencode']['session_init_timeout'] = value
    with pytest.raises(ValueError, match='session_init_timeout'):
        await app.create_instance(config)
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['early_hang', 'deadline', 'exit', 'cancel'])
async def test_owned_service_health_uses_short_probes_and_cleans_up(tmp_path, monkeypatch, scenario):
    import time
    from jiuwenswarm.common import utils
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode_service, opencode_transport
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode_equipment import Equipment
    monkeypatch.setattr(utils, 'get_agent_sessions_dir', lambda: tmp_path)
    monkeypatch.setattr(opencode_service, 'build_server_model_config', lambda: ({}, None))
    monkeypatch.setattr(opencode_service, 'STARTUP_TIMEOUT', 0.12 if scenario == 'deadline' else 4)
    monkeypatch.setattr(opencode_service.os, 'killpg', lambda *args: None)
    # Real HTTP preserves actual socket read-timeout behavior; no sleeps model startup readiness.
    original_client = httpx._client.AsyncClient
    monkeypatch.setattr(opencode_transport, 'create_client', lambda url, **kw: original_client(base_url=url, timeout=15, trust_env=False))
    ready = asyncio.Event()
    release = asyncio.Event()
    handlers = set()
    requests = []
    async def handle(reader, writer):
        handlers.add(asyncio.current_task())
        try:
            await reader.readuntil(b'\r\n\r\n')
            requests.append(time.monotonic())
            ready.set()
            if len(requests) == 1 or scenario == 'deadline':
                await release.wait()
            body = b'{"healthy":true}'
            writer.write(b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(asyncio.current_task())
    class Process:
        pid = 999999999
        returncode = 9 if scenario == 'exit' else None
        stopped = False
        def terminate(self): self.returncode = -15; self.stopped = True
        def kill(self): self.returncode = -9; self.stopped = True
        async def wait(self): return self.returncode
    proc = Process()
    server = None
    async def spawn(*args, **kwargs):
        nonlocal server
        server = await asyncio.start_server(handle, '127.0.0.1', int(args[-1]))
        return proc
    monkeypatch.setattr(opencode_service.asyncio, 'create_subprocess_exec', spawn)
    service = opencode_service.SessionService('fake-cli', str(tmp_path))
    pending = asyncio.create_task(service.configure(Equipment()))
    started = time.monotonic()
    try:
        if scenario == 'early_hang':
            await asyncio.wait_for(pending, 3)
            assert len(requests) == 2 and time.monotonic() - started < 3
            assert service.revision is not None
        elif scenario == 'cancel':
            await ready.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError): await pending
            assert proc.stopped and service.client is None
        else:
            with pytest.raises(RuntimeError, match='startup') as caught: await pending
            assert ('TimeoutError' if scenario == 'deadline' else 'exit 9') in str(caught.value)
            assert service.client is None and service.process is None
    finally:
        release.set()
        await service.close()
        if server: server.close(); await server.wait_closed()
        if handlers: await asyncio.gather(*list(handlers), return_exceptions=True)
    assert not service.root.exists()


@pytest.mark.asyncio
async def test_initialization_timeout_reaches_runtime_error_without_secret(host, caplog, monkeypatch):
    app, config, _, _, _ = host
    await app.create_instance(config)
    client = app._adapter._client
    original = client.request
    async def fail_create(method, path, **kwargs):
        if method == 'POST' and path == '/session':
            raise httpx.ReadTimeout('SECRET_URL_AND_CREDENTIAL')
        return await original(method, path, **kwargs)
    client.request = fail_create
    from unittest.mock import AsyncMock
    from jiuwenswarm.runtime import AgentRuntime
    from jiuwenswarm.server.runtime.agent_manager import AgentManager
    monkeypatch.setenv('JIUWENSWARM_AGENT_SDK', 'opencode-direct')
    manager = AgentManager()
    monkeypatch.setattr(manager, 'get_agent_for_request', AsyncMock(return_value=app))
    runtime = AgentRuntime(agent_manager=manager, initializer=AsyncMock())
    try:
        chunks = [(c.payload or {}) async for c in runtime.stream(request('failure-history'))]
        failures = [c for c in chunks if c.get('event_type') == 'runtime.error']
        assert len(failures) == 1
        assert 'session initialization' in failures[0]['error'] and 'ReadTimeout' in failures[0]['error']
        assert 'SECRET_URL_AND_CREDENTIAL' not in str(chunks) + caplog.text
        assert not any(c.get('event_type') == 'chat.final' for c in chunks)
        assert not app.has_session_runtime('failure-history')
    finally:
        await runtime.close()
        await app.cleanup()


@pytest.mark.asyncio
async def test_no_implicit_turn_limit_and_native_timeout_does_not_claim_deadline(host, monkeypatch):
    app, config, _, _, _ = host
    await app.create_instance(config)
    assert app._adapter._timeout is None
    original = app._adapter._call
    async def failed_prompt(method, path, **kw):
        if path.endswith('/prompt_async'):
            raise TimeoutError('private-native-error')
        return await original(method, path, **kw)
    monkeypatch.setattr(app._adapter, '_call', failed_prompt)
    try:
        chunks = [x.payload async for x in app.process_message_stream(request())]
        assert not any(x.get('code') == 'provider_timeout' for x in chunks)
        assert any(x.get('event_type') == 'chat.error' for x in chunks)
        assert 'private-native-error' not in str(chunks)
    finally:
        await app.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [False, True, 0, -1, float('inf'), float('nan')])
async def test_invalid_explicit_turn_budget_is_rejected(host, value):
    app, config, _, _, _ = host
    config['opencode']['turn_timeout'] = value
    with pytest.raises(ValueError, match='turn_timeout'):
        await app.create_instance(config)


@pytest.mark.asyncio
async def test_timeout_abort_ack_without_idle_keeps_execution_owner(host, monkeypatch):
    app, config, _, events, _ = host
    config['opencode']['turn_timeout'] = 0.01
    events[:] = [event('permission.asked', id='pending', permission='read', patterns=['fixture'])]
    await app.create_instance(config)
    original = app._adapter._call
    async def busy_status(method, path, **kw):
        if path == '/session/status':
            return {'ses_test': {'type':'busy'}}
        return await original(method, path, **kw)
    monkeypatch.setattr(app._adapter, '_call', busy_status)
    chunks = [x.payload async for x in app.process_message_stream(request())]
    assert not any(x.get('event_type') == 'chat.interrupt_result' and x.get('success') for x in chunks)
    assert app._adapter._sessions['test-session'].abort_failed
    with pytest.raises(ValueError, match='equipment cannot change during an active turn'):
        _ = [x async for x in app.process_message_stream(request())]
    monkeypatch.setattr(app._adapter, '_call', original)
    await app.cleanup()
