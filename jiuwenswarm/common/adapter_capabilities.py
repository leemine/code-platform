"""Lightweight capability declaration shared by provider discovery and execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterCapabilities:
    """Implemented integration capabilities, not the native SDK's full feature set."""
    equipment: frozenset[str] = frozenset()
    main_instructions: bool = False
    user_questions: bool = False
    native_resume: bool = False
    context_usage: bool = False
    manual_compaction: bool = False
