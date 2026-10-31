"""Verify real installed/frozen external modules without a Native installation."""
from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
import json
import logging
import sys


def main():
    assert importlib.util.find_spec('openjiuwen') is None, 'Core must not be installed in the external profile'
    from jiuwenswarm.common import native_integration
    from gateway.extensions.registry import ExtensionRegistry
    from jiuwenswarm.server.worker.runtime_backend import preload_shared_execution_code
    from jiuwenswarm.server.runtime.agent_adapter.agent_adapters import create_adapter
    from jiuwenswarm.common.config_panel.execution_provider_settings import public_fields
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer
    from jiuwenswarm.agents.harness.common.rails.interrupt.contract import is_interrupt_resume_payload

    preload_shared_execution_code()
    expected = {
        'claude-direct': 'ClaudeAdapter',
        'codex-direct': 'CodexAdapter',
        'opencode-direct': 'OpenCodeAdapter',
    }
    adapters = {name: type(create_adapter(name)).__name__ for name in expected}
    assert adapters == expected, adapters
    providers = json.loads(public_fields({})['execution_provider_catalog'])
    assert {item['id'] for item in providers} == set(expected), providers
    assert len(providers) == len(expected), providers
    assert is_interrupt_resume_payload({'request_id': 'test', 'source': 'permission_interrupt', 'answers': [{}]})
    assert not is_interrupt_resume_payload({'query': 'hello'})
    registry = ExtensionRegistry(None, {}, logging.getLogger(__name__))
    context = {}
    async def hook(ctx):
        ctx['called'] = True
    registry.register('before_chat', hook)
    asyncio.run(registry.trigger('before_chat', context))
    assert context == {'called': True}
    assert not any(name == 'openjiuwen' or name.startswith('openjiuwen.') for name in sys.modules)
    print(json.dumps({
        'ok': True, 'core_present': False, 'frozen': bool(getattr(sys, 'frozen', False)),
        'executable': sys.executable, 'module': native_integration.__file__,
        'adapters': adapters, 'server': AgentWebSocketServer.__name__,
        'workswarm_version': importlib.metadata.version('workswarm'),
        'providers': [item['id'] for item in providers],
    }, indent=2))


if __name__ == '__main__':
    main()
