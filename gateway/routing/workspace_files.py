"""Adapt existing container-file APIs to the original authenticated E2A route."""
from __future__ import annotations

import base64

from gateway.routing.container_files import AgentFileDownloadChunk, AgentOSFileTransferError

_CHUNK = 512 * 1024


async def workspace_file_request(client, operation, *, user_id, session_id="", agent_type=None,
                                 instance_id=None, content=None, **params):
    from jiuwenswarm.common.schema.message import ReqMethod
    from gateway.routing.e2a_proxy import fetch_agent_unary

    # Never permit a caller-supplied instance to bypass the bound account route.
    if instance_id or (agent_type and agent_type != "jiuwenswarm"):
        raise AgentOSFileTransferError("bound builtin workspace required", code="FORBIDDEN")
    method = getattr(ReqMethod, "FILE_WORKSPACE_" + operation.upper())

    async def call(arguments):
        ok, payload = await fetch_agent_unary(
            agent_client=client, req_method=method, params=arguments, session_id=session_id,
            user_id=user_id, channel_id="file-api", label="workspace-files",
        )
        if not ok:
            raise AgentOSFileTransferError(payload.get("error", "workspace unavailable"),
                                           code=payload.get("code", "SERVICE_UNAVAILABLE"))
        return payload

    if operation == "write":
        for offset in range(0, max(1, len(content)), _CHUNK):
            payload = await call({**params, "offset": offset,
                                  "data_base64": base64.b64encode(content[offset:offset + _CHUNK]).decode("ascii")})
        return payload
    if operation == "read":
        params["offset"] = max(int(params.get("offset", 0)), 0)
        params["limit"] = min(max(int(params.get("limit", 65536)), 1), _CHUNK)
    payload = await call(params)
    if operation == "list":
        return payload["items"]
    if operation != "read":
        return payload
    try:
        data = base64.b64decode(payload["data_base64"], validate=True)
        if (payload["offset"] != params["offset"] or payload["path"] != params["path"]
                or payload["chunk_size"] != len(data) or len(data) > params["limit"]
                or payload["size"] < 0 or payload["eof"] != (params["offset"] + len(data) >= payload["size"])):
            raise ValueError("invalid chunk")
        return AgentFileDownloadChunk(data=data, path=payload["path"], offset=payload["offset"],
                                      chunk_size=len(data), size=payload["size"],
                                      content_type=payload["content_type"], eof=payload["eof"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AgentOSFileTransferError("invalid workspace response", code="INTERNAL_ERROR") from exc
