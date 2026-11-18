"""Real Git trees/receipts/registry, synthetic repository and no external services."""
import base64
import hashlib
from pathlib import Path
import subprocess
import uuid

import pytest
from jiuwenswarm.server.control import project_import as subject
from jiuwenswarm.server.runtime.session import project_store


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()


@pytest.fixture
def source(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    data.mkdir()
    monkeypatch.setenv('JIUWENSWARM_DATA_DIR', str(data))
    monkeypatch.setattr(project_store, 'get_agent_root_dir', lambda: data)
    project_store.invalidate_cache()
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    (repo / 'README.md').write_text('original content\n')
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
    sha = git(repo, 'rev-parse', 'HEAD')
    bundle = tmp_path / 'source.bundle'
    git(repo, 'bundle', 'create', str(bundle), 'refs/heads/main')
    raw = bundle.read_bytes()
    params = {'operation_id': uuid.uuid4().hex, 'name': 'example', 'lfs_mode': 'deferred', 'source': {
        'repository_id': 1, 'account_id': 2, 'full_name': 'owner/repo', 'branch': 'main', 'commit': sha},
        'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    yield params, raw, data
    project_store.invalidate_cache()


def call(params, action, user='alice', **fields):
    return subject.execute({'action': action, 'operation_id': params['operation_id'], **fields}, user)


def upload(params, raw):
    subject.execute({'action': 'begin', **params}, 'alice')
    cut = len(raw) // 2
    call(params, 'chunk', offset=0, data=base64.b64encode(raw[:cut]).decode())
    # Retry an acknowledged prefix, then recover its durable offset.
    call(params, 'chunk', offset=0, data=base64.b64encode(raw[:cut]).decode())
    assert call(params, 'status')['offset'] == cut
    call(params, 'chunk', offset=cut, data=base64.b64encode(raw[cut:]).decode())
    call(params, 'verify')
    return call(params, 'publish')


def test_preparation_and_receipt_recovery_do_not_create_session(source):
    params, raw, data = source
    result = upload(params, raw)
    assert result['state'] == 'ready'
    assert result['checks'] == {'workspace': 'ready', 'source': 'ready', 'dependencies': 'unknown', 'execution_authorized': False}
    project = result['project']
    root = Path(project['project_dir'])
    assert (root / 'README.md').read_text() == 'original content\n'
    assert git(root, 'rev-parse', 'HEAD') == params['source']['commit']
    assert git(root, 'branch', '--show-current') == 'main'
    assert call(params, 'publish')['project']['project_id'] == project['project_id']
    assert len(project_store.list_projects()) == 1
    assert not (data / 'sessions').exists()
    assert 'token' not in (root / '.git/config').read_text()


def test_multi_project_selection_and_old_directory_retained(source):
    params, raw, _ = source
    first = upload(params, raw)['project']
    second = upload({**params, 'name': 'second', 'operation_id': uuid.uuid4().hex}, raw)['project']
    assert first['project_dir'] != second['project_dir']
    assert len(project_store.list_projects()) == 2
    (Path(first['project_dir']) / 'README.md').write_text('user changes')
    assert call(params, 'status')['project']['project_id'] == first['project_id']
    assert (Path(first['project_dir']) / 'README.md').read_text() == 'user changes'


def test_account_scope_conflict_and_hidden_receipt(source):
    params, raw, _ = source
    result = upload(params, raw)
    with pytest.raises(ValueError, match='NOT_FOUND'):
        call(params, 'status', user='bob')
    with pytest.raises(ValueError, match='CONFLICT'):
        subject.execute({'action': 'begin', **params, 'name': 'changed'}, 'alice')
    project_store.hide_project(result['project']['project_id'])
    with pytest.raises(PermissionError, match='UNAVAILABLE'):
        call(params, 'status')


def test_existing_directory_never_overwritten(source):
    params, raw, _ = source
    result = upload(params, raw)
    root = Path(result['project']['project_dir'])
    with pytest.raises(ValueError, match='DIRECTORY_EXISTS'):
        subject.execute({'action': 'begin', **params, 'operation_id': uuid.uuid4().hex}, 'alice')
    assert (root / 'README.md').read_text() == 'original content\n'


def test_invalid_digest_and_changed_root_fail_closed(source):
    params, raw, _ = source
    broken = {**params, 'sha256': 'f'*64}
    with pytest.raises(ValueError, match='BUNDLE_MISMATCH'):
        upload(broken, raw)
    assert project_store.list_projects() == []
    root = Path(project_store.resolve_default_project_dir(params['name'], 'code'))
    root.rename(root.with_name('preserved'))
    root.symlink_to(root.with_name('preserved'), target_is_directory=True)
    with pytest.raises(ValueError, match='ROOT_CHANGED'):
        call(broken, 'status')


def test_pinned_commit_survives_a_force_moved_branch(source, tmp_path):
    params, _, _ = source
    repo = tmp_path / 'repo'
    pinned = params['source']['commit']
    git(repo, 'update-ref', 'refs/swarm-cache/' + pinned, pinned)
    git(repo, 'checkout', '--orphan', 'replacement')
    git(repo, 'rm', '-rf', '.')
    (repo/'new.txt').write_text('new independent history')
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'replacement')
    git(repo, 'branch', '-f', 'main', 'HEAD')
    bundle = tmp_path/'moved.bundle'
    git(repo, 'bundle', 'create', str(bundle), '--branches', '--tags', 'refs/swarm-cache/'+pinned)
    raw = bundle.read_bytes()
    result = upload({**params, 'size':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()},raw)
    root = Path(result['project']['project_dir'])
    assert git(root, 'rev-parse', 'HEAD') == pinned
    assert (root/'README.md').read_text() == 'original content\n'
    assert not (root/'new.txt').exists()


def test_slow_checkout_does_not_publish_without_a_new_authorized_request(source):
    params, raw, _ = source
    subject.execute({'action':'begin',**params},'alice')
    call(params,'chunk',offset=0,data=base64.b64encode(raw).decode())
    with pytest.raises(ValueError,match='VERIFICATION_REQUIRED'):
        call(params,'publish')
    assert call(params,'verify')['state']=='verified'
    assert project_store.list_projects()==[]
    assert call(params,'publish')['state']=='ready'


def test_gitcode_source_preserves_provider_branch_and_credential_free_origin(source):
    params, raw, data = source
    params['source'].update(provider='gitcode', account_id='64e5ed8f7e20aa73efcbc302')
    result = upload(params, raw)
    root = Path(result['project']['project_dir'])
    assert git(root, 'remote', 'get-url', 'origin') == 'https://gitcode.com/owner/repo.git'
    assert git(root, 'rev-parse', 'HEAD') == params['source']['commit']
    assert git(root, 'branch', '--show-current') == 'main'
    assert result['project']['repository_source']['provider'] == 'gitcode'
    assert call(params, 'status')['state'] == 'ready'
    assert not (data / 'sessions').exists()
    changed = {**params, 'source': {**params['source'], 'provider': 'github', 'account_id': 2}}
    with pytest.raises(ValueError, match='CONFLICT'):
        subject.execute({'action': 'begin', **changed}, 'alice')
