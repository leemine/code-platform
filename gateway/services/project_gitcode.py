"""GitCode personal-token connection and read-only repository discovery.

The public token-creation page belongs to GitCode. Tokens are accepted only by
this authenticated broker and are never forwarded to a project/runtime.
"""
from __future__ import annotations
import re
import secrets
from urllib.parse import quote
from jiuwenswarm.common.auth.session_store import encrypt_json
from gateway.services.project_connections import RepositoryConnections, RepositoryError

METHODS = frozenset('project.gitcode.' + name for name in (
    'status', 'connect', 'disconnect', 'accounts', 'repositories', 'branches', 'resolve'))
TOKEN_URL = 'https://gitcode.com/setting/token-classic/create'


class GitCodeError(RepositoryError):
    pass


def account_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise GitCodeError('GITCODE_INVALID_ACCOUNT')
    return value


def repository_id(value):
    if type(value) is not int or not 0 < value < 2**53:
        raise GitCodeError('GITCODE_INVALID_REPOSITORY')
    return value


def repository_name(value):
    if (not isinstance(value, str) or len(value) > 250
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value)
            or any(part in {'.', '..'} for part in value.split('/'))):
        raise GitCodeError('GITCODE_INVALID_REPOSITORY')
    return value


class GitCodeConnections(RepositoryConnections):
    provider = 'gitcode'
    fingerprint = 'gitcode-pat-v1'
    api_origin = 'https://api.gitcode.com'
    error_type = GitCodeError

    def connect(self, identity, target, token, guard):
        if (not isinstance(token, str) or not 1 <= len(token) <= 4096
                or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise GitCodeError('GITCODE_INVALID_TOKEN')
        guard(target)
        scope, generation = self.scope(identity, target), secrets.token_hex(16)
        with self.network_slot():
            with self.lock:
                if self.closed:
                    raise GitCodeError('GITCODE_UNAVAILABLE')
                previous_generation, previous = self.read(scope)
                if previous.get('state') == 'connecting':
                    raise GitCodeError('GITCODE_BUSY')
                with self.db() as db:
                    db.execute('INSERT OR REPLACE INTO connections VALUES (?,?,?)',
                               (scope, generation, encrypt_json({'state': 'connecting'})))
            try:
                user = self.request('GET', '/api/v5/user', token=token)
                identifier = account_id(user.get('id'))
                login = user.get('login')
                if not isinstance(login, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', login):
                    raise GitCodeError('GITCODE_INVALID_RESPONSE')
                guard(target)
                with self.lock:
                    if self.closed:
                        raise GitCodeError('GITCODE_UNAVAILABLE')
                    self.write(scope, generation, {'state': 'connected', 'account_id': identifier,
                        'login': login, 'access_token': token})
            except Exception:
                with self.lock, self.db() as db:
                    if previous_generation:
                        db.execute('UPDATE connections SET generation=?,body=? WHERE scope=? AND generation=?',
                            (previous_generation, encrypt_json(previous), scope, generation))
                    else:
                        db.execute('DELETE FROM connections WHERE scope=? AND generation=?', (scope, generation))
                raise
        return {'state': 'connected', 'login': login}

    def disconnect(self, identity, target):
        scope = self.scope(identity, target)
        with self.lock, self.db() as db:
            db.execute('DELETE FROM connections WHERE scope=?', (scope,))
        return {'state': 'disconnected'}

    def usable_connection(self, identity, target, guard):
        guard(target)
        scope = self.scope(identity, target)
        generation, body = self.read(scope)
        if body.get('state') != 'connected':
            raise GitCodeError('GITCODE_REAUTHORIZE')
        try:
            with self.network_slot():
                user = self.request('GET', '/api/v5/user', token=body['access_token'])
            if account_id(user.get('id')) != body['account_id']:
                raise GitCodeError('GITCODE_ACCOUNT_CHANGED')
            guard(target)
            if self.closed or self.read(scope)[0] != generation:
                raise GitCodeError('GITCODE_CONNECTION_CHANGED')
            return generation, body
        except GitCodeError as error:
            if str(error) in {'GITCODE_ACCESS_DENIED', 'GITCODE_ACCOUNT_CHANGED'}:
                self.write(scope, generation, {'state': 'reauthorize'})
                raise GitCodeError('GITCODE_REAUTHORIZE') from None
            raise

    def status(self, identity, target, guard):
        guard(target)
        _, body = self.read(self.scope(identity, target))
        if body.get('state') == 'connected':
            try:
                _, body = self.usable_connection(identity, target, guard)
            except GitCodeError as error:
                if str(error) != 'GITCODE_REAUTHORIZE':
                    raise
                body = {'state': 'reauthorize'}
        return {'configured': True, 'state': body.get('state', 'disconnected') if body.get('state') != 'connecting' else 'disconnected',
                'login': body.get('login', ''), 'authorization_mode': 'token', 'can_import': False}

    def _repository(self, body, params):
        if account_id(params.get('account_id')) != body['account_id']:
            raise GitCodeError('GITCODE_ACCOUNT_CHANGED')
        identifier = repository_id(params.get('repository_id'))
        name = repository_name(params.get('full_name'))
        row = self.request('GET', '/api/v5/repos/' + name, token=body['access_token'])
        if row.get('id') != identifier or repository_name(row.get('full_name')) != name:
            raise GitCodeError('GITCODE_INVALID_REPOSITORY')
        return row

    def _delivered(self, identity, target, generation, guard):
        guard(target)
        if self.read(self.scope(identity, target))[0] != generation:
            raise GitCodeError('GITCODE_CONNECTION_CHANGED')

    @staticmethod
    def _branch(row):
        name, commit = row.get('name'), row.get('commit', {}).get('id')
        if (not isinstance(name, str) or not 1 <= len(name) <= 250 or any(ord(c) < 32 for c in name)
                or not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}', commit)):
            raise GitCodeError('GITCODE_INVALID_BRANCH')
        return {'name': name, 'commit': commit}

    def resolve(self, identity, target, params, guard):
        generation, body = self.usable_connection(identity, target, guard)
        with self.network_slot():
            selected = self._repository(body, params)
            branch = params.get('branch') or selected.get('default_branch')
            if not isinstance(branch, str) or not 1 <= len(branch) <= 250 or any(ord(c) < 32 for c in branch):
                raise GitCodeError('GITCODE_INVALID_BRANCH')
            data = self.request('GET', '/api/v5/repos/' + selected['full_name'] + '/branches/' + quote(branch, safe=''), token=body['access_token'])
            resolved = self._branch(data)
            if resolved['name'] != branch:
                raise GitCodeError('GITCODE_INVALID_BRANCH')
        self._delivered(identity, target, generation, guard)
        return {'repository_id': selected['id'], 'account_id': body['account_id'],
                'full_name': selected['full_name'], 'branch': resolved, 'provider': 'gitcode'}

    def catalog(self, identity, target, action, params, guard):
        generation, body = self.usable_connection(identity, target, guard)
        page = params.get('ref_page' if action == 'branches' else 'page', 1)
        if type(page) is not int or not 1 <= page <= 1000:
            raise GitCodeError('GITCODE_INVALID_PAGE')
        with self.network_slot():
            if action == 'accounts':
                rows = items = [{'id': body['account_id'], 'account': body['login']}]
            elif action == 'repositories':
                if account_id(params.get('account_id')) != body['account_id']:
                    raise GitCodeError('GITCODE_ACCOUNT_CHANGED')
                rows = self.request('GET', f'/api/v5/user/repos?sort=updated&per_page=30&page={page}&repo_type=code', token=body['access_token'])
                items = [{'id': repository_id(row['id']), 'full_name': repository_name(row['full_name']),
                          'default_branch': row.get('default_branch', ''), 'private': bool(row.get('private'))} for row in rows]
            elif action == 'branches':
                selected = self._repository(body, params)
                rows = self.request('GET', f'/api/v5/repos/{selected["full_name"]}/branches?per_page=30&page={page}', token=body['access_token'])
                items = [self._branch(row) for row in rows]
            else:
                raise GitCodeError('GITCODE_INVALID_ACTION')
        self._delivered(identity, target, generation, guard)
        return {'items': items, 'has_more': len(rows) == 30}

    def close(self):
        with self.lock:
            self.closed = True
            self.lease.release()
