"""Official Git LFS integration; credentials stay in the broker Git process."""
from pathlib import Path
import hashlib
import os
import re
import shlex
import shutil

MAX_ASSETS = 256 * 1024 * 1024


class MissingObjects(ValueError):
    """Safe, structured failure detail; count paths, not unique objects."""
    def __init__(self, missing_files):
        super().__init__('GIT_LFS_OBJECT_UNAVAILABLE')
        self.missing_files = missing_files


def executable():
    value = os.environ.get('SWARM_GIT_LFS_EXECUTABLE') or shutil.which('git-lfs')
    if not value or not Path(value).is_absolute() or not Path(value).is_file() or not os.access(value, os.X_OK):
        raise ValueError('GIT_LFS_UNAVAILABLE')
    return str(Path(value).resolve())


def filters():
    command = shlex.quote(executable())
    return {'filter.lfs.clean': command + ' clean -- %f',
            'filter.lfs.smudge': command + ' smudge -- %f',
            'filter.lfs.process': command + ' filter-process', 'filter.lfs.required': 'true'}


def parse_pointer(content, *, bounded=True):
    if not content.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
        return None
    match = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n', content)
    if not match:
        raise ValueError('GIT_LFS_INVALID_POINTER')
    size = int(match[2])
    # Official LFS clean retains empty files as empty Git blobs. A historical
    # pointer to an empty object cannot round-trip to a clean worktree.
    if bounded and size == 0:
        raise ValueError('GIT_LFS_UNSUPPORTED_EMPTY_POINTER')
    if bounded and size > MAX_ASSETS:
        raise ValueError('GIT_LFS_SIZE_LIMIT')
    return {'oid': match[1].decode(), 'size': size}


def verify(path, item):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != item['size']:
        raise ValueError('GIT_LFS_OBJECT_INCOMPLETE')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != item['oid']:
            raise ValueError('GIT_LFS_HASH_MISMATCH')


def object_path(root, oid, *, bare=False):
    return Path(root) / ('' if bare else '.git') / 'lfs' / 'objects' / oid[:2] / oid[2:4] / oid


def fetch(root, name, commit, token):
    from .project_checkout import git, inspect_tree
    facts = inspect_tree(root, commit, allow_lfs=True)
    items = facts.get('lfs', [])
    if not items:
        return []
    # No repository-supplied URL, custom transfer adapter, user config or helper.
    # The authenticated GitHub LFS endpoint delegates object downloads to the
    # official client. It does not receive an Agent filesystem/credential path.
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', name):
        raise ValueError('GIT_INVALID_SOURCE')
    configs = {'remote.origin.url': f'https://github.com/{name}.git',
               'lfs.url': f'https://github.com/{name}.git/info/lfs',
               'lfs.basictransfersonly': 'true', 'lfs.concurrenttransfers': '2',
               'lfs.fetchrecentalways': 'false', 'lfs.fetchinclude': '', 'lfs.fetchexclude': '',
               'lfs.transfer.maxretries': '2', 'lfs.activitytimeout': '30'}
    try:
        git(root, 'lfs', 'fetch', 'origin', commit, token=token, network=True,
            lfs=True, extra_config=configs, budget_root=root)
    except ValueError as exc:
        if str(exc) != 'GIT_LFS_OBJECT_UNAVAILABLE':
            raise
        # Fetch may have completed some objects before failing. Count only paths
        # still lacking verified bytes; a shared object may serve several files.
        unavailable = set()
        for item in {(item['oid'], item['size']): item for item in items}.values():
            try:
                verify(object_path(root, item['oid'], bare=True), item)
            except ValueError:
                unavailable.add((item['oid'], item['size']))
        raise MissingObjects(sum((item['oid'], item['size']) in unavailable for item in items)) from None
    for item in items:
        verify(object_path(root, item['oid'], bare=True), item)
    return items


def checkout(root, items, private):
    from .project_checkout import git
    for item in items:
        source = Path(private) / item['oid']
        verify(source, item)
        target = object_path(root, item['oid'])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or target.parent.resolve() != target.parent:
            raise ValueError('GIT_LFS_STORAGE_INVALID')
        if not target.exists():
            temporary = target.with_suffix('.tmp')
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        verify(target, item)
    for key, value in filters().items():
        git(root, 'config', '--local', key, value)
    # Unlike pull/fetch, checkout is local-only and cannot request credentials.
    git(root, 'lfs', 'checkout', lfs=True, budget_root=root)
    for item in items:
        path = Path(root) / item['path']
        if path.resolve() != path or not path.is_relative_to(Path(root)):
            raise ValueError('GIT_LFS_STORAGE_INVALID')
        verify(path, item)
