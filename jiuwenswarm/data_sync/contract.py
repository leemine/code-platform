"""Bounded project inventory values, independent of Gateway and Providers."""
from __future__ import annotations

import hashlib
import json
import re

VERSION = 1
CAPABILITIES = frozenset({"project-inventory-v1", "frozen-directory-v1", "durable-receipt-v1"})
CLOUD_EXPORT_CAPABILITY = "cloud-role-export-v1"
MAX_PROJECTS = 10000
MAX_BYTES = 4 * 1024 * 1024
PAGE_SIZE = 100
RETENTION = 30 * 86400
SNAPSHOT_TTL = 3600


class SyncError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise SyncError("INVALID_ID")
    return value


def proof_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise SyncError("INVALID_SOURCE_PROOF")
    return hashlib.sha256(value.encode()).hexdigest()


def negotiate(version, capabilities):
    if type(version) is not int or version != VERSION or not isinstance(capabilities, list):
        raise SyncError("SYNC_UNSUPPORTED")
    if any(not isinstance(v, str) for v in capabilities) or not CAPABILITIES.issubset(capabilities):
        raise SyncError("SYNC_UNSUPPORTED")
    return {"version": VERSION, "capabilities": sorted(CAPABILITIES | {CLOUD_EXPORT_CAPABILITY}), "max_projects": MAX_PROJECTS,
            "max_inventory_bytes": MAX_BYTES, "page_size": PAGE_SIZE, "account_complete": False}


def inventory(items):
    if not isinstance(items, list) or len(items) > MAX_PROJECTS or len(encoded(items)) > MAX_BYTES:
        raise SyncError("SYNC_QUOTA")
    result = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"native_id", "name", "work_mode"}:
            raise SyncError("INVALID_PROJECT")
        identifier(item["native_id"])
        if (not isinstance(item["name"], str) or not 1 <= len(item["name"]) <= 200
                or any(ord(c) < 32 for c in item["name"]) or item["work_mode"] not in {"code", "work"}):
            raise SyncError("INVALID_PROJECT")
        result.append(dict(item))
    if len({item["native_id"] for item in result}) != len(result):
        raise SyncError("DUPLICATE_PROJECT")
    return sorted(result, key=lambda item: item["native_id"])


def project_selection(values):
    if not isinstance(values, (list, tuple)) or len(values) > MAX_PROJECTS:
        raise SyncError("INVALID_SELECTION")
    result = [identifier(value) for value in values]
    if len(set(result)) != len(result):
        raise SyncError("INVALID_SELECTION")
    return sorted(result)
