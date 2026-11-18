"""Account-instance import receipts on the original AgentServer Control plane.

Gateway and Router authenticate every call. Receipts are scoped by routed user,
never credentials; only a verified new directory enters the original ProjectStore.
No Session, runtime warm-up, dependency account or model call is performed.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re

import portalocker
from jiuwenswarm.server.runtime.session import project_store
from .project_checkout import MAX_BUNDLE, materialize, source_snapshot, attach_source_branch, workspace_snapshot
from .project_git_safety import _configuration

def valid_source_account(source):
    value = source.get('account_id')
    if source.get('provider', 'github') == 'gitcode':
        return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is not None
    return type(value) is int and 0 < value < 2**53


CHUNK = 3 * 1024 * 1024


def persist(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    project_store._fsync_dir(path.parent)


def execute(params, user_id):
    if not isinstance(user_id, str) or not user_id:
        raise PermissionError('PROJECT_IMPORT_IDENTITY_REQUIRED')
    if params == {'action': 'capabilities'}:
        return {'project_import_version': 1, 'repository_providers': ['github', 'gitcode'], 'lfs_mode': 'deferred'}
    operation = params.get('operation_id')
    if not isinstance(operation, str) or not re.fullmatch(r'[a-f0-9]{32}', operation):
        raise ValueError('PROJECT_IMPORT_INVALID_OPERATION')
    action = params.get('action')
    scope = hashlib.sha256(json.dumps([user_id, operation]).encode()).hexdigest()
    private = project_store.get_agent_root_dir() / 'project-imports' / scope
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    if private.is_symlink() or private.resolve() != private:
        raise PermissionError('PROJECT_IMPORT_STORAGE_INVALID')
    path = private / 'operation.json'
    with portalocker.Lock(str(private / 'operation.lock'), timeout=1):
        record = json.loads(path.read_text()) if path.exists() else None
        if action == 'begin':
            if set(params) != {'action', 'operation_id', 'name', 'source', 'size', 'sha256', 'lfs_mode'} or params['lfs_mode'] != 'deferred':
                raise ValueError('PROJECT_IMPORT_INVALID_FIELDS')
            project_store.validate_project_dir_name(params['name'])
            source = params['source']
            if (not isinstance(source, dict) or set(source) - {'provider'} != {'repository_id', 'account_id', 'full_name', 'branch', 'commit'}
                    or source.get('provider', 'github') not in {'github', 'gitcode'}
                    or not valid_source_account(source)
                    or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', str(source['full_name']))
                    or not re.fullmatch(r'[a-f0-9]{40}', str(source['commit']))
                    or not isinstance(source['branch'], str) or not source['branch'] or source['branch'].startswith('-')
                    or type(source['repository_id']) is not int or not 0 < source['repository_id'] < 2**53
                    or type(params['size']) is not int or not 0 < params['size'] <= MAX_BUNDLE
                    or not re.fullmatch(r'[a-f0-9]{64}', str(params['sha256']))):
                raise ValueError('PROJECT_IMPORT_INVALID_SOURCE')
            intent = {k: params[k] for k in ('name', 'source', 'size', 'sha256')}
            if record and record['intent'] != intent:
                raise ValueError('PROJECT_IMPORT_CONFLICT')
            if not record:
                root = Path(project_store.resolve_default_project_dir(params['name'], 'code'))
                if root.exists() or root.is_symlink():
                    raise ValueError('PROJECT_IMPORT_DIRECTORY_EXISTS')
                for project in project_store.list_projects(include_hidden=True, cache_bust=True):
                    if project.name == params['name'] and project.work_mode == 'code':
                        raise ValueError('PROJECT_IMPORT_NAME_EXISTS')
                    if not project.project_dir:
                        continue
                    existing = Path(project.project_dir).resolve()
                    if existing == root or existing in root.parents or root in existing.parents:
                        raise PermissionError('PROJECT_IMPORT_WORKSPACE_OVERLAP')
                root.parent.mkdir(parents=True, exist_ok=True)
                if root.parent.resolve() != root.parent:
                    raise ValueError('PROJECT_IMPORT_ROOT_INVALID')
                record = {'intent': intent, 'root': str(root), 'state': 'reserved', 'offset': 0}
                persist(path, record)
                root.mkdir(mode=0o700)
                st = root.stat()
                record.update(inode=[st.st_dev, st.st_ino], state='receiving')
                persist(path, record)
        elif action not in {'chunk', 'verify', 'publish', 'status'}:
            raise ValueError('PROJECT_IMPORT_INVALID_ACTION')
        elif action in {'status', 'verify', 'publish'} and set(params) != {'action', 'operation_id'}:
            raise ValueError('PROJECT_IMPORT_INVALID_FIELDS')
        if not record:
            raise ValueError('PROJECT_IMPORT_NOT_FOUND')
        root = Path(record['root'])
        st = root.stat()
        if root.is_symlink() or root.resolve() != root or record.get('inode') != [st.st_dev, st.st_ino]:
            raise ValueError('PROJECT_IMPORT_ROOT_CHANGED')
        bundle = private / 'source.bundle'
        if bundle.is_symlink() or path.is_symlink():
            raise ValueError('PROJECT_IMPORT_STORAGE_INVALID')
        if action == 'chunk':
            if set(params) != {'action', 'operation_id', 'offset', 'data'}:
                raise ValueError('PROJECT_IMPORT_INVALID_FIELDS')
            raw = base64.b64decode(params['data'], validate=True)
            offset = params['offset']
            if type(offset) is not int or not raw or len(raw) > CHUNK or offset < 0 or offset + len(raw) > record['intent']['size']:
                raise ValueError('PROJECT_IMPORT_INVALID_CHUNK')
            if offset < record['offset']:
                with bundle.open('rb') as handle:
                    handle.seek(offset)
                    if offset + len(raw) > record['offset'] or handle.read(len(raw)) != raw:
                        raise ValueError('PROJECT_IMPORT_CHUNK_CONFLICT')
            elif offset == record['offset'] and record['state'] == 'receiving':
                with bundle.open('r+b' if bundle.exists() else 'w+b') as handle:
                    handle.seek(offset)
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                record['offset'] += len(raw)
                persist(path, record)
            else:
                raise ValueError('PROJECT_IMPORT_OFFSET_CONFLICT')
        if action == 'verify' and record['state'] != 'ready':
            if record['offset'] != record['intent']['size'] or hashlib.sha256(bundle.read_bytes()).hexdigest() != record['intent']['sha256']:
                raise ValueError('PROJECT_IMPORT_BUNDLE_MISMATCH')
            _configuration(root)
            if record['state'] not in {'verified', 'registering'}:
                record['state'] = 'verifying'
                persist(path, record)
                record['facts'] = materialize(root, bundle, record['intent']['source']['commit'], allow_lfs=True, defer_lfs=True)
                record['state'] = 'verified'
                persist(path, record)
        if action == 'publish' and record['state'] != 'ready':
            if record['state'] not in {'verified', 'registering'}:
                raise ValueError('PROJECT_IMPORT_VERIFICATION_REQUIRED')
            source = {**record['intent']['source'], 'operation_id': operation,
                      'root_inode': record['inode'], 'version': 1,
                      'lfs': record['facts'].get('lfs', []), 'lfs_mode': 'deferred'}
            from types import SimpleNamespace
            candidate = SimpleNamespace(project_dir=str(root), repository_source=source)
            source_snapshot(candidate)
            attach_source_branch(candidate)
            project = project_store.get_project_by_dir_and_mode(str(root), 'code', cache_bust=True)
            if project:
                if project.hidden or project.repository_source != source:
                    raise ValueError('PROJECT_IMPORT_REGISTRY_CONFLICT')
            else:
                record['state'] = 'registering'
                persist(path, record)
                project, _ = project_store.create_project_checked(record['intent']['name'], str(root), 'code', repository_source=source)
            record.update(state='ready', project_id=project.project_id)
            persist(path, record)
        result = {'operation_id': operation, 'state': record['state'], 'offset': record['offset']}
        if record['state'] == 'ready':
            project = project_store.get_project_by_id(record['project_id'], cache_bust=True)
            if not project or project.hidden or project.repository_source.get('operation_id') != operation:
                raise PermissionError('PROJECT_IMPORT_PROJECT_UNAVAILABLE')
            from jiuwenswarm.server.runtime.session.lifecycle import guard
            guard(project_id=project.project_id)
            workspace_snapshot(project)
            from .store.project_queries import project_info_payload
            result.update(project=project_info_payload(project), checks={'workspace': 'ready', 'source': 'ready',
                          'dependencies': 'unknown', 'execution_authorized': False})
        return result
