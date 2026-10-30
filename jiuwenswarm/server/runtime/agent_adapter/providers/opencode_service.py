"""Session-owned official CLI process for directory-scoped Skill/MCP settings.

The project cwd stays unchanged. Only task-owned config/data and child processes
are touched; borrowed servers are never reconfigured or disposed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import signal
import shutil
import socket
import tempfile
from pathlib import Path

from . import opencode_transport as transport
from .opencode_models import build_server_model_config

logger = logging.getLogger(__name__)
HEALTH_TIMEOUT = 0.5
STARTUP_TIMEOUT = 40


def permission_config(equipment, profile):
    if profile not in {"default", "full_access"}:
        raise ValueError("Unsupported OpenCode permission profile")
    action = "allow" if profile == "full_access" else "ask"
    return {"*": action, "task": "deny", "question": "allow",
            "skill": {"*": "deny", **{name: action for name in equipment.skills}}}


class SessionService:
    def __init__(self, executable: str, directory: str):
        from jiuwenswarm.common.utils import get_agent_sessions_dir
        parent = get_agent_sessions_dir() / ".opencode"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = Path(tempfile.mkdtemp(prefix="session-", dir=parent))
        self.executable = executable
        self.directory = directory
        self.process = None
        self.client = None
        self.revision = None

    async def configure(self, equipment, *, permission_profile="default"):
        model_config, _ = build_server_model_config()
        config = {**model_config, "$schema": "https://opencode.ai/config.json", "autoupdate": False,
                  "permission": permission_config(equipment, permission_profile),
                  "skills": {"paths": [str(self.root / "skills")]}, "mcp": equipment.mcps}
        digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode())
        total = 0
        for name, directory in sorted(equipment.skills.items()):
            digest.update(name.encode())
            digest.update(equipment.skill_documents.get(name, "").encode())
            for file in sorted(directory.rglob("*")):
                if any(part in {".archive", ".git", "__pycache__"} for part in file.relative_to(directory).parts):
                    continue
                if file.is_symlink():
                    raise ValueError("Skill symlinks are not supported")
                if file.is_file():
                    total += file.stat().st_size
                    if total > 50 * 1024 * 1024:
                        raise ValueError("OpenCode equipment exceeds the 50 MiB resource limit")
                    digest.update(str(file.relative_to(directory)).encode())
                    digest.update(file.read_bytes())
        revision = digest.hexdigest()
        if revision == self.revision and self.process and self.process.returncode is None:
            return
        await self.stop()
        self.revision = None
        skills = self.root / "skills"
        if skills.exists():
            shutil.rmtree(skills)
        skills.mkdir(mode=0o700)
        for index, (name, directory) in enumerate(equipment.skills.items()):
            shutil.copytree(directory, skills / str(index), ignore=shutil.ignore_patterns(".archive", ".git", "__pycache__"))
            if name in equipment.skill_documents:
                (skills / str(index) / "SKILL.md").write_text(equipment.skill_documents[name])
        config_file = self.root / "opencode.json"
        config_file.write_text(json.dumps(config))
        config_file.chmod(0o600)
        # Use a private HOME/XDG namespace while retaining the actual project cwd.
        env = {k: v for k, v in os.environ.items() if not k.startswith("OPENCODE_")}
        env["HOME"] = str(self.root / "home")
        for key, leaf in [("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                          ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")]:
            env[key] = str(self.root / leaf)
        password = secrets.token_urlsafe(32)
        env.update(OPENCODE_CONFIG=str(config_file), OPENCODE_SERVER_PASSWORD=password)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.process = await asyncio.create_subprocess_exec(
            self.executable, "serve", "--hostname", "127.0.0.1", "--port", str(port),
            cwd=self.directory, env=env, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=os.name != "nt",
        )
        self.client = transport.create_client(f"http://127.0.0.1:{port}", password=password)
        try:
            async with asyncio.timeout(STARTUP_TIMEOUT):
                while True:
                    if self.process.returncode is not None:
                        logger.warning("OpenCode startup process exited code=%s", self.process.returncode)
                        raise RuntimeError(f"OpenCode startup failed (process exit {self.process.returncode})")
                    try:
                        if await transport.healthy(self.client, timeout=HEALTH_TIMEOUT):
                            break
                    except transport.TransportError:
                        pass
                    await asyncio.sleep(0.15)
            self.revision = revision
        except TimeoutError:
            logger.warning("OpenCode startup health deadline exceeded seconds=%s", STARTUP_TIMEOUT)
            await self.stop()
            raise RuntimeError("OpenCode startup health check timed out (TimeoutError)") from None
        except BaseException:
            await self.stop()
            raise

    async def stop(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None
        if self.process is not None:
            if self.process.returncode is None:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), 5)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            # A stdio MCP descendant may outlive a crashed server. This group
            # was created exclusively for this service, never for a borrowed CLI.
            if os.name != "nt":
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            self.process = None

    async def close(self):
        await self.stop()
        shutil.rmtree(self.root)
