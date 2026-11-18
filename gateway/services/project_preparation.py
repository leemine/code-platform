"""GitHub preparation coordinator on the existing managed-node transport.

The target owns ProjectStore/ACL and checkout receipts; this durable broker
record only pins remote selection and tracks delivery. It never creates a Turn.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import re
import secrets
import time
import threading

from jiuwenswarm.server.control.project_checkout import make_bundle, GitCommandError
from jiuwenswarm.server.control.project_import import CHUNK
from jiuwenswarm.server.control.project_lfs import MissingObjects


class Preparations:
    def __init__(self, gateway, service, *, lfs_mode="deferred"):
        if lfs_mode not in {"deferred", "full"}:
            raise ValueError("PROJECT_PREPARE_INVALID_LFS_MODE")
        self.lfs_mode = lfs_mode
        self.gateway, self.service = gateway, service
        self.tasks = {}
        self.closing = threading.Event()
        with service.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS preparations (scope TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(scope,id))')

    def read(self, scope, operation):
        with self.service.db() as db:
            row = db.execute('SELECT body FROM preparations WHERE scope=? AND id=?', (scope, operation)).fetchone()
        return json.loads(row['body']) if row else None

    def save(self, scope, operation, body):
        with self.service.db() as db:
            db.execute('INSERT OR REPLACE INTO preparations VALUES (?,?,?)', (scope, operation, json.dumps(body)))

    async def request(self, principal, identity, params, query=False):
        if self.closing.is_set():
            raise ValueError('PROJECT_PREPARE_UNAVAILABLE')
        target = params.get('execution_target')
        operation = params.get('operation_id')
        if not isinstance(operation, str) or not re.fullmatch(r'[a-f0-9]{32}', operation):
            raise ValueError('PROJECT_PREPARE_INVALID_OPERATION')
        def guard(selected):
            if principal.identity() != identity:
                raise PermissionError('PROJECT_PREPARE_IDENTITY_CHANGED')
            self.gateway.project_target(identity, selected, 'project_import_version')
        await asyncio.to_thread(guard, target)
        if self.closing.is_set():
            raise ValueError('PROJECT_PREPARE_UNAVAILABLE')
        scope = self.service.scope(identity, target)
        key = (scope, operation)
        body = self.read(*key)
        if query:
            if set(params) != {'execution_target', 'operation_id'} or body is None:
                raise ValueError('PROJECT_PREPARE_NOT_FOUND')
        else:
            fields = {'execution_target', 'operation_id', 'name', 'account_id', 'repository_id', 'branch'}
            if self.service.provider == 'gitcode':
                fields.add('full_name')
            if set(params) != fields:
                raise ValueError('PROJECT_PREPARE_INVALID_FIELDS')
            from jiuwenswarm.server.runtime.session.project_store import validate_project_dir_name
            validate_project_dir_name(params["name"])
            intent = {k: params[k] for k in fields - {'execution_target', 'operation_id'}}
            if body and body['intent'] != intent:
                raise ValueError('PROJECT_PREPARE_CONFLICT')
            if body is None:
                if len(self.tasks) >= 2:
                    raise ValueError('PROJECT_PREPARE_BUSY')
                body = {'intent': intent, 'state': 'accepted'}
                self.save(*key, body)
            if key not in self.tasks and body['state'] != 'ready':
                if len(self.tasks) >= 2:
                    raise ValueError('PROJECT_PREPARE_BUSY')
                body['state'] = 'accepted'
                body.pop('error', None)
                body.pop('missing_lfs_files', None)
                body.pop('diagnostic', None)
                self.save(*key, body)
                task = asyncio.create_task(self.run(identity, target, operation, scope, guard))
                self.tasks[key] = task
                task.add_done_callback(lambda _: self.tasks.pop(key, None))
        if body['state'] == 'ready':
            # Receipt is not a durable access grant. Recheck target project ACL.
            current = await self.gateway.node_request(target, {'method': '_project_import',
                'params': {'action': 'status', 'operation_id': operation}})
            await asyncio.to_thread(guard, target)
            if not current.get('ok') or current.get('payload', {}).get('state') != 'ready':
                raise ValueError('PROJECT_PREPARE_RESULT_CHANGED')
            return {**current['payload'], 'execution_target': target, 'operation_id': operation,
                    'selection': body['intent'], 'download': body.get('download')}
        state = body['state']
        if query and key not in self.tasks and state not in ('failed', 'ready'):
            state = 'interrupted'
        return {'execution_target': target, 'operation_id': operation, 'state': state,
                'error': body.get('error'), 'diagnostic': body.get('diagnostic'),
                'download': body.get('download'),
                'missing_lfs_files': body.get('missing_lfs_files'), 'source': body.get('source'), 'selection': body['intent']}

    async def run(self, identity, target, operation, scope, guard):
        body = self.read(scope, operation)
        stopped = threading.Event()
        authority = guard
        def guard(selected):
            if stopped.is_set() or self.closing.is_set():
                raise ValueError('PROJECT_PREPARE_INTERRUPTED')
            authority(selected)
        async def blocking(function, *args, **kwargs):
            # Cancelling to_thread alone abandons its live process and database
            # writes. Keep ownership until the worker confirms that it exited.
            worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                stopped.set()
                try:
                    await asyncio.shield(worker)
                except Exception:
                    pass
                raise
        def save(state):
            body['state'] = state
            body.pop('error', None)
            body.pop('missing_lfs_files', None)
            body.pop('diagnostic', None)
            self.save(scope, operation, body)
        async def target_call(params):
            await blocking(guard, target)
            result = await self.gateway.node_request(target, {'method': '_project_import', 'params': {'operation_id': operation, **params}})
            await blocking(guard, target)
            if not result.get('ok'):
                code = result.get('payload', {}).get('code')
                if code in {'GIT_LFS_NOT_SUPPORTED', 'GIT_LFS_UNAVAILABLE', 'GIT_LFS_OBJECT_INCOMPLETE', 'GIT_LFS_HASH_MISMATCH', 'GIT_LFS_STORAGE_INVALID', 'GIT_LFS_SIZE_LIMIT', 'GIT_LFS_INVALID_POINTER', 'GIT_LFS_UNSUPPORTED_EMPTY_POINTER', 'GIT_LFS_OBJECT_UNAVAILABLE'}:
                    raise ValueError(code)
                raise ValueError('PROJECT_PREPARE_TARGET_REJECTED')
            return result['payload']
        scratch = None
        try:
            save('resolving')
            intent = body['intent']
            resolved = await blocking(self.service.resolve, identity, target, intent, guard)
            fresh = {k: resolved[k] for k in ('repository_id', 'account_id', 'full_name')}
            if self.service.provider == 'gitcode':
                fresh['provider'] = 'gitcode'
            fresh.update(branch=resolved['branch']['name'], commit=resolved['branch']['commit'])
            if 'source' not in body:
                body['source'] = fresh
            elif any(body['source'][k] != fresh[k] for k in ('repository_id', 'account_id', 'full_name')):
                raise ValueError('PROJECT_PREPARE_SOURCE_CHANGED')
            # Same operation always fetches its original commit, even if branch moves.
            save('fetching')
            generation, credential = await blocking(self.service.usable_connection, identity, target, guard)
            async def revalidate_source():
                current = await blocking(self.service.resolve, identity, target, intent, guard)
                if any(body['source'][key] != current[key] for key in ('repository_id', 'account_id', 'full_name')):
                    raise ValueError('PROJECT_PREPARE_SOURCE_CHANGED')
                if self.service.read(scope)[0] != generation:
                    raise ValueError('PROJECT_PREPARE_CONNECTION_CHANGED')
            if body.get('bundle'):
                bundle = self.service.root / body['bundle'] / 'source.bundle'
                if not bundle.is_file() or bundle.is_symlink():
                    raise ValueError('PROJECT_PREPARE_BUNDLE_UNAVAILABLE')
            else:
                scratch = self.service.root / ('checkout-' + secrets.token_hex(16))
                def validate_download():
                    guard(target)
                    if self.service.read(scope)[0] != generation:
                        raise ValueError('PROJECT_PREPARE_CONNECTION_CHANGED')
                download_started = time.monotonic()
                def progress(value):
                    body['download'] = {**value, 'elapsed_ms': round((time.monotonic() - download_started) * 1000)}
                    body['download_attempts'] = [*body.get('download_attempts', []), body['download']][-8:]
                    self.save(scope, operation, body)
                cache = (self.service.root / 'repositories' / hashlib.sha256(scope.encode()).hexdigest()
                         if self.lfs_mode == 'deferred' else None)
                bundle = await blocking(make_bundle, scratch, body['source']['full_name'], body['source']['commit'], credential['access_token'],
                    cache_root=cache, repository_id=body['source']['repository_id'],
                    validate=validate_download, progress=progress, complete=True,
                    provider=self.service.provider, username=credential.get('login') if self.service.provider == 'gitcode' else 'x-access-token')
                body['bundle'] = scratch.name
                save('fetching')
            credential = None
            await blocking(guard, target)
            await revalidate_source()
            size = bundle.stat().st_size
            sha = await blocking(lambda: hashlib.sha256(bundle.read_bytes()).hexdigest())
            save('transferring')
            receipt = await target_call({'action': 'begin', 'name': intent['name'], 'source': body['source'], 'size': size, 'sha256': sha, 'lfs_mode': self.lfs_mode})
            if receipt['state'] != 'ready':
                with bundle.open('rb') as handle:
                    offset = receipt['offset']
                    handle.seek(offset)
                    while True:
                        raw = handle.read(CHUNK)
                        if not raw:
                            break
                        receipt = await target_call({'action': 'chunk', 'offset': offset, 'data': base64.b64encode(raw).decode()})
                        offset = receipt['offset']
                save('verifying')
                await target_call({'action': 'verify'})
                # Slow checkout finishes before fresh account/GitHub authority
                # is checked for the separate project registration request.
                # Revalidate remote authority just before target publication.
                await revalidate_source()
                receipt = await target_call({'action': 'publish'})
                if receipt['state'] == 'assets':
                    if self.lfs_mode == 'deferred':
                        raise ValueError('PROJECT_PREPARE_POLICY_UNSUPPORTED')
                    from jiuwenswarm.server.control.project_lfs import fetch, object_path
                    save('fetching_assets')
                    _, credential = await blocking(self.service.usable_connection, identity, target, guard)
                    assets = await blocking(fetch, bundle.parent, body['source']['full_name'],
                                                     body['source']['commit'], credential['access_token'])
                    credential = None
                    expected = {item['oid']: item['size'] for item in assets}
                    save('transferring_assets')
                    for item in receipt['assets']:
                        if expected.get(item['oid']) != item['size']:
                            raise ValueError('GIT_LFS_MANIFEST_MISMATCH')
                        offset = item['offset']
                        with object_path(bundle.parent, item['oid'], bare=True).open('rb') as handle:
                            handle.seek(offset)
                            while True:
                                raw = handle.read(CHUNK)
                                if not raw:
                                    break
                                answer = await target_call({'action': 'asset.chunk', 'oid': item['oid'],
                                    'offset': offset, 'data': base64.b64encode(raw).decode()})
                                offset = answer['asset_offset']
                    save('verifying')
                    await revalidate_source()
                    receipt = await target_call({'action': 'publish'})
            if receipt['state'] != 'ready':
                raise ValueError('PROJECT_PREPARE_NOT_READY')
            body['result'] = receipt
            save('ready')
        except asyncio.CancelledError:
            body.update(state='interrupted', error='PROJECT_PREPARE_INTERRUPTED')
            self.save(scope, operation, body)
            raise
        except Exception as exc:
            # Never return raw Git/upstream/filesystem errors or local paths.
            code = str(exc)
            if not re.fullmatch(r'(?:GIT|GITHUB|GITCODE|PROJECT_PREPARE)_[A-Z_]+', code):
                code = 'PROJECT_PREPARE_FAILED'
            body.update(state='failed', error=code)
            if isinstance(exc, GitCommandError):
                body['diagnostic'] = exc.diagnostic
            if isinstance(exc, MissingObjects) and exc.missing_files > 0:
                body['missing_lfs_files'] = exc.missing_files
            self.save(scope, operation, body)
        # Retain the exact bundle for crash/transfer retry; task-owned cleanup
        # may remove it after delivery evidence is archived. Never regenerate a
        # different pack under an existing target receipt.

    async def close(self):
        self.closing.set()
        tasks = list(self.tasks.values())
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
