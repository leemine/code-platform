"""Provider-only recovery regressions; no real model calls or user data."""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import json
import sys
import os
from pathlib import Path
from types import SimpleNamespace

if __name__ == '__main__' and getattr(sys, 'frozen', False):
    # The desktop's supported script entry lets us test its actual frozen
    # dependencies without replacing an installed application or Provider.
    sys.path.append(os.environ['PROVIDER_TEST_PACKAGES'])
    from jiuwenswarm.common.external_cli_runtime import activate_external_cli_runtime_paths
    activate_external_cli_runtime_paths()

import pytest


@pytest.fixture
def providers(monkeypatch, tmp_path):
    package = 'jiuwenswarm.server.runtime.agent_adapter.providers'
    parent = importlib.import_module(package)
    loaded = {}
    for leaf in ['session_recovery', 'codex', 'claude', 'opencode_service', 'opencode']:
        spec = importlib.util.spec_from_file_location(package + '.' + leaf, Path(__file__).with_name(leaf + '.py'))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        monkeypatch.setattr(parent, leaf, module, raising=False)
        loaded[leaf] = module
    from jiuwenswarm.common import utils
    from jiuwenswarm.server.runtime.session import session_history
    monkeypatch.setattr(utils, 'get_agent_sessions_dir', lambda: tmp_path / 'sessions')
    monkeypatch.setattr(session_history, 'read_session_history_records', lambda sid: [])
    return SimpleNamespace(**loaded)


@pytest.mark.parametrize('provider', ['codex', 'claude', 'opencode'])
def test_binding_roundtrip_rejects_mismatch_and_missing_data(providers, tmp_path, provider):
    recovery = providers.session_recovery
    root = tmp_path / 'sessions' / recovery.NAMESPACES[provider] / 'native'
    root.mkdir(parents=True)
    recovery.save(provider, '../untrusted-id', root=root, directory=str(tmp_path), native_id='native-id',
        model_revision='model', settings_revision='settings', permission='default')
    restored = recovery.load(provider, '../untrusted-id', str(tmp_path))
    assert restored['native_id'] == 'native-id'
    assert restored['root'] == str(root.resolve())
    with pytest.raises(ValueError, match='binding'):
        recovery.load(provider, '../untrusted-id', str(tmp_path / 'another'))
    root.rmdir()
    with pytest.raises(ValueError, match='binding'):
        recovery.load(provider, '../untrusted-id', str(tmp_path))


def test_corruption_does_not_become_a_new_session(providers, tmp_path):
    recovery = providers.session_recovery
    root = tmp_path / 'sessions/.codex-direct/native'
    root.mkdir(parents=True)
    recovery.save('codex', 'one', root=root, directory=str(tmp_path), native_id='id',
        model_revision='model', settings_revision='settings', permission='default')
    file = recovery._file('codex', 'one')
    file.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError, match='binding'):
        recovery.load('codex', 'one', str(tmp_path))


@pytest.mark.parametrize('provider', ['codex', 'claude'])
def test_adapter_release_and_recreate_preserves_binding(providers, tmp_path, provider):
    async def scenario():
        module = getattr(providers, provider)
        adapter_type = module.CodexAdapter if provider == 'codex' else module.ClaudeAdapter
        first = adapter_type()
        first._settings = {'enabled': True}
        first._permission_profile = 'full_access'
        await first.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(tmp_path))
        session = first._sessions['one']
        if provider == 'codex':
            session.thread_id = 'original-native'
        else:
            session.native_id = 'original-native'
            session.started = True
        session.model_revision = 'model'
        first._save_binding(session)
        await first.cleanup()
        assert session.root.is_dir()
        second = adapter_type()
        second._settings = {'enabled': True}
        await second.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(tmp_path))
        resumed = second._sessions['one']
        assert resumed.root == session.root
        assert resumed.desired_permission == 'full_access'
        assert resumed.model_revision == 'model'
        if provider == 'codex':
            assert resumed.thread_id == 'original-native'
        else:
            assert resumed.native_id == 'original-native' and resumed.started
        changed = adapter_type()
        changed._settings = {'enabled': True, 'new_model_policy': True}
        with pytest.raises(ValueError, match='configuration changed'):
            await changed.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(tmp_path))
    asyncio.run(scenario())


@pytest.mark.parametrize('wrong_thread', [False, True])
def test_codex_reconnect_uses_resume_not_start(providers, monkeypatch, tmp_path, wrong_thread):
    async def scenario():
        module = providers.codex
        from openai_codex import client as sdk
        calls = []
        class Client:
            def __init__(self, config, approval_handler):
                pass
            def start(self):
                pass
            def initialize(self):
                pass
            def thread_start(self, options):
                raise AssertionError('Recovery must not start another thread')
            def thread_resume(self, native_id, options):
                calls.append(native_id)
                return SimpleNamespace(thread=SimpleNamespace(id='another' if wrong_thread else native_id,
                    model_dump=lambda **kw: {'cwd': str(tmp_path), 'status': {'type': 'idle'}}), model_dump=lambda **kw: {
                    'approvalPolicy': options['approvalPolicy'], 'approvalsReviewer': 'user',
                    'sandbox': {'type': 'workspaceWrite'}})
            def close(self):
                pass
        monkeypatch.setattr(sdk, 'CodexClient', Client)
        monkeypatch.setattr(module, 'model_overrides', lambda model, settings: {})
        adapter = module.CodexAdapter()
        adapter._settings = {'enabled': True}
        model = SimpleNamespace(model_dump_json=lambda: 'model', client_options={}, api_key='fixture-key', model_name='fixture')
        await adapter.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(tmp_path))
        session = adapter._sessions['one']
        session.thread_id = 'native-one'
        session.model_revision = hashlib.sha256(b'model').hexdigest()
        if wrong_thread:
            with pytest.raises(RuntimeError, match='initialization failed'):
                await adapter._connect(session, model)
            assert session.client is None and session.thread_id == 'native-one'
            return
        await adapter._connect(session, model)
        assert calls == ['native-one']
        assert session.client is not None
    asyncio.run(scenario())


def test_claude_recreated_options_resume_original_session(providers, tmp_path):
    async def scenario():
        adapter = providers.claude.ClaudeAdapter()
        adapter._settings = {'enabled': True}
        await adapter.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(tmp_path))
        session = adapter._sessions['one']
        session.started = True
        adapter._save_binding(session)
        await adapter.cleanup()
        adapter._settings = {'enabled': True}
        await adapter.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(tmp_path))
        model = SimpleNamespace(api_base='https://example.invalid', api_key='fixture', model_name='fixture', client_options={})
        options = adapter._options(adapter._sessions['one'], model)
        assert options.resume == session.native_id and options.session_id is None
        assert options.env['CLAUDE_CONFIG_DIR'] == str(session.root / 'config')
    asyncio.run(scenario())


def test_opencode_recreated_service_uses_same_native_session(providers, monkeypatch, tmp_path):
    async def scenario():
        module = providers.opencode
        calls = []
        class Service:
            def __init__(self, executable, directory, *, root=None):
                self.root = root or tmp_path / 'sessions/.opencode/native'
                self.root.mkdir(parents=True, exist_ok=True)
                self.retain_data = False
            async def configure(self, equipment, *, permission_profile='default'):
                pass
            async def close(self):
                assert self.retain_data
        monkeypatch.setattr(providers.opencode_service, 'SessionService', Service)
        async def call(adapter, method, path, *, body=None, session=None):
            calls.append((method, path))
            if path == '/session/status':
                return {}
            return {'id': 'native-one', 'directory': str(tmp_path)}
        async def permissions(adapter, session):
            session.effective_permission = session.desired_permission
        monkeypatch.setattr(module.OpenCodeAdapter, '_call', call)
        monkeypatch.setattr(module.OpenCodeAdapter, '_apply_permissions', permissions)
        first = module.OpenCodeAdapter()
        first._configured = True
        first._executable = 'official-cli'
        first._directory = str(tmp_path)
        await first.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(tmp_path))
        root = first._sessions['one'].service.root
        await first.cleanup_session_adapter('one')
        second = module.OpenCodeAdapter()
        second._configured = True
        second._executable = 'official-cli'
        second._directory = str(tmp_path)
        await second.prepare_session(session_id='one', channel_id='web', mode='code', project_dir=str(tmp_path))
        assert second._sessions['one'].native_id == 'native-one'
        assert second._sessions['one'].service.root == root
        assert calls.count(('POST', '/session')) == 1
        assert ('DELETE', '/session/native-one') not in calls
    asyncio.run(scenario())


@pytest.mark.parametrize('provider', ['codex', 'claude', 'opencode'])
def test_legacy_history_without_binding_is_not_silently_replayed(providers, monkeypatch, tmp_path, provider):
    from jiuwenswarm.server.runtime.session import session_history
    monkeypatch.setattr(session_history, 'read_session_history_records', lambda sid: [{'role': 'assistant'}])
    async def scenario():
        types = {'codex': providers.codex.CodexAdapter, 'claude': providers.claude.ClaudeAdapter,
                 'opencode': providers.opencode.OpenCodeAdapter}
        adapter = types[provider]()
        adapter._settings = {'enabled': True}
        adapter._configured = True
        adapter._directory = str(tmp_path)
        with pytest.raises(ValueError, match='recovery binding'):
            await adapter.prepare_session(session_id='legacy', channel_id='web', mode='code', project_dir=str(tmp_path))
        assert not adapter._sessions
    asyncio.run(scenario())


@pytest.mark.parametrize('provider', ['opencode', 'codex', 'claude'])
def test_live_native_context_survives_adapter_restart(providers, tmp_path, provider):
    if provider not in os.environ.get('PROVIDER_RECOVERY_LIVE', '').split(','):
        pytest.skip('Explicit live Provider acceptance is disabled')
    from jiuwenswarm.common.config import get_config
    from jiuwenswarm.common.model_catalog import ModelCatalog
    from jiuwenswarm.common.schema.agent import AgentRequest
    from jiuwenswarm.common.schema.message import ReqMethod
    import uuid

    async def scenario():
        module = getattr(providers, provider)
        types = {'opencode': module.OpenCodeAdapter} if provider == 'opencode' else {
            'codex': module.CodexAdapter} if provider == 'codex' else {'claude': module.ClaudeAdapter}
        candidates = ModelCatalog().list_public_models()
        wanted = 'anthropic' if provider == 'claude' else 'openai'
        candidates = [entry for entry in candidates if entry['enabled'] and entry['provider'].lower() == wanted]
        preference = 'deepseek' if provider == 'opencode' else 'gpt' if provider == 'codex' else 'claude'
        candidates.sort(key=lambda entry: preference not in entry['model_name'].lower())
        explicit = json.loads(os.environ.get('PROVIDER_RECOVERY_MODEL_IDS', '{}')).get(provider)
        if explicit:
            candidates = [entry for entry in candidates if entry['model_id'] == explicit]
        if provider != 'opencode':
            compatible = []
            for entry in candidates:
                probe = AgentRequest(request_id='probe', channel_id='web', session_id='recovery-probe',
                    params={'model_selection': {'type': 'model', 'id': entry['model_id']}})
                try:
                    module.resolve_model(probe)
                    compatible.append(entry)
                except ValueError:
                    continue
            candidates = compatible
        if not candidates:
            pytest.skip('No compatible configured model is available')
        selection = {'type': 'model', 'id': candidates[0]['model_id']}
        marker = 'RECOVERY_' + uuid.uuid4().hex
        sid = 'recovery-' + uuid.uuid4().hex
        config = dict(get_config())
        config['permissions'] = dict(config.get('permissions') or {})
        config['run_permissions_enabled'] = False
        if provider == 'opencode':
            config['opencode'] = dict(config.get('opencode') or {})
            config['opencode'].pop('url', None)
        else:
            config[provider] = dict(module.config_snapshot(config)[provider])
            config[provider]['enabled'] = True
        async def turn(adapter, query):
            import warnings
            request = AgentRequest(request_id=uuid.uuid4().hex, channel_id='web', session_id=sid,
                req_method=ReqMethod.CHAT_SEND, is_stream=True,
                params={'mode': 'code', 'model_selection': selection})
            with warnings.catch_warnings():
                if provider == 'claude':
                    from claude_agent_sdk import CanUseToolShadowedWarning
                    # Match normal app warning behavior for explicit Full Access;
                    # pytest's global warnings-as-errors is not a CLI failure.
                    warnings.simplefilter('default', CanUseToolShadowedWarning)
                chunks = [chunk.payload async for chunk in adapter.process_message_stream_impl(request,
                    {'query': query, 'workspace_dir': str(tmp_path)})]
            assert not any(chunk.get('event_type') == 'chat.error' for chunk in chunks)
            return '\n'.join(chunk.get('content', '') for chunk in chunks if chunk.get('event_type') == 'chat.final')
        first = types[provider]()
        await first.create_instance(config, mode='code')
        second = None
        try:
            await asyncio.wait_for(turn(first, 'Remember this exact marker: ' + marker + '. Reply OK. Do not use tools or write files.'), 180)
            old = first._sessions[sid]
            native = old.thread_id if provider == 'codex' else old.native_id
            root = old.service.root if provider == 'opencode' else old.root
            await first.cleanup()
            second = types[provider]()
            await second.create_instance(config, mode='code')
            answer = await asyncio.wait_for(turn(second, 'What exact marker did I give you in the previous message? Reply with only that marker. Do not use tools or read files.'), 180)
            new = second._sessions[sid]
            assert (new.thread_id if provider == 'codex' else new.native_id) == native
            assert (new.service.root if provider == 'opencode' else new.root) == root
            assert marker in answer
            print('Native recovery passed:', provider, 'model:', candidates[0]['model_name'])
        finally:
            if second is not None:
                await second.cleanup()
            await first.cleanup()
    asyncio.run(scenario())


if __name__ == '__main__':
    import tempfile
    package = 'jiuwenswarm.server.runtime.agent_adapter.providers'
    parent = importlib.import_module(package)
    leaves = [] if os.environ.get('PROVIDER_TEST_BASELINE') == '1' else [
        'session_recovery', 'codex', 'claude', 'opencode_service', 'opencode']
    for leaf in leaves:
        spec = importlib.util.spec_from_file_location(package + '.' + leaf, Path(__file__).with_name(leaf + '.py'))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        setattr(parent, leaf, module)
    temporary = tempfile.mkdtemp(prefix='.recovery-tests-', dir=Path(__file__).parent)
    suites = json.loads(os.environ.get('PROVIDER_TEST_SUITES', '[]')) or [__file__]
    raise SystemExit(pytest.main([*suites, '--confcutdir=' + str(Path(__file__).parent),
        '--basetemp=' + temporary, '--import-mode=importlib', '-o', 'addopts=',
        '-o', 'cache_dir=' + str(Path(__file__).parent / '.pytest_cache'),
        '-p', 'pytest_asyncio.plugin', '-q', '--tb=short']))
