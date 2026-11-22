import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from jiuwenswarm.server.runtime.agent_adapter.providers import codex_managed_stdio as relay


@pytest.mark.asyncio
async def test_relay_exits_on_peer_close_with_sdk_stdin_still_open(monkeypatch):
    stdin_read, stdin_write = os.pipe()
    stdout_read, stdout_write = os.pipe()
    received_input = asyncio.Event()

    class Socket:
        def __init__(self):
            self.sent = []
            self.close = AsyncMock()

        async def send(self, value):
            self.sent.append(value)
            received_input.set()

        async def __aiter__(self):
            await received_input.wait()
            yield '{"id":1,"result":{}}'

    socket = Socket()
    with (
        os.fdopen(stdin_read, "rb", buffering=0) as stdin,
        os.fdopen(stdin_write, "wb", buffering=0) as sender,
        os.fdopen(stdout_read, "rb", buffering=0) as receiver,
        os.fdopen(stdout_write, "wb", buffering=0) as stdout,
    ):
        monkeypatch.setattr(relay, "sys", SimpleNamespace(
            stdin=SimpleNamespace(buffer=stdin),
            stdout=SimpleNamespace(buffer=stdout),
        ))
        sender.write(b'{"id":1,"method":"initialize"}\n')

        await asyncio.wait_for(relay._relay_stdio(socket), timeout=3)

        assert not sender.closed
        assert receiver.read() == b'{"id":1,"result":{}}\n'
        assert socket.sent == ['{"id":1,"method":"initialize"}']
        socket.close.assert_awaited_once_with(code=1000, reason="")


@pytest.mark.asyncio
@pytest.mark.parametrize("frame", (b"oversized\n", b"xyz"))
async def test_relay_rejects_overlong_or_unterminated_sdk_frame(monkeypatch, frame):
    monkeypatch.setattr(relay, "MAX_FRAME_BYTES", 4)
    reader = asyncio.StreamReader(limit=relay.MAX_FRAME_BYTES)
    reader.feed_data(frame)
    reader.feed_eof()
    socket = SimpleNamespace(send=AsyncMock(), close=AsyncMock())

    await relay._relay_stdin(socket, reader)

    socket.send.assert_not_awaited()
    socket.close.assert_awaited_once_with(code=1009, reason="SDK frame exceeds limit")
