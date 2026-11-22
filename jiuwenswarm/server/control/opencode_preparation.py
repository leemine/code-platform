"""OpenCode prewarm over the existing account Worker, without an execution session."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import re

from gateway.common.security.service_auth import configured_service_auth
from gateway.common.opencode_runtime import DEVICE_CONTEXT, DEVICE_ID, WORKER_ROOT
from gateway.common.work_mode import is_default_project_id
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.session.project_store import get_project_by_id


async def prepare_project_runtime(request: AgentRequest) -> bool:
    params = request.params
    if request.is_stream or request.session_id or not isinstance(params, dict):
        raise ValueError("Invalid project runtime request")
    runtime_id = None
    if set(params) == {"runtime_id"}:
        runtime_id = params["runtime_id"]
        if not isinstance(runtime_id, str) or not DEVICE_ID.fullmatch(runtime_id):
            raise ValueError("Invalid managed device ID")
        project_id = DEVICE_CONTEXT
    else:
        project_id = params.get("project_id")
        if (set(params) != {"project_id"} or not isinstance(project_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}", project_id)
                or is_default_project_id(project_id)):
            raise ValueError("Invalid project runtime request")
    url = os.environ.get("JIUWENSWARM_OPENCODE_RELAY_URL", "").strip().rstrip("/")
    auth = configured_service_auth()
    if not url or auth is None or auth.public_binding()["owner"]["actor_id"] != request.user_id:
        raise PermissionError("Managed OpenCode requires a current account Worker")
    if runtime_id is not None:
        directory = Path(WORKER_ROOT)
    else:
        project = await asyncio.to_thread(get_project_by_id, project_id, cache_bust=True)
        if not project or project.hidden or project.work_mode != "code":
            raise PermissionError("Managed OpenCode requires a visible Code project")
        directory = Path(project.project_dir)
    if not directory.is_absolute() or not directory.is_dir():
        raise PermissionError("Invalid project workspace")

    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode_managed import (
        confirm_ready, relay_client, sync_account_models,
    )

    async with asyncio.timeout(140):
        device = {"runtime_id": runtime_id} if runtime_id is not None else {}
        async with relay_client(url, str(auth.path), project_id, shared=True, **device) as client:
            await sync_account_models(client, str(directory), 40)
            await confirm_ready(client, str(directory), 100)
    return True
