"""Distinguish an absent local Gateway from a live upstream authority error."""
import http.client
import json
import socket
import threading
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jiuwenswarm.channels.web.app_web import _SpaStaticHandler


@contextmanager
def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request(port):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    try:
        connection.request('GET', '/api/v1/auth/organization/status')
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), json.loads(response.read())
    finally:
        connection.close()


def test_absent_local_gateway_reports_local_failure(tmp_path):
    # Reserve an unused port without listening; no competing service can bind it.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        class Proxy(_SpaStaticHandler):
            api_target = f'http://127.0.0.1:{reservation.getsockname()[1]}'
        with serve(partial(Proxy, directory=str(tmp_path))) as port:
            status, headers, body = request(port)
    assert status == 502
    assert body['code'] == 'LOCAL_SERVICE_UNAVAILABLE'
    assert headers['Cache-Control'] == 'no-store'


def test_authority_unavailable_is_forwarded_unchanged(tmp_path):
    class Authority(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"code":"AUTHORITY_UNAVAILABLE"}'
            self.send_response(503)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    with serve(Authority) as upstream:
        class Proxy(_SpaStaticHandler):
            api_target = f'http://127.0.0.1:{upstream}'
        with serve(partial(Proxy, directory=str(tmp_path))) as port:
            status, _, body = request(port)
    assert status == 503
    assert body == {'code': 'AUTHORITY_UNAVAILABLE'}
