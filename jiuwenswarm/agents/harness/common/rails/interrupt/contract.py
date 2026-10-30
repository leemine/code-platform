"""Shared interaction envelope predicates, independent of Native rails."""
from typing import Any

SKILL_EVOLUTION_APPROVAL_SCHEMA = "openjiuwen.skill_evolution_approval.v1"
EVOLUTION_INTERRUPT_SOURCE = "evolution_interrupt"
LEGACY_SKILL_EVOLUTION_APPROVAL_SOURCE = "skill_evolution_approval"
INTERRUPT_RESUME_SOURCES = frozenset(
    {
        "permission_interrupt",
        "confirm_interrupt",
        "ask_user_interrupt",
        EVOLUTION_INTERRUPT_SOURCE,
    }
)
EVOLUTION_INTERRUPT_METADATA_SOURCES = frozenset(
    {
        EVOLUTION_INTERRUPT_SOURCE,
        LEGACY_SKILL_EVOLUTION_APPROVAL_SOURCE,
    }
)
SKILL_EVOLUTION_APPROVAL_TOOL_KINDS = {
    "evolve_skill_experiences": "evolve",
    "simplify_skill_experiences": "simplify",
}

def has_interrupt_resume_payload(params: Any) -> bool:
    if not isinstance(params, dict):
        return False
    if not str(params.get("request_id") or "").strip():
        return False
    answers = params.get("answers")
    return isinstance(answers, list) and bool(answers)


def is_interrupt_resume_payload(params: Any) -> bool:
    if not has_interrupt_resume_payload(params):
        return False
    source = str(params.get("source") or "").strip()
    if source in INTERRUPT_RESUME_SOURCES:
        return True
    if source != LEGACY_SKILL_EVOLUTION_APPROVAL_SOURCE:
        return False
    evolution_meta = params.get("evolution_meta")
    return (
        isinstance(evolution_meta, dict)
        and evolution_meta.get("approval_transport") == "interrupt"
    )



class RootPermissionQueueError(ValueError):
    """Fail-closed root permission queue error."""


