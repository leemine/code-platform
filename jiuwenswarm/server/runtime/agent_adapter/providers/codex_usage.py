"""Read-only projection of Codex thread counters, never a model-call ledger."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone


_COUNTERS = {
    "inputTokens": "input_tokens",
    "outputTokens": "output_tokens",
    "totalTokens": "total_tokens",
    "cachedInputTokens": "cached_input_tokens",
    "reasoningOutputTokens": "reasoning_output_tokens",
    "cacheWriteInputTokens": "cache_write_input_tokens",
}


def _count(value):
    return value if type(value) is int and 0 <= value <= (1 << 53) - 1 else None


def _counts(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in _COUNTERS if _count(value.get(key)) is not None}


@dataclass
class CodexUsage:
    """Cache native observations in the existing adapter Session only.

    History owns durable snapshots. Revision is an observation timestamp in
    microseconds (not a fabricated model-call count), ordered within this reader.
    No native history replay, extra RPC, disk counter or second consumer is used.
    """

    total: dict | None = None
    baseline: dict | None = None
    seen: bool = False
    revision: int = 0
    previous: dict | None = None
    continuous: bool = False
    discontinuous: bool = False
    window: int | None = None

    def begin_turn(self, *, new_thread: bool):
        if new_thread:
            self.discontinuous = False
        self.baseline = ({key: 0 for key in _COUNTERS} if new_thread else
                         dict(self.total) if self.continuous and self.total is not None else None)
        self.seen = False
        self.previous = None
        self.continuous = False

    def end_turn(self, *, completed: bool):
        # Interrupted/failed turns may have usage after the last observed frame.
        self.continuous = completed and self.seen and not self.discontinuous

    def project(self, payload, *, session_id: str, thread_id: str, turn_id: str, request_id: str):
        if payload.get("threadId") != thread_id or payload.get("turnId") != turn_id:
            return []
        usage = payload.get("tokenUsage")
        if not isinstance(usage, dict):
            return []
        total = _counts(usage.get("total"))
        last = _counts(usage.get("last"))
        window = _count(usage.get("modelContextWindow"))
        window = window if window else None
        observation = {"total": total, "last": last, "model_context_window": window}
        if observation == self.previous or not total and window is None:
            return []
        previous_window = self.window
        self.window = window
        self.previous = observation
        self.revision = max(self.revision + 1, time.time_ns() // 1000)
        source = {"codex": {"thread_id": thread_id, "turn_id": turn_id,
                            "usage_scope": "thread", **observation}}
        events = []
        if total:
            self.seen = True
            if self.total is not None and any(
                key in total and total[key] < value for key, value in self.total.items()
            ):
                self.baseline = None
                self.discontinuous = True
            self.total = total
            # A reset or an out-of-order snapshot cannot establish session totals.
            values = {} if self.discontinuous else {_COUNTERS[key]: value for key, value in total.items()}
            if self.discontinuous:
                source["codex"]["counter_continuity"] = "unknown"
            unknown = {"input_tokens": None, "output_tokens": None,
                       "input_calls": None, "output_calls": None, "calls_total": None}
            event = {"event_type": "chat.usage_summary", "session_id": session_id,
                     "session_usage": {"schema_version": 1, "revision": self.revision,
                                       "session_id": session_id, "main": {**unknown, **values},
                                       "others": dict(unknown)}, "provider": source}
            if self.baseline is not None:
                delta = {_COUNTERS[key]: value - self.baseline[key]
                         for key, value in total.items() if key in self.baseline}
                if delta:
                    event["usage"] = delta
            events.append(event)
        if window is not None or previous_window is not None:
            events.append({"event_type": "context.usage", "schema_version": "context-usage.v1",
                           "phase": "post_call", "request_id": request_id,
                           "timestamp": datetime.now(timezone.utc).isoformat(),
                           "product_session_id": session_id, "role": None, "depth": 0,
                           "team_id": None, "member_name": None,
                           "context_window": {"limit_tokens": window, "input_tokens": None,
                                              "occupancy_rate": None},
                           "parts": {}, "session_kv_cache_hit_rate": None, "provider": source})
        return events
