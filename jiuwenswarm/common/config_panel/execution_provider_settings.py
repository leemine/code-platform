"""Installed execution adapter catalog; model configuration stays in Swarm."""
import json
from collections import Counter
from jiuwenswarm.common.native_integration import native_available
from importlib.metadata import entry_points


def public_fields(config):
    entries = tuple(entry_points(group="jiuwenswarm.agent_adapters"))
    counts = Counter(entry.name for entry in entries)
    profiles = {}
    catalog = [{"id": "harness", "label": "Deepagent", "available": True,
                "modes": ["agent", "code", "team"], "reason": None}] if native_available() else []
    seen = {"harness", "pi"}
    for entry in sorted(entries, key=lambda item: item.name):
        if entry.name in seen:
            continue
        seen.add(entry.name)
        row = {"id": entry.name, "label": entry.name, "available": False,
               "modes": [], "reason": "unavailable"}
        profiles[entry.name] = []
        if counts[entry.name] > 1:
            row["reason"] = "ambiguous"
            catalog.append(row)
            continue
        try:
            factory = entry.load()
            label = getattr(factory, "display_name", None)
            modes = getattr(factory, "supported_modes", ())
            # Registration alone does not advertise a plugin as a user-facing engine.
            if not isinstance(label, str) or not label.strip():
                continue
            row["label"] = label
            row["modes"] = [mode for mode in modes if mode in {"agent", "code"}]
            row["available"] = bool(row["modes"])
            row["reason"] = None if row["available"] else "unsupported_mode"
            declared = getattr(factory, "permission_profiles", ())
            profiles[entry.name] = [p for p in declared if p in {"default", "automatic", "full_access"}]
        except Exception:
            # Never expose import errors: they can include local paths or credentials.
            pass
        catalog.append(row)
    return {"opencode_adapter_available": "true" if any(
                row["id"] == "opencode-direct" and row["available"] for row in catalog) else "false",
            "execution_provider_catalog": json.dumps(catalog),
            "execution_provider_permission_profiles": json.dumps(profiles)}
