# Dependency reachability review

The locked npm audit reports 50 moderate affected dependency entries covering three unique advisories. These are residual risks for review.

| Advisory | Installed path and reachability | Decision |
| --- | --- | --- |
| [GHSA-8988-4f7v-96qf](https://github.com/advisories/GHSA-8988-4f7v-96qf) | Synthetics SDK -> SDK trace/node and auto-instrumentation -> OpenTelemetry core <2.8.0. W3C baggage parsing can allocate unbounded memory. Incoming function HTTP is reachable only by the Monitoring invoker. | Set OTEL_PROPAGATORS=tracecontext before SDK initialization. Baggage propagation is disabled for this monitor. Accept the installed legacy core provisionally with authenticated invocation, bounded requests and memory. Upgrading all SDK trace packages to core 2.x requires SDK changes and separate compatibility review. |
| [GHSA-qqmp-wf37-98f9](https://github.com/advisories/GHSA-qqmp-wf37-98f9) | SDK -> auto-instrumentations-node -> database instrumentations. Vulnerable versions can emit db.user attributes. | This function opens only HTTPS requests. It has no DB client, DB credentials, Redis connection, VPC connector or database queries. Database hooks therefore have no operation to instrument in this journey. Accept the residual installed modules for this scope; adding a database client requires renewed review and upgraded instrumentation. |
| [GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq) | SDK/transitive auth/export dependencies -> uuid <11.1.1. The defect requires use of UUID v3/v5/v6 with a caller-provided output buffer. | Monitor code uses Node crypto SHA-256, not uuid. The selected SDK/logger/export path does not supply a caller-controlled UUID output buffer. Accept the residual versions in this scope. A blanket uuid 11 override would cross incompatible majors for older consumers; require consumer-specific upgrade before adding UUID buffer operations. |

Axios 1.21.0 and Jaeger propagator 2.12.0 remain pinned overrides for the previously detected high advisories. A local test with the actual installed SDK and these overrides passed active trace context, the three-step journey and an instrumented loopback HTTP request carrying the same trace ID. It observed no baggage header. Remote export was replaced in that local fixture.

These decisions cover the reviewed function, not every possible use of the dependencies. Provisioning still requires operator review of this residual-risk record and live authenticated-invocation validation.
