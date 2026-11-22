"""Operator-owned deployment configuration, never overridden by business input."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

from gateway.common.opencode_model_policy import MODEL_POLICY_ENV
from gateway.common.managed_codex import RELAY_ENV as CODEX_RELAY_ENV
from gateway.common.opencode_runtime import runtime_source
from gateway.common.security.opencode_relay_auth import OPENCODE_MANAGED_RELAY_PATH, OPENCODE_RELAY_PATH
from gateway.common.security.provider_relay_tls import CA_ENV, CA_TARGET

CONFIG_ENV = "CODE_PLATFORM_CLOUD_CONFIG"
OPENCODE_RELAY_ENV = "JIUWENSWARM_OPENCODE_RELAY_URL"
OPENCODE_WORKER_RELAY_PATH = OPENCODE_RELAY_PATH + "-worker"
OPENCODE_MANAGED_WORKER_RELAY_PATH = OPENCODE_MANAGED_RELAY_PATH + "-worker"


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
    opencode_provider: dict | None = None
    codex_provider: dict | None = None
    provider_relay_origin: str | None = None
    provider_relay_ca_file: str | None = None

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

    @property
    def provider_relay_base(self) -> str:
        return (self.provider_relay_origin or self.public_origin).rstrip("/") + self.api_prefix

    @property
    def uses_provider_relay_tls(self) -> bool:
        return self.provider_relay_origin is not None or self.provider_relay_ca_file is not None

    def _validate_provider_relay(self):
        origin = self.provider_relay_origin
        if origin is not None:
            if not isinstance(origin, str) or any(char.isspace() or char == "\\" for char in origin):
                raise ValueError("provider_relay_origin must be an HTTPS origin")
            target = urlsplit(origin)
            if (target.scheme != "https" or not target.hostname or target.username is not None
                    or target.password is not None or target.path not in ("", "/")
                    or "?" in origin or "#" in origin or target.port == 0):
                raise ValueError("provider_relay_origin must be an HTTPS origin")
        ca_file = self.provider_relay_ca_file
        if ca_file is not None:
            if not isinstance(ca_file, str):
                raise ValueError("provider_relay_ca_file must be an absolute deployment file path")
            path = Path(ca_file)
            if (not path.is_absolute() or ".." in path.parts or str(path) != ca_file
                    or path == path.parent or any(char in ca_file for char in (":", "\0", "\n", "\r"))
                    or any(path.is_relative_to(root) for root in (self.state_root, self.workspace_root))):
                raise ValueError("provider_relay_ca_file must be outside account and state directories")

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
        if self.opencode_provider is not None:
            self._validate_opencode_provider()
        if self.codex_provider is not None:
            self._validate_codex_provider()
        for mount in self.extra_mounts:
            target = str(mount.get("target", ""))
            if not target.startswith("/") or any(Path(target) == Path(x) or Path(target).is_relative_to(x) or Path(x).is_relative_to(target)
                                                    for x in ("/data", "/run/jiuwenswarm", CA_TARGET)):
                raise ValueError("extra mount overlaps isolated runtime storage")
        if set(dict(self.runtime_env)) & {"HOME", "PYTHONPATH", "PYTHONHOME", "JIUWENSWARM_DATA_DIR", "JIUWENSWARM_CONFIG_DIR", "JIUWENSWARM_INSTANCE_AUTH_FILE", OPENCODE_RELAY_ENV, CODEX_RELAY_ENV, MODEL_POLICY_ENV, CA_ENV}:
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
        self._validate_provider_relay()
        if self.cpu <= 0 or self.memory <= 0 or self.ready_timeout <= 0:
            raise ValueError("positive resource limits and deadline required")

    def _validate_codex_provider(self):
        from gateway.services.managed_codex_models import model_endpoint

        profile = self.codex_provider
        required = {"image", "shared_runtime", "account_allowlist", "model_endpoints"}
        if (not isinstance(profile, dict) or not required <= profile.keys()
                or profile.keys() - (required | {"cpu", "memory", "idle_seconds", "session_model_canary"})):
            raise ValueError("Managed Codex requires image, shared runtime, model endpoints and account allowlist")
        if (not self.resource_reconciler_socket or not self.public_origin.startswith("https://")
                or not isinstance(profile["image"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", profile["image"])):
            raise ValueError("Managed Codex requires HTTPS, a verified physical boundary and an immutable image")
        if self.opencode_provider and profile["image"] == self.opencode_provider["image"]:
            raise ValueError("Managed Provider images must be distinct")
        source = Path(runtime_source(profile["shared_runtime"]))
        if any(source.is_relative_to(root) or root.is_relative_to(source)
               for root in (self.workspace_root, self.state_root)):
            raise ValueError("Codex shared runtime must be outside account and state directories")
        accounts = profile["account_allowlist"]
        if (not isinstance(accounts, list)
                or any(not isinstance(account, str) or not account or account.strip() != account for account in accounts)):
            raise ValueError("Managed Codex account_allowlist must contain authenticated account IDs")
        if "session_model_canary" in profile:
            canary = profile["session_model_canary"]
            if (not isinstance(canary, dict) or not {"image", "accounts"} <= canary.keys()
                    or canary.keys() - {"image", "accounts", "memory"}
                    or not isinstance(canary["image"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", canary["image"])
                    or canary["image"] == profile["image"]
                    or self.opencode_provider and canary["image"] == self.opencode_provider["image"]
                    or not isinstance(canary["accounts"], list)
                    or any(not isinstance(account, str) or account not in accounts for account in canary["accounts"])):
                raise ValueError("Codex session model canary requires a distinct immutable image and admitted accounts")
            if "memory" in canary and (type(canary["memory"]) is not int or canary["memory"] <= 0):
                raise ValueError("Codex session model canary requires a positive memory budget")
        endpoints = profile["model_endpoints"]
        if (not isinstance(endpoints, list) or not endpoints
                or any(not isinstance(value, str) or not model_endpoint(value) for value in endpoints)):
            raise ValueError("Managed Codex requires explicitly allowed HTTPS model endpoints")
        for key in ("cpu", "memory"):
            value = profile.get(key, 1024)
            if type(value) is not int or value <= 0:
                raise ValueError("Managed Codex requires a positive resource budget")
        interval = profile.get("idle_seconds", 300)
        if type(interval) not in {int, float} or not math.isfinite(interval) or interval <= 0:
            raise ValueError("Managed Codex requires a positive idle timeout")

    def _validate_opencode_provider(self):
        if self.resource_reconciler_socket is None:
            raise ValueError("Managed OpenCode requires physical resource confirmation")
        frontend = urlsplit(self.frontend_endpoint)
        if (frontend.scheme not in {"http", "https"} or not frontend.hostname
                or frontend.username or frontend.password or frontend.query or frontend.fragment):
            raise ValueError("Managed OpenCode requires an explicit YuanRong Frontend endpoint")
        profile = self.opencode_provider
        if (not isinstance(profile, dict) or "image" not in profile
                or profile.keys() - {"image", "model_config", "cpu", "memory", "idle_seconds", "auth_transport",
                                     "account_allowlist", "admit_new_bindings", "shared_runtime", "display_name"}
                or not isinstance(profile["image"], str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", profile["image"])):
            raise ValueError("Managed OpenCode requires an immutable image")
        if "display_name" in profile:
            name = profile["display_name"]
            if (not isinstance(name, str) or name != name.strip()
                    or not 0 < len(name) <= 64 or not name.isprintable()):
                raise ValueError("Managed OpenCode display_name must contain 1 to 64 printable characters")
        if "admit_new_bindings" in profile:
            if type(profile["admit_new_bindings"]) is not bool:
                raise ValueError("Managed OpenCode admit_new_bindings must be a boolean")
            if "account_allowlist" in profile:
                raise ValueError("Managed OpenCode admission configuration has both a switch and an account_allowlist")
        if "account_allowlist" in profile:
            accounts = profile["account_allowlist"]
            if not isinstance(accounts, list) or any(
                not isinstance(account, str) or not account or account.strip() != account for account in accounts
            ):
                raise ValueError("Managed OpenCode account_allowlist must contain authenticated account IDs")
        auth_transport = profile.get("auth_transport", "basic")
        if auth_transport not in ("basic", "query"):
            raise ValueError("Unsupported OpenCode authentication transport")
        if auth_transport == "query" and frontend.hostname not in ("127.0.0.1", "::1"):
            raise ValueError("OpenCode query authentication requires a loopback YuanRong Frontend")
        if "model_config" in profile:
            if not isinstance(profile["model_config"], str):
                raise ValueError("Managed OpenCode requires a model configuration file")
            path = Path(profile["model_config"])
            if (not path.is_absolute() or path.is_relative_to(self.workspace_root)
                    or path.resolve() != path or not path.is_file()):
                raise ValueError("Managed OpenCode model configuration must be outside account workspaces")
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("Managed OpenCode model configuration must be private")
        if "shared_runtime" in profile:
            source = Path(runtime_source(profile["shared_runtime"]))
            protected = (self.workspace_root, self.state_root)
            if any(source.is_relative_to(root) or root.is_relative_to(source) for root in protected):
                raise ValueError("OpenCode shared runtime must be outside account and state directories")
        for key in ("cpu", "memory"):
            value = profile.get(key, 1024)
            if type(value) is not int or value <= 0:
                raise ValueError("Managed OpenCode requires a positive resource budget")
        interval = profile.get("idle_seconds", 300)
        if type(interval) not in {int, float} or not math.isfinite(interval) or interval <= 0:
            raise ValueError("Managed OpenCode requires a positive idle timeout")
