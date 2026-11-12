"""The probe must not confuse a broken CLI or readable marker with success."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

source = Path(__file__).resolve().parents[3] / "deploy/cloud-workspace/codex_sandbox_probe.py"
spec = importlib.util.spec_from_file_location("codex_sandbox_probe", source)
probe_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe_module)


@pytest.mark.parametrize("failure", ["namespace", "readable", "link-readable", "version", "timeout",
                                     "missing-file", "bad-marker", "command-error"])
def test_probe_never_reports_incomplete_boundary_as_ready(tmp_path, monkeypatch, failure):
    binary = tmp_path / "fake-codex"; binary.touch()
    real_run = subprocess.run
    def run(args, **kwargs):
        if args[-1] == "--version":
            return subprocess.CompletedProcess(args, 0, "codex-cli " + ("0.162.0" if failure == "version" else "0.163.0") + "\n", "")
        assert args[1:5] == ["sandbox", "--config", 'sandbox_mode="workspace-write"', "--"]
        if failure == "timeout": raise subprocess.TimeoutExpired(args, 15)
        if failure == "namespace": return subprocess.CompletedProcess(args, 1, "", "bwrap: namespace denied")
        command = args[5:]
        if len(command) > 1 and command[-2] == "write":
            return subprocess.CompletedProcess(args, 77, "", "")
        if len(command) > 1 and command[-2] == "read":
            if failure in {"missing-file", "bad-marker", "command-error"}:
                return subprocess.CompletedProcess(args, {"missing-file": 78, "bad-marker": 79, "command-error": 127}[failure], "", "")
            if failure == "readable" or command[-1].endswith("control-link"):
                return real_run(command, **kwargs)
            return subprocess.CompletedProcess(args, 77, "", "")
        return real_run(command, **kwargs)
    monkeypatch.setattr(probe_module.subprocess, "run", run)
    if failure in {"version", "timeout"}:
        with pytest.raises((ValueError, subprocess.TimeoutExpired)): probe_module.probe(binary, tmp_path)
    else:
        result = probe_module.probe(binary, tmp_path)
        assert not result["complete_boundary_ready"]
        assert result["execution_ready"] == (failure != "namespace")
    assert list(tmp_path.iterdir()) == [binary]


@pytest.mark.parametrize("mode,condition,expected", [
    ("read", "marker", 0), ("read", "different", 79), ("read", "absent", 78),
    ("write", "marker", 0), ("write", "directory", 78),
])
def test_probe_classifier_distinguishes_io_errors(tmp_path, mode, condition, expected):
    import sys
    target = tmp_path / "marker"
    if condition == "directory":
        target.mkdir()
    elif condition != "absent":
        target.write_text("synthetic-control-marker" if condition == "marker" else "different")
    result = subprocess.run([sys.executable, "-I", "-c", probe_module._BOUNDARY_CHECK, mode, str(target)],
                            capture_output=True, timeout=5)
    assert result.returncode == expected
