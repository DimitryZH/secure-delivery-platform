# Sample Service

`app.py` is a small standard-library Python HTTP service used to validate the delivery path. `Dockerfile` packages it with Python 3.12 and starts the server on `0.0.0.0`; `PORT` defaults to 8080.

- `GET /healthz` returns HTTP 200 JSON with `status=ok`.
- `GET /` returns HTTP 200 JSON with `service=sample-service`, `status=running`, and `environment` from `APP_ENV` (default `unknown`). Other GET paths use the same response.

The shared deployment sets `APP_ENV` to the target namespace. The workload is a validation target, not a production application or observability framework. See [runtime validation](../../docs/operator-runbook.md#runtime-validation) and [Trusted Delivery](../../docs/trusted-delivery.md).

## Structured stdout

Startup emits a JSON `startup` event. Each HTTP response, including standard request errors and unsupported methods, emits one flushed JSON `http_request` event with `service`, `environment`, `method`, `path`, `status`, `latency_ms`, `severity`, and `health_check`. Latency uses a monotonic clock from request reading through response handling; it is not client-observed latency or proof of response receipt. Severity is INFO below 400, WARNING for 4xx, and ERROR for 5xx.

Only the URL path is logged; query strings, fragments, URL authority, headers, cookies, and bodies are excluded. An unparseable URL uses `<invalid-path>`; a malformed request line can have null method and empty path without exposing its raw contents. `health_check` is true only when the request is handled by the health endpoint: exact GET `/healthz`. GET `/healthz` with a query string and POST `/healthz` are false; routing is unchanged. Default HTTP access messages remain suppressed. An idle connection closed without an HTTP response produces no request event.

GKE workload collection supplies cluster/namespace/Pod/container identity; events do not duplicate release annotations. See [application log inspection](../../docs/operator-runbook.md#application-log-inspection) for Cloud Logging queries and release correlation. Repository tests run with:

```sh
python -B -m unittest discover -s scripts/tests -p test_sample_service_logging.py -v
```
