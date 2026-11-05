#!/usr/bin/env python3
"""Prepare and evaluate the complete dev shop; never creates releases or rollouts."""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("complete_release", ROOT / "cloudbuild/online-shop/complete.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
require = c.require
legacy = c.legacy
ap = legacy.module("catalog_capacity", HERE / "acceptance.py")

# Only these deployment executables may differ from a reused producer. The
# current deployment still reviews *all* trust files; shared release verification,
# profiles, runtime contracts, supporting policy and signing code must match both.
DEPLOYMENT_CODE = ("deploy/online-shop/complete.py", "deploy/online-shop/complete-acceptance.py")


def reviewed(record, revision):
    c.reviewed(revision)
    producing = record["configuration_revision"]
    require(re.fullmatch(c.r.SHA, producing or ""), "producing_revision_required")
    if producing != revision:
        with c.r.fetched(c.r.SDP, producing) as source:
            source.git("fetch", "--no-tags", c.r.SDP + ".git", "main")
            source.git("merge-base", "--is-ancestor", producing, "FETCH_HEAD")
            for name in c.TRUST_FILES:
                if name not in DEPLOYMENT_CODE:
                    require((ROOT / name).read_bytes().replace(b"\r\n", b"\n") == source.blob(name),
                            "incompatible_producing_trust_files")

def runtime_contract():
    value = c.r.read(HERE / "complete-runtime-v1.json")
    require(type(value.get("version")) is int and value["version"] == 1 and value["aml_revision"] == c.r.REVISION
            and value["source_sha256"] == c.profile()["contracts_sha256"]["kubernetes/online-shop.yaml"], "runtime_contract_binding")
    return value["documents"]

def meta(record, revision, identity, digest):
    return {"release.secure-delivery.dev/" + k:v for k,v in {
        "release-set-id":record["release_set_id"], "deployment-configuration":revision,
        "component":identity, "image-digest":digest, "environment":"dev",
        "application-revision":c.r.REVISION}.items()}

def collector_config(record):
    q = copy.deepcopy(c.r.read(HERE / "collector.json"))
    q["receivers"] = {"otlp": q["receivers"]["otlp"]}
    q["processors"] = {"memory_limiter":{"check_interval":"1s","limit_mib":512,"spike_limit_mib":64}, "batch":{"timeout":"1s","send_batch_size":128}}
    # pdata's inactive numeric oneof getter returns zero. Checking value_int
    # preserves existing nonzero INT64s; rewriting INT64 zero is a no-op. Convert
    # only exact, nonnegative integral sums in range, including DOUBLE zero.
    counters = ' or '.join('metric.name == "' + name + '"' for name in (
        "online_shop.transport.requests", "online_shop.transport.errors", "online_shop.business.operations"))
    q["processors"]["transform/integer_counters"] = {"error_mode":"propagate", "metric_statements":[{
        "context":"datapoint", "statements":[
            'set(datapoint.value_int, Int(datapoint.value_double)) where (' + counters + ')'
            ' and metric.type == METRIC_DATA_TYPE_SUM and metric.is_monotonic == true'
            ' and datapoint.value_int == 0 and datapoint.value_double >= 0'
            ' and datapoint.value_double < 9223372036854775807'
            ' and datapoint.value_double == Int(datapoint.value_double)']} ]}
    q["service"]["pipelines"] = {}
    for row in record["components"]:
        identity = row["id"]
        attributes = [{"key":k,"value":v,"action":"upsert"} for k,v in {
            "service.name":identity,"service.namespace":"online-shop","service.version":c.r.REVISION if row["role"] == "application" else c.redis_policy()["redis_version"],
            "deployment.environment.name":"dev","release_set_id":record["release_set_id"],"component_digest":row["digest"]}.items()]
        attributes += [a for a in c.r.read(HERE / "collector.json")["processors"]["resource/catalog"]["attributes"]
                       if a["key"].startswith(("cloud.","k8s."))]
        q["processors"]["resource/" + identity] = {"attributes":attributes}
        container = "catalog" if identity == "productcatalogservice" else "redis" if identity == "redis-cart" else "server"
        receiver = copy.deepcopy(c.r.read(HERE / "collector.json")["receivers"]["file_log/catalog"])
        receiver["include"] = ["/var/log/pods/dev_" + identity + "-*/" + container + "/*.log"]
        receiver["operators"].insert(1, {"type":"filter","expr":'attributes["log.iostream"] != "stdout"'})
        if identity == "redis-cart":
            # Native Redis has operational text logs and INFO metrics, not fake
            # server traces. Never collect command arguments, values, keys or PII.
            receiver["operators"] = [receiver["operators"][0],receiver["operators"][1]]
        else:
            receiver["operators"].insert(3, {"type":"filter", "expr":'body["service.name"] != "' + identity
                + '" or body["service.version"] != "' + c.r.REVISION + '"'})
            condition = ('resource.attributes["service.name"] != "' + identity + '" or resource.attributes["service.version"] != "'
                         + c.r.REVISION + '" or resource.attributes["deployment.environment.name"] != "dev"')
            q["processors"]["filter/" + identity] = {"error_mode":"propagate", "traces":{"span":[condition]},"metrics":{"metric":[condition]}}
            for signal in ("traces","metrics"):
                normalization = (["transform/integer_counters"]
                    if signal == "metrics" and identity in ("currencyservice","paymentservice") else [])
                q["service"]["pipelines"][signal + "/" + identity] = {"receivers":["otlp"],
                    "processors":["memory_limiter","filter/" + identity,*normalization,"resource/" + identity,"batch"],"exporters":["googlecloud"]}
        q["receivers"]["file_log/" + identity] = receiver
        q["service"]["pipelines"]["logs/" + identity] = {"receivers":["file_log/" + identity],
            "processors":["memory_limiter","resource/" + identity,"batch"],"exporters":["googlecloud"]}
    return q


def redis_metrics_config(record):
    # One Recreate singleton scrapes INFO. A DaemonSet scraper would emit the
    # same Redis series once per node and violate the no-duplicate contract.
    q=collector_config(record)
    q["extensions"]={"health_check":q["extensions"]["health_check"]}
    q["receivers"]={"redis":{"endpoint":"redis-cart.dev.svc.cluster.local:6379","collection_interval":"10s"}}
    q["processors"]={k:v for k,v in q["processors"].items() if k in ("memory_limiter","resource/redis-cart","batch")}
    q["processors"]["memory_limiter"].update(limit_mib=128,spike_limit_mib=32)
    q["service"]={"extensions":["health_check"],"pipelines":{"metrics/redis-cart":{"receivers":["redis"],
        "processors":["memory_limiter","resource/redis-cart","batch"],"exporters":["googlecloud"]}}}
    return q

ENDPOINT_HOST = "shop.runtimeplatforms.dev"
ENDPOINT_NAME = "shop-dev-edge"


def endpoint_resources(record, revision):
    annotations = meta(record,revision,"frontend",next(x["digest"] for x in record["components"] if x["id"]=="frontend"))
    def resource(api,kind,name,spec,extra=None):
        return {"apiVersion":api,"kind":kind,"metadata":{"name":name,"namespace":"dev",
            "annotations":{**annotations,**(extra or {})}},"spec":spec}
    parent={"name":ENDPOINT_NAME,"namespace":"dev"}
    target={"group":"","kind":"Service","name":"frontend"}
    return [
      resource("gateway.networking.k8s.io/v1","Gateway",ENDPOINT_NAME,{
        "gatewayClassName":"gke-l7-global-external-managed",
        "addresses":[{"type":"NamedAddress","value":ENDPOINT_NAME}],
        "listeners":[{"name":"http","hostname":ENDPOINT_HOST,"port":80,"protocol":"HTTP","allowedRoutes":{"namespaces":{"from":"Same"},"kinds":[{"group":"gateway.networking.k8s.io","kind":"HTTPRoute"}]}},
          {"name":"https","hostname":ENDPOINT_HOST,"port":443,"protocol":"HTTPS","allowedRoutes":{"namespaces":{"from":"Same"},"kinds":[{"group":"gateway.networking.k8s.io","kind":"HTTPRoute"}]}}]},
        {"networking.gke.io/certmap":ENDPOINT_NAME}),
      resource("gateway.networking.k8s.io/v1","HTTPRoute","shop-https",{
        "parentRefs":[{**parent,"sectionName":"https"}],"hostnames":[ENDPOINT_HOST],
        "rules":[{"matches":[{"path":{"type":"PathPrefix","value":"/"}}],"backendRefs":[{"group":"","kind":"Service","name":"frontend","port":80,"weight":1}]}]}),
      resource("gateway.networking.k8s.io/v1","HTTPRoute","shop-http-redirect",{
        "parentRefs":[{**parent,"sectionName":"http"}],"hostnames":[ENDPOINT_HOST],
        "rules":[{"filters":[{"type":"RequestRedirect","requestRedirect":{"scheme":"https","hostname":ENDPOINT_HOST,"statusCode":301}}]}]}),
      resource("networking.gke.io/v1","GCPGatewayPolicy",ENDPOINT_NAME,{
        "default":{"sslPolicy":ENDPOINT_NAME},"targetRef":{"group":"gateway.networking.k8s.io","kind":"Gateway","name":ENDPOINT_NAME}}),
      resource("networking.gke.io/v1","GCPBackendPolicy",ENDPOINT_NAME,{
        "default":{"securityPolicy":ENDPOINT_NAME,"logging":{"enabled":True,"sampleRate":1000000}},"targetRef":target}),
      resource("networking.gke.io/v1","HealthCheckPolicy",ENDPOINT_NAME,{
        "default":{"checkIntervalSec":15,"timeoutSec":5,"healthyThreshold":2,"unhealthyThreshold":2,
          "config":{"type":"HTTP","httpHealthCheck":{"portSpecification":"USE_FIXED_PORT","port":8080,"requestPath":"/_healthz"}}},"targetRef":target})]


def render(record, revision, refs):
    c.validate_candidate(record, record["configuration_revision"], refs)
    require(re.fullmatch(c.r.SHA, revision or ""), "invalid_deployment_revision")
    documents = copy.deepcopy(runtime_contract())
    rows = {x["id"]:x for x in record["components"]}
    for d in documents:
        identity = d["metadata"]["name"]
        require(identity in rows and d["kind"] in ("Deployment","Service","ServiceAccount"), "unexpected_runtime_member")
        d["metadata"]["namespace"] = "dev"
        d["metadata"]["annotations"] = meta(record, revision, identity, rows[identity]["digest"])
        if d["kind"] == "Service":
            require(d["spec"].get("type","ClusterIP") == "ClusterIP", "external_service_forbidden")
            d["spec"]["type"] = "ClusterIP"
        elif d["kind"] == "ServiceAccount":
            d["automountServiceAccountToken"] = False
        else:
            d["spec"]["replicas"] = 1
            d["spec"]["strategy"] = ({"type":"Recreate"} if identity == "redis-cart" else
                {"type":"RollingUpdate","rollingUpdate":{"maxSurge":1,"maxUnavailable":0}})
            template = d["spec"]["template"]
            template["metadata"]["annotations"] = meta(record, revision, identity, rows[identity]["digest"])
            pod = template["spec"]
            require(len(pod["containers"]) == 1 and not pod.get("initContainers") and not pod.get("ephemeralContainers"), "unexpected_runtime_container")
            pod["serviceAccountName"] = identity
            pod["automountServiceAccountToken"] = False
            pod["securityContext"]["seccompProfile"] = {"type":"RuntimeDefault"}
            pod["terminationGracePeriodSeconds"] = 15 if identity == "redis-cart" else 30
            app = pod["containers"][0]
            app["image"] = rows[identity]["repository"] + "@" + rows[identity]["digest"]
            if identity != "redis-cart":
                if identity == "productcatalogservice":app.update(name="catalog",workingDir="/src")
                env = {e["name"]:e["value"] for e in app.get("env",[])}
                env.pop("ENABLE_PROFILER",None)
                env.update(ONLINE_SHOP_TELEMETRY_ENABLED="true",ONLINE_SHOP_VERSION=rows[identity]["source"]["revision"],
                    ONLINE_SHOP_ENVIRONMENT="dev",OTEL_EXPORTER_OTLP_ENDPOINT="http://catalog-collector.dev.svc.cluster.local:4317",
                    OTEL_EXPORTER_OTLP_PROTOCOL="grpc",OTEL_TRACES_EXPORTER="otlp",OTEL_METRICS_EXPORTER="otlp",
                    OTEL_TRACES_SAMPLER_ARG="0.1",OTEL_METRIC_EXPORT_INTERVAL="10000",PYTHONDONTWRITEBYTECODE="1")
                if identity in ("currencyservice","paymentservice","emailservice","recommendationservice","productcatalogservice","shippingservice"):
                    env["DISABLE_PROFILER"] = "1"
                app["env"] = [{"name":k,"value":v} for k,v in sorted(env.items())]
                app["startupProbe"] = {k:v for k,v in app["readinessProbe"].items() if k not in ("initialDelaySeconds","periodSeconds")}
                app["startupProbe"].update(periodSeconds=5,failureThreshold=36 if identity == "adservice" else 24)
                pod.setdefault("volumes",[]).append({"name":"tmp","emptyDir":{"sizeLimit":"64Mi"}})
                app.setdefault("volumeMounts",[]).append({"name":"tmp","mountPath":"/tmp"})
    config = json.dumps(collector_config(record),indent=2,sort_keys=True) + "\n"
    name = "shop-collector-" + c.r.sha(config.encode())[:12]
    # Preserve the existing supporting identity/service/DaemonSet and its narrow
    # dev KSA->GSA binding. The approved Collector image itself is unchanged.
    meta_support = meta(record, revision,"collector",legacy.policy()["collector"]["manifest_digest"])
    documents += [{"apiVersion":"v1","kind":"ServiceAccount","metadata":{"name":"redis-cart","namespace":"dev",
        "annotations":meta(record,revision,"redis-cart",rows["redis-cart"]["digest"]),},"automountServiceAccountToken":False},
      {"apiVersion":"v1","kind":"ServiceAccount","metadata":{"name":"catalog-collector","namespace":"dev",
        "annotations":{"iam.gke.io/gcp-service-account":"catalog-telemetry@" + c.r.policy()["project"] + ".iam.gserviceaccount.com"}},"automountServiceAccountToken":False},
      {"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":name,"namespace":"dev","annotations":meta_support},"immutable":True,"data":{"config.json":config}},
      {"apiVersion":"apps/v1","kind":"DaemonSet","metadata":{"name":"catalog-collector","namespace":"dev","annotations":meta_support},"spec":{
        "updateStrategy":{"type":"RollingUpdate","rollingUpdate":{"maxSurge":0,"maxUnavailable":1}},"selector":{"matchLabels":{"app":"catalog-collector"}},
        "template":{"metadata":{"labels":{"app":"catalog-collector"},"annotations":meta_support},"spec":{
          "serviceAccountName":"catalog-collector","automountServiceAccountToken":False,
          "nodeSelector":{"kubernetes.io/os":"linux","kubernetes.io/arch":"amd64","iam.gke.io/gke-metadata-server-enabled":"true"},
          "securityContext":{"seccompProfile":{"type":"RuntimeDefault"}},"terminationGracePeriodSeconds":30,
          "containers":[{"name":"collector","image":legacy.policy()["collector"]["mirror_image"],"args":["--config=/etc/otelcol/config.json"],
            "securityContext":{"runAsUser":0,"runAsNonRoot":False,"privileged":False,"readOnlyRootFilesystem":True,"allowPrivilegeEscalation":False,"capabilities":{"drop":["ALL"]}},
            "resources":{"requests":{"cpu":"300m","memory":"512Mi"},"limits":{"cpu":"800m","memory":"768Mi"}},
            "ports":[{"containerPort":4317},{"containerPort":13133}],
            "startupProbe":{"httpGet":{"path":"/","port":13133},"periodSeconds":2,"failureThreshold":30},
            "readinessProbe":{"httpGet":{"path":"/","port":13133}},"livenessProbe":{"httpGet":{"path":"/","port":13133}},
            "volumeMounts":[{"name":"config","mountPath":"/etc/otelcol","readOnly":True},{"name":"podlogs","mountPath":"/var/log/pods","readOnly":True},{"name":"cursors","mountPath":"/var/lib/otelcol"}]}],
          "volumes":[{"name":"config","configMap":{"name":name}},{"name":"podlogs","hostPath":{"path":"/var/log/pods","type":"Directory"}},{"name":"cursors","emptyDir":{"sizeLimit":"128Mi"}}]}}}},
      {"apiVersion":"v1","kind":"Service","metadata":{"name":"catalog-collector","namespace":"dev","annotations":meta_support},
       "spec":{"type":"ClusterIP","selector":{"app":"catalog-collector"},"ports":[{"name":"otlp-grpc","port":4317,"targetPort":4317}]}}]
    metrics_raw=json.dumps(redis_metrics_config(record),indent=2,sort_keys=True)+"\n"
    metrics_name="shop-redis-metrics-"+c.r.sha(metrics_raw.encode())[:12]
    metrics_meta=meta(record,revision,"redis-metrics-collector",legacy.policy()["collector"]["manifest_digest"])
    agent=copy.deepcopy(next(d for d in documents if d["kind"]=="DaemonSet"))
    agent["kind"]="Deployment";agent["metadata"]={"name":"shop-redis-metrics","namespace":"dev","annotations":metrics_meta}
    agent["spec"].pop("updateStrategy");agent["spec"].update(replicas=1,strategy={"type":"Recreate"},selector={"matchLabels":{"app":"shop-redis-metrics"}})
    template=agent["spec"]["template"];template["metadata"]={"labels":{"app":"shop-redis-metrics"},"annotations":metrics_meta}
    pod=template["spec"];pod["volumes"]=[{"name":"config","configMap":{"name":metrics_name}}]
    app=pod["containers"][0];app["volumeMounts"]=[{"name":"config","mountPath":"/etc/otelcol","readOnly":True}]
    app["ports"]=[{"containerPort":13133}]
    app["securityContext"].update(runAsUser=10001,runAsNonRoot=True)
    app["resources"]={"requests":{"cpu":"100m","memory":"192Mi"},"limits":{"cpu":"300m","memory":"256Mi"}}
    documents += [agent,{"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":metrics_name,"namespace":"dev","annotations":metrics_meta},
                         "immutable":True,"data":{"config.json":metrics_raw}}]
    documents += endpoint_resources(record,revision)
    return sorted(documents,key=lambda d:(d["kind"],d["metadata"]["name"]))

def rendered(record, revision, refs, context):
    labels = legacy.clouddeploy_labels(context)
    docs = render(record,revision,refs)
    for d in docs:
        if d["kind"] not in ("Deployment","DaemonSet","Service"):continue
        metadata = [d["metadata"]]
        if d["kind"] in ("Deployment","DaemonSet"):metadata.append(d["spec"]["template"]["metadata"])
        for value in metadata:value["labels"] = {**value.get("labels",{}),**labels}
    return docs

def inventory(docs, record, revision, refs, context=None):
    expected = render(record,revision,refs) if context is None else rendered(record,revision,refs,context)
    require(c.r.canonical(docs) == c.r.canonical(expected), "complete_rendered_inventory_mismatch")
    return {"applications":len(c.APPS),"dependencies":["redis-cart"],"supporting":["collector"],"loadgenerator":"excluded"}

def capacity(snapshot, documents):
    # First-fit decreasing on each actual eligible node; all existing non-shop
    # requests remain charged. Count *both* old/new application replicas, singleton
    # Redis and one supporting agent per node. No aggregate-only capacity claim.
    bins=[]
    for node in snapshot["nodes"]["items"]:
        labels=node["metadata"]["labels"]
        require(labels.get("kubernetes.io/os")=="linux" and labels.get("kubernetes.io/arch")=="amd64"
            and labels.get("iam.gke.io/gke-metadata-server-enabled")=="true" and not node["spec"].get("taints")
            and not node["spec"].get("unschedulable") and any(x["type"]=="Ready" and x["status"]=="True" for x in node["status"]["conditions"]),"node_constraints_or_readiness")
        current=[p for p in snapshot["pods"]["items"] if p.get("spec",{}).get("nodeName")==node["metadata"]["name"]
            and p.get("status",{}).get("phase") not in ("Succeeded","Failed")
            and not (p["metadata"].get("namespace")=="dev" and p["metadata"].get("labels",{}).get("app") in (*c.MEMBERS,"catalog-collector","shop-redis-metrics"))]
        alloc=node["status"]["allocatable"]
        bins.append([ap.quantity(alloc["cpu"],True)-sum(ap.pod_requests(p,"cpu") for p in current),
            ap.quantity(alloc["memory"])-sum(ap.pod_requests(p,"memory") for p in current),int(alloc["pods"])-len(current)])
    require(bins,"no_nodes")
    demand=[]
    for d in documents:
        if d["kind"] not in ("Deployment","DaemonSet"):continue
        pod=d["spec"]["template"]
        n=len(bins) if d["kind"]=="DaemonSet" else 1 if d["metadata"]["name"]=="redis-cart" else 2
        need=[ap.pod_requests(pod,"cpu"),ap.pod_requests(pod,"memory"),1]
        if d["kind"]=="DaemonSet":
            # Reserve its actual placement on every node, not a generic free bin.
            for b in bins:
                for i in range(3):b[i]-=need[i]
        else:demand += [need for _ in range(1 if d["metadata"]["name"]=="shop-redis-metrics" else n)]
    # Sample has no requests: keep an explicit allowance plus a negative-test
    # slot and unallocated CPU/memory headroom; these are reserves, not limits.
    demand += [[100,128*1024**2,0] for _ in range(3)] + [[200,256*1024**2,1],[300,512*1024**2,0]]
    failures=sum(any(x<0 for x in b) for b in bins)
    for need in sorted(demand,key=lambda x:(x[0],x[1]),reverse=True):
        index=next((i for i,b in enumerate(bins) if all(have>=amount for have,amount in zip(b,need))),None)
        if index is None:failures+=1
        else:bins[index]=[have-amount for have,amount in zip(bins[index],need)]
    pending=[p for p in snapshot["pods"]["items"] if not p.get("spec",{}).get("nodeName") and p.get("status",{}).get("phase") not in ("Succeeded","Failed")]
    return {"capacity_ready":not failures and not pending,"unscheduled_budget_items":failures,"unassigned_pods":len(pending),
        "node_count":len(bins),"application_overlap_replicas":2,"redis_overlap_replicas":1,"collector_per_node":1,
        "remaining_bins":[{"cpu_m":float(b[0]),"memory_mi":float(b[1]/1024**2),"slots":b[2]} for b in bins]}

def prepare(record, revision, refs, value, release, output, cloud):
    reviewed(record, revision)
    context={"release_resource":release,"target_resource":"projects/"+c.r.policy()["project"]+"/locations/us-central1/targets/dev"}
    legacy.clouddeploy_labels(context)
    c.verify(record,record["configuration_revision"],value,refs,cloud)
    trusted=c.attest(record,record["configuration_revision"],value,refs,cloud,inspect=True)
    require(trusted["status"]=="trusted","incomplete_trust")
    legacy.verify_support(cloud,"projects/"+c.r.policy()["project"]+"/occurrences/2b1c6135-42d3-453a-9942-f473dea60444")
    docs=render(record,revision,refs);inventory(docs,record,revision,refs)
    output=Path(output);require(not output.exists(),"output_directory_must_not_exist")
    (output/"rendered/dev").mkdir(parents=True)
    raw=json.dumps({"apiVersion":"v1","kind":"List","items":docs},indent=2)+"\n"
    (output/"rendered/dev/shop.json").write_text(raw,encoding="utf-8",newline="\n")
    (output/"skaffold.yaml").write_bytes((HERE/"complete-skaffold.yaml").read_bytes().replace(b"\r\n",b"\n"))
    result={"release_set_id":record["release_set_id"],"deployment_revision":revision,"clouddeploy_release":release,
        "rendered_inventory_sha256":c.r.sha(c.r.canonical(rendered(record,revision,refs,context))),
        "prepared_bytes_sha256":c.r.sha(raw.encode()),"trusted":trusted,"mutation_performed":False}
    (output/"preparation.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result

def endpoint_evidence(item, now):
    """Reviewed readbacks, not labels or unbound readiness assertions."""
    require(now-timedelta(minutes=5)<=legacy.sample.utc(item["observed_at"])<=now+timedelta(seconds=30)
        and bool(item["evidence_ref"]),"endpoint_evidence_stale")
    require(item["project"]==c.r.policy()["project"] and item["hostname"]==ENDPOINT_HOST
        and item["scope"]=="global","endpoint_scope_mismatch")
    address=item["address"]
    require(address["name"]==ENDPOINT_NAME and address["ipVersion"]=="IPV4"
        and address["addressType"]=="EXTERNAL" and ipaddress.ip_address(address["address"]).version==4
        and ipaddress.ip_address(address["address"]).is_global,"endpoint_address_mismatch")
    require(item["dns"]=={"name":ENDPOINT_HOST+".","type":"A","rrdatas":[address["address"]],
        "delegation_matches_reviewed_child_zone":True},"endpoint_dns_mismatch")
    require(item["ssl_policy"]=={"name":ENDPOINT_NAME,"profile":"MODERN","minTlsVersion":"TLS_1_2"},"endpoint_tls_policy_mismatch")
    cert=item["certificate"]
    require(cert["name"] in {"projects/"+identity+"/locations/global/certificates/"+ENDPOINT_NAME
        for identity in (c.r.policy()["project"],c.r.policy()["project_number"])}
        and cert["managed"]["domains"]==[ENDPOINT_HOST] and cert["managed"]["state"]=="ACTIVE"
        and legacy.sample.utc(cert["expireTime"])>=now+timedelta(minutes=75),"endpoint_certificate_not_active")
    require(item["certificate_map"]=={"name":ENDPOINT_NAME,"hostname":ENDPOINT_HOST,"certificates":[cert["name"]]},"endpoint_certificate_map_mismatch")
    policy=item["armor"]
    require(policy["name"]==ENDPOINT_NAME and policy["type"]=="CLOUD_ARMOR","endpoint_armor_scope")
    rules={r["priority"]:r for r in policy["rules"]}
    require(len(policy["rules"])==len(rules)==4 and set(rules)=={100,1000,2000,2147483647},"endpoint_armor_rules")
    require(rules[100]["action"]=="deny(403)" and not rules[100].get("preview",False)
        and rules[100]["match"]=={"expr":{"expression":"request.path == '/__sdp_edge_probe__'"}},"endpoint_probe_policy")
    waf="evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1}) || evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})"
    require(rules[1000]["action"]=="deny(403)" and rules[1000].get("preview") is True
        and rules[1000]["match"]=={"expr":{"expression":waf}},"endpoint_waf_preview")
    any_ip={"versionedExpr":"SRC_IPS_V1","config":{"srcIpRanges":["*"]}}
    require(rules[2000]["action"]=="throttle" and rules[2000].get("preview") is True
        and rules[2000]["match"]==any_ip and rules[2000]["rateLimitOptions"]=={
            "conformAction":"allow","exceedAction":"deny(429)","enforceOnKey":"IP",
            "rateLimitThreshold":{"count":1200,"intervalSec":60}},"endpoint_rate_preview")
    require(rules[2147483647]["action"]=="allow" and not rules[2147483647].get("preview",False)
        and rules[2147483647]["match"]==any_ip,"endpoint_default_policy")
    return True


def evaluate(snapshot, record, revision, refs, release, now=None):
    c.validate_candidate(record,record["configuration_revision"],refs)
    now=now or datetime.now(timezone.utc);checks=[]
    def check(name,ok):checks.append({"id":name,"status":"PASS" if ok else "FAIL"})
    check("request_binding",snapshot.get("request")=={"release_set_id":record["release_set_id"],"deployment_revision":revision,"target":"dev","action":"deploy","clouddeploy_release":release})
    required={"release":["independently_verified","all_eleven_signatures_verified","redis_provenance_approved","collector_independently_verified"],
        "admission":["cluster_enforced","exact_attestor_required","no_bypass"],
        "target":["snapshot_matches_current","capacity_bin_packing_passed","metadata_and_wif_ready","all_stdout_exclusions_ready","no_duplicate_sinks","no_rollout_conflict","sample_baseline_preserved","gateway_api_ready","endpoint_infrastructure_reviewed","dns_delegation_reviewed","certificate_active","armor_preview_policy_ready","frontend_only_exposure"],
        "caller":["rollout_create","deployment_act_as"],"review":["continue"]}
    for section,fields in required.items():
        value=snapshot.get(section,{})
        try:fresh=now-timedelta(minutes=5)<=legacy.sample.utc(value.get("observed_at"))<=now+timedelta(seconds=30)
        except (ValueError,TypeError):fresh=False
        check(section+"_fresh_bound",fresh and bool(value.get("evidence_ref")) and value.get("release_set_id")==record["release_set_id"] and value.get("deployment_revision")==revision)
        for field in fields:check(section+"_"+field,value.get(field) is True)
    try:
        edge=snapshot.get("endpoint",{})
        require(edge.get("release_set_id")==record["release_set_id"] and edge.get("deployment_revision")==revision,"endpoint_release_binding")
        check("endpoint_readbacks",endpoint_evidence(edge,now))
    except (ValueError,KeyError,TypeError,AttributeError):check("endpoint_readbacks",False)
    try:c.redis_admission();approved=True
    except ValueError:approved=False
    check("reviewed_redis_admission",approved)
    context=snapshot.get("clouddeploy",{})
    try:
        fresh=now-timedelta(minutes=5)<=legacy.sample.utc(context.get("observed_at"))<=now+timedelta(seconds=30)
        check("clouddeploy_context",fresh and bool(context.get("evidence_ref")) and context.get("release_resource")==release and context.get("release_snapshot_matches_current") is True
            and context.get("release_set_id")==record["release_set_id"] and context.get("deployment_revision")==revision)
        actual=snapshot.get("rendered_documents")
        redirect = next((doc for doc in actual if doc["kind"] == "HTTPRoute"
            and doc["metadata"]["name"] == "shop-http-redirect"
            and doc["metadata"]["namespace"] == "dev"), None)
        # GKE rejects explicit redirect ports during reconciliation, after Kubernetes admission.
        check("gke_redirect_implicit_port", redirect is not None and all(
            "port" not in entry.get("requestRedirect", {})
            for rule in redirect["spec"]["rules"] for entry in rule.get("filters", [])))
        inventory(actual,record,revision,refs,context)
        check("exact_complete_inventory",True)
        expected=c.r.sha(c.r.canonical(rendered(record,revision,refs,context)))
        check("immutable_rendered_commitment",snapshot.get("release_annotations",{}).get("rendered_inventory_sha256")==expected==c.r.sha(c.r.canonical(actual)))
    except (ValueError,KeyError,TypeError,AttributeError):check("exact_complete_inventory",False)
    for label in ("source","rendered","resolved_skaffold"):
        item=snapshot.get("artifacts",{}).get(label,{})
        try:valid=now-timedelta(minutes=5)<=legacy.sample.utc(item.get("observed_at"))<=now+timedelta(seconds=30) and legacy.sample.utc(item.get("retention_expires_at"))>=now+timedelta(minutes=75)
        except (ValueError,TypeError):valid=False
        uri=item.get("uri","")
        check(label+"_protected_bytes",valid and bool(item.get("evidence_ref")) and item.get("available") is True and item.get("live_generation") is True
            and re.fullmatch(r"gs://"+re.escape(c.r.policy()["project"]+"-clouddeploy")+r"/[^#]+#[1-9][0-9]*",uri) is not None
            and re.fullmatch(r"[0-9a-f]{64}",item.get("expected_sha256","")) is not None and item.get("actual_sha256")==item.get("expected_sha256")
            and item.get("release_set_id")==record["release_set_id"] and item.get("deployment_revision")==revision)
        if label=="source":check("immutable_source_hash",snapshot.get("release_annotations",{}).get("source_sha256")==item.get("expected_sha256"))
    return {"decision":"READY" if all(x["status"]=="PASS" for x in checks) else "BLOCKED","checks":checks,"target":"dev","mutation_performed":False}

def gateway_admission_statuses(stderr, endpoint):
    """Read kubectl's HTTP response trace for this Gateway's dry-run writes."""
    path = "/apis/gateway.networking.k8s.io/v1/namespaces/dev/gateways"
    expected_paths = {"POST": path, "PATCH": f"{path}/{ENDPOINT_NAME}"}
    for method, url, status in re.findall(
            r'"Response" verb="(POST|PATCH)" url="([^"]+)" status="([0-9]{3})\b',
            stderr.decode(errors="replace")):
        target = urlsplit(url)
        if (target.scheme == "https" and target.netloc == endpoint
                and target.path == expected_paths[method] and parse_qs(target.query).get("dryRun") == ["All"]):
            yield int(status)


def gateway_dry_run(gateway, cloud):
    """Use Skaffold's client-side apply semantics with server-side admission."""
    env = c.r.read(ROOT / "deploy/environments.json")
    cluster_path = f"projects/{env['project']}/locations/{env['location']}/clusters/{env['cluster']}"
    cluster = c.r.decode(cloud.request("https://container.googleapis.com/v1/" + cluster_path))
    require(cluster["name"] == env["cluster"] and cluster["location"] == env["location"],
            "gateway_dry_run_cluster_mismatch")
    endpoint = str(ipaddress.IPv4Address(cluster["endpoint"]))
    kubectl = shutil.which("kubectl")
    auth_plugin = shutil.which("gke-gcloud-auth-plugin")
    require(kubectl and auth_plugin, "gateway_dry_run_tools_unavailable")
    kubeconfig = {
        "apiVersion": "v1", "kind": "Config",
        "clusters": [{"name": "reviewed-dev", "cluster": {
            "server": f"https://{endpoint}",
            "certificate-authority-data": cluster["masterAuth"]["clusterCaCertificate"],
        }}],
        "contexts": [{"name": "reviewed-dev", "context": {
            "cluster": "reviewed-dev", "user": "gke", "namespace": "dev",
        }}],
        "current-context": "reviewed-dev",
        "users": [{"name": "gke", "user": {"exec": {
            "apiVersion": "client.authentication.k8s.io/v1beta1",
            "command": auth_plugin, "interactiveMode": "Never", "provideClusterInfo": True,
        }}}],
    }
    with TemporaryDirectory() as directory:
        config = Path(directory) / "kubeconfig.json"
        config.write_bytes(c.r.canonical(kubeconfig))
        command = [kubectl, f"--kubeconfig={config}", f"--cache-dir={Path(directory) / 'cache'}"]

        def admit(args, manifest=None):
            result = subprocess.run(
                command + args + ["--dry-run=server", "--request-timeout=30s", "--v=6", "-o", "json"],
                input=manifest, capture_output=True, timeout=90, env={**os.environ, "KUBECTL_KUBERC": "false"})
            statuses = list(gateway_admission_statuses(result.stderr, endpoint))
            # kubectl may retry a conflict internally, even in dry-run mode.
            require(409 not in statuses and b"(Conflict)" not in result.stderr, "gateway_dry_run_http_409")
            require(result.returncode == 0, "gateway_dry_run_failed")
            admitted = c.r.decode(result.stdout)
            require(admitted["kind"] == "Gateway" and admitted["metadata"]["name"] == ENDPOINT_NAME
                    and admitted["metadata"]["namespace"] == "dev", "gateway_dry_run_response_mismatch")
            return admitted, statuses

        admitted, statuses = admit(["apply", "--server-side=false", "-f", "-"], c.r.canonical(gateway))
        if not statuses:
            # A no-op client-side apply can stop after GET. Run admission for the same
            # resource version without changing its contents or accepting a concurrent update.
            version = admitted["metadata"]["resourceVersion"]
            require(isinstance(version, str) and version, "gateway_dry_run_resource_version_missing")
            patch = json.dumps({"metadata": {"resourceVersion": version}})
            _, statuses = admit(["patch", "gateway", ENDPOINT_NAME, "--type=merge", "--patch=" + patch,
                                 "--field-manager=kubectl-client-side-apply"])
        require(bool(statuses) and all(status in (200, 201) for status in statuses), "gateway_dry_run_failed")


def preflight(snapshot, record, revision, refs, release, cloud):
    result = evaluate(snapshot, record, revision, refs, release)
    if result["decision"] != "READY":
        return result
    gateway = next(doc for doc in snapshot["rendered_documents"] if doc["kind"] == "Gateway")
    try:
        gateway_dry_run(gateway, cloud)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError) as error:
        result["decision"] = "BLOCKED"
        result["checks"].append({"id": "gateway_server_dry_run", "status": "FAIL"})
        reason = str(error)
        result["reason"] = reason if reason in ("gateway_dry_run_http_409", "gateway_dry_run_tools_unavailable") else "gateway_dry_run_failed"
        return result
    # The admission request can outlast the snapshot's freshness window.
    result = evaluate(snapshot, record, revision, refs, release)
    result["checks"].append({"id": "gateway_server_dry_run", "status": "PASS"})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("prepare","preflight"))
    for name in ("candidate","deployment-revision","clouddeploy-release","output-dir","snapshot"):parser.add_argument("--"+name,required=name in ("candidate","deployment-revision","clouddeploy-release"))
    args=parser.parse_args()
    try:
        record=c.r.read(args.candidate)
        reviewed(record,args.deployment_revision)
        with c.r.fetched(c.r.AML,c.r.REVISION) as source:value=c.plans(source);refs=c.references(source,value)
        c.validate_candidate(record,record["configuration_revision"],refs)
        if args.action=="prepare":result=prepare(record,args.deployment_revision,refs,value,args.clouddeploy_release,args.output_dir,c.r.Cloud())
        else:
            cloud = c.r.Cloud()
            c.verify(record,record["configuration_revision"],value,refs,cloud)
            result=preflight(c.r.read(args.snapshot),record,args.deployment_revision,refs,args.clouddeploy_release,cloud)
        print(json.dumps(result,sort_keys=True));return 3 if result.get("decision")=="BLOCKED" else 0
    except (OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.SubprocessError):
        print(json.dumps({"decision":"BLOCKED","reason":"complete_policy_or_evidence_check_failed","mutation_performed":False}));return 3

if __name__=="__main__":raise SystemExit(main())
