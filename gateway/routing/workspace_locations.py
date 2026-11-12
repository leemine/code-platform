"""Operator-configured entry navigation, never arbitrary per-request routing."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from gateway.routing.e2a_proxy import is_agentos_routing_client, is_legacy_shared_directory_client


def entry_url(kind):
    raw = os.environ.get("CODE_PLATFORM_" + kind.upper() + "_ENTRY_URL", "")
    if not raw:
        return None
    url = urlsplit(raw)
    local_http = kind == "local" and url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
    if (not (url.scheme == "https" or local_http) or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("invalid workspace entry URL")
    return raw.rstrip("/") + "/"


def catalog(client):
    if is_agentos_routing_client(client):
        kind = "cloud"
    elif is_legacy_shared_directory_client(client):
        kind = "local"
    else:
        raise ValueError("workspace host identity unavailable")
    return {"kind": kind, "switch_mode": "entry_navigation", "entries": [
        {"kind": value, "current": value == kind, "url": entry_url(value) if value != kind else None}
        for value in ("local", "cloud")
    ]}
