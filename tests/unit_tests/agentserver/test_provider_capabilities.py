"""Declare implemented integration features without changing Native defaults."""
import pytest

from jiuwenswarm.server.runtime.agent_adapter.interface import JiuWenSwarm
from jiuwenswarm.server.runtime.agent_adapter.providers.codex import CodexAdapter
from jiuwenswarm.server.runtime.agent_adapter.providers.claude import ClaudeAdapter
from jiuwenswarm.server.runtime.agent_adapter.providers.opencode import OpenCodeAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize('factory', [CodexAdapter, ClaudeAdapter, OpenCodeAdapter])
async def test_unsupported_usage_and_manual_compaction_are_explicit(factory):
    facade = JiuWenSwarm()
    facade._adapter = factory(mode='code')
    with pytest.raises(ValueError, match='provider_capability_unsupported: context_usage'):
        await facade.get_context_usage('session')
    with pytest.raises(ValueError, match='provider_capability_unsupported: manual_compaction'):
        await facade.compact_partial('session', 0)
    # The descriptor describes the integration, never the SDK's entire feature set.
    assert facade._adapter.capabilities.native_resume is True
    assert facade._adapter.capabilities.main_instructions is (factory is OpenCodeAdapter)
    assert facade._adapter.capabilities.user_questions is (factory is OpenCodeAdapter)


@pytest.mark.asyncio
async def test_legacy_native_usage_and_compaction_are_not_limited_by_external_descriptors():
    calls = []
    class Native:
        async def get_context_usage(self, *, session_id):
            calls.append(session_id)
            return {'used_tokens': 42}
        async def compact_partial(self, *, session_id, turn_index, direction):
            calls.append((session_id, turn_index, direction))
            return {'status': 'ok'}
    facade = JiuWenSwarm()
    facade._adapter = Native()
    assert await facade.get_context_usage('native') == {'used_tokens': 42}
    assert await facade.compact_partial('native', 1) == {'status': 'ok'}
    assert calls == ['native', ('native', 1, 'from')]
