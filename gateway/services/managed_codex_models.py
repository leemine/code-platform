"""Serve a single authorized Responses model to a Codex generation."""
from __future__ import annotations

from contextlib import ExitStack
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socket
from socketserver import ThreadingMixIn
from threading import Thread
from urllib.parse import urlsplit

from gateway.common.managed_codex import EFFECTIVE_CONTEXT_PERCENT, MAX_FRAME_BYTES, ManagedModel, model_endpoint
from gateway.common.security.service_auth import canonical


CATALOG_FILENAME = "model-catalog.json"


def native_model_catalog(name: str, context_window: int) -> bytes:
    # Codex caps the thread override at the catalog maximum. Keep custom model
    # capabilities conservative and leave the upstream connection in the broker.
    return canonical({"models": [{
        "slug": name,
        "display_name": name,
        "description": None,
        "supported_reasoning_levels": [],
        "shell_type": "unified_exec",
        "visibility": "none",
        "supported_in_api": True,
        "priority": 99,
        "model_messages": {
            "instructions_template": "You are a coding assistant. Follow the user's instructions and configured permissions.",
        },
        "availability_nux": None,
        "upgrade": None,
        "include_apps_usage_instructions": False,
        "support_verbosity": False,
        "default_verbosity": None,
        "apply_patch_tool_type": None,
        "truncation_policy": {"mode": "bytes", "limit": 10000},
        "context_window": context_window,
        "max_context_window": context_window,
        "effective_context_window_percent": EFFECTIVE_CONTEXT_PERCENT,
        "experimental_supported_tools": [],
    }]})


class _Responses(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_args):
        pass

    def do_POST(self):
        if self.path != "/v1/responses":
            self.send_error(404)
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("chunked requests are unsupported")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_FRAME_BYTES:
                raise ValueError("model request size outside limit")
            raw = self.rfile.read(size)
            payload = json.loads(raw)
            if len(raw) != size or not isinstance(payload, dict):
                raise ValueError("invalid model request")
        except (OSError, ValueError):
            self.send_error(400)
            return
        model = self.server.model
        if payload.get("model") != model.name:
            self.send_error(403)
            return
        endpoint = urlsplit(model.endpoint)
        client = http.client.HTTPSConnection(endpoint.hostname, endpoint.port, timeout=125)
        started = False
        try:
            client.request("POST", endpoint.path + "/responses", body=raw, headers={
                "Authorization": "Bearer " + model.key,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            })
            with client.getresponse() as response:
                if not 200 <= response.status < 300:
                    self.send_error(502)
                    return
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
            client.close()
            self.close_connection = True


class _UnixHTTPServer(ThreadingMixIn, HTTPServer):
    address_family = socket.AF_UNIX
    daemon_threads = True

    def server_bind(self):
        self.socket.bind(self.server_address)


class CodexModelBroker:
    """Only the serving Gateway process holds the upstream credential."""

    def __init__(self, directory: Path, model: ManagedModel):
        self.path = directory / "model.sock"
        with ExitStack() as scope:
            fd = os.open(directory, os.O_DIRECTORY | os.O_NOFOLLOW)
            scope.callback(os.close, fd)
            # The canonical state path can exceed Linux's AF_UNIX address limit.
            address = f"/proc/self/fd/{fd}/model.sock"
            if self.path.exists() or self.path.is_symlink():
                if self.path.is_symlink() or not self.path.is_socket():
                    raise PermissionError("Invalid managed Codex model socket")
                previous = scope.enter_context(socket.socket(socket.AF_UNIX))
                previous.settimeout(1)
                try:
                    previous.connect(address)
                except ConnectionRefusedError:
                    self.path.unlink()
                else:
                    raise PermissionError("Managed Codex model broker still has a listener")
            self.server = _UnixHTTPServer(address, _Responses)
        self.server.model = model
        os.chmod(self.path, 0o600)
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.path.unlink(missing_ok=True)
