"""Short-lived Worker assertions for a fixed managed Provider request."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time

from gateway.common.security.service_auth import ServiceAuthenticator, canonical


def _request_digest(method: str, path: str, directory: str, body: bytes) -> str:
    return hashlib.sha256(canonical([method, path, directory, hashlib.sha256(body).hexdigest()])).hexdigest()


def _signature(config: dict, claims: dict) -> str:
    return hmac.new(bytes.fromhex(config["signing_key"]), canonical(claims), hashlib.sha256).hexdigest()


def sign_assertion(worker: ServiceAuthenticator, *, audience: str, method: str,
                   path: str, directory: str, body: bytes) -> str:
    config = worker._config()
    claims = {
        "aud": audience,
        "actor": config["login_owner"]["actor_id"],
        "environment": config["instance_id"],
        "epoch": config["epoch"],
        "exp": int(time.time()) + 15,
        "nonce": secrets.token_hex(24),
        "request": _request_digest(method, path, directory, body),
    }
    return canonical({"claims": claims, "signature": _signature(config, claims)}).decode()


def parse_assertion(header: str, *, audience: str) -> tuple[dict, str]:
    if not header or len(header) > 4096:
        raise PermissionError("Worker assertion required")
    value = json.loads(header)
    claims, signature = value["claims"], value["signature"]
    if (set(claims) != {"aud", "actor", "environment", "epoch", "exp", "nonce", "request"}
            or claims["aud"] != audience
            or any(not isinstance(claims[key], str) for key in ("actor", "environment", "nonce", "request"))
            or type(claims["epoch"]) is not int or type(claims["exp"]) is not int
            or not re.fullmatch(r"[0-9a-f]{48}", claims["nonce"])
            or not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature)):
        raise PermissionError("Invalid Worker assertion")
    return claims, signature


def verify_assertion(auth_file, claims: dict, signature: str, *, method: str, path: str,
                     directory: str, body: bytes) -> None:
    config = ServiceAuthenticator(auth_file)._config()
    now = time.time()
    if (not now < claims["exp"] <= now + 15
            or config["login_owner"]["actor_id"] != claims["actor"]
            or config["instance_id"] != claims["environment"] or config["epoch"] != claims["epoch"]
            or claims["request"] != _request_digest(method, path, directory, body)
            or not hmac.compare_digest(signature, _signature(config, claims))):
        raise PermissionError("Invalid Worker assertion")
