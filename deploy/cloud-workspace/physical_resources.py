"""Deployment-side completion proof for the existing instance deletion chain.

No creator, sweeper, scheduler or account database. A durable dispatch fence and
Docker's unique container name make the original calls observable after failure.
Only a proven, never-started orphan may be removed by a deletion confirmation.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
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


class PhysicalResources:
    def __init__(self, boundary, journal_root: Path, identity_root: Path, identity_target: str,
                 upstream: str, frontend: str, timeout: float = 10):
        self.boundary = boundary
        self.root, self.identity_root = Path(journal_root), Path(identity_root)
        self.identity_target = identity_target
        self.upstream, self.frontend, self.timeout = upstream, frontend.rstrip("/"), timeout
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

    @staticmethod
    def _private(path: Path, uid: int) -> None:
        if not path.is_absolute() or path.resolve() != path:
            raise ValueError("noncanonical physical scope")
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("physical scope owner or mode differs")

    def scope(self, workspace: str, identity: str, image: str, user: str) -> dict:
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

    def create_scope(self, request: dict) -> dict:
        host = request.get("HostConfig", {})
        mounts = [(m.get("Source"), m.get("Target"), m.get("ReadOnly", False))
                  for m in host.get("Mounts", []) if m.get("Type") == "bind"]
        for bind in host.get("Binds", []):
            parts = bind.split(":")
            mounts.append((parts[0], parts[1], len(parts) == 3 and "ro" in parts[2].split(",")))
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
                or value.get("Config", {}).get("Labels", {}).get(LABEL) != scope["key"]
                or not any(m.get("Source") == scope["workspace"] and m.get("Destination") == "/data" for m in mounts)
                or not any(m.get("Source") == scope["identity"] and m.get("Destination") == self.identity_target
                           and m.get("RW") is False for m in mounts)):
            raise ValueError("physical ownership differs; no deletion permitted")

    @contextmanager
    def dispatch(self, request: dict, path: str):
        scope = self.create_scope(request)
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

    def confirm_deleted(self, request: dict) -> dict:
        if set(request) != {"workspace", "identity", "image", "user", "instance_id"}:
            raise ValueError("invalid physical confirmation fields")
        scope = self.scope(request["workspace"], request["identity"], request["image"], request["user"])
        instance = request["instance_id"]
        if not isinstance(instance, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", instance):
            raise ValueError("invalid instance reference")
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
                receipt = {**scope, "state": "NOT_SENT", "observed": False}
                self.write(path, receipt)
            value = self.inspect(scope)
            if value is not None:
                state = value.get("State", {})
                if (state.get("Status") != "created" or state.get("Running") is not False
                        or state.get("StartedAt") != "0001-01-01T00:00:00Z"):
                    raise ValueError("physical resource requires original lifecycle recovery")
                receipt.update(observed=True, container_id=value["Id"])
                self.write(path, receipt)
                status, _ = self.docker("DELETE", "/containers/" + value["Id"] + "?force=false&v=false")
                if status not in (204, 404):
                    raise ValueError("physical compensation remains pending")
                if self.inspect(scope) is not None:
                    raise ValueError("physical container still exists")
            elif not receipt.get("observed") and receipt["state"] not in ("NOT_SENT", "DELETED"):
                raise ValueError("dispatch outcome is unknown; absence alone is insufficient")
            receipt.update(state="DELETED")
            self.write(path, receipt)
            return {"absent": True, "scope": scope["key"]}
