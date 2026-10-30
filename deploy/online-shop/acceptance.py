#!/usr/bin/env python3
"""Check saved API readbacks. This tool never creates traffic or cloud resources."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("catalog_workflow", HERE / "workflow.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
require = w.require


def quantity(value, cpu=False):
    require(isinstance(value, str), "invalid_quantity")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([a-zA-Z]*)", value)
    require(match is not None, "unsupported_quantity")
    suffix = match[2]
    factors = {"": 1, "m": Decimal("0.001"), "n": Decimal("0.000000001"),
               "u": Decimal("0.000001"), "K": 1000, "M": 1000**2, "G": 1000**3,
               "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    require(suffix in factors, "unsupported_quantity_suffix")
    return Decimal(match[1]) * factors[suffix] * (1000 if cpu else 1)


def pod_requests(pod, field):
    spec = pod["spec"]
    require(not spec.get("resources"), "pod_level_resources_require_review")
    def amount(container):
        return quantity(container.get("resources", {}).get("requests", {}).get(field, "0"), field == "cpu")
    steady = sum(amount(c) for c in spec.get("containers", []))
    sidecars = peak = Decimal(0)
    for init in spec.get("initContainers", []):
        if init.get("restartPolicy") == "Always":
            sidecars += amount(init)
            steady += amount(init)
            peak = max(peak, sidecars)
        else:
            peak = max(peak, sidecars + amount(init))
    return max(steady, peak) + quantity(spec.get("overhead", {}).get(field, "0"), field == "cpu")


def capacity(nodes, pods):
    """Conservative per-node headroom: app surge + agent + negative-test Pod."""
    rows = []
    pending = [p for p in pods["items"] if not p.get("spec", {}).get("nodeName")
               and p.get("status", {}).get("phase") not in ("Succeeded", "Failed")]
    for node in nodes["items"]:
        labels = node["metadata"]["labels"]
        eligible = labels.get("kubernetes.io/os") == "linux" and labels.get("kubernetes.io/arch") == "amd64"
        ready = any(c["type"] == "Ready" and c["status"] == "True" for c in node["status"].get("conditions", []))
        scheduled = [p for p in pods["items"] if p.get("spec", {}).get("nodeName") == node["metadata"]["name"]
                     and p.get("status", {}).get("phase") not in ("Succeeded", "Failed")]
        allocatable = node["status"]["allocatable"]
        free_cpu = quantity(allocatable["cpu"], True) - sum(pod_requests(p, "cpu") for p in scheduled)
        free_memory = quantity(allocatable["memory"]) - sum(pod_requests(p, "memory") for p in scheduled)
        slots = int(allocatable["pods"]) - len(scheduled)
        schedulable = eligible and ready and not node["spec"].get("unschedulable") and not node["spec"].get("taints")
        rows.append({"eligible": bool(schedulable), "free_cpu_m": float(free_cpu),
                     "free_memory_mi": float(free_memory / 1024**2), "pod_slots": slots,
                     "headroom": bool(schedulable and free_cpu >= 600 and free_memory >= 768 * 1024**2 and slots >= 4)})
    return {"capacity_ready": bool(rows and any(x["headroom"] for x in rows) and not pending),
            "nodes": rows, "unassigned_pods": len(pending), "reserve_cpu_m": 600, "reserve_memory_mi": 768,
            "limit": "Fresh WI node labels, affinities, quotas and rollout conflicts must also pass target preflight; this does not scale a cluster."}


def runtime(pods, record, revision):
    w.candidate_policy(record)
    expected = {"catalog": record["components"][0]["repository"] + "@" + record["components"][0]["digest"],
                "collector": w.policy()["collector"]["mirror_image"]}
    counts = {"catalog": 0, "collector": 0}
    app_nodes, collector_nodes = [], []
    for pod in pods["items"]:
        app = pod["metadata"].get("labels", {}).get("app")
        if app not in ("productcatalogservice", "catalog-collector"): continue
        require(pod["metadata"].get("namespace") == "dev", "wrong_runtime_namespace")
        require(not pod.get("metadata", {}).get("deletionTimestamp"), "terminating_runtime")
        require(pod["metadata"].get("annotations") == w.annotations(record, revision), "runtime_release_metadata_mismatch")
        require(not pod["spec"].get("initContainers") and not pod["spec"].get("ephemeralContainers"), "unexpected_runtime_container")
        containers = pod["spec"]["containers"]
        require(len(containers) == 1, "unexpected_runtime_membership")
        c = containers[0]
        expected_name = "catalog" if app == "productcatalogservice" else "collector"
        require(c["name"] == expected_name and c["image"] == expected[expected_name], "runtime_image_mismatch")
        statuses = pod.get("status", {}).get("containerStatuses", [])
        require(len(statuses) == 1 and statuses[0].get("ready") is True and statuses[0].get("name") == c["name"], "runtime_not_ready")
        require(statuses[0].get("imageID", "").removeprefix("docker-pullable://") == c["image"], "running_digest_unproven")
        counts[expected_name] += 1
        node = pod["spec"].get("nodeName")
        require(bool(node), "runtime_node_unknown")
        (app_nodes if expected_name == "catalog" else collector_nodes).append(node)
    require(counts["catalog"] == 1 and counts["collector"] >= 1, "missing_runtime_member")
    require(len(collector_nodes) == len(set(collector_nodes)) and set(app_nodes) <= set(collector_nodes), "filelog_node_coverage_mismatch")
    return {"runtime": "passed", "members": counts}


def signals(snapshot, record, since):
    """Actual Trace v1, Monitoring and Logging responses, bounded by traffic time."""
    w.candidate_policy(record)
    start = w.sample.utc(since)
    now = datetime.now(timezone.utc)
    require(start <= now, "future_traffic_window")
    trace = snapshot["trace"]
    require(re.fullmatch(r"[0-9a-f]{32}", trace.get("traceId", "")) is not None and trace.get("spans"), "empty_trace")
    valid_spans = {format(int(s["spanId"]), "016x") for s in trace["spans"]
                   if s.get("name") == "hipstershop.ProductCatalogService/ListProducts" and w.sample.utc(s["startTime"]) >= start}
    require(bool(valid_spans), "functional_trace_missing")
    logs = snapshot["logs"].get("entries", [])
    linked = []
    for entry in logs:
        body = entry.get("jsonPayload", {})
        if body.get("event") != "request.completed" or body.get("operation") != "/hipstershop.ProductCatalogService/ListProducts": continue
        require(entry.get("trace") == "projects/" + w.r.policy()["project"] + "/traces/" + trace["traceId"], "native_log_trace_link_missing")
        require(body.get("trace_id") == trace["traceId"] and entry.get("spanId") == body.get("span_id") in valid_spans, "log_span_correlation_mismatch")
        require(w.sample.utc(entry["timestamp"]) >= start and entry.get("logName") == "projects/" + w.r.policy()["project"] + "/logs/online-shop%2Fcatalog", "wrong_log_window_or_stream")
        resource = entry.get("resource", {})
        require(resource.get("type") == "k8s_container" and resource.get("labels", {}).get("namespace_name") == "dev"
                and resource["labels"].get("cluster_name") == "secure-delivery-platform"
                and resource["labels"].get("container_name") == "catalog", "wrong_log_runtime_resource")
        labels = entry.get("labels", {})
        require(labels.get("service.name") == "productcatalogservice" and labels.get("service.version") == w.r.REVISION
                and labels.get("deployment.environment.name") == "dev" and labels.get("release_set_id") == record["release_set_id"]
                and labels.get("component_digest") == record["components"][0]["digest"], "log_release_attribution_missing")
        linked.append(entry)
    require(bool(linked), "correlated_logs_missing")
    series = snapshot["metrics"].get("timeSeries", [])
    found = []
    for item in series:
        labels = item.get("metric", {}).get("labels", {})
        if labels.get("kind") != "server" or labels.get("operation") != "/hipstershop.ProductCatalogService/ListProducts": continue
        require(labels.get("service_name") == "productcatalogservice" and labels.get("service_version") == w.r.REVISION
                and labels.get("deployment_environment_name") == "dev" and labels.get("release_set_id") == record["release_set_id"]
                and labels.get("component_digest") == record["components"][0]["digest"], "metric_release_attribution_missing")
        points = [p for p in item.get("points", []) if w.sample.utc(p["interval"]["endTime"]) >= start
                  and float(p.get("value", {}).get("int64Value", p.get("value", {}).get("doubleValue", 0))) > 0]
        if points and "online_shop" in item["metric"]["type"] and "requests" in item["metric"]["type"]: found.append(item)
    require(bool(found), "nonempty_functional_metrics_missing")
    return {"signals": "passed", "native_trace_linkage": True, "linked_logs": len(linked), "functional_metric_series": len(found)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=("capacity", "runtime", "signals"))
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--candidate")
    parser.add_argument("--deployment-revision")
    parser.add_argument("--since")
    args = parser.parse_args()
    try:
        record = None
        if args.check in ("runtime", "signals"):
            record = w.r.read(args.candidate)
            w.candidate_policy(record)
        value = w.r.read(args.snapshot)
        if args.check == "capacity": result = capacity(value["nodes"], value["pods"])
        elif args.check == "runtime": result = runtime(value, record, args.deployment_revision)
        else: result = signals(value, record, args.since)
        print(json.dumps(result))
        return 3 if result.get("capacity_ready") is False else 0
    except (OSError, KeyError, ValueError, TypeError, AttributeError):
        print(json.dumps({"status": "failed", "reason": "acceptance_evidence_missing_or_inconsistent"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
