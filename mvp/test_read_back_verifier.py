import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.action_executor import ActionResult
from core.read_back_verifier import ReadAfterWriteVerifier, ReadBackConfig


class _Handler(BaseHTTPRequestHandler):
    payload = {}
    status = 200
    delay = 0

    def do_GET(self):  # noqa: N802
        if self.delay:
            import time
            time.sleep(self.delay)
        body = json.dumps(type(self).payload).encode("utf-8")
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def _server(payload, *, status=200, delay=0):
    _Handler.payload = payload
    _Handler.status = status
    _Handler.delay = delay
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _verifier(server, **kwargs):
    port = server.server_address[1]
    return ReadAfterWriteVerifier(
        ReadBackConfig(
            base_url=f"http://127.0.0.1:{port}",
            endpoint="state/{target}",
            allowed_hosts=frozenset({"127.0.0.1"}),
            **kwargs,
        )
    )


def _result():
    return ActionResult(
        action_type="update_crm",
        status="completed",
        execution_id="EXE-VERIFY123",
        output={"target": "customer-42", "request_body": {"status": "active", "owner": "sales"}},
    )


def test_read_after_write_verifies_matching_external_state():
    server, thread = _server({"status": "active", "owner": "sales"})
    try:
        verifier = _verifier(server, response_path="", expected_path="request_body")
        result = verifier.verify(_result())
        assert result.status == "verified"
        assert "matches" in result.checks[1]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_read_after_write_fails_when_external_state_is_stale():
    server, thread = _server({"status": "pending", "owner": "sales"})
    try:
        verifier = _verifier(server)
        result = verifier.verify(_result())
        assert result.status == "failed"
        assert "does not match" in result.checks[1]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_read_after_write_can_require_execution_identity():
    server, thread = _server({"execution_id": "EXE-OTHER", "state": {"status": "active", "owner": "sales"}})
    try:
        verifier = _verifier(
            server,
            response_path="state",
            expected_path="request_body",
            execution_id_path="execution_id",
            require_execution_id_match=True,
        )
        result = verifier.verify(_result())
        assert result.status == "failed"
        assert "does not match" in result.checks[0]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_read_after_write_rejects_oversized_response():
    server, thread = _server({"status": "active", "blob": "x" * 1000})
    try:
        verifier = _verifier(server, max_response_bytes=100)
        result = verifier.verify(_result())
        assert result.status == "failed"
        assert "size limit" in result.checks[0]
    finally:
        server.shutdown()
        thread.join(timeout=2)
