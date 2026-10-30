# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""AgentServer → Gateway 下行推送抽象与 WebSocket 默认实现。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


_websocket_push_sender: Callable[[dict[str, Any]], Awaitable[bool]] | None = None


def set_websocket_push_sender(sender: Callable[[dict[str, Any]], Awaitable[bool]] | None) -> None:
    """Bind the running server; a Runtime-direct process must not create one."""
    global _websocket_push_sender
    _websocket_push_sender = sender


def clear_websocket_push_sender(sender: Callable[[dict[str, Any]], Awaitable[bool]]) -> None:
    """A stopped server must not clear a later server's binding."""
    global _websocket_push_sender
    if _websocket_push_sender == sender:
        _websocket_push_sender = None


@runtime_checkable
class GatewayPushTransport(Protocol):
    async def send_push(self, msg: dict[str, Any]) -> bool:
        """向 Gateway 发送一条消息，并返回是否已写入传输。"""
        ...


class WebSocketGatewayPushTransport:
    """通过进程内 AgentWebSocketServer 单例推送（分离部署 + WebSocket 默认路径）。"""

    async def send_push(self, msg: dict[str, Any]) -> bool:
        sender = _websocket_push_sender
        return bool(await sender(msg)) if sender is not None else False
