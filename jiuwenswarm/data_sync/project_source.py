"""Export an explicit selection from the original durable ProjectStore."""
from __future__ import annotations

from .contract import digest, inventory


def selected_inventory(selected_ids):
    if not isinstance(selected_ids, (list, tuple)) or any(not isinstance(value, str) for value in selected_ids):
        raise ValueError("explicit project selection required")
    if len(selected_ids) > 10000 or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("invalid project selection")
    if not selected_ids:
        return []  # Explicitly withdrawing the selection, not a failed scan.
    from jiuwenswarm.server.runtime.session.project_store import snapshot_projects_for_export
    # One original store read freezes the metadata list before any network IO.
    selected = set(selected_ids)
    result = [{"native_id": row.project_id, "name": row.name, "work_mode": row.work_mode}
              for row in snapshot_projects_for_export() if row.project_id in selected]
    return inventory(result)


def inventory_payload(items, operation_id, base_revision):
    # Wire values only; no dependency from the source connector to Gateway.
    items = inventory(items)
    return {"operation_id": operation_id, "base_revision": base_revision, "items": items,
            "total": len(items), "inventory_digest": digest(items), "complete": True}
