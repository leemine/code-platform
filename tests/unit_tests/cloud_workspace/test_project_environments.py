"""Original account/E2A adapters and durable preparation; no real GitHub grant."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from gateway.auth.account_authenticator import AccountPrincipal
from gateway.auth.request_scope import current_scope
from gateway.services.project_identity import ProjectIdentity, ProjectPrincipal
from gateway.services.project_environments import ProjectEnvironments
from gateway.services.project_github import GitHubConnections
from gateway.services.project_preparation import Preparations
from jiuwenswarm.server.control import project_import
from tests.unit_tests.cloud_workspace.test_project_import import source


@pytest.fixture(autouse=True)
def close_brokers(monkeypatch):
    original = GitHubConnections.__init__
    instances = []
    def tracked(self, *args, **kwargs):
        original(self, *args, **kwargs)
        instances.append(self)
    monkeypatch.setattr(GitHubConnections, '__init__', tracked)
    yield
    for service in instances:
        service.close()


@pytest.fixture
def account(monkeypatch, tmp_path):
    from gateway.auth import session_store
    monkeypatch.setattr(session_store, 'auth_dir', lambda: tmp_path / 'auth')
    monkeypatch.delenv('JIUWENSWARM_PROJECT_GITHUB_CONFIG', raising=False)
    state = {'revoked': False, 'checks': 0}
    def session(token):
        state['checks'] += 1
        if state['revoked']:
            raise PermissionError('expired')
        return {'user_id': 'alice', 'authority': 'test'}
    principal = AccountPrincipal(SimpleNamespace(session=session), 'synthetic', 'alice', 'test')
    reset = current_scope.set(principal)
    yield principal, state
    current_scope.reset(reset)


@pytest.mark.asyncio
async def test_missing_cli_status_does_not_allocate_instance_or_start_session(account, monkeypatch):
    monkeypatch.setattr("gateway.services.project_github.shutil.which", lambda _: None)
    channel = SimpleNamespace(channel_id='web', send_response=AsyncMock())
    bridge = ProjectEnvironments(channel, object())
    bridge.call = AsyncMock(side_effect=AssertionError('must not contact runtime'))
    await bridge.handle('project.github.status', None, 'r1', {}, None)
    assert channel.send_response.call_args.kwargs['payload'] == {
        'execution_target': 'cloud', 'configured': False, 'state': 'disconnected', 'can_import': False,
        'authorization_mode': 'gh', 'device': None, 'login': '', 'reason': None}
    assert account[1]['checks'] >= 3
    account[1]['revoked'] = True
    await bridge.handle('project.github.status', None, 'r2', {}, None)
    assert channel.send_response.call_args.kwargs['code'] == 'UNAUTHORIZED'


@pytest.mark.asyncio
async def test_no_target_or_user_override_and_fresh_delivery_check(account, monkeypatch):
    channel = SimpleNamespace(channel_id='web', send_response=AsyncMock())
    bridge = ProjectEnvironments(channel, object())
    async def fetch(**kwargs):
        assert kwargs['user_id'] == 'alice'
        assert kwargs['req_method'].value == 'project.import'
        account[1]['revoked'] = True
        return True, {'project_import_version': 1}
    monkeypatch.setattr('gateway.services.project_environments.fetch_agent_unary', fetch)
    with pytest.raises(PermissionError):
        await bridge.call('project.import', {'action': 'capabilities'})
    account[1]['revoked'] = False
    await bridge.handle('project.github.status', None, 'r', {'execution_target': 'another-user'}, None)
    assert channel.send_response.call_args.kwargs['ok'] is False
    await bridge.handle('project.github.status', None, 'r', {'user_id': 'bob'}, None)
    assert channel.send_response.call_args.kwargs['code'] == 'GITHUB_INVALID_FIELDS'


@pytest.mark.asyncio
async def test_prepare_pins_commit_recovers_lost_reply_and_never_overwrites(source, account, tmp_path, monkeypatch):
    from gateway.services import project_preparation as coordinator
    params, raw, _ = source
    service = GitHubConnections(tmp_path/'broker', {'executable':'python3'})
    identity = ProjectIdentity('test', 'alice')
    principal = ProjectPrincipal(account[0])
    resolved = {**params['source'], 'branch': {'name': 'main', 'commit': params['source']['commit']}}
    service.resolve = lambda *args: dict(resolved)
    service.usable_connection = lambda *args: ('g1', {'access_token': 'synthetic'})
    service.read = lambda scope: ('g1', {})
    def make_bundle(root, *args, **kwargs):
        kwargs['validate']()
        root.mkdir(mode=0o700)
        out = root/'source.bundle'
        out.write_bytes(raw)
        return out
    monkeypatch.setattr(coordinator, 'make_bundle', make_bundle)
    channel = SimpleNamespace(channel_id='web')
    bridge = ProjectEnvironments(channel, object())
    calls, lost = [], [True]
    async def target_call(target, request):
        calls.append(request['params']['action'])
        result = project_import.execute(request['params'], 'alice')
        if request['params']['action'] == 'publish' and lost[0]:
            lost[0] = False
            raise ConnectionError('reply lost')
        return {'ok': True, 'payload': result}
    bridge.node_request = target_call
    preparation = Preparations(bridge, service)
    intent = {'execution_target': 'cloud', 'operation_id': params['operation_id'], 'name': params['name'],
              'account_id': 2, 'repository_id': 1, 'branch': 'main'}
    assert (await preparation.request(principal, identity, intent))['state'] == 'accepted'
    await asyncio.gather(*list(preparation.tasks.values()))
    key = service.scope(identity, 'cloud')
    first = preparation.read(key, params['operation_id'])
    assert first['state'] == 'failed'
    resolved['branch'] = {'name': 'main', 'commit': 'a'*40}
    await preparation.request(principal, identity, intent)
    await asyncio.gather(*list(preparation.tasks.values()))
    status = await preparation.request(principal, identity, {'execution_target':'cloud','operation_id':params['operation_id']}, query=True)
    assert status['state'] == 'ready'
    assert status['project']['repository_source']['commit'] == params['source']['commit']
    assert calls.count('publish') == 1
    assert preparation.read(key, params['operation_id'])['bundle'] == first['bundle']
    account[1]['revoked'] = True
    with pytest.raises(PermissionError):
        await preparation.request(principal, identity, {'execution_target':'cloud','operation_id':params['operation_id']}, query=True)


def test_deployment_requires_private_device_configuration(tmp_path, monkeypatch):
    config = tmp_path/'github.json'
    config.write_text(json.dumps({'root':str(tmp_path/'private'),'authorization_mode':'web'}))
    config.chmod(0o600)
    monkeypatch.setenv('JIUWENSWARM_PROJECT_GITHUB_CONFIG', str(config))
    with pytest.raises(ValueError, match='CLI_CONFIGURATION_REQUIRED'):
        ProjectEnvironments(None, None)


@pytest.mark.asyncio
async def test_revocation_after_checkout_prevents_project_registration(source, account, tmp_path, monkeypatch):
    from gateway.services import project_preparation as coordinator
    from jiuwenswarm.server.runtime.session import project_store
    params, raw, _ = source
    service = GitHubConnections(tmp_path/'broker-revoked', {'executable':'python3'})
    identity = ProjectIdentity('test', 'alice')
    principal = ProjectPrincipal(account[0])
    def resolve(*args):
        args[-1]('cloud')
        return {**params['source'], 'branch':{'name':'main','commit':params['source']['commit']}}
    service.resolve = resolve
    service.usable_connection = lambda *args: ('g1', {'access_token':'synthetic'})
    service.read = lambda scope: ('g1', {})
    def make_bundle(root, *args, **kwargs):
        kwargs['validate']()
        root.mkdir(mode=0o700)
        out = root/'source.bundle'
        out.write_bytes(raw)
        return out
    monkeypatch.setattr(coordinator, 'make_bundle', make_bundle)
    bridge = ProjectEnvironments(SimpleNamespace(channel_id='web'), object())
    calls = []
    async def target_call(target, request):
        action = request['params']['action']
        calls.append(action)
        result = project_import.execute(request['params'], 'alice')
        if action == 'verify':
            assert result['state'] == 'verified'
            account[1]['revoked'] = True
        return {'ok':True, 'payload':result}
    bridge.node_request = target_call
    preparation = Preparations(bridge, service)
    intent = {'execution_target':'cloud','operation_id':params['operation_id'],'name':params['name'],
              'account_id':2,'repository_id':1,'branch':'main'}
    await preparation.request(principal, identity, intent)
    await asyncio.gather(*list(preparation.tasks.values()))
    record = preparation.read(service.scope(identity,'cloud'),params['operation_id'])
    assert record['state'] == 'failed'
    assert 'verify' in calls and 'publish' not in calls
    assert project_store.list_projects(cache_bust=True) == []


@pytest.mark.asyncio
async def test_gitcode_uses_account_route_and_capability_and_retains_github(account, monkeypatch):
    from gateway.services.project_gitcode import GitCodeConnections
    calls = []
    def request(service, method, path, *, token):
        calls.append((service.provider, method, path))
        assert token == 'synthetic-gitcode'
        return {'id': 'opaque-user', 'login': 'owner'}
    monkeypatch.setattr(GitCodeConnections, 'request', request)
    channel = SimpleNamespace(channel_id='web', send_response=AsyncMock())
    bridge = ProjectEnvironments(channel, object())
    bridge.call = AsyncMock(return_value=(True, {'project_import_version': 1}))
    try:
        await bridge.handle('project.gitcode.connect', None, 'c1', {'access_token': 'synthetic-gitcode'}, None)
        assert channel.send_response.call_args.kwargs['payload']['state'] == 'connected'
        assert bridge.project_gitcode.root != bridge.project_github.root
        await bridge.handle('project.gitcode.status', None, 'c2', {}, None)
        assert channel.send_response.call_args.kwargs['payload']['can_import'] is False
        bridge.call.return_value = (True, {'project_import_version': 1, 'repository_providers': ['github', 'gitcode']})
        await bridge.handle('project.gitcode.status', None, 'c3', {}, None)
        assert channel.send_response.call_args.kwargs['payload']['can_import'] is True
        assert len(calls) == 3
        account[1]['revoked'] = True
        await bridge.handle('project.gitcode.accounts', None, 'c4', {}, None)
        assert channel.send_response.call_args.kwargs['code'] == 'UNAUTHORIZED'
        assert len(calls) == 3
    finally:
        await bridge.close()
