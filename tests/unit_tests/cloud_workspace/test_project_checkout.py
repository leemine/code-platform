"""Fetch budgets and cancellation at the actual subprocess boundary."""
import os
from pathlib import Path

import pytest

from jiuwenswarm.server.control import project_checkout as subject


def test_fetch_uses_remaining_total_budget_and_cleans_only_own_partial(tmp_path, monkeypatch):
    repo = tmp_path / 'checkout'
    calls = []
    old_partial = repo / 'objects/pack/tmp_pack_previous'

    def fake_git(root, *args, **options):
        if args[0] == 'init':
            old_partial.parent.mkdir(parents=True)
            old_partial.write_bytes(b'old')
        if args[0] == 'cat-file':
            raise subject.GitCommandError('GIT_COMMAND_FAILED', 'cat-file')
        if args[0] == 'fetch':
            calls.append(options)
            (old_partial.parent / 'tmp_pack_current').write_bytes(b'partial')
            raise subject.GitCommandError('GIT_AUTHENTICATION_FAILED', 'fetch')
        return b''

    monkeypatch.setattr(subject, 'git', fake_git)
    with pytest.raises(subject.GitCommandError, match='GIT_AUTHENTICATION_FAILED'):
        subject.make_bundle(repo, 'owner/repo', 'a' * 40, 'private-token')
    assert .95 * subject.NETWORK_GIT_TIMEOUT < calls[0]['timeout_seconds'] <= subject.NETWORK_GIT_TIMEOUT
    assert old_partial.read_bytes() == b'old'
    assert not (old_partial.parent / 'tmp_pack_current').exists()


@pytest.mark.parametrize('cancel', [False, True])
def test_subprocess_is_reaped_on_deadline_or_permission_revocation(tmp_path, monkeypatch, cancel):
    script = tmp_path / 'fake-git'
    pidfile = tmp_path / 'pid'
    script.write_text('#!/bin/sh\necho $$ > ' + str(pidfile) + '\nexec /bin/sleep 20\n')
    script.chmod(0o700)
    monkeypatch.setattr(subject.shutil, 'which', lambda _: str(script))
    validations = []

    def validate():
        validations.append(True)
        if len(validations) == 2:
            raise PermissionError('revoked')

    expected = PermissionError if cancel else subject.GitCommandError
    with pytest.raises(expected, match='revoked' if cancel else 'GIT_TIMEOUT'):
        subject.git(tmp_path, 'fetch', network=True, timeout_seconds=3 if cancel else .2,
                    validate=validate if cancel else None)
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    if cancel:
        assert len(validations) == 2


def test_low_speed_error_is_retryable_without_leaking_diagnostic():
    code, retryable = subject.classify_git_failure(b'curl: Operation too slow. secret-url', network=True)
    assert (code, retryable) == ('GIT_TRANSFER_FAILED', True)
