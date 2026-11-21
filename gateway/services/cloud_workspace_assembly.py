"""Optional cloud composition using the host's registered instance Router."""
from gateway.auth.account_authenticator import AccountAuthenticator
from gateway.auth.remote_accounts import RemoteAccounts
from gateway.services.cloud_environments import EnvironmentStore, EnvironmentService
from gateway.extensions.cloud_workspace.config import OPENCODE_RELAY_PATH
from gateway.services.cloud_instance_policy import CloudInstancePolicy

def assemble(config, client):
    from gateway.extensions.agentos.agentos_router.router_client import AgentOSRouterClient
    if not isinstance(client, AgentOSRouterClient):
        raise RuntimeError("cloud workspace requires the original AgentOS Router")
    config.validate()
    if (config.frontend_endpoint.rstrip("/") != client._yuanrong.frontend_endpoint.rstrip("/")
            or config.namespace != client._yuanrong.agent_namespace
            or config.function_version_urn != client._yuanrong.function_version_urn):
        raise ValueError("cloud deployment must use the host's configured instance client")
    accounts = RemoteAccounts(config.account_backend_config, config.authority)
    store = EnvironmentStore(config.state_root / "environments.db", config.authority,
                             config.workspace_root, config.state_root / "instance-auth", config.runtime_profile())
    authenticator = AccountAuthenticator(accounts, config.public_origin)
    from gateway.services.resource_reconciler import ResourceReconciler
    resources = ResourceReconciler(config.resource_reconciler_socket) if config.resource_reconciler_socket else None
    relay_url = None
    relay = None
    model_policy = None
    if config.opencode_provider:
        from gateway.services.cloud_opencode_pool import CloudOpencodePool
        from gateway.services.cloud_opencode_relay import CloudOpencodeRelay
        pool = CloudOpencodePool(store, client._yuanrong, config, resources=resources)
        model_policy = pool.model_policy
        relay = CloudOpencodeRelay(store, pool, auth_transport=config.opencode_provider.get("auth_transport", "basic"))
        relay_url = config.public_origin.rstrip("/") + config.api_prefix + OPENCODE_RELAY_PATH
    policy = CloudInstancePolicy(
        store, ready_timeout=config.ready_timeout, resources=resources, opencode_relay_url=relay_url, opencode_model_policy=model_policy,
    )
    client.configure_instance_lifecycle(policy, authenticator)
    return accounts, authenticator, EnvironmentService(store, accounts, client, opencode_relay=relay)
