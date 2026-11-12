"""Instance transport authentication extracted from codeswarm's assertion codec.

Preserves the existing body hash, target/epoch, audience, nonce and short-lived
Gateway assertion wire format. No account database or Gateway-wide key enters a
Runtime. This module has no account/project/Runtime lifecycle dependencies.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time
from http import HTTPStatus

SERVICE_AUTH_ENV = "JIUWENSWARM_INSTANCE_AUTH_FILE"
SERVICE_AUTH_HEADER = "X-Jiuwen-Gateway-Assertion"
ASSERTION = "_organization_assertion"


def service_request(payload):
    """Narrow existing installation/cron purposes, extracted from codeswarm."""
    method = payload.get("method") or payload.get("req_method")
    channel = payload.get("channel") or payload.get("channel_id")
    return method in {"config.get", "models.list", "project.lifecycle"} or (
        channel == "__cron__" and method in {
            "project.cron.resolve_binding", "cron.sessions.delete", "session.create",
            "proactive.tick", "chat.send", "history.append_record", "chat.cancel",
            "cron.jobs.sync", "cron.command.ack", "cron.run_now.ack",
        })


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


class ServiceAuthenticator:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._seen: dict[str, float] = {}
        self._config()

    def public_binding(self):
        """Return transport binding evidence without exposing its signing key."""
        cfg = self._config()
        return {"environment_id": cfg["instance_id"], "epoch": cfg["epoch"],
                "owner": dict(cfg["login_owner"]),
                "workspace_digest": hashlib.sha256(canonical(cfg["workspace"])).hexdigest()}

    def _config(self):
        if self.path.is_symlink():
            raise PermissionError("invalid instance credential")
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or (
            os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077)
        ):
            raise PermissionError("instance credential must be private")
        cfg = json.loads(self.path.read_text())
        owner = cfg.get("login_owner", {})
        if (set(cfg) - {"revocations_file"} != {"mode", "instance_id", "epoch", "workspace", "login_owner", "signing_key"}
                or cfg["mode"] != "user_instance" or type(cfg["epoch"]) is not int or cfg["epoch"] < 1
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", str(cfg["instance_id"]))
                or not Path(cfg["workspace"]).is_absolute()
                or set(owner) != {"actor_id", "authority"}
                or any(not isinstance(v, str) or not v.strip() for v in owner.values())
                or not re.fullmatch(r"[0-9a-f]{64}", str(cfg["signing_key"]))):
            raise PermissionError("invalid instance binding")
        if "revocations_file" in cfg and cfg["revocations_file"] != "revocations.json":
            raise PermissionError("invalid revocation file")
        return cfg

    def _check_revocation(self, cfg, digest):
        if "revocations_file" in cfg:
            path = self.path.parent / cfg["revocations_file"]
            if path.is_symlink():
                raise PermissionError("invalid revocation file")
            records = json.loads(path.read_text())
            if digest in records and (records[digest] is True or float(records[digest]) > time.time()):
                raise PermissionError("account session revoked")

    @property
    def instance_id(self):
        return self._config()["instance_id"]

    def sign_wire(self, payload: dict, principal=None, token=None, *, service=False) -> dict:
        cfg = self._config()
        wire = dict(payload)
        wire.pop(ASSERTION, None)
        wire["_instance_target"] = {"instance_id": cfg["instance_id"], "epoch": cfg["epoch"]}
        owner = cfg["login_owner"]
        if principal is not None and (principal["user_id"] != owner["actor_id"] or principal["authority"] != owner["authority"]):
            raise PermissionError("login does not own this instance")
        if service and (principal is not None or not service_request(payload)):
            raise PermissionError("invalid maintenance purpose")
        if principal is None and not service and payload != {"upgrade": "agentserver"}:
            raise PermissionError("account authorization required for requests")
        if principal is not None:
            if not token:
                raise PermissionError("account credential required")
            self._check_revocation(cfg, hashlib.sha256(token.encode()).hexdigest())
        now = time.time()
        claims = {"purpose": "service" if service else ("user" if principal is not None else "upgrade"), "aud": "jiuwenswarm-agentserver", "iat": now, "exp": now + 15,
                  "nonce": secrets.token_hex(24),
                  "credential": hashlib.sha256(token.encode()).hexdigest() if principal is not None and token else None,
                  "actor": owner["actor_id"] if principal is not None else None,
                  "authority": owner["authority"] if principal is not None else None,
                  "body": hashlib.sha256(canonical(wire)).hexdigest()}
        signature = hmac.new(bytes.fromhex(cfg["signing_key"]), canonical(claims), hashlib.sha256).hexdigest()
        wire[ASSERTION] = {"claims": claims, "signature": signature}
        return wire

    def sign(self) -> str:
        return json.dumps(self.sign_wire({"upgrade": "agentserver"}), separators=(",", ":"))

    def verify_wire(self, payload: dict, *, upgrade=False) -> dict:
        cfg = self._config()
        wire = dict(payload)
        assertion = wire.pop(ASSERTION)
        claims, signature = assertion["claims"], assertion["signature"]
        now = time.time()
        issued, expiry = float(claims["iat"]), float(claims["exp"])
        expected = hmac.new(bytes.fromhex(cfg["signing_key"]), canonical(claims), hashlib.sha256).hexdigest()
        target = {"instance_id": cfg["instance_id"], "epoch": cfg["epoch"]}
        if (wire.get("_instance_target") != target
                or not isinstance(signature, str) or not hmac.compare_digest(signature, expected)
                or claims.get("aud") != "jiuwenswarm-agentserver"
                or not math.isfinite(issued) or not math.isfinite(expiry)
                or not issued <= now < expiry <= issued + 20
                or claims.get("body") != hashlib.sha256(canonical(wire)).hexdigest()):
            raise PermissionError("invalid Gateway assertion")
        owner = cfg["login_owner"]
        if upgrade:
            if (set(wire) != {"upgrade", "_instance_target"} or wire["upgrade"] != "agentserver"
                    or claims.get("purpose") not in (None, "upgrade") or claims.get("actor") is not None):
                raise PermissionError("invalid upgrade purpose")
        elif claims.get("purpose") == "service":
            if not service_request(wire) or claims.get("actor") is not None or claims.get("credential") is not None:
                raise PermissionError("invalid maintenance purpose")
        elif (claims.get("purpose") not in (None, "user") or claims.get("actor") != owner["actor_id"] or claims.get("authority") != owner["authority"]
              or not re.fullmatch(r"[0-9a-f]{64}", str(claims.get("credential", "")))):
            raise PermissionError("authenticated instance owner required")
        if not upgrade and claims.get("purpose") != "service":
            self._check_revocation(cfg, claims["credential"])
        self._seen = {nonce: end for nonce, end in self._seen.items() if end > now}
        nonce = claims["nonce"]
        if not isinstance(nonce, str) or len(nonce) != 48 or nonce in self._seen or len(self._seen) >= 10000:
            raise PermissionError("replayed or overloaded Gateway assertion")
        self._seen[nonce] = expiry
        return owner

    def verify(self, raw: str | None) -> bool:
        try:
            if not raw or len(raw) > 4096:
                return False
            self.verify_wire(json.loads(raw), upgrade=True)
            return True
        except (ValueError, TypeError, KeyError, PermissionError, OSError):
            return False


_cached_auth: tuple[str, ServiceAuthenticator] | None = None


def configured_service_auth():
    global _cached_auth
    path = os.environ.get(SERVICE_AUTH_ENV)
    if not path:
        if os.environ.get("CODE_PLATFORM_ROLE") == "account-instance":
            raise PermissionError("account instance authentication is required")
        return None
    if _cached_auth is None or _cached_auth[0] != path:
        _cached_auth = (path, ServiceAuthenticator(path))
    auth = _cached_auth[1]
    if os.environ.get("CODE_PLATFORM_ROLE") == "account-instance":
        cfg = auth._config()
        data = os.environ.get("JIUWENSWARM_DATA_DIR", "")
        if not data or Path(data).resolve() / "agent" != Path(cfg["workspace"]).resolve():
            raise PermissionError("instance workspace differs from trusted binding")
    return auth


def check_service_handshake(args: tuple):
    from gateway.common.security.ws_origin import extract_handshake_request, get_header_value
    try:
        auth = configured_service_auth()
        if auth is None:
            return None
        _, headers = extract_handshake_request(args)
        if auth.verify(get_header_value(headers, SERVICE_AUTH_HEADER)):
            return None
    except (OSError, ValueError, KeyError, PermissionError):
        pass
    body = b"Unauthorized service\n"
    headers = [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))]
    if args and not isinstance(args[0], str):
        from websockets.datastructures import Headers
        from websockets.http11 import Response
        return Response(401, "Unauthorized", Headers(headers), body)
    return HTTPStatus.UNAUTHORIZED, headers, body


def bind_service_request(request):
    auth = configured_service_auth()
    if auth is not None:
        owner = auth._config()["login_owner"]["actor_id"]
        if request.user_id and request.user_id != owner:
            raise PermissionError("instance request owner mismatch")
        request.user_id = owner
    return request


def verify_service_message(data: dict):
    try:
        auth = configured_service_auth()
        if auth is not None:
            owner = auth.verify_wire(data)
            supplied = data.get("user_id")
            if supplied and supplied != owner["actor_id"]:
                raise PermissionError("instance owner mismatch")
            data["user_id"] = owner["actor_id"]
    except PermissionError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PermissionError("invalid instance authorization") from exc
