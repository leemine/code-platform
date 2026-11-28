"""Own one private stdio connection to the plugin's Node coordinator."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4


class SidecarError(RuntimeError):
    """The process refused an operation or its result is unavailable."""


class Sidecar:
    def __init__(self, entry: Path, path: Path, members: list[str], node: str):
        self.entry = entry
        self.path = path
        self.members = members
        self.node = node
        self.process = None
        self.lock = asyncio.Lock()
        self.closed = False

    async def call(self, method: str, params: dict):
        async with self.lock:
            if self.closed:
                raise SidecarError("STOPPED")
            try:
                if self.process is None or self.process.returncode is not None:
                    self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    self.process = await asyncio.create_subprocess_exec(
                        self.node, str(self.entry), str(self.path),
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL, limit=1_048_576,
                    )
                    await self._exchange("initialize", {"members": self.members})
                return await self._exchange(method, params)
            except asyncio.CancelledError:
                await self._release()
                raise
            except (OSError, ValueError, TimeoutError):
                await self._release()
                raise SidecarError("ORCHESTRATOR_UNAVAILABLE") from None

    async def _exchange(self, method: str, params: dict):
        rid = uuid4().hex
        message = json.dumps({"id": rid, "method": method, "params": params}, ensure_ascii=False)
        async with asyncio.timeout(8):
            self.process.stdin.write(message.encode("utf-8") + b"\n")
            await self.process.stdin.drain()
            line = await self.process.stdout.readline()
        data = json.loads(line)
        if data.get("id") != rid:
            raise ValueError("Uncorrelated sidecar response")
        if not data.get("ok"):
            raise SidecarError(data.get("code") or "CORE_REFUSED")
        return data.get("result")

    async def _release(self):
        process, self.process = self.process, None
        if process is None or process.returncode is not None:
            return
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 3)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def close(self):
        async with self.lock:
            self.closed = True
            await self._release()
