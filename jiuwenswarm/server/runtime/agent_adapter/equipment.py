"""Resolve Swarm assets and commit their snapshot at the original Facade seam.

Native retains its original reconcile implementation. Native Provider formats
and installation/readback are deliberately outside this module.
"""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path


def names(value, field_name):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"Invalid equipment field: {field_name}")
    return list(dict.fromkeys(x.strip() for x in value))


@dataclass(frozen=True)
class EquipmentPolicy:
    directory: str
    include_global_skills: bool = False


@dataclass(frozen=True)
class EquipmentAssets:
    packages: tuple[tuple[Path, bool], ...]
    skills: tuple[tuple[Path, dict], ...]
    selected_skills: tuple[str, ...]
    disabled_skills: frozenset[str]
    connectors: dict = field(repr=False)
    snapshot: dict


async def resolve_assets(params, *, include_global_skills):
    from jiuwenswarm.server.runtime import extension_package_manager as packages
    from jiuwenswarm.common.config import get_mcp_server_config
    from jiuwenswarm.server.runtime.mcp.credential import CredentialStore, resolve_placeholders

    template = params.get("agent_template_name", "")
    if not isinstance(template, str):
        raise ValueError("Invalid equipment field: agent_template_name")
    plugins = names(params.get("plugin_names"), "plugin_names")
    explicit_mcps = names(params.get("mcp"), "mcp")
    paths = []
    if template:
        if not packages.is_agent_template_installed(template):
            raise ValueError(f"agent_template not installed: {template}")
        paths.append((packages.resolve_agent_template_dir(template), True))
    for name in plugins:
        if not packages.is_plugin_allowed(name):
            raise ValueError(f"plugin not installed: {name}")
        paths.append((packages.resolve_plugin_dir(name), False))
    needed = list(dict.fromkeys(explicit_mcps + packages.collect_connectors_for_packages(
        agent_template_id=template or None, plugin_ids=plugins)))
    pending = packages.unready_connectors(needed)
    if pending:
        raise ValueError("equipment connector not connected: " + ", ".join(pending))
    connectors = {}
    for name in needed:
        entry = get_mcp_server_config(name)
        if not entry:
            raise ValueError(f"MCP has no portable connection configuration: {name}")
        entry = resolve_placeholders(deepcopy(entry), CredentialStore(), name)
        if "${" in json.dumps(entry):
            raise ValueError(f"MCP credentials are unresolved: {name}")
        connectors[name] = entry
    selected = names(params.get("skills"), "skills")
    skills, disabled = [], frozenset()
    if include_global_skills or selected:
        from jiuwenswarm.server.runtime.skill.skill_manager import SkillManager
        manager = SkillManager()
        disabled = frozenset(manager.list_disabled_skills())
        catalog = await manager.handle_skills_list({})
        for item in catalog.get("skills", []):
            if not item.get("installed") or item.get("enabled") is False or item.get("skill_type") == "swarm_skill":
                continue
            detail = await manager.handle_skills_get({"name": item["name"]})
            file = detail.get("file_path")
            if not file:
                if item["name"] in selected:
                    raise ValueError("Container Skill packs require an explicit portable Skill")
                continue
            skills.append((Path(file).parent, deepcopy(detail)))
    return EquipmentAssets(tuple(paths), tuple(skills), tuple(selected), disabled, connectors,
                           {"agent_template_name": template, "plugin_names": plugins, "mcp": explicit_mcps})


async def reconcile_equipment(adapter, session_id, request, *, execution=None):
    """Mount through the Provider, then commit only a still-authorized snapshot."""
    from jiuwenswarm.runtime.context import get_current_runtime
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_equipment, save_session_equipment

    if request.params.get("answers"):
        return  # Control replies stay on the existing control channel.
    sid = session_id or "default"
    runtime = get_current_runtime()
    before = runtime.get_session_snapshot(sid) if runtime else None
    previous = deepcopy(get_session_equipment(sid))
    task = asyncio.current_task()

    def ensure_current():
        if task is not None and task.cancelling():
            raise asyncio.CancelledError
        if runtime is not None:
            current = runtime.get_session_snapshot(sid)
            if (before is None or current is None or current.generation != before.generation
                    or current.state in {"quiescing", "closed"}):
                raise RuntimeError("Equipment execution no longer owns the current session generation")
        if get_session_equipment(sid) != previous:
            raise RuntimeError("Equipment snapshot changed while configuring the Provider")

    policy = adapter.equipment_input_policy(sid, request, execution=execution)
    assets = await resolve_assets(request.params, include_global_skills=policy.include_global_skills)
    ensure_current()
    await adapter.apply_equipment(sid, request, assets, directory=policy.directory,
                                  execution=execution, ensure_current=ensure_current)
    ensure_current()
    # No await between the final ownership check and the existing metadata commit.
    save_session_equipment(sid, **assets.snapshot)
