"""One completed-message view of OpenCode counters; step views are not added."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


_MAX_COUNT = (1 << 53) - 1


def _positive(value: object) -> int | None:
    # Session.getUsage normalizes absent values to zero. Provenance is lost.
    return value if type(value) is int and 0 < value <= _MAX_COUNT else None


@dataclass
class OpenCodeUsage:
    messages: dict[str, dict[str, int]] = field(default_factory=dict)
    complete: bool = True
    previous: dict[str, int] | None = None
    revision: int = 0

    def observe(self, info: Any, *, native_id: str) -> None:
        if not isinstance(info, dict) or info.get("sessionID") != native_id or info.get("role") != "assistant":
            return
        timing = info.get("time") if isinstance(info.get("time"), dict) else {}
        if not isinstance(info.get("id"), str) or not info["id"] or not timing.get("completed"):
            return
        tokens = info.get("tokens") if isinstance(info.get("tokens"), dict) else {}
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        raw = {"input_tokens": tokens.get("input"), "output_tokens": tokens.get("output"),
               "total_tokens": tokens.get("total"), "reasoning_output_tokens": tokens.get("reasoning"),
               "cached_input_tokens": cache.get("read"), "cache_write_input_tokens": cache.get("write")}
        self.messages[info["id"]] = {key: value for key, value in raw.items() if _positive(value) is not None}

    def restore(self, rows: Any, *, native_id: str) -> None:
        self.complete = isinstance(rows, list) and all(
            isinstance(row, dict) and isinstance(row.get("info"), dict)
            and row["info"].get("sessionID") == native_id for row in rows)
        if self.complete:
            self.messages.clear()
            for row in rows:
                self.observe(row["info"], native_id=native_id)

    def project(self, *, session_id: str, native_id: str) -> dict[str, Any] | None:
        counts = {}
        if self.complete and self.messages:
            keys = set.intersection(*(set(value) for value in self.messages.values()))
            counts = {key: sum(value[key] for value in self.messages.values()) for key in keys}
            counts = {key: value for key, value in counts.items() if _positive(value) is not None}
        if counts == self.previous or self.previous is None and not counts:
            return None
        self.previous = counts
        self.revision = max(self.revision + 1, time.time_ns() // 1000)
        unknown = {"input_tokens": None, "output_tokens": None, "input_calls": None,
                   "output_calls": None, "calls_total": None}
        return {"event_type": "chat.usage_summary", "session_id": session_id,
                "session_usage": {"schema_version": 1, "revision": self.revision,
                                  "session_id": session_id, "scope": "native",
                                  "main": {**unknown, **counts}, "others": dict(unknown)},
                "provider": {"opencode": {"native_session_id": native_id, "usage_scope": "completed_session_messages",
                    "history_complete": self.complete, "zero_provenance": "not_available",
                    "input_semantics": "uncached_input", "output_semantics": "excluding_reasoning"}}}
