"""Actual filesystem/HTTP tests for the deployment log mount boundary."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import tempfile
import time

import pytest

source = Path(__file__).resolve().parents[3] / "deploy/cloud-workspace/docker_log_boundary.py"
spec = importlib.util.spec_from_file_location("docker_log_boundary", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def boundary(tmp_path):
    users, logs, shared = (tmp_path / n for n in ("users", "private", "shared"))
    for p in (users, logs, shared):
        p.mkdir(mode=0o700)
    actor = users / ("env_" + "1" * 32)
    actor.mkdir(mode=0o700)
    uid = os.getuid() or 10001
    if os.getuid() == 0:
        os.chown(users, uid, uid)
        os.chown(actor, uid, uid)
    gate = module.LogBoundary(workspace_root=users, log_root=logs, shared_log_dirs=[shared],
                              workspace_name_pattern=r"env_[a-f0-9]{32}",
                              images=["test@sha256:abc"], user="pilot", uid=uid)
    request = {"Image": "test@sha256:abc", "User": "pilot", "Env": ["SECRET=not-to-audit"],
               "Cmd": ["existing-runtime"], "HostConfig": {"Mounts": [
                   {"Type": "bind", "Source": str(actor), "Target": "/data"},
                   {"Type": "bind", "Source": str(shared), "Target": str(shared)}]}}
    return gate, request, actor, shared


def test_replaces_only_shared_mount_keeps_protocol_and_per_account_logs(boundary):
    gate, request, actor, shared = boundary
    before = copy.deepcopy(request)
    value, audit = gate.rewrite(request)
    assert request == before
    assert value["Cmd"] == request["Cmd"] and value["Env"] == request["Env"]
    assert value["HostConfig"]["Mounts"][0] == request["HostConfig"]["Mounts"][0]
    log = Path(value["HostConfig"]["Mounts"][1]["Source"])
    assert log.parent == gate.log_root and log.stat().st_mode & 0o777 == 0o700
    assert value["HostConfig"]["Mounts"][1]["Target"] == str(shared)
    assert "SECRET" not in json.dumps(audit) and "Cmd" not in audit
    assert gate.rewrite(request)[0] == value
    other = actor.with_name("env_" + "2" * 32)
    other.mkdir(mode=0o700)
    if os.getuid() == 0:
        os.chown(other, gate.uid, gate.uid)
    request["HostConfig"]["Mounts"][0]["Source"] = str(other)
    assert gate.rewrite(request)[1]["private_log_directory"] != str(log)


@pytest.mark.parametrize("change", ["image", "root", "privileged", "volumes_from", "missing_log", "outside", "symlink", "mode", "ancestor", "private_source"])
def test_refuses_unsafe_or_unexpected_create(boundary, change):
    gate, value, actor, shared = boundary
    mounts = value["HostConfig"]["Mounts"]
    if change == "image": value["Image"] = "other"
    elif change == "root": value["User"] = "root"
    elif change == "privileged": value["HostConfig"]["Privileged"] = True
    elif change == "volumes_from": value["HostConfig"]["VolumesFrom"] = ["other"]
    elif change == "missing_log": mounts.pop()
    elif change == "outside": mounts[0]["Source"] = str(shared)
    elif change == "symlink":
        linked = actor.with_name("env_" + "3" * 32)
        linked.symlink_to(actor)
        mounts[0]["Source"] = str(linked)
    elif change == "mode": actor.chmod(0o755)
    elif change == "ancestor": mounts[1]["Source"] = str(shared.parent)
    elif change == "private_source": mounts[1]["Source"] = str(gate.log_root)
    with pytest.raises(ValueError): gate.rewrite(value)


def test_legacy_bind_syntax_and_private_log_symlink_refusal(boundary):
    gate, value, actor, shared = boundary
    value["HostConfig"] = {"Binds": [f"{actor}:/data:rw", f"{shared}:{shared}:rw"]}
    rewritten, audit = gate.rewrite(value)
    assert rewritten["HostConfig"]["Binds"][1] == f"{audit['private_log_directory']}:{shared}:rw"
    log = Path(audit["private_log_directory"])
    log.rmdir()
    log.symlink_to(actor)
    with pytest.raises(ValueError): gate.rewrite(value)


def test_actual_unix_http_create_is_rewritten_before_forwarding(boundary, tmp_path):
    gate, request, actor, shared = boundary
    short = tempfile.TemporaryDirectory(prefix="swarm-dlb-", dir="/tmp")
    upstream_path, listen_path = str(Path(short.name) / "d.sock"), str(Path(short.name) / "b.sock")
    received = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
        upstream.bind(upstream_path)
        upstream.listen(1)
        def receive():
            conn, _ = upstream.accept()
            with conn, conn.makefile("rb") as reader:
                line = reader.readline()
                headers = {}
                while (row := reader.readline()) != b"\r\n":
                    k, v = row.decode().split(":", 1)
                    headers[k.lower()] = v.strip()
                received.append(json.loads(reader.read(int(headers["content-length"]))))
                conn.sendall(b'HTTP/1.1 201 Created\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{"Id":"ok"}')
        worker = threading.Thread(target=receive, daemon=True)
        worker.start()
        with module.Server(listen_path, module.Handler) as server:
            server.upstream, server.boundary = upstream_path, gate
            serving = threading.Thread(target=server.serve_forever, daemon=True)
            serving.start()
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(3)
                    client.connect(listen_path)
                    body = json.dumps(request).encode()
                    client.sendall(f"POST /v1.51/containers/create?name=owned HTTP/1.1\r\nHost: docker\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
                    chunks = []
                    while (part := client.recv(4096)): chunks.append(part)
                assert b'201 Created' in b"".join(chunks)
                worker.join(3)
                assert received[0]["HostConfig"]["Mounts"][1]["Source"] != str(shared)
            finally:
                server.shutdown()
                serving.join(3)
                short.cleanup()


@pytest.mark.parametrize("method,path,allowed", [
    ("GET", "/v1.51/images/plain-image/json", True),
    ("GET", "/v1.51/images/swarm-runtime:candidate/json", True),
    ("GET", "/v1.51/images/sha256:abc123/json", True),
    ("GET", "/v1.51/images/registry.local:5000/team/app@sha256:abc123/json", True),
    ("POST", "/v1.51/images/swarm-runtime:candidate/json", False),
    ("GET", "/v1.51/containers/create:owned", False),
    ("GET", "/v1.51/images/swarm%3Aruntime/json", False),
    ("GET", "/v1.51/images/runtime/../containers/create", False),
])
def test_actual_unix_http_image_inspection_preserves_create_path_guard(boundary, method, path, allowed):
    gate, _, _, _ = boundary
    received = []
    with tempfile.TemporaryDirectory(prefix="swarm-dlb-", dir="/tmp") as short:
        upstream_path, listen_path = str(Path(short) / "d.sock"), str(Path(short) / "b.sock")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.bind(upstream_path)
            upstream.listen(1)
            upstream.settimeout(1)

            def receive():
                try:
                    conn, _ = upstream.accept()
                except socket.timeout:
                    return
                with conn, conn.makefile("rb") as reader:
                    received.append(reader.readline())
                    while reader.readline() not in (b"\r\n", b""):
                        pass
                    conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}')

            worker = threading.Thread(target=receive, daemon=True)
            worker.start()
            with module.Server(listen_path, module.Handler) as server:
                server.upstream, server.boundary = upstream_path, gate
                serving = threading.Thread(target=server.serve_forever, daemon=True)
                serving.start()
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.settimeout(3)
                        client.connect(listen_path)
                        client.sendall(f"{method} {path} HTTP/1.1\r\nHost: docker\r\nContent-Length: 0\r\n\r\n".encode())
                        chunks = []
                        while (part := client.recv(4096)):
                            chunks.append(part)
                    status = b"".join(chunks).split(b"\r\n", 1)[0]
                    assert (b"200 OK" in status) if allowed else (b"502" in status)
                    worker.join(2)
                    assert bool(received) is allowed
                    if allowed:
                        assert received[0] == f"{method} {path} HTTP/1.1\r\n".encode()
                finally:
                    server.shutdown()
                    serving.join(3)
                    worker.join(2)


@pytest.mark.parametrize("name", ["u_" + "1" * 32, "env_short", "env_" + "A" * 32, "env_" + "1" * 33])
def test_platform_boundary_rejects_non_environment_directory(boundary, name):
    gate, request, actor, _ = boundary
    invalid = actor.with_name(name)
    invalid.mkdir(mode=0o700)
    if os.getuid() == 0:
        os.chown(invalid, gate.uid, gate.uid)
    request["HostConfig"]["Mounts"][0]["Source"] = str(invalid)
    with pytest.raises(ValueError, match="invalid account workspace"):
        gate.rewrite(request)


def with_rule(gate, pattern):
    return module.LogBoundary(workspace_root=gate.workspace_root, workspace_name_pattern=pattern,
                              log_root=gate.log_root, shared_log_dirs=gate.shared,
                              images=gate.images, user=gate.user, uid=gate.uid)


@pytest.mark.parametrize("pattern", [None, "", " ", "[", ".*", r".+", r"env_|", "x" * 257])
def test_invalid_deployment_rule_fails_before_creating_logs(boundary, pattern):
    gate, _, _, _ = boundary
    with pytest.raises(ValueError, match="workspace name pattern"):
        with_rule(gate, pattern)
    assert list(gate.log_root.iterdir()) == []


def test_rule_change_preserves_existing_private_logs_and_payload(boundary):
    gate, request, _, _ = boundary
    original, audit = gate.rewrite(request)
    marker = Path(audit["private_log_directory"]) / "retained.log"
    marker.write_text("keep existing log bytes")
    compatible = with_rule(gate, r"(?:env|task)_[a-f0-9]{32}")
    rewritten, updated = compatible.rewrite(request)
    assert rewritten == original and updated == audit
    assert marker.read_text() == "keep existing log bytes"
    with pytest.raises(ValueError, match="invalid account workspace"):
        with_rule(gate, r"tenant-[0-9]{6}").rewrite(request)
    assert marker.read_text() == "keep existing log bytes"


@pytest.mark.parametrize("change", ["outside", "nested", "symlink", "mode", "unmatched"])
def test_custom_rule_cannot_relax_filesystem_boundary(boundary, change):
    gate, request, actor, _ = boundary
    gate = with_rule(gate, r"tenant-[0-9]{6}")
    custom = actor.with_name("tenant-000001")
    actor.rename(custom)
    if change == "outside":
        custom = custom.rename(gate.workspace_root.parent / custom.name)
    elif change == "nested":
        parent = gate.workspace_root / "nested"
        parent.mkdir(mode=0o700)
        custom = custom.rename(parent / custom.name)
    elif change == "symlink":
        target = custom
        custom = custom.with_name("tenant-000002")
        custom.symlink_to(target)
    elif change == "mode":
        custom.chmod(0o755)
    elif change == "unmatched":
        custom = custom.rename(custom.with_name("tenant-000001-extra"))
    request["HostConfig"]["Mounts"][0]["Source"] = str(custom)
    with pytest.raises(ValueError):
        gate.rewrite(request)
    assert list(gate.log_root.iterdir()) == []


@pytest.mark.parametrize("rule", [None, "["])
def test_cli_requires_valid_explicit_rule_before_socket_creation(boundary, rule):
    gate, _, _, _ = boundary
    with tempfile.TemporaryDirectory(prefix="dlb-cli-", dir="/tmp") as directory:
        listen = Path(directory) / "b.sock"
        cmd = [sys.executable, str(source), "--listen", str(listen), "--workspace-root", str(gate.workspace_root),
               "--private-log-root", str(gate.log_root), "--shared-log-dir", str(gate.shared[0]),
               "--image", next(iter(gate.images)), "--user", gate.user, "--uid", str(gate.uid)]
        if rule is not None:
            cmd += ["--workspace-name-pattern", rule]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        assert result.returncode == 2
        assert ("--workspace-name-pattern" if rule is None else "invalid workspace name pattern") in result.stderr
        assert not listen.exists() and list(gate.log_root.iterdir()) == []


@pytest.mark.parametrize("pattern,name", [(r"env_[a-f0-9]{32}", "env_" + "1" * 32),
                                         (r"tenant-[0-9]{6}", "tenant-000001")])
def test_real_cli_uses_deployment_rule_with_unix_docker_stub(boundary, pattern, name):
    gate, request, actor, shared = boundary
    custom = actor if actor.name == name else actor.rename(actor.with_name(name))
    request["HostConfig"]["Mounts"][0]["Source"] = str(custom)
    original = copy.deepcopy(request)
    with tempfile.TemporaryDirectory(prefix="dlb-cli-", dir="/tmp") as directory:
        upstream_path, listen = Path(directory) / "d.sock", Path(directory) / "b.sock"
        received = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.bind(str(upstream_path))
            upstream.listen(1)
            upstream.settimeout(5)

            def receive():
                conn, _ = upstream.accept()
                with conn, conn.makefile("rb") as reader:
                    reader.readline()
                    headers = {}
                    for row in iter(reader.readline, b"\r\n"):
                        if not row:
                            return
                        key, value = row.decode().split(":", 1)
                        headers[key.lower()] = value.strip()
                    received.append(json.loads(reader.read(int(headers["content-length"]))))
                    conn.sendall(b'HTTP/1.1 201 Created\r\nContent-Length: 11\r\nConnection: close\r\n\r\n{"Id":"ok"}')

            worker = threading.Thread(target=receive, daemon=True)
            worker.start()
            cmd = [sys.executable, str(source), "--listen", str(listen), "--upstream", str(upstream_path),
                   "--workspace-root", str(gate.workspace_root), "--workspace-name-pattern", pattern,
                   "--private-log-root", str(gate.log_root), "--shared-log-dir", str(shared),
                   "--image", next(iter(gate.images)), "--user", gate.user, "--uid", str(gate.uid)]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 4
                while not listen.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                assert listen.is_socket() and process.poll() is None
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(3)
                    client.connect(str(listen))
                    body = json.dumps(request).encode()
                    client.sendall(f"POST /containers/create HTTP/1.1\r\nHost: docker\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
                    chunks = []
                    while True:
                        part = client.recv(4096)
                        if not part:
                            break
                        chunks.append(part)
                assert b"201 Created" in b"".join(chunks)
                worker.join(3)
                assert len(received) == 1
                source_path = Path(received[0]["HostConfig"]["Mounts"][1]["Source"])
                assert source_path.parent == gate.log_root and source_path.is_dir()
                assert source_path.stat().st_mode & 0o777 == 0o700
                received[0]["HostConfig"]["Mounts"][1]["Source"] = str(shared)
                assert received[0] == original
            finally:
                process.terminate()
                process.communicate(timeout=5)
                worker.join(6)


def cli_command(gate, listen, upstream, *extra):
    return [sys.executable, str(source), '--listen', str(listen), '--upstream', str(upstream),
            '--workspace-root', str(gate.workspace_root), '--workspace-name-pattern', r'env_[a-f0-9]{32}',
            '--private-log-root', str(gate.log_root), '--shared-log-dir', str(gate.shared[0]),
            '--image', next(iter(gate.images)), '--user', gate.user, '--uid', str(gate.uid), *extra]


def await_socket(process, path):
    for _ in range(100):
        assert process.poll() is None
        if path.is_socket():
            return
        time.sleep(.02)
    raise AssertionError('socket not ready')


def unix_call(path, payload=b'GET /_ping HTTP/1.1\r\nHost: docker\r\n\r\n'):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(path))
        client.sendall(payload)
        chunks = []
        while True:
            try:
                part = client.recv(65536)
            except ConnectionResetError:
                if chunks:
                    return b''.join(chunks)
                raise
            if not part:
                return b''.join(chunks)
            chunks.append(part)


def test_cli_signal_cleanup_lock_and_abnormal_restart(boundary):
    gate = boundary[0]
    with tempfile.TemporaryDirectory(prefix='dlb-life-', dir='/tmp') as folder:
        listen, upstream = Path(folder) / 'b.sock', Path(folder) / 'missing.sock'
        cmd = cli_command(gate, listen, upstream, '--recover-stale-socket')
        first = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        second = None
        try:
            await_socket(first, listen)
            inode = listen.stat().st_ino
            collision = subprocess.run(cmd, capture_output=True, timeout=3)
            assert collision.returncode == 2 and b'lock is held' in collision.stderr
            assert listen.stat().st_ino == inode
            first.kill()
            first.wait(timeout=3)
            assert listen.is_socket()
            strict = subprocess.run(cmd[:-1], capture_output=True, timeout=3)
            assert strict.returncode == 2 and b'explicit recovery' in strict.stderr
            assert listen.stat().st_ino == inode
            second = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                assert second.poll() is None
                try:
                    response = unix_call(listen)
                    if b'502' in response:
                        break
                except (ConnectionRefusedError, FileNotFoundError):
                    pass
                time.sleep(.02)
            else:
                raise AssertionError('recovery not ready')
            second.terminate()
            assert second.wait(timeout=3) == 0 and not listen.exists()
            assert Path(str(listen) + '.lock').is_file()
        finally:
            for process in [first, second]:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)


@pytest.mark.parametrize('kind', ['regular', 'symlink', 'live', 'lock_symlink'])
def test_recovery_never_removes_foreign_paths_or_live_listener(boundary, kind):
    gate = boundary[0]
    with tempfile.TemporaryDirectory(prefix='dlb-refuse-', dir='/tmp') as folder:
        listen = Path(folder) / 'b.sock'
        target = Path(folder) / 'keep'
        target.write_text('preserve')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as foreign:
            if kind == 'regular':
                listen.write_text('preserve')
            elif kind == 'symlink':
                listen.symlink_to(target)
            elif kind == 'live':
                foreign.bind(str(listen))
                listen.chmod(0o700)
                foreign.listen(1)
            else:
                Path(str(listen) + '.lock').symlink_to(target)
            result = subprocess.run(cli_command(gate, listen, Path(folder) / 'up.sock', '--recover-stale-socket'),
                                    capture_output=True, timeout=3)
            assert result.returncode == 2 and target.read_text() == 'preserve'
            if kind != 'lock_symlink':
                assert listen.exists()
            if kind == 'regular':
                assert listen.read_text() == 'preserve'


@pytest.mark.parametrize('flag,value', [('--max-connections', '0'), ('--max-connections', '257'),
                                       ('--request-timeout', '0'), ('--connect-timeout', '-1'),
                                       ('--upstream-timeout', 'nan'), ('--stream-idle-timeout', 'inf')])
def test_invalid_resource_limits_fail_before_socket(boundary, flag, value):
    with tempfile.TemporaryDirectory(prefix='dlb-limit-', dir='/tmp') as folder:
        listen = Path(folder) / 'b.sock'
        result = subprocess.run(cli_command(boundary[0], listen, Path(folder) / 'up.sock', flag, value),
                                capture_output=True, timeout=3)
        assert result.returncode == 2 and not listen.exists()


def test_connection_limit_rejects_overload_and_releases_idle_slot(boundary):
    with tempfile.TemporaryDirectory(prefix='dlb-limit-', dir='/tmp') as folder:
        listen = Path(folder) / 'b.sock'
        process = subprocess.Popen(cli_command(boundary[0], listen, Path(folder) / 'missing.sock',
                                              '--max-connections', '1', '--request-timeout', '.4'),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            await_socket(process, listen)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as held:
                held.settimeout(3)
                held.connect(str(listen))
                held.sendall(b'GET /_ping HTTP/1.1\r\n')
                time.sleep(.05)
                assert b'503' in unix_call(listen)
                assert held.recv(4096) == b''
            # The expired incomplete request must release its capacity.
            assert b'502' in unix_call(listen)
        finally:
            process.terminate()
            process.wait(timeout=3)


@pytest.mark.parametrize('partial,upgrade', [(False, False), (True, False), (True, True)])
def test_upstream_timeout_closes_without_retry_or_second_http_response(boundary, partial, upgrade):
    with tempfile.TemporaryDirectory(prefix='dlb-timeout-', dir='/tmp') as folder:
        upstream_path, listen = Path(folder) / 'up.sock', Path(folder) / 'b.sock'
        received = []
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.bind(str(upstream_path))
            upstream.listen(2)
            upstream.settimeout(2)
            def stall():
                conn, _ = upstream.accept()
                with conn:
                    received.append(conn.recv(4096))
                    if partial:
                        conn.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: tcp\r\n\r\n' if upgrade
                                     else b'HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\npartial')
                    time.sleep(.6)
            worker = threading.Thread(target=stall, daemon=True)
            worker.start()
            process = subprocess.Popen(cli_command(boundary[0], listen, upstream_path,
                                                  '--upstream-timeout', '.15', '--stream-idle-timeout', '.15'),
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                await_socket(process, listen)
                request = b'GET /_ping HTTP/1.1\r\nHost: docker\r\n' + (b'Upgrade: tcp\r\n' if upgrade else b'') + b'\r\n'
                started = time.monotonic()
                response = unix_call(listen, request)
                assert time.monotonic() - started < 2
                assert response.count(b'HTTP/1.1 ') == 1
                assert (b'502' not in response) if partial else (b'502' in response)
                worker.join(2)
                upstream.settimeout(.05)
                with pytest.raises(socket.timeout):
                    upstream.accept()
                assert len(received) == 1
            finally:
                process.terminate()
                process.wait(timeout=3)
                worker.join(2)
