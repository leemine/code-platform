"""Availability of the optional Native implementation (never import it to probe)."""
from importlib.util import find_spec


def native_available() -> bool:
    return find_spec("openjiuwen") is not None


def model_provider_values() -> list[str]:
    if native_available():
        from openjiuwen.core.foundation.llm import ProviderType
        return [provider.value for provider in ProviderType]
    # External adapters currently support this shared catalog protocol only.
    return ["OpenAI"]


def is_openai_account_provider(value: str) -> bool:
    if native_available():
        from openjiuwen.core.foundation.llm.utils.provider_utils import is_openai_account_provider as native_check
        return native_check(value)
    return str(value).strip().lower() == "openaiaccount"
