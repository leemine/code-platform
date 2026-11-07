"""Translate Swarm's selected connectors into Codex's native MCP configuration."""
from dataclasses import dataclass, field
from hashlib import sha256
from ipaddress import ip_address
import re
from urllib.parse import urlsplit


SERVER_PREFIX = "swarm_mcp_"
ELICITATION = "mcpServer/elicitation/request"
_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


@dataclass(frozen=True)
class McpSelection:
    servers: dict
    names: dict
    env: dict = field(repr=False)


def _url(value):
    if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        return None
    try:
        url = urlsplit(value)
        _ = url.port
        if not url.hostname or url.username is not None or url.query or url.fragment:
            return None
        if url.scheme == "https":
            return value
        if url.scheme == "http" and (url.hostname == "localhost" or ip_address(url.hostname).is_loopback):
            return value
    except ValueError:
        pass
    return None


def prepare_mcp(assets):
    # These are declarations of the existing connector, not a second credential lookup.
    from jiuwenswarm.server.runtime.mcp.credential import (
        KIND_CLI_OAUTH, KIND_OAUTH, detect_credential_kind,
    )

    selected = set(assets.snapshot["mcp"])
    if set(assets.connectors) != selected or assets.packages or assets.selected_skills:
        raise ValueError("Codex MCP requires explicit session connector selection")
    servers, names, env = {}, {}, {}
    for name, entry in assets.connectors.items():
        if entry.get("transport") not in {"http", "streamable-http", "streamable_http"}:
            raise ValueError("Codex MCP requires Streamable HTTP")
        if detect_credential_kind(name) in {KIND_OAUTH, KIND_CLI_OAUTH}:
            raise ValueError("Codex MCP does not support OAuth connectors yet")
        url = _url(entry.get("url"))
        if url is None:
            raise ValueError("Codex MCP requires an HTTPS or loopback HTTP URL without credentials, query or fragment")
        key = sha256(name.encode()).hexdigest()
        native = SERVER_PREFIX + key[:24]
        headers = entry.get("headers") or {}
        if not isinstance(headers, dict):
            raise ValueError("Codex MCP headers must be named strings")
        config = {"url": url, "required": True, "startup_timeout_sec": 8}
        if headers:
            references = {}
            for header, value in headers.items():
                if (not isinstance(header, str) or not _HEADER_NAME.fullmatch(header)
                        or not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value)
                        or header.lower() in {h.lower() for h in references}):
                    raise ValueError("Codex MCP headers must be valid and unambiguous")
                variable = "SWARM_CODEX_MCP_" + sha256(f"{key}:{header}".encode()).hexdigest().upper()
                references[header] = variable
                env[variable] = value
            config["env_http_headers"] = references
        servers[native] = config
        names[native] = name
    return McpSelection(servers, names, env)


def confirm_mcp(client, thread_id, selection):
    from openai_codex.generated.v2_all import ListMcpServerStatusResponse, McpServerConnectionStatus

    seen = set()
    params = {"threadId": thread_id, "detail": "toolsAndAuthOnly"}
    while True:
        response = client.request("mcpServerStatus/list", params, response_model=ListMcpServerStatusResponse)
        for server in response.data:
            if not server.name.startswith(SERVER_PREFIX):
                continue
            if (server.name not in selection.servers or server.name in seen
                    or server.runtime_status != McpServerConnectionStatus.connected
                    or server.server_capabilities is None or server.tools_error is not None
                    or not server.tools):
                raise ValueError("Codex did not confirm the selected MCP tools")
            seen.add(server.name)
        if not response.next_cursor:
            break
        params["cursor"] = response.next_cursor
    if seen != set(selection.servers):
        raise ValueError("Codex did not confirm the selected MCP tools")


def is_confirmation(params, selection):
    if selection is None or params.get("serverName") not in selection.names or params.get("mode") != "form":
        return False
    schema = params.get("requestedSchema")
    return (isinstance(schema, dict) and schema.get("type") == "object"
            and schema.get("properties") == {} and schema.get("required", []) == []
            and not set(schema) - {"type", "properties", "required", "additionalProperties", "$schema"})


def approval_reply(method, decision):
    if method == ELICITATION:
        return {"action": decision, "content": None}
    return {"decision": decision}
