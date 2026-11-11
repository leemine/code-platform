"""Deployment failure contracts: no real Docker, network, account or volume writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[3] / 'deploy/web/proxy_switch.py'
spec = importlib.util.spec_from_file_location('proxy_switch', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Engine:
    def __init__(self):
        self.calls = []
        self.items = {name: {'Id': 'old-' + name, 'State': {'Running': True},
            'Config': {'Labels': {'test-owner': 'task'}}, 'Mounts': []} for name in ['web', 'edge']}
        self.fail = None
        self.created = 0
        self.absent = 'Error: No such object: '

    def run(self, args):
        self.calls.append(args)
        if args[:3] == ['docker', 'image', 'inspect']:
            return '[]'
        name = args[-1]
        key = next((key for key, row in self.items.items() if row['Id'] == name), name)
        operation = args[1]
        if operation == 'inspect':
            if key not in self.items:
                raise subprocess.CalledProcessError(1, args, stderr=self.absent + name)
            return json.dumps([self.items[key]])
        if operation == 'stop':
            self.items[key]['State']['Running'] = False
            if self.fail == 'stop':
                self.fail = None
                raise RuntimeError('injected stop failure')
        elif operation == 'rename':
            key = next((key for key, row in self.items.items() if row['Id'] == args[2]), args[2])
            self.items[args[3]] = self.items.pop(key)
            if self.fail == 'rename':
                self.fail = None
                raise RuntimeError('injected lost rename response')
        elif operation == 'start':
            self.items[key]['State']['Running'] = True
        elif operation == 'rm':
            del self.items[key]
        elif operation == 'run':
            if '--rm' in args:
                assert '--name' not in args and args[args.index('--network') + 1] == 'none'
                assert 'test-owner=task' in args
                if self.fail == 'syntax':
                    raise RuntimeError('invalid proxy configuration')
                return ''
            name = args[args.index('--name') + 1]
            labels = dict(value.split('=', 1) for i, value in enumerate(args) if i and args[i-1] == '--label')
            self.created += 1
            self.items[name] = {'Id': f'new-{self.created}', 'State': {'Running': True}, 'Config': {'Labels': labels}, 'Mounts': []}
            if self.fail == name:
                self.fail = None
                raise RuntimeError('injected response loss after creation')
            return self.items[name]['Id']
        return ''


class ProxySwitchTest(unittest.TestCase):
    def setUp(self):
        tls = patch.object(module.ssl, 'create_default_context', return_value=object())
        self.tls = tls.start()
        self.addCleanup(tls.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        cert = root/'cert.pem'; cert.write_text('synthetic public certificate')
        self.manifest = {'root': str(root), 'names': ['web', 'edge'], 'owner_label': {'key': 'test-owner', 'value': 'task'},
            'files': {str(cert): hashlib.sha256(cert.read_bytes()).hexdigest()},
            'health': {'ca_file': str(cert), 'url': 'https://127.0.0.1:28803/status', 'http_version': 11},
            'containers': [{'name': name, 'image': 'sha256:' + 'a'*64, 'user': '1000:1000', 'memory': '128m',
                'cpus': 1, 'pids_limit': 32, 'entrypoint': 'test', 'args': [], 'mounts': [],
                **({'preflight_args': ['-t']} if name == 'edge' else {})} for name in ['web', 'edge']]}
        self.engine = Engine()

    def restored(self):
        self.assertEqual(set(self.engine.items), {'web', 'edge'})
        for name in ['web', 'edge']:
            self.assertEqual(self.engine.items[name]['Id'], 'old-' + name)
            self.assertTrue(self.engine.items[name]['State']['Running'])

    def test_missing_material_fails_before_stopping(self):
        Path(next(iter(self.manifest['files']))).unlink()
        with self.assertRaises(FileNotFoundError):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.assertFalse(self.engine.calls)
        self.restored()

    def test_bad_hash_fails_before_stopping(self):
        self.manifest['files'][next(iter(self.manifest['files']))] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'digest'):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.restored()

    def test_unowned_container_is_not_stopped(self):
        self.engine.items['edge']['Config']['Labels'] = {}
        with self.assertRaisesRegex(ValueError, 'not owned'):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.assertFalse(any(call[1] == 'stop' for call in self.engine.calls))

    def test_lost_create_response_compensates_only_replacements(self):
        self.engine.fail = 'edge'
        with self.assertRaisesRegex(RuntimeError, 'original containers restored'):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.restored()

    def test_health_failure_restores_original_ids(self):
        def failed(config):
            raise RuntimeError('health timeout')
        with self.assertRaisesRegex(RuntimeError, 'original containers restored'):
            module.switch(self.manifest, self.engine.run, failed)
        self.restored()

    def test_stop_failure_restores_stopped_container(self):
        self.engine.fail = 'stop'
        with self.assertRaisesRegex(RuntimeError, 'original containers restored'):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.restored()

    def test_container_absence_variant_restores_original_ids(self):
        self.engine.absent = 'Error response from daemon: No such container: '
        self.engine.fail = 'edge'
        with self.assertRaisesRegex(RuntimeError, 'original containers restored'):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.restored()

    def test_remote_lowercase_absence_restores_original_ids(self):
        self.engine.absent = 'error: no such object: '
        self.engine.fail = 'edge'
        with self.assertRaisesRegex(RuntimeError, 'original containers restored'):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.restored()

    def test_engine_unavailable_is_not_treated_as_absence(self):
        def unavailable(args):
            raise subprocess.CalledProcessError(1, args, stderr='Cannot connect to the Docker daemon')
        with self.assertRaises(subprocess.CalledProcessError):
            module.inspect('edge', unavailable)

    def test_lost_rename_response_restores_original_names(self):
        self.engine.fail = 'rename'
        with self.assertRaisesRegex(RuntimeError, 'original containers restored'):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.restored()

    def test_proxy_syntax_failure_preserves_running_containers(self):
        self.engine.fail = 'syntax'
        with self.assertRaisesRegex(RuntimeError, 'invalid proxy'):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.restored()

    def test_invalid_ca_fails_before_stop(self):
        self.tls.side_effect = module.ssl.SSLError('invalid CA')
        with self.assertRaises(module.ssl.SSLError):
            module.switch(self.manifest, self.engine.run, lambda config: None)
        self.restored()
        self.assertFalse(any(call[1] == 'stop' for call in self.engine.calls))

    def test_success_retains_originals_and_repeated_apply_is_noop(self):
        result = module.switch(self.manifest, self.engine.run, lambda config: None)
        self.assertEqual(result['state'], 'active')
        for name, retained in result['retained'].items():
            self.assertEqual(self.engine.items[retained['backup']]['Id'], 'old-' + name)
            self.assertFalse(self.engine.items[retained['backup']]['State']['Running'])
        count = self.engine.created
        result = module.switch(self.manifest, self.engine.run, lambda config: None)
        self.assertEqual(result['state'], 'already_active')
        self.assertEqual(self.engine.created, count)

    def test_direct_mode_retains_edge_for_compensation(self):
        self.manifest['containers'] = self.manifest['containers'][:1]
        result = module.switch(self.manifest, self.engine.run, lambda config: None)
        self.assertNotIn('edge', self.engine.items)
        self.assertIn('edge', result['retained'])


if __name__ == '__main__':
    unittest.main()
