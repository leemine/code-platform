"""Exercise draft asset transfer without network or personal configuration."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def transfer_module():
    script = Path(__file__).resolve().parents[2] / '.github' / 'scripts' / 'transfer-release-assets.py'
    spec = importlib.util.spec_from_file_location('release_asset_transfer', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def scenario(transfer_module, monkeypatch):
    product = 'a' * 40
    source_sha = 'b' * 40
    payload = b'installer fixture\n'
    asset = {'run_id': 71, 'source_sha': source_sha, 'artifact': 'arbitrary-build',
             'file': 'platform-package.exe', 'sha256': hashlib.sha256(payload).hexdigest(),
             'bytes': len(payload)}
    manifest = {'tag': 'v9.8.7-test', 'target_commit': product, 'assets': [asset]}
    release = {'draft': True, 'tag_name': manifest['tag'], 'target_commitish': product, 'assets': []}
    state = {'repo': 'example/another-repo', 'manifest': manifest, 'release': release,
             'run': {'conclusion': 'success', 'head_sha': source_sha}, 'uploads': [],
             'source': {'source_sha': source_sha, 'product_base_sha': product, 'profile': 'external'},
             'payload': payload, 'downloads': 0, 'break_server_digest': False,
             'publish_after_download': False}

    def api(repo, route):
        assert repo == state['repo']
        if route == 'releases/93':
            return copy.deepcopy(release)
        assert route == 'actions/runs/71'
        return state['run']

    def command(args, check):
        assert check
        if args[:3] == ['gh', 'run', 'download']:
            assert args[3:8] == ['71', '--repo', state['repo'], '--name', 'arbitrary-build']
            directory = Path(args[-1])
            directory.mkdir(parents=True)
            (directory / 'source.json').write_text(json.dumps(state['source']))
            (directory / asset['file']).write_bytes(state['payload'])
            state['downloads'] += 1
            if state['publish_after_download']:
                release['draft'] = False
        else:
            assert args[:6] == ['gh', 'release', 'upload', manifest['tag'], '--repo', state['repo']]
            file = Path(args[6])
            assert file.read_bytes() == state['payload']
            state['uploads'].append(file.name)
            release['assets'].append({'name': file.name, 'size': file.stat().st_size,
                                      'state': 'uploaded', 'digest': 'sha256:' + (
                                          '0' * 64 if state['break_server_digest'] else asset['sha256'])})

    monkeypatch.setattr(transfer_module, 'gh_json', api)
    monkeypatch.setattr(transfer_module.subprocess, 'run', command)
    return state


def test_transfer_uses_manifest_repository_tag_and_ci_source(transfer_module, scenario, tmp_path):
    transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert scenario['uploads'] == ['platform-package.exe']
    assert scenario['release']['draft'] is True


def test_matching_existing_asset_is_not_overwritten(transfer_module, scenario, tmp_path):
    transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path / 'first')
    transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path / 'retry')
    assert len(scenario['uploads']) == 1


@pytest.mark.parametrize('field,value', [('draft', False), ('tag_name', 'other-tag'),
                                        ('target_commitish', 'c' * 40)])
def test_wrong_release_stops_before_download(transfer_module, scenario, tmp_path, field, value):
    scenario['release'][field] = value
    with pytest.raises(ValueError, match='matching draft'):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert scenario['downloads'] == 0 and not scenario['uploads']


@pytest.mark.parametrize('field,value', [('conclusion', 'failure'), ('head_sha', 'c' * 40)])
def test_wrong_run_stops_before_download(transfer_module, scenario, tmp_path, field, value):
    scenario['run'][field] = value
    with pytest.raises(ValueError, match='successful at the declared SHA'):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert scenario['downloads'] == 0 and not scenario['uploads']


@pytest.mark.parametrize('field,value', [('source_sha', 'c' * 40), ('product_base_sha', 'c' * 40),
                                        ('profile', 'native')])
def test_wrong_provenance_is_not_uploaded(transfer_module, scenario, tmp_path, field, value):
    scenario['source'][field] = value
    with pytest.raises(ValueError, match='provenance'):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert not scenario['uploads']


@pytest.mark.parametrize('payload,error', [(b'truncated', 'size'),
                                         (b'corrupted fixture\n', 'SHA256')])
def test_corrupted_file_is_not_uploaded(transfer_module, scenario, tmp_path, payload, error):
    scenario['payload'] = payload
    with pytest.raises(ValueError, match=error):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert not scenario['uploads']


def test_conflicting_asset_is_not_overwritten(transfer_module, scenario, tmp_path):
    scenario['release']['assets'] = [{'name': 'platform-package.exe', 'state': 'uploaded',
                                     'size': 1, 'digest': 'sha256:' + '0' * 64}]
    with pytest.raises(ValueError, match='Existing release asset'):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert scenario['downloads'] == 0 and not scenario['uploads']


def test_server_digest_is_verified(transfer_module, scenario, tmp_path):
    scenario['break_server_digest'] = True
    with pytest.raises(ValueError, match='Existing release asset'):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)


def test_draft_is_rechecked_before_upload(transfer_module, scenario, tmp_path):
    scenario['publish_after_download'] = True
    with pytest.raises(ValueError, match='matching draft'):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert not scenario['uploads']


def test_all_artifacts_are_checked_before_any_upload(transfer_module, scenario, tmp_path):
    second = copy.deepcopy(scenario['manifest']['assets'][0])
    second['file'] = 'missing-package.dmg'
    scenario['manifest']['assets'].append(second)
    with pytest.raises(ValueError, match='exactly one'):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert not scenario['uploads']


@pytest.mark.parametrize('field,value', [('file', '../unsafe.exe'), ('file', 'dir\\unsafe.exe'),
                                        ('sha256', ''), ('bytes', 0), ('run_id', True),
                                        ('source_sha', 'main')])
def test_invalid_manifest_has_no_external_effects(transfer_module, scenario, tmp_path, field, value):
    scenario['manifest']['assets'][0][field] = value
    with pytest.raises(ValueError):
        transfer_module.transfer(scenario['repo'], '93', scenario['manifest'], tmp_path)
    assert scenario['downloads'] == 0 and not scenario['uploads']
