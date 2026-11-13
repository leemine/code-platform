"""Exercise the real TLS cloud channel through the local browser bridge."""
import asyncio
import json
import socket
from contextlib import asynccontextmanager

import pytest
import uvicorn
from fastapi import FastAPI
from websockets.legacy.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from gateway.services.cloud_resource_address import CloudAddresses
from gateway.services.data_sync.ui import COOKIE
from tests.unit_tests.data_sync.test_directory_ui import ui_hosts


@asynccontextmanager
async def local_ws(host):
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen(8)
    port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    host.local.local.config['public_origin'] = origin
    app = FastAPI()
    for route in host.local.websocket_routes():
        app.add_api_websocket_route(route.path, route.endpoint)
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done(): await task
                await asyncio.sleep(.01)
        yield f'ws://127.0.0.1:{port}/api/v1/data-sync/ws', origin
    finally:
        await host.local.local.execution.close()
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()


async def receive(ws, kind, request_id=None):
    async with asyncio.timeout(8):
        while True:
            frame = json.loads(await ws.recv())
            if frame.get('type') == kind and (request_id is None or frame.get('id') == request_id):
                return frame


def test_addresses_are_target_and_account_bound_and_preserve_user_tool_bodies():
    a = CloudAddresses('wss://one/ws', {'authority': 'a', 'actor_id': 'user'})
    b = CloudAddresses('wss://two/ws', {'authority': 'a', 'actor_id': 'user'})
    c = CloudAddresses('wss://one/ws', {'authority': 'a', 'actor_id': 'other'})
    sid = a.encode('s', 'sess_1')
    assert a.params({'session_id': sid}) == {'session_id': 'sess_1'}
    for other in (b, c):
        with pytest.raises(PermissionError): other.params({'session_id': sid})
    with pytest.raises(PermissionError): a.params({'project_id': 'default_code'})
    body = {'session_id': 'sess_1', 'content': {'session_id': 'literal'}, 'tool_arguments': {'project_id': 'literal'}}
    out = a.result(body)
    assert out['session_id'] == sid and out['content'] == body['content'] and out['tool_arguments'] == body['tool_arguments']
    assert a.params({'previous_session_id': 'local_id', 'previous_mode': 'agent'}) == {}


@pytest.mark.asyncio
async def test_local_bridge_runs_original_cloud_requests_stream_history_and_approval(ui_hosts):
    host = ui_hosts
    host.channel.on_message(lambda message: False)
    received = []
    async def handler(ws, req_id, params, session_id):
        received.append(dict(params))
        await host.channel.send_response(ws, req_id, ok=True, payload={'session_id': 'sess_cloud', 'project_id': 'proj_cloud'})
        await host.channel.send_event(ws, 'chat.chunk', {'session_id': 'sess_cloud', 'content': 'cloud result'})
    for method in ('session.create', 'chat.send', 'chat.user_answer', 'history.get', 'chat.interrupt', 'command.goal'):
        host.channel.register_method(method, handler)
    login = await host.client.post('/api/v1/data-sync/login', json={'username': 'ui-user', 'password': 'isolated-ui-password'})
    assert login.status_code == 200
    token = host.client.cookies.get(COOKIE)
    identity = await host.local.local.identity(token)
    addresses = CloudAddresses(host.local.local.endpoint, identity)
    async with local_ws(host) as (url, origin):
        async with connect(url, origin=origin, extra_headers={'Cookie': COOKIE + '=' + token}) as ws:
            await ws.send(json.dumps({'type': 'req', 'id': 'create', 'method': 'session.create',
                'params': {'project_id': addresses.encode('p', 'proj_cloud'), 'project_dir': '/local/never', 'create_token': 'once'}}))
            result = await receive(ws, 'res', 'create')
            sid = result['payload']['session_id']
            assert sid == addresses.encode('s', 'sess_cloud')
            assert 'project_dir' not in received[0] and received[0]['project_id'] == 'proj_cloud'
            event = await receive(ws, 'event')
            assert event['payload'] == {'session_id': sid, 'content': 'cloud result'}
            for method in ('chat.send', 'chat.user_answer', 'history.get', 'chat.interrupt', 'command.goal'):
                await ws.send(json.dumps({'type': 'req', 'id': method, 'method': method,
                    'params': {'session_id': sid, 'content': 'unchanged'}}))
                assert (await receive(ws, 'res', method))['ok']
                await receive(ws, 'event')
            assert all(p['session_id'] == 'sess_cloud' for p in received[1:])
            await host.local.local.execution.discard(token)
            with pytest.raises(ConnectionClosed): await ws.recv()
    assert len(received) == 6
    assert (host.root / 'source-files/keep.txt').read_text() == 'original content'


@pytest.mark.asyncio
async def test_bridge_rejects_bad_origin_local_selector_and_revoked_cookie(ui_hosts):
    host = ui_hosts
    host.channel.on_message(lambda message: False)
    token = host.accounts.login('ui-user', 'isolated-ui-password')['token']
    async with local_ws(host) as (url, origin):
        with pytest.raises(InvalidStatusCode):
            async with connect(url, origin='https://wrong.test', extra_headers={'Cookie': COOKIE + '=' + token}): pass
        async with connect(url, origin=origin, extra_headers={'Cookie': COOKIE + '=' + token}) as ws:
            await ws.send(json.dumps({'type': 'req', 'id': 'bad', 'method': 'chat.send', 'params': {'session_id': 'local_session'}}))
            with pytest.raises(ConnectionClosed):
                while True: await ws.recv()
        host.accounts.logout(token)
        async with connect(url, origin=origin, extra_headers={'Cookie': COOKIE + '=' + token}) as ws:
            with pytest.raises(ConnectionClosed) as closed:
                await ws.recv()
            assert closed.value.code == 1008


@pytest.mark.asyncio
async def test_transport_loss_requests_reconnect_without_replaying_an_input(ui_hosts):
    host = ui_hosts
    host.channel.on_message(lambda message: False)
    calls = []
    async def lost(ws, req_id, params, session_id):
        calls.append(params)
        await ws.close(code=1011)
    host.channel.register_method('chat.send', lost)
    token = host.accounts.login('ui-user', 'isolated-ui-password')['token']
    addresses = CloudAddresses(host.local.local.endpoint, await host.local.local.identity(token))
    async with local_ws(host) as (url, origin):
        async with connect(url, origin=origin, extra_headers={'Cookie': COOKIE + '=' + token}) as ws:
            await ws.send(json.dumps({'type': 'req', 'id': 'once', 'method': 'chat.send',
                'params': {'session_id': addresses.encode('s', 'sess_cloud'), 'content': 'once'}}))
            with pytest.raises(ConnectionClosed) as closed:
                while True: await ws.recv()
            assert closed.value.code == 1011
    assert len(calls) == 1


def test_history_record_metadata_is_scoped_without_changing_user_or_tool_content():
    a = CloudAddresses('wss://one/ws', {'authority': 'a', 'actor_id': 'user'})
    record = {'session_id': 'sess_1', 'event_type': 'chat.final',
              'content': '{"session_id":"user literal"}', 'tool_arguments': {'session_id': 'opaque'}}
    for content in (record, json.dumps(record)):
        frame = a.frame({'type': 'event', 'event': 'history.message',
                         'payload': {'session_id': 'sess_1', 'content': content}})
        mapped = frame['payload']['content']
        if isinstance(mapped, str): mapped = json.loads(mapped)
        assert mapped['session_id'] == frame['payload']['session_id'] == a.encode('s', 'sess_1')
        assert mapped['content'] == record['content'] and mapped['tool_arguments'] == record['tool_arguments']


@pytest.mark.asyncio
async def test_upgrade_does_not_wait_for_authority_but_cloud_requests_do(ui_hosts, monkeypatch):
    host = ui_hosts
    host.channel.on_message(lambda message: False)
    token = host.accounts.login('ui-user', 'isolated-ui-password')['token']
    original_identity = host.local.local.identity
    gate = asyncio.Event()
    calls = []

    async def delayed_identity(credential):
        await gate.wait()
        return await original_identity(credential)

    async def models(ws, req_id, params, session_id):
        calls.append(req_id)
        await host.channel.send_response(ws, req_id, ok=True, payload={'models': []})

    monkeypatch.setattr(host.local.local, 'identity', delayed_identity)
    host.channel.register_method('models.list', models)
    async with local_ws(host) as (url, origin):
        try:
            async with connect(url, origin=origin, extra_headers={'Cookie': COOKIE + '=' + token}, open_timeout=1) as ws:
                await ws.send(json.dumps({'type': 'req', 'id': 'models', 'method': 'models.list', 'params': {}}))
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(ws.recv(), .05)
                assert calls == []
                gate.set()
                ready = await receive(ws, 'event')
                assert ready['event'] == 'connection.ack' and ready['payload']['transport'] == 'cloud-bridge'
                assert (await receive(ws, 'res', 'models'))['ok']
                assert calls == ['models']
        finally:
            gate.set()


@pytest.mark.asyncio
async def test_open_bridge_rechecks_revocation_before_each_request(ui_hosts):
    host = ui_hosts
    host.channel.on_message(lambda message: False)
    calls = []

    async def models(ws, req_id, params, session_id):
        calls.append(req_id)
        await host.channel.send_response(ws, req_id, ok=True, payload={'models': []})

    host.channel.register_method('models.list', models)
    token = host.accounts.login('ui-user', 'isolated-ui-password')['token']
    async with local_ws(host) as (url, origin):
        async with connect(url, origin=origin, extra_headers={'Cookie': COOKIE + '=' + token}) as ws:
            await receive(ws, 'event')
            await ws.send(json.dumps({'type': 'req', 'id': 'before', 'method': 'models.list', 'params': {}}))
            assert (await receive(ws, 'res', 'before'))['ok']
            host.accounts.logout(token)
            await ws.send(json.dumps({'type': 'req', 'id': 'after', 'method': 'models.list', 'params': {}}))
            with pytest.raises(ConnectionClosed):
                while True:
                    await ws.recv()
    assert calls == ['before']
