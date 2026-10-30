# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Code prompt exports; importing shared prompt constants does not load Core."""

__all__ = ["build_code_system_prompt"]


def __getattr__(name):
    if name != "build_code_system_prompt":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from .code_prompt_builder import build_code_system_prompt
    globals()[name] = build_code_system_prompt
    return build_code_system_prompt
