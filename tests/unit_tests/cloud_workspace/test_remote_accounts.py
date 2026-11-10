import json

import pytest

from gateway.auth.remote_accounts import RemoteAccounts, AccountAuthorityUnavailable


def backend(tmp_path):
    p = tmp_path / 'authority.json'
    p.write_text(json.dumps({'url': 'https://account.example.invalid', 'ca': None}))
    p.chmod(0o600)
    return RemoteAccounts(p, 'same-authority')


def test_remote_identity_reuses_authoritative_subject_and_does_not_copy_passwords(tmp_path, monkeypatch):
    api = backend(tmp_path)
    calls = []
    def request(path, cfg, method, values, token):
        calls.append((method, token))
        return 200, json.dumps({'user_id': 'original-subject', 'authority': 'same-authority', 'username': 'existing'}).encode()
    monkeypatch.setattr('gateway.auth.remote_accounts.authority_post', request)
    assert api.session('existing-cookie')['user_id'] == 'original-subject'
    assert calls == [('session', 'existing-cookie')]
    assert sorted(p.name for p in tmp_path.iterdir()) == ['authority.json']


def test_remote_authority_failure_has_no_local_identity_fallback(tmp_path, monkeypatch):
    api = backend(tmp_path)
    monkeypatch.setattr('gateway.auth.remote_accounts.authority_post', lambda *a: (503, b'{}'))
    with pytest.raises(AccountAuthorityUnavailable):
        api.session('cookie')
    monkeypatch.setattr('gateway.auth.remote_accounts.authority_post', lambda *a: (200, b'{"user_id":"old","authority":"changed"}'))
    with pytest.raises(PermissionError):
        api.session('cookie')
