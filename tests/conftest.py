import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from mcprack_client import config as client_config


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never read or write the developer's real settings, state or config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setattr(client_config, "system_config_path", lambda: tmp_path / "no-system-client.env")
    for name in ("MCPRACK_URL", "MCPRACK_TOKEN", "MCPRACK_TRUSTED_ORIGINS", "MCPRACK_ALLOW_INSECURE"):
        monkeypatch.delenv(name, raising=False)


class FakeMcprack:
    """A loopback HTTP server standing in for mcprack. `answer` is what
    /api/v1/me/config/<client> returns; `hits` records what it was asked."""

    def __init__(self):
        self.answer = {"mcpServers": {}}
        self.status = 200
        self.raw = None
        self.location = None
        self.hits = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.hits.append({"path": self.path, "authorization": self.headers.get("Authorization")})
                if outer.location:
                    self.send_response(outer.status if 300 <= outer.status < 400 else 302)
                    self.send_header("Location", outer.location)
                    self.end_headers()
                    return
                body = outer.raw if outer.raw is not None else json.dumps({"ok": True, "data": {"config": outer.answer}}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def mcprack():
    server = FakeMcprack()
    yield server
    server.close()
