# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Project disk store used by Front Control.

Control owns lightweight project reads and bounded repository import receipts.
Ordinary create, rename, pin and interactive Git operations use execution.
"""

from __future__ import annotations

import asyncio
import logging

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponse
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.server.control.methods import CONTROL_PROJECT_METHODS
from jiuwenswarm.server.control.responses import build_error_response
from jiuwenswarm.server.control.store.project_queries import (
    load_pinned_sessions,
    load_project_cron_sessions,
    load_project_info,
    load_project_list,
    load_project_sessions,
    resolve_cron_binding,
)

logger = logging.getLogger(__name__)


def _ok(request: AgentRequest, payload: dict) -> AgentResponse:
    return AgentResponse(
        request_id=request.request_id,
        channel_id=request.channel_id,
        ok=True,
        payload=payload,
        metadata=request.metadata,
    )


def _from_triple(
    request: AgentRequest,
    result: tuple[dict | None, str | None, str | None],
) -> AgentResponse:
    payload, error, code = result
    if error is not None:
        return build_error_response(request, error, code=code or "INTERNAL_ERROR")
    return _ok(request, payload or {})


async def handle_project_request(request: AgentRequest) -> AgentResponse:
    method = request.req_method.value if request.req_method is not None else ""
    if method not in CONTROL_PROJECT_METHODS:
        return build_error_response(
            request, f"unsupported control project method: {method}", code="BAD_REQUEST"
        )
    params = request.params if isinstance(request.params, dict) else {}
    try:
        if request.req_method == ReqMethod.PROJECT_IMPORT:
            from jiuwenswarm.server.control.project_import import execute
            try:
                value = await asyncio.to_thread(execute, params, request.user_id)
                return _ok(request, value)
            except Exception as exc:
                import re
                code = str(exc)
                if not re.fullmatch(r'(?:GIT|PROJECT_IMPORT)_[A-Z_]+', code):
                    code = 'PROJECT_IMPORT_FAILED'
                return build_error_response(request, 'Project preparation unavailable', code=code)
        if request.req_method == ReqMethod.PROJECT_LIST:
            if "sync_export" in params:
                from jiuwenswarm.data_sync.cloud_export import export_inventory

                result = await asyncio.to_thread(export_inventory, params, request.user_id)
                return _from_triple(request, result)
            return _from_triple(request, load_project_list(params))
        if request.req_method == ReqMethod.PROJECT_INFO:
            return _from_triple(request, load_project_info(params))
        if request.req_method == ReqMethod.PROJECT_PINNED_SESSIONS:
            return _ok(request, load_pinned_sessions())
        if request.req_method == ReqMethod.PROJECT_GET_SESSIONS:
            return _from_triple(request, load_project_sessions(params, request.user_id))
        if request.req_method == ReqMethod.PROJECT_GET_CRON_SESSIONS:
            return _from_triple(
                request, load_project_cron_sessions(params, request.user_id)
            )
        if request.req_method == ReqMethod.PROJECT_CRON_RESOLVE_BINDING:
            from jiuwenswarm.server.runtime.session.lifecycle import LifecycleError, guard

            try:
                guard(project_id=str(params.get("project_id") or ""))
            except LifecycleError as exc:
                return build_error_response(request, str(exc), code=exc.code)
            return _from_triple(
                request, resolve_cron_binding(params, request.channel_id)
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[project_repository] %s failed: %s", method, exc)
        return build_error_response(request, str(exc), code="INTERNAL_ERROR")
    return build_error_response(
        request, f"unsupported control project method: {method}", code="BAD_REQUEST"
    )
