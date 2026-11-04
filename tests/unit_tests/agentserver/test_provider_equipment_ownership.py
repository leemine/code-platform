"""Exercise the original Facade seam and existing Runtime ownership context."""
import asyncio
from types import SimpleNamespace
from dataclasses import replace
from jiuwenswarm.runtime.session.model import RuntimeSessionSnapshot, RuntimeSessionState, SessionPersistencePolicy

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.runtime.context import set_runtime_context, reset_runtime_context
from jiuwenswarm.server.runtime.agent_adapter import equipment, interface
from jiuwenswarm.server.runtime.session import session_metadata


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'failed', 'stale', 'closed', 'cancelled', 'concurrent'])
async def test_facade_commits_only_current_successful_equipment(tmp_path, monkeypatch, outcome):
    from jiuwenswarm.common import utils
    monkeypatch.setattr(utils, 'get_agent_sessions_dir', lambda: tmp_path)
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: tmp_path)
    sid = 'equipment-' + outcome
    session_metadata.save_session_equipment(sid, agent_template_name='old')
    assets = equipment.EquipmentAssets((), (), (), frozenset(), {},
        {'agent_template_name': 'new', 'plugin_names': [], 'mcp': []})
    async def resolve(params, *, include_global_skills):
        assert not include_global_skills
        return assets
    monkeypatch.setattr(equipment, 'resolve_assets', resolve)
    snapshot = RuntimeSessionSnapshot(sid, 'web', SessionPersistencePolicy.PERSISTENT, 1, RuntimeSessionState.ACTIVE)
    runtime = SimpleNamespace(get_session_snapshot=lambda session_id: snapshot)
    applied = []
    class Adapter:
        def equipment_input_policy(self, session_id, request, *, execution=None):
            return equipment.EquipmentPolicy(str(tmp_path))
        async def apply_equipment(self, session_id, request, resolved, *, directory, execution=None, ensure_current):
            nonlocal snapshot
            ensure_current()
            assert resolved is assets and directory == str(tmp_path)
            applied.append(session_id)
            await asyncio.sleep(0)
            if outcome == 'failed':
                raise ValueError('native readback failed')
            if outcome == 'stale':
                snapshot = replace(snapshot, generation=snapshot.generation + 1)
            if outcome == 'closed':
                snapshot = replace(snapshot, state=RuntimeSessionState.CLOSED)
            if outcome == 'concurrent':
                session_metadata.save_session_equipment(sid, agent_template_name='other')
            if outcome == 'cancelled':
                # Even a plugin swallowing CancelledError must not commit late.
                asyncio.current_task().cancel()
                try:
                    await asyncio.sleep(0)
                except asyncio.CancelledError:
                    pass
    facade = interface.JiuWenSwarm()
    facade._adapter = Adapter()
    req = AgentRequest(request_id='equipment', channel_id='web', session_id=sid,
                       req_method=ReqMethod.CHAT_SEND, params={'agent_template_name': 'new'})
    token = set_runtime_context(runtime, None)
    try:
        async def reconcile():
            await facade.reconcile_session_mcp(sid, [], execution_request=req)
        task = asyncio.create_task(reconcile())
        if outcome == 'success':
            await task
        else:
            with pytest.raises((ValueError, RuntimeError, asyncio.CancelledError)):
                await task
        expected = 'new' if outcome == 'success' else 'other' if outcome == 'concurrent' else 'old'
        assert session_metadata.get_session_equipment(sid)['agent_template_name'] == expected
        assert applied == [sid]
    finally:
        reset_runtime_context(token)


@pytest.mark.asyncio
async def test_legacy_native_reconcile_signature_remains_supported():
    calls = []
    class Adapter:
        async def reconcile_session_mcp(self, session_id, needed, *, model_name=None):
            calls.append((session_id, needed, model_name))
    facade = interface.JiuWenSwarm()
    facade._adapter = Adapter()
    await facade.reconcile_session_mcp('native', ['mcp'], model_name='existing')
    assert calls == [('native', ['mcp'], 'existing')]


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['new_generation', 'cancelled_producer'])
async def test_late_role_acceptance_cannot_overwrite_equipment(tmp_path, monkeypatch, boundary):
    monkeypatch.setattr(session_metadata, 'get_agent_sessions_dir', lambda: tmp_path)
    sid = 'role-acceptance'
    session_metadata.save_session_equipment(sid, agent_template_name='old')
    snapshot = RuntimeSessionSnapshot(sid, 'web', SessionPersistencePolicy.PERSISTENT, 1, RuntimeSessionState.ACTIVE)
    runtime = SimpleNamespace(get_session_snapshot=lambda _sid: snapshot)
    facade = interface.JiuWenSwarm()
    facade._adapter = object()
    request = AgentRequest(request_id='switch', channel_id='web', session_id=sid,
                           req_method=ReqMethod.CHAT_SEND, params={'agent_template_name': 'new'})
    execution = SimpleNamespace(main_agent_role=SimpleNamespace(template_ref='new'))
    token = set_runtime_context(runtime, None)
    try:
        commit = await facade.reconcile_session_mcp(
            sid, [], execution_request=request, execution_input=execution,
        )
        assert session_metadata.get_session_equipment(sid)['agent_template_name'] == 'old'
        if boundary == 'new_generation':
            snapshot = replace(snapshot, generation=2)
            with pytest.raises(RuntimeError, match='no longer owns'):
                commit()
        else:
            async def cancelled_producer():
                asyncio.current_task().cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.sleep(0)
                commit()

            with pytest.raises(asyncio.CancelledError):
                await asyncio.create_task(cancelled_producer())
        assert session_metadata.get_session_equipment(sid)['agent_template_name'] == 'old'
    finally:
        reset_runtime_context(token)
