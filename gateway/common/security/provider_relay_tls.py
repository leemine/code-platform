"""TLS trust configured by the deployment for account Worker relay clients."""
import os
import ssl


CA_ENV = "CODE_PLATFORM_PROVIDER_RELAY_CA_FILE"
CA_TARGET = "/run/jiuwenswarm-provider-relay/ca.pem"


def relay_ssl_context() -> ssl.SSLContext | None:
    """Return the shared TLS policy, or leave a legacy client's defaults in place."""
    ca_file = os.environ.get(CA_ENV)
    if ca_file is None:
        return None
    context = ssl.create_default_context()
    if ca_file:
        context.load_verify_locations(cafile=ca_file)
    return context
