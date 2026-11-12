from types import SimpleNamespace

import pytest

from gateway.auth.accounts import AccountStore
from gateway.auth.account_authenticator import AccountAuthenticator
from gateway.auth.request_scope import current_scope
from gateway.extensions.auth.credential_authenticator import AuthContext
from gateway.extensions.data_sync.extension import DataSyncPlugin, register_extensions
from gateway.services.data_sync.store import DirectoryStore
from jiuwenswarm.data_sync.contract import CAPABILITIES


def test_source_credential_uses_original_log_redaction():
    from gateway.common.log_sanitize import mask_sensitive
    secret = "abcdef12" * 8
    for text in [str({"source_token": secret}), '{"source_token":"' + secret + '"}']:
        assert secret not in mask_sensitive(text)


@pytest.mark.asyncio
async def test_registered_handlers_reuse_account_guards_and_recheck_delivery(tmp_path, monkeypatch):
    accounts = AccountStore(tmp_path / "authority/accounts.db", "test-authority")
    accounts.register("sync-user", "isolated-test-password")
    login = accounts.login("sync-user", "isolated-test-password")
    auth = AccountAuthenticator(accounts)
    methods, responses, options = {}, [], {}
    sentinel = object()
    methods["chat.send"] = sentinel
    def register(name, handler, **kwargs):
        methods[name], options[name] = handler, kwargs
    async def respond(ws, req_id, **kwargs):
        responses.append(kwargs)
    plugin = DataSyncPlugin(DirectoryStore(tmp_path / "sync"), lambda identity: "env-original-logical-id")
    plugin.bind_web_channel(SimpleNamespace(register_method=register, send_response=respond), None)
    assert methods["chat.send"] is sentinel and all(value == {"local_only": True} for value in options.values())
    scope_token = current_scope.set(None)
    try:
        async def call(action, params):
            await methods["data_sync." + action](None, "request", params, "transport-correlation")
            return responses[-1]
        assert (await call("negotiate", {"version": 1, "capabilities": sorted(CAPABILITIES)}))["code"] == "UNAUTHORIZED"
        result = await auth.authenticate(AuthContext(channel_type="web", headers={"Authorization": "Bearer " + login["token"]}))
        assert result.success
        await result.extensions["request_guard"]()
        params = {"kind": "local", "installation_id": "installation-one", "source_token": "a" * 64,
                  "version": 1, "capabilities": sorted(CAPABILITIES)}
        for forbidden in ["user_id", "authority", "session_id", "root", "instance_id"]:
            assert (await call("source.register", {**params, forbidden: "forged"}))["code"] == "INVALID_REQUEST"
        first = await call("source.register", params)
        assert first["ok"] and first["payload"]["kind"] == "local"
        assert (await call("source.register", params))["payload"] == first["payload"]
        cloud = {key: value for key, value in params.items() if key != "installation_id"}
        cloud["kind"] = "cloud"
        assert (await call("source.register", cloud))["code"] == "SOURCE_HOST_ONLY"
        original = plugin.dispatch
        def revoke_before_delivery(*args):
            value = original(*args)
            accounts.logout(login["token"])
            return value
        monkeypatch.setattr(plugin, "dispatch", revoke_before_delivery)
        assert (await call("negotiate", {"version": 1, "capabilities": sorted(CAPABILITIES)}))["code"] == "UNAUTHORIZED"
    finally:
        current_scope.reset(scope_token)


@pytest.mark.asyncio
async def test_disabled_plugin_has_no_side_effects_and_cloud_does_not_ensure(tmp_path, monkeypatch):
    registered = []
    def never_ensure(*args):
        raise AssertionError("sync must not create execution instances")
    original_store = SimpleNamespace(get=lambda identity: {"environment_id": "logical-env"})
    cloud = SimpleNamespace(environments=SimpleNamespace(store=original_store, ensure=never_ensure))
    registry = SimpleNamespace(register_application_plugin=registered.append, get_application_plugin=lambda name: cloud)
    monkeypatch.delenv("CODE_PLATFORM_DATA_SYNC_ROOT", raising=False)
    assert await register_extensions(registry) == [] and registered == []
    monkeypatch.setenv("CODE_PLATFORM_DATA_SYNC_ROOT", str(tmp_path / "data-sync"))
    monkeypatch.setenv("CODE_PLATFORM_CLOUD_CONFIG", "/operator/cloud.json")
    plugins = await register_extensions(registry)
    assert plugins == registered and plugins[0].environment_store() is original_store
