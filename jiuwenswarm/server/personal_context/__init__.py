"""Optional Native personal context integration."""
__all__ = ["PersonalContextHostAPI"]


def __getattr__(name):
    if name != "PersonalContextHostAPI":
        raise AttributeError(name)
    from .host_api import PersonalContextHostAPI
    return PersonalContextHostAPI
