"""Durable dispatch/confirmation tests over real Unix HTTP sockets."""
import copy
from contextlib import nullcontext
import http.client
import http.server
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import threading
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs

import pytest

from tests.unit_tests.cloud_workspace.test_docker_log_boundary import boundary, module

spec = importlib.util.spec_from_file_location("physical_resources", Path(module.__file__).with_name("physical_resources.py"))
physical = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(Path(spec.origin).parent))
try:
    spec.loader.exec_module(physical)
finally:
    sys.path.pop(0)


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


@pytest.fixture
def provider(boundary, tmp_path, monkeypatch):
    gate, worker, account, shared = boundary
    provider_root = tmp_path / "providers"
    binding = provider_root / ("b" * 32)
    state = binding / "state"
    generation = binding / ("a" * 32)
    project = account / "agent/workspace/project"
    project.mkdir(parents=True)
    for path in (provider_root, binding, state, generation):
        path.mkdir(mode=0o700)
    if os.getuid() == 0:
        for path in (provider_root, binding, state, generation, project):
            os.chown(path, gate.uid, gate.uid)
    journal = tmp_path / "journal"
    journal.mkdir(mode=0o700)
    credentials = tmp_path / "worker-identities"
    credentials.mkdir(mode=0o700)
    if os.getuid() == 0:
        os.chown(credentials, gate.uid, gate.uid)
    image = "sha256:" + "4" * 64
    target = "/data/agent/workspace/project"
    definition_path = binding / "scope.json"
    definition = {"version": 1, "binding_id": binding.name, "account_workspace": str(account),
                  "project_source": str(project), "project_target": target, "image": image, "user": gate.user}
    definition_path.write_text(json.dumps(definition))
    definition_path.chmod(0o600)
    if os.getuid() == 0:
        os.chown(definition_path, gate.uid, gate.uid)
    resources = physical.PhysicalResources(gate, journal, credentials, "/run/jiuwenswarm", str(tmp_path / "docker.sock"),
        "http://frontend", provider_root=provider_root, provider_images=[image])
    request = {"Image": image, "User": gate.user, "HostConfig": {"Mounts": [
        {"Type": "bind", "Source": str(project), "Target": target},
        {"Type": "bind", "Source": str(state), "Target": "/state"},
        {"Type": "bind", "Source": str(generation), "Target": "/run/opencode", "ReadOnly": True},
        {"Type": "bind", "Source": str(state), "Target": "/home/" + gate.user},
        {"Type": "bind", "Source": str(shared), "Target": str(shared)},
    ]}}
    response = {"container": None, "renamed": None, "deletes": [], "frontend_absent": True}

    def docker(method, path):
        if method == "DELETE":
            response["deletes"].append(path)
            response["container"] = None
            return 204, {}
        assert method == "GET"
        if path.startswith("/containers/cpo-"):
            value = response["container"]
        else:
            assert path == "/containers/" + "1" * 64 + "/json"
            value = response["renamed"]
        return (404, {}) if value is None else (200, value)

    def check_frontend(url, **kwargs):
        if response["frontend_absent"]:
            raise HTTPError(url, 404, "absent", {}, None)
        raise HTTPError(url, 503, "unavailable", {}, None)

    monkeypatch.setattr(resources, "docker", docker)
    monkeypatch.setattr(physical, "urlopen", check_frontend)
    payload = dict(workspace=str(state), identity=str(generation), image=image, user=gate.user, instance_id="op-1")
    return resources, request, payload, definition_path, response


def _prepare_provider(resources, request):
    scope = resources.create_scope(request)
    rewritten, _ = resources.boundary.rewrite(request, provider_scope=scope)
    return scope, rewritten


def test_shared_physical_scope_allows_only_the_bound_workers_project_root(provider):
    resources, request, _, path, _ = provider
    definition = json.loads(path.read_text())
    worker_root = Path(definition["account_workspace"], "agent/workspace")
    if os.getuid() == 0:
        os.chown(worker_root, resources.boundary.uid, resources.boundary.uid)
    definition.update(version=2, project_source=str(worker_root), project_target=str(physical.PROJECT_ROOT))
    path.write_text(json.dumps(definition))
    mount = request["HostConfig"]["Mounts"][0]
    mount.update(Source=str(worker_root), Target=str(physical.PROJECT_ROOT))
    scope, _ = _prepare_provider(resources, request)
    assert scope["project_source"] == str(worker_root)
    mount.update(Source=definition["account_workspace"], Target="/data")
    with pytest.raises(ValueError, match="physical project, state or generation"):
        _prepare_provider(resources, request)
    definition["version"] = 1
    path.write_text(json.dumps(definition))
    with pytest.raises(ValueError, match="outside its account binding"):
        _prepare_provider(resources, request)


@pytest.mark.parametrize("invalid", ["wrong_project", "wrong_generation", "worker", "alias", "volume", "writable_config"])
def test_provider_physical_scope_rejects_unapproved_mounts(provider, invalid):
    resources, request, *_ = provider
    mounts = request["HostConfig"]["Mounts"]
    if invalid == "wrong_project":
        mounts[0]["Source"] = mounts[0]["Source"].replace("env_" + "1" * 32, "env_" + "2" * 32)
    elif invalid == "wrong_generation":
        mounts[2]["Source"] = mounts[2]["Source"].replace("b" * 32, "c" * 32)
    elif invalid == "worker":
        mounts.append({"Type": "bind", "Source": mounts[0]["Source"], "Target": "/data"})
    elif invalid == "alias":
        mounts[3]["Source"] = mounts[0]["Source"]
    elif invalid == "volume":
        mounts.append({"Type": "volume", "Source": "other", "Target": "/extra"})
    else:
        mounts[2]["ReadOnly"] = False
    with pytest.raises(ValueError):
        resources.create_scope(request)


def test_provider_physical_scope_authenticates_binding_and_legacy_binds(provider):
    resources, request, _, definition, _ = provider
    original = resources.create_scope(request)
    assert original["role"] == "opencode" and original["name"] == "cpo-" + original["slot"]
    host = request["HostConfig"]
    host["Binds"] = [f'{m["Source"]}:{m["Target"]}:{"ro" if m.get("ReadOnly") else "rw"}' for m in host.pop("Mounts")]
    assert resources.create_scope(request) == original
    scope = json.loads(definition.read_text())
    scope["account_workspace"] = scope["account_workspace"].replace("env_" + "1" * 32, "env_" + "2" * 32)
    definition.write_text(json.dumps(scope))
    with pytest.raises(ValueError, match="outside its account binding"):
        resources.create_scope(request)


def test_provider_physical_scope_supports_stock_log_root_trailing_slash(provider):
    resources, request, *_ = provider
    host = request["HostConfig"]
    mounts = host.pop("Mounts")
    log = mounts[-1]["Source"]
    host["Binds"] = [f'{m["Source"]}:{m["Target"]}' + (":ro" if m.get("ReadOnly") else "")
                     for m in mounts[:-1]] + [f"{log}/:{log}/"]
    scope, rewritten = _prepare_provider(resources, request)
    private_log = resources.boundary.log_root / scope["slot"]
    assert rewritten["HostConfig"]["Binds"][-1] == f"{private_log}:{log}/"
    with resources.dispatch(rewritten, "/containers/create", scope=scope):
        pass
    host["Binds"].append(f"{log}:{log}")
    with pytest.raises(ValueError, match="invalid OpenCode physical log mount"):
        resources.create_scope(request)


def test_provider_confirmation_fences_live_container_and_reuses_physical_slot(provider):
    resources, request, payload, _, response = provider
    scope, rewritten = _prepare_provider(resources, request)
    assert str(resources.boundary.log_root / scope["slot"]) in str(rewritten["HostConfig"]["Mounts"])
    with pytest.raises(ValueError, match="no physical dispatch receipt"):
        resources.confirm_deleted(payload)
    with resources.dispatch(rewritten, "/containers/create", scope=scope) as (receipt_file, receipt, path):
        assert parse_qs(urlsplit(path).query)["name"] == [scope["name"]]
        receipt.update(state="CREATED", observed=True, container_id="1" * 64)
        resources.write(receipt_file, receipt)
    response["container"] = {"Id": "1" * 64, "Image": scope["image"], "Config": rewritten,
        "State": {"Status": "exited", "Running": False, "StartedAt": "2026-11-21T02:00:00Z"},
        "Mounts": [{"Type": "bind", "Source": m["Source"], "Destination": m["Target"], "RW": not m.get("ReadOnly", False)}
                   for m in rewritten["HostConfig"]["Mounts"]]}
    with pytest.raises(ValueError, match="original lifecycle recovery"):
        resources.confirm_deleted(payload)
    assert response["deletes"] == [] and resources.read(receipt_file)["state"] == "CREATED"
    next_identity = Path(payload["identity"]).with_name("c" * 32)
    next_identity.mkdir(mode=0o700)
    if os.getuid() == 0:
        os.chown(next_identity, resources.boundary.uid, resources.boundary.uid)
    request["HostConfig"]["Mounts"][2]["Source"] = str(next_identity)
    next_scope, next_request = _prepare_provider(resources, request)
    assert scope["slot"] == next_scope["slot"] and scope["key"] != next_scope["key"]
    with pytest.raises(ValueError, match="previous physical operation"):
        with resources.dispatch(next_request, "/containers/create", scope=next_scope):
            pass
    response["renamed"] = response["container"]
    response["container"] = None
    with pytest.raises(ValueError, match="observed OpenCode container absence remains unconfirmed"):
        resources.confirm_deleted(payload)
    assert response["deletes"] == [] and resources.read(receipt_file)["state"] == "CREATED"
    response["renamed"] = None
    assert resources.confirm_deleted(payload)["absent"] is True
    with pytest.raises(ValueError, match="already dispatched"):
        with resources.dispatch(rewritten, "/containers/create", scope=scope):
            pass
    with resources.dispatch(next_request, "/containers/create", scope=next_scope):
        assert Path(scope["workspace"]).is_dir()


def test_provider_confirmation_validates_observed_id_before_orphan_delete(provider):
    resources, request, payload, _, response = provider
    scope, rewritten = _prepare_provider(resources, request)
    with resources.dispatch(rewritten, "/containers/create", scope=scope) as (journal, receipt, _):
        receipt.update(state="CREATED", observed=True, container_id="1" * 64)
        resources.write(journal, receipt)
    response["container"] = {"Id": "2" * 64, "Image": scope["image"], "Config": rewritten,
        "State": {"Status": "created", "Running": False, "StartedAt": "0001-01-01T00:00:00Z"},
        "Mounts": [{"Type": "bind", "Source": m["Source"], "Destination": m["Target"], "RW": not m.get("ReadOnly", False)}
                   for m in rewritten["HostConfig"]["Mounts"]]}
    with pytest.raises(ValueError, match="identity differs from the receipt"):
        resources.confirm_deleted(payload)
    assert response["deletes"] == []
    response["container"]["Id"] = "1" * 64
    assert resources.confirm_deleted(payload)["absent"] is True
    assert response["deletes"] == ["/containers/" + "1" * 64 + "?force=false&v=false"]


def test_provider_fault_check_uses_only_the_confirmed_running_container_bridge(provider, monkeypatch):
    resources, request, payload, _, response = provider
    scope, rewritten = _prepare_provider(resources, request)
    with resources.dispatch(rewritten, "/containers/create", scope=scope) as (journal, receipt, _):
        receipt.update(state="CREATED", observed=True, container_id="1" * 64)
        resources.write(journal, receipt)
    container = response["container"] = {
        "Id": "1" * 64, "Image": scope["image"], "Config": rewritten,
        "State": {"Status": "running", "Running": True},
        "NetworkSettings": {"Networks": {"bridge": {"IPAddress": "172.18.0.3"}}},
        "Mounts": [{"Type": "bind", "Source": mount["Source"], "Destination": mount["Target"],
                    "RW": not mount.get("ReadOnly", False)} for mount in rewritten["HostConfig"]["Mounts"]],
    }
    outcome = None
    checks = []

    def connect(address, *, timeout):
        checks.append(address)
        assert 0 < timeout <= 2
        if outcome is not None:
            raise outcome
        return nullcontext()

    monkeypatch.setattr(physical.socket, "create_connection", connect)
    assert resources.confirm_opencode_unavailable(payload) == {"unavailable": False}
    outcome = ConnectionRefusedError()
    assert resources.confirm_opencode_unavailable(payload) == {"unavailable": True}
    outcome = TimeoutError()
    with pytest.raises(TimeoutError):
        resources.confirm_opencode_unavailable(payload)
    container["Id"] = "2" * 64
    with pytest.raises(ValueError, match="confirmed running instance"):
        resources.confirm_opencode_unavailable(payload)
    container["Id"] = "1" * 64
    container["NetworkSettings"]["Networks"]["bridge"]["IPAddress"] = "127.0.0.1"
    with pytest.raises(ValueError, match="not private"):
        resources.confirm_opencode_unavailable(payload)
    assert checks == [("172.18.0.3", 4096)] * 3
    assert response["deletes"] == [] and resources.read(journal)["state"] == "CREATED"


@pytest.mark.parametrize(("connect_error", "write_error", "read_result", "stalled"), [
    (TimeoutError, None, None, None),
    (ConnectionRefusedError, None, None, None),
    (None, TimeoutError, None, None),
    (None, None, TimeoutError, True),
    (None, None, ConnectionResetError, None),
    (None, None, b"H", False),
    (None, None, b"", False),
])
def test_provider_stall_requires_successful_connect_and_write_before_read_timeout(
    provider, monkeypatch, connect_error, write_error, read_result, stalled,
):
    resources, _, payload, _, _ = provider
    address = ("172.18.0.3", 4096)
    monkeypatch.setattr(resources, "_opencode_probe_address", lambda request: nullcontext(address))

    class Connection:
        def sendall(self, raw):
            assert raw.startswith(b"GET /global/health HTTP/1.1\r\n")
            assert b"Authorization" not in raw
            if write_error:
                raise write_error()

        def recv(self, size):
            assert size == 1
            if isinstance(read_result, type):
                raise read_result()
            return read_result

    def connect(target, *, timeout):
        assert target == address and 0 < timeout <= 2
        if connect_error:
            raise connect_error()
        return nullcontext(Connection())

    monkeypatch.setattr(physical.socket, "create_connection", connect)
    if stalled is None:
        with pytest.raises(OSError):
            resources.confirm_opencode_stalled(payload)
    else:
        assert resources.confirm_opencode_stalled(payload) == {"stalled": stalled}


def test_opencode_stall_confirmation_rejects_worker_scope(stack):
    _, _, _, _, restricted, payload = stack
    assert call(restricted, "POST", "/v1/confirm-opencode-stalled", payload)[0] == 503


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


def test_runtime_mount_is_pinned_and_absent_node_refuses_create(provider, monkeypatch):
    resources, request, _, anchor, _ = provider
    generation_mount = request["HostConfig"]["Mounts"][2]
    source = Path("/opt/runtime-assets") / ("9" * 64)
    definition = json.loads(anchor.read_text())
    definition.update(image="sha256:" + "5" * 64, shared_runtime=str(source))
    generation = Path(generation_mount["Source"]) / "scope.json"
    generation.write_text(json.dumps(definition))
    generation.chmod(0o600)
    if os.getuid() == 0:
        os.chown(generation, resources.boundary.uid, resources.boundary.uid)
    image = definition["image"]
    resources.provider_images = resources.provider_images | {image}
    resources.runtime_assets[image] = source
    request["Image"] = image
    runtime = {"Type": "bind", "Source": str(source), "Target": physical.RUNTIME_TARGET, "ReadOnly": True}
    request["HostConfig"]["Mounts"].append(runtime)

    def unavailable(_):
        raise FileNotFoundError()

    monkeypatch.setattr(physical, "runtime_identity", unavailable)
    with pytest.raises(ValueError, match="not provisioned"):
        resources.create_scope(request)

    monkeypatch.setattr(physical, "runtime_identity", lambda _: (10, 11))
    monkeypatch.setattr(physical, "tree_digest", lambda _: "0" * 64)
    with pytest.raises(ValueError, match="digest mismatch"):
        resources.create_scope(request)
    monkeypatch.setattr(physical, "tree_digest", lambda _: source.name)
    assert resources.create_scope(request)["shared_runtime"] == str(source)
    runtime["ReadOnly"] = False
    with pytest.raises(ValueError, match="mount differs"):
        resources.create_scope(request)
    runtime["ReadOnly"] = True
    definition["project_target"] = "/data/agent/workspace/other"
    generation.write_text(json.dumps(definition))
    with pytest.raises(ValueError, match="outside its account binding"):
        resources.create_scope(request)
