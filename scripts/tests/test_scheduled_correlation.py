"""Offline recorded synthetic/edge correlation; no SDK, cloud, or traffic calls."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "monitoring/online-shop/diagnose-scheduled.py"
spec = importlib.util.spec_from_file_location("scheduled_diagnostic", SCRIPT)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
EXECUTION = "recorded-test-execution"
VERSION = "a" * 64


def fixture():
    c = d.c
    accepted = c.legacy.policy()["accepted_release"]
    rows = []
    for i, identity in enumerate(c.APPS):
        catalog = identity == "productcatalogservice"
        rows.append(c.app_record(identity, accepted["configuration_revision"] if catalog else "d" * 40,
            {}, accepted["build_id"] if catalog else "11111111-2222-3333-4444-" + str(i).zfill(12),
            accepted["manifest_digest"] if catalog else "sha256:" + hashlib.sha256(identity.encode()).hexdigest(),
            "sha256:" + "f" * 64))
    record = c.candidate("d" * 40, rows)
    rowmap = {x["id"]: x for x in rows}
    project = c.r.policy()["project"]
    base = datetime(2026, 11, 8, 15, 9, 19, tzinfo=timezone.utc)
    stamp = lambda ms: (base + timedelta(milliseconds=ms)).isoformat()
    trace_id = "1" * 32
    native = "projects/" + project + "/traces/" + trace_id
    attribution = {"monitor": "shop-dev-browse-v1", "execution_id": EXECUTION,
        "application_trace_id": trace_id, "monitor_version": VERSION, "environment": "dev"}
    function = [{"timestamp": stamp(600), "trace": native, "spanId": d.sid(10),
        "resource": {"labels": {"revision_name": "test-revision"}},
        "jsonPayload": {**attribution, "message": "synthetic.journey.passed", "requests": 3, "duration_ms": 600}},
        {"jsonPayload": {**attribution, "message": "synthetic.cleanup", "redis_writes": 0,
                         "local_session_discarded": True}},
        {"labels": {"execution_id": EXECUTION}, "jsonPayload": {"google.monitoring.v3.UptimeCheckResult": {
            "syntheticResult": {"syntheticGenericResultV1": {"ok": True},
                "runtimeMetadata": {"K_REVISION": "test-revision", "K_SERVICE": "shop-dev-browse"}}}}}]
    context = {"project_id": project, "project_number": "465837787797", "scheme": "EXTERNAL_MANAGED",
        "zone": "global", "hostname": "shop.runtimeplatforms.dev", "address": "8.233.86.84",
        "source_ip": "192.0.2.1", "server_ip": "10.0.0.2", "backend_pod_name": "frontend-test-pod", "backend_service_name": "frontend-backend",
        "forwarding_rule_name": "edge-443", "target_proxy_name": "edge-proxy", "url_map_name": "edge-map"}
    spans = [{"spanId": "10", "name": "shop.synthetic.browse"}]
    edges = []
    logs = []

    def labels(identity):
        return {"service.name": identity, "service.version": rowmap[identity]["source"]["revision"],
            "service.instance.id": identity + "-test-pod",
            "component_digest": rowmap[identity]["digest"], "release_set_id": record["release_set_id"],
            "deployment.environment.name": "dev"}

    for i, path in enumerate(("/", "/product/P1", "/cart")):
        ms = i * 200
        url = "https://shop.runtimeplatforms.dev" + path
        spans.extend([{"spanId": str(11+i), "parentSpanId": "10", "kind": "RPC_CLIENT", "name": "GET",
            "startTime": stamp(ms), "endTime": stamp(ms+100), "labels": {"/http/url": url,
                "http.target": path, "/http/method": "GET", "/http/status_code": "200", "net.peer.ip": "8.233.86.84"}},
            {"spanId": str(21+i), "parentSpanId": str(11+i), "kind": "RPC_SERVER",
                "startTime": stamp(ms+15), "endTime": stamp(ms+65), "labels": {**labels("frontend"),
                    "http.route": path if path != "/product/P1" else "/product/{id}", "http.response.status_code": "200"}}])
        edges.append({"timestamp": stamp(ms+10), "trace": "projects/"+project+"/traces/"+"f"*32,
            "httpRequest": {"requestUrl": url, "requestMethod": "GET", "status": 200, "latency": "0.06s",
                "userAgent": d.MARKER, "remoteIp": context["source_ip"], "serverIp": context["server_ip"]},
            "resource": {"type": "http_load_balancer", "labels": {k:context[k] for k in
                ("project_id", "zone", "backend_service_name", "forwarding_rule_name", "target_proxy_name", "url_map_name")}},
            "jsonPayload": {"backendTargetProjectNumber": "projects/465837787797",
                "statusDetails": "response_sent_by_backend", "enforcedSecurityPolicy": {"name": "shop-dev-edge",
                    "priority": 2000, "outcome": "ACCEPT", "configuredAction": "THROTTLE",
                    "rateLimitAction": {"outcome": "RATE_LIMIT_THRESHOLD_CONFORM", "key": context["source_ip"]}}}})
    spans.append({"spanId": "31", "parentSpanId": "21", "kind": "RPC_SERVER", "labels": labels("currencyservice"),
                  "startTime": stamp(20), "endTime": stamp(60)})
    for identity, span in (("frontend", 21), ("currencyservice", 31)):
        logs.append({"trace": native, "spanId": d.sid(span), "labels": labels(identity),
                     "jsonPayload": {"event": "request.completed", "trace_id": trace_id, "span_id": d.sid(span)}})
    return {"version": 1, "candidate": record, "release": {"source_sha256": VERSION, "revision_id": "test-revision"},
        "function_logs": {"entries": function}, "trace": {"projectId": project, "traceId": trace_id, "spans": spans},
        "application_logs": {"entries": logs}, "edge_logs": {"entries": edges}, "edge_context": context,
        "edge_capture": {"pagination_complete": True, "sample_rate": 1, "start": stamp(-2000), "end": stamp(2600)},
        "session_readback": {"execution_id": EXECUTION, "exists": 0, "owned_forward_closed": True}}


class CorrelationTests(unittest.TestCase):
    def run_diagnostic(self, value):
        return d.diagnose(value, EXECUTION, VERSION, value["candidate"]["release_set_id"])

    def test_independent_lb_ids_are_allowed_with_unique_operational_binding(self):
        result = self.run_diagnostic(fixture())
        self.assertEqual(result["recorded_execution_acceptance"], "passed")
        self.assertFalse(result["edge_native_trace_id_matches_application"])
        self.assertEqual(len(result["edge_bijection"]), 3)

    def test_wrong_time_url_method_marker_ip_and_backend_fail(self):
        changes = [(["timestamp"], "2026-11-08T15:09:24Z"),
            (["httpRequest", "requestUrl"], "https://shop.runtimeplatforms.dev/product/foreign"),
            (["httpRequest", "requestMethod"], "POST"), (["httpRequest", "userAgent"], "unrelated"),
            (["httpRequest", "remoteIp"], "192.0.2.2"), (["httpRequest", "serverIp"], "10.0.0.3"),
            (["resource", "labels", "backend_service_name"], "other-backend"),
            (["jsonPayload", "enforcedSecurityPolicy", "outcome"], "DENY")]
        for path, value in changes:
            with self.subTest(path=path):
                data = fixture(); target = data["edge_logs"]["entries"][0]
                for key in path[:-1]: target = target[key]
                target[path[-1]] = value
                with self.assertRaises(ValueError): self.run_diagnostic(data)

    def test_ambiguity_extra_missing_and_incomplete_pages_fail(self):
        for mode in ("duplicate", "ambiguous", "missing", "pagination", "sampling"):
            with self.subTest(mode=mode):
                data = fixture()
                if mode == "duplicate": data["edge_logs"]["entries"].append(copy.deepcopy(data["edge_logs"]["entries"][0]))
                if mode == "ambiguous": data["edge_logs"]["entries"][1] = copy.deepcopy(data["edge_logs"]["entries"][0])
                if mode == "missing": data["edge_logs"]["entries"].pop()
                if mode == "pagination": data["edge_capture"]["pagination_complete"] = False
                if mode == "sampling": data["edge_capture"]["sample_rate"] = 0.5
                with self.assertRaises(ValueError): self.run_diagnostic(data)

    def test_native_function_application_trace_and_parent_chain_remain_required(self):
        for mode in ("trace", "parent", "native_log", "function_span", "release", "digest"):
            with self.subTest(mode=mode):
                data = fixture()
                if mode == "trace": data["trace"]["traceId"] = "2"*32
                if mode == "parent": data["trace"]["spans"][2]["parentSpanId"] = "99"
                if mode == "native_log": data["application_logs"]["entries"][0]["trace"] = "unrelated"
                if mode == "function_span": data["trace"]["spans"].pop(0)
                if mode == "release": data["trace"]["spans"][2]["labels"]["release_set_id"] = "sha256:"+"0"*64
                if mode == "digest": data["trace"]["spans"][2]["labels"]["component_digest"] = "sha256:"+"0"*64
                with self.assertRaises(ValueError): self.run_diagnostic(data)

    def test_candidate_identity_reconstruction_and_reviewed_identity_are_required(self):
        data = fixture(); old = data["candidate"]["release_set_id"]
        data["candidate"]["components"][0]["digest"] = "sha256:"+"0"*64
        with self.assertRaises(ValueError): d.diagnose(data, EXECUTION, VERSION, old)
        data["candidate"]["release_set_id"] = d.c.r.fingerprint({k:v for k,v in data["candidate"].items() if k!="release_set_id"})
        with self.assertRaises(ValueError): d.diagnose(data, EXECUTION, VERSION, old)

    def test_cli_requires_explicit_execution_and_uses_only_snapshot(self):
        data = fixture()
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory)/"snapshot.json";snapshot.write_text(json.dumps(data), encoding="utf-8")
            args = [sys.executable, str(SCRIPT), "--snapshot", str(snapshot), "--execution-id", EXECUTION,
                    "--monitor-version", VERSION, "--release-set-id", data["candidate"]["release_set_id"]]
            result = subprocess.run(args, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertNotIn(b"192.0.2.1", result.stdout)
            args[args.index(EXECUTION)] = "other-execution"
            result = subprocess.run(args, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
