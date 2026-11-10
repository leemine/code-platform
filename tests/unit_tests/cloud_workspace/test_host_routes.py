import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.extensions.application_host import mount_application_plugin_http_routes
from gateway.extensions.cloud_workspace.config import CONFIG_ENV
from gateway.extensions.loader import ExtensionLoader
from gateway.extensions.registry import ExtensionRegistry
from gateway.extensions.sdk.application_plugin import ApplicationPluginExtension, HTTPRouteContribution
from gateway.extensions.types import ExtensionMetadata


class Plugin(ApplicationPluginExtension):
    plugin_id = 'host-test'

    def __init__(self, path='/host-test'):
        self.path, self.enabled = path, True

    @property
    def metadata(self):
        return ExtensionMetadata(id=self.plugin_id, name='Test', version='1', description='', author='test',
                                 min_jiuwenswarm_version='', dependencies={}, config_schema=None)

    def is_enabled(self):
        return self.enabled

    async def initialize(self, config):
        pass

    async def shutdown(self):
        pass

    def http_routes(self):
        async def endpoint(request):
            return {'path': request.url.path}
        return (HTTPRouteContribution(self.path, endpoint),)


def test_host_mounts_plugin_and_enforces_enable_state():
    registry = ExtensionRegistry(None, {}, None)
    plugin = Plugin()
    registry.register_application_plugin(plugin)
    app = FastAPI()
    mount_application_plugin_http_routes(app, registry)
    with TestClient(app) as client:
        assert client.get('/host-test').json() == {'path': '/host-test'}
        plugin.enabled = False
        assert client.get('/host-test').status_code == 503


def test_host_refuses_existing_route_or_reserved_path():
    for path in ['/taken', '/api/application-plugins/private']:
        registry = ExtensionRegistry(None, {}, None)
        registry.register_application_plugin(Plugin(path))
        app = FastAPI()
        app.add_api_route('/taken', lambda: {})
        with pytest.raises(ValueError):
            mount_application_plugin_http_routes(app, registry)


@pytest.mark.asyncio
async def test_normal_extension_loader_loads_configured_plugin(tmp_path, monkeypatch):
    # initialize/connect only; no account/provisioning request or external I/O.
    import gateway.extensions.cloud_workspace as package
    from pathlib import Path
    cfg = {'authority': 'loader-test', 'public_origin': 'https://127.0.0.1',
           'state_root': str(tmp_path / 'control'), 'workspace_root': str(tmp_path / 'users'),
           'image': 'sha256:' + 'a' * 64, 'frontend_endpoint': 'http://127.0.0.1:1',
           'function_version_urn': 'test', 'registration_enabled': False, 'account_backend_config': str(tmp_path / 'account.json')}
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(cfg))
    monkeypatch.setenv(CONFIG_ENV, str(config))
    registry = ExtensionRegistry(None, {}, None)
    loader = ExtensionLoader(registry)
    loaded = await loader.load_extension(Path(package.__file__).parent)
    assert registry.get_application_plugin('cloud_workspace') is loaded[0]
    assert loaded[0].websocket_routes() == ()
    class Channel:
        def __init__(self):
            self.methods = {}
        def register_method(self, name, handler, **kwargs):
            self.methods[name] = handler
    channel = Channel()
    loaded[0].bind_web_channel(channel, None)
    assert set(channel.methods) == {'cloud.environment.ensure', 'cloud.environment.status'}
    assert loaded[0].accounts is None
    from gateway.extensions.cloud_workspace.config import CloudConfig
    loaded[0].config = CloudConfig.load()
    assert loaded[0].http_routes()[0].path == '/api/v1/auth/organization/register'
    await loaded[0].shutdown()
