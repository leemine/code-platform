"""GitHub workspace preparation on the existing authenticated account route."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import re
import stat
from functools import partial

from gateway.auth.account_authenticator import current_account
from gateway.services.project_identity import ProjectPrincipal
from gateway.services.project_github import GitHubConnections, GitHubError, METHODS
from gateway.services.project_preparation import Preparations
from gateway.services.project_gitcode import GitCodeConnections, METHODS as GITCODE_METHODS
from gateway.routing.e2a_proxy import fetch_agent_unary
from jiuwenswarm.common.schema.message import ReqMethod

ENVIRONMENT_METHODS = frozenset({'project.environment.prepare', 'project.environment.status', 'project.environment.list'})


class ProjectEnvironments:
    def __init__(self, channel, client):
        self.channel, self.client = channel, client
        from gateway.auth.session_store import auth_dir
        config = {'root': str(auth_dir() / 'project-github-gh')}
        self.project_github = None
        self.preparations = None
        self.project_gitcode = None
        self.gitcode_preparations = None
        self.gitcode_root = auth_dir() / 'project-gitcode'
        path = os.environ.get('JIUWENSWARM_PROJECT_GITHUB_CONFIG')
        if path:
            config_path = Path(path)
            info = config_path.lstat()
            if not stat.S_ISREG(info.st_mode) or (os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
                raise ValueError('GITHUB_PRIVATE_CONFIGURATION_REQUIRED')
            config = json.loads(config_path.read_text())
            if set(config) - {'root', 'executable'}:
                raise ValueError('GITHUB_CLI_CONFIGURATION_REQUIRED')
        self.project_github = GitHubConnections(config['root'], config)
        self.preparations = Preparations(self, self.project_github)

    @staticmethod
    def actor():
        principal = current_account()
        if principal is None:
            raise PermissionError('PROJECT_ACCOUNT_REQUIRED')
        wrapped = ProjectPrincipal(principal)
        return wrapped, wrapped.identity()

    def project_target(self, identity, target, capability):
        if target != 'cloud' or capability not in {'project_read_version', 'project_import_version'}:
            raise PermissionError('PROJECT_TARGET_DENIED')
        principal = current_account()
        if principal is None or (principal.authority, principal.user_id) != (identity.authority, identity.actor_id):
            raise PermissionError('PROJECT_ACCOUNT_CHANGED')

    async def call(self, method, params):
        _, identity = await asyncio.to_thread(self.actor)
        result = await fetch_agent_unary(agent_client=self.client, req_method=ReqMethod(method),
            params=params, session_id=None, user_id=identity.actor_id, channel_id=self.channel.channel_id,
            label='project-environment', timeout_seconds=150)
        _, current = await asyncio.to_thread(self.actor)
        if current != identity:
            raise PermissionError('PROJECT_ACCOUNT_CHANGED')
        return result

    async def node_request(self, target, data):
        _, identity = await asyncio.to_thread(self.actor)
        await asyncio.to_thread(self.project_target, identity, target, 'project_import_version')
        if set(data) != {'method', 'params'} or data['method'] != '_project_import':
            raise ValueError('PROJECT_PREPARE_INVALID_FIELDS')
        ok, payload = await self.call('project.import', data['params'])
        return {'ok': ok, 'payload': payload}

    def repository_service(self, provider):
        if provider == 'github':
            return self.project_github, self.preparations
        if provider != 'gitcode':
            raise ValueError('PROJECT_PREPARE_INVALID_PROVIDER')
        if self.project_gitcode is None:
            self.project_gitcode = GitCodeConnections(self.gitcode_root)
            self.gitcode_preparations = Preparations(self, self.project_gitcode)
        return self.project_gitcode, self.gitcode_preparations

    async def capable(self, provider='github'):
        ok, value = await self.call('project.import', {'action': 'capabilities'})
        return ok and value.get('project_import_version') == 1 and (provider == 'github' or provider in value.get('repository_providers', []))

    async def repository_request(self, principal, identity, method, params):
        provider, action = method.split('.')[1:]
        service, _ = self.repository_service(provider)
        allowed = {'execution_target'} | {
            'begin': {'draft_id'}, 'poll': {'attempt_id'}, 'accounts': {'page'},
            'repositories': {'account_id', 'page'},
            'branches': {'account_id', 'repository_id', 'page', 'ref_page'},
            'resolve': {'account_id', 'repository_id', 'branch'},
        }.get(action, set())
        if provider == 'gitcode':
            if action == 'connect':
                allowed |= {'access_token'}
            if action in {'branches', 'resolve'}:
                allowed |= {'full_name'}
        if set(params) - allowed:
            raise GitHubError('GITHUB_INVALID_FIELDS')
        target = params['execution_target']
        def guard(selected):
            if principal.identity() != identity:
                raise PermissionError('PROJECT_ACCOUNT_CHANGED')
            self.project_target(identity, selected, 'project_read_version')
        await asyncio.to_thread(guard, target)
        if service is None:
            if action == 'status':
                return {'execution_target': target, 'configured': False, 'state': 'unconfigured', 'can_import': False}
            raise GitHubError('GITHUB_NOT_CONFIGURED')
        if action == 'status':
            payload = await asyncio.to_thread(service.status, identity, target, guard)
            payload['can_import'] = bool(payload['configured']) and await self.capable(provider)
        elif action == 'connect':
            payload = await asyncio.to_thread(service.connect, identity, target, params.get('access_token'), guard)
        elif action == 'begin':
            payload = await asyncio.to_thread(service.begin, identity, target, params.get('draft_id'), guard)
        elif action == 'poll':
            payload = await asyncio.to_thread(service.poll_device, identity, target, params.get('attempt_id'), guard)
        elif action == 'resolve':
            payload = await asyncio.to_thread(service.resolve, identity, target, params, guard)
        elif action == 'disconnect':
            payload = await asyncio.to_thread(service.disconnect, identity, target)
        else:
            payload = await asyncio.to_thread(service.catalog, identity, target, action, params, guard)
        await asyncio.to_thread(guard, target)
        return {**payload, 'execution_target': target}

    async def handle(self, method, ws, req_id, params, session_id):
        try:
            if not isinstance(params, dict):
                raise ValueError('PROJECT_PREPARE_INVALID_FIELDS')
            params = {'execution_target': 'cloud', **params}
            principal, identity = await asyncio.to_thread(self.actor)
            await asyncio.to_thread(self.project_target, identity, params['execution_target'], 'project_read_version')
            if method in METHODS | GITCODE_METHODS:
                payload = await self.repository_request(principal, identity, method, params)
            elif method == 'project.environment.list':
                if set(params) != {'execution_target'}:
                    raise ValueError('PROJECT_PREPARE_INVALID_FIELDS')
                ok, value = await self.call('project.list', {'work_mode': 'code'})
                if not ok:
                    raise ConnectionError()
                payload = {'execution_target': 'cloud', 'projects': [p for p in value.get('projects', []) if p.get('repository_source')]}
            else:
                provider = params.pop('provider', 'github')
                _, preparations = self.repository_service(provider)
                if preparations is None:
                    raise GitHubError('GITHUB_NOT_CONFIGURED')
                if not await self.capable(provider):
                    raise ValueError('PROJECT_PREPARE_TARGET_UNSUPPORTED')
                payload = await preparations.request(principal, identity, params, query=method.endswith('.status'))
                if provider == 'gitcode':
                    payload['provider'] = provider
            await asyncio.to_thread(principal.identity)
            await self.channel.send_response(ws, req_id, ok=True, payload=payload)
        except Exception as exc:
            code = str(exc)
            if not re.fullmatch(r'(?:GITHUB|GITCODE|GIT|PROJECT_PREPARE)_[A-Z_]{1,80}', code):
                code = 'UNAUTHORIZED' if isinstance(exc, PermissionError) else 'PROJECT_PREPARE_UNAVAILABLE'
            await self.channel.send_response(ws, req_id, ok=False, error='Cloud project operation unavailable', code=code)

    async def close(self):
        for preparations in (self.preparations, self.gitcode_preparations):
            if preparations:
                await preparations.close()
        for service in (self.project_github, self.project_gitcode):
            if service:
                await asyncio.to_thread(service.close)

    def register(self):
        for method in METHODS | GITCODE_METHODS | ENVIRONMENT_METHODS:
            self.channel.register_method(method, partial(self.handle, method), local_only=True)
