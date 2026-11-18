"""GitCode contracts with mocked upstream, real encrypted store and fencing."""
import json
import httpx
import pytest
from gateway.services.project_gitcode import GitCodeConnections, GitCodeError
from gateway.services.project_identity import ProjectIdentity

A = ProjectIdentity('authority', 'alice')
B = ProjectIdentity('authority', 'bob')
TOKEN = 'synthetic-gitcode-private-token'
USER = '64e5ed8f7e20aa73efcbc302'
SELECTION = {'account_id': USER, 'repository_id': 42, 'full_name': 'owner/repo', 'branch': 'main'}


@pytest.fixture
def service(tmp_path, monkeypatch):
    from gateway.auth import session_store
    monkeypatch.setattr(session_store, 'auth_dir', lambda: tmp_path)
    calls, fault = [], {}
    def handler(request):
        calls.append(request)
        assert request.url.host == 'api.gitcode.com'
        assert 'access_token' not in request.url.params
        assert request.headers['authorization'] == 'Bearer ' + TOKEN
        if fault.get('callback'):
            fault.pop('callback')()
        if fault.get('status'):
            return httpx.Response(fault['status'], json={'secret': TOKEN})
        row = {'id': 42, 'full_name': 'owner/repo', 'default_branch': 'main', 'private': True}
        branch = {'name': 'main', 'commit': {'id': 'a' * 40}}
        values = {'/api/v5/user': {'id': USER, 'login': 'owner'}, '/api/v5/user/repos': [row],
                  '/api/v5/repos/owner/repo': row, '/api/v5/repos/owner/repo/branches/main': branch,
                  '/api/v5/repos/owner/repo/branches': [branch]}
        return httpx.Response(200, json=values[request.url.path])
    s = GitCodeConnections(tmp_path / 'gitcode', transport=httpx.MockTransport(handler))
    yield s, calls, fault
    s.close()


def connect(s):
    return s.connect(A, 'cloud', TOKEN, lambda _: None)


def test_token_encryption_scope_and_repository_discovery(service):
    s, calls, _ = service
    assert connect(s) == {'state': 'connected', 'login': 'owner'}
    assert TOKEN.encode() not in s.path.read_bytes()
    assert s.status(B, 'cloud', lambda _: None)['state'] == 'disconnected'
    assert s.status(A, 'cloud', lambda _: None)['state'] == 'connected'
    accounts = s.catalog(A, 'cloud', 'accounts', {}, lambda _: None)
    assert accounts['items'] == [{'id': USER, 'account': 'owner'}]
    repos = s.catalog(A, 'cloud', 'repositories', SELECTION, lambda _: None)
    assert repos['items'][0]['id'] == 42
    branches = s.catalog(A, 'cloud', 'branches', SELECTION, lambda _: None)
    assert branches['items'] == [{'name': 'main', 'commit': 'a'*40}]
    source = s.resolve(A, 'cloud', SELECTION, lambda _: None)
    assert source['provider'] == 'gitcode' and source['account_id'] == USER
    assert TOKEN not in json.dumps([accounts, repos, branches, source])
    assert sum(r.url.path == '/api/v5/user' for r in calls) == 6


@pytest.mark.parametrize('status,code,state', [(401,'REAUTHORIZE','reauthorize'),
    (503,'UPSTREAM_UNAVAILABLE','connected'), (429,'RATE_LIMITED','connected'),
    (302,'UPSTREAM_UNAVAILABLE','connected')])
def test_transient_failures_preserve_credentials_and_denial_revokes(service, status, code, state):
    s, _, fault = service
    connect(s)
    fault['status'] = status
    with pytest.raises(GitCodeError, match='^GITCODE_' + code + '$'):
        s.usable_connection(A, 'cloud', lambda _: None)
    assert s.read(s.scope(A, 'cloud'))[1]['state'] == state


def test_disconnect_fences_late_connect_and_catalog(service):
    s, _, fault = service
    fault['callback'] = lambda: s.disconnect(A, 'cloud')
    with pytest.raises(GitCodeError, match='CONNECTION_CHANGED'):
        connect(s)
    assert s.status(A, 'cloud', lambda _: None)['state'] == 'disconnected'
    connect(s)
    fault['callback'] = lambda: s.disconnect(A, 'cloud')
    with pytest.raises(GitCodeError, match='CONNECTION_CHANGED'):
        s.resolve(A, 'cloud', SELECTION, lambda _: None)


def test_fresh_account_guard_before_storage_and_delivery(service):
    s, _, fault = service
    revoked = [False]
    def guard(_):
        if revoked[0]:
            raise PermissionError('revoked')
    fault['callback'] = lambda: revoked.__setitem__(0, True)
    with pytest.raises(PermissionError):
        s.connect(A, 'cloud', TOKEN, guard)
    assert s.read(s.scope(A, 'cloud'))[1] == {}


@pytest.mark.parametrize('changes', [{'full_name': '../repo'}, {'full_name': 'https://evil.invalid/a'},
    {'repository_id': 43}, {'account_id': 'someone-else'}, {'full_name': 'owner/..'}])
def test_reject_confused_repository_and_account(service, changes):
    s, _, _ = service
    connect(s)
    with pytest.raises(GitCodeError):
        s.resolve(A, 'cloud', {**SELECTION, **changes}, lambda _: None)


def test_reopen_preserves_encrypted_grant_and_rechecks_upstream(service):
    s, calls, _ = service
    connect(s)
    root, transport = s.root, s.transport
    s.close()
    reopened = GitCodeConnections(root, transport=transport)
    try:
        assert reopened.status(A, 'cloud', lambda _: None)['login'] == 'owner'
        assert len(calls) == 2
    finally:
        reopened.close()


@pytest.mark.parametrize('status', [401, 429, 503])
def test_failed_replacement_preserves_previous_connection(service, status):
    s, _, fault = service
    connect(s)
    previous = s.read(s.scope(A, 'cloud'))
    fault['status'] = status
    with pytest.raises(GitCodeError):
        connect(s)
    assert s.read(s.scope(A, 'cloud')) == previous


def test_failed_replacement_does_not_resurrect_disconnected_connection(service):
    s, _, fault = service
    connect(s)
    fault.update(status=503, callback=lambda: s.disconnect(A, 'cloud'))
    with pytest.raises(GitCodeError):
        connect(s)
    assert s.read(s.scope(A, 'cloud')) == ('', {})
