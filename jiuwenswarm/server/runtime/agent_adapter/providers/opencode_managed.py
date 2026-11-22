"""Shared managed OpenCode preparation for explicit allocation and first send."""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from . import opencode_transport as transport


def relay_client(url: str, auth_file: str, project_id: str, *, shared: bool, runtime_id: str | None = None):
    from gateway.common.opencode_runtime import DEVICE_ID
    from gateway.common.security.opencode_relay_auth import OpenCodeRelayAuth
    from gateway.common.security.provider_relay_tls import relay_ssl_context

    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or not parsed.path
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.params):
        raise ValueError("Managed OpenCode relay requires a configured HTTPS path")
    if runtime_id is not None:
        if not DEVICE_ID.fullmatch(runtime_id):
            raise ValueError("Invalid managed device ID")
        base = f"{url}-device/{runtime_id}"
    else:
        base = url + "-worker" if shared else url
    context = relay_ssl_context()
    return httpx.AsyncClient(
        base_url=f"{base}/{project_id}",
        auth=OpenCodeRelayAuth(auth_file),
        verify=context if context is not None else True,
        trust_env=False,
    )


async def validate_device(runtime_id: str, project_id: str, directory: str, user_id: str):
    import os

    from gateway.common.security.service_auth import configured_service_auth

    auth = configured_service_auth()
    url = os.environ.get("JIUWENSWARM_OPENCODE_RELAY_URL", "").strip().rstrip("/")
    if not url or auth is None or auth.public_binding()["owner"]["actor_id"] != user_id:
        raise ValueError("Managed OpenCode requires a current account Worker")
    try:
        async with relay_client(url, str(auth.path), project_id, shared=True, runtime_id=runtime_id) as client:
            result = await client.get("device/check", params={"directory": directory}, timeout=10)
            result.raise_for_status()
            if result.json().get("runtime_id") != runtime_id:
                raise ValueError("Incorrect managed device identity")
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise ValueError("Managed OpenCode device is unavailable for this session") from exc


async def confirm_ready(client, directory: str, timeout: float):
    health = await transport.request_json(client, "GET", "/global/health", directory=directory,
                                          timeout=timeout, operation="session initialization")
    if not isinstance(health, dict) or health.get("healthy") is not True:
        raise RuntimeError("Managed OpenCode server is unhealthy")


async def sync_account_models(client, directory: str, timeout: float):
    from gateway.common.opencode_model_policy import account_models_revision, worker_model_policy
    from jiuwenswarm.common.model_catalog import ModelCatalog
    from .opencode_models import account_model_providers

    if not client or not (worker_model_policy() or {}).get("account_model_sync"):
        return

    async def sync(body):
        response = await client.post(
            "account-models/sync", json=body, params={"directory": directory},
            timeout=timeout,
        )
        if response.status_code == 409 and response.json().get("code") in {
            "opencode_model_sync_busy", "opencode_model_sync_changed",
        }:
            await asyncio.sleep(0.5)
            return None
        response.raise_for_status()
        return response.json()["revision"]

    try:
        async with asyncio.timeout(timeout):
            while True:
                revision = account_models_revision(account_model_providers(ModelCatalog()))
                previous = await sync({"revision": revision})
                if previous == revision:
                    return
                if previous is not None:
                    # Read again after the round trip in case the account was edited.
                    providers = account_model_providers(ModelCatalog())
                    if await sync({"provider": providers, "previous": previous}) is not None:
                        return
    except TimeoutError:
        raise RuntimeError("Timed out waiting for OpenCode to apply account models; retry when the current turn is idle") from None
