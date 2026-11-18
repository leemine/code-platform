"""Account-scoped official gh login and read-only project discovery."""
from __future__ import annotations
import json
import re
import secrets
import shutil
import threading
import time
from urllib.parse import quote
import contextvars
import portalocker
from jiuwenswarm.common.auth.session_store import encrypt_json
from gateway.services.project_gh_login import GhLogin
from gateway.services.project_connections import RepositoryConnections, RepositoryError

METHODS = frozenset('project.github.' + name for name in (
    'status', 'begin', 'poll', 'disconnect', 'accounts', 'repositories', 'branches', 'resolve'))

class GitHubError(RepositoryError):
    """Only fixed error codes cross the public transport."""

def positive_id(value):
    if type(value) is not int or not 0 < value < 2**53:
        raise GitHubError('GITHUB_INVALID_ID')
    return value

class GitHubConnections(RepositoryConnections):
    provider = 'github'
    fingerprint = 'official-gh-v1'
    api_origin = 'https://api.github.com'
    api_headers = {'X-GitHub-Api-Version': '2022-11-28'}
    error_type = GitHubError

    def __init__(self, root, config=None, *, transport=None, clock=time.time, login_factory=GhLogin):
        config = config or {}
        self.login_factory = login_factory
        self.executable = shutil.which(config.get('executable', 'gh'))
        super().__init__(root, transport=transport, clock=clock)
        self.pending = {}
        try:
            with self.db() as db:
                rows = db.execute('SELECT scope,body FROM connections').fetchall()
                for row in rows:
                    if self.decode(row['body']).get('state') == 'pending':
                        db.execute('DELETE FROM connections WHERE scope=?', (row['scope'],))
            for path in self.root.glob('gh-tmp-*'):
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
        except Exception:
            self.lease.release()
            raise

    def begin(self, identity, target, draft, guard=lambda _: None):
        if not isinstance(draft, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', draft):
            raise GitHubError('GITHUB_INVALID_DRAFT')
        guard(target)
        if not self.executable:
            raise GitHubError('GITHUB_CLI_UNAVAILABLE')
        scope, generation = self.scope(identity, target), secrets.token_hex(16)
        with self.lock:
            if self.closed or scope in self.pending or len(self.pending) >= 4:
                raise GitHubError('GITHUB_BUSY')
            login = self.login_factory(self.executable, self.root / ('gh-tmp-' + secrets.token_hex(16)))
            attempt = {'generation': generation, 'login': login, 'expires': self.clock() + 900}
            self.pending[scope] = attempt
            try:
                with self.db() as db:
                    db.execute('INSERT OR REPLACE INTO connections VALUES (?,?,?)',
                        (scope, generation, encrypt_json({'state': 'pending'})))
                login.start()
                context = contextvars.copy_context()
                worker = threading.Thread(target=lambda: context.run(self._finish_login, scope, attempt, target, guard), daemon=True)
                attempt['worker'] = worker
                worker.start()
            except Exception:
                self.pending.pop(scope, None)
                with self.db() as db:
                    db.execute('DELETE FROM connections WHERE scope=? AND generation=?', (scope, generation))
                login.close()
                raise
        try:
            login.changed.wait(15)
            guard(target)
            if not login.code:
                raise GitHubError('GITHUB_AUTHORIZATION_FAILED')
            return {'flow': 'device', 'device': self._device(attempt)}
        except Exception:
            self.disconnect(identity, target, expected=generation)
            raise

    def _device(self, attempt):
        return {'attempt_id': attempt['generation'], 'user_code': attempt['login'].code,
                'verification_uri': 'https://github.com/login/device', 'expires_at': attempt['expires'], 'retry_after': 2}

    def _finish_login(self, scope, attempt, target, guard):
        login, generation = attempt['login'], attempt['generation']
        try:
            while not login.finished.wait(1):
                if self.closed or self.clock() >= attempt['expires'] or self.read(scope)[0] != generation:
                    raise GitHubError('GITHUB_AUTHORIZATION_EXPIRED')
            if self.closed or login.process.returncode:
                raise GitHubError('GITHUB_AUTHORIZATION_FAILED')
            guard(target)
            user = json.loads(login.run(['api', 'user']))
            positive_id(user.get('id'))
            if not re.fullmatch(r'[A-Za-z0-9-]{1,100}', user.get('login', '')):
                raise GitHubError('GITHUB_INVALID_RESPONSE')
            credentials = login.credentials()
            guard(target)
            self.write(scope, generation, {'state': 'connected', 'login': user['login'], 'account_id': user['id'], 'credentials': credentials})
        except Exception:
            try:
                self.write(scope, generation, {'state': 'reauthorize', 'reason': 'authorization_failed'})
            except GitHubError:
                pass
        finally:
            login.close()
            with self.lock:
                if self.pending.get(scope) is attempt:
                    self.pending.pop(scope, None)

    def disconnect(self, identity, target, *, expected=None):
        scope = self.scope(identity, target)
        with self.lock:
            if expected is not None and self.read(scope)[0] != expected:
                return {'state': 'disconnected'}
            attempt = self.pending.pop(scope, None)
            with self.db() as db:
                db.execute('DELETE FROM connections WHERE scope=?', (scope,))
        if attempt:
            attempt['login'].close()
            worker = attempt.get('worker')
            if worker and worker is not threading.current_thread():
                worker.join()
        return {'state': 'disconnected'}

    def poll_device(self, identity, target, attempt_id, guard):
        guard(target)
        scope = self.scope(identity, target)
        generation, body = self.read(scope)
        if generation != attempt_id:
            raise GitHubError('GITHUB_CONNECTION_CHANGED')
        with self.lock:
            attempt = self.pending.get(scope)
        if body.get('state') == 'pending' and not attempt:
            return {'state': 'reauthorize', 'reason': 'authorization_failed'}
        guard(target)
        return {'state': body.get('state', 'disconnected'), 'retry_after': 2, 'reason': body.get('reason')}

    def usable_connection(self, identity, target, guard):
        guard(target)
        scope = self.scope(identity, target)
        # Keep account credential use serialized; validate identity with live GitHub responses.
        with portalocker.Lock(str(self.root / (scope + '.lock')), timeout=1):
            generation, body = self.read(scope)
            if body.get('state') != 'connected':
                raise GitHubError('GITHUB_REAUTHORIZE')
            login = self.login_factory(self.executable, self.root / ('gh-tmp-' + secrets.token_hex(16)))
            try:
                login.restore(body['credentials'])
                token = login.run(['auth', 'token', '--hostname', 'github.com']).strip()
                if not token or any(ch.isspace() for ch in token):
                    raise GitHubError('GITHUB_REAUTHORIZE')
                with self.network_slot():
                    user = self.request('GET', '/user', token=token)
                if user.get('id') != body['account_id']:
                    raise GitHubError('GITHUB_ACCOUNT_CHANGED')
                guard(target)
                self.write(scope, generation, {**body, 'credentials': login.credentials()})
                return generation, {**body, 'access_token': token}
            except GitHubError as error:
                if str(error) not in {'GITHUB_ACCESS_DENIED', 'GITHUB_ACCOUNT_CHANGED', 'GITHUB_REAUTHORIZE'}:
                    raise
                self.write(scope, generation, {'state': 'reauthorize'})
                raise GitHubError('GITHUB_REAUTHORIZE') from None
            except (ValueError, KeyError):
                self.write(scope, generation, {'state': 'reauthorize'})
                raise GitHubError('GITHUB_REAUTHORIZE') from None
            finally:
                login.close()

    def status(self, identity, target, guard=None):
        scope = self.scope(identity, target)
        _, body = self.read(scope)
        if guard:
            guard(target)
            if body.get('state') == 'connected':
                try:
                    _, body = self.usable_connection(identity, target, guard)
                except GitHubError as error:
                    if str(error) != 'GITHUB_REAUTHORIZE':
                        raise
                    body = {'state': 'reauthorize'}
        with self.lock:
            attempt = self.pending.get(scope)
        device = self._device(attempt) if attempt and attempt['login'].code else None
        return {'configured': bool(self.executable), 'state': body.get('state', 'disconnected'),
                'login': body.get('login', ''), 'authorization_mode': 'gh', 'device': device,
                'can_import': False, 'reason': body.get('reason')}

    def _repository(self, body, params):
        if positive_id(params.get('account_id')) != body['account_id']:
            raise GitHubError('GITHUB_ACCOUNT_CHANGED')
        repository = positive_id(params.get('repository_id'))
        row = self.request('GET', f'/repositories/{repository}', token=body['access_token'])
        if row.get('id') != repository or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', row.get('full_name', '')):
            raise GitHubError('GITHUB_INVALID_REPOSITORY')
        return row

    def resolve(self, identity, target, params, guard):
        generation, body = self.usable_connection(identity, target, guard)
        with self.network_slot():
            selected = self._repository(body, params)
            branch = params.get('branch') or selected.get('default_branch')
            if not isinstance(branch, str) or not 1 <= len(branch) <= 250 or any(ord(c) < 32 for c in branch):
                raise GitHubError('GITHUB_INVALID_BRANCH')
            data = self.request('GET', f'/repos/{selected["full_name"]}/branches/{quote(branch, safe="")}', token=body['access_token'])
            commit = data.get('commit', {}).get('sha', '')
            if not re.fullmatch(r'[a-f0-9]{40}', commit):
                raise GitHubError('GITHUB_INVALID_COMMIT')
        guard(target)
        if self.read(self.scope(identity, target))[0] != generation:
            raise GitHubError('GITHUB_CONNECTION_CHANGED')
        return {'repository_id': selected['id'], 'account_id': body['account_id'],
                'full_name': selected['full_name'], 'branch': {'name': branch, 'commit': commit}}

    def catalog(self, identity, target, action, params, guard):
        generation, body = self.usable_connection(identity, target, guard)
        page = params.get('page', 1)
        if type(page) is not int or not 1 <= page <= 1000:
            raise GitHubError('GITHUB_INVALID_PAGE')
        with self.network_slot():
            if action == 'accounts':
                rows = [{'id': body['account_id'], 'account': body['login']}]
                items = rows
            elif action == 'repositories':
                if positive_id(params.get('account_id')) != body['account_id']:
                    raise GitHubError('GITHUB_ACCOUNT_CHANGED')
                rows = self.request('GET', f'/user/repos?affiliation=owner,collaborator,organization_member&sort=updated&per_page=30&page={page}', token=body['access_token'])
                items = [{'id': positive_id(row['id']), 'full_name': row['full_name'],
                          'default_branch': row.get('default_branch', ''), 'private': bool(row.get('private'))} for row in rows]
            elif action == 'branches':
                selected = self._repository(body, params)
                ref_page = params.get('ref_page', 1)
                if type(ref_page) is not int or not 1 <= ref_page <= 1000:
                    raise GitHubError('GITHUB_INVALID_PAGE')
                rows = self.request('GET', f'/repos/{selected["full_name"]}/branches?per_page=30&page={ref_page}', token=body['access_token'])
                items = [{'name': row['name'], 'commit': row['commit']['sha']} for row in rows]
            else:
                raise GitHubError('GITHUB_INVALID_ACTION')
        guard(target)
        if self.read(self.scope(identity, target))[0] != generation:
            raise GitHubError('GITHUB_CONNECTION_CHANGED')
        return {'items': items, 'has_more': len(rows) == 30}

    def close(self):
        with self.lock:
            self.closed = True
            attempts = list(self.pending.values())
            self.pending.clear()
        for attempt in attempts:
            attempt['login'].close()
            worker = attempt.get('worker')
            if worker and worker is not threading.current_thread():
                worker.join()
        self.lease.release()
