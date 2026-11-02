"""Project provider-owned facts into the existing Swarm child history/UI schema.

No execution, event subscription, controls, or scheduling belongs here.
"""
from __future__ import annotations

import time


class SubagentProjection:
    def __init__(self, provider: str, parent_session_id: str):
        self.provider = provider
        self.parent = parent_session_id
        self.children: dict[str, dict] = {}
        self.seen: dict[tuple, object] = {}

    def register(self, native_id: str, title: str, *, task_id: str | None = None):
        now = int(time.time() * 1000)
        child = self.children.setdefault(native_id, {
            "subagent_id": self.provider + "-" + native_id,
            "parent_session_id": self.parent, "display_name": title or native_id,
            "task_description": title or "", "task_id": task_id or native_id,
            "created_at": now, "updated_at": now, "revision": 0, "sequence": 0,
        })
        if task_id:
            child["task_id"] = task_id
        return child

    def _persist(self, native_id, event_type, content, extra, identity):
        from jiuwenswarm.server.runtime.session.session_history import append_history_record
        child = self.children[native_id]
        append_history_record(session_id=self.parent, subagent_id=child["subagent_id"],
            request_id=identity, channel_id="subagent", role="assistant", content=content,
            timestamp=time.time(), event_type=event_type,
            extra={"parent_session_id": self.parent, "task_id": child["task_id"], **extra}, mode="subagent")

    def roster(self, native_id, *, outcome=None, closed=False, native_status=None):
        child = self.children[native_id]
        child["revision"] += 1
        child["updated_at"] = int(time.time() * 1000)
        payload = {k: v for k, v in child.items() if k != "sequence"}
        payload.update(event_type="chat.subtask_update", session_id=self.parent,
            status="closed" if closed else "idle" if outcome else "running",
            lifecycle="closed" if closed else "live", turn_outcome=outcome,
            can_send_input=False, needs_resume=False,
            closed_reason=outcome if closed else None,
            closed_at=child["updated_at"] if closed else None)
        if native_status is not None:
            payload["provider"] = {self.provider: {"status": native_status}}
        self._persist(native_id, "chat.subtask_update", "", payload,
            f"{child['subagent_id']}:roster:{child['revision']}")
        return payload

    def activity(self, native_id, kind, summary, *, identity, tool_name=None, tool_call_id=None, ok=None):
        child = self.children[native_id]
        key = (native_id, child["task_id"], "activity", identity, kind)
        value = (kind, summary, tool_name, ok)
        if self.seen.get(key) == value:
            return None
        self.seen[key] = value
        child["sequence"] += 1
        payload = {"event_type": "chat.subagent_activity", "session_id": self.parent,
            "parent_session_id": self.parent, "subagent_id": child["subagent_id"],
            "task_id": child["task_id"], "activity_id": f"{child['subagent_id']}:{child['task_id']}:{identity}:{kind}",
            "sequence": child["sequence"], "kind": kind, "summary": summary,
            "at_ms": int(time.time() * 1000)}
        if tool_name:
            payload["tool_name"] = tool_name
        if tool_call_id:
            payload["tool_call_id"] = tool_call_id
        if ok is not None:
            payload["ok"] = ok
        self._persist(native_id, "chat.subagent_activity", summary, {"subagent_activity": payload},
            f"{child['subagent_id']}:activity:{child['sequence']}")
        return payload

    def result(self, native_id, content, *, source):
        if not isinstance(content, str) or not content.strip():
            return
        child = self.children[native_id]
        key = (native_id, child["task_id"], "result")
        if self.seen.get(key) == content:
            return
        self.seen[key] = content
        child["sequence"] += 1
        self._persist(native_id, "chat.final", content,
            {"provider": {self.provider: {"result_source": source}}},
            f"{child['subagent_id']}:{child['task_id']}:result:{child['sequence']}")
