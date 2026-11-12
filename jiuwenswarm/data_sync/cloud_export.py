"""Cloud metadata export inside the original authenticated AgentServer role."""
import os
import hashlib

from gateway.common.security.service_auth import canonical, configured_service_auth
from .contract import SyncError, digest, project_selection
from .project_source import selected_inventory


def export_inventory(params, user_id):
    try:
        if set(params) != {"sync_export", "project_ids"} or params["sync_export"] is not True:
            raise SyncError("INVALID_REQUEST")
        selected = project_selection(params["project_ids"])
        if os.environ.get("CODE_PLATFORM_ROLE") != "account-instance":
            raise SyncError("SOURCE_ROLE_REQUIRED")
        auth = configured_service_auth()
        if auth is None:
            raise SyncError("SOURCE_ROLE_REQUIRED")
        binding = auth.public_binding()
        if binding["owner"]["actor_id"] != user_id:
            raise PermissionError()
        from jiuwenswarm.common.utils import get_agent_root_dir
        actual_root = hashlib.sha256(canonical(str(get_agent_root_dir().resolve()))).hexdigest()
        if actual_root != binding["workspace_digest"]:
            raise SyncError("SOURCE_BINDING_CHANGED")
        items = selected_inventory(selected)
        if auth.public_binding() != binding:
            raise SyncError("SOURCE_BINDING_CHANGED")
        return {"binding": binding, "items": items, "complete": True,
                "total": len(items), "inventory_digest": digest(items)}, None, None
    except SyncError as exc:
        return None, "cloud project export rejected", exc.code
    except PermissionError:
        return None, "cloud project export unauthorized", "UNAUTHORIZED"
    except (OSError, ValueError, TypeError, KeyError):
        return None, "cloud inventory unavailable", "SOURCE_UNAVAILABLE"
