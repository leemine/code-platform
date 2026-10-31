"""Lightweight entry points; configuration reads never load execution modules."""
from jiuwenswarm.common.codex_adapter_config import availability, config_snapshot


def create_codex(*, mode):
    from jiuwenswarm.server.runtime.agent_adapter.providers.codex import CodexAdapter
    return CodexAdapter(mode=mode)


def create_opencode(*, mode):
    from jiuwenswarm.server.runtime.agent_adapter.providers.opencode import OpenCodeAdapter
    return OpenCodeAdapter(mode=mode)


def opencode_config_snapshot(config):
    return {"opencode": config.get("opencode", {})}


create_codex.display_name = "Codex"
create_codex.supported_modes = ("agent", "code")
create_codex.permission_profiles = ("default", "full_access")
create_codex.config_snapshot = config_snapshot
create_codex.availability = availability
create_opencode.display_name = "OpenCode"
create_opencode.supported_modes = ("agent", "code")
create_opencode.permission_profiles = ("default", "full_access")
create_opencode.config_snapshot = opencode_config_snapshot
