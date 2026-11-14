"""Operator TLS consumer: verified publication, reload acknowledgement and alerts.

Issuance/renewal belongs to Caddy, ACME or an enterprise CA. No account credentials,
Runtime imports, certificate verification bypass or remote command API.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time
import uuid


def command(argv):
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) for x in argv):
        raise ValueError('command must be a nonempty argv list')
    # Never emit command output: issuer hooks can contain deployment secrets.
    return subprocess.run(argv, check=True, capture_output=True, timeout=30).stdout


def metadata(path):
    info = ssl._ssl._test_decode_cert(str(path))
    pem = Path(path).read_text()
    first = pem[:pem.index('-----END CERTIFICATE-----') + len('-----END CERTIFICATE-----')]
    return {'sha256': hashlib.sha256(ssl.PEM_cert_to_DER_cert(first)).hexdigest(),
            'expires': ssl.cert_time_to_seconds(info['notAfter'])}


def served(endpoint):
    context = ssl.create_default_context(cafile=endpoint.get('ca_file'))
    with socket.create_connection((endpoint['host'], endpoint['port']), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname=endpoint['server_name']) as stream:
            info = stream.getpeercert()
            return {'sha256': hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest(),
                    'expires': ssl.cert_time_to_seconds(info['notAfter'])}


def validate(cert, key, endpoint, minimum):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    name = endpoint['server_name']
    try:
        ipaddress.ip_address(name)
        flag = '-verify_ip'
    except ValueError:
        flag = '-verify_hostname'
    args = ['openssl', 'verify', '-purpose', 'sslserver', flag, name,
            '-untrusted', str(cert)]
    if endpoint.get('ca_file'):
        args.extend(['-CAfile', endpoint['ca_file']])
    command(args + [str(cert)])
    result = metadata(cert)
    if result['expires'] - time.time() < minimum:
        raise ValueError('candidate has insufficient remaining validity')
    return result


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temporary.open('x') as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def point(root, target):
    link = root / ('.next-' + uuid.uuid4().hex)
    try:
        link.symlink_to(target)
        os.replace(link, root / 'current')
    finally:
        link.unlink(missing_ok=True)


def await_served(endpoint, expected, timeout):
    deadline = time.monotonic() + timeout
    while True:
        try:
            actual = served(endpoint)
            if actual['sha256'] == expected:
                return actual
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('served certificate did not acknowledge reload')
        time.sleep(.2)


def publish(item):
    root = Path(item['destination'])
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError('destination must be an existing owned directory')
    current = root / 'current'
    previous = None
    if current.is_symlink():
        resolved = current.resolve(strict=True)
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError('current must resolve inside destination')
        previous = os.readlink(current)
    elif current.exists():
        raise ValueError('current must be a managed symlink')
    version = root / ('version-' + uuid.uuid4().hex)
    version.mkdir(mode=0o700)
    uid, gid = item['uid'], item['gid']
    os.chown(version, uid, gid)
    cert, key = version / 'cert.pem', version / 'key.pem'
    try:
        # Copy before validating: an issuer may rotate files between reads.
        # Reject mismatched snapshots before changing the serving pointer.
        for source, target in [(item['source_cert'], cert), (item['source_key'], key)]:
            with target.open('xb') as stream:
                os.chmod(target, 0o600)
                stream.write(Path(source).read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.chown(target, uid, gid)
        expected = validate(cert, key, item['endpoint'], item.get('minimum_valid_seconds', 600))
        try:
            actual = served(item['endpoint'])
        except (OSError, ValueError):
            actual = None
        same_disk = previous is not None and metadata(current / 'cert.pem')['sha256'] == expected['sha256']
        if same_disk and actual and actual['sha256'] == expected['sha256']:
            return {**actual, 'action': 'unchanged'}
        # If a process died after publication but before reload, use the
        # already-published pair and still require fresh served acknowledgement.
        if not same_disk:
            point(root, version.name)
        try:
            command(item['preflight'])
            command(item['reload'])
            actual = await_served(item['endpoint'], expected['sha256'], item.get('reload_timeout_seconds', 20))
        except Exception:
            if not same_disk:
                if previous is None:
                    current.unlink()
                else:
                    point(root, previous)
                    command(item['preflight'])
                    command(item['reload'])
                    await_served(item['endpoint'], metadata(current / 'cert.pem')['sha256'], item.get('reload_timeout_seconds', 20))
            raise
        return {**actual, 'action': 'reloaded'}
    finally:
        # Retain published versions for explicit rollback; only discard this
        # invocation's unpublished staging pair, never issuer files or old data.
        if not current.is_symlink() or current.resolve() != version.resolve():
            cert.unlink(missing_ok=True)
            key.unlink(missing_ok=True)
            version.rmdir()


def check(item):
    try:
        if item.get('mode') == 'publish':
            result = publish(item)
        elif item.get('mode') == 'monitor':
            result = {**served(item['endpoint']), 'action': 'monitored'}
        else:
            raise ValueError('unknown certificate mode')
        remaining = result['expires'] - time.time()
        result['status'] = 'expiring' if remaining < item.get('warn_before_seconds', 86400) else 'ok'
        # CA expiry needs explicit trust migration, never automatic root replacement.
        for ca in item.get('watch_ca_files', []):
            if metadata(ca)['expires'] - time.time() < item.get('ca_warn_before_seconds', 2592000):
                result['status'] = 'ca_expiring'
        return {'id': item['id'], **result}
    except Exception as error:
        return {'id': item['id'], 'status': 'error', 'error_type': type(error).__name__}


def run(config):
    state = Path(config['state_dir'])
    if not state.is_absolute() or state.is_symlink() or not state.is_dir():
        raise ValueError('state_dir must be an existing private directory')
    items = config['certificates']
    names = [item['id'] for item in items]
    if not names or len(names) != len(set(names)) or any(not name.replace('-', '').replace('_', '').isalnum() for name in names):
        raise ValueError('unique simple certificate ids required')
    with (state / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = [check(item) for item in items]
        result = {'checked_at': time.time(), 'certificates': rows}
        atomic_json(state / 'status.json', result)
        metrics = []
        for row in rows:
            labels = '{certificate="' + row['id'] + '"}'
            metrics.extend(['code_platform_tls_last_check_seconds' + labels + ' ' + str(result['checked_at']),
                            'code_platform_tls_healthy' + labels + ' ' + str(int(row['status'] == 'ok')),
                            'code_platform_tls_expiry_seconds' + labels + ' ' + str(row.get('expires', 0))])
        pending = state / 'tls.prom.tmp'
        pending.write_text('\n'.join(metrics) + '\n')
        os.replace(pending, state / 'tls.prom')
        print(json.dumps(result), flush=True)
        return 0 if all(row['status'] == 'ok' for row in rows) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    try:
        raise SystemExit(run(json.loads(args.manifest.read_text())))
    except Exception as error:
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
