"""Transfer declared, verified Actions artifacts to an existing draft release."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def gh_json(repo, route):
    return json.loads(subprocess.check_output(
        ['gh', 'api', f'repos/{repo}/{route}'], text=True,
    ))


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError('Release manifest must be an object')
    tag = manifest.get('tag')
    if not isinstance(tag, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', tag):
        raise ValueError('A release tag is required')
    if not re.fullmatch(r'[0-9a-f]{40}', str(manifest.get('target_commit', ''))):
        raise ValueError('target_commit must be a full commit SHA')
    assets = manifest.get('assets')
    if not isinstance(assets, list) or not assets:
        raise ValueError('At least one artifact asset is required')
    names = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError('Each asset must be an object')
        if type(asset.get('run_id')) is not int or asset['run_id'] <= 0:
            raise ValueError('run_id must be a positive integer')
        if not re.fullmatch(r'[0-9a-f]{40}', str(asset.get('source_sha', ''))):
            raise ValueError('source_sha must be a full commit SHA')
        if not isinstance(asset.get('artifact'), str) or not asset['artifact'].strip():
            raise ValueError('An exact artifact name is required')
        name = asset.get('file')
        if (not isinstance(name, str) or not name or name in {'.', '..'}
                or '/' in name or '\\' in name or any(ord(c) < 32 for c in name)):
            raise ValueError('file must be a single asset filename')
        if name in names:
            raise ValueError('Duplicate release asset filename')
        names.add(name)
        if not re.fullmatch(r'[0-9a-f]{64}', str(asset.get('sha256', ''))):
            raise ValueError('An expected SHA256 is required')
        if type(asset.get('bytes')) is not int or asset['bytes'] <= 0:
            raise ValueError('bytes must be a positive integer')


def check_release(repo, release_id, manifest):
    release = gh_json(repo, f'releases/{release_id}')
    if (not release.get('draft') or release.get('tag_name') != manifest['tag']
            or release.get('target_commitish') != manifest['target_commit']):
        raise ValueError('Release must remain a matching draft with an explicit target SHA')
    return release


def check_existing(release, asset):
    existing = [item for item in release['assets'] if item['name'] == asset['file']]
    if not existing:
        return False
    if (len(existing) != 1 or existing[0].get('state') != 'uploaded'
            or existing[0].get('digest') != 'sha256:' + asset['sha256']
            or existing[0].get('size') != asset['bytes']):
        raise ValueError('Existing release asset does not match the manifest')
    return True


def transfer(repo, release_id, manifest, root):
    validate_manifest(manifest)
    if not re.fullmatch(r'[1-9][0-9]*', str(release_id)):
        raise ValueError('An existing numeric draft release ID is required')
    release = check_release(repo, release_id, manifest)
    for asset in manifest['assets']:
        check_existing(release, asset)
    verified = []
    # Validate every downloaded input before writing any release asset.
    for index, asset in enumerate(manifest['assets']):
        run = gh_json(repo, f"actions/runs/{asset['run_id']}")
        if run.get('conclusion') != 'success' or run.get('head_sha') != asset['source_sha']:
            raise ValueError('Artifact source run must be successful at the declared SHA')
        directory = root / str(index)
        subprocess.run(['gh', 'run', 'download', str(asset['run_id']), '--repo', repo,
                        '--name', asset['artifact'], '--dir', str(directory)], check=True)
        sources = list(directory.rglob('source.json'))
        files = [path for path in directory.rglob('*') if path.name == asset['file']]
        if len(sources) != 1 or len(files) != 1:
            raise ValueError('Artifact must contain exactly one source.json and declared file')
        source = json.loads(sources[0].read_text(encoding='utf-8-sig'))
        if (source.get('source_sha') != asset['source_sha'] or source.get('profile') != 'external'
                or source.get('product_base_sha', source.get('source_sha')) != manifest['target_commit']):
            raise ValueError('Artifact provenance does not match the declared product source')
        file = files[0]
        if file.is_symlink() or not file.is_file() or file.stat().st_size != asset['bytes']:
            raise ValueError('Artifact file size or type does not match')
        digest = hashlib.sha256()
        with file.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != asset['sha256']:
            raise ValueError('Artifact SHA256 does not match')
        verified.append((asset, file))
    for asset, file in verified:
        release = check_release(repo, release_id, manifest)
        if not check_existing(release, asset):
            subprocess.run(['gh', 'release', 'upload', manifest['tag'], '--repo', repo,
                            str(file)], check=True)
        release = check_release(repo, release_id, manifest)
        if not check_existing(release, asset):
            raise ValueError('Uploaded asset is missing from the draft')
        print(json.dumps({'asset': asset['file'], 'bytes': asset['bytes'],
                          'sha256': asset['sha256'], 'source_run': asset['run_id']}))
    print('Verified assets transferred; draft publication remains a separate step.')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='release-assets-') as temporary:
        transfer(os.environ['GH_REPO'], os.environ['RELEASE_ID'],
                 json.loads(os.environ['RELEASE_MANIFEST']), Path(temporary))
