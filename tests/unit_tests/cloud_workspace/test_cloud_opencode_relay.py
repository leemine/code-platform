import asyncio
import base64
from contextlib import asynccontextmanager, nullcontext
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from gateway.common.security.opencode_relay_auth import HEADER, OpenCodeRelayAuth
from gateway.services.cloud_opencode_pool import OpenCodeFault
from gateway.services.cloud_opencode_relay import CloudOpencodeRelay, _OpenCodeQueryAuthTransport


ROUTE = "/provider/opencode"
SHARED_ROUTE = ROUTE + "-worker"
DIRECTORY = "/data/agent/workspace/demo"


@pytest.mark.parametrize(("shared", "runtime_id", "suffix"), [
    (False, None, ""),
    (True, None, "-worker"),
    (True, "a" * 32, "-device/" + "a" * 32),
])
def test_worker_relay_paths_use_deployment_tls_context(monkeypatch, relay, shared, runtime_id, suffix):
    import ssl

    from gateway.common.security import provider_relay_tls
    from jiuwenswarm.server.runtime.agent_adapter.providers import opencode_managed

    context = ssl.create_default_context()
    captured = {}
    monkeypatch.setattr(provider_relay_tls, "relay_ssl_context", lambda: context)
    monkeypatch.setattr(opencode_managed.httpx, "AsyncClient", lambda **options: captured.update(options))

    _, _, credentials, _ = relay
    origin = "https://relay.example.test/provider/managed/opencode"
    opencode_managed.relay_client(origin, credentials["one"], "project", shared=shared, runtime_id=runtime_id)

    assert captured["base_url"] == origin + suffix + "/project"
    assert captured["verify"] is context
    assert captured["trust_env"] is False


@pytest.fixture
def relay(tmp_path):
    accounts, credentials = {}, {}
    for index, actor in enumerate(("one", "two"), 1):
        workspace = tmp_path / actor
        (workspace / "agent").mkdir(parents=True)
        projects = [{"project_id": "same", "project_dir": DIRECTORY}]
        if actor == "one":
            projects.append({"project_id": "private", "project_dir": DIRECTORY + "-private"})
        (workspace / "agent/projects.json").write_text(json.dumps({"projects": projects}))
        auth = tmp_path / (actor + ".json")
        auth.write_text(json.dumps({
            "mode": "user_instance", "instance_id": actor + "-worker", "epoch": 1, "workspace": str(workspace),
            "login_owner": {"actor_id": actor, "authority": "test-org"}, "signing_key": str(index) * 64,
        }))
        auth.chmod(0o600)
        credentials[actor] = auth
        accounts[actor] = {"state": "ALLOCATED", "epoch": 1, "environment_id": actor + "-worker",
                           "account_id": actor, "auth_file": auth, "workspace": str(workspace),
                           "authority": "test-org"}

    class Pool:
        yuanrong = SimpleNamespace(frontend_endpoint="https://yuanrong.test", agent_namespace="tests")
        active = 0
        sessions = {}

        @asynccontextmanager
        async def hold(self, account, project, directory, *, shared=False):
            self.active += 1
            binding_id = account["account_id"] + ("-shared" if shared else "-" + project)
            try:
                yield SimpleNamespace(
                    instance_id=binding_id, binding_id=binding_id, directory=directory, password="only-upstream",
                )
            finally:
                self.active -= 1

        def register_session(self, lease, project_id, native_id):
            self.sessions[(lease.binding_id, native_id)] = (project_id, lease.directory)

        def project_sessions(self, lease, project_id):
            return {native_id for (binding, native_id), scope in self.sessions.items()
                    if binding == lease.binding_id and scope == (project_id, lease.directory)}

        def owns_session(self, lease, project_id, native_id):
            return self.sessions.get((lease.binding_id, native_id)) == (project_id, lease.directory)

    store = SimpleNamespace(by_user=accounts.__getitem__, guard_binding=lambda *args: nullcontext())
    pool = Pool()
    broker = CloudOpencodeRelay(store, pool)
    app = Starlette(routes=[
        Route(ROUTE + "/{project_id}/{path:path}", broker.handle, methods=["GET", "POST"]),
        Route(SHARED_ROUTE + "/{project_id}/{path:path}", broker.handle_shared, methods=["GET", "POST"]),
    ])
    return broker, app, credentials, accounts


def _client(app, auth=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://gateway.test", auth=auth)


@pytest.mark.asyncio
async def test_shared_relay_keeps_session_routes_events_and_controls_project_scoped(relay):
    broker, app, credentials, _ = relay
    requests = []
    sessions = {"ses_same": {"id": "ses_same", "directory": DIRECTORY},
                "ses_private": {"id": "ses_private", "directory": DIRECTORY + "-private"}}
    events = [
        {"type": "server.connected", "properties": {"secret": "not forwarded"}},
        {"type": "message.updated", "properties": {"info": {"sessionID": "ses_same"}, "marker": "own"}},
        {"type": "message.part.updated", "properties": {"part": {"sessionID": "ses_private"}, "marker": "foreign"}},
        {"type": "session.updated", "properties": {"info": {"id": "ses_private"}}},
        {"type": "permission.asked", "properties": {"sessionID": "ses_same", "id": "perm_own"}},
        {"type": "session.error", "properties": {"secret": "unscoped"}},
        {"type": "message.updated", "properties": {
            "sessionID": "ses_same", "info": {"sessionID": "ses_private"}, "marker": "conflicting",
        }},
    ]

    async def upstream(request):
        path = request.url.path.removeprefix("/serverless/v1/http/")
        requests.append((request.method, path, request.url.params["instance"]))
        if path == "session" and request.method == "POST":
            native_id = "ses_same" if request.url.params["directory"] == DIRECTORY else "ses_private"
            return httpx.Response(200, json=sessions[native_id])
        if path == "session":
            return httpx.Response(200, json=list(sessions.values()))
        if path == "session/status":
            return httpx.Response(200, json={key: {"type": "busy"} for key in sessions})
        if path in ("permission", "question"):
            return httpx.Response(200, json=[{"id": path + "_own", "sessionID": "ses_same"},
                                             {"id": path + "_foreign", "sessionID": "ses_private"}])
        if path == "event":
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                                  text="".join("data: " + json.dumps(event) + "\n\n" for event in events))
        return httpx.Response(200, json={})

    first, second = SHARED_ROUTE + "/same", SHARED_ROUTE + "/private"
    async with broker._client, httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        broker._client = client
        async with _client(app, OpenCodeRelayAuth(credentials["one"])) as worker:
            assert (await worker.post(first + "/session", json={})).json() == sessions["ses_same"]
            assert (await worker.post(second + "/session", json={})).json() == sessions["ses_private"]
            assert (await worker.get(first + "/session")).json() == [sessions["ses_same"]]
            assert set((await worker.get(first + "/session/status")).json()) == {"ses_same"}
            assert (await worker.get(first + "/session/ses_private/message")).status_code == 404
            assert (await worker.post(first + "/session/ses_private/abort")).status_code == 404
            assert (await worker.post(first + "/session", json={"parentID": "ses_private"})).status_code == 404
            assert (await worker.post(first + "/session/ses_same/prompt_async",
                                      json={"parts": [{"id": "forged", "type": "text", "text": "x"}]})).status_code == 403
            for kind in ("permission", "question"):
                assert (await worker.post(f"{first}/{kind}/{kind}_foreign/reply", json={})).status_code == 404
                assert (await worker.post(f"{first}/{kind}/{kind}_own/reply", json={})).status_code == 200
            event_stream = await worker.get(first + "/event")
            assert event_stream.status_code == 200 and '"marker": "own"' in event_stream.text
            assert '"id": "perm_own"' in event_stream.text
            assert all(value not in event_stream.text for value in ("ses_private", "foreign", "conflicting", "secret"))
        async with _client(app, OpenCodeRelayAuth(credentials["two"])) as another:
            assert (await another.get(first + "/session")).json() == []
            assert (await another.get(first + "/session/ses_same")).status_code == 404
    assert all(path not in ("session/ses_private/message", "session/ses_private/abort",
                            "permission/permission_foreign/reply", "question/question_foreign/reply")
               for _, path, _ in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(("http_code", "healthy", "expected"), [(200, True, True), (201, True, False), (200, False, False)])
async def test_ready_probe_requires_authenticated_ok_and_healthy_response(relay, http_code, healthy, expected):
    broker, *_ = relay

    async def upstream(request):
        assert request.method == "GET"
        assert request.url.path == "/serverless/v1/http/global/health"
        assert request.headers["authorization"] == "Basic " + base64.b64encode(b"opencode:test").decode()
        return httpx.Response(http_code, json={"healthy": healthy})

    lease = SimpleNamespace(instance_id="scoped-instance", directory=DIRECTORY, password="test")
    async with broker._client, httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        broker._client = client
        assert await broker.pool.ready_check(lease) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "body", "expected"), [
    (502, "failed to dial sandbox\n", OpenCodeFault.LISTENER_UNAVAILABLE),
    (502, "bad gateway", None),
    (504, "", None),
    (404, "sandbox not found", None),
    (401, "", None),
    (200, '{"healthy":true}', None),
    (httpx.ConnectTimeout, "", None),
    (httpx.WriteTimeout, "", None),
    (httpx.PoolTimeout, "", None),
    (httpx.ReadTimeout, "", OpenCodeFault.HEALTH_STALLED),
    (httpx.RemoteProtocolError, "", OpenCodeFault.LISTENER_UNAVAILABLE),
])
async def test_fault_probe_distinguishes_frontend_read_timeout_and_connection_failure(relay, status, body, expected):
    broker, *_ = relay

    async def upstream(request):
        assert request.url.path == "/serverless/v1/http/global/health"
        assert request.url.params["instance"] == "scoped-instance"
        if isinstance(status, type):
            raise status("transport failed")
        return httpx.Response(status, text=body)

    lease = SimpleNamespace(instance_id="scoped-instance", directory=DIRECTORY, password="test")
    async with broker._client, httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        broker._client = client
        assert await broker.pool.fault_check(lease) is expected


@pytest.mark.asyncio
async def test_query_auth_keeps_the_credential_off_the_client_request_and_logs(caplog):
    password = "isolated-opencode-credential"
    expected = base64.b64encode(f"opencode:{password}".encode()).decode()

    async def upstream(request):
        assert request.url.params["auth_token"] == expected
        assert request.url.params["directory"] == DIRECTORY
        assert "Authorization" not in request.headers
        assert await request.aread() == b"{}"
        return httpx.Response(200, json={"healthy": True})

    transport = _OpenCodeQueryAuthTransport(httpx.MockTransport(upstream))
    with caplog.at_level(logging.INFO, logger="httpx"):
        async with httpx.AsyncClient(transport=transport) as client:
            result = await client.post("http://127.0.0.1/serverless/v1/http/session",
                                       params={"directory": DIRECTORY}, auth=("opencode", password), content=b"{}")
    assert result.json() == {"healthy": True}
    assert "auth_token" not in result.request.url.params
    assert "HTTP Request:" in caplog.text and "auth_token" not in caplog.text
    assert expected not in caplog.text and password not in caplog.text


@pytest.mark.asyncio
async def test_relay_routes_account_projects_and_only_forwards_provider_auth(relay):
    broker, app, credentials, _ = relay
    seen = []

    async def upstream(request):
        seen.append(request)
        if request.url.path.endswith("/provider"):
            return httpx.Response(200, json={"all": [{"id": "test", "models": {"m": {"name": "Model"}}, "key": "private"}]})
        return httpx.Response(200, json={"healthy": True})

    async with broker._client, httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        broker._client = client
        for actor in ("one", "two"):
            async with _client(app, OpenCodeRelayAuth(credentials[actor])) as worker:
                health = await worker.get(ROUTE + "/same/global/health")
                assert health.json()["healthy"] and broker.pool.active == 0
                models = await worker.get(ROUTE + "/same/provider", params={"directory": DIRECTORY})
                assert models.json() == {"all": [{"id": "test", "models": {"m": None}}]}
                wrong = await worker.get(ROUTE + "/same/event", params={"directory": "/data"})
                assert wrong.status_code == 403
        async with _client(app, OpenCodeRelayAuth(credentials["two"])) as worker:
            assert (await worker.get(ROUTE + "/private/global/health")).status_code == 403

    assert [x.url.params["instance"] for x in seen] == ["one-same", "one-same", "two-same", "two-same"]
    assert all(x.url.params["directory"] == DIRECTORY and x.url.params["port"] == "4096" for x in seen)
    assert all(x.url.path.startswith("/serverless/v1/http/") for x in seen)
    assert all(HEADER not in x.headers and x.headers.get("authorization", "").startswith("Basic ") for x in seen)


@pytest.mark.asyncio
async def test_relay_denies_replay_changed_body_and_stale_worker(relay):
    broker, app, credentials, accounts = relay

    async def upstream(request):
        return httpx.Response(200, json={"id": "ses_same"})

    path = ROUTE + "/same/session"
    async with broker._client, httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client, _client(app) as worker:
        broker._client = client
        auth = OpenCodeRelayAuth(credentials["one"])
        assert (await worker.post(path, json={})).status_code == 403
        signed = next(auth.auth_flow(worker.build_request("POST", path, json={})))
        assert (await worker.send(signed)).status_code == 200
        assert (await worker.send(signed)).status_code == 403
        original = next(auth.auth_flow(worker.build_request("POST", path, json={})))
        altered = worker.build_request("POST", path, json={"title": "tampered"}, headers={HEADER:original.headers[HEADER]})
        assert (await worker.send(altered)).status_code == 403
        accounts["one"]["epoch"] += 1
        assert (await worker.post(path, json={}, auth=auth)).status_code == 403
        assert broker.pool.active == 0


@pytest.mark.asyncio
async def test_relay_holds_provider_while_sse_response_is_open(relay):
    broker, app, credentials, _ = relay
    active, finish = asyncio.Event(), asyncio.Event()

    class Events(httpx.AsyncByteStream):
        async def __aiter__(self):
            assert broker.pool.active == 1
            active.set()
            await finish.wait()
            yield b"data: {}\n\n"

    async def upstream(request):
        return httpx.Response(200, stream=Events(), headers={"Content-Type":"text/event-stream"})

    async with broker._client, httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        broker._client = client
        async with _client(app, OpenCodeRelayAuth(credentials["one"])) as worker:
            event = asyncio.create_task(worker.get(ROUTE + "/same/event", params={"directory": DIRECTORY}))
            try:
                await asyncio.wait_for(active.wait(), 2)
                assert broker.pool.active == 1
                finish.set()
                assert (await event).content == b"data: {}\n\n"
                assert broker.pool.active == 0
            finally:
                event.cancel()
                await asyncio.gather(event, return_exceptions=True)

@pytest.mark.asyncio
async def test_account_model_sync_requires_worker_and_project_and_keeps_config_private(relay, monkeypatch):
    from gateway.common.opencode_model_policy import account_models_revision
    broker, app, credentials, _ = relay
    calls = []

    async def sync(account, project, directory, revision, **options):
        calls.append((account["account_id"], project, directory, options["shared"]))
        return revision

    monkeypatch.setattr(broker.pool, "sync_models", sync, raising=False)
    path = SHARED_ROUTE + "/private/account-models/sync"
    revision = account_models_revision({})
    async with broker._client, _client(app) as anonymous, _client(app, OpenCodeRelayAuth(credentials["two"])) as other:
        assert (await anonymous.post(path, json={"revision": revision})).status_code == 403
        assert (await other.post(path, json={"revision": revision})).status_code == 403
        async with _client(app, OpenCodeRelayAuth(credentials["one"])) as worker:
            invalid = await worker.post(path, json={"previous": revision, "provider": {"invalid": {}}})
            assert invalid.status_code == 403 and calls == []
            response = await worker.post(path, json={"previous": revision, "provider": {}})
            assert response.json() == {"revision": revision}
            assert calls == [("one", "private", DIRECTORY + "-private", True)]
