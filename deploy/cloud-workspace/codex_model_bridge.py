"""Forward Codex's loopback Responses requests to its host-owned Unix socket."""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import socket


_MAX_BODY = 8 * 1024 * 1024


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=130)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class ResponsesHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        model = self.server.model
        valid_path = (self.path == "/v1/responses" if model is not None
                      else re.fullmatch(r"/[a-f0-9]{32}/v1/responses", self.path) is not None)
        if not valid_path:
            self.send_error(404)
            return
        self.connection.settimeout(15)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= _MAX_BODY or self.headers.get("Transfer-Encoding"):
                raise ValueError("Invalid request size")
            raw = self.rfile.read(size)
            payload = json.loads(raw)
            if len(raw) != size or not isinstance(payload, dict):
                raise ValueError("Invalid model request")
        except (OSError, ValueError):
            self.send_error(400)
            return
        if model is not None and payload.get("model") != model:
            self.send_error(403)
            return
        broker = UnixConnection(self.server.path)
        started = False
        try:
            broker.request("POST", self.path, body=raw, headers={
                "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            })
            with broker.getresponse() as response:
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                self.send_header("Connection", "close")
                self.end_headers()
                started = True
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (OSError, http.client.HTTPException):
            if not started:
                self.send_error(502)
        finally:
            broker.close()
            self.close_connection = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--model")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), ResponsesHandler) as server:
        server.path = args.socket
        server.model = args.model
        server.serve_forever()
