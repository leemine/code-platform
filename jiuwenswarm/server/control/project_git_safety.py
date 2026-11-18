"""Validate imported Git metadata before any checkout/status operation."""
import os
from pathlib import Path
import shutil
import subprocess

def _deny(message):
    raise ValueError('PROJECT_IMPORT_GIT_CONFIGURATION_DENIED')

def _environment(root):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0')
    return env


def _repository_root(root):
    """Use upstream parent discovery, then authorize the actual repository."""
    return next((parent for parent in (root, *root.parents)
                 if (parent / '.git').exists() or (parent / '.git').is_symlink()), root)


def _configuration(root, *, bare=False, allowed_filters=None):
    gitdir = root if bare else root / '.git'
    if not bare:
        gitdir = _repository_root(root) / '.git'
    if not gitdir.exists() and not gitdir.is_symlink():
        return {}
    if not gitdir.is_dir() or gitdir.is_symlink():
        _deny('Linked Git directories require separate resource authorization')
    for relative in ('config', 'HEAD', 'index', 'objects', 'refs', 'logs', 'hooks', 'packed-refs', 'objects/info'):
        path = gitdir / relative
        if path.is_symlink() or not path.resolve().is_relative_to(gitdir.resolve()):
            _deny('Git metadata must remain inside its authorized workspace')
    for directory, dirs, files in os.walk(gitdir, followlinks=False):
        if any((Path(directory) / name).is_symlink() for name in dirs + files):
            _deny('Git metadata symlinks require separate resource authorization')
    if any((gitdir / name).exists() for name in ('commondir', 'worktrees', 'objects/info/alternates')):
        _deny('Shared Git storage requires separate resource authorization')
    config = gitdir / 'config'
    if not config.exists():
        return {}
    executable = shutil.which('git')
    if not executable:
        _deny('Git is unavailable')
    result = subprocess.run([executable, 'config', '--file', str(config), '--no-includes', '--null', '--list'],
                            env=_environment(root), capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        _deny('Git configuration is unavailable')
    values = {}
    for entry in result.stdout.split('\0'):
        if not entry:
            continue
        key, _, value = entry.partition('\n')
        key = key.lower()
        if allowed_filters and key in allowed_filters and value == allowed_filters[key]:
            values.setdefault(key, []).append(value)
            continue
        if (key.startswith(('include.', 'includeif.', 'filter.', 'url.'))
                or key in {'core.worktree', 'core.sshcommand', 'core.gitproxy', 'extensions.partialclone'}
                or key.endswith('.promisor')
                or key.endswith(('.textconv', '.command', '.receivepack', '.uploadpack'))):
            _deny('Git executable configuration requires separate authorization')
        values.setdefault(key, []).append(value)
    return values


