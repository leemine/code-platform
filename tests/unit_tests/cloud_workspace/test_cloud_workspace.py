import asyncio
import hashlib
import hmac
import json
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
    plugin.bind_web_channel(SimpleNamespace(register_method=lambda name, handler, **kw: methods.update({name: handler})), None)
    assert methods["session.execution.options"] is original and len(methods) == 3
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://127.0.0.1") as client:
        base = config.api_prefix; headers = {"Origin": "https://127.0.0.1"}
        body = {"username": "http-user", "password": "long-test-password"}
        assert (await client.post(base + "/register", json=body, headers={"Origin": "https://attacker.invalid"})).status_code == 401
        assert (await client.post(base + "/register", json=body, headers=headers)).status_code == 201
        response = await client.post(base + "/login", json=body, headers=headers)
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert all(value in cookie for value in ("secure", "httponly", "samesite=strict"))
        assert (await client.post(base + "/environment/ensure", json={"user_id": "forged"}, headers=headers)).status_code == 400
        assert (await client.get(base + "/environment")).status_code == 200
        assert (await client.post(base + "/logout", json={}, headers=headers)).status_code == 200
        assert (await client.get(base + "/status")).json()["authenticated"] is False

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
