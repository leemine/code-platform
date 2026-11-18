"""Official CLI adapter contract with controlled child processes and real state.

These tests do not constitute real GitHub authorization or repository acceptance.
"""
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from gateway.services.project_identity import ProjectIdentity
from gateway.services.project_github import GitHubConnections, GitHubError
from gateway.services.project_gh_login import GhLogin

A = ProjectIdentity('authority', 'alice')
B = ProjectIdentity('authority', 'bob')

class FakeLogin:
    all = []
    def __init__(self, executable, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700)
        self.changed = threading.Event()
        self.finished = threading.Event()
        self.process = SimpleNamespace(returncode=0)
        self.code = None
        self.closed = False
        self.user = {'id':7, 'login':'example'}
        self.credentials_value = {'hosts.yml':'synthetic-private-credential'}
        self.all.append(self)
    def start(self):
        self.code = 'ABCD-EFGH'
        self.changed.set()
    def run(self, args):
        if args == ['api','user']:
            return json.dumps(self.user)
        assert args == ['auth','token','--hostname','github.com']
        return 'synthetic-private-token'
    def credentials(self):return dict(self.credentials_value)
    def restore(self, values):self.credentials_value = dict(values)
    def close(self):
        self.closed = True
        self.finished.set()
        import shutil
        shutil.rmtree(self.directory,ignore_errors=True)

@pytest.fixture
def service(tmp_path, monkeypatch):
    from gateway.auth import session_store
    monkeypatch.setattr(session_store, 'auth_dir', lambda: tmp_path)
    calls, faults = [], {}
    def handler(request):
        calls.append(request)
        if faults.get('callback'):faults.pop('callback')()
        if faults.get('status'):return httpx.Response(faults['status'],json={'secret':'must-not-leak'},headers=faults.get('headers',{}))
        assert request.headers['authorization']=='Bearer synthetic-private-token'
        repository={'id':42,'full_name':'owner/repo','default_branch':'main','private':True}
        if request.url.path=='/user':value={'id':7,'login':'example'}
        elif request.url.path=='/user/repos':value=[repository]
        elif request.url.path=='/repositories/42':value=repository
        elif request.url.path=='/repos/owner/repo/branches/main':value={'name':'main','commit':{'sha':'a'*40}}
        elif request.url.path=='/repos/owner/repo/branches':value=[{'name':'main','commit':{'sha':'a'*40}}]
        else:raise AssertionError(request.url.path)
        return httpx.Response(200,json=value)
    FakeLogin.all=[]
    s=GitHubConnections(tmp_path/'private', {'executable':'python3'},transport=httpx.MockTransport(handler),login_factory=FakeLogin)
    yield s,calls,faults
    s.close()

def ready(s, who=A):
    result=s.begin(who,'cloud','draft',lambda _:None)
    attempt=s.pending[s.scope(who,'cloud')]
    attempt['login'].finished.set()
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        state=s.poll_device(who,'cloud',result['device']['attempt_id'],lambda _:None)
        if state['state']=='connected':return result
        time.sleep(.01)
    raise AssertionError('fake login did not finish')

def test_official_login_output_is_only_short_code(service):
    s,_,_=service
    result=ready(s)
    assert result['flow']=='device' and result['device']['user_code']=='ABCD-EFGH'
    assert result['device']['verification_uri']=='https://github.com/login/device'
    status=s.status(A,'cloud',lambda _:None)
    assert status['state']=='connected' and status['authorization_mode']=='gh'
    assert 'synthetic' not in json.dumps(result)+json.dumps(status)
    assert b'synthetic-private' not in s.path.read_bytes()
    assert all(item.closed for item in FakeLogin.all)
    assert not list(s.root.glob('gh-tmp-*'))

def test_accounts_are_isolated_and_old_attempt_cannot_be_reused(service):
    s,_,_=service
    old=ready(s)
    assert s.status(B,'cloud')['state']=='disconnected'
    with pytest.raises(GitHubError,match='CONNECTION_CHANGED'):
        s.poll_device(B,'cloud',old['device']['attempt_id'],lambda _:None)
    s.disconnect(A,'cloud')
    with pytest.raises(GitHubError,match='REAUTHORIZE'):s.usable_connection(A,'cloud',lambda _:None)

def test_disconnect_fences_late_success(service):
    s,_,_=service
    result=s.begin(A,'cloud','draft')
    login=FakeLogin.all[-1]
    s.disconnect(A,'cloud')
    login.finished.set()
    time.sleep(.05)
    assert s.status(A,'cloud')['state']=='disconnected'
    assert not list(s.root.glob('gh-tmp-*'))

def test_revoke_during_login_never_saves_credentials(service):
    s,_,_=service
    state={'revoked':False}
    def guard(_):
        if state['revoked']:raise PermissionError()
    result=s.begin(A,'cloud','draft',guard)
    state['revoked']=True
    FakeLogin.all[-1].finished.set()
    time.sleep(.05)
    assert s.read(s.scope(A,'cloud'))[1]['state']=='reauthorize'
    assert 'credentials' not in s.read(s.scope(A,'cloud'))[1]

def test_catalog_and_resolve_recheck_account_and_repository(service):
    s,calls,_=service;ready(s)
    seen=[]
    guard=lambda target:seen.append(target)
    assert s.catalog(A,'cloud','accounts',{},guard)['items']==[{'id':7,'account':'example'}]
    rows=s.catalog(A,'cloud','repositories',{'account_id':7},guard)
    assert rows['items'][0]['full_name']=='owner/repo'
    value=s.resolve(A,'cloud',{'account_id':7,'repository_id':42,'branch':'main'},guard)
    assert value['account_id']==7 and value['branch']['commit']=='a'*40
    assert len(seen)>=6
    assert '/repositories/42' in [r.url.path for r in calls]
    with pytest.raises(GitHubError,match='ACCOUNT_CHANGED'):
        s.catalog(A,'cloud','repositories',{'account_id':8},guard)

@pytest.mark.parametrize('status,headers,code',[(401,{},'REAUTHORIZE'),(404,{},'REAUTHORIZE'),(429,{},'RATE_LIMITED'),(403,{'x-ratelimit-remaining':'0'},'RATE_LIMITED'),(503,{},'UPSTREAM_UNAVAILABLE')])
def test_api_errors_are_bounded_and_do_not_leak(service,status,headers,code):
    s,_,faults=service;ready(s);faults.update(status=status,headers=headers)
    with pytest.raises(GitHubError,match='^GITHUB_'+code+'$'):
        s.catalog(A,'cloud','repositories',{'account_id':7},lambda _:None)
    if status in (429, 503) or headers:
        assert s.read(s.scope(A,'cloud'))[1]['state']=='connected'

def test_disconnect_while_fetching_discards_result(service):
    s,_,faults=service;ready(s);faults['callback']=lambda:s.disconnect(A,'cloud')
    with pytest.raises(GitHubError,match='CONNECTION_CHANGED'):
        s.catalog(A,'cloud','repositories',{'account_id':7},lambda _:None)

def test_private_store_rejects_symlink_and_public_modes(tmp_path):
    root=tmp_path/'public';root.mkdir(mode=0o755)
    with pytest.raises(GitHubError,match='PRIVATE_STORAGE'):GitHubConnections(root)
    root.chmod(0o700);link=tmp_path/'link';link.symlink_to(root)
    with pytest.raises(GitHubError,match='PRIVATE_STORAGE'):GitHubConnections(link)

def test_gh_never_inherits_host_credentials_or_browser(tmp_path,monkeypatch):
    monkeypatch.setenv('GH_TOKEN','operator-token')
    monkeypatch.setenv('GITHUB_TOKEN','operator-token')
    monkeypatch.setenv('GH_CONFIG_DIR','/operator/private')
    monkeypatch.setenv('GH_BROWSER','operator-command')
    login=GhLogin('/usr/bin/gh',tmp_path/'attempt')
    try:
        assert 'GH_TOKEN' not in login.environment and 'GITHUB_TOKEN' not in login.environment
        assert login.environment['GH_CONFIG_DIR']==str(tmp_path/'attempt')
        assert login.environment['GH_BROWSER']=='/bin/true'
        login.restore({'hosts.yml':'synthetic-private-credential'})
        assert (tmp_path/'attempt/hosts.yml').stat().st_mode & 0o077 == 0
        assert login.credentials()=={'hosts.yml':'synthetic-private-credential'}
    finally:login.close()
    assert not (tmp_path/'attempt').exists()


def test_duplicate_begin_does_not_spawn_or_cancel_current_login(service):
    s, _, _ = service
    first = s.begin(A, 'cloud', 'one')
    with pytest.raises(GitHubError, match='GITHUB_BUSY'):
        s.begin(A, 'cloud', 'two')
    assert len(FakeLogin.all) == 1
    assert s.read(s.scope(A, 'cloud'))[0] == first['device']['attempt_id']
    s.disconnect(A, 'cloud', expected='old-generation')
    assert s.poll_device(A, 'cloud', first['device']['attempt_id'], lambda _: None)['state'] == 'pending'


def test_shutdown_closes_pending_login_and_releases_storage(service):
    s, _, _ = service
    s.begin(A, 'cloud', 'one')
    s.close()
    assert not list(s.root.glob('gh-tmp-*'))
    replacement = GitHubConnections(s.root, {'executable':'python3'}, login_factory=FakeLogin)
    try:
        assert replacement.status(A, 'cloud')['state'] != 'connected'
    finally:
        replacement.close()
