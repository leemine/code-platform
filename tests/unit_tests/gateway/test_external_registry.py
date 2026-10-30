"""The production registry keeps hooks effective without the optional Core."""
import logging

import pytest

from gateway.extensions.registry import ExtensionRegistry


@pytest.mark.asyncio
async def test_external_registry_orders_hooks_and_preserves_context():
    registry = ExtensionRegistry(None, {}, logging.getLogger(__name__))
    context = {'steps': []}
    async def first(ctx):
        ctx['steps'].append('first')
    def last(ctx):
        ctx['steps'].append('last')
    registry.register('before_chat', last, priority=1)
    registry.register('before_chat', first, priority=100)
    await registry.trigger('before_chat', context)
    assert context['steps'] == ['first', 'last']
    registry.unregister('before_chat', first)
    context['steps'].clear()
    await registry.trigger('before_chat', context)
    assert context['steps'] == ['last']


@pytest.mark.asyncio
async def test_external_registry_does_not_swallow_blocking_hook():
    registry = ExtensionRegistry(None, {}, logging.getLogger(__name__))
    def deny(ctx):
        raise PermissionError('blocked')
    registry.register('before_chat', deny)
    with pytest.raises(PermissionError, match='blocked'):
        await registry.trigger('before_chat', {})
    with pytest.raises(ValueError, match='Native'):
        registry.register('before_chat', deny, filters=['unknown'])


@pytest.mark.asyncio
async def test_native_registry_keeps_framework_delegation():
    calls = []
    class Framework:
        def register_sync(self, *args, **kwargs):
            calls.append(('register', args, kwargs))
        async def trigger(self, *args, **kwargs):
            calls.append(('trigger', args, kwargs))
    registry = ExtensionRegistry(Framework(), {}, logging.getLogger(__name__))
    handler = lambda ctx: None
    registry.register('event', handler, once=True)
    await registry.trigger('event', {'native': True})
    assert calls[0] == ('register', ('event', handler), {'priority': 100, 'once': True})
    assert calls[1] == ('trigger', ('event', {'native': True}), {})
