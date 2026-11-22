from gateway.services.project_environments import ENVIRONMENT_METHODS
from gateway.services.project_github import METHODS
from gateway.services.project_gitcode import METHODS as GITCODE_METHODS
import asyncio
import hashlib
import hmac
import json
import logging
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
import httpx
from gateway.auth.accounts import AccountStore, AccountError
from gateway.auth.account_authenticator import AccountAuthenticator, current_account
from gateway.auth.request_scope import current_scope
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.common.security.service_auth import ServiceAuthenticator, SERVICE_AUTH_HEADER, check_service_handshake, canonical
from gateway.services.cloud_environments import EnvironmentService, EnvironmentStore, EnvironmentUnavailable
from gateway.services.cloud_instance_policy import CloudInstancePolicy
from gateway.extensions.cloud_workspace.config import CloudConfig
from gateway.extensions.cloud_workspace.extension import CloudWorkspacePlugin
from gateway.extensions.application_host import mount_application_plugin_http_routes
from gateway.extensions.registry import ExtensionRegistry
from gateway.extensions.agentos.agentos_router.models import AgentInfo
from tests.unit_tests.extensions.test_agentos_router import FakeYuanRongClient, FakeAgentWsClient, _router_client

class Infrastructure(FakeYuanRongClient):
    def __init__(self):
        super().__init__()
        self.allocations = {}
        self.lose_reply = self.empty_view = self.delete_pending = False
        self.started = asyncio.Event()
        self.continue_create = None

    async def create_sandbox(self, **kwargs):
        self.started.set()
        if self.continue_create is not None:
            await self.continue_create.wait()
        result = await super().create_sandbox(**kwargs)
        self.allocations[result.sandbox_id] = {"instance_id": result.sandbox_id, "name": kwargs["name"],
            "rootfs": {**kwargs["runtime_spec"]["rootfs"], "workspace": kwargs["workspace"], "mounts": kwargs["mounts"]}, "status": "running"}
        if self.lose_reply:
            raise TimeoutError("POST acknowledgement lost")
        return result

    async def list_agent_instances(self):
        return [] if self.empty_view else list(self.allocations.values())

    async def get_agent_info(self, instance_id):
        return self.allocations[instance_id]

    async def delete_sandbox(self, instance_id):
        self.delete_calls.append(instance_id)
        if not self.delete_pending:
            self.allocations.pop(instance_id, None)

    async def instance_absent(self, instance_id):
        return instance_id not in self.allocations

class Ws(FakeAgentWsClient):
    agent_ready = True
    def set_transport_auth(self, **kwargs):
        self.transport = kwargs

@pytest.fixture
def config(tmp_path):
    authority_config = tmp_path / "authority.json"
    authority_config.write_text(json.dumps({"url": "http://127.0.0.1:1"}))
    authority_config.chmod(0o600)
    return CloudConfig(authority="isolated-test", public_origin="https://127.0.0.1",
        state_root=tmp_path / "control", workspace_root=tmp_path / "users", image="sha256:" + "a" * 64,
        frontend_endpoint="http://yuanrong.test:8888", function_version_urn="urn:test:function:1",
        registration_enabled=True, account_backend_config=str(authority_config))

@pytest.fixture(autouse=True)
def isolated_scope():
    token = current_scope.set(None)
    yield
    current_scope.reset(token)

def service(config, infra):
    accounts = AccountStore(config.state_root.parent / "authority" / "accounts.db", config.authority)
    store = EnvironmentStore(config.state_root / "environments.db", config.authority,
                             config.workspace_root, config.state_root / "auth", config.runtime_profile())
    router = _router_client(infra, ws_client_factory=lambda: Ws(infra), sandbox_idle_timeout_seconds=0,
                            connect_warmup_enabled=False)
    router.configure_instance_lifecycle(CloudInstancePolicy(store), AccountAuthenticator(accounts))
    return accounts, EnvironmentService(store, accounts, router)


def test_runtime_login_preserves_private_volume_uid_gid(config, monkeypatch):
    import pwd
    login = pwd.getpwuid(os.getuid())
    assert config.runtime_profile()["runtime_user"] == login.pw_name
    with pytest.raises(ValueError, match="login name"):
        replace(config, runtime_user=f"{os.getuid()}:{os.getgid()}").validate()
    monkeypatch.setattr(pwd, "getpwnam", lambda _: SimpleNamespace(pw_uid=os.getuid() + 1, pw_gid=os.getgid()))
    with pytest.raises(ValueError, match="uid/gid"):
        replace(config, runtime_user=login.pw_name).validate()


@pytest.mark.asyncio
async def test_reconcile_without_name_requires_exact_private_runtime(config):
    infra = Infrastructure()
    _, app = service(config, infra)
    actor = await registered(app)
    await app.instances.connect("")
    try:
        row = await app.ensure(actor)
        policy = app.instances._instance_lifecycle
        plan = policy.plan(AgentInfo(user_id=actor["user_id"], agent_type="jiuwenswarm"))
        info = infra.allocations[row["instance_id"]]
        info.pop("name")
        assert policy.matches(plan, info)
        for key, value in [("imageurl", "sha256:" + "b" * 64), ("user", "other"), ("workspace", "/other")]:
            assert not policy.matches(plan, {**info, "rootfs": {**info["rootfs"], key: value}})
        assert not policy.matches(plan, {**info, "name": "other-operation"})
    finally:
        await app.instances.disconnect()

async def registered(app, name="test-user"):
    actor, _ = await app.register(name, "long-test-password")
    return actor


@pytest.mark.asyncio
async def test_bound_runtime_home_is_private_persistent_and_not_a_symlink(config, tmp_path):
    _, app = service(config, Infrastructure())
    actor = await registered(app)
    row = app.store.prepare(actor["user_id"])
    home = Path(row["workspace"]) / "home"
    assert home.is_dir() and home.stat().st_mode & 0o777 == 0o700
    assert home.stat().st_uid == os.getuid()
    marker = home / "provider-state"
    marker.write_text("retained")
    app.store.prepare(actor["user_id"])
    assert marker.read_text() == "retained"
    marker.unlink()
    home.rmdir()
    home.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PermissionError, match="symlink"):
        app.store.prepare(actor["user_id"])

@pytest.mark.asyncio
async def test_worker_workspace_mode_does_not_prevent_environment_reconnect(config):
    infra = Infrastructure()
    _, app = service(config, infra)
    actor = await registered(app)
    await app.instances.connect("")
    try:
        initial = await app.ensure(actor)
        workspace = Path(initial["workspace"]) / "agent" / "workspace"
        assert workspace.is_dir()
        workspace.chmod(0o755)
        recovered = await app.ensure(actor)
        assert recovered["state"] == "READY" and recovered["instance_id"] == initial["instance_id"]
        assert infra.create_calls == 1
        assert workspace.stat().st_mode & 0o777 == 0o755
        assert workspace.parent.stat().st_mode & 0o777 == 0o700
    finally:
        await app.instances.disconnect()


@pytest.mark.asyncio
async def test_parallel_connections_and_restart_use_original_singleflight(config):
    infra = Infrastructure()
    _, app = service(config, infra)
    actor = await registered(app)
    await app.instances.connect("")
    rows = await asyncio.gather(*(app.ensure(actor) for _ in range(12)))
    assert infra.create_calls == 1
    assert {r["instance_id"] for r in rows} == {"sbx-1"}
    await app.instances.disconnect()
    _, recovered = service(replace(config, image="sha256:" + "b" * 64), infra)
    await recovered.instances.connect("")
    row = await recovered.ensure(actor)
    assert row["instance_id"] == "sbx-1" and row["profile"]["image_digest"] == config.image
    assert infra.create_calls == 1
    await recovered.instances.disconnect()

@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_unknown_create_never_reposts(config, empty):
    infra = Infrastructure(); infra.lose_reply = True; infra.empty_view = empty
    _, app = service(config, infra)
    actor = await registered(app)
    await app.instances.connect("")
    with pytest.raises(EnvironmentUnavailable) as failed:
        await app.ensure(actor)
    assert isinstance(failed.value.__cause__, TimeoutError)
    assert app.store.get(actor)["state"] == "UNKNOWN"
    if empty:
        for _ in range(2):
            with pytest.raises(EnvironmentUnavailable):
                await app.ensure(actor)
    else:
        assert (await app.ensure(actor))["instance_id"] == "sbx-1"
    assert infra.create_calls == 1
    await app.instances.disconnect()

@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_original_creator(config):
    infra = Infrastructure(); infra.continue_create = asyncio.Event()
    _, app = service(config, infra)
    actor = await registered(app)
    await app.instances.connect("")
    waiter = asyncio.create_task(app.ensure(actor))
    await asyncio.wait_for(infra.started.wait(), 2)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError): await waiter
    infra.continue_create.set()
    assert (await app.ensure(actor))["state"] == "READY"
    assert infra.create_calls == 1
    await app.instances.disconnect()

@pytest.mark.asyncio
async def test_registration_receipt_recovers_after_binding_write_failure(config, monkeypatch):
    accounts, app = service(config, Infrastructure())
    original = app.store.bind_registration
    monkeypatch.setattr(app.store, "bind_registration", lambda *a: (_ for _ in ()).throw(OSError("disk failed")))
    with pytest.raises(OSError): await registered(app)
    original_login = accounts.login("test-user", "long-test-password")
    monkeypatch.setattr(app.store, "bind_registration", original)
    actor = await registered(app)
    assert actor["user_id"] == original_login["user_id"]
    assert app.store.get(actor)["state"] == "NEW"
    with pytest.raises(AccountError):
        await app.register("test-user", "different-password")
    assert b"long-test-password" not in app.store.path.read_bytes()

@pytest.mark.asyncio
async def test_delete_ack_without_absence_blocks_new_epoch_then_recovers(config):
    infra = Infrastructure(); _, app = service(config, infra)
    actor = await registered(app)
    await app.instances.connect("")
    old = await app.ensure(actor)
    infra.delete_pending = True
    with pytest.raises(RuntimeError): await app.instances.delete_agent(actor["user_id"], "jiuwenswarm")
    assert app.store.get(actor)["state"] == "DELETING"
    with pytest.raises(RuntimeError): await app.ensure(actor)
    assert infra.create_calls == 1
    infra.delete_pending = False
    new = await app.ensure(actor)
    assert new["epoch"] == old["epoch"] + 1 and new["operation_id"] != old["operation_id"]
    assert new["workspace"] == old["workspace"] and new["profile"] == old["profile"]
    with pytest.raises(EnvironmentUnavailable): app.store.transition(old, "DELETED")
    await app.instances.disconnect()

@pytest.mark.asyncio
async def test_old_unbound_account_is_not_replaced_and_login_survives(config):
    accounts, app = service(config, Infrastructure())
    actor = accounts.register("old-account", "long-test-password")
    with pytest.raises(EnvironmentUnavailable): await app.ensure(actor)
    assert app.instances._yuanrong.create_calls == 0
    assert accounts.session(accounts.login("old-account", "long-test-password")["token"])["user_id"] == actor["user_id"]

@pytest.mark.asyncio
async def test_private_mounts_and_revoked_request_delivery(config):
    accounts, app = service(config, Infrastructure())
    actor = await registered(app)
    other = await registered(app, "other-user")
    row = app.store.prepare(actor["user_id"])
    other_row = app.store.prepare(other["user_id"])
    assert row["workspace"] != other_row["workspace"] and row["auth_file"] != other_row["auth_file"]
    token = accounts.login("test-user", "long-test-password")["token"]
    result = await app.instances.authenticate_http(path="/ws", headers={"Cookie": "jiuwenswarm_organization=" + token}, channel="web")
    assert result.success and result.user_id == actor["user_id"]
    policy = app.instances._instance_lifecycle
    wire = await policy.sign_request(actor["user_id"], {"method": "config.get", "params": {}})
    assert token not in json.dumps(wire)
    with pytest.raises(PermissionError): await policy.sign_request(other["user_id"], {"method": "config.get"})
    app.store.revoke(actor, token)
    accounts.logout(token)
    with pytest.raises(PermissionError): ServiceAuthenticator(row["auth_file"]).verify_wire(wire)
    with pytest.raises(PermissionError): await policy.check_delivery(actor["user_id"])
    with pytest.raises(PermissionError): await policy.sign_request(actor["user_id"], {"method": "chat.send"})
    current_scope.set(None)
    with pytest.raises(PermissionError): await policy.sign_request(actor["user_id"], {"method": "chat.send"})

@pytest.mark.asyncio
async def test_plugin_uses_original_http_contributions_and_leaves_session_options(config):
    accounts, service_ = service(config, Infrastructure())
    plugin = CloudWorkspacePlugin(config)
    await plugin.initialize()
    plugin.accounts, plugin.environments = accounts, service_
    plugin.authenticator = AccountAuthenticator(accounts)
    registry = ExtensionRegistry(None, {}, None); registry.register_application_plugin(plugin)
    app = FastAPI(); mount_application_plugin_http_routes(app, registry)
    methods = {"session.execution.options": object()}; original = methods["session.execution.options"]
    plugin.bind_web_channel(SimpleNamespace(register_method=lambda name, handler, **kw: methods.update({name: handler})), SimpleNamespace(require_agent_client=lambda: object()))
    try:
        assert methods["session.execution.options"] is original and set(methods) == {"session.execution.options", "cloud.environment.ensure", "cloud.environment.status"} | METHODS | GITCODE_METHODS | ENVIRONMENT_METHODS
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://127.0.0.1") as client:
            base = config.api_prefix; headers = {"Origin": "https://127.0.0.1"}
            body = {"username": "http-user", "password": "long-test-password"}
            assert (await client.post(base + "/register", json=body, headers={"Origin": "https://attacker.invalid"})).status_code == 401
            assert (await client.post(base + "/register", json=body, headers=headers)).status_code == 201
            response = await client.post(base + "/login", json=body, headers=headers)
            assert response.status_code == 200
            cookie = response.headers["set-cookie"].lower()
            assert all(value in cookie for value in ("secure", "httponly", "samesite=strict"))
            status = await client.get(base + "/status")
            first = status.json()
            assert status.headers["cache-control"] == "no-store"
            assert first["actor_id"] == first["subject_id"]
            assert len(first["session_revision"]) == 24
            assert "token" not in first
            assert (await client.get(base + "/status")).json()["session_revision"] == first["session_revision"]
            assert (await client.post(base + "/login", json=body, headers=headers)).status_code == 200
            second = (await client.get(base + "/status")).json()
            assert second["actor_id"] == first["actor_id"]
            assert second["session_revision"] != first["session_revision"]
            assert (await client.post(base + "/environment/ensure", json={"user_id": "forged"}, headers=headers)).status_code == 400
            assert (await client.get(base + "/environment")).status_code == 200
            assert (await client.post(base + "/logout", json={}, headers=headers)).status_code == 200
            assert (await client.get(base + "/status")).json()["authenticated"] is False
    finally:
        await plugin.shutdown()

@pytest.mark.asyncio
async def test_runtime_catalog_reply_is_project_scoped_and_public(config, monkeypatch):
    from unittest.mock import Mock

    plugin = CloudWorkspacePlugin(replace(config, opencode_provider={"display_name": "Review runtime"}))
    status = {"available": True, "reason": None, "state": "not_created"}
    available = Mock(return_value=status)
    account_runtime = Mock(return_value=status)
    device = {"runtime_id": "a" * 32, "display_name": "独立开发", **status, "state": "ready"}
    template = {"runtime_profile_id": "opencode-cloud", "cpu": 1000, "memory": 4096, "available": True}
    pool = SimpleNamespace(account_runtime=account_runtime, account_devices=Mock(return_value=[device]),
                           device_runtime=Mock(return_value=device),
                           runtime_template=Mock(return_value=template), register_device=Mock(return_value=device))
    account = {"account_id": "owner"}
    plugin.environments = SimpleNamespace(opencode_relay=SimpleNamespace(
        project_runtime=available, store=SimpleNamespace(get=Mock(return_value=account)), pool=pool,
    ))
    prewarm = AsyncMock(return_value=(True, {"ready": True}))
    monkeypatch.setattr("gateway.routing.e2a_proxy.fetch_agent_unary", prewarm)
    monkeypatch.setattr("gateway.services.project_environments.ProjectEnvironments", Mock())
    methods = {}
    responses = AsyncMock()
    channel = SimpleNamespace(
        register_method=lambda name, handler, **options: methods.update({name: (handler, options)}),
        send_response=responses, channel_id="web",
    )
    plugin.bind_web_channel(channel, SimpleNamespace(require_agent_client=lambda: object()))
    request, options = methods["project.runtime.status"]
    assert options == {"local_only": True}
    ws = object()
    check = AsyncMock(return_value={"user_id": "owner", "authority": "isolated-test"})
    get_account = Mock(return_value=None)
    monkeypatch.setattr("gateway.extensions.cloud_workspace.extension.current_account", get_account)
    await request(ws, "unauthorized", {"project_id": "repo"}, None)
    responses.assert_awaited_with(ws, "unauthorized", ok=False, code="PROJECT_RUNTIME_FORBIDDEN")
    get_account.return_value = SimpleNamespace(check=check)
    await request(ws, "unsupported-selector", {"project_id": "repo", "user_id": "another"}, None)
    responses.assert_awaited_with(ws, "unsupported-selector", ok=False, code="INVALID_REQUEST")
    available.assert_not_called()
    await request(ws, "valid", {"project_id": "repo"}, None)
    available.assert_called_once_with(check.return_value, "repo")
    assert check.await_count == 3
    responses.assert_awaited_with(ws, "valid", ok=True, payload={
        "provider_id": "opencode-direct", "runtime_profile_id": "opencode-cloud",
        "display_name": "Review runtime", **status,
    })

    list_request, options = methods["cloud.runtime.list"]
    assert options == {"local_only": True}
    await list_request(ws, "list", {}, None)
    account_runtime.assert_called_once_with(account)
    responses.assert_awaited_with(ws, "list", ok=True, payload={"runtimes": [{
        "provider_id": "opencode-direct", "runtime_profile_id": "opencode-cloud",
        "display_name": "Review runtime", **status,
    }, {
        "provider_id": "opencode-direct", "runtime_profile_id": "opencode-cloud", **device,
    }], "templates": [template]})

    create, options = methods["cloud.runtime.create"]
    assert options == {"local_only": True}
    fields = {"runtime_profile_id": "opencode-cloud", "display_name": "独立开发", "create_token": "b" * 32}
    await create(ws, "project-selector", {**fields, "project_id": "repo"}, None)
    responses.assert_awaited_with(ws, "project-selector", ok=False, code="INVALID_REQUEST")
    pool.register_device.assert_not_called()

    ensure, options = methods["project.runtime.ensure"]
    assert options == {"local_only": True}
    await ensure(ws, "unknown-provider", {"project_id": "repo", "provider_id": "other"}, None)
    responses.assert_awaited_with(ws, "unknown-provider", ok=False, code="INVALID_REQUEST")
    prewarm.assert_not_called()
    paused = {"available": False, "reason": "managed_admission_closed", "state": "not_created"}
    available.return_value = paused
    await ensure(ws, "paused", {"project_id": "repo", "provider_id": "opencode-direct"}, None)
    assert responses.await_args.kwargs["payload"]["available"] is False
    prewarm.assert_not_called()

    ready = {**status, "state": "ready"}
    available.side_effect = [status, ready]
    await ensure(ws, "ensure", {"project_id": "repo", "provider_id": "opencode-direct"}, None)
    assert prewarm.await_args.kwargs["req_method"].value == "project.runtime.prepare"
    assert prewarm.await_args.kwargs["params"] == {"project_id": "repo"}
    assert prewarm.await_args.kwargs["session_id"] is None
    assert prewarm.await_args.kwargs["user_id"] == "owner"
    assert responses.await_args.kwargs["payload"]["state"] == "ready"

    await create(ws, "create", fields, None)
    pool.register_device.assert_called_once_with(account, "独立开发", "b" * 32)
    assert prewarm.await_args.kwargs["params"] == {"runtime_id": device["runtime_id"]}
    assert prewarm.await_args.kwargs["session_id"] is None
    assert responses.await_args.kwargs["payload"] == {
        "provider_id": "opencode-direct", "runtime_profile_id": "opencode-cloud", **device, "start_failed": False,
    }


@pytest.mark.asyncio
async def test_web_model_rejection_records_authenticated_account_and_only_reason(config, caplog, monkeypatch):
    infra = Infrastructure()
    accounts, service_ = service(config, infra)
    plugin = CloudWorkspacePlugin(config)
    plugin.accounts, plugin.environments = accounts, service_
    plugin.authenticator = AccountAuthenticator(accounts)
    service_.opencode_relay = SimpleNamespace(handle=plugin.http, handle_shared=plugin.http, handle_device=plugin.http)
    registry = ExtensionRegistry(None, {}, None)
    registry.register_application_plugin(plugin)
    app = FastAPI()
    mount_application_plugin_http_routes(app, registry)
    path = config.api_prefix + "/observations/opencode-model-rejection"
    payload = {"reason": "opencode_shared_model_protocol_unsupported"}
    headers = {"Origin": config.public_origin}
    logger = logging.getLogger("gateway.extensions.cloud_workspace.extension")
    caplog.set_level("INFO", logger=logger.name)
    monkeypatch.setattr(logger, "handlers", [caplog.handler])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=config.public_origin) as client:
        assert (await client.post(path, json=payload, headers=headers)).status_code == 401
        credentials = {"username": "web-rejection", "password": "long-test-password"}
        assert (await client.post(config.api_prefix + "/register", json=credentials, headers=headers)).status_code == 201
        login = await client.post(config.api_prefix + "/login", json=credentials, headers=headers)
        assert login.status_code == 200
        assert (await client.post(path, json=payload, headers={"Origin": "https://invalid.example"})).status_code == 401
        assert (await client.post(path, json=payload | {"model": "private-model"}, headers=headers)).status_code == 400
        assert (await client.post(path, json={"reason": "arbitrary"}, headers=headers)).status_code == 400
        assert (await client.post(path, json=payload, headers=headers)).json() == {"recorded": True}
    events = [r.getMessage() for r in caplog.records if r.msg.startswith("opencode_web_model_rejected")]
    assert len(events) == 1
    assert events[0].endswith(f" account_id={login.json()['user_id']} reason={payload['reason']}")
    event_id = events[0].split()[1].removeprefix("event_id=")
    assert len(bytes.fromhex(event_id)) == 12
    assert not infra.allocations


@pytest.mark.asyncio
async def test_writer_and_symlink_boundaries(config, tmp_path):
    _, app = service(config, Infrastructure()); _, another = service(config, Infrastructure())
    app.store.acquire_writer()
    with pytest.raises(EnvironmentUnavailable): another.store.acquire_writer()
    app.store.close(); another.store.acquire_writer(); another.store.close()
    actor = await registered(app)
    row = app.store.get(actor)
    outside = tmp_path / "outside"; outside.mkdir(mode=0o700)
    Path(row["workspace"]).symlink_to(outside)
    with pytest.raises(PermissionError): app.store.prepare(actor["user_id"])

@pytest.mark.parametrize("changes", [{"account_backend_config": None}, {"image": "platform:latest"},
    {"extra_mounts": ({"source": "/tmp", "target": "/data"},)}, {"runtime_env": (("PYTHONPATH", "/tmp"),)}])
def test_config_fails_closed(config, changes):
    with pytest.raises(ValueError): replace(config, **changes).validate()

def test_service_auth_missing_forged_cross_instance_expired_and_replay(tmp_path, monkeypatch):
    path = tmp_path / 'auth.json'
    path.write_text(json.dumps({'mode': 'user_instance', 'instance_id': 'env-one', 'epoch': 1,
                                      'workspace': '/data/agent', 'login_owner': {'actor_id': 'u_one', 'authority': 'test'},
                                      'signing_key': 'ab' * 32}))
    path.chmod(0o600)
    signer = ServiceAuthenticator(path)
    monkeypatch.setenv('JIUWENSWARM_INSTANCE_AUTH_FILE', str(path))
    assert check_service_handshake(('/ws', {}))[0] == 401
    proof = signer.sign()
    assert check_service_handshake(('/ws', {SERVICE_AUTH_HEADER: proof})) is None
    assert check_service_handshake(('/ws', {SERVICE_AUTH_HEADER: proof}))[0] == 401
    invalid = json.loads(signer.sign())
    invalid['_instance_target']['instance_id'] = 'env-two'
    assert not signer.verify(json.dumps(invalid))
    invalid = json.loads(signer.sign())
    claims = invalid['_organization_assertion']['claims']
    claims['iat'] -= 500
    claims['exp'] -= 500
    invalid['_organization_assertion']['signature'] = hmac.new(bytes.fromhex('ab' * 32), canonical(claims), hashlib.sha256).hexdigest()
    assert not signer.verify(json.dumps(invalid))
    monkeypatch.delenv('JIUWENSWARM_INSTANCE_AUTH_FILE')
    assert check_service_handshake(('/ws', {})) is None


def test_signed_message_binds_owner_body_and_instance(tmp_path):
    path = tmp_path / 'wire-auth.json'
    path.write_text(json.dumps({'mode': 'user_instance', 'instance_id': 'env-wire', 'epoch': 3,
                               'workspace': '/data/agent', 'login_owner': {'actor_id': 'u_owner', 'authority': 'test'},
                               'signing_key': 'cd' * 32}))
    path.chmod(0o600)
    auth = ServiceAuthenticator(path)
    owner = {'user_id': 'u_owner', 'authority': 'test'}
    raw = {'request_id': 'req-one', 'req_method': 'session.execution.options', 'params': {}}
    signed = auth.sign_wire(raw, owner, 'login-token-only-in-memory')
    assert auth.verify_wire(signed)['actor_id'] == 'u_owner'
    with pytest.raises(PermissionError):
        auth.verify_wire(signed)
    tampered = auth.sign_wire(raw, owner, 'login-token-only-in-memory')
    tampered['params'] = {'user_id': 'another'}
    with pytest.raises(PermissionError):
        auth.verify_wire(tampered)
    with pytest.raises(PermissionError):
        auth.sign_wire(raw, {'user_id': 'someone-else', 'authority': 'test'}, 'token')




@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_handshake_denial_is_unavailable_without_recreating(config, status):
    from websockets.legacy.exceptions import InvalidStatusCode
    from websockets.datastructures import Headers
    infra = Infrastructure()
    _, app = service(config, infra)
    actor = await registered(app)
    await app.instances.connect("")
    try:
        original = app.instances._connect_ws_until_ready
        app.instances._connect_ws_until_ready = AsyncMock(side_effect=InvalidStatusCode(status, Headers()))
        for _ in range(2):
            with pytest.raises(EnvironmentUnavailable) as error:
                await app.ensure(actor)
            assert isinstance(error.value.__cause__, InvalidStatusCode)
            assert app.store.get(actor)["state"] == "ALLOCATED"
        assert infra.create_calls == 1
        app.instances._connect_ws_until_ready = original
        assert (await app.ensure(actor))["state"] == "READY"
        assert infra.create_calls == 1
    finally:
        await app.instances.disconnect()

@pytest.mark.parametrize("field,value", [
    ("resource_pool_id", "pool-b"),
    ("frontend_endpoint", "http://other-pool.test:8888"),
    ("namespace", "other-tenant"),
    ("function_version_urn", "urn:other:function:1"),
    ("resource_pool_id", None),
])
@pytest.mark.asyncio
async def test_pool_binding_rejects_retarget_before_infrastructure(config, field, value):
    bound = replace(config, resource_pool_id="pool-a")
    infra = Infrastructure()
    _, original = service(bound, infra)
    actor = await registered(original)
    before = original.store.get(actor)
    _, changed = service(replace(bound, **{field: value}), infra)
    with pytest.raises(EnvironmentUnavailable, match="pool binding"):
        await changed.ensure(actor)
    with pytest.raises(EnvironmentUnavailable, match="pool binding"):
        await changed.instances.connect("")
    assert changed.store._writer is None
    assert infra.create_calls == 0 and infra.delete_calls == []
    assert original.store.get(actor) == before


@pytest.mark.asyncio
async def test_same_pool_preserves_binding_across_default_image_change(config):
    bound = replace(config, resource_pool_id="pool-a")
    infra = Infrastructure()
    _, original = service(bound, infra)
    actor = await registered(original)
    before = original.store.get(actor)
    _, reopened = service(replace(bound, image="sha256:" + "b" * 64,
                                  frontend_endpoint=bound.frontend_endpoint + "/"), infra)
    await reopened.instances.connect("")
    try:
        row = await reopened.ensure(actor)
        assert row["profile"] == before["profile"]
        assert infra.create_calls == 1
    finally:
        await reopened.instances.disconnect()


@pytest.mark.asyncio
async def test_legacy_pool_binding_is_not_silently_assigned(config):
    infra = Infrastructure()
    _, old = service(config, infra)
    actor = await registered(old)
    before = old.store.get(actor)
    assert "placement" not in before["profile"]
    _, bound = service(replace(config, resource_pool_id="pool-a"), infra)
    with pytest.raises(EnvironmentUnavailable, match="pool binding"):
        await bound.ensure(actor)
    assert old.store.get(actor) == before
    assert infra.create_calls == 0


def test_registration_retry_cannot_move_intent_to_another_pool(config):
    _, original = service(replace(config, resource_pool_id="pool-a"), Infrastructure())
    intent = original.store.registration("pending-account", "long-test-password")
    _, changed = service(replace(config, resource_pool_id="pool-b"), Infrastructure())
    with pytest.raises(EnvironmentUnavailable, match="pool binding"):
        changed.store.registration("pending-account", "long-test-password")
    actor = {"authority": config.authority, "user_id": "test-pool-owner", "username": "pending-account"}
    with pytest.raises(EnvironmentUnavailable, match="pool binding"):
        changed.store.bind_registration(intent, actor)
    with original.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM environment_bindings").fetchone()[0] == 0
        saved = dict(db.execute("SELECT * FROM registration_intents").fetchone())
    assert saved == intent


def test_import_rejects_foreign_pool_before_reading_credentials(config):
    _, target = service(replace(config, resource_pool_id="pool-b"), Infrastructure())
    actor = {"authority": config.authority, "user_id": "test-pool-owner"}
    with pytest.raises(EnvironmentUnavailable, match="pool binding"):
        target.store.adopt_existing(actor, instance_id="other-instance",
            profile=replace(config, resource_pool_id="pool-a").runtime_profile(),
            workspace=config.workspace_root / "not-created", auth_file="/not-read")


@pytest.mark.parametrize("pool_id", ["", "../pool", "pool a", 123])
def test_pool_identifier_requires_explicit_operator_name(config, pool_id):
    with pytest.raises(ValueError, match="resource_pool_id"):
        replace(config, resource_pool_id=pool_id).validate()


@pytest.mark.parametrize("endpoint", ["file:///tmp/pool", "http://user:secret@pool.test", "http://pool.test?token=x"])
def test_bound_pool_endpoint_cannot_embed_credentials(config, endpoint):
    with pytest.raises(ValueError, match="explicit endpoint"):
        replace(config, resource_pool_id="pool-a", frontend_endpoint=endpoint).validate()


@pytest.mark.asyncio
async def test_physical_confirmation_failure_blocks_retry_across_gateway_restart(config):
    config = replace(config, resource_reconciler_socket="/run/confirmation/socket")
    infra = Infrastructure(); _, app = service(config, infra)
    actor = await registered(app)
    resources = SimpleNamespace(confirm_deleted=AsyncMock(side_effect=RuntimeError("physical pending")))
    app.instances._instance_lifecycle.resources = resources
    await app.instances.connect("")
    old = await app.ensure(actor)
    with pytest.raises(RuntimeError, match="physical pending"):
        await app.instances.delete_agent(actor["user_id"], "jiuwenswarm")
    assert infra.allocations == {} and app.store.get(actor)["state"] == "DELETING"
    await app.instances.disconnect()
    _, recovered = service(config, infra)
    recovered.instances._instance_lifecycle.resources = resources
    await recovered.instances.connect("")
    try:
        with pytest.raises(EnvironmentUnavailable, match="requires recovery"): await recovered.ensure(actor)
        assert infra.create_calls == 1 and recovered.store.get(actor)["epoch"] == old["epoch"]
        resources.confirm_deleted.side_effect = None
        new = await recovered.ensure(actor)
        assert new["epoch"] == old["epoch"] + 1 and infra.create_calls == 2
        assert new["workspace"] == old["workspace"]
        with pytest.raises(EnvironmentUnavailable, match="epoch"):
            await recovered.instances._instance_lifecycle.confirm_deleted(AgentInfo(user_id=actor["user_id"],
                agent_type="jiuwenswarm", sandbox_id=old["instance_id"], metadata={"instance_epoch": old["epoch"]}))
    finally:
        await recovered.instances.disconnect()


@pytest.mark.asyncio
async def test_required_physical_verification_cannot_be_silently_disabled(config):
    bound = replace(config, resource_reconciler_socket="/run/confirmation/socket")
    infra = Infrastructure(); _, app = service(bound, infra)
    actor = await registered(app)
    _, changed = service(config, infra)
    with pytest.raises(EnvironmentUnavailable, match="physical verification"):
        await changed.instances.connect("")
    await app.instances.connect("")
    try:
        await app.ensure(actor)
        with pytest.raises(EnvironmentUnavailable, match="backend"):
            await app.instances.delete_agent(actor["user_id"], "jiuwenswarm")
        assert app.store.get(actor)["state"] == "DELETING"
        assert infra.create_calls == 1
    finally:
        await app.instances.disconnect()


@pytest.mark.asyncio
async def test_managed_opencode_policy_reaches_existing_account_launch(config, tmp_path):
    from gateway.extensions.cloud_workspace.config import OPENCODE_RELAY_ENV

    model_config = tmp_path / "provider-models.json"
    model_config.write_text("{}")
    model_config.chmod(0o600)
    managed = replace(config, opencode_provider={"image": "sha256:" + "b" * 64, "model_config": str(model_config)})
    with pytest.raises(ValueError, match="physical resource confirmation"):
        managed.validate()
    managed = replace(managed, resource_reconciler_socket=str(tmp_path / "physical.sock"))
    managed.validate()
    for enabled in (False, True):
        replace(managed, opencode_provider={**managed.opencode_provider, "admit_new_bindings": enabled}).validate()
    for enabled in (None, "false", 0, 1, []):
        with pytest.raises(ValueError, match="admit_new_bindings"):
            replace(managed, opencode_provider={**managed.opencode_provider, "admit_new_bindings": enabled}).validate()
    with pytest.raises(ValueError, match="both a switch and an account_allowlist"):
        replace(managed, opencode_provider={**managed.opencode_provider,
                                           "admit_new_bindings": True, "account_allowlist": []}).validate()
    for allowlist in ([], ["u_pilot"]):
        replace(managed, opencode_provider={**managed.opencode_provider, "account_allowlist": allowlist}).validate()
    for allowlist in (None, "u_pilot", [7], [""], [" u_pilot "]):
        with pytest.raises(ValueError, match="account_allowlist"):
            replace(managed, opencode_provider={**managed.opencode_provider, "account_allowlist": allowlist}).validate()
    replace(managed, opencode_provider={"image": managed.opencode_provider["image"]}).validate()
    runtime_digest = "e" * 64
    shared = {**managed.opencode_provider, "shared_runtime": f"/opt/runtime-assets/{runtime_digest}"}
    replace(managed, opencode_provider=shared).validate()
    with pytest.raises(ValueError, match="outside account"):
        replace(managed, opencode_provider={**shared, "shared_runtime": str(config.workspace_root / runtime_digest)}).validate()
    query_auth = replace(managed, opencode_provider={**managed.opencode_provider, "auth_transport": "query"})
    replace(query_auth, frontend_endpoint="http://127.0.0.1:19888").validate()
    with pytest.raises(ValueError, match="loopback YuanRong Frontend"):
        replace(query_auth, frontend_endpoint="https://routed.example").validate()
    with pytest.raises(ValueError, match="overrides isolated paths"):
        replace(managed, runtime_env=((OPENCODE_RELAY_ENV, "https://incorrect.test"),)).validate()

    _, app = service(config, Infrastructure())
    actor = await registered(app)
    info = AgentInfo(user_id=actor["user_id"], agent_type="jiuwenswarm")
    assert OPENCODE_RELAY_ENV not in CloudInstancePolicy(app.store).plan(info).env_vars
    endpoint = managed.public_origin + managed.api_prefix + "/provider/opencode"
    plan = CloudInstancePolicy(app.store, opencode_relay_url=endpoint).plan(info)
    assert plan.env_vars[OPENCODE_RELAY_ENV] == endpoint
    scoped = CloudInstancePolicy(app.store, opencode_relay_url=endpoint, opencode_model_policy=lambda row: None)
    assert OPENCODE_RELAY_ENV not in scoped.plan(info).env_vars
    assert OPENCODE_RELAY_ENV not in app.store.get(actor)["profile"]["runtime_env"]


def test_managed_relay_paths_use_existing_signed_handlers(config):
    plugin = CloudWorkspacePlugin(config)
    relay = SimpleNamespace(handle=AsyncMock(), handle_shared=AsyncMock(), handle_device=AsyncMock())
    plugin.environments = SimpleNamespace(opencode_relay=relay)
    relay_routes = {route.path.removeprefix(config.api_prefix).split("/{project_id}")[0]: route.endpoint
                    for route in plugin.http_routes() if "/{project_id}" in route.path}
    assert relay_routes == {
        "/provider/opencode": relay.handle, "/provider/opencode-worker": relay.handle_shared,
        "/provider/managed/opencode": relay.handle, "/provider/managed/opencode-worker": relay.handle_shared,
        "/provider/opencode-device/{runtime_id}": relay.handle_device,
        "/provider/managed/opencode-device/{runtime_id}": relay.handle_device,
    }


def test_provider_relay_ca_applies_only_to_admitted_worker(config, tmp_path):
    from gateway.common.managed_codex import RELAY_ENV as CODEX_RELAY_ENV
    from gateway.common.security.provider_relay_tls import CA_ENV, CA_TARGET
    from gateway.extensions.cloud_workspace.config import OPENCODE_RELAY_ENV

    ca = tmp_path / "relay-ca.pem"
    deployment = replace(config, provider_relay_origin="https://relay.example.test:8443/",
                         provider_relay_ca_file=str(ca))
    deployment.validate()
    assert deployment.provider_relay_base == "https://relay.example.test:8443" + config.api_prefix
    assert config.provider_relay_base == config.public_origin + config.api_prefix
    assert deployment.runtime_profile() == config.runtime_profile()

    store = EnvironmentStore(config.state_root / "environments.db", config.authority,
                             config.workspace_root, config.state_root / "auth", config.runtime_profile())
    actor = {"authority": config.authority, "username": "relay-user", "user_id": "relay-user"}
    intent = store.registration(actor["username"], "long-test-password")
    store.bind_registration(intent, actor)
    info = AgentInfo(user_id=actor["user_id"], agent_type="jiuwenswarm")
    base = deployment.provider_relay_base
    policy = CloudInstancePolicy(store, opencode_relay_url=base + "/provider/opencode",
                                 codex_relay_url="wss://" + base.removeprefix("https://") + "/provider/managed/codex",
                                 codex_admits=lambda row: True,
                                 provider_relay_tls=True, provider_relay_ca_file=str(ca))
    plan = policy.plan(info)
    assert plan.env_vars[OPENCODE_RELAY_ENV] == base + "/provider/opencode"
    assert plan.env_vars[CODEX_RELAY_ENV] == "wss://" + base.removeprefix("https://") + "/provider/managed/codex"
    assert plan.env_vars[CA_ENV] == CA_TARGET
    assert [mount for mount in plan.mounts if mount["target"] == CA_TARGET] == [
        {"source": str(ca), "target": CA_TARGET, "readonly": True},
    ]
    policy.opencode_model_policy = lambda row: None
    policy.codex_admits = lambda row: False
    plan = policy.plan(info)
    assert {OPENCODE_RELAY_ENV, CODEX_RELAY_ENV, CA_ENV}.isdisjoint(plan.env_vars)
    assert all(mount["target"] != CA_TARGET for mount in plan.mounts)


def test_provider_relay_configuration_rejects_unsafe_values(config):
    from gateway.common.security.provider_relay_tls import CA_ENV, CA_TARGET

    for origin in ("http://relay.test", "https://user@relay.test", "https://relay.test/path",
                   "https://relay.test?", "https://relay.test#", "https://relay.test:0"):
        with pytest.raises(ValueError, match="provider_relay_origin"):
            replace(config, provider_relay_origin=origin).validate()
    for ca in ("relative.pem", "/certs/../ca.pem", str(config.workspace_root / "ca.pem"),
               str(config.state_root / "ca.pem")):
        with pytest.raises(ValueError, match="provider_relay_ca_file"):
            replace(config, provider_relay_ca_file=ca).validate()
    with pytest.raises(ValueError, match="overrides isolated paths"):
        replace(config, runtime_env=((CA_ENV, "/tmp/user.pem"),)).validate()
    with pytest.raises(ValueError, match="extra mount overlaps"):
        replace(config, extra_mounts=({"source": "/tmp/user-ca", "target": CA_TARGET},)).validate()


def test_provider_relay_context_verifies_peer_and_fails_on_invalid_bundle(monkeypatch, tmp_path):
    import ssl
    from gateway.common.security.provider_relay_tls import CA_ENV, relay_ssl_context

    monkeypatch.delenv(CA_ENV, raising=False)
    assert relay_ssl_context() is None
    monkeypatch.setenv(CA_ENV, "")
    context = relay_ssl_context()
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    ca = tmp_path / "invalid.pem"
    ca.write_text("invalid PEM")
    monkeypatch.setenv(CA_ENV, str(ca))
    with pytest.raises(ssl.SSLError):
        relay_ssl_context()


@pytest.mark.asyncio
async def test_codex_runtime_catalog_and_start_use_the_account_worker_without_a_project(config, monkeypatch):
    from unittest.mock import Mock

    from gateway.common.managed_codex import MODEL_UNAVAILABLE

    account = {"account_id": "owner"}
    identity = {"user_id": "owner", "authority": "isolated-test"}
    runtime_id = "a" * 32
    registered = {"runtime_id": runtime_id, "display_name": "Codex device", "state": "not_started",
                  "model_id": None, "available": True, "session_models": True}
    ready = {**registered, "state": "ready"}
    template = {"runtime_profile_id": "codex-cloud", "cpu": 1000, "memory": 1024, "available": True}
    pool = SimpleNamespace(
        account_devices=Mock(return_value=[ready]), device_runtime=Mock(return_value=ready),
        runtime_template=Mock(return_value=template), register_device=Mock(return_value=registered),
        device_model_id=Mock(return_value="account-model"),
        uses_session_models=Mock(return_value=True),
    )
    plugin = CloudWorkspacePlugin(config)
    plugin.environments = SimpleNamespace(codex_relay=SimpleNamespace(pool=pool, store=SimpleNamespace(get=Mock(return_value=account)),
        allowed_endpoints={"https://models.example.test/v1"}))
    monkeypatch.setattr("gateway.extensions.cloud_workspace.extension.current_account",
                        lambda: SimpleNamespace(check=AsyncMock(return_value=identity)))
    monkeypatch.setattr("gateway.services.project_environments.ProjectEnvironments", Mock())
    prewarm = AsyncMock(return_value=(True, {"ready": True}))
    monkeypatch.setattr("gateway.routing.e2a_proxy.fetch_agent_unary", prewarm)
    methods = {}
    channel = SimpleNamespace(register_method=lambda name, handler, **_: methods.update({name: handler}),
                              channel_id="web", send_response=AsyncMock())
    plugin.bind_web_channel(channel, SimpleNamespace(require_agent_client=lambda: object()))
    assert "project.runtime.status" not in methods
    ws = object()
    public = {"provider_id": "codex-direct", "runtime_profile_id": "codex-cloud", **ready}
    await methods["cloud.runtime.list"](ws, "list", {}, None)
    channel.send_response.assert_awaited_with(ws, "list", ok=True, payload={"runtimes": [public], "templates": [template]})

    await methods["cloud.runtime.create"](ws, "create", {
        "runtime_profile_id": "codex-cloud", "display_name": "Codex device", "create_token": "b" * 32,
    }, None)
    pool.register_device.assert_called_once_with(account, "Codex device", "b" * 32)
    assert prewarm.await_args.kwargs["params"] == {"provider_id": "codex-direct", "runtime_id": runtime_id}
    assert prewarm.await_args.kwargs["session_id"] is None and prewarm.await_args.kwargs["user_id"] == "owner"
    channel.send_response.assert_awaited_with(ws, "create", ok=True, payload={**public, "start_failed": False})

    legacy = {**ready, "model_id": "account-model", "session_models": False}
    pool.device_runtime.return_value = legacy
    prewarm.return_value = False, {"code": MODEL_UNAVAILABLE}
    await methods["cloud.runtime.start"](ws, "start", {"runtime_id": runtime_id}, None)
    assert prewarm.await_args.kwargs["params"] == {"provider_id": "codex-direct", "runtime_id": runtime_id,
                                                  "model_id": "account-model"}
    channel.send_response.assert_awaited_with(ws, "start", ok=True, payload={
        **public, **legacy, "start_failed": True, "start_error": MODEL_UNAVAILABLE,
    })
    await methods["cloud.runtime.start"](ws, "foreign", {"runtime_id": "c" * 32}, None)
    channel.send_response.assert_awaited_with(ws, "foreign", ok=False, code="PROJECT_RUNTIME_FORBIDDEN")
    assert prewarm.await_count == 2


    catalog = {"model_ids": ["account-model", "selected-model"], "default_model_id": "account-model"}
    prewarm.return_value = True, catalog
    await methods["cloud.runtime.models"](ws, "models", {}, None)
    assert prewarm.await_args.kwargs["params"] == {"provider_id": "codex-direct", "model_id": None,
                                                  "allowed_model_endpoints": ["https://models.example.test/v1"]}
    channel.send_response.assert_awaited_with(ws, "models", ok=True, payload=catalog)
    pool.register_device.reset_mock()
    fields = {"runtime_profile_id": "codex-cloud", "display_name": "Codex device", "create_token": "b" * 32}
    await methods["cloud.runtime.create"](ws, "unsupported", {**fields, "model_id": "unsupported"}, None)
    pool.register_device.assert_not_called()
    channel.send_response.assert_awaited_with(ws, "unsupported", ok=False, code="INVALID_REQUEST")

    pool.uses_session_models.return_value = False
    prewarm.side_effect = [(True, {"model_ids": ["selected-model"]}), (True, {"ready": True})]
    await methods["cloud.runtime.create"](ws, "legacy-create", {**fields, "model_id": "selected-model"}, None)
    pool.register_device.assert_called_once_with(account, "Codex device", "b" * 32, "selected-model")
    assert prewarm.await_args_list[-2].kwargs["params"]["model_id"] == "selected-model"
