"""Deployment-side completion proof for the existing instance deletion chain.

No creator, sweeper, scheduler or account database. A durable dispatch fence and
Docker's unique container name make the original calls observable after failure.
Only a proven, never-started orphan may be removed by a deletion confirmation.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
from ipaddress import IPv4Address
import json
import os
from pathlib import Path
import re
import socket
import stat
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import urlopen

LABEL = "io.code-platform.physical-scope"
LIMIT = 4 * 1024 * 1024
OPENCODE_BINDING = re.compile(r"[a-f0-9]{32}")
IMAGE_DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
CONTAINER_ID = re.compile(r"[a-f0-9]{64}")
PROJECT_ROOT = Path("/data/agent/workspace")
STATE_TARGET = "/state"
PROVIDER_IDENTITY_TARGET = "/run/opencode"
CODEX_IDENTITY_TARGET = "/run/codex"
OPENCODE_PORT = 4096
CODEX_PORT = 18768

from opencode_runtime_asset import RUNTIME_TARGET, asset_rules, runtime_identity, tree_digest


class PhysicalResources:
    def __init__(self, boundary, journal_root: Path, identity_root: Path, identity_target: str,
                 upstream: str, frontend: str, timeout: float = 10, *, provider_root=None, provider_images=(),
                 runtime_assets=(), codex_root=None, codex_images=(), codex_runtime_assets=(), codex_security=None):
        self.boundary = boundary
        self.root, self.identity_root = Path(journal_root), Path(identity_root)
        self.identity_target = identity_target
        self.upstream, self.frontend, self.timeout = upstream, frontend.rstrip("/"), timeout
        self.provider_root = Path(provider_root) if provider_root is not None else None
        self.provider_images = frozenset(provider_images)
        self.codex_root = Path(codex_root) if codex_root is not None else None
        self.codex_images = frozenset(codex_images)
        self.codex_security = codex_security
        self.runtime_assets = {**asset_rules(runtime_assets, self.provider_images),
                               **asset_rules(codex_runtime_assets, self.codex_images)}
        self._verified_runtime_assets = {}

        for path, uid in [(self.root, os.getuid()), (self.identity_root, boundary.uid)]:
            self._private(path, uid)
        if (self.root.is_relative_to(boundary.workspace_root)
                or boundary.workspace_root.is_relative_to(self.root)
                or self.root.is_relative_to(self.identity_root) or self.identity_root.is_relative_to(self.root)):
            raise ValueError("physical journal must be separate from workspace and identity roots")
        endpoint = urlsplit(frontend)
        if (endpoint.scheme not in {"http", "https"} or not endpoint.hostname or endpoint.username
                or endpoint.password or endpoint.query or endpoint.fragment):
            raise ValueError("explicit trusted instance frontend required")
        if not identity_target.startswith("/") or identity_target == "/data":
            raise ValueError("distinct identity mount target required")
        if bool(self.provider_root) != bool(self.provider_images) or (
                self.provider_images and (identity_target == PROVIDER_IDENTITY_TARGET
                    or self.provider_images & boundary.images
                    or any(not isinstance(image, str) or not IMAGE_DIGEST.fullmatch(image)
                           for image in self.provider_images))):
            raise ValueError("OpenCode physical admission requires a distinct root and image allowlist")
        if self.provider_root is not None:
            self._private(self.provider_root, boundary.uid)
            roots = (self.root, self.identity_root, boundary.workspace_root, boundary.log_root, *boundary.shared)
            if any(self.provider_root.is_relative_to(root) or root.is_relative_to(self.provider_root) for root in roots):
                raise ValueError("OpenCode physical storage must be separate from other runtime roots")
        if (bool(self.codex_root) != bool(self.codex_images) or bool(self.codex_images) != bool(codex_security)
                or self.codex_images & (self.provider_images | boundary.images)
                or any(image not in self.runtime_assets for image in self.codex_images)
                or (self.codex_images and identity_target == CODEX_IDENTITY_TARGET)):
            raise ValueError("Codex admission requires a distinct root, shared runtime and pinned security")
        if self.codex_root is not None:
            self._private(self.codex_root, boundary.uid)
            roots = (self.root, self.identity_root, boundary.workspace_root, boundary.log_root, *boundary.shared)
            if self.provider_root is not None:
                roots += (self.provider_root,)
            if any(self.codex_root.is_relative_to(root) or root.is_relative_to(self.codex_root) for root in roots):
                raise ValueError("Codex physical storage must be separate from other runtime roots")

    @staticmethod
    def _private(path: Path, uid: int) -> None:
        if not path.is_absolute() or path.resolve() != path:
            raise ValueError("noncanonical physical scope")
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("physical scope owner or mode differs")

    def scope(self, workspace: str, identity: str, image: str, user: str) -> dict:
        if self.is_provider_image(image):
            return self._provider_scope(workspace, identity, image, user)
        workspace, identity = Path(workspace), Path(identity)
        if workspace.parent != self.boundary.workspace_root or not self.boundary.workspace_name_pattern.fullmatch(workspace.name):
            raise ValueError("workspace is outside deployment scope")
        if identity == self.identity_root or not identity.is_relative_to(self.identity_root):
            raise ValueError("identity is outside deployment scope")
        self._private(workspace, self.boundary.uid)
        self._private(identity, self.boundary.uid)
        if image not in self.boundary.images or user != self.boundary.user:
            raise ValueError("unapproved physical image or user")
        slot = hashlib.sha256(str(workspace).encode()).hexdigest()
        key = hashlib.sha256((str(workspace) + "\0" + str(identity)).encode()).hexdigest()
        return {"workspace": str(workspace), "identity": str(identity), "image": image,
                "user": user, "slot": slot, "key": key, "name": "cpw-" + slot}

    def is_provider_image(self, image) -> bool:
        return isinstance(image, str) and image in (self.provider_images | self.codex_images)

    def _provider_scope(self, workspace: str, identity: str, image: str, user: str) -> dict:
        state, generation = Path(workspace), Path(identity)
        binding = state.parent
        codex = image in self.codex_images
        role = "codex" if codex else "opencode"
        physical_root = self.codex_root if codex else self.provider_root
        if (state.name != "state" or binding.parent != physical_root
                or generation.parent != binding or not OPENCODE_BINDING.fullmatch(binding.name)
                or not OPENCODE_BINDING.fullmatch(generation.name) or user != self.boundary.user):
            raise ValueError("invalid Provider physical scope")
        for directory in (binding, state, generation):
            self._private(directory, self.boundary.uid)
        operation_scope = generation / "scope.json"
        if operation_scope.exists() or operation_scope.is_symlink():
            anchor = self._read_provider_definition(binding / "scope.json", binding.name, None, user)
            definition = self._read_provider_definition(operation_scope, binding.name, image, user, generation=True)
            if any(anchor[key] != definition[key] for key in anchor if key != "image"):
                raise ValueError("OpenCode generation workspace differs from its binding")
        else:
            definition = self._read_provider_definition(binding / "scope.json", binding.name, image, user)
        expected_asset = self.runtime_assets.get(image)
        if definition.get("shared_runtime") != (str(expected_asset) if expected_asset else None):
            raise ValueError("OpenCode image runtime asset differs from node policy")

        slot = hashlib.sha256(str(state).encode()).hexdigest()
        key = hashlib.sha256((str(state) + "\0" + str(generation)).encode()).hexdigest()
        scope = {"workspace": str(state), "identity": str(generation), "image": image,
                "user": user, "slot": slot, "key": key, "name": ("cpc-" if codex else "cpo-") + slot,
                "role": role, "account_workspace": definition["account_workspace"],
                "project_source": definition["project_source"], "project_target": definition["project_target"]}
        if expected_asset:
            scope["shared_runtime"] = str(expected_asset)
        return scope


    def _read_provider_definition(self, path: Path, binding_id: str, image: str | None, user: str,
                                  *, generation=False) -> dict:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as record:
            info = os.fstat(record.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.boundary.uid
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise ValueError("invalid private OpenCode scope definition")
            raw = record.read(8193)
        if len(raw) > 8192:
            raise ValueError("OpenCode scope definition too large")
        value = json.loads(raw)
        fields = {"version", "binding_id", "account_workspace", "project_source", "project_target", "image", "user"}
        if generation and isinstance(value, dict) and "shared_runtime" in value:
            fields.add("shared_runtime")
        if (not isinstance(value, dict) or set(value) != fields or type(value["version"]) is not int
                or value["version"] not in (1, 2) or value["binding_id"] != binding_id
                or not isinstance(value["image"], str) or not IMAGE_DIGEST.fullmatch(value["image"])
                or (image is not None and value["image"] != image) or value["user"] != user):
            raise ValueError("OpenCode scope definition differs")
        account, project, target = (Path(value[field]) for field in ("account_workspace", "project_source", "project_target"))
        if (account.parent != self.boundary.workspace_root or not self.boundary.workspace_name_pattern.fullmatch(account.name)
                or account.resolve() != account or str(account) != value["account_workspace"]
                or not target.is_relative_to(PROJECT_ROOT) or (target == PROJECT_ROOT) != (value["version"] == 2)
                or ".." in target.parts or str(target) != value["project_target"]
                or project != account / "agent/workspace" / target.relative_to(PROJECT_ROOT)
                or project.resolve() != project or str(project) != value["project_source"]):
            raise ValueError("OpenCode project is outside its account binding")
        return value

    @staticmethod
    def _provider_create_mounts(request: dict) -> dict[str, tuple[str, bool]]:
        host = request.get("HostConfig", {})
        mounts = {}
        for mount in host.get("Mounts", []):
            if mount.get("Type") != "bind":
                raise ValueError("OpenCode physical storage requires bind mounts")
            readonly = mount.get("ReadOnly", False)
            target = mount["Target"]
            if target in mounts or type(readonly) is not bool:
                raise ValueError("ambiguous OpenCode physical mount")
            if target == RUNTIME_TARGET:
                options = mount.get("BindOptions") or {}
                if set(options) - {"Propagation"} or options.get("Propagation") not in (None, "", "rprivate"):
                    raise ValueError("OpenCode shared runtime mount must use private propagation")
            mounts[target] = (mount["Source"], readonly)
        for bind in host.get("Binds", []):
            parts = bind.split(":")
            if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] not in ("ro", "rw")):
                raise ValueError("invalid OpenCode bind syntax")
            source, target = parts[:2]
            if target in mounts:
                raise ValueError("ambiguous OpenCode physical mount")
            mounts[target] = (source, len(parts) == 3 and parts[2] == "ro")
        return mounts

    def _check_provider_mounts(self, scope: dict, mounts: dict, *, private_logs: bool) -> None:
        target = CODEX_IDENTITY_TARGET if scope.get("role") == "codex" else PROVIDER_IDENTITY_TARGET
        required = {STATE_TARGET: (scope["workspace"], False), target: (scope["identity"], True),
                    scope["project_target"]: (scope["project_source"], False)}
        if "shared_runtime" in scope:
            required[RUNTIME_TARGET] = (scope["shared_runtime"], True)
        if any(mounts.get(target) != value for target, value in required.items()):
            raise ValueError("OpenCode physical project, state or generation mount differs")
        home_alias = f'/home/{scope["user"]}'
        seen_logs = set()
        for target, (source, readonly) in mounts.items():
            if target in required or (target == home_alias and (source, readonly) == required[STATE_TARGET]):
                continue
            if not isinstance(target, str) or not isinstance(source, str):
                raise ValueError("invalid OpenCode physical log mount")
            log_target = Path(target)
            # The legacy Docker launcher can append a slash to the declared log root.
            root_alias = log_target in self.boundary.shared and target == str(log_target) + "/"
            if (not log_target.is_absolute() or (str(log_target) != target and not root_alias)
                    or ".." in log_target.parts or log_target in seen_logs
                    or any(log_target.is_relative_to(path) or Path(path).is_relative_to(log_target)
                           for path in (*required, home_alias))):
                raise ValueError("invalid OpenCode physical log mount")
            seen_logs.add(log_target)
            for root in self.boundary.shared:
                if not log_target.is_relative_to(root):
                    continue
                expected = self.boundary.log_root / scope["slot"] / log_target.relative_to(root) if private_logs else log_target
                raw_source = target if root_alias and not private_logs else str(expected)
                if raw_source == source and expected.resolve() == expected:
                    break
            else:
                raise ValueError("unexpected OpenCode physical mount")

    def _verify_runtime_asset(self, scope: dict) -> None:
        if "shared_runtime" not in scope:
            return
        path = Path(scope["shared_runtime"])
        try:
            stamp = runtime_identity(path)
            if self._verified_runtime_assets.get(path) != stamp:
                if tree_digest(path) != path.name or runtime_identity(path) != stamp:
                    raise ValueError("OpenCode runtime asset digest mismatch")
                self._verified_runtime_assets[path] = stamp
        except FileNotFoundError as error:
            raise ValueError("OpenCode runtime asset is not provisioned on this node") from error

    def create_scope(self, request: dict) -> dict:
        if self.is_provider_image(request.get("Image")):
            mounts = self._provider_create_mounts(request)
            state = mounts.get(STATE_TARGET)
            target = CODEX_IDENTITY_TARGET if request["Image"] in self.codex_images else PROVIDER_IDENTITY_TARGET
            identity = mounts.get(target)
            if not state or not identity:
                raise ValueError("OpenCode requires state and generation mounts")
            scope = self._provider_scope(state[0], identity[0], request["Image"], request.get("User"))
            self._private(Path(scope["account_workspace"]), self.boundary.uid)
            project = Path(scope["project_source"])
            if not project.is_dir() or project.stat().st_uid != self.boundary.uid:
                raise ValueError("OpenCode project workspace is unavailable")
            self._check_provider_mounts(scope, mounts, private_logs=False)
            self._verify_runtime_asset(scope)
            return scope
        host = request.get("HostConfig", {})
        mounts = [(m.get("Source"), m.get("Target"), m.get("ReadOnly", False))
                  for m in host.get("Mounts", []) if m.get("Type") == "bind"]
        for bind in host.get("Binds", []):
            parts = bind.split(":")
            mounts.append((parts[0], parts[1], len(parts) == 3 and "ro" in parts[2].split(",")))
        for source, target, _ in mounts:
            if any(Path(source).is_relative_to(path.parent) or path.parent.is_relative_to(Path(source))
                   for path in self.runtime_assets.values()):
                raise ValueError("OpenCode runtime asset is restricted to its Provider image")
            if self.runtime_assets and (Path(target).is_relative_to(RUNTIME_TARGET)
                                       or Path(RUNTIME_TARGET).is_relative_to(Path(target))):
                raise ValueError("OpenCode runtime mount is restricted to its Provider image")
        work = [m for m in mounts if m[1] == "/data"]
        identity = [m for m in mounts if m[1] == self.identity_target]
        if len(work) != 1 or len(identity) != 1 or identity[0][2] is not True:
            raise ValueError("one workspace and one read-only identity mount required")
        return self.scope(work[0][0], identity[0][0], request.get("Image"), request.get("User"))

    @contextmanager
    def locked(self, scope: dict):
        directory = self.root / scope["slot"]
        directory.mkdir(mode=0o700, exist_ok=True)
        self._private(directory, os.getuid())
        fd = os.open(directory / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise ValueError("invalid physical operation lock")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield directory
        finally:
            os.close(fd)

    @staticmethod
    def read(path: Path) -> dict | None:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise ValueError("invalid physical dispatch receipt")
            value = stream.read(8193)
        if len(value) > 8192:
            raise ValueError("physical receipt too large")
        return json.loads(value)

    @staticmethod
    def write(path: Path, value: dict) -> None:
        # Per-slot flock owns this path. Persist before forwarding any create.
        temp = path.with_name(path.name + ".tmp")
        fd = os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise ValueError("invalid temporary physical receipt")
            stream.truncate(0)
            json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def docker(self, method: str, path: str) -> tuple[int, dict]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout); connection.connect(self.upstream)
            connection.sendall(f"{method} {path} HTTP/1.1\r\nHost: docker\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
            response = http.client.HTTPResponse(connection); response.begin()
            raw = response.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError("physical inspection response too large")
            return response.status, json.loads(raw) if raw else {}

    def inspect(self, scope: dict) -> dict | None:
        status, value = self.docker("GET", "/containers/" + scope["name"] + "/json")
        if status == 404:
            return None
        if status != 200:
            raise ValueError("physical inspection unavailable")
        self.matches(scope, value)
        return value

    def matches(self, scope: dict, value: dict) -> None:
        mounts = value.get("Mounts", [])
        if (value.get("Image") != scope["image"] or value.get("Config", {}).get("User") != scope["user"]
                or value.get("Config", {}).get("Labels", {}).get(LABEL) != scope["key"]):
            raise ValueError("physical ownership differs; no deletion permitted")
        if scope.get("role") in {"opencode", "codex"}:
            actual = {}
            for mount in mounts:
                target = mount["Destination"]
                if mount.get("Type") != "bind" or type(mount.get("RW")) is not bool or target in actual:
                    raise ValueError("physical ownership differs; no deletion permitted")
                if target == RUNTIME_TARGET and mount.get("Propagation") != "rprivate":
                    raise ValueError("OpenCode shared runtime mount propagation differs")
                actual[target] = (mount["Source"], not mount["RW"])
            self._check_provider_mounts(scope, actual, private_logs=True)
            if scope["role"] == "codex":
                self.codex_security.verify_inspect(value)
        elif (not any(m.get("Source") == scope["workspace"] and m.get("Destination") == "/data" for m in mounts)
                or not any(m.get("Source") == scope["identity"] and m.get("Destination") == self.identity_target
                           and m.get("RW") is False for m in mounts)):
            raise ValueError("physical ownership differs; no deletion permitted")

    @contextmanager
    def dispatch(self, request: dict, path: str, *, scope=None):
        scope = self.create_scope(request) if scope is None else scope
        if scope.get("role") in {"opencode", "codex"}:
            if request.get("Image") != scope["image"] or request.get("User") != scope["user"]:
                raise ValueError("OpenCode physical image or user differs")
            if self._provider_scope(scope["workspace"], scope["identity"], scope["image"], scope["user"]) != scope:
                raise ValueError("OpenCode physical scope changed during admission")
            self._check_provider_mounts(scope, self._provider_create_mounts(request), private_logs=True)
        with self.locked(scope) as directory:
            receipt_path = directory / (scope["key"] + ".json")
            if self.read(receipt_path) is not None:
                raise ValueError("physical operation was already dispatched or fenced")
            for other in directory.glob("*.json"):
                if self.read(other).get("state") != "DELETED":
                    raise ValueError("previous physical operation is unresolved")
            status, _ = self.docker("GET", "/containers/" + scope["name"] + "/json")
            if status != 404:
                raise ValueError("physical slot is occupied or unavailable")
            query = parse_qsl(urlsplit(path).query, keep_blank_values=True)
            if any(k == "name" and v != scope["name"] for k, v in query):
                raise ValueError("Docker name conflicts with physical slot")
            query = [(k, v) for k, v in query if k != "name"] + [("name", scope["name"])]
            labels = dict(request.get("Labels") or {})
            if LABEL in labels and labels[LABEL] != scope["key"]:
                raise ValueError("physical label differs")
            request["Labels"] = {**labels, LABEL: scope["key"]}
            receipt = {**scope, "state": "NOT_SENT", "observed": False}
            self.write(receipt_path, receipt)
            yield receipt_path, receipt, urlsplit(path).path + "?" + urlencode(query)

    def _confirmation_scope(self, request: dict) -> tuple[dict, str]:
        if not isinstance(request, dict) or set(request) != {"workspace", "identity", "image", "user", "instance_id"}:
            raise ValueError("invalid physical confirmation fields")
        scope = self.scope(request["workspace"], request["identity"], request["image"], request["user"])
        instance = request["instance_id"]
        if not isinstance(instance, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", instance):
            raise ValueError("invalid instance reference")
        return scope, instance

    @contextmanager
    def _provider_probe_address(self, request: dict, role: str):
        scope, _ = self._confirmation_scope(request)
        if scope.get("role") != role:
            raise ValueError("physical address request has a different Provider scope")
        with self.locked(scope) as directory:
            receipt = self.read(directory / (scope["key"] + ".json"))
            if (receipt is None or receipt.get("state") != "CREATED" or receipt.get("observed") is not True
                    or any(receipt.get(key) != value for key, value in scope.items())):
                raise ValueError("OpenCode fault check requires a matching physical receipt")
            value = self.inspect(scope)
            identifier = receipt.get("container_id")
            if (not isinstance(identifier, str) or not CONTAINER_ID.fullmatch(identifier)
                    or value is None or value.get("Id") != identifier
                    or value.get("State", {}).get("Running") is not True):
                raise ValueError("OpenCode container is not a confirmed running instance")
            bridge = value.get("NetworkSettings", {}).get("Networks", {}).get("bridge", {})
            address = IPv4Address(bridge.get("IPAddress", ""))
            if not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
                raise ValueError("OpenCode container bridge address is not private")
            yield str(address), CODEX_PORT if role == "codex" else OPENCODE_PORT

    def _opencode_probe_address(self, request: dict):
        return self._provider_probe_address(request, "opencode")

    def confirm_codex_address(self, request: dict) -> dict:
        with self._provider_probe_address(request, "codex") as (address, _):
            return {"address": address}

    def confirm_opencode_unavailable(self, request: dict) -> dict:
        with self._opencode_probe_address(request) as address:
            try:
                with socket.create_connection(address, timeout=min(2, self.timeout)):
                    return {"unavailable": False}
            except ConnectionRefusedError:
                return {"unavailable": True}

    def confirm_opencode_stalled(self, request: dict) -> dict:
        with self._opencode_probe_address(request) as address:
            with socket.create_connection(address, timeout=min(2, self.timeout)) as connection:
                connection.sendall(b"GET /global/health HTTP/1.1\r\nHost: opencode\r\nConnection: close\r\n\r\n")
                try:
                    # Any reply, including an auth challenge, establishes HTTP responsiveness.
                    connection.recv(1)
                except TimeoutError:
                    return {"stalled": True}
                return {"stalled": False}

    def fence_undispatched_codex(self, request: dict) -> dict:
        """Reject any late dispatch for a generation that never reached Docker."""
        scope, instance = self._confirmation_scope(request)
        if scope.get("role") != "codex":
            raise ValueError("undispatched fence requires a Codex generation")
        fence = {**scope, "state": "DELETED", "observed": False,
                 "reason": "never-dispatched", "instance_id": instance}
        with self.locked(scope) as directory:
            path = directory / (scope["key"] + ".json")
            receipt = self.read(path)
            if receipt is not None and receipt != fence:
                return {"fenced": False}
            status, _ = self.docker("GET", "/containers/" + scope["name"] + "/json")
            if status != 404:
                return {"fenced": False}
            if receipt is None:
                self.write(path, fence)
            return {"fenced": True}

    def confirm_deleted(self, request: dict) -> dict:
        scope, instance = self._confirmation_scope(request)
        with self.locked(scope) as directory:
            # Recheck the original authority before a physical compensation.
            try:
                with urlopen(self.frontend + "/api/agent/" + instance, timeout=self.timeout):
                    raise ValueError("original instance still exists")
            except HTTPError as error:
                if error.code != 404:
                    raise ValueError("original instance absence is unconfirmed") from None
            path = directory / (scope["key"] + ".json")
            receipt = self.read(path)
            if receipt is not None and any(receipt.get(k) != v for k, v in scope.items()):
                raise ValueError("physical receipt ownership differs")
            # Fence undispatched late creates too. A missing receipt is safe only
            # on this explicitly guarded, newly provisioned deployment scope.
            if receipt is None:
                if scope.get("role") in {"opencode", "codex"}:
                    raise ValueError("OpenCode allocation has no physical dispatch receipt")
                receipt = {**scope, "state": "NOT_SENT", "observed": False}
                self.write(path, receipt)
            value = self.inspect(scope)
            if value is not None:
                identifier = value.get("Id")
                if (not isinstance(identifier, str) or not CONTAINER_ID.fullmatch(identifier)
                        or (receipt.get("observed") and receipt.get("container_id") != identifier)):
                    raise ValueError("physical container identity differs from the receipt")
                state = value.get("State", {})
                if (state.get("Status") != "created" or state.get("Running") is not False
                        or state.get("StartedAt") != "0001-01-01T00:00:00Z"):
                    raise ValueError("physical resource requires original lifecycle recovery")
                receipt.update(observed=True, container_id=identifier)
                self.write(path, receipt)
                status, _ = self.docker("DELETE", "/containers/" + identifier + "?force=false&v=false")
                if status not in (204, 404):
                    raise ValueError("physical compensation remains pending")
                if self.inspect(scope) is not None:
                    raise ValueError("physical container still exists")
            elif not receipt.get("observed") and receipt["state"] not in ("NOT_SENT", "DELETED"):
                raise ValueError("dispatch outcome is unknown; absence alone is insufficient")
            if scope.get("role") in {"opencode", "codex"} and receipt.get("observed"):
                identifier = receipt.get("container_id")
                if not isinstance(identifier, str) or not CONTAINER_ID.fullmatch(identifier):
                    raise ValueError("invalid OpenCode physical create receipt")
                status, _ = self.docker("GET", "/containers/" + identifier + "/json")
                if status != 404:
                    raise ValueError("observed OpenCode container absence remains unconfirmed")
            receipt.update(state="DELETED")
            self.write(path, receipt)
            return {"absent": True, "scope": scope["key"]}
