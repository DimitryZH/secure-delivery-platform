#!/usr/bin/env python3
"""Offline correlation of a recorded scheduled execution; never generate traffic."""
import argparse
from datetime import datetime, timedelta
import importlib.util
import ipaddress
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("shop_acceptance", ROOT / "deploy/online-shop/complete-acceptance.py")
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)
c = acceptance.c
require = c.require
MARKER = "sdp-online-shop-synthetic/browse-v1"


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "timestamp_timezone_required")
    return result


def sid(value):
    return format(int(value), "016x")


def edge_matches(clients, entries, context, coverage):
    """Require a unique bijection within an exhaustively collected evidence window.

    LB native IDs are recorded separately, never used as the application identity.
    The stable User-Agent/IP are operational correlation, not authentication.
    """
    require(coverage["pagination_complete"] is True and coverage["sample_rate"] == 1,
            "incomplete_edge_capture")
    require(len(clients) == len(entries) == 3, "edge_request_budget")
    ipaddress.IPv4Address(context["source_ip"])
    require(context["scheme"] == "EXTERNAL_MANAGED" and context["zone"] == "global",
            "unexpected_load_balancer")
    matches = []
    used = set()
    for client in clients:
        labels = client["labels"]
        url = labels["/http/url"]
        path = url.removeprefix("https://" + context["hostname"])
        require(path in ("/", "/cart") or re.fullmatch(r"/product/[A-Za-z0-9_-]+", path),
                "unexpected_client_url")
        require(labels["/http/method"] == "GET" and labels["/http/status_code"] == "200"
                and labels["net.peer.ip"] == context["address"], "unexpected_client_request")
        start, end = utc(client["startTime"]), utc(client["endTime"])
        require(utc(coverage["start"]) <= start <= end <= utc(coverage["end"]),
                "client_outside_edge_capture")
        candidates = []
        for index, entry in enumerate(entries):
            request = entry["httpRequest"]
            latency = request["latency"]
            require(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?s", latency), "invalid_edge_latency")
            edge_start = utc(entry["timestamp"])
            edge_end = edge_start + timedelta(seconds=float(latency[:-1]))
            if request["requestUrl"] == url and start <= edge_start <= edge_end <= end:
                candidates.append(index)
        require(len(candidates) == 1 and candidates[0] not in used, "ambiguous_or_missing_edge_match")
        index = candidates[0]
        entry = entries[index]
        request = entry["httpRequest"]
        resource = entry["resource"]
        require(resource["type"] == "http_load_balancer", "wrong_edge_resource")
        for key in ("project_id", "zone", "backend_service_name", "forwarding_rule_name",
                    "target_proxy_name", "url_map_name"):
            require(resource["labels"].get(key) == context[key], "edge_resource_binding")
        require(request["requestMethod"] == "GET" and request["status"] == 200
                and request["userAgent"] == MARKER and request["remoteIp"] == context["source_ip"]
                and request["serverIp"] == context["server_ip"], "edge_request_binding")
        payload = entry["jsonPayload"]
        require(payload["backendTargetProjectNumber"] == "projects/" + context["project_number"]
                and payload["statusDetails"] == "response_sent_by_backend", "edge_backend_binding")
        policy = payload["enforcedSecurityPolicy"]
        require(policy["name"] == "shop-dev-edge" and policy["priority"] == 2000
                and policy["outcome"] == "ACCEPT" and policy["configuredAction"] == "THROTTLE"
                and policy["rateLimitAction"]["outcome"] == "RATE_LIMIT_THRESHOLD_CONFORM"
                and policy["rateLimitAction"]["key"] == context["source_ip"], "armor_verdict_mismatch")
        used.add(index)
        matches.append({"path": path, "edge_timestamp": entry["timestamp"],
                        "client_start": client["startTime"], "client_end": client["endTime"],
                        "method": "GET", "status": 200})
    require(len(used) == len(entries), "unmatched_edge_entries")
    require(sorted(x["path"] for x in matches)[0] == "/"
            and {x["path"] for x in matches} >= {"/", "/cart"}, "wrong_journey_paths")
    return matches


def diagnose(snapshot, execution_id, monitor_version, release_set_id):
    require(type(snapshot.get("version")) is int and snapshot["version"] == 1, "snapshot_version")
    record = snapshot["candidate"]
    require(record["release_set_id"] == release_set_id, "unreviewed_release_set")
    c.validate_candidate(record, record["configuration_revision"],
                         {row["id"]: row.get("plan") for row in record["components"]})
    rows = {x["id"]: x for x in record["components"]}
    release = snapshot["release"]
    require(release["source_sha256"] == monitor_version, "unreviewed_monitor_source")
    entries = snapshot["function_logs"]["entries"]
    passed = [x for x in entries if x.get("jsonPayload", {}).get("message") == "synthetic.journey.passed"
              and x["jsonPayload"].get("execution_id") == execution_id]
    require(len(passed) == 1, "execution_success_not_unique")
    entry = passed[0]
    body = entry["jsonPayload"]
    require(entry["resource"]["labels"]["revision_name"] == release["revision_id"]
            and type(body["requests"]) is int and body["requests"] == 3
            and type(body["duration_ms"]) is int and 0 <= body["duration_ms"] < 30000
            and body["monitor"] == "shop-dev-browse-v1"
            and body["monitor_version"] == monitor_version and body["environment"] == "dev",
            "execution_revision_or_budget")
    results = [x for x in entries if x.get("labels", {}).get("execution_id") == execution_id
               and "google.monitoring.v3.UptimeCheckResult" in x.get("jsonPayload", {})]
    require(len(results) == 1, "sdk_result_not_unique")
    result = results[0]["jsonPayload"]["google.monitoring.v3.UptimeCheckResult"]["syntheticResult"]
    require(result["syntheticGenericResultV1"]["ok"] is True
            and result["runtimeMetadata"]["K_REVISION"] == release["revision_id"]
            and result["runtimeMetadata"]["K_SERVICE"] == "shop-dev-browse", "sdk_result_failed")
    cleanup = [x["jsonPayload"] for x in entries if x.get("jsonPayload", {}).get("message") == "synthetic.cleanup"
               and x["jsonPayload"].get("execution_id") == execution_id]
    require(len(cleanup) == 1 and cleanup[0]["redis_writes"] == 0
            and cleanup[0]["local_session_discarded"] is True, "execution_cleanup_missing")
    trace_id = body["application_trace_id"]
    project = c.r.policy()["project"]
    native = "projects/" + project + "/traces/" + trace_id
    trace = snapshot["trace"]
    require(re.fullmatch(r"[0-9a-f]{32}", trace_id) and trace["traceId"] == trace_id
            and trace["projectId"] == project and entry.get("trace") == native, "native_trace_mismatch")
    spans = {sid(x["spanId"]): x for x in trace["spans"]}
    require(len(spans) == len(trace["spans"]), "duplicate_trace_span")
    root = spans.get(entry.get("spanId"))
    require(root and root["name"] == "shop.synthetic.browse", "execution_span_missing")
    clients = [x for x in spans.values() if x.get("kind") == "RPC_CLIENT"
               and x.get("parentSpanId") == root["spanId"]]
    require(len(clients) == 3, "three_execution_client_spans_required")
    app = {key: (x.get("labels", {}).get("service.name"), x) for key, x in spans.items()
           if x.get("labels", {}).get("service.name") in c.APPS}
    start = utc(entry["timestamp"]) - timedelta(milliseconds=body["duration_ms"], seconds=2)
    end = utc(entry["timestamp"]) + timedelta(seconds=2)
    for identity, span in app.values():
        labels = span["labels"]
        require(labels.get("service.version") == rows[identity]["source"]["revision"]
                and labels.get("deployment.environment.name") == "dev"
                and labels.get("release_set_id") == release_set_id
                and labels.get("component_digest") == rows[identity]["digest"], "trace_component_attribution")
        require(start <= utc(span["startTime"]) <= utc(span["endTime"]) <= end, "trace_outside_execution")
    frontend = [x for identity, x in app.values() if identity == "frontend" and x.get("kind") == "RPC_SERVER"]
    require(sorted(x["labels"].get("http.route") for x in frontend) == ["/", "/cart", "/product/{id}"],
            "frontend_journey_routes")
    require(all(x["labels"].get("service.instance.id") == snapshot["edge_context"]["backend_pod_name"]
                for x in frontend), "frontend_backend_instance_mismatch")
    for client in clients:
        children = [x for x in frontend if x.get("parentSpanId") == client["spanId"]]
        path = client["labels"]["http.target"]
        route = path if path in ("/", "/cart") else "/product/{id}"
        require(len(children) == 1 and children[0]["labels"]["http.response.status_code"] == "200",
                "w3c_client_frontend_parent_missing")
        require(children[0]["labels"]["http.route"] == route, "w3c_client_frontend_route_mismatch")
    require(any(span.get("parentSpanId") and sid(span["parentSpanId"]) in app
                and app[sid(span["parentSpanId"])][0] == "frontend" and identity != "frontend"
                for identity, span in app.values()), "downstream_trace_missing")
    logs = snapshot["application_logs"]
    require(not logs.get("nextPageToken"), "application_logs_incomplete")
    logged = set()
    for log in logs.get("entries", []):
        labels = log.get("labels", {})
        identity = labels.get("service.name")
        if identity not in c.APPS:
            continue
        key = log.get("spanId")
        payload = log["jsonPayload"]
        require(key in app and app[key][0] == identity and log.get("trace") == native
                and payload.get("trace_id") == trace_id and payload.get("span_id") == key,
                "native_application_log_mismatch")
        require(labels.get("service.version") == rows[identity]["source"]["revision"]
                and labels.get("deployment.environment.name") == "dev"
                and labels.get("release_set_id") == release_set_id
                and labels.get("component_digest") == rows[identity]["digest"], "log_component_attribution")
        if acceptance.server_completion(identity, payload, key, app):
            logged.add(identity)
    require("frontend" in logged and len(logged) >= 2, "component_completion_logs_missing")
    edge = snapshot["edge_logs"]
    require(not edge.get("nextPageToken"), "edge_logs_incomplete")
    require(snapshot["edge_context"]["project_id"] == project
            and snapshot["edge_context"]["hostname"] == acceptance.w.ENDPOINT_HOST, "unreviewed_edge_target")
    matches = edge_matches(clients, edge.get("entries", []), snapshot["edge_context"], snapshot["edge_capture"])
    state = snapshot["session_readback"]
    require(state["execution_id"] == execution_id and state["exists"] == 0
            and state["owned_forward_closed"] is True, "exact_session_cleanup_unproven")
    return {"recorded_execution_acceptance": "passed", "execution_id": execution_id,
            "requests": 3, "native_w3c_correlation": "passed", "edge_bijection": matches,
            "same_source_ip_and_backend": True, "armor_priority": 2000, "armor_outcome": "ACCEPT",
            "edge_native_trace_id_matches_application": all(x.get("trace") == native for x in edge["entries"]),
            "edge_binding_limit": "unique within complete recorded candidates; not an authenticated execution marker",
            "redis_exists": 0, "owned_forward_closed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--monitor-version", required=True)
    parser.add_argument("--release-set-id", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(diagnose(json.loads(args.snapshot.read_bytes()), args.execution_id,
                                  args.monitor_version, args.release_set_id), sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        # Inputs contain private sessions/addresses. Do not print their values.
        print(json.dumps({"recorded_execution_acceptance": "blocked",
                          "reason": str(error) if type(error) is ValueError else type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
