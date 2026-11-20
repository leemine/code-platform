"""Restricted deployment completion contract; no infrastructure lifecycle client."""
import httpx


class ResourceReconciler:
    def __init__(self, socket_path):
        self.socket_path = str(socket_path)

    async def confirm_deleted(self, *, workspace, identity, image, user, instance_id):
        result = await self._inspect("confirm-deleted", "physical deletion remains unconfirmed",
                                     workspace, identity, image, user, instance_id)
        if result.get("absent") is not True:
            raise RuntimeError("physical deletion remains unconfirmed")

    async def confirm_opencode_unavailable(self, *, workspace, identity, image, user, instance_id):
        result = await self._inspect("confirm-opencode-unavailable", "physical fault remains unconfirmed",
                                     workspace, identity, image, user, instance_id)
        return result.get("unavailable") is True

    async def _inspect(self, operation, error_message, workspace, identity, image, user, instance_id):
        transport = httpx.AsyncHTTPTransport(uds=self.socket_path, retries=0)
        try:
            async with httpx.AsyncClient(transport=transport, timeout=15, trust_env=False) as client:
                response = await client.post(f"http://deployment/v1/{operation}", json={
                    "workspace": workspace, "identity": identity, "image": image,
                    "user": user, "instance_id": instance_id})
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError("invalid physical confirmation response")
                return result
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError(error_message) from error
