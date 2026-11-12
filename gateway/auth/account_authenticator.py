"""Account authority adapter for the existing Gateway authentication contract."""
from __future__ import annotations

import asyncio
from gateway.auth.request_scope import current_scope as _current
from dataclasses import dataclass, field

from gateway.auth.accounts import credential
from gateway.extensions.auth.credential_authenticator import AuthContext, AuthResult, CredentialAuthenticator



@dataclass(frozen=True)
class AccountPrincipal:
    accounts: object = field(repr=False)
    token: str = field(repr=False)
    user_id: str
    authority: str

    async def check(self):
        value = await asyncio.to_thread(self.accounts.session, self.token)
        if value["user_id"] != self.user_id or value["authority"] != self.authority:
            raise PermissionError("authenticated account changed")
        return value

    async def activate(self):
        await self.check()
        _current.set(self)


def current_account():
    return _current.get()


class AccountAuthenticator(CredentialAuthenticator):
    def __init__(self, accounts, public_origin=None):
        self.accounts = accounts
        self.public_origin = public_origin

    async def authenticate(self, context: AuthContext) -> AuthResult:
        token = credential(context.headers) or str(context.credentials.get("token") or "")
        try:
            if self.public_origin:
                from urllib.parse import urlsplit
                headers = {k.lower(): v for k, v in context.headers.items()}
                origin = headers.get("origin")
                if origin:
                    actual, expected = urlsplit(origin), urlsplit(self.public_origin)
                    if (actual.scheme, actual.hostname, actual.port or 443) != (expected.scheme, expected.hostname, expected.port or 443):
                        raise PermissionError("origin denied")
                elif context.channel_type == "web" and headers.get("cookie") and not headers.get("authorization"):
                    raise PermissionError("browser websocket origin required")
            value = await asyncio.to_thread(self.accounts.session, token)
            principal = AccountPrincipal(self.accounts, token, value["user_id"], value["authority"])
            _current.set(principal)
            connection_scope = next((v for k, v in context.headers.items()
                                     if k.lower() == "x-jiuwen-connection-scope"), "")
            return AuthResult(success=True, user_id=principal.user_id, extensions={
                "authority": principal.authority, "routing_user_id": principal.user_id,
                "request_guard": principal.activate,
                "delivery_guard": principal.check,
                "rpc_only_prefix": "data_sync." if context.channel_type == "web" and connection_scope == "data-sync" else "",
            })
        except (PermissionError, RuntimeError, ValueError, OSError) as exc:
            from gateway.auth.remote_accounts import AccountAuthorityUnavailable
            _current.set(None)
            code = "AUTHORITY_UNAVAILABLE" if isinstance(exc, AccountAuthorityUnavailable) else "UNAUTHORIZED"
            return AuthResult(success=False, error="account authentication unavailable", extensions={"error_code": code})
