"""Optional cloud composition using the host's registered instance Router."""
from gateway.auth.account_authenticator import AccountAuthenticator
from gateway.auth.remote_accounts import RemoteAccounts
from gateway.services.cloud_environments import EnvironmentStore, EnvironmentService
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
    client.configure_instance_lifecycle(CloudInstancePolicy(store, ready_timeout=config.ready_timeout, resources=resources), authenticator)
    return accounts, authenticator, EnvironmentService(store, accounts, client)
