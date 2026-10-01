"""Real (not mocked) tests for healthcheck.py — spins up actual local HTTP
servers in background threads and points the health checker at them, so
this exercises the real network code path, not a stub.
"""
import http.server
import json
import pathlib
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from healthcheck import check_once, main, read_last_state, write_state  # noqa: E402


class _Handler(http.server.BaseHTTPRequestHandler):
    """Mimics real trytond behavior: only OPTIONS/POST are meaningful at "/";
    confirmed against an actual running GNU Health instance, which returns
    405 on GET even when healthy. do_GET is still implemented, used by the
    tests that specifically check non-default-method behavior.
    """

    status_code = 200

    def do_GET(self):  # noqa: N802 (stdlib method name)
        self.send_response(self.status_code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(self.status_code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002 - silence test noise
        pass


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    """Stands in for a webhook receiver; records what it got."""

    received: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.__class__.received.append(json.loads(body))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        pass


def _run_server(handler_cls, status_code: int | None = None):
    if status_code is not None:
        handler_cls = type("H", (handler_cls,), {"status_code": status_code})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture
def healthy_server():
    server = _run_server(_Handler, status_code=200)
    yield server
    server.shutdown()


@pytest.fixture
def unhealthy_server():
    server = _run_server(_Handler, status_code=500)
    yield server
    server.shutdown()


@pytest.fixture
def webhook_server():
    _RecordingHandler.received = []
    server = _run_server(_RecordingHandler)
    yield server
    server.shutdown()


def test_check_once_reports_healthy_on_200(healthy_server):
    url = f"http://127.0.0.1:{healthy_server.server_port}/"
    ok, detail = check_once(url, timeout=2.0)
    assert ok is True
    assert "HTTP 200" in detail


def test_default_method_is_options_not_get(healthy_server):
    # Regression test for a real bug: a server that only implements OPTIONS
    # at "/" (like real trytond) must be reported healthy by default.
    class _OptionsOnlyHandler(http.server.BaseHTTPRequestHandler):
        def do_OPTIONS(self):  # noqa: N802
            self.send_response(204)
            self.end_headers()

        def do_GET(self):  # noqa: N802
            self.send_response(405)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A002
            pass

    server = _run_server(_OptionsOnlyHandler)
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        ok, detail = check_once(url, timeout=2.0)  # default method
        assert ok is True, f"expected OPTIONS default to succeed, got: {detail}"
        # Confirm this isn't a coincidence: GET against the same server fails.
        ok_get, _ = check_once(url, timeout=2.0, method="GET")
        assert ok_get is False
    finally:
        server.shutdown()


def test_check_once_reports_unhealthy_on_500(unhealthy_server):
    url = f"http://127.0.0.1:{unhealthy_server.server_port}/"
    ok, detail = check_once(url, timeout=2.0)
    assert ok is False
    assert "HTTP 500" in detail


def test_check_once_reports_unhealthy_on_connection_refused():
    # Nothing listening on this port.
    ok, detail = check_once("http://127.0.0.1:1/", timeout=2.0)
    assert ok is False
    assert "unreachable" in detail


def test_state_file_round_trip(tmp_path):
    state_file = tmp_path / "state.json"
    assert read_last_state(state_file) is None
    write_state(state_file, "up", "HTTP 200 in 0.01s")
    assert read_last_state(state_file) == "up"
    write_state(state_file, "down", "HTTP 500 in 0.01s")
    assert read_last_state(state_file) == "down"


def test_main_exit_code_healthy(healthy_server, capsys):
    url = f"http://127.0.0.1:{healthy_server.server_port}/"
    code = main(["--url", url])
    assert code == 0
    assert "[OK]" in capsys.readouterr().out


def test_main_exit_code_unhealthy(unhealthy_server, capsys):
    url = f"http://127.0.0.1:{unhealthy_server.server_port}/"
    code = main(["--url", url])
    assert code == 1
    assert "[FAIL]" in capsys.readouterr().out


def test_main_notifies_webhook_only_on_transition(unhealthy_server, webhook_server, tmp_path):
    url = f"http://127.0.0.1:{unhealthy_server.server_port}/"
    webhook = f"http://127.0.0.1:{webhook_server.server_port}/"
    state_file = tmp_path / "state.json"

    # First failing check: no prior state -> should notify (down for the first time).
    main(["--url", url, "--webhook", webhook, "--state-file", str(state_file)])
    time.sleep(0.05)
    assert len(_RecordingHandler.received) == 1
    assert "DOWN" in _RecordingHandler.received[0]["text"]

    # Second failing check: still down, no transition -> should NOT notify again.
    main(["--url", url, "--webhook", webhook, "--state-file", str(state_file)])
    time.sleep(0.05)
    assert len(_RecordingHandler.received) == 1  # unchanged


def test_main_notifies_on_recovery(healthy_server, unhealthy_server, webhook_server, tmp_path):
    webhook = f"http://127.0.0.1:{webhook_server.server_port}/"
    state_file = tmp_path / "state.json"
    down_url = f"http://127.0.0.1:{unhealthy_server.server_port}/"
    up_url = f"http://127.0.0.1:{healthy_server.server_port}/"

    main(["--url", down_url, "--webhook", webhook, "--state-file", str(state_file)])
    main(["--url", up_url, "--webhook", webhook, "--state-file", str(state_file)])
    time.sleep(0.05)

    assert len(_RecordingHandler.received) == 2
    assert "DOWN" in _RecordingHandler.received[0]["text"]
    assert "UP" in _RecordingHandler.received[1]["text"]
