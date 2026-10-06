"""Offline HTTP checks for structured stdout and unchanged sample responses."""
from contextlib import redirect_stdout, redirect_stderr
from http.client import HTTPConnection
from http.server import HTTPServer
import importlib.util
import io
import json
import math
from pathlib import Path
import socket
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("sample_service", ROOT / "app/sample-service/app.py")
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)


class SampleServiceLoggingTest(unittest.TestCase):
    def request(self, path="/", method="GET", environment="dev", raw=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with HTTPServer(("127.0.0.1", 0), service.Handler) as server:
            server.timeout = 3
            with patch.dict(service.os.environ, {"APP_ENV": environment}), redirect_stdout(stdout), redirect_stderr(stderr):
                worker = threading.Thread(target=server.handle_request, daemon=True)
                worker.start()
                try:
                    if raw is not None:
                        with socket.create_connection(server.server_address, timeout=3) as client:
                            client.sendall(raw)
                            chunks = []
                            while chunk := client.recv(4096):
                                chunks.append(chunk)
                        response = b"".join(chunks)
                        headers, _, body = response.partition(b"\r\n\r\n")
                        status = int(headers.split(b" ")[1]) if headers.startswith(b"HTTP/") else None
                    else:
                        client = HTTPConnection(*server.server_address, timeout=3)
                        try:
                            client.request(method, path, body="private-body",
                                           headers={"Authorization": "Bearer private-token",
                                                    "Cookie": "session=private-cookie"})
                            response = client.getresponse()
                            status, body = response.status, response.read()
                        finally:
                            client.close()
                finally:
                    worker.join(timeout=4)
                self.assertFalse(worker.is_alive(), "HTTP request did not finish")
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1, stdout.getvalue())
        event = json.loads(lines[0])
        self.assertEqual(set(event), {"event", "service", "environment", "method", "path",
                                     "status", "latency_ms", "severity", "health_check"})
        self.assertEqual(event["event"], "http_request")
        self.assertEqual(event["service"], "sample-service")
        self.assertEqual(event["environment"], environment)
        self.assertIsInstance(event["latency_ms"], (int, float))
        self.assertTrue(math.isfinite(event["latency_ms"]))
        self.assertGreaterEqual(event["latency_ms"], 0)
        self.assertIsInstance(event["health_check"], bool)
        for secret in ("private-token", "private-cookie", "private-body", "private-query", "private-user"):
            self.assertNotIn(secret, stdout.getvalue())
        return status, body, event

    def test_root_response_and_request_event(self):
        status, body, event = self.request(environment="stage")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"service": "sample-service", "status": "running", "environment": "stage"})
        self.assertEqual((event["method"], event["path"], event["status"], event["severity"], event["health_check"]),
                         ("GET", "/", 200, "INFO", False))

    def test_health_response_and_request_event(self):
        status, body, event = self.request("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})
        self.assertEqual((event["method"], event["path"], event["status"], event["severity"], event["health_check"]),
                         ("GET", "/healthz", 200, "INFO", True))

    def test_query_is_removed_without_changing_existing_routing(self):
        for path in ("/other?token=private-query", "/healthz?token=private-query"):
            with self.subTest(path=path):
                status, body, event = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), {"service": "sample-service", "status": "running", "environment": "dev"})
                self.assertEqual(event["path"], path.split("?")[0])
                self.assertFalse(event["health_check"])

    def test_post_health_path_is_not_a_health_check(self):
        status, _, event = self.request("/healthz", method="POST")
        self.assertEqual(status, 501)
        self.assertEqual((event["method"], event["path"], event["severity"]),
                         ("POST", "/healthz", "ERROR"))
        self.assertFalse(event["health_check"])

    def test_absolute_target_omits_authority_and_query(self):
        _, _, event = self.request("http://private-user:private-token@example.invalid/path?token=private-query")
        self.assertEqual(event["path"], "/path")

    def test_unsupported_method_has_error_severity_and_no_body_secret(self):
        status, _, event = self.request("/unsupported?token=private-query", method="POST")
        self.assertEqual(status, 501)
        self.assertEqual((event["method"], event["path"], event["status"], event["severity"]),
                         ("POST", "/unsupported", 501, "ERROR"))

    def test_bad_request_has_warning_severity(self):
        _, _, event = self.request(raw=b"GET /private-query HTTP/1.1 extra\r\n\r\n")
        self.assertEqual(event["status"], 400)
        self.assertEqual(event["severity"], "WARNING")

    def test_invalid_url_does_not_leak_request_or_break_response(self):
        status, body, event = self.request(raw=b"GET http://[private-query/path HTTP/1.1\r\nHost: example.invalid\r\n\r\n")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "running")
        self.assertEqual(event["path"], "<invalid-path>")

    def test_idle_connection_does_not_create_request_event(self):
        stdout = io.StringIO()
        with HTTPServer(("127.0.0.1", 0), service.Handler) as server, redirect_stdout(stdout):
            server.timeout = 3
            worker = threading.Thread(target=server.handle_request, daemon=True)
            worker.start()
            with socket.create_connection(server.server_address, timeout=3):
                pass
            worker.join(timeout=4)
            self.assertFalse(worker.is_alive())
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
