from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import time
from urllib.parse import urlsplit


def write_log(event, **fields):
    print(json.dumps({"event": event, "service": "sample-service",
                      "environment": os.getenv("APP_ENV", "unknown"), **fields}), flush=True)


class Handler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        started = time.monotonic()
        self._response_status = None
        self._health_check = False
        self.path = ""
        self.command = None
        try:
            super().handle_one_request()
        finally:
            # No event for an idle connection closed without an HTTP response.
            if self._response_status is not None:
                try:
                    path = urlsplit(self.path).path
                except ValueError:
                    path = "<invalid-path>"
                status = self._response_status
                write_log("http_request", method=self.command, path=path,
                          status=status, latency_ms=(time.monotonic() - started) * 1000,
                          severity="ERROR" if status >= 500 else "WARNING" if status >= 400 else "INFO",
                          health_check=self._health_check)

    def log_request(self, code="-", size="-"):
        self._response_status = int(code)

    def do_GET(self):
        if self.path == "/healthz":
            self._health_check = True
            self._send_json({"status": "ok"})
            return

        payload = {
            "service": "sample-service",
            "status": "running",
            "environment": os.getenv("APP_ENV", "unknown"),
        }
        self._send_json(payload)

    def log_message(self, format, *args):
        return

    def _send_json(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    write_log("startup", severity="INFO", port=port)
    server.serve_forever()
