"""Read Swarm equipment through existing asset services; translate portable parts.

No Native adapter, Core package loader, authorization bypass or second catalog.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Equipment:
    system: str = ""
    skills: dict[str, Path] = field(default_factory=dict)
    skill_documents: dict[str, str] = field(default_factory=dict)
    mcps: dict = field(default_factory=dict)
    snapshot: dict = field(default_factory=dict)


from ..equipment import names


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.exists():
        raise ValueError("Equipment resource is missing or outside its package")
    return path


def add_skill(result: Equipment, directory: Path, metadata=None):
    directory = directory.resolve()
    file = contained(directory, "SKILL.md")
    text = file.read_text(encoding="utf-8")
    frontmatter = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if metadata is not None:
        # Swarm supports legacy/plain Skill headers. Use its public asset
        # metadata as discovery identity, preserving the original body/resources.
        meta = {"name": metadata.get("name"), "description": metadata.get("description")}
        text = "---\n" + yaml.safe_dump(meta, allow_unicode=True) + "---\n" + (frontmatter.group(2) if frontmatter else text)
    elif frontmatter is None:
        raise ValueError("OpenCode requires Skill frontmatter")
    else:
        try:
            meta = yaml.safe_load(frontmatter.group(1))
        except yaml.YAMLError as exc:
            raise ValueError("Equipment Skill has invalid frontmatter") from exc
    name = meta.get("name") if isinstance(meta, dict) else None
    if not isinstance(name, str) or not name.strip() or not meta.get("description"):
        raise ValueError("OpenCode Skill requires name and description")
    if name in result.skills and result.skills[name] != directory:
        raise ValueError(f"Conflicting equipment Skill: {name}")
    # Do not copy links outside the package, caches or implicit executable hooks.
    for item in directory.rglob("*"):
        if item.is_symlink():
            raise ValueError("Equipment Skill symlinks are not supported")
    result.skills[name] = directory
    result.skill_documents[name] = text


def read_package(result: Equipment, directory: Path, *, template: bool):
    manifest = json.loads(contained(directory, "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Invalid equipment manifest")
    portable = {"package_type", "name", "version", "display_name", "description", "display_description",
                "author", "license", "metadata", "tags", "icon", "avatar", "persona", "skills", "mcps", "runtime"}
    unsupported = [k for k, v in manifest.items() if k not in portable and v]
    if unsupported:
        raise ValueError("OpenCode unsupported equipment fields: " + ", ".join(sorted(unsupported)))
    runtime = manifest.get("runtime")
    if runtime and runtime != "native":
        if not isinstance(runtime, dict) or runtime.get("provider_name") != "opencode":
            raise ValueError("equipment_provider_conflict: template requires another Provider")
        if runtime.get("config") or set(runtime) - {"provider_name", "config"}:
            raise ValueError("OpenCode template runtime configuration is not portable")
    elif runtime == "native":
        raise ValueError("equipment_provider_conflict: template requires Native")
    persona = manifest.get("persona")
    if persona:
        if not template or not isinstance(persona, dict) or set(persona) != {"dir"}:
            raise ValueError("Unsupported equipment persona")
        folder = contained(directory, persona["dir"])
        files = sorted(folder.rglob("*.md"))
        if not files:
            raise ValueError("Equipment persona has no markdown")
        result.system = "\n\n".join(contained(directory, str(f.relative_to(directory))).read_text(encoding="utf-8") for f in files)
    for item in manifest.get("skills", []):
        if not isinstance(item, dict) or set(item) - {"dir", "mode", "enabled_skills"} or "dir" not in item:
            raise ValueError("Unsupported equipment Skill declaration")
        if item.get("mode", "all") not in {"all", "auto_list"}:
            raise ValueError("Unsupported equipment Skill mode")
        folder = contained(directory, item["dir"])
        allowed = item.get("enabled_skills")
        if allowed is not None:
            allowed = names(allowed, "enabled_skills")
        files = [folder / "SKILL.md"] if (folder / "SKILL.md").is_file() else sorted(folder.rglob("SKILL.md"))
        if not files:
            raise ValueError("Equipment Skill declaration contains no SKILL.md")
        for file in files:
            discovered = Equipment()
            add_skill(discovered, file.parent)
            # Existing package semantics: an empty list is unfiltered, and
            # selections refer to the declared Skill name, not its folder.
            if not allowed or next(iter(discovered.skills)) in allowed:
                add_skill(result, file.parent)
    for item in manifest.get("mcps", []):
        if not isinstance(item, dict) or set(item) != {"connector"} or not isinstance(item["connector"], str):
            raise ValueError("Only existing Swarm MCP connector references are supported")


def mcp_config(name, entry, directory):
    transport = entry.get("transport")
    if transport == "stdio":
        if entry.get("cwd") and Path(entry["cwd"]).resolve() != Path(directory).resolve():
            raise ValueError("OpenCode MCP cannot override the project working directory")
        command = entry.get("command")
        args = entry.get("args", [])
        if not isinstance(command, str) or not command or not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ValueError(f"Invalid MCP command: {name}")
        config = {"type": "local", "command": [command, *args], "environment": entry.get("env", {}), "enabled": True}
    elif transport in {"http", "sse", "streamable-http", "streamable_http"}:
        if not isinstance(entry.get("url"), str) or not entry["url"].startswith(("http://", "https://")):
            raise ValueError(f"Invalid MCP URL: {name}")
        config = {"type": "remote", "url": entry["url"], "headers": entry.get("headers", {}), "oauth": False, "enabled": True}
    else:
        raise ValueError(f"Unsupported MCP transport: {name}")
    if entry.get("timeout_s"):
        config["timeout"] = int(float(entry["timeout_s"]) * 1000)
    return config


def convert_equipment(assets, *, directory):
    """Convert prepared assets; do not read Swarm configuration or credentials."""
    result = Equipment(snapshot=dict(assets.snapshot))
    for path, template in assets.packages:
        read_package(result, path, template=template)
    if set(result.skills) & assets.disabled_skills:
        raise ValueError("Equipment package references a disabled Skill")
    for path, detail in assets.skills:
        add_skill(result, path, detail)
    if set(assets.selected_skills) - set(result.skills):
        raise ValueError("Requested equipment Skill is unavailable or disabled")
    for name, entry in assets.connectors.items():
        result.mcps[name] = mcp_config(name, entry, directory)
    return result


async def resolve_equipment(params, *, directory, include_global_skills):
    """Compatibility entry; production Facade prepares assets before conversion."""
    from ..equipment import resolve_assets
    assets = await resolve_assets(params, include_global_skills=include_global_skills)
    return convert_equipment(assets, directory=directory)
