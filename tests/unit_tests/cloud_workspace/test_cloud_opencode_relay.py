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
from gateway.services.cloud_opencode_relay import CloudOpencodeRelay, _OpenCodeQueryAuthTransport


ROUTE = "/provider/opencode"
DIRECTORY = "/data/agent/workspace/demo"


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

        @asynccontextmanager
        async def hold(self, account, project, directory):
            self.active += 1
            try:
                yield SimpleNamespace(
                    instance_id=account["account_id"] + "-" + project, directory=directory, password="only-upstream",
                )
            finally:
                self.active -= 1

    store = SimpleNamespace(by_user=accounts.__getitem__, guard_binding=lambda *args: nullcontext())
    pool = Pool()
    broker = CloudOpencodeRelay(store, pool)
    app = Starlette(routes=[Route(ROUTE + "/{project_id}/{path:path}", broker.handle, methods=["GET", "POST"])])
    return broker, app, credentials, accounts


def _client(app, auth=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://gateway.test", auth=auth)


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "body", "expected"), [
    (502, "failed to dial sandbox\n", True),
    (502, "bad gateway", False),
    (404, "sandbox not found", False),
    (401, "", False),
    (200, '{"healthy":true}', False),
    (httpx.ConnectTimeout, "", False),
    (httpx.RemoteProtocolError, "", True),
])
async def test_fault_probe_classifies_frontend_dial_failure_and_disconnect(relay, status, body, expected):
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
        assert await broker.pool.unavailable_check(lease) is expected


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
