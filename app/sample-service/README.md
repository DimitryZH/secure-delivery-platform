# Sample Service

`app.py` is a small standard-library Python HTTP service used to validate the delivery path. `Dockerfile` packages it with Python 3.12 and starts the server on `0.0.0.0`; `PORT` defaults to 8080.

- `GET /healthz` returns HTTP 200 JSON with `status=ok`.
- `GET /` returns HTTP 200 JSON with `service=sample-service`, `status=running`, and `environment` from `APP_ENV` (default `unknown`). Other GET paths use the same response.

The shared deployment sets `APP_ENV` to the target namespace. The workload is a validation target, not a production application or observability framework. See [runtime validation](../../docs/operator-runbook.md#runtime-validation) and [Trusted Delivery](../../docs/trusted-delivery.md).
