"""Authenticated private relay for Codex App Server's native stdio."""
import asyncio
from contextlib import suppress
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import signal
import tempfile


PORT = 18768
FRAME = 8 * 1024 * 1024
PROJECT_ROOT = Path("/data/agent/workspace")
STATE_ROOT = Path("/state")
MODEL_CATALOG = Path("/run/codex/model-catalog.json")
SESSION = re.compile(r"[A-Za-z0-9_-]{1,160}")
COMMAND = (
    "/opt/codex/bin/codex",
    "-c", 'model_provider="swarm"',
    "-c", 'model_providers.swarm.name="Swarm model service"',
    "-c", 'model_providers.swarm.base_url="http://127.0.0.1:17543/v1"',
    "-c", 'model_providers.swarm.wire_api="responses"',
    "-c", "model_providers.swarm.requires_openai_auth=false",
)


async def line(reader):
    raw = await reader.readline()
    if raw and (len(raw) > FRAME + 1 or not raw.endswith(b"\n")):
        raise ValueError("Invalid Codex frame")
    return raw


async def reply(writer, value):
    writer.write(json.dumps(value, separators=(",", ":")).encode() + b"\n")
    await writer.drain()


async def pump(source, target):
    while raw := await line(source):
        target.write(raw)
        await target.drain()


async def drain_output(reader):
    while await reader.read(65536):
        pass


async def stop(process):
    process.stdin.close()
    drain = asyncio.create_task(drain_output(process.stdout))
    try:
        try:
            await asyncio.wait_for(process.wait(), 1)
        except TimeoutError:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), 1)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
    finally:
        drain.cancel()
        await asyncio.gather(drain, return_exceptions=True)


class StdioBridge:
    def __init__(self, digest):
        self.digest = digest
        self.active: dict[str, asyncio.Event] = {}

    def authorize(self, raw):
        if not raw or len(raw) > 8192:
            raise ValueError("Invalid Codex handshake")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("Invalid Codex handshake")
        capability = request.pop("capability", None)
        if (not isinstance(capability, str) or len(capability) > 128
                or not hmac.compare_digest(hashlib.sha256(capability.encode()).hexdigest(), self.digest)):
            raise PermissionError("Codex capability rejected")
        return request

    async def relay(self, reader, writer, *, state, directory):
        home = state / "home"
        codex_home = state / "codex"
        for path in (state, home, codex_home):
            path.mkdir(mode=0o700, exist_ok=True)
            if path.resolve() != path or path.stat().st_mode & 0o077:
                raise PermissionError("Invalid Codex session state")
        env = {k: v for k, v in os.environ.items() if k != "CODEX_CAPABILITY_DIGEST"}
        env.update(HOME=str(home), CODEX_HOME=str(codex_home))
        command = COMMAND
        if MODEL_CATALOG.is_file():
            command += ("-c", "model_catalog_json=" + json.dumps(str(MODEL_CATALOG)))
        process = await asyncio.create_subprocess_exec(
            *command, "app-server", "--listen", "stdio://", cwd=directory, env=env, start_new_session=True,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            limit=FRAME + 1)
        tasks = []
        try:
            await reply(writer, {"ready": True})
            tasks = [asyncio.create_task(pump(reader, process.stdin)),
                     asyncio.create_task(pump(process.stdout, writer))]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await stop(process)

    async def handle(self, reader, writer):
        session = None
        try:
            raw = await asyncio.wait_for(line(reader), 5)
            request = self.authorize(raw)
            if request == {"op": "idle"}:
                await reply(writer, {"idle": not self.active})
                return
            if request == {"op": "probe"}:
                with tempfile.TemporaryDirectory(prefix="ready-", dir=STATE_ROOT) as temporary:
                    await self.relay(reader, writer, state=Path(temporary), directory=PROJECT_ROOT)
                return
            if set(request) != {"op", "session", "directory"} or request["op"] != "stream":
                raise ValueError("Unsupported Codex operation")
            value = request["session"]
            directory = Path(request["directory"])
            if (not SESSION.fullmatch(value) or directory == PROJECT_ROOT
                    or not directory.is_relative_to(PROJECT_ROOT) or directory.resolve(strict=True) != directory
                    or not directory.is_dir()):
                raise PermissionError("Codex stream scope rejected")
            # The Gateway may release its transport while the old App Server
            # is still exiting and closing its persistent thread store.
            prior = self.active.get(value)
            if prior is not None:
                await asyncio.wait_for(prior.wait(), 3)
            if value in self.active:
                raise PermissionError("Codex session already has a transport")
            self.active[value] = asyncio.Event()
            session = value
            sessions = STATE_ROOT / "sessions"
            sessions.mkdir(mode=0o700, exist_ok=True)
            if sessions.resolve() != sessions or sessions.stat().st_mode & 0o077:
                raise PermissionError("Invalid Codex sessions root")
            await self.relay(reader, writer, state=sessions / hashlib.sha256(value.encode()).hexdigest(),
                             directory=directory)
        except (OSError, PermissionError, ValueError, TypeError, TimeoutError):
            pass
        finally:
            if session is not None:
                self.active.pop(session).set()
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()


async def main():
    digest = os.environ["CODEX_CAPABILITY_DIGEST"]
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid Codex capability digest")
    bridge = StdioBridge(digest)
    server = await asyncio.start_server(bridge.handle, "0.0.0.0", PORT, limit=FRAME + 1)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
