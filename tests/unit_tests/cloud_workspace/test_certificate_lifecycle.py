"""Real local TLS rotation and failure injection; no Docker or external network."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('certificate_lifecycle', Path(__file__).resolve().parents[3] / 'deploy/tls/certificate_lifecycle.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def openssl(*args):
    subprocess.run(['openssl', *map(str, args)], check=True, capture_output=True)


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ca = self.root/'ca.pem'; self.ca_key = self.root/'ca.key'
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', self.ca_key, '-out', self.ca, '-days', '3', '-subj', '/CN=test-ca', '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        self.old = self.issue('old')
        self.new = self.issue('new')
        self.dest = self.root/'deployed'; self.dest.mkdir()
        initial = self.dest/'initial'; initial.mkdir()
        for src, name in zip(self.old, ['cert.pem', 'key.pem']):
            (initial/name).write_bytes(src.read_bytes())
        (self.dest/'current').symlink_to('initial')
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(*self.old)
        self.socket = socket.socket(); self.socket.bind(('127.0.0.1', 0)); self.socket.listen(); self.socket.settimeout(.1)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True); self.thread.start()
        self.addCleanup(self.close)
        self.endpoint = {'host':'127.0.0.1', 'port':self.socket.getsockname()[1], 'server_name':'127.0.0.1', 'ca_file':str(self.ca)}
        self.item = {'id':'test', 'mode':'publish', 'source_cert':str(self.new[0]), 'source_key':str(self.new[1]),
            'destination':str(self.dest), 'uid':os.getuid(), 'gid':os.getgid(), 'endpoint':self.endpoint,
            'preflight':['syntax'], 'reload':['reload'], 'reload_timeout_seconds':.3, 'warn_before_seconds':3600}
        self.real_command = m.command
        self.calls = []

    def issue(self, name, ip='127.0.0.1'):
        cert, key, csr = [self.root/(name+ext) for ext in ['.pem','.key','.csr']]
        ext = self.root/(name+'.ext'); ext.write_text('subjectAltName=IP:'+ip+'\nbasicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\n')
        openssl('req','-new','-newkey','rsa:2048','-nodes','-keyout',key,'-out',csr,'-subj','/CN='+name)
        openssl('x509','-req','-in',csr,'-CA',self.ca,'-CAkey',self.ca_key,'-set_serial',str(len(list(self.root.iterdir()))),'-days','2','-extfile',ext,'-out',cert)
        return cert,key

    def serve(self):
        while not self.stop.is_set():
            try:raw,_ = self.socket.accept()
            except (TimeoutError, OSError):continue
            try:
                with self.context.wrap_socket(raw, server_side=True):pass
            except (ssl.SSLError, OSError):raw.close()

    def close(self):
        self.stop.set(); self.thread.join(2); self.socket.close()

    def command(self, args):
        if args == ['syntax']:
            self.calls.append('syntax'); return b''
        if args == ['reload']:
            self.calls.append('reload')
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(self.dest/'current/cert.pem', self.dest/'current/key.pem')
            self.context = context
            return b''
        return self.real_command(args)

    def test_rotation_verified_and_idempotent(self):
        with patch.object(m,'command',self.command):
            r = m.check(self.item)
            self.assertEqual(r['status'],'ok'); self.assertEqual(r['action'],'reloaded')
            self.assertEqual(r['sha256'],m.metadata(self.new[0])['sha256'])
            self.assertEqual(m.check(self.item)['action'],'unchanged')
        self.assertEqual(self.calls,['syntax','reload'])
        self.assertEqual((self.dest/'current/key.pem').stat().st_mode & 0o777,0o600)

    def test_bad_key_does_not_publish_or_reload(self):
        self.item['source_key']=str(self.old[1])
        with patch.object(m,'command',self.command):self.assertEqual(m.check(self.item)['status'],'error')
        self.assertEqual(os.readlink(self.dest/'current'),'initial'); self.assertEqual(self.calls,[])

    def test_missing_issuer_file_cleans_unpublished_staging(self):
        self.item['source_key']=str(self.root/'missing.key')
        with patch.object(m,'command',self.command):self.assertEqual(m.check(self.item)['status'],'error')
        self.assertEqual(os.readlink(self.dest/'current'),'initial')
        self.assertEqual(list(self.dest.glob('version-*')),[])

    def test_wrong_identity_does_not_publish(self):
        self.item['source_cert'], self.item['source_key']=map(str,self.issue('wrong','127.0.0.2'))
        with patch.object(m,'command',self.command):self.assertEqual(m.check(self.item)['status'],'error')
        self.assertEqual(os.readlink(self.dest/'current'),'initial')

    def test_reload_failure_restores_previous_pair(self):
        failed = False
        def command(args):
            nonlocal failed
            if args==['reload'] and not failed:
                failed=True; raise RuntimeError('reload rejected')
            return self.command(args)
        with patch.object(m,'command',command):self.assertEqual(m.check(self.item)['status'],'error')
        self.assertEqual(os.readlink(self.dest/'current'),'initial')
        self.assertEqual(m.served(self.endpoint)['sha256'],m.metadata(self.old[0])['sha256'])

    def test_command_success_without_loading_is_failure(self):
        def command(args):
            if args==['reload']:return b''
            return self.command(args)
        with patch.object(m,'command',command):self.assertEqual(m.check(self.item)['status'],'error')
        self.assertEqual(os.readlink(self.dest/'current'),'initial')

    def test_recover_publication_before_crash(self):
        for src,name in zip(self.new,['cert.pem','key.pem']):
            (self.dest/'current'/name).write_bytes(src.read_bytes())
        with patch.object(m,'command',self.command):self.assertEqual(m.check(self.item)['action'],'reloaded')
        self.assertEqual(m.served(self.endpoint)['sha256'],m.metadata(self.new[0])['sha256'])

    def test_expiry_alert_ca_alert_and_status_metrics(self):
        item={'id':'watched','mode':'monitor','endpoint':self.endpoint,'warn_before_seconds':4*86400}
        state=self.root/'state';state.mkdir()
        self.assertEqual(m.run({'state_dir':str(state),'certificates':[item]}),1)
        self.assertEqual(json.loads((state/'status.json').read_text())['certificates'][0]['status'],'expiring')
        self.assertIn('code_platform_tls_healthy{certificate="watched"} 0',(state/'tls.prom').read_text())
        item['warn_before_seconds']=3600;item['watch_ca_files']=[str(self.ca)]
        self.assertEqual(m.check(item)['status'],'ca_expiring')

    def test_untrusted_served_certificate_fails_closed(self):
        self.endpoint['ca_file']=None
        self.assertEqual(m.check({'id':'watched','mode':'monitor','endpoint':self.endpoint})['status'],'error')

    def test_insufficient_validity_keeps_existing(self):
        self.item['minimum_valid_seconds']=4*86400
        with patch.object(m,'command',self.command):self.assertEqual(m.check(self.item)['status'],'error')
        self.assertEqual(os.readlink(self.dest/'current'),'initial')


if __name__=='__main__':unittest.main()
