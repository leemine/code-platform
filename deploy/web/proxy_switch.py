"""Reversible two-role Web/TLS deployment switch; not a Gateway lifecycle owner.

The manifest supplies paths, immutable images and container names. Old containers
are retained stopped after success, and restored on failure. No business data or
volumes are deleted. This optional deployment utility has no Runtime dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import ssl
import subprocess
import time
import urllib.request
import uuid


def command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def inspect(name, run=command):
    try:
        return json.loads(run(['docker', 'inspect', name]))[0]
    except subprocess.CalledProcessError as error:
        # Only absence is optional; engine failures must not authorize replacement.
        if any(message in (error.stderr or '').lower() for message in ('no such object:', 'no such container:')):
            return None
        raise


def verify_health(config):
    context = ssl.create_default_context(cafile=config['ca_file'])
    deadline = time.monotonic() + config.get('timeout_seconds', 30)
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(config['url'], context=context, timeout=3) as response:
                body = json.load(response)
                if response.status == 200 and response.version == config['http_version'] and body.get('enabled') is True:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise RuntimeError('Deployment readiness failed')


def preflight(manifest, run=command):
    root = Path(manifest['root']).resolve(strict=True)
    names = manifest['names']
    label = manifest['owner_label']
    if len(names) != 2 or len(set(names)) != 2 or not label.get('key') or not label.get('value'):
        raise ValueError('Exactly two explicitly owned deployment roles are required')
    files = manifest['files']
    if not files:
        raise ValueError('Recovery and deployment file hashes are required')
    for path, digest in files.items():
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError('Deployment file is outside its owned root')
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != digest:
            raise ValueError('Deployment file digest differs')
    health = manifest['health']
    if health['ca_file'] not in files or not health['url'].startswith('https://127.0.0.1:'):
        raise ValueError('Readiness must use verified local TLS')
    ssl.create_default_context(cafile=health['ca_file'])
    desired = manifest['containers']
    if not desired or len({row['name'] for row in desired}) != len(desired):
        raise ValueError('Deployment roles must be unique')
    for row in desired:
        if row['name'] not in names or not row['image'].startswith('sha256:'):
            raise ValueError('Container name or immutable image is invalid')
        run(['docker', 'image', 'inspect', row['image']])
        for mount in row['mounts']:
            source = Path(mount['source']).resolve(strict=True)
            if not source.is_relative_to(root):
                raise ValueError('Mount is outside the owned deployment root')
            if source.is_file() and str(source) not in files:
                raise ValueError('Mounted file is not verified')
    old = {}
    for name in names:
        item = inspect(name, run)
        if item is None:
            continue
        if item['Config'].get('Labels', {}).get(label['key']) != label['value']:
            raise ValueError('Existing container is not owned by this deployment')
        if any(not Path(m['Source']).resolve().is_relative_to(root) for m in item['Mounts']):
            raise ValueError('Existing mount is outside the owned deployment root')
        old[name] = item
    return old


def create_args(row, owner, revision):
    args = ['docker', 'run', '-d', '--name', row['name'], '--label', f"{owner['key']}={owner['value']}",
            '--label', f'io.code-platform.web-release={revision}', '--network', 'host',
            '--user', row['user'], '--memory', row['memory'], '--cpus', str(row['cpus']),
            '--pids-limit', str(row['pids_limit']), '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--restart', row.get('restart', 'no')]
    if row.get('read_only'):
        args.append('--read-only')
    if row.get('tmpfs'):
        args.extend(['--tmpfs', row['tmpfs']])
    if row.get('log_driver'):
        args.extend(['--log-driver', row['log_driver']])
        for key, value in row.get('log_options', {}).items():
            args.extend(['--log-opt', f'{key}={value}'])
    for mount in row['mounts']:
        args.extend(['-v', f"{mount['source']}:{mount['target']}" + (':ro' if mount['readonly'] else '')])
    return args + ['--entrypoint', row['entrypoint'], row['image'], *row['args']]


def switch(manifest, run=command, health=verify_health):
    old = preflight(manifest, run)
    revision = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    desired = manifest['containers']
    if set(old) == {row['name'] for row in desired} and all(
        item['Config'].get('Labels', {}).get('io.code-platform.web-release') == revision
        and item['State']['Running'] for item in old.values()
    ):
        health(manifest['health'])
        return {'state': 'already_active', 'revision': revision, 'retained': {}}
    # Syntax checks run before any working container is stopped, in a short-lived
    # container with no network. The command is the same owned image/entrypoint.
    for row in desired:
        if row.get('preflight_args') is not None:
            args = create_args(row, manifest['owner_label'], revision)
            args[2:5] = ['--rm']
            args[args.index('--network') + 1] = 'none'
            args = args[:args.index('--restart')] + args[args.index('--restart') + 2:]
            args = args[:args.index(row['image']) + 1] + row['preflight_args']
            run(args)
    retained = {}
    attempted = []
    transaction = uuid.uuid4().hex[:12]
    try:
        for name, item in old.items():
            if inspect(name, run)['Id'] != item['Id']:
                raise RuntimeError('Deployment container changed after preflight')
            # Register before stop: a failed stop/rename must also restore it.
            retained[name] = {'id': item['Id'], 'backup': None, 'running': item['State']['Running']}
            run(['docker', 'stop', '-t', '5', name])
            backup = name + '-previous-' + transaction
            run(['docker', 'rename', name, backup])
            retained[name]['backup'] = backup
        for row in desired:
            attempted.append(row['name'])
            run(create_args(row, manifest['owner_label'], revision))
        health(manifest['health'])
    except BaseException as error:
        failures = []
        for name in reversed(attempted):
            try:
                item = inspect(name, run)
                if item is not None:
                    labels = item['Config'].get('Labels', {})
                    if labels.get('io.code-platform.web-release') != revision or labels.get(manifest['owner_label']['key']) != manifest['owner_label']['value']:
                        raise RuntimeError('Refusing to remove an unowned replacement')
                    run(['docker', 'rm', '-f', item['Id']])
            except Exception as cleanup_error:
                failures.append(str(cleanup_error))
        for name, item in retained.items():
            try:
                current = inspect(name, run)
                if current is None:
                    run(['docker', 'rename', item['id'], name])
                elif current['Id'] != item['id']:
                    raise RuntimeError('Original deployment name was claimed by another container')
                if item['running']:
                    run(['docker', 'start', item['id']])
            except Exception as restore_error:
                failures.append(str(restore_error))
        if failures:
            raise RuntimeError('Switch failed; restoration needs intervention: ' + '; '.join(failures)) from error
        raise RuntimeError('Switch failed; original containers restored') from error
    return {'state': 'active', 'revision': revision, 'retained': retained}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    print(json.dumps(switch(json.loads(args.manifest.read_text())), indent=2))
