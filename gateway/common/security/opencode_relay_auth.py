"""Bind managed OpenCode requests to the current account Worker and request."""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from gateway.common.security.provider_relay_auth import parse_assertion as parse_provider_assertion
from gateway.common.security.provider_relay_auth import sign_assertion, verify_assertion as verify_provider_assertion
from gateway.common.security.service_auth import ServiceAuthenticator


HEADER = "X-Jiuwen-Opencode-Assertion"
OPENCODE_RELAY_PATH = "/provider/opencode"
OPENCODE_MANAGED_RELAY_PATH = "/provider/managed/opencode"
_AUDIENCE = "jiuwenswarm-managed-opencode"


def compatible_relay_url(url: str) -> str | None:
    """Return the other deployed path on the same origin and API prefix."""
    parsed = urlsplit(url)
    for path, alias in (
        (OPENCODE_MANAGED_RELAY_PATH, OPENCODE_RELAY_PATH),
        (OPENCODE_RELAY_PATH, OPENCODE_MANAGED_RELAY_PATH),
    ):
        if parsed.path.endswith(path):
            return parsed._replace(path=parsed.path[:-len(path)] + alias).geturl()
    return None


class OpenCodeRelayAuth(httpx.Auth):
    requires_request_body = True

    def __init__(self, auth_file):
        self.worker = ServiceAuthenticator(auth_file)

    def auth_flow(self, request):
        request.headers[HEADER] = sign_assertion(
            self.worker, audience=_AUDIENCE, method=request.method, path=request.url.path,
            directory=request.url.params.get("directory", ""), body=request.content,
        )
        yield request


def parse_assertion(header: str) -> tuple[dict, str]:
    return parse_provider_assertion(header, audience=_AUDIENCE)


def verify_assertion(auth_file, claims: dict, signature: str, *, method: str, path: str,
                     directory: str, body: bytes) -> None:
    verify_provider_assertion(auth_file, claims, signature, method=method, path=path, directory=directory, body=body)
