"""Availability of the optional Native implementation (never import it to probe)."""
from importlib.metadata import PackageNotFoundError, distribution


def native_available() -> bool:
    try:
        distribution("openjiuwen")
    except PackageNotFoundError:
        return False
    return True


def model_provider_values() -> list[str]:
    if native_available():
        from openjiuwen.core.foundation.llm import ProviderType
        return [provider.value for provider in ProviderType]
    # Protocols consumed by the installed external main-agent adapters.
    return ["OpenAI", "Anthropic"]


def is_openai_account_provider(value: str) -> bool:
    if native_available():
        from openjiuwen.core.foundation.llm.utils.provider_utils import is_openai_account_provider as native_check
        return native_check(value)
    return str(value).strip().lower() == "openaiaccount"
