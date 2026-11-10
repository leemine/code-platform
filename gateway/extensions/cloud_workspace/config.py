"""Operator-owned deployment configuration, never overridden by business input."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_ENV = "CODE_PLATFORM_CLOUD_CONFIG"


@dataclass(frozen=True)
class CloudConfig:
    authority: str
    public_origin: str
    state_root: Path
    workspace_root: Path
    image: str
    frontend_endpoint: str
    function_version_urn: str
    api_prefix: str = "/api/v1/auth/organization"
    namespace: str = "default"
    runtime: str = "python3.11"
    runtime_user: str | None = None
    cpu: int = 2000
    memory: int = 4096
    ready_timeout: float = 120
    registration_enabled: bool = False
    account_backend_config: str | None = None
    runtime_command: tuple = ("/opt/venv/bin/jiuwenswarm-agentserver", "--port", "18092")
    extra_mounts: tuple = ()
    runtime_env: tuple = ()
    resource_pool_id: str | None = None
    resource_reconciler_socket: str | None = None

    @classmethod
    def load(cls, path=None):
        values = json.loads(Path(path or os.environ[CONFIG_ENV]).read_text())
        for key in ("state_root", "workspace_root"):
            values[key] = Path(values[key])
        for key in ("extra_mounts", "runtime_env", "runtime_command"):
            if key in values:
                values[key] = tuple(values[key])
        cfg = cls(**values)
        cfg.validate()
        return cfg

    def runtime_profile(self):
        profile = {"image_digest": self.image, "runtime": self.runtime,
                "runtime_user": self._runtime_account(), "cpu": self.cpu, "memory": self.memory,
                "namespace": self.namespace, "command": list(self.runtime_command),
                "extra_mounts": list(self.extra_mounts), "runtime_env": dict(self.runtime_env)}
        if self.resource_pool_id is not None:
            profile["placement"] = {"pool_id": self.resource_pool_id,
                                    "frontend_endpoint": self.frontend_endpoint.rstrip("/"),
                                    "namespace": self.namespace,
                                    "function_version_urn": self.function_version_urn}
        if self.resource_reconciler_socket is not None:
            profile["physical_verification"] = True
        return profile

    def _runtime_account(self):
        # Yuanrong also uses this login in /home/<user>; Docker UID:GID syntax
        # would introduce an extra colon into its bind-mount specification.
        if os.name != "posix":
            raise ValueError("cloud runtime requires a POSIX deployment account")
        import pwd
        try:
            name = self.runtime_user or pwd.getpwuid(os.getuid()).pw_name
            if not re.fullmatch(r"[a-z_][a-z0-9_-]*[$]?", name):
                raise ValueError("runtime_user must be a deployment login name")
            account = pwd.getpwnam(name)
        except KeyError as exc:
            raise ValueError("runtime deployment account is missing") from exc
        if (account.pw_uid, account.pw_gid) != (os.getuid(), os.getgid()):
            raise ValueError("runtime uid/gid must match the private mounted files")
        return name

    def validate(self):
        if not self.account_backend_config:
            raise ValueError("independent account authority configuration is required")
        if self.resource_pool_id is not None:
            if (not isinstance(self.resource_pool_id, str)
                    or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", self.resource_pool_id)):
                raise ValueError("resource_pool_id must identify a preprovisioned execution pool")
            endpoint = urlsplit(self.frontend_endpoint)
            if (endpoint.scheme not in {"http", "https"} or not endpoint.hostname
                    or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                    or not self.namespace or not self.function_version_urn):
                raise ValueError("execution pool requires an explicit endpoint, namespace and function URN")
        if self.resource_reconciler_socket is not None:
            endpoint = Path(self.resource_reconciler_socket)
            if not endpoint.is_absolute() or ".." in endpoint.parts:
                raise ValueError("resource_reconciler_socket must be an absolute deployment path")
        self._runtime_account()
        for mount in self.extra_mounts:
            target = str(mount.get("target", ""))
            if not target.startswith("/") or any(Path(target) == Path(x) or Path(target).is_relative_to(x) or Path(x).is_relative_to(target)
                                                    for x in ("/data", "/run/jiuwenswarm")):
                raise ValueError("extra mount overlaps isolated runtime storage")
        if set(dict(self.runtime_env)) & {"HOME", "PYTHONPATH", "PYTHONHOME", "JIUWENSWARM_DATA_DIR", "JIUWENSWARM_CONFIG_DIR", "JIUWENSWARM_INSTANCE_AUTH_FILE"}:
            raise ValueError("runtime environment overrides isolated paths")
        public = urlsplit(self.public_origin)
        if (public.scheme != "https" or not public.hostname or public.username or public.password
                or public.path not in ("", "/") or public.query or public.fragment):
            raise ValueError("public_origin must be a trusted HTTPS origin")
        if not self.authority or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image):
            raise ValueError("authority and immutable runtime image are required")
        if (not self.api_prefix.startswith("/") or self.api_prefix.endswith("/")
                or "{" in self.api_prefix or ".." in self.api_prefix):
            raise ValueError("invalid API prefix")
        if not self.state_root.is_absolute() or not self.workspace_root.is_absolute():
            raise ValueError("storage roots must be absolute")
        if (self.state_root == self.workspace_root or self.state_root.is_relative_to(self.workspace_root)
                or self.workspace_root.is_relative_to(self.state_root)):
            raise ValueError("control and workspace roots must be separate")
        if self.cpu <= 0 or self.memory <= 0 or self.ready_timeout <= 0:
            raise ValueError("positive resource limits and deadline required")
