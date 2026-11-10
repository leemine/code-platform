"""Durable dispatch/confirmation tests over real Unix HTTP sockets."""
import copy
import http.client
import http.server
import importlib.util
import json
import os
from pathlib import Path
import socket
import threading
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs

import pytest

from tests.unit_tests.cloud_workspace.test_docker_log_boundary import boundary, module

spec = importlib.util.spec_from_file_location("physical_resources", Path(module.__file__).with_name("physical_resources.py"))
physical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(physical)


@pytest.fixture
def stack(boundary, tmp_path, monkeypatch):
    gate, request, actor, shared = boundary
    identity_root = tmp_path / "identities"
    identity = identity_root / "epoch-1"
    journal = tmp_path / "journal"
    for path in (identity_root, identity, journal):
        path.mkdir(mode=0o700)
        if path != journal and os.getuid() == 0:
            os.chown(path, gate.uid, gate.uid)
    request["HostConfig"]["Mounts"].append({"Type": "bind", "Source": str(identity),
        "Target": "/run/jiuwenswarm", "ReadOnly": True})
    state = {"containers": {}, "creates": 0, "deletes": [], "drop": False}

    class Docker(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self): self.perform()
        do_POST = do_DELETE = do_GET
        def perform(self):
            target = urlsplit(self.path)
            if self.command == "POST":
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                name = parse_qs(target.query)["name"][0]
                if name in state["containers"]:
                    status, value = 409, {}
                else:
                    state["creates"] += 1
                    identifier = f'{state["creates"]:064x}'
                    state["containers"][name] = {"Id": identifier, "Image": body["Image"], "Config": body,
                        "State": {"Status": "created", "Running": False, "StartedAt": "0001-01-01T00:00:00Z"},
                        "Mounts": [{"Source": m["Source"], "Destination": m["Target"], "RW": not m.get("ReadOnly", False)}
                            for m in body["HostConfig"]["Mounts"]]}
                    status, value = 201, {"Id": identifier}
                    if state["drop"]:
                        state["drop"] = False
                        self.connection.shutdown(socket.SHUT_RDWR)
                        return
            elif self.command == "DELETE":
                assert parse_qs(target.query) == {"force": ["false"], "v": ["false"]}
                identifier = target.path.split("/")[2]
                state["deletes"].append(identifier)
                state["containers"] = {n: c for n, c in state["containers"].items() if c["Id"] != identifier}
                status, value = 204, None
            else:
                value = state["containers"].get(target.path.split("/")[2])
                status = 200 if value else 404
            raw = json.dumps(value).encode() if value else b""
            self.send_response(status); self.send_header("Content-Length", str(len(raw)))
            self.end_headers(); self.wfile.write(raw)

    def absent(*args, **kwargs):
        raise HTTPError("http://frontend/api/agent/instance", 404, "gone", {}, None)
    monkeypatch.setattr(physical, "urlopen", absent)
    servers = []
    def serve(path, handler):
        server = module.Server(str(path), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        servers.append((server, thread)); thread.start()
        return server
    upstream = tmp_path / "docker.sock"
    serve(upstream, Docker)
    resources = physical.PhysicalResources(gate, journal, identity_root, "/run/jiuwenswarm", str(upstream), "http://frontend")
    proxy = tmp_path / "proxy.sock"
    server = serve(proxy, module.Handler)
    server.boundary, server.upstream, server.resources = gate, str(upstream), resources
    restricted = tmp_path / "confirm.sock"
    server = serve(restricted, module.ConfirmationHandler); server.resources = resources
    payload = dict(workspace=str(actor), identity=str(identity), image=request["Image"], user=request["User"], instance_id="instance-1")
    yield resources, request, state, proxy, restricted, payload
    for server, thread in reversed(servers):
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def call(path, method, target, value):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(3); connection.connect(str(path))
        body = json.dumps(value).encode()
        connection.sendall(f"{method} {target} HTTP/1.1\r\nHost: test\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()+body)
        response = http.client.HTTPResponse(connection); response.begin()
        return response.status, response.read()


def create(stack):
    return call(stack[3], "POST", "/v1.41/containers/create", stack[1])[0]


def test_lost_create_response_recovered_without_replay_and_fences_late_request(stack):
    resources, request, state, proxy, restricted, payload = stack
    state["drop"] = True
    with pytest.raises(http.client.RemoteDisconnected): create(stack)
    assert state["creates"] == 1
    assert create(stack) == 502 and state["creates"] == 1
    # New process/object uses only persistent deployment evidence.
    restored = physical.PhysicalResources(resources.boundary, resources.root, resources.identity_root,
        resources.identity_target, resources.upstream, resources.frontend)
    assert restored.confirm_deleted(payload)["absent"] is True
    assert not state["containers"] and len(state["deletes"]) == 1
    assert create(stack) == 502  # Late request from the already-deleted generation.
    identity = Path(payload["identity"]).with_name("epoch-2"); identity.mkdir(mode=0o700)
    if os.getuid() == 0: os.chown(identity, resources.boundary.uid, resources.boundary.uid)
    request["HostConfig"]["Mounts"][-1]["Source"] = str(identity)
    assert create(stack) == 201 and state["creates"] == 2 and len(state["containers"]) == 1


def test_unknown_dispatch_with_no_observation_never_assumes_absence(stack):
    resources, request, state, proxy, restricted, payload = stack
    with resources.dispatch(request, "/containers/create") as (path, receipt, _):
        receipt["state"] = "SENT"; resources.write(path, receipt)
    assert call(restricted, "POST", "/v1/confirm-deleted", payload)[0] == 503
    assert create(stack) == 502 and state["creates"] == 0


@pytest.mark.parametrize("change", ["running", "exited", "image", "identity", "label", "frontend"])
def test_no_compensation_without_exact_ownership_and_never_started_state(stack, monkeypatch, change):
    resources, request, state, proxy, restricted, payload = stack
    assert create(stack) == 201
    container = next(iter(state["containers"].values()))
    if change == "running": container["State"].update(Status="running", Running=True)
    elif change == "exited": container["State"].update(Status="exited", StartedAt="2026-11-10T00:00:00Z")
    elif change == "image": container["Image"] = "foreign"
    elif change == "identity": container["Mounts"][-1]["Source"] += "-foreign"
    elif change == "label": container["Config"]["Labels"][physical.LABEL] = "foreign"
    else:
        def live(*args, **kwargs): raise HTTPError("http://frontend", 503, "unavailable", {}, None)
        monkeypatch.setattr(physical, "urlopen", live)
    assert call(restricted, "POST", "/v1/confirm-deleted", payload)[0] == 503
    assert state["deletes"] == [] and len(state["containers"]) == 1


def test_confirmation_socket_does_not_forward_docker_and_limits_payload(stack):
    *_, restricted, payload = stack
    assert call(restricted, "POST", "/containers/create", payload)[0] == 503
    assert call(restricted, "GET", "/containers/json", {})[0] == 501
    assert call(restricted, "POST", "/v1/confirm-deleted", {**payload, "force": True})[0] == 503
    assert call(restricted, "POST", "/v1/confirm-deleted", {"data": "x"*8192})[0] == 503
    assert stack[2]["creates"] == 0


@pytest.mark.asyncio
async def test_gateway_restricted_client_uses_actual_unix_transport(stack):
    from gateway.services.resource_reconciler import ResourceReconciler
    resources, request, state, proxy, restricted, payload = stack
    assert create(stack) == 201
    await ResourceReconciler(restricted).confirm_deleted(**payload)
    assert state["deletes"] and not state["containers"]


def test_slot_lock_prevents_concurrent_create_or_confirmation(stack):
    resources, request, state, proxy, restricted, payload = stack
    with resources.dispatch(request, "/containers/create"):
        assert create(stack) == 502
        assert call(restricted, "POST", "/v1/confirm-deleted", payload)[0] == 503
    assert state["creates"] == 0
    assert call(restricted, "POST", "/v1/confirm-deleted", payload)[0] == 200
    assert create(stack) == 502


def test_receipt_temporary_hardlink_is_rejected_without_truncating_target(stack, tmp_path):
    resources = stack[0]
    target = tmp_path / "retained"; target.write_text("retained"); target.chmod(0o600)
    path = resources.root / "receipt.json"
    os.link(target, path.with_name(path.name + ".tmp"))
    with pytest.raises(ValueError, match="temporary"):
        resources.write(path, {"state": "DELETED"})
    assert target.read_text() == "retained" and not path.exists()


def test_restricted_socket_lease_accepts_only_operator_owned_group_endpoint(tmp_path):
    group = os.getgid()
    parent = tmp_path / "restricted"; parent.mkdir(mode=0o710)
    path = parent / "confirm.sock"
    with module.socket_lease(path, False, group):
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(path)); path.chmod(0o660)
            assert module.socket_identity(path, group)
    with module.socket_lease(path, True, group):
        assert not path.exists()
    parent.chmod(0o770)
    with pytest.raises(ValueError):
        with module.socket_lease(path, False, group): pass
