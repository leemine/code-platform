"""Observe native model totals, without reconstructing a cross-process ledger."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


_FIELDS = {
    "inputTokens": "input_tokens",
    "outputTokens": "output_tokens",
    "cacheReadInputTokens": "cached_input_tokens",
    "cacheCreationInputTokens": "cache_write_input_tokens",
}
_MAX_COUNT = (1 << 53) - 1


def _count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= _MAX_COUNT else None


@dataclass
class ClaudeUsage:
    previous: dict[str, int] | None = None
    revision: int = 0

    def project(self, models: Any, *, session_id: str, native_id: str, crashed: bool = False) -> dict[str, Any] | None:
        # Result.usage is main-loop-only. model_usage includes native children.
        # It is cumulative within the CLI call; older CLIs reset it on resume.
        if not isinstance(models, dict) or not models:
            if self.previous is None:
                return None
            models = {"unreported": {}}
        counts = {}
        for source, target in _FIELDS.items():
            values = [_count(row.get(source)) if isinstance(row, dict) else None for row in models.values()]
            if all(value is not None for value in values):
                total = sum(values)
                if _count(total) is not None:
                    counts[target] = total
        reported = counts
        if crashed and counts and not any(counts.values()):
            # The CLI may zero all result counters after an execution crash.
            counts = {}
        if counts == self.previous:
            return None
        self.previous = counts
        self.revision = max(self.revision + 1, time.time_ns() // 1000)
        unknown = {"input_tokens": None, "output_tokens": None, "input_calls": None,
                   "output_calls": None, "calls_total": None}
        return {"event_type": "chat.usage_summary", "session_id": session_id,
                "session_usage": {"schema_version": 1, "revision": self.revision,
                                  "session_id": session_id, "scope": "native",
                                  "main": {**unknown, **counts}, "others": dict(unknown)},
                "provider": {"claude": {"native_session_id": native_id, "usage_scope": "native_model_usage",
                    "includes_subagents": True, "input_semantics": "uncached_input",
                    "resume_totals": "native_cli_defined",
                    **({"counter_continuity": "unknown", "reported_counts": reported} if counts is not reported else {})}}}
