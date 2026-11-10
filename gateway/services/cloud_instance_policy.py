"""Environment policy supplied to the original instance lifecycle owner."""
from __future__ import annotations

from gateway.auth.account_authenticator import current_account
from gateway.common.security.service_auth import ServiceAuthenticator, SERVICE_AUTH_HEADER
from gateway.extensions.agentos.agentos_router.lifecycle import LaunchPlan
from gateway.services.cloud_environments import EnvironmentUnavailable


class CloudInstancePolicy:
    def __init__(self, store, *, ready_timeout=120, resources=None):
        self.resources = resources
        self.store = store
        self.ready_timeout = ready_timeout

    def start(self):
        self.store.acquire_writer()
        try:
            self.store.rows()  # Validate durable state before enabling startup cleanup.
        except BaseException:
            self.store.close()
            raise

    def close(self):
        self.store.close()

    def protect(self, user_id, agent_type):
        # This control-plane role protects existing account bindings, including unknown legacy IDs.
        return agent_type == "jiuwenswarm" and bool(user_id)

    def pending_delete(self, user_id):
        from gateway.extensions.agentos.agentos_router.models import AgentInfo
        row = self.store.by_user(user_id)
        if row["state"] != "DELETING":
            return None
        return AgentInfo(user_id=user_id, agent_type="jiuwenswarm", sandbox_id=row["instance_id"],
                         metadata={"instance_epoch": row["epoch"]})

    def plan(self, info):
        if not self.protect(info.user_id, info.agent_type):
            raise PermissionError("account control plane only supports its bound builtin instances")
        row = self.store.prepare(info.user_id)
        profile = row["profile"]
        from pathlib import Path
        mounts = [{"source": str(Path(row["auth_file"]).parent), "target": "/run/jiuwenswarm", "readonly": True},
                  {"source": row["workspace"], "target": "/data", "readonly": False}, *profile["extra_mounts"]]
        env = dict(profile["runtime_env"])
        env.update(CODE_PLATFORM_ROLE="account-instance", JIUWENSWARM_DATA_DIR="/data", JIUWENSWARM_CONFIG_DIR="/data/config", AGENT_SERVER_HOST="0.0.0.0",
                   JIUWENSWARM_INSTANCE_AUTH_FILE="/run/jiuwenswarm/instance-auth.json",
                   JIUWENSWARM_CONTAINER_FILE_ROOT="/home/agentos")
        spec = {"sandbox_type": "docker", "runtime": profile["runtime"],
                "rootfs": {"imageurl": profile["image_digest"], "user": profile["runtime_user"], "ports": ["18092"]},
                "cpu": profile["cpu"], "memory": profile["memory"], "cmds": [profile["command"]]}
        return LaunchPlan(row["name"], row["workspace"], spec, env, mounts, row["instance_id"],
                          row["state"] in {"CREATING", "UNKNOWN"}, row)

    def creating(self, plan):
        self.store.transition(plan.receipt, "CREATING", expected="NEW")

    def created(self, plan, instance_id):
        self.store.transition(plan.receipt, "ALLOCATED", instance_id=instance_id)

    def unknown(self, plan):
        self.store.transition(plan.receipt, "UNKNOWN")

    def matches(self, plan, info):
        root = info.get("rootfs") or {}
        expected = plan.runtime_spec["rootfs"]
        # Some Frontend versions omit name in GET. The private epoch mount
        # plus workspace and immutable runtime profile still identify ownership.
        return ((not info.get("name") or info["name"] == plan.name)
                and root.get("workspace") == plan.workspace
                and root.get("imageurl") == expected["imageurl"]
                and root.get("user") == expected["user"]
                and any(m.get("source") == plan.mounts[0]["source"] and m.get("target") == "/run/jiuwenswarm"
                        and m.get("readonly") is True for m in root.get("mounts", [])))

    def deleting(self, info):
        row = self.store.by_user(info.user_id)
        if row["instance_id"] != info.sandbox_id or row["epoch"] != info.metadata.get("instance_epoch"):
            raise EnvironmentUnavailable("instance deletion ownership or epoch differs")
        if row["state"] not in {"ALLOCATED", "DELETING"}:
            raise EnvironmentUnavailable("instance is not eligible for deletion")
        self.store.transition(row, "DELETING", expected=row["state"])

    async def confirm_deleted(self, info):
        from pathlib import Path
        row = self.store.by_user(info.user_id)
        if (row["instance_id"] != info.sandbox_id or row["epoch"] != info.metadata.get("instance_epoch")
                or row["state"] != "DELETING"):
            raise EnvironmentUnavailable("physical confirmation ownership or epoch differs")
        if row["profile"].get("physical_verification"):
            if self.resources is None:
                raise EnvironmentUnavailable("required physical confirmation backend is unavailable")
            await self.resources.confirm_deleted(workspace=row["workspace"],
                identity=str(Path(row["auth_file"]).parent), image=row["profile"]["image_digest"],
                user=row["profile"]["runtime_user"], instance_id=row["instance_id"])

    def deleted(self, info):
        row = self.store.by_user(info.user_id)
        if row["instance_id"] != info.sandbox_id or row["epoch"] != info.metadata.get("instance_epoch"):
            raise EnvironmentUnavailable("late instance deletion receipt")
        self.store.transition(row, "DELETED", expected="DELETING")

    def transport_headers(self, user_id):
        row = self.store.by_user(user_id)
        return {SERVICE_AUTH_HEADER: ServiceAuthenticator(row["auth_file"]).sign()}

    async def sign_request(self, user_id, wire):
        row = self.store.by_user(user_id)
        auth = ServiceAuthenticator(row["auth_file"])
        principal = current_account()
        if principal is None:
            return auth.sign_wire(wire, service=True)  # Narrow existing maintenance purposes.
        value = await principal.check()
        if value["user_id"] != user_id:
            raise PermissionError("request does not own target instance")
        return auth.sign_wire(wire, value, principal.token)

    async def check_delivery(self, user_id):
        principal = current_account()
        if principal is None:
            return
        value = await principal.check()
        if value["user_id"] != user_id:
            raise PermissionError("response identity differs")
