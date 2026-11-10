"""In-process authorization context; never serialized into protocol messages."""
from contextvars import ContextVar
from dataclasses import dataclass, field

current_scope = ContextVar("gateway_request_authorization", default=None)

@dataclass
class ScopedMessage:
    message: object
    scope: object = field(repr=False)

def capture(message):
    scope = current_scope.get()
    return ScopedMessage(message, scope) if scope is not None else message

def restore(item):
    if isinstance(item, ScopedMessage):
        current_scope.set(item.scope)
        return item.message
    current_scope.set(None)
    return item
