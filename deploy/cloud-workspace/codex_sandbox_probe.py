"""No-model probe for the locked Codex CLI, using only disposable test data.

Run inside an already identified disposable diagnostic container. This program
does not create instances, install policies, read credentials, or change Codex.
Exit 1 means the complete boundary is NOT ready, even if commands can execute.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


_BOUNDARY_CHECK = """
import errno
from pathlib import Path
import sys
try:
    if sys.argv[1] == "write":
        Path(sys.argv[2]).write_text("changed")
    elif Path(sys.argv[2]).read_text() != "synthetic-control-marker":
        sys.exit(79)
except OSError as error:
    allowed = {errno.EACCES, errno.EPERM}
    if sys.argv[1] == "write":
        allowed.add(errno.EROFS)
    sys.exit(77 if error.errno in allowed else 78)
"""


def probe(binary: Path, root: Path) -> dict:
    if not binary.is_absolute() or not binary.is_file() or not root.is_absolute() or root.resolve() != root:
        raise ValueError("explicit installed CLI and canonical disposable root required")
    with tempfile.TemporaryDirectory(prefix="codex-boundary-", dir=root) as directory:
        home = Path(directory)
        workspace = home / "workspace"
        workspace.mkdir(mode=0o700)
        control = home / "synthetic-control"
        control.write_text("synthetic-control-marker")
        control.chmod(0o600)
        # Prove the outer filesystem itself permits this write, before checking
        # whether the inner sandbox rejects it. No production file is opened.
        control.write_text("positive-control")
        control.write_text("synthetic-control-marker")
        link = workspace / "control-link"
        link.symlink_to(control)
        env = {"PATH": "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin", "HOME": directory,
               "CODEX_HOME": directory, "LANG": "C.UTF-8"}
        version = subprocess.run([str(binary), "--version"], env=env, capture_output=True, text=True, timeout=10)
        if version.returncode != 0 or version.stdout.strip() != "codex-cli 0.163.0":
            raise ValueError("probe is validated only for the locked Codex CLI 0.163.0")
        commands = {
            "minimal": ["/bin/true"],
            "workspace_write": ["/bin/sh", "-c", "printf success > probe-output"],
            "outside_write": [sys.executable, "-I", "-c", _BOUNDARY_CHECK, "write", str(control)],
            "synthetic_control_read": [sys.executable, "-I", "-c", _BOUNDARY_CHECK, "read", str(control)],
            "synthetic_link_read": [sys.executable, "-I", "-c", _BOUNDARY_CHECK, "read", str(link)],
        }
        results = {}
        for name, command in commands.items():
            # 0.163.0 takes the command directly; `sandbox linux` would execute
            # an application named linux and can obscure the real boundary.
            result = subprocess.run([str(binary), "sandbox", "--config", 'sandbox_mode="workspace-write"',
                                     "--", *command], env=env, cwd=workspace, capture_output=True, text=True, timeout=15)
            results[name] = {"exit": result.returncode, "stderr": result.stderr[:2000]}
        execution = results["minimal"]["exit"] == 0 and results["workspace_write"]["exit"] == 0
        if execution:
            execution = (workspace / "probe-output").read_text() == "success"
        # Only the probe's explicit permission errno is a denial. Missing files,
        # invalid commands, namespace failures and marker mismatch are not proof.
        write_boundary = execution and results["outside_write"]["exit"] == 77
        write_boundary = write_boundary and control.read_text() == "synthetic-control-marker"
        read_boundary = execution and results["synthetic_control_read"]["exit"] == 77
        read_boundary = read_boundary and results["synthetic_link_read"]["exit"] == 77
        return {"cli": version.stdout.strip(), "uid": os.getuid(), "cases": results,
                "execution_ready": execution, "write_boundary": write_boundary,
                "synthetic_control_read_blocked": read_boundary,
                "complete_boundary_ready": execution and write_boundary and read_boundary,
                "scope": "synthetic CLI probe only; not UI, credentials, model, or lifecycle acceptance"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-binary", type=Path, required=True)
    parser.add_argument("--disposable-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = probe(args.codex_binary, args.disposable_root)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"complete_boundary_ready": False, "error": type(error).__name__}))
        raise SystemExit(2) from None
    print(json.dumps(result))
    raise SystemExit(0 if result["complete_boundary_ready"] else 1)


if __name__ == "__main__":
    main()
