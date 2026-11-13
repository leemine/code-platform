"""Slow cloud calls survive the ordinary HTTP timeout without retrying writes."""
import http.client
import threading
import time
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jiuwenswarm.channels.web.app_web import _SpaStaticHandler


@contextmanager
def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield server.server_port
    finally:
        server.shutdown(); server.server_close(); thread.join(5)


def test_cloud_deadline_covers_slow_response_and_does_not_replay_write(tmp_path):
    calls = []
    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            time.sleep(.3)
            try:
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"created":true}')
            except BrokenPipeError: pass
        def log_message(self, *args): pass
    with serve(Upstream) as upstream:
        class Proxy(_SpaStaticHandler):
            api_target = f'http://127.0.0.1:{upstream}'
            _HTTP_PROXY_TIMEOUT = .1
            _CLOUD_WORKSPACE_TIMEOUT = 1
            def log_message(self, *args): pass
        with serve(partial(Proxy, directory=str(tmp_path))) as proxy:
            for path, expected in [('/api/v1/ordinary', 502), ('/api/v1/data-sync/workspace', 200)]:
                client = http.client.HTTPConnection('127.0.0.1', proxy, timeout=3)
                client.request('POST', path, '{}', {'Content-Type': 'application/json'})
                response = client.getresponse()
                assert response.status == expected
                response.read(); client.close()
    assert calls == ['/api/v1/ordinary', '/api/v1/data-sync/workspace']
