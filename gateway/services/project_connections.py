"""Private account-scoped repository credentials and bounded HTTPS requests."""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
import httpx
import portalocker
from jiuwenswarm.common.auth.session_store import decrypt_json, encrypt_json
from gateway.services.project_identity import ProjectIdentity as TrustedIdentity


class RepositoryError(ValueError):
    """Only fixed provider error codes cross the public transport."""


class RepositoryConnections:
    provider = ''
    fingerprint = ''
    api_origin = ''
    api_headers = {}
    error_type = RepositoryError

    @classmethod
    def error(cls, suffix):
        return cls.error_type(cls.provider.upper() + '_' + suffix)

    def __init__(self, root, *, transport=None, clock=time.time):
        self.clock, self.transport = clock, transport
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / 'connections.sqlite3'
        for path in (self.root, self.path):
            if path.is_symlink() or path.resolve() != path.absolute():
                raise self.error('PRIVATE_STORAGE_REQUIRED')
            if path.exists() and os.name == 'posix':
                info = path.stat()
                if info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise self.error('PRIVATE_STORAGE_REQUIRED')
        self.lease = portalocker.Lock(str(self.root / 'service.lock'), timeout=0)
        self.lease.acquire()
        self.closed = False
        try:
            self.path.touch(mode=0o600, exist_ok=True)
            self.capacity, self.lock = threading.BoundedSemaphore(4), threading.RLock()
            with self.db() as db:
                db.execute('CREATE TABLE IF NOT EXISTS configuration (fingerprint TEXT PRIMARY KEY)')
                previous = db.execute('SELECT fingerprint FROM configuration').fetchone()
                if previous and previous['fingerprint'] != self.fingerprint:
                    raise self.error('CONFIGURATION_CHANGED_USE_SEPARATE_STORAGE')
                db.execute('INSERT OR IGNORE INTO configuration VALUES (?)', (self.fingerprint,))
                db.execute('CREATE TABLE IF NOT EXISTS connections (scope TEXT PRIMARY KEY, generation TEXT NOT NULL, body TEXT NOT NULL)')
        except Exception:
            self.lease.release()
            raise

    @contextmanager
    def db(self):
        try:
            db = sqlite3.connect(self.path, timeout=3)
        except sqlite3.Error:
            raise self.error('STORAGE_UNAVAILABLE') from None
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        except sqlite3.Error:
            raise self.error('STORAGE_UNAVAILABLE') from None
        finally:
            db.close()

    @classmethod
    def decode(cls, raw):
        try:
            value = decrypt_json(raw)
            if not isinstance(value, dict):
                raise ValueError('invalid record')
            return value
        except (ValueError, KeyError, TypeError):
            raise cls.error('STORAGE_UNAVAILABLE') from None

    @classmethod
    def scope(cls, identity, target):
        if not isinstance(identity, TrustedIdentity) or not isinstance(target, str) or not 1 <= len(target) <= 128:
            raise cls.error('INVALID_SCOPE')
        return hashlib.sha256(json.dumps([identity.authority, identity.subject_id, identity.actor_id, target]).encode()).hexdigest()

    def read(self, scope):
        with self.db() as db:
            row = db.execute('SELECT * FROM connections WHERE scope=?', (scope,)).fetchone()
        return (row['generation'], self.decode(row['body'])) if row else ('', {})

    def write(self, scope, generation, body):
        with self.db() as db:
            result = db.execute('UPDATE connections SET body=? WHERE scope=? AND generation=?',
                                (encrypt_json(body), scope, generation))
            if result.rowcount != 1:
                raise self.error('CONNECTION_CHANGED')

    @contextmanager
    def network_slot(self):
        if not self.capacity.acquire(blocking=False):
            raise self.error('BUSY')
        try:
            yield
        finally:
            self.capacity.release()

    def request(self, method, path, *, token=None):
        # Every endpoint is constructed internally; never follow a Link/Location URL.
        url = self.api_origin + path
        headers = {'Accept': 'application/json', **self.api_headers}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        try:
            transport = self.transport
            if transport is None:
                # Retry a failed TCP/TLS connection before sending the request.
                transport = httpx.HTTPTransport(retries=1, trust_env=False)
            timeout = httpx.Timeout(12, connect=6)
            with httpx.Client(transport=transport, timeout=timeout, follow_redirects=False, trust_env=False) as client:
                with client.stream(method, url, headers=headers) as response:
                    if response.status_code == 429 or (response.status_code == 403 and (
                            response.headers.get('x-ratelimit-remaining') == '0'
                            or response.headers.get('retry-after') is not None)):
                        raise self.error('RATE_LIMITED')
                    if response.status_code in (401, 403, 404):
                        raise self.error('ACCESS_DENIED')
                    if response.status_code != 200:
                        raise self.error('UPSTREAM_UNAVAILABLE')
                    raw = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_bytes():
                        if time.monotonic() - started > 20:
                            raise self.error('UPSTREAM_UNAVAILABLE')
                        raw.extend(chunk)
                        if len(raw) > 2 * 1024 * 1024:
                            raise self.error('RESPONSE_TOO_LARGE')
            value = json.loads(raw)
            if isinstance(value, dict) and value.get('error'):
                raise self.error('AUTHORIZATION_FAILED')
            return value
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise self.error('UPSTREAM_UNAVAILABLE') from None
        except (httpx.HTTPError, json.JSONDecodeError, UnicodeError):
            raise self.error('UPSTREAM_UNAVAILABLE') from None

