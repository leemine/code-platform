"""Wire names and model validation shared by the Codex Worker and Gateway."""

from dataclasses import dataclass, field
from hashlib import sha256
from urllib.parse import urlsplit

from gateway.common.security.service_auth import canonical

PROFILE_ID = "codex-cloud"
MODEL_UNAVAILABLE = "RUNTIME_DEVICE_MODEL_UNAVAILABLE"

AUDIENCE = "jiuwenswarm-managed-codex"
RELAY_PATH = "/provider/managed/codex"
RELAY_ENV = "CODE_PLATFORM_MANAGED_CODEX_RELAY"
ASSERTION_HEADER = "X-Jiuwen-Codex-Assertion"
DIRECTORY_HEADER = "X-Jiuwen-Codex-Directory"
MAX_FRAME_BYTES = 8 * 1024 * 1024
NATIVE_PORT = 18768
IDENTITY_TARGET = "/run/codex"
MODEL_FIELDS = frozenset({"model", "base_url", "api_key"})
EFFECTIVE_CONTEXT_PERCENT = 95


def validate_device_model_id(value):
    if (not isinstance(value, str) or not value or value != value.strip()
            or not value.isprintable() or len(value) > 200):
        raise ValueError("Invalid Codex device model ID")
    return value


def model_endpoint(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment
            or not url.path.startswith("/") or "\\" in url.path or ".." in url.path.split("/")
            or any(ord(char) <= 32 for char in value)):
        raise ValueError("Managed Codex needs an explicit HTTPS model endpoint")
    if url.port not in (None, 443):
        raise ValueError("Managed Codex model endpoint must use standard HTTPS")
    return url._replace(path=url.path.rstrip("/")).geturl()


@dataclass(frozen=True)
class ManagedModel:
    name: str
    endpoint: str
    key: str = field(repr=False)
    context_window: int | None = None

    @property
    def revision(self) -> str:
        return sha256(canonical([self.name, self.endpoint, self.key])).hexdigest()

    @classmethod
    def parse(cls, data, allowed_endpoints):
        if not isinstance(data, dict) or set(data) not in (MODEL_FIELDS, MODEL_FIELDS | {"context_window"}):
            raise ValueError("Managed Codex model fields differ")
        name, base, key = (data[k] for k in ("model", "base_url", "api_key"))
        if (not isinstance(name, str) or not name.strip() or len(name) > 200
                or not isinstance(base, str) or not isinstance(key, str) or not key.strip()
                or len(key) > 8192 or any(not 32 < ord(char) < 127 for char in key)):
            raise ValueError("Managed Codex model is not configured")
        endpoint = model_endpoint(base)
        if endpoint not in allowed_endpoints:
            raise ValueError("Selected model endpoint is outside managed Codex admission")
        context_window = data.get("context_window")
        if "context_window" in data and (type(context_window) is not int
                or not 0 < context_window <= (2**63 - 1) // EFFECTIVE_CONTEXT_PERCENT):
            raise ValueError("Invalid managed Codex model context window")
        return cls(name, endpoint, key, context_window)
