"""Account/endpoint-scoped addresses; an address never grants authorization."""
from __future__ import annotations

import base64
import hashlib
import json
import re

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}\Z")
_SESSION = {"session_id", "sessionId", "host_session_id", "parent_session_id", "parentSessionId", "previous_session_id", "source_session_id", "target_session_id", "root_session_id", "owner_session_id"}
_PROJECT = {"project_id", "projectId"}
_OPAQUE = {"content", "arguments", "tool_arguments", "result", "rendered_result", "provider_data", "provider_config", "raw", "sources", "binding", "execution_binding"}


class CloudAddresses:
    def __init__(self, endpoint, identity):
        self.owner = hashlib.sha256((endpoint + "\0" + identity["authority"] + "\0" + identity["actor_id"]).encode()).hexdigest()[:24]

    def encode(self, kind, value):
        if not isinstance(value, str) or not _ID.fullmatch(value):
            raise ValueError("invalid cloud resource ID")
        return "cloud" + kind + "_" + self.owner + "_" + base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")

    def decode(self, kind, value):
        prefix = "cloud" + kind + "_" + self.owner + "_"
        if not isinstance(value, str) or not value.startswith(prefix) or len(value) > 256:
            raise PermissionError("cloud resource owner or target mismatch")
        encoded = value[len(prefix):]
        try:
            physical = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True).decode()
        except (ValueError, UnicodeError):
            raise ValueError("invalid cloud resource address") from None
        if self.encode(kind, physical) != value:
            raise ValueError("noncanonical cloud resource address")
        return physical

    def result(self, value):
        # Application fields only. User text, tool bodies and provider bindings are opaque.
        if isinstance(value, list):
            return [self.result(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {key: item if key in _OPAQUE else
                self.encode("s" if key in _SESSION else "p", item)
                if key in _SESSION | _PROJECT and isinstance(item, str) and item else self.result(item)
                for key, item in value.items()}

    def frame(self, value):
        out = self.result(value)
        if value.get("event") != "history.message" or not isinstance(value.get("payload"), dict):
            return out
        # This one content field is a protocol history record. The record's own
        # user content/tool bodies remain opaque through result().
        content = value["payload"].get("content")
        record = content
        if isinstance(content, str):
            try:
                record = json.loads(content)
            except ValueError:
                return out  # Includes the legacy "done" sentinel.
        if isinstance(record, dict):
            mapped = self.result(record)
            out["payload"]["content"] = json.dumps(mapped, ensure_ascii=False) if isinstance(content, str) else mapped
        return out

    def params(self, value):
        out = dict(value)
        for key in _SESSION | _PROJECT:
            if out.get(key):
                if key == "previous_session_id" and not str(out[key]).startswith("clouds_"):
                    out.pop(key); out.pop("previous_mode", None)
                else:
                    out[key] = self.decode("s" if key in _SESSION else "p", out[key])
        if out.get("conversation_id"):
            out["conversation_id"] = self.decode("s", out["conversation_id"])
        for key in ("session_ids", "project_ids"):
            if key in out:
                if not isinstance(out[key], list) or len(out[key]) > 100:
                    raise ValueError("bounded resource list required")
                out[key] = [self.decode("s" if key == "session_ids" else "p", item) for item in out[key]]
        out.pop("execution_target", None)
        return out
