"""Discardable, account/target-scoped Git objects in the private broker volume.

Projects keep independent .git directories. A cache is never an authority grant,
and returned operation packs survive eviction through their own hard link.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil

import portalocker

MAX_REPOSITORIES = 4
MAX_REPOSITORY_BYTES = 512 * 1024 * 1024


def _directory(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('GIT_CACHE_STORAGE_INVALID')
    missing, current = [], path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for item in reversed(missing):
        try:
            item.mkdir(mode=0o700)
        except FileExistsError:
            pass
    st = path.lstat()
    if not path.is_dir() or path.is_symlink() or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('GIT_CACHE_STORAGE_INVALID')
    return path


def _size(root):
    size = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(current) / name
            if path.is_symlink() or path.stat().st_uid != os.getuid():
                raise ValueError('GIT_CACHE_STORAGE_INVALID')
        size += sum((Path(current) / name).stat().st_size for name in files)
    return size


def cached_bundle(scope_root, repository_id, commit, destination, prepare, *, validate=None, progress=None,
                  format_id='snapshot-v1', refresh=False):
    if type(repository_id) is not int or not 0 < repository_id < 2**53 or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('GIT_INVALID_SOURCE')
    scope_root = _directory(scope_root)
    _directory(scope_root.parent)
    lock = scope_root / '.lock'
    if lock.is_symlink():
        raise ValueError('GIT_CACHE_STORAGE_INVALID')
    try:
        # All cache lifecycle changes for one account/target serialize. Other
        # accounts use different roots; no active project directories are GC'd.
        with portalocker.Lock(str(lock), mode='a', timeout=30):
            if validate:
                validate()
            repositories = [p for p in scope_root.iterdir() if p.name.isdecimal()]
            for entry in repositories:
                _directory(entry)
            entry = scope_root / str(repository_id)
            if not entry.exists() and len(repositories) >= MAX_REPOSITORIES:
                oldest = min(repositories, key=lambda p: p.stat().st_mtime_ns)
                _size(oldest)  # Refuse unsafe trees, even during eviction.
                shutil.rmtree(oldest)
            entry = _directory(entry)
            if _size(entry) > MAX_REPOSITORY_BYTES:
                raise ValueError('GIT_CACHE_STORAGE_LIMIT')
            repository = _directory(entry / 'repository.git')
            packed, receipt = entry / 'bundle.pack', entry / 'bundle.json'
            hit = False
            if receipt.exists():
                try:
                    record = json.loads(receipt.read_text())
                    if not isinstance(record, dict):
                        raise ValueError()
                except ValueError:
                    raise ValueError('GIT_CACHE_INVALID') from None
                if (not refresh and record.get('commit') == commit
                        and record.get('format', 'snapshot-v1') == format_id):
                    if not packed.is_file() or packed.stat().st_size != record.get('bytes'):
                        raise ValueError('GIT_CACHE_INVALID')
                    with packed.open('rb') as handle:
                        if hashlib.file_digest(handle, 'sha256').hexdigest() != record.get('sha256'):
                            raise ValueError('GIT_CACHE_INVALID')
                    hit = True
            if not hit:
                temporary = entry / 'bundle.partial'
                # Incomplete packs are never cache hits after a crash.
                temporary.unlink(missing_ok=True)
                try:
                    prepare(repository, temporary)
                    if _size(entry) > MAX_REPOSITORY_BYTES:
                        raise ValueError('GIT_CACHE_STORAGE_LIMIT')
                    with temporary.open('rb') as handle:
                        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
                    record = {'commit': commit, 'bytes': temporary.stat().st_size, 'sha256': digest,
                              'format': format_id}
                    os.replace(temporary, packed)
                    pending = entry / 'bundle.json.partial'
                    with pending.open('w') as handle:
                        json.dump(record, handle)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(pending, receipt)
                finally:
                    temporary.unlink(missing_ok=True)
            if validate:
                validate()
            # The caller created this operation's new private directory. Never
            # overwrite its existing files or borrow a mutable project checkout.
            os.link(packed, destination)
            os.utime(entry, None)
            if progress:
                progress({'phase': 'pack', 'cache_hit': hit, 'bytes': destination.stat().st_size})
            return destination
    except portalocker.exceptions.LockException:
        raise ValueError('GIT_CACHE_BUSY') from None
