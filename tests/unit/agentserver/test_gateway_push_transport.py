from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from jiuwenswarm.server.gateway_push.transport import WebSocketGatewayPushTransport


@pytest.mark.asyncio
async def test_websocket_gateway_push_transport_forwards_to_ws_server(monkeypatch) -> None:
    from jiuwenswarm.server.gateway_push import transport as module
    send_push = AsyncMock(return_value=True)
    monkeypatch.setattr(module, "_websocket_push_sender", send_push)

    transport = WebSocketGatewayPushTransport()
    msg = {
        "request_id": "req-1",
        "channel_id": "web",
        "payload": {"event_type": "chat.delta", "content": "hello"},
    }
    await transport.send_push(msg)

    send_push.assert_awaited_once_with(msg)


@pytest.mark.asyncio
async def test_stale_server_stop_does_not_clear_new_sender(monkeypatch):
    from jiuwenswarm.server.gateway_push import transport as module
    old, new = AsyncMock(return_value=True), AsyncMock(return_value=True)
    monkeypatch.setattr(module, '_websocket_push_sender', old)
    module.set_websocket_push_sender(new)
    module.clear_websocket_push_sender(old)
    assert await WebSocketGatewayPushTransport().send_push({'new':True})
    new.assert_awaited_once_with({'new':True})
    module.clear_websocket_push_sender(new)
    assert await WebSocketGatewayPushTransport().send_push({}) is False
