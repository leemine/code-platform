"""Account service port for the existing independent identity authority.

Gateways share identity through its public API, never by copying credentials or
creating a second authority. Transport extracted from codeswarm account_transport.
"""
import json
import http.client
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit

from gateway.auth.accounts import AccountError
from gateway.auth.account_transport import authority_post


class AccountAuthorityUnavailable(RuntimeError):
    pass


class RemoteAccounts:
    def __init__(self, path, authority):
        self.path, self.authority = Path(path), authority
        self.ttl = 86400
        self.config()

    def config(self):
        if self.path.is_symlink():
            raise PermissionError("invalid account service configuration")
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or (os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
            raise PermissionError("account service configuration must be private")
        cfg = json.loads(self.path.read_text())
        url = urlsplit(cfg['url'])
        if (not url.hostname or url.username or url.password or url.query or url.fragment
                or url.scheme not in {'http', 'https'}
                or (url.scheme == 'http' and url.hostname not in {'127.0.0.1', 'localhost', '::1'})):
            raise PermissionError("a trusted HTTPS account service is required")
        return cfg

    def call(self, operation, values=None, token=None):
        try:
            status, raw = authority_post(str(self.path), self.config(), operation, values, token)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise AccountAuthorityUnavailable("account authority unavailable") from exc
        if status in {401, 403}:
            raise PermissionError("account login required")
        if status >= 500:
            raise AccountAuthorityUnavailable("account authority unavailable")
        try:
            result = json.loads(raw)
        except ValueError as exc:
            raise AccountAuthorityUnavailable("account authority invalid response") from exc
        if not isinstance(result, dict):
            raise AccountAuthorityUnavailable("account authority invalid response")
        if not 200 <= status < 300:
            raise AccountError(result.get('code', 'ACCOUNT_SERVICE_ERROR'), 'account operation failed', status)
        if operation != 'logout' and (result.get('authority') != self.authority or not isinstance(result.get('user_id'), str) or not result['user_id'].strip()):
            raise PermissionError("account authority mismatch")
        if operation == "login" and (not isinstance(result.get("token"), str) or not result["token"]):
            raise AccountAuthorityUnavailable("account authority invalid login response")
        return result

    def register(self, username, password, *, operation_id=None):
        values = {"username": username, "password": password}
        if operation_id is not None:
            values["operation_id"] = operation_id
        return self.call("register", values)

    def login(self, username, password):
        return self.call('login', {'username': username, 'password': password})

    def session(self, token):
        return self.call('session', token=token)

    def logout(self, token):
        return self.call('logout', token=token)
