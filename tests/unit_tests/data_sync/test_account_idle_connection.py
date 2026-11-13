"""Retire dead idle transports before a mutation without replaying the mutation."""
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from gateway.auth.account_transport import AccountHTTPPool


def test_peer_closed_idle_socket_is_not_reused_for_login():
    closed = threading.Event()
    requests = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            requests.append((self.path, body, self.client_address))
            self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers()
            self.wfile.write(b'{}'); self.wfile.flush()
            if self.path == '/first':
                time.sleep(.05)
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                closed.set()
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    pool = AccountHTTPPool(f'http://127.0.0.1:{server.server_port}', None)
    try:
        assert pool.request('POST','/first',b'{}',{},operation='login')[0] == 200
        assert closed.wait(2)
        assert pool.request('POST','/login',b'new-login',{},operation='login')[0] == 200
        assert [row[:2] for row in requests] == [('/first',b'{}'),('/login',b'new-login')]
        assert requests[0][2] != requests[1][2]
    finally:
        pool.close();server.shutdown();server.server_close();thread.join(3)


def test_tls_eof_retries_only_reads_without_relaxing_certificate_checks(monkeypatch):
    import ssl
    import pytest
    import gateway.auth.account_transport as transport

    for failure, retry_read, expected in [
        (ssl.SSLEOFError('peer closed'), True, 2),
        (ssl.SSLZeroReturnError('peer closed'), True, 2),
        (ssl.SSLEOFError('peer closed'), False, 1),
        (ssl.SSLCertVerificationError('untrusted'), True, 1),
        (ssl.SSLError('protocol failure'), True, 1),
    ]:
        contexts, requests = [], []
        class Connection:
            sock = None
            def __init__(self, *args, context, timeout):
                contexts.append(context)
            def request(self, verb, path, body, headers):
                requests.append((verb, path, body))
            def getresponse(self):
                if len(requests) == 1:
                    raise failure
                return self
            status = 200
            def read(self, limit): return b'{}'
            def getheaders(self): return []
            def close(self): pass
        monkeypatch.setattr(transport.http.client, 'HTTPSConnection', Connection)
        pool = AccountHTTPPool('https://cloud.test', None)
        try:
            if expected == 2:
                assert pool.request('GET', '/status', None, {}, operation='status', retry_read=retry_read)[0] == 200
            else:
                with pytest.raises(type(failure)):
                    pool.request('POST', '/login', b'once', {}, operation='login', retry_read=retry_read)
            assert len(requests) == expected
            assert all(context is pool.context for context in contexts)
            assert pool.context.verify_mode == ssl.CERT_REQUIRED
            assert pool.context.check_hostname is True
        finally:
            pool.close()
