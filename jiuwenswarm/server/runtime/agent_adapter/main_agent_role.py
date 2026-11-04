"""Resolve a session-bound role without importing any Provider or its SDK."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


_ROLE_FIELDS = frozenset({
    "package_type", "name", "version", "display_name", "description", "display_description",
    "author", "license", "metadata", "tags", "icon", "avatar", "persona", "runtime",
})
_MAX_ROLE_BYTES = 8 * 1024


@dataclass(frozen=True)
class MainAgentRole:
    template_ref: str
    instructions: str = field(repr=False)

    def binding(self) -> dict[str, str]:
        return {
            "template_ref": self.template_ref,
            "revision": hashlib.sha256(self.instructions.encode("utf-8")).hexdigest(),
        }


def resolve_main_agent_role(template_ref: object, provider: str) -> MainAgentRole:
    """Read only the approved, installed package's portable persona."""
    from jiuwenswarm.server.runtime import extension_package_manager as packages

    if (not isinstance(template_ref, str) or not template_ref or len(template_ref) > 128
            or template_ref != template_ref.strip() or "/" in template_ref or "\\" in template_ref
            or template_ref in {".", ".."} or any(ord(ch) < 32 for ch in template_ref)):
        raise ValueError("Invalid role_template_ref")
    if not packages.is_agent_template_installed(template_ref):
        raise ValueError("Main Agent role template is not installed")

    try:
        root = packages.resolve_agent_template_dir(template_ref).resolve()
        manifest_path = root / "manifest.json"
        if manifest_path.is_symlink():
            raise ValueError("Role manifest cannot be a symlink")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Invalid role template manifest")
        if any(value for key, value in manifest.items() if key not in _ROLE_FIELDS):
            raise ValueError("Main Agent role requires a persona-only template")
        runtime = manifest.get("runtime")
        if runtime and (
            not isinstance(runtime, dict)
            or runtime.get("provider_name") not in (provider, provider.removesuffix("-direct"))
            or set(runtime) - {"provider_name", "config"} or runtime.get("config")
        ):
            raise ValueError("Main Agent role template requires another Provider or private runtime configuration")

        persona = manifest.get("persona")
        if not isinstance(persona, dict) or set(persona) != {"dir"} or not isinstance(persona["dir"], str):
            raise ValueError("Main Agent role template requires a persona directory")
        relative = Path(persona["dir"])
        folder = root / relative
        if (relative.is_absolute() or folder.is_symlink()
                or folder.resolve() == root or not folder.resolve().is_relative_to(root)
                or not folder.is_dir()):
            raise ValueError("Main Agent persona must be inside the installed template")

        documents = []
        remaining = _MAX_ROLE_BYTES
        for file in sorted(folder.rglob("*.md")):
            if file.is_symlink() or not file.resolve().is_relative_to(root) or not file.is_file():
                raise ValueError("Main Agent persona contains an invalid file")
            with file.open("rb") as stream:
                data = stream.read(remaining + 1)
            if len(data) > remaining:
                raise ValueError("Main Agent role exceeds the persona size limit")
            text = data.decode("utf-8").strip()
            remaining -= len(data)
            if text:
                if documents:
                    remaining -= 2
                if remaining < 0:
                    raise ValueError("Main Agent role exceeds the persona size limit")
                documents.append(text)
        if not documents:
            raise ValueError("Main Agent role template has no persona text")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Main Agent role template could not be read") from exc
    return MainAgentRole(template_ref, "\n\n".join(documents))
