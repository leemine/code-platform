"""Preparation ownership at shutdown and connection publication boundaries."""
import asyncio
import os
import threading
from types import SimpleNamespace

import pytest

from gateway.services.project_environments import ProjectEnvironments
from tests.unit_tests.cloud_workspace.test_project_environments import account, close_brokers
from tests.unit_tests.cloud_workspace.test_project_import import source


def prepare_service(bridge, params, raw, monkeypatch):
    from gateway.services import project_preparation as coordinator
    service = bridge.project_github
    generation = ['one']
    service.resolve = lambda *args: {**params['source'], 'branch': {
        'name': 'main', 'commit': params['source']['commit']}}
    service.usable_connection = lambda *args: (generation[0], {'access_token': 'synthetic'})
    service.read = lambda scope: (generation[0], {})

    def bundle(root, *args, **kwargs):
        kwargs['validate']()
        root.mkdir(mode=0o700)
        path = root / 'source.bundle'
        path.write_bytes(raw)
        return path

    monkeypatch.setattr(coordinator, 'make_bundle', bundle)
    return generation


@pytest.mark.asyncio
async def test_shutdown_during_admission_cannot_start_a_late_preparation(account):
    bridge = ProjectEnvironments(SimpleNamespace(channel_id='web'), object())
    principal, identity = bridge.actor()
    entered, release = threading.Event(), threading.Event()

    def check_identity():
        entered.set()
        assert release.wait(3)
        return identity

    principal.identity = check_identity
    request = asyncio.create_task(bridge.preparations.request(principal, identity, {
        'execution_target': 'cloud', 'operation_id': 'd' * 32, 'name': 'late',
        'account_id': 2, 'repository_id': 1, 'branch': 'main'}))
    try:
        async with asyncio.timeout(2):
            while not entered.is_set():
                await asyncio.sleep(.01)
        await bridge.close()
        release.set()
        with pytest.raises(ValueError, match='UNAVAILABLE'):
            await request
        assert bridge.preparations.tasks == {}
        assert bridge.preparations.read(bridge.project_github.scope(identity, 'cloud'), 'd' * 32) is None
    finally:
        release.set()
        await asyncio.gather(request, return_exceptions=True)
        await bridge.close()


@pytest.mark.asyncio
async def test_connection_replacement_after_checkout_cannot_publish(source, account, monkeypatch):
    from jiuwenswarm.server.control import project_import
    from jiuwenswarm.server.runtime.session import project_store
    params, raw, _ = source
    bridge = ProjectEnvironments(SimpleNamespace(channel_id='web'), object())
    generations = prepare_service(bridge, params, raw, monkeypatch)
    calls = []

    async def target(target, request):
        action = request['params']['action']
        calls.append(action)
        value = project_import.execute(request['params'], 'alice')
        if action == 'verify':
            generations[0] = 'replacement'
        return {'ok': True, 'payload': value}

    bridge.node_request = target
    principal, identity = bridge.actor()
    intent = {'execution_target': 'cloud', 'operation_id': params['operation_id'],
              'name': params['name'], 'account_id': 2, 'repository_id': 1, 'branch': 'main'}
    try:
        await bridge.preparations.request(principal, identity, intent)
        await asyncio.gather(*list(bridge.preparations.tasks.values()))
        assert 'verify' in calls and 'publish' not in calls
        assert project_store.list_projects(cache_bust=True) == []
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_shutdown_reaps_owned_git_before_releasing_broker(account, tmp_path, monkeypatch):
    from gateway.services import project_preparation as coordinator
    from jiuwenswarm.server.control import project_checkout
    bridge = ProjectEnvironments(SimpleNamespace(channel_id='web'), object())
    service = bridge.project_github
    pidfile = tmp_path / 'child.pid'
    executable = tmp_path / 'fake-git'
    executable.write_text('#!/bin/sh\necho $$ > ' + str(pidfile) + '\nexec /bin/sleep 30\n')
    executable.chmod(0o700)
    monkeypatch.setattr(project_checkout.shutil, 'which', lambda _: str(executable))
    running, exited = threading.Event(), threading.Event()
    service.resolve = lambda *args: {'account_id': 2, 'repository_id': 1, 'full_name': 'owner/repo',
                                   'branch': {'name': 'main', 'commit': 'a' * 40}}
    service.usable_connection = lambda *args: ('one', {'access_token': 'synthetic'})
    service.read = lambda scope: ('one', {})

    def download(root, *args, **kwargs):
        running.set()
        try:
            project_checkout.git(tmp_path, 'fetch', network=True, timeout_seconds=3,
                                 validate=kwargs['validate'])
        finally:
            exited.set()

    monkeypatch.setattr(coordinator, 'make_bundle', download)
    original_close = service.close
    released_after_exit = []

    def close():
        released_after_exit.append(exited.is_set())
        original_close()

    service.close = close
    principal, identity = bridge.actor()
    operation = 'b' * 32
    await bridge.preparations.request(principal, identity, {'execution_target': 'cloud',
        'operation_id': operation, 'name': 'example', 'account_id': 2,
        'repository_id': 1, 'branch': 'main'})
    try:
        async with asyncio.timeout(2):
            while not pidfile.exists():
                await asyncio.sleep(.01)
        await asyncio.wait_for(bridge.close(), timeout=4)
        assert running.is_set() and exited.is_set()
        assert released_after_exit == [True]
        with pytest.raises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)
        assert bridge.preparations.read(service.scope(identity, 'cloud'), operation)['state'] == 'interrupted'
        with pytest.raises(ValueError, match='UNAVAILABLE'):
            await bridge.preparations.request(principal, identity, {'execution_target': 'cloud',
                'operation_id': 'c' * 32, 'name': 'another', 'account_id': 2,
                'repository_id': 1, 'branch': 'main'})
    finally:
        await bridge.close()
        async with asyncio.timeout(4):
            while not exited.is_set():
                await asyncio.sleep(.01)
