# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Keep Native Rail classes lazy when importing the shared heartbeat domain."""
from importlib import import_module

_EXPORTS = {
    "CodeTaskPlanningRail": ".code_task_planning_rail",
    "PlanApprovalInterruptRail": ".code_plan_approval_interrupt_rail",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value
