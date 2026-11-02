#!/usr/bin/env python3
"""Prepare and evaluate the complete dev shop; never creates releases or rollouts."""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("complete_release", ROOT / "cloudbuild/online-shop/complete.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
require = c.require
legacy = c.legacy
ap = legacy.module("catalog_capacity", HERE / "acceptance.py")

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
                q["service"]["pipelines"][signal + "/" + identity] = {"receivers":["otlp"],
                    "processors":["memory_limiter","filter/" + identity,"resource/" + identity,"batch"],"exporters":["googlecloud"]}
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
    c.reviewed(revision)
    if record["configuration_revision"]!=revision:c.reviewed(record["configuration_revision"])
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

def evaluate(snapshot, record, revision, refs, release, now=None):
    c.validate_candidate(record,record["configuration_revision"],refs)
    now=now or datetime.now(timezone.utc);checks=[]
    def check(name,ok):checks.append({"id":name,"status":"PASS" if ok else "FAIL"})
    check("request_binding",snapshot.get("request")=={"release_set_id":record["release_set_id"],"deployment_revision":revision,"target":"dev","action":"deploy","clouddeploy_release":release})
    required={"release":["independently_verified","all_eleven_signatures_verified","redis_provenance_approved","collector_independently_verified"],
        "admission":["cluster_enforced","exact_attestor_required","no_bypass"],
        "target":["snapshot_matches_current","capacity_bin_packing_passed","metadata_and_wif_ready","all_stdout_exclusions_ready","no_duplicate_sinks","no_rollout_conflict","sample_baseline_preserved"],
        "caller":["rollout_create","deployment_act_as"],"review":["continue"]}
    for section,fields in required.items():
        value=snapshot.get(section,{})
        try:fresh=now-timedelta(minutes=5)<=legacy.sample.utc(value.get("observed_at"))<=now+timedelta(seconds=30)
        except (ValueError,TypeError):fresh=False
        check(section+"_fresh_bound",fresh and bool(value.get("evidence_ref")) and value.get("release_set_id")==record["release_set_id"] and value.get("deployment_revision")==revision)
        for field in fields:check(section+"_"+field,value.get(field) is True)
    try:c.redis_admission();approved=True
    except ValueError:approved=False
    check("reviewed_redis_admission",approved)
    context=snapshot.get("clouddeploy",{})
    try:
        fresh=now-timedelta(minutes=5)<=legacy.sample.utc(context.get("observed_at"))<=now+timedelta(seconds=30)
        check("clouddeploy_context",fresh and bool(context.get("evidence_ref")) and context.get("release_resource")==release and context.get("release_snapshot_matches_current") is True
            and context.get("release_set_id")==record["release_set_id"] and context.get("deployment_revision")==revision)
        actual=snapshot.get("rendered_documents")
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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("prepare","preflight"))
    for name in ("candidate","deployment-revision","clouddeploy-release","output-dir","snapshot"):parser.add_argument("--"+name,required=name in ("candidate","deployment-revision","clouddeploy-release"))
    args=parser.parse_args()
    try:
        c.reviewed(args.deployment_revision)
        record=c.r.read(args.candidate)
        if record["configuration_revision"]!=args.deployment_revision:c.reviewed(record["configuration_revision"])
        with c.r.fetched(c.r.AML,c.r.REVISION) as source:value=c.plans(source);refs=c.references(source,value)
        c.validate_candidate(record,record["configuration_revision"],refs)
        if args.action=="prepare":result=prepare(record,args.deployment_revision,refs,value,args.clouddeploy_release,args.output_dir,c.r.Cloud())
        else:
            c.verify(record,record["configuration_revision"],value,refs,c.r.Cloud())
            result=evaluate(c.r.read(args.snapshot),record,args.deployment_revision,refs,args.clouddeploy_release)
        print(json.dumps(result,sort_keys=True));return 3 if result.get("decision")=="BLOCKED" else 0
    except (OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.SubprocessError):
        print(json.dumps({"decision":"BLOCKED","reason":"complete_policy_or_evidence_check_failed","mutation_performed":False}));return 3

if __name__=="__main__":raise SystemExit(main())
