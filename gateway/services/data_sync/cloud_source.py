"""Publish original cloud-role exports under the existing environment authority."""
import asyncio
import secrets
import time

from openjiuwen_protocol.e2a.gateway_normalize import e2a_from_agent_fields
from openjiuwen_protocol.message import ReqMethod

from gateway.common.security.service_auth import ServiceAuthenticator
from jiuwenswarm.data_sync.contract import SyncError, digest, identifier, inventory, project_selection


class CloudSourcePublisher:
    def __init__(self, directory, environment_store, agent_client):
        self.directory = directory
        self.environment_store = environment_store
        self.agent_client = agent_client

    @staticmethod
    def _binding(row, identity):
        if row["state"] != "ALLOCATED" or not row["instance_id"]:
            raise SyncError("SOURCE_UNAVAILABLE")
        value = ServiceAuthenticator(row["auth_file"]).public_binding()
        if (value["environment_id"] != row["environment_id"] or value["epoch"] != row["epoch"]
                or value["owner"] != {"actor_id": identity["user_id"], "authority": identity["authority"]}):
            raise SyncError("SOURCE_BINDING_CHANGED")
        return value

    async def choices(self, principal):
        identity = await principal.check()
        environments = self.environment_store()
        row = await asyncio.to_thread(environments.get, identity)
        binding = await asyncio.to_thread(self._binding, row, identity)
        send = getattr(self.agent_client, "send_existing_request", None)
        if not callable(send):
            raise SyncError("SOURCE_ROUTE_UNSUPPORTED")
        request = e2a_from_agent_fields(
            request_id="sync-" + secrets.token_hex(16), channel_id="web", session_id=None,
            req_method=ReqMethod.PROJECT_LIST, is_stream=False, timestamp=time.time(),
            user_id=identity["user_id"], params={"filter": "all", "work_mode": "code"},
        )
        async with asyncio.timeout(30):
            response = await send(request, expected_instance_id=row["instance_id"], timeout=25)
        await principal.check()
        if not response.ok or not isinstance(response.payload, dict):
            raise SyncError("SOURCE_UNAVAILABLE")
        rows = response.payload.get("projects")
        if not isinstance(rows, list) or len(rows) > 10000:
            raise SyncError("SOURCE_EXPORT_INVALID")
        def check_binding():
            with environments.guard_binding(identity, row):
                if self._binding(row, identity) != binding:
                    raise SyncError("SOURCE_BINDING_CHANGED")
        await asyncio.to_thread(check_binding)
        return {"projects": [{"native_id": identifier(item["project_id"]), "name": str(item["name"])}
                             for item in rows if item.get("work_mode") == "code" and not item.get("is_default")
                             and not item.get("hidden")]}

    async def publish(self, principal, params):
        operation = identifier(params.get("operation_id"))
        selected = project_selection(params.get("project_ids"))
        identity = await principal.check()
        scope = digest(["platform-data-sync-v1", identity["authority"], identity["user_id"]])
        environments = self.environment_store()
        row = await asyncio.to_thread(environments.get, identity)
        binding = await asyncio.to_thread(self._binding, row, identity)
        status = await asyncio.to_thread(self.directory.cloud_status, scope, row["environment_id"], operation, selected)
        if status["receipt"] is not None:
            await principal.check()
            return status["receipt"]
        send = getattr(self.agent_client, "send_existing_request", None)
        if not callable(send):
            raise SyncError("SOURCE_ROUTE_UNSUPPORTED")
        request = e2a_from_agent_fields(
            request_id="sync-" + secrets.token_hex(16), channel_id="web", session_id=None,
            req_method=ReqMethod.PROJECT_LIST, is_stream=False, timestamp=time.time(),
            user_id=identity["user_id"], params={"sync_export": True, "project_ids": selected},
        )
        await principal.check()
        async with asyncio.timeout(30):
            response = await send(request, expected_instance_id=row["instance_id"], timeout=25)
        await principal.check()
        if not response.ok:
            raise SyncError("SOURCE_UNAVAILABLE")
        payload = response.payload
        if not isinstance(payload, dict) or set(payload) != {"binding", "items", "complete", "total", "inventory_digest"}:
            raise SyncError("SOURCE_EXPORT_UNSUPPORTED")
        items = inventory(payload["items"])
        if (payload["binding"] != binding or payload["complete"] is not True
                or type(payload["total"]) is not int or payload["total"] != len(items)
                or payload["inventory_digest"] != digest(items)
                or any(item["native_id"] not in selected for item in items)):
            raise SyncError("SOURCE_EXPORT_INVALID")

        def commit():
            # No network or await under this short original environment lock.
            with environments.guard_binding(identity, row):
                if self._binding(row, identity) != binding:
                    raise SyncError("SOURCE_BINDING_CHANGED")
                workspace = digest([row["environment_id"], row["workspace"], binding["workspace_digest"]])
                return self.directory.publish_cloud(scope, row["environment_id"], row["epoch"], workspace,
                    operation, selected, status["revision"], items)

        result = await asyncio.to_thread(commit)
        await principal.check()
        return result
