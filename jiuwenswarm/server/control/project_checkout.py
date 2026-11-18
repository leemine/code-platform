"""Bounded Git plumbing shared by the credential broker and project importer.

Never inherit user Git configuration, execute repository hooks, or recursively
materialize submodules or arbitrary filters. Explicit LFS restoration uses the
official client; credentials are used only in the broker process.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from contextlib import ExitStack

MAX_BUNDLE = 128 * 1024 * 1024
MAX_TREE = 512 * 1024 * 1024
MAX_FILES = 50000
LOCAL_GIT_TIMEOUT = 120
NETWORK_GIT_TIMEOUT = 900


class GitCommandError(ValueError):
    """Fixed diagnostics only; never retain Git stderr or credential URLs."""

    def __init__(self, code, phase, exit_code=None, *, retryable=False):
        super().__init__(code)
        self.diagnostic = {'phase': phase, 'code': code, 'exit_code': exit_code,
                           'retryable': retryable}


def classify_git_failure(diagnostic, *, network=False):
    text = diagnostic.lower()
    rules = (
        ((b'certificate',), 'GIT_CERTIFICATE_FAILED', False),
        ((b'authentication failed', b'could not read username', b'could not read password'), 'GIT_AUTHENTICATION_FAILED', False),
        ((b'repository not found', b'returned error: 404', b'not our ref'), 'GIT_SOURCE_UNAVAILABLE', False),
        ((b'returned error: 429', b'returned error: 503', b'returned error: 502', b'returned error: 504'), 'GIT_REMOTE_BUSY', True),
        ((b'could not resolve host',), 'GIT_DNS_FAILED', True),
        ((b'failed to connect', b'connection timed out', b'connection reset', b'early eof', b'operation too slow', b'rpc failed', b'http/2 stream', b'tls connection was non-properly terminated'), 'GIT_TRANSFER_FAILED', True),
        ((b'no space left', b'disk quota exceeded'), 'GIT_STORAGE_LIMIT', False),
        ((b'fsck error', b'object corrupt', b'index-pack failed'), 'GIT_OBJECT_INVALID', False),
    )
    for markers, code, retryable in rules:
        if any(marker in text for marker in markers):
            return code, bool(network and retryable)
    return 'GIT_COMMAND_FAILED', False


def _tree_bytes(root):
    total = 0
    for path in Path(root).rglob('*'):
        try:
            entry = path.stat(follow_symlinks=False)
        except FileNotFoundError:
            # Git can rename an in-progress pack while the budget is sampled.
            continue
        if stat.S_ISREG(entry.st_mode):
            total += entry.st_size
    return total


def git(root, *args, token=None, username='x-access-token', network=False, budget_root=None, stdin_data=None, input_file=None, output_file=None, lfs=False, extra_config=None, timeout_seconds=None, validate=None):
    executable = shutil.which('git')
    if not executable:
        raise ValueError('GIT_UNAVAILABLE')
    with tempfile.TemporaryDirectory(prefix='swarm-git-') as home:
        env = {'PATH': '/usr/bin:/bin', 'HOME': home, 'XDG_CONFIG_HOME': home,
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
               'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1', 'LC_ALL': 'C'}
        if lfs:
            from .project_lfs import executable as lfs_executable
            env['PATH'] = str(Path(lfs_executable()).parent) + os.pathsep + env['PATH']
        if token:
            # No credential in argv/config/remote URL or on disk. This private
            # broker process must run outside execution UIDs/volumes.
            ask = Path(home) / 'askpass'
            ask.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" "$SWARM_GIT_USERNAME";; *) printf "%s\\n" "$SWARM_GIT_PASSWORD";; esac\n')
            ask.chmod(0o700)
            env.update(GIT_ASKPASS=str(ask), SWARM_GIT_PASSWORD=token, SWARM_GIT_USERNAME=username)
        command = [executable, '-c', 'core.hooksPath=/dev/null', '-c', 'init.templateDir=',
                   '-c', 'protocol.allow=never', '-c', f'protocol.{"https" if network else "file"}.allow=always',
                   '-c', 'http.followRedirects=false', '-c', 'credential.helper=',
                   *(['-c', 'http.version=HTTP/1.1', '-c', 'http.lowSpeedLimit=1024', '-c', 'http.lowSpeedTime=60'] if network else []),
                   '-c', 'fetch.fsckObjects=true', '-c', 'transfer.fsckObjects=true',
                   '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false', '-c', 'core.autocrlf=false', '-c', 'core.attributesFile=/dev/null',
                   *[part for key, value in (extra_config or {}).items() for part in ('-c', key + '=' + value)],
                   '-C', str(root), *args]
        # Upstream stderr may contain credentials. Bound and classify it locally;
        # neither raw bytes nor exceptions containing them leave this function.
        with ExitStack() as stack:
            output = stack.enter_context(open(output_file, 'w+b') if output_file else tempfile.TemporaryFile())
            errors = stack.enter_context(tempfile.TemporaryFile())
            incoming = subprocess.DEVNULL
            if input_file:
                incoming = stack.enter_context(open(input_file, 'rb'))
            elif stdin_data is not None:
                incoming = stack.enter_context(tempfile.TemporaryFile())
                incoming.write(stdin_data)
                incoming.seek(0)
            proc = subprocess.Popen(command, env=env, stdout=output, stderr=errors,
                                    stdin=incoming, start_new_session=True)
            # A bounded network fetch can download the complete repository;
            # keep its budget separate from local plumbing and storage limits.
            deadline = time.monotonic() + (timeout_seconds if timeout_seconds is not None else
                                          NETWORK_GIT_TIMEOUT if network else LOCAL_GIT_TIMEOUT)
            next_validation = 0.0
            try:
                while proc.poll() is None:
                    if validate and time.monotonic() >= next_validation:
                        validate()
                        next_validation = time.monotonic() + 1.0
                    if time.monotonic() > deadline:
                        raise GitCommandError('GIT_TIMEOUT', args[0], retryable=network)
                    if budget_root and _tree_bytes(budget_root) > MAX_TREE:
                        raise ValueError('GIT_STORAGE_LIMIT')
                    if os.fstat(output.fileno()).st_size > (MAX_BUNDLE if output_file else 16 * 1024 * 1024):
                        raise ValueError('GIT_OUTPUT_LIMIT')
                    if os.fstat(errors.fileno()).st_size > 1024 * 1024:
                        raise ValueError('GIT_OUTPUT_LIMIT')
                    time.sleep(.05)
                if (os.fstat(errors.fileno()).st_size > 1024 * 1024
                        or os.fstat(output.fileno()).st_size > (MAX_BUNDLE if output_file else 16 * 1024 * 1024)):
                    raise ValueError('GIT_OUTPUT_LIMIT')
                if proc.returncode:
                    errors.seek(0)
                    diagnostic = errors.read(65536)
                    if lfs:
                        if b'Object does not exist on the server' in diagnostic and b'[404]' in diagnostic:
                            raise ValueError('GIT_LFS_OBJECT_UNAVAILABLE')
                    code, retryable = classify_git_failure(diagnostic, network=network)
                    raise GitCommandError(code, args[0], proc.returncode, retryable=retryable)
                if output_file:
                    output.flush()
                    os.fsync(output.fileno())
                    return b""
                output.seek(0)
                return output.read()
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()


def inspect_tree(repo, commit, *, allow_lfs=False, defer_lfs=False):
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('GIT_INVALID_COMMIT')
    rows = git(repo, 'ls-tree', '-r', '-l', '-z', commit).split(b'\0')
    count, size = 0, 0
    small_blobs = {}
    assets = []
    for row in rows:
        if not row:
            continue
        metadata, name = row.split(b'\t', 1)
        mode, kind, oid, length = metadata.split()
        count += 1
        if (kind != b'blob' or mode not in (b'100644', b'100755') or name.startswith(b'/')
                or b'\\' in name or any(c < 32 for c in name)
                or any(p.lower() in (b'', b'.', b'..', b'.git') for p in name.split(b'/'))):
            # P0 explicitly rejects symlinks and submodules instead of producing
            # an apparently ready but incomplete/escaping workspace.
            raise ValueError('GIT_UNSUPPORTED_TREE_ENTRY')
        size += int(length)
        if int(length) <= 1024:
            small_blobs.setdefault(oid, []).append(name.decode('utf-8'))
        if count > MAX_FILES or size > MAX_TREE:
            raise ValueError('GIT_TREE_LIMIT')
    # Inspect LFS before transferring the pack or publishing a workspace. Native
    # batch plumbing avoids one subprocess per small file and never runs filters.
    if small_blobs:
        data = git(repo, 'cat-file', '--batch', stdin_data=b'\n'.join(sorted(small_blobs)) + b'\n')
        offset = 0
        for _ in small_blobs:
            end = data.index(b'\n', offset)
            oid, kind, length = data[offset:end].split()
            length = int(length)
            content = data[end + 1:end + 1 + length]
            if kind != b'blob' or len(content) != length:
                raise ValueError('GIT_INVALID_TREE')
            from .project_lfs import parse_pointer, MAX_ASSETS
            pointer = parse_pointer(content, bounded=not defer_lfs)
            if pointer:
                if not allow_lfs:
                    raise ValueError('GIT_LFS_NOT_SUPPORTED')
                assets.extend({**pointer, 'path': path} for path in small_blobs[oid])
                if not defer_lfs and sum(item['size'] for item in assets) > MAX_ASSETS:
                    raise ValueError('GIT_LFS_SIZE_LIMIT')
            offset = end + 2 + length
    return {'files': count, 'bytes': size, **({'lfs': assets} if assets else {})}


def repository_url(provider, name):
    hosts = {'github': 'github.com', 'gitcode': 'gitcode.com'}
    if (provider not in hosts or not isinstance(name, str) or len(name) > 250
            or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', name)
            or any(part in {'.', '..'} for part in name.split('/'))):
        raise ValueError('GIT_INVALID_SOURCE')
    return 'https://' + hosts[provider] + '/' + name + '.git'


def make_bundle(root, name, commit, token, *, cache_root=None, repository_id=None,
                validate=None, progress=None, complete=False, provider='github', username='x-access-token'):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', name) or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('GIT_INVALID_SOURCE')
    remote_url = repository_url(provider, name)
    def prepare(repository, bundle):
        if validate:
            validate()
        if not (repository / 'HEAD').exists():
            git(repository, 'init', '--bare', '.')
        else:
            from .project_git_safety import _configuration
            _configuration(repository, bare=True)
        try:
            git(repository, 'cat-file', '-e', commit + '^{commit}')
            present = True
        except GitCommandError:
            present = False
        if complete or not present:
            fetch_deadline = time.monotonic() + NETWORK_GIT_TIMEOUT
            shallow_lock = repository / 'shallow.lock'
            for attempt in range(1, 4):
                if validate:
                    validate()
                if progress:
                    progress({'phase': 'fetch', 'attempt': attempt, 'cache_hit': False})
                had_shallow_lock = shallow_lock.exists()
                pack_dir = repository / 'objects' / 'pack'
                previous_partial_packs = set(pack_dir.glob('tmp_pack_*'))
                try:
                    options = (['--unshallow'] if complete and (repository / 'shallow').exists() else [])
                    options += (['--prune', '--atomic'] if complete else ['--depth=1', '--no-tags'])
                    refs = (['+refs/heads/*:refs/heads/*', '+refs/tags/*:refs/tags/*'] if complete else [commit])
                    git(repository, 'fetch', *options, '--no-recurse-submodules',
                        remote_url, *refs, token=token, username=username,
                        network=True, budget_root=repository,
                        timeout_seconds=max(.1, fetch_deadline - time.monotonic()), validate=validate)
                    break
                except GitCommandError as exc:
                    if progress:
                        progress({**exc.diagnostic, 'attempt': attempt, 'cache_hit': False})
                    if (not exc.diagnostic['retryable'] or attempt == 3
                            or time.monotonic() + attempt >= fetch_deadline):
                        raise
                    time.sleep(attempt)
                finally:
                    # This repository is exclusively held by the cache lease.
                    # git() has reaped its process group before cleanup, including
                    # permission cancellation. Never remove pre-existing files.
                    if not had_shallow_lock:
                        shallow_lock.unlink(missing_ok=True)
                    for partial in set(pack_dir.glob('tmp_pack_*')) - previous_partial_packs:
                        partial.unlink(missing_ok=True)
            if complete and not present:
                # A branch may move after resolution. Fetch the pinned original
                # object too; never silently replace this operation's commit.
                try:
                    git(repository, 'cat-file', '-e', commit + '^{commit}')
                except GitCommandError:
                    if validate:
                        validate()
                    git(repository, 'fetch', '--no-tags', '--no-recurse-submodules',
                        remote_url, commit, token=token, username=username,
                        network=True, budget_root=repository, validate=validate,
                        timeout_seconds=max(.1, fetch_deadline - time.monotonic()))
            # Keep advertised haves for the next incremental fetch. These refs
            # live only in the private broker cache, never in a user project.
            git(repository, 'update-ref', 'refs/swarm-cache/' + commit, commit)
        inspect_tree(repository, commit, allow_lfs=True, defer_lfs=True)
        if complete:
            if git(repository, 'rev-parse', '--is-shallow-repository').strip() != b'false':
                raise ValueError('GIT_INCOMPLETE_HISTORY')
            git(repository, 'bundle', 'create', '-', '--branches', '--tags', 'refs/swarm-cache/' + commit,
                output_file=bundle, budget_root=repository)
        else:
            git(repository, 'pack-objects', '--stdout', '--revs', stdin_data=(commit + '\n').encode(),
                output_file=bundle, budget_root=repository)
        if validate:
            validate()
    root = Path(root)
    root.mkdir(mode=0o700)
    bundle = root / 'source.bundle'
    if cache_root is not None:
        from .project_repository_cache import cached_bundle
        return cached_bundle(cache_root, repository_id, commit, bundle, prepare,
                             validate=validate, progress=progress,
                             format_id='repository-v1' if complete else 'snapshot-v1', refresh=complete)
    prepare(root, bundle)
    # Both native formats preserve original object IDs. Only legacy snapshot
    # packs have shallow markers; complete bundles carry branch/tag history.
    if bundle.stat().st_size > MAX_BUNDLE:
        raise ValueError('GIT_BUNDLE_LIMIT')
    return bundle


def materialize(root, bundle, commit, *, allow_lfs=False, defer_lfs=False):
    git(root, 'init', '.')
    with Path(bundle).open('rb') as handle:
        packed = handle.read(4) == b'PACK'
    if packed:
        git(root, 'index-pack', '--stdin', input_file=bundle, budget_root=root)
        # Commit existence/type and its complete tree are verified before use.
        if git(root, 'cat-file', '-t', commit).strip() != b'commit':
            raise ValueError('GIT_COMMIT_MISMATCH')
        (Path(root) / '.git' / 'shallow').write_text(commit + '\n')
    else:
        git(root, 'bundle', 'verify', str(bundle))
        refs = git(root, 'bundle', 'list-heads', str(bundle)).decode().splitlines()
        if not refs or len(refs) > MAX_FILES:
            raise ValueError('GIT_INVALID_SOURCE')
        for row in refs:
            oid, ref = row.split(' ', 1)
            if (not re.fullmatch(r'[a-f0-9]{40}', oid)
                    or not ref.startswith(('refs/heads/', 'refs/tags/', 'refs/swarm-cache/'))):
                raise ValueError('GIT_INVALID_SOURCE')
            git(root, 'check-ref-format', ref)
        git(root, 'fetch', '--no-tags', '--no-recurse-submodules', str(bundle),
            '+refs/heads/*:refs/remotes/origin/*', '+refs/tags/*:refs/tags/*', commit, budget_root=root)
        if git(root, 'cat-file', '-t', commit).strip() != b'commit':
            raise ValueError('GIT_COMMIT_MISMATCH')
    facts = inspect_tree(root, commit, allow_lfs=allow_lfs, defer_lfs=defer_lfs)
    git(root, 'checkout', '--detach', commit, budget_root=root)
    return facts



def attach_source_branch(project):
    """Attach only a verified unchanged import; never reset an existing branch.

    Used at publication (and explicit publication retry for legacy imports).
    The immutable source commit is unchanged. Read/status never mutate Git.
    """
    source = source_snapshot(project)
    root = Path(project.project_dir)
    branch = source['branch']
    if not isinstance(branch, str) or not branch or branch.startswith('-'):
        raise ValueError('PROJECT_IMPORT_INVALID_BRANCH')
    ref = 'refs/heads/' + branch
    git(root, 'check-ref-format', ref)
    current = git(root, 'rev-parse', '--abbrev-ref', 'HEAD').decode().strip()
    if current != 'HEAD':
        return
    refs = git(root, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads/').decode().splitlines()
    existing = dict(line.split(' ', 1) for line in refs)
    if ref in existing and existing[ref] != source['commit']:
        raise ValueError('PROJECT_IMPORT_BRANCH_CONFLICT')
    # Compare-and-swap creation prevents clobbering a concurrently created ref.
    if ref not in existing:
        git(root, 'update-ref', ref, source['commit'], '0' * 40)
    if git(root, 'for-each-ref', '--format=%(refname)', 'refs/remotes/origin/').strip():
        # Initialize ordinary clone metadata only during first publication.
        # Retry must never overwrite an attached project's user remote config.
        name = source.get('full_name')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', name):
            raise ValueError('PROJECT_IMPORT_INVALID_SOURCE')
        git(root, 'config', 'remote.origin.url', repository_url(source.get('provider', 'github'), name))
        git(root, 'config', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/origin/*')
        git(root, 'config', 'branch.' + branch + '.remote', 'origin')
        git(root, 'config', 'branch.' + branch + '.merge', ref)
    git(root, 'symbolic-ref', 'HEAD', ref)


def _checked_workspace(project):
    """Validate the registered directory and Git metadata without freezing edits."""
    source = getattr(project, 'repository_source', {})
    if not source:
        return None
    root = Path(project.project_dir)
    if root.is_symlink() or str(root.resolve()) != str(root):
        raise ValueError('PROJECT_SOURCE_CHANGED')
    st = root.stat()
    if source.get('root_inode') != [st.st_dev, st.st_ino]:
        raise ValueError('PROJECT_SOURCE_CHANGED')
    from .project_git_safety import _configuration
    from .project_lfs import filters
    hydrated = bool(source.get('lfs')) and source.get('lfs_mode') != 'deferred'
    _configuration(root, allowed_filters=filters() if hydrated else None)
    # Git may use forward slashes on Windows; compare path identities, not text.
    if Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != root:
        raise ValueError('PROJECT_SOURCE_CHANGED')
    return root, source, hydrated


def source_snapshot(project):
    """Strict initial checkout/publication verification; never relax for retry."""
    checked = _checked_workspace(project)
    if checked is None:
        return None
    root, source, hydrated = checked
    from .project_lfs import verify
    for item in source.get('lfs', []) if hydrated else []:
        path = root / item['path']
        if path.resolve() != path:
            raise ValueError('PROJECT_SOURCE_CHANGED')
        verify(path, item)
    if git(root, 'rev-parse', 'HEAD').decode().strip() != source['commit']:
        raise ValueError('PROJECT_SOURCE_CHANGED')
    if git(root, 'status', '--porcelain', '--untracked-files=normal', lfs=hydrated):
        raise ValueError('PROJECT_SOURCE_DIRTY_RECHECK_REQUIRED')
    return dict(source)


def workspace_snapshot(project):
    """Existing projects use current work, preserving the original import facts.

    This observes Git only; account/project/resource admission stays with Runtime.
    No reset, checkout, commit, clean or restoration of imported LFS content occurs.
    """
    checked = _checked_workspace(project)
    if checked is None:
        return None
    root, source, hydrated = checked
    return {**source, 'workspace': {
        'commit': git(root, 'rev-parse', 'HEAD').decode().strip(),
        'branch': git(root, 'rev-parse', '--abbrev-ref', 'HEAD').decode().strip(),
        'dirty': bool(git(root, 'status', '--porcelain', '--untracked-files=normal', lfs=hydrated)),
    }}
