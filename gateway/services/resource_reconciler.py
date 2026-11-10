"""Restricted deployment completion contract; no infrastructure lifecycle client."""
import httpx


class ResourceReconciler:
    def __init__(self, socket_path):
        self.socket_path = str(socket_path)

    async def confirm_deleted(self, *, workspace, identity, image, user, instance_id):
        transport = httpx.AsyncHTTPTransport(uds=self.socket_path, retries=0)
        try:
            async with httpx.AsyncClient(transport=transport, timeout=15, trust_env=False) as client:
                response = await client.post("http://deployment/v1/confirm-deleted", json={
                    "workspace": workspace, "identity": identity, "image": image,
                    "user": user, "instance_id": instance_id})
                response.raise_for_status()
                if response.json().get("absent") is not True:
                    raise RuntimeError("physical deletion remains unconfirmed")
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError("physical deletion remains unconfirmed") from error
