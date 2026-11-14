# Cloud Deploy shared support

Online Shop uses `catalog-dev` and the existing `dev` target, shared deployment
identity and protected source/render storage. Its preparation, rendering and
acceptance contracts are in [complete workload delivery](../online-shop/complete-README.md).

`release-preflight.py` is a read-only evidence evaluator and supplies shared
time/protection helpers to Online Shop. READY is eligibility, not authorization.
The sample-specific bundle generator and Skaffold file are removed.
`deploy/deploy-release.py` remains byte-for-byte unchanged as an unsupported legacy
dependency in the producing trust-file set; its CLI must not be used for sample
restoration. Removing its manifests/configuration retires the active delivery path. Their prior results are [historical](../../docs/historical/sample-service/README.md).
See [retirement](../../docs/sample-service-retirement.md) for deletion and retention boundaries.
