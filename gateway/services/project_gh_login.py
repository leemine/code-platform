"""Run the unmodified official gh login in a task-owned private configuration.

Only a short user code is exposed. Raw CLI output and credential files never
leave the Gateway. No ambient credentials, browser launch or global git setup.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path


class GhLogin:
    def __init__(self, executable, directory):
        self.executable = executable
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.environment = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': str(self.directory), 'XDG_CONFIG_HOME': str(self.directory),
            'GH_CONFIG_DIR': str(self.directory), 'GH_HOST': 'github.com',
            'GH_BROWSER': '/bin/true', 'BROWSER': '/bin/true',
            'GH_NO_UPDATE_NOTIFIER': '1', 'GH_NO_EXTENSION_UPDATE_NOTIFIER': '1',
            'GH_PROMPT_DISABLED': '1', 'NO_COLOR': '1', 'TERM': 'dumb',
            'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'GIT_TERMINAL_PROMPT': '0',
        }
        self.close_lock = threading.Lock()
        self.process = None
        self.code = None
        self.changed = threading.Event()
        self.finished = threading.Event()
        self.output = bytearray()

    def start(self):
        try:
            self.process = subprocess.Popen([self.executable, 'auth', 'login', '--hostname', 'github.com',
                '--git-protocol', 'https', '--web', '--skip-ssh-key', '--insecure-storage'],
                cwd=self.directory, env=self.environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.process.stdin.write(b'\n')
            self.process.stdin.close()
            threading.Thread(target=self._read, daemon=True).start()
        except Exception:
            self.close()
            raise ValueError('GITHUB_CLI_UNAVAILABLE') from None

    def _read(self):
        try:
            while True:
                raw = self.process.stdout.read(1)
                if not raw:
                    break
                self.output.extend(raw)
                if len(self.output) > 16384:
                    self.process.terminate()
                    break
                code = re.search(rb'\b([A-Z0-9]{4}-[A-Z0-9]{4})\b', self.output)
                if code and self.code is None:
                    self.code = code.group(1).decode('ascii')
                    self.changed.set()
            self.process.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        finally:
            self.output.clear()
            self.finished.set()
            self.changed.set()

    def run(self, args):
        result = subprocess.run([self.executable, *args], cwd=self.directory, env=self.environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        if result.returncode or len(result.stdout) > 1024 * 1024:
            raise ValueError('GITHUB_REAUTHORIZE')
        return result.stdout.decode('utf-8')

    def credentials(self):
        values = {}
        for name in ('hosts.yml', 'config.yml'):
            path = self.directory / name
            if path.exists():
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
                    raise ValueError('GITHUB_INVALID_CREDENTIAL_STORE')
                path.chmod(0o600)
                values[name] = path.read_text()
        if not values.get('hosts.yml'):
            raise ValueError('GITHUB_REAUTHORIZE')
        return values

    def restore(self, values):
        if not isinstance(values, dict) or set(values) - {'hosts.yml', 'config.yml'}:
            raise ValueError('GITHUB_INVALID_CREDENTIAL_STORE')
        for name, value in values.items():
            if not isinstance(value, str) or len(value) > 128 * 1024:
                raise ValueError('GITHUB_INVALID_CREDENTIAL_STORE')
            path = self.directory / name
            with path.open('x', encoding='utf-8') as stream:
                os.chmod(path, 0o600)
                stream.write(value)

    def close(self):
        with self.close_lock:
            process = self.process
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                if process.stdout:
                    process.stdout.close()
            shutil.rmtree(self.directory, ignore_errors=True)
