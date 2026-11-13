"""The standalone agent: talks to a tiny fake server, imports nothing from the app."""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("ops_agent", Path(__file__).resolve().parent.parent / "agent" / "agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class Fake(BaseHTTPRequestHandler):
    status = 201
    received: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.received.append((self.path, self.headers.get("X-API-Key"), body))
        self.send_response(Fake.status)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Fake.status, Fake.received = 201, []
    httpd = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture(autouse=True)
def _clear_stop():
    agent.stop.clear()
    yield
    agent.stop.clear()


def test_measure_has_three_percentages():
    data = agent.measure()
    assert set(data) == {"cpu_percent", "memory_percent", "disk_percent"}
    assert all(0 <= v <= 100 for v in data.values())


def test_once_sends_a_report_with_the_key_in_the_header(server):
    assert agent.main(["--url", server, "--key", "ops_abc", "--once"]) == 0
    path, key, body = Fake.received[0]
    assert path == "/api/ingest" and key == "ops_abc" and "cpu_percent" in body


def test_key_from_file_and_environment(server, tmp_path, monkeypatch):
    key_file = tmp_path / "key"
    key_file.write_text("ops_from_file\n")
    assert agent.main(["--url", server, "--key-file", str(key_file), "--once"]) == 0
    monkeypatch.setenv("OPS_KEY", "ops_from_env")
    monkeypatch.setenv("OPS_URL", server)
    assert agent.main(["--once"]) == 0
    assert [k for _, k, _ in Fake.received] == ["ops_from_file", "ops_from_env"]


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_stops_with_exit_code_2(server, status):
    Fake.status = status
    assert agent.main(["--url", server, "--key", "ops_wrong"]) == 2  # no --once: it must stop by itself


def test_unreachable_server_is_retried_not_fatal(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "measure", lambda: {"cpu_percent": 1.0, "memory_percent": 2.0, "disk_percent": 3.0})

    def failing_send(*a, **k):
        calls.append(1)
        if len(calls) == 3:
            agent.stop.set()
        raise OSError("cannot reach server (refused)")

    monkeypatch.setattr(agent, "send", failing_send)
    waits = []
    monkeypatch.setattr(agent.stop, "wait", lambda t: waits.append(t))
    assert agent.run("http://127.0.0.1:9", "ops_x", 5) == 0
    assert len(calls) == 3 and waits == [10, 20, 40]  # growing pauses
    agent.stop.clear()
    assert agent.run("http://127.0.0.1:9", "ops_x", 5, once=True) == 1  # --once: no retry loop, exit code 1


def test_bad_settings_exit_early(monkeypatch):
    monkeypatch.delenv("OPS_KEY", raising=False)
    monkeypatch.delenv("OPS_KEY_FILE", raising=False)
    with pytest.raises(SystemExit):
        agent.main(["--url", "http://127.0.0.1:1"])  # no key
    with pytest.raises(SystemExit):
        agent.main(["--url", "ftp://x", "--key", "k"])
    with pytest.raises(SystemExit):
        agent.main(["--url", "http://127.0.0.1:1", "--key", "k", "--every", "0"])


def test_agent_is_standalone():
    source = (Path(agent.__file__)).read_text()
    assert "import app" not in source and "from app" not in source
