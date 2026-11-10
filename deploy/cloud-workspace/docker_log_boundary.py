#!/usr/bin/env python3
"""Private Unix Docker API boundary for a dedicated account runtime launcher.

This is a deployment adapter, not an instance allocator. Only container-create
JSON is changed; the official launcher and daemon retain lifecycle ownership.
Never expose this socket to Agents or browsers. Run under the host operator.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager, ExitStack
import errno
import fcntl
import hashlib
import http.server
import http.client
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import socketserver
import stat
import threading
import math

MAX_BODY = 8 * 1024 * 1024


def private_directory(path: Path, uid: int) -> None:
    if not path.exists():
        path.mkdir(mode=0o700)
        os.chown(path, uid, uid)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private directory owner/mode mismatch")


class LogBoundary:
    def __init__(self, *, workspace_root, workspace_name_pattern, log_root, shared_log_dirs, images, user, uid):
        # Operator-owned admission rule, independent of application account IDs.
        if not isinstance(workspace_name_pattern, str) or not workspace_name_pattern.strip():
            raise ValueError("explicit workspace name pattern required")
        if len(workspace_name_pattern) > 256:
            raise ValueError("workspace name pattern too long")
        try:
            self.workspace_name_pattern = re.compile(workspace_name_pattern, re.ASCII)
        except re.error:
            raise ValueError("invalid workspace name pattern") from None
        if any(self.workspace_name_pattern.fullmatch(name) for name in ("", ".", "..", "/", "a/b", "a\\b")):
            raise ValueError("workspace name pattern must match directory names only")
        self.workspace_root = Path(workspace_root)
        self.log_root = Path(log_root)
        self.shared = tuple(Path(p) for p in shared_log_dirs)
        self.images = frozenset(images)
        self.user, self.uid = user, uid
        for p in (self.workspace_root, self.log_root, *self.shared):
            if not p.is_absolute() or p.resolve() != p or ".." in p.parts:
                raise ValueError("boundary paths must be canonical absolute paths")
        if not self.images or uid <= 0 or not user or user == "root":
            raise ValueError("explicit images and non-root image user required")
        for p in (self.workspace_root, self.log_root):
            if not p.is_dir() or p.is_symlink() or stat.S_IMODE(p.stat().st_mode) != 0o700:
                raise ValueError("operator must pre-create private roots")
        if any(self.log_root.is_relative_to(p) or p.is_relative_to(self.log_root) for p in self.shared):
            raise ValueError("private and shared logs must be disjoint")
        if self.workspace_root.stat().st_uid != uid or self.log_root.stat().st_uid != os.getuid():
            raise ValueError("root ownership mismatch")
        if self.log_root.is_relative_to(self.workspace_root) or self.workspace_root.is_relative_to(self.log_root):
            raise ValueError("workspace and private logs must be disjoint")

    def rewrite(self, request):
        value = copy.deepcopy(request)
        if not isinstance(value, dict) or value.get("Image") not in self.images or value.get("User") != self.user:
            raise ValueError("unapproved image or execution user")
        host = value.get("HostConfig", {})
        if not isinstance(host, dict) or host.get("Privileged") or host.get("VolumesFrom"):
            raise ValueError("unsupported privileged or inherited mounts")
        mounts = []
        for item in host.get("Mounts", []):
            if not isinstance(item, dict):
                raise ValueError("invalid mount")
            if item.get("Type") == "bind":
                mounts.append((item.get("Source"), item.get("Target"), item))
        binds = host.get("Binds", [])
        for index, bind in enumerate(binds):
            if not isinstance(bind, str):
                raise ValueError("invalid bind")
            parts = bind.split(":")
            if len(parts) not in (2, 3):
                raise ValueError("invalid bind syntax")
            mounts.append((parts[0], parts[1], (binds, index, parts)))
        workspaces = [source for source, target, _ in mounts if target == "/data"]
        if len(workspaces) != 1:
            raise ValueError("one account /data mount required")
        workspace = Path(workspaces[0])
        if (workspace.parent != self.workspace_root or len(workspace.name) > 255
                or "\\" in workspace.name or "\x00" in workspace.name
                or not self.workspace_name_pattern.fullmatch(workspace.name)):
            raise ValueError("invalid account workspace")
        if workspace.resolve() != workspace or not workspace.is_dir() or workspace.is_symlink():
            raise ValueError("workspace missing or linked")
        if workspace.stat().st_uid != self.uid or stat.S_IMODE(workspace.stat().st_mode) != 0o700:
            raise ValueError("workspace owner/mode mismatch")
        private = self.log_root / hashlib.sha256(str(workspace).encode()).hexdigest()
        replacements = []
        for source, target, item in mounts:
            if not isinstance(source, str) or not isinstance(target, str):
                raise ValueError("invalid bind paths")
            source_path = Path(source)
            if not source_path.is_absolute() or source_path.resolve() != source_path:
                raise ValueError("noncanonical mount source")
            if source_path == self.log_root or source_path.is_relative_to(self.log_root):
                raise ValueError("private log source must be generated by boundary")
            for root in self.shared:
                if source_path == root or source_path.is_relative_to(root):
                    # Preserve the in-container path expected by the stock runtime.
                    if target != source:
                        raise ValueError("unexpected shared log target")
                    replacements.append((source_path.relative_to(root), item))
                    break
                if root.is_relative_to(source_path):
                    raise ValueError("ancestor mount exposes shared logs")
        if not replacements:
            raise ValueError("expected automatic log mount missing")
        private_directory(private, self.uid)
        for relative, item in replacements:
            dest = private
            for part in relative.parts:
                dest = dest / part
                private_directory(dest, self.uid)
            if isinstance(item, dict):
                item["Source"] = str(dest)
            else:
                binds, index, parts = item
                parts[0] = str(dest)
                binds[index] = ":".join(parts)
        # No payload, environment, credentials, or command lines in the audit.
        return value, {"account": workspace.name, "private_log_directory": str(private),
                       "replaced_mounts": len(replacements)}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_GET(self):
        self.forward()

    do_POST = do_PUT = do_DELETE = do_HEAD = do_PATCH = do_GET

    def forward(self):
        self.close_connection = True
        responded = False
        try:
            # Only local control-plane JSON calls are needed. Fail closed on
            # unsupported framing instead of forwarding an unexamined create.
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) > 1:
                raise ValueError("unsupported request framing")
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > MAX_BODY:
                raise ValueError("request body too large")
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError("incomplete request body")
            path = self.path.split("?", 1)[0]
            # Stock Docker clients inspect image tags/digests before creating a
            # container. Permit their literal ':'/'@' only on this read-only
            # endpoint; encoded or alternate create paths still fail closed.
            image_inspect = self.command == "GET" and re.fullmatch(
                r"/(?:v[0-9]+\.[0-9]+/)?images/[A-Za-z0-9][A-Za-z0-9_.:/@-]*/json", path)
            if (not (re.fullmatch(r"/[A-Za-z0-9_./-]+", path) or image_inspect)
                    or "//" in path or any(p in {".", ".."} for p in path.split("/"))):
                raise ValueError("noncanonical API path")
            if path.rstrip("/").endswith("/containers/create") and path.endswith("/"):
                raise ValueError("noncanonical create path")
            if re.fullmatch(r"/(?:v[0-9]+\.[0-9]+/)?containers/create", path):
                if self.command != "POST":
                    raise ValueError("invalid create method")
                decoded = json.loads(body)
                print(json.dumps({"create_image": decoded.get("Image"), "create_user": decoded.get("User"),
                    "host_keys": sorted(decoded.get("HostConfig", {})),
                    "bind_count": len(decoded.get("HostConfig", {}).get("Binds", []))}), flush=True)
                request, audit = self.server.boundary.rewrite(decoded)
                if getattr(self.server, "resources", None) is not None:
                    self.guarded_create(request)
                    return
                body = json.dumps(request, separators=(",", ":")).encode()
                print(json.dumps(audit), flush=True)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
                upstream.settimeout(self.server.connect_timeout)
                upstream.connect(self.server.upstream)
                headers = [(k, v) for k, v in self.headers.items()
                           if k.lower() not in {"connection", "content-length", "expect"}]
                upgrade = self.headers.get("Upgrade")
                headers += [("Content-Length", str(len(body))), ("Connection", "Upgrade" if upgrade else "close")]
                head = f"{self.command} {self.path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers) + "\r\n"
                upstream.settimeout(self.server.upstream_timeout)
                upstream.sendall(head.encode("latin1") + body)
                # Preserve Docker's streamed/chunked responses and HTTP hijack.
                # One request per connection prevents later creates bypassing
                # the rewrite; upgraded execution sessions are opaque bytes.
                upstream.settimeout(self.server.upstream_timeout)
                if upgrade:
                    sockets = [upstream, self.connection]
                    while True:
                        ready, _, _ = select.select(sockets, [], [], self.server.stream_idle_timeout)
                        if not ready:
                            return
                        for source in ready:
                            data = source.recv(65536)
                            if not data:
                                return
                            if source is upstream:
                                responded = True
                            (self.connection if source is upstream else upstream).sendall(data)
                else:
                    while True:
                        data = upstream.recv(65536)
                        if not data:
                            break
                        responded = True
                        self.connection.sendall(data)
        except (ValueError, TypeError, KeyError, OSError, http.client.HTTPException) as error:
            # Fixed local validation errors contain no request values.
            reason = str(error) if type(error) is ValueError and str(error) in {
                "unapproved image or execution user", "one account /data mount required",
                "invalid account workspace", "noncanonical mount source", "unexpected shared log target",
                "private directory owner/mode mismatch", "workspace owner/mode mismatch",
                "expected automatic log mount missing", "unsupported request framing",
                "noncanonical API path",
                "invalid bind syntax", "ancestor mount exposes shared logs",
                "unsupported privileged or inherited mounts"} else type(error).__name__
            print(json.dumps({"boundary_error": reason}), flush=True)
            # Never include user payload or exception strings in responses.
            if not responded and not isinstance(error, (BrokenPipeError, ConnectionResetError)):
                try:
                    self.send_error(502, "Docker boundary rejected request or upstream unavailable")
                except OSError:
                    pass


    def guarded_create(self, request):
        resources = self.server.resources
        with resources.dispatch(request, self.path) as (path, receipt, target):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
                upstream.settimeout(self.server.connect_timeout)
                upstream.connect(self.server.upstream)
                body = json.dumps(request, separators=(",", ":")).encode()
                head = (f"POST {target} HTTP/1.1\r\nHost: docker\r\nContent-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n")
                # Persist intent before dispatch. Crash/timeout never implies no effect.
                receipt["state"] = "SENT"
                resources.write(path, receipt)
                upstream.settimeout(self.server.upstream_timeout)
                upstream.sendall(head.encode() + body)
                response = http.client.HTTPResponse(upstream)
                response.begin()
                raw = response.read(MAX_BODY + 1)
                if len(raw) > MAX_BODY:
                    raise ValueError("create response too large")
                if response.status == 201:
                    identifier = json.loads(raw).get("Id")
                    if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{64}", identifier):
                        raise ValueError("invalid physical create receipt")
                    receipt.update(state="CREATED", observed=True, container_id=identifier)
                    resources.write(path, receipt)
                # No upstream replay, including a failed downstream delivery.
                self.send_response(response.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)


class ConfirmationHandler(http.server.BaseHTTPRequestHandler):
    """Narrow internal endpoint. Never forwards an arbitrary Docker operation."""
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_POST(self):
        self.close_connection = True
        try:
            if (self.path != "/v1/confirm-deleted" or self.headers.get("Transfer-Encoding")
                    or len(self.headers.get_all("Content-Length", [])) != 1):
                raise ValueError("invalid confirmation request")
            size = int(self.headers["Content-Length"])
            if not 0 < size <= 8192:
                raise ValueError("invalid confirmation size")
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("incomplete confirmation")
            value = self.server.resources.confirm_deleted(json.loads(raw))
            payload = json.dumps(value).encode()
        except (ValueError, TypeError, KeyError, OSError, http.client.HTTPException):
            self.send_error(503, "Physical completion remains unconfirmed")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, address, handler, *, max_connections=32, request_timeout=30,
                 connect_timeout=5, upstream_timeout=60, stream_idle_timeout=300):
        self.slots = threading.BoundedSemaphore(max_connections)
        self.request_timeout = request_timeout
        self.connect_timeout = connect_timeout
        self.upstream_timeout = upstream_timeout
        self.stream_idle_timeout = stream_idle_timeout
        super().__init__(address, handler)

    def get_request(self):
        conn, address = super().get_request()
        conn.settimeout(self.request_timeout)
        return conn, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(0.2)
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def socket_identity(path, group=None):
    info = path.lstat()
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
            or (info.st_mode & 0o077 if group is None else
                stat.S_IMODE(info.st_mode) != 0o660 or info.st_gid != group)):
        raise ValueError("existing socket is not private and operator owned")
    return info.st_dev, info.st_ino


@contextmanager
def socket_lease(listen, recover, group=None):
    # The persistent flock serializes our own processes. Only the operator may
    # write this parent; other programs must not reuse this dedicated endpoint.
    if (not listen.is_absolute() or listen.parent.resolve() != listen.parent
            or stat.S_IMODE(listen.parent.stat().st_mode) != (0o700 if group is None else 0o710)
            or (group is not None and listen.parent.stat().st_gid != group)
            or listen.parent.stat().st_uid != os.getuid()):
        raise ValueError("socket parent must be canonical and private")
    fd = os.open(str(listen) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError("invalid socket lock file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("socket operator lock is held") from None
        if listen.exists() or listen.is_symlink():
            identity = socket_identity(listen, group)
            if not recover:
                raise ValueError("existing socket requires explicit recovery")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                if probe.connect_ex(str(listen)) != errno.ECONNREFUSED:
                    raise ValueError("socket may still have a live listener")
            if socket_identity(listen, group) != identity:
                raise ValueError("socket changed during recovery")
            listen.unlink()
        yield
    finally:
        # Never unlink the lock: another process may already be waiting on it.
        os.close(fd)


def positive_timeout(value):
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= 3600:
        raise argparse.ArgumentTypeError("timeout must be finite and within (0, 3600]")
    return number


def connection_limit(value):
    number = int(value)
    if not 1 <= number <= 256:
        raise argparse.ArgumentTypeError("max connections must be within [1, 256]")
    return number


def terminate(_signum, _frame):
    # Closing the process also closes in-flight upstream sockets. Never replay
    # an ambiguous request; reconciliation belongs to the original caller.
    raise SystemExit(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", required=True)
    parser.add_argument("--upstream", default="/var/run/docker.sock")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--workspace-name-pattern", required=True,
                        help="Operator-owned full-match regex for a direct workspace directory name; no default")
    parser.add_argument("--private-log-root", required=True)
    parser.add_argument("--shared-log-dir", action="append", required=True)
    parser.add_argument("--image", action="append", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--recover-stale-socket", action="store_true")
    parser.add_argument("--max-connections", type=connection_limit, default=32)
    parser.add_argument("--request-timeout", type=positive_timeout, default=30)
    parser.add_argument("--connect-timeout", type=positive_timeout, default=5)
    parser.add_argument("--upstream-timeout", type=positive_timeout, default=60)
    parser.add_argument("--stream-idle-timeout", type=positive_timeout, default=300)
    parser.add_argument("--physical-journal-root")
    parser.add_argument("--identity-root")
    parser.add_argument("--identity-target")
    parser.add_argument("--reconcile-listen")
    parser.add_argument("--reconcile-frontend")
    parser.add_argument("--reconcile-gid", type=int)
    args = parser.parse_args()
    physical_args = [args.physical_journal_root, args.identity_root, args.identity_target,
                     args.reconcile_listen, args.reconcile_frontend, args.reconcile_gid]
    if any(v is not None for v in physical_args) and not all(v is not None for v in physical_args):
        parser.error("physical confirmation requires all six explicit deployment parameters")
    if args.reconcile_gid is not None and args.reconcile_gid <= 0:
        parser.error("confirmation group must be non-root")
    try:
        boundary = LogBoundary(workspace_root=args.workspace_root, workspace_name_pattern=args.workspace_name_pattern,
                               log_root=args.private_log_root, shared_log_dirs=args.shared_log_dir,
                               images=args.image, user=args.user, uid=args.uid)
    except ValueError as error:
        parser.error(str(error))
    listen = Path(args.listen)
    upstream = Path(args.upstream)
    if not upstream.is_absolute() or upstream == listen:
        parser.error("upstream must be a distinct absolute Unix socket path")
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    previous = os.umask(0o077)
    try:
        with ExitStack() as stack:
            resources = None
            if args.physical_journal_root is not None:
                from physical_resources import PhysicalResources
                resources = PhysicalResources(boundary, Path(args.physical_journal_root), Path(args.identity_root),
                    args.identity_target, str(upstream), args.reconcile_frontend)
                restricted = Path(args.reconcile_listen)
                if restricted in (listen, upstream):
                    raise ValueError("confirmation endpoint must be distinct")
                stack.enter_context(socket_lease(restricted, args.recover_stale_socket, args.reconcile_gid))
                confirmation = stack.enter_context(Server(str(restricted), ConfirmationHandler,
                    max_connections=args.max_connections, request_timeout=args.request_timeout))
                os.chown(restricted, os.getuid(), args.reconcile_gid)
                restricted.chmod(0o660)
                owned = socket_identity(restricted, args.reconcile_gid)
                def cleanup_confirmation():
                    confirmation.shutdown()
                    if restricted.exists() and socket_identity(restricted, args.reconcile_gid) == owned:
                        restricted.unlink()
                confirmation.resources = resources
                threading.Thread(target=confirmation.serve_forever, daemon=True).start()
                stack.callback(cleanup_confirmation)
            stack.enter_context(socket_lease(listen, args.recover_stale_socket))
            with Server(str(listen), Handler, max_connections=args.max_connections,
                        request_timeout=args.request_timeout, connect_timeout=args.connect_timeout,
                        upstream_timeout=args.upstream_timeout, stream_idle_timeout=args.stream_idle_timeout) as server:
                identity = socket_identity(listen)
                server.upstream, server.boundary = str(upstream), boundary
                server.resources = resources
                try:
                    server.serve_forever()
                finally:
                    # Do not remove a replacement path even during shutdown.
                    if listen.exists() and socket_identity(listen) == identity:
                        listen.unlink()
    except (ValueError, OSError) as error:
        parser.error(str(error))
    finally:
        os.umask(previous)


if __name__ == "__main__":
    main()
