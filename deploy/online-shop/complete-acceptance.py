#!/usr/bin/env python3
"""Complete-shop acceptance: fresh cloud guard before runtime, signals or traffic."""
import argparse
from datetime import datetime, timezone
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import re
import socket
import subprocess
import urllib.parse
import urllib.request
import uuid

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("shop_workflow",HERE/"complete.py")
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
c=w.c;require=c.require

def guard(record, value, refs, cloud):
    proof=c.verify(record,record["configuration_revision"],value,refs,cloud)
    require(proof["status"]=="passed" and len(proof["components"])==11,"incomplete_independent_proof")
    found=c.existing_occurrences(cloud,[x["artifact"] for x in proof["components"]])
    require(all(found[x["artifact"]] for x in proof["components"]),"complete_admission_proof_missing")
    w.legacy.verify_support(cloud,"projects/"+c.r.policy()["project"]+"/occurrences/2b1c6135-42d3-453a-9942-f473dea60444")

def runtime(snapshot,record,revision,value,refs,cloud):
    guard(record,value,refs,cloud)  # Supplied Pod readbacks never define trusted expected state.
    rows={x["id"]:x for x in record["components"]}
    counts={identity:0 for identity in (*c.MEMBERS,"collector","redis-metrics-collector")};collector_nodes=set();app_nodes=set()
    for pod in snapshot["pods"]["items"]:
        if pod["metadata"].get("namespace")!="dev":continue
        app=pod["metadata"].get("labels",{}).get("app")
        identity="collector" if app=="catalog-collector" else "redis-metrics-collector" if app=="shop-redis-metrics" else app
        if identity not in counts:
            require(pod["metadata"].get("annotations",{}).get("release.secure-delivery.dev/release-set-id")!=record["release_set_id"],"unexpected_complete_runtime_member")
            continue
        require(not pod["metadata"].get("deletionTimestamp"),"terminating_complete_runtime")
        supporting=identity in ("collector","redis-metrics-collector")
        digest=w.legacy.policy()["collector"]["manifest_digest"] if supporting else rows[identity]["digest"]
        artifact=w.legacy.policy()["collector"]["mirror_image"] if supporting else rows[identity]["repository"]+"@"+digest
        require(pod["metadata"].get("annotations")==w.meta(record,revision,identity,digest),"runtime_component_metadata_mismatch")
        spec=pod["spec"];statuses=pod.get("status",{}).get("containerStatuses",[])
        require(not spec.get("initContainers") and not spec.get("ephemeralContainers") and len(spec["containers"])==len(statuses)==1,"unexpected_runtime_container")
        require(spec["containers"][0]["image"]==artifact and statuses[0].get("imageID","").removeprefix("docker-pullable://")==artifact,"running_component_digest_unproven")
        require(statuses[0].get("ready") is True and statuses[0].get("name")==spec["containers"][0]["name"],"complete_runtime_not_ready")
        require(pod.get("status",{}).get("phase")=="Running" and any(x.get("type")=="Ready" and x.get("status")=="True" for x in pod["status"].get("conditions",[])),"complete_pod_not_ready")
        require(spec.get("automountServiceAccountToken") is False and spec.get("serviceAccountName")==("catalog-collector" if supporting else identity),"runtime_identity_mismatch")
        node=spec.get("nodeName");require(bool(node),"runtime_node_unknown")
        (collector_nodes if identity=="collector" else app_nodes).add(node)
        counts[identity]+=1
    require(all(counts[x]==1 for x in (*c.MEMBERS,"redis-metrics-collector")) and counts["collector"]==len(collector_nodes)>0 and app_nodes<=collector_nodes,"incomplete_runtime_or_log_coverage")
    redis=[d for d in snapshot["deployments"]["items"] if d["metadata"].get("namespace")=="dev" and d["metadata"]["name"]=="redis-cart"]
    require(len(redis)==1 and redis[0]["spec"]["replicas"]==1 and redis[0]["spec"]["strategy"]=={"type":"Recreate"},"redis_singleton_violation")
    expected=set(c.MEMBERS)|{"shop-redis-metrics"};available=set()
    for d in snapshot["deployments"]["items"]:
        if d["metadata"].get("namespace")!="dev" or d["metadata"]["name"] not in expected:continue
        status=d.get("status",{})
        require(status.get("observedGeneration")==d["metadata"].get("generation") and status.get("replicas")==status.get("updatedReplicas")==status.get("readyReplicas")==status.get("availableReplicas")==1,"complete_deployment_unavailable")
        available.add(d["metadata"]["name"])
    require(available==expected,"complete_deployment_missing")
    agents=[d for d in snapshot["daemonsets"]["items"] if d["metadata"].get("namespace")=="dev" and d["metadata"]["name"]=="catalog-collector"]
    require(len(agents)==1,"collector_daemonset_missing")
    ds=agents[0];status=ds.get("status",{})
    require(status.get("observedGeneration")==ds["metadata"].get("generation") and status.get("desiredNumberScheduled")==status.get("updatedNumberScheduled")==status.get("numberReady")==status.get("numberAvailable")==len(collector_nodes),"collector_daemonset_unavailable")
    return {"runtime":"passed","members":counts}

def signals(snapshot,record,since,value,refs,cloud):
    guard(record,value,refs,cloud)
    start=w.legacy.sample.utc(since);require(start<=datetime.now(timezone.utc),"future_traffic_window")
    trace=snapshot["trace"];require(re.fullmatch(r"[0-9a-f]{32}",trace.get("traceId","")) and trace.get("spans"),"empty_complete_trace")
    rows={x["id"]:x for x in record["components"]};spans={};services=set();edges=set()
    for span in trace["spans"]:
        labels=span.get("labels",{});identity=labels.get("service.name")
        require(identity in c.APPS,"unknown_trace_component")
        require(labels.get("service.version")==rows[identity]["source"]["revision"] and labels.get("deployment.environment.name")=="dev"
            and labels.get("release_set_id")==record["release_set_id"] and labels.get("component_digest")==rows[identity]["digest"],"trace_component_attribution")
        require(w.legacy.sample.utc(span["startTime"])>=start,"trace_outside_traffic_window")
        sid=format(int(span["spanId"]),"016x");require(sid not in spans,"duplicate_trace_span")
        spans[sid]=(identity,span);services.add(identity)
    for identity,span in spans.values():
        parent=span.get("parentSpanId")
        if parent:
            parent=format(int(parent),"016x")
            if parent in spans and spans[parent][0]!=identity:edges.add((spans[parent][0],identity))
    require(services==set(c.APPS) and len(edges)>=len(c.APPS)-1,"shopping_distributed_trace_incomplete")
    connected={c.APPS[0]}
    for _ in c.APPS:
        for parent,child in edges:
            if parent in connected or child in connected:connected.update((parent,child))
    require(connected==set(c.APPS),"shopping_trace_components_disconnected")
    logged=set()
    for entry in snapshot["logs"].get("entries",[]):
        labels=entry.get("labels",{});identity=labels.get("service.name")
        if identity not in c.APPS or entry.get("jsonPayload",{}).get("event")!="request.completed":continue
        body=entry["jsonPayload"];sid=entry.get("spanId")
        require(entry.get("trace")=="projects/"+c.r.policy()["project"]+"/traces/"+trace["traceId"]
            and body.get("trace_id")==trace["traceId"] and body.get("span_id")==sid and sid in spans and spans[sid][0]==identity,"native_component_log_correlation")
        require(labels.get("service.version")==rows[identity]["source"]["revision"] and labels.get("deployment.environment.name")=="dev"
            and labels.get("release_set_id")==record["release_set_id"] and labels.get("component_digest")==rows[identity]["digest"],"log_component_attribution")
        require(entry.get("logName")=="projects/"+c.r.policy()["project"]+"/logs/online-shop%2Fcatalog"
            and entry.get("resource",{}).get("type")=="k8s_container" and entry["resource"]["labels"].get("namespace_name")=="dev"
            and w.legacy.sample.utc(entry["timestamp"])>=start,"wrong_component_log_stream_or_window")
        logged.add(identity)
    require(logged==set(c.APPS),"complete_correlated_logs_missing")
    measured=set();redis_measured=False
    for series in snapshot["metrics"].get("timeSeries",[]):
        metric=series.get("metric",{});labels=metric.get("labels",{});identity=labels.get("service_name")
        if identity not in rows:continue
        require(labels.get("release_set_id")==record["release_set_id"] and labels.get("component_digest")==rows[identity]["digest"]
            and labels.get("deployment_environment_name")=="dev","metric_component_attribution")
        require(labels.get("service_version")== (c.r.REVISION if identity in c.APPS else "external-unresolved"),"metric_component_version")
        positive=any(w.legacy.sample.utc(p["interval"]["endTime"])>=start and float(p.get("value",{}).get("int64Value",p.get("value",{}).get("doubleValue",0)))>0 for p in series.get("points",[]))
        if identity=="redis-cart":redis_measured=redis_measured or (positive and "redis" in metric.get("type","") and metric["type"].startswith("workload.googleapis.com/"))
        elif positive and labels.get("kind")=="server" and "online_shop" in metric.get("type","") and "requests" in metric["type"]:measured.add(identity)
    require(measured==set(c.APPS) and redis_measured,"complete_application_or_redis_metrics_missing")
    require(snapshot.get("original_stdout_duplicate_entries")==0 and snapshot.get("sink_review_no_duplicates") is True,"duplicate_ingestion_unproven")
    return {"signals":"passed","application_components":sorted(services),"cross_service_edges":len(edges),"native_component_logs":sorted(logged),"redis_native_metrics":True}

def journey(base, output):
    require(base=="http://127.0.0.1:8080","frontend_loopback_only")
    output=Path(output);require(not output.exists(),"journey_output_must_not_exist");output.mkdir(parents=True)
    count=0
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            nonlocal count
            count+=1;require(count<=20,"journey_request_budget")
            target=urllib.parse.urlsplit(newurl)
            require(target.scheme=="http" and target.netloc=="127.0.0.1:8080" and not target.fragment,"unexpected_frontend_redirect")
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar),Redirect())
    session="issue100-"+uuid.uuid4().hex;trace=uuid.uuid4().hex
    jar.set_cookie(http.cookiejar.Cookie(0,"shop_session-id",session,None,False,"127.0.0.1",False,False,"/",True,False,None,True,None,None,{}))
    def request(path,data=None):
        nonlocal count
        count+=1;require(count<=20,"journey_request_budget")
        req=urllib.request.Request(base+path,data=urllib.parse.urlencode(data).encode() if data is not None else None,
            headers={"traceparent":"00-"+trace+"-"+uuid.uuid4().hex[:16]+"-01"})
        with opener.open(req,timeout=20) as response:
            require(response.status==200,"shopping_http_failure");raw=response.read(2*1024*1024+1)
        require(len(raw)<=2*1024*1024,"shopping_response_too_large")
        (output/(str(count).zfill(2)+".private.html")).write_bytes(raw)
        return raw.decode("utf-8")
    since=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    completed=False
    try:
        home=request("/");products=re.findall(r'/product/([A-Za-z0-9_-]+)',home);require(products,"browse_products_missing")
        product=products[0];require(product in request("/product/"+product),"product_details_missing")
        request("/setCurrency",{"currency_code":"EUR"})
        require(any(x.name=="shop_currency" and x.value=="EUR" for x in jar),"currency_selection_not_retained")
        request("/cart",{"product_id":product,"quantity":"1"})
        require(product in request("/cart"),"cart_add_missing")
        request("/cart",{"product_id":product,"quantity":"1"})
        cart=request("/cart");require(re.search(r"Quantity:\s*2",cart),"cart_quantity_addition_missing")
        order=request("/cart/checkout",{"email":"issue100@example.invalid","street_address":"1 Test Street","zip_code":"94043","city":"Test City",
            "state":"CA","country":"United States","credit_card_number":"4111111111111111","credit_card_expiration_month":"12",
            "credit_card_expiration_year":str(datetime.now(timezone.utc).year+2),"credit_card_cvv":"123"})
        require("Your order is complete!" in order and "Tracking #" in order and re.search(r"[0-9a-f]{8}-[0-9a-f-]{27,}",order),"checkout_confirmation_missing")
        require("Your shopping cart is empty!" in request("/cart"),"post_checkout_cart_not_empty")
        completed=True
        result={"journey":"passed","browse_details_currency_cart_checkout_confirmation":True,"trace_id":trace,"since":since,
            "synthetic_session":session,"cleanup":"Cart cleared; exact Redis session key still requires scoped DEL per documented AML semantics."}
    finally:
        # Clear only the isolated session. AML ClearCart writes an empty protobuf
        # value, so a separately recorded exact-key DEL is still required.
        try:request("/cart/empty",{})
        finally:
            (output/"session.private.json").write_text(json.dumps({"session":session,"completed":completed,"trace_id":trace,"since":since}),encoding="utf-8")
    return {**result,"requests":count}

def cleanup_redis(session, endpoint):
    require(re.fullmatch(r"issue100-[0-9a-f]{32}",session or "") and endpoint=="127.0.0.1:16379","scoped_synthetic_redis_key_required")
    def command(name):
        parts=[name.encode(),session.encode()]
        wire=b"*2\r\n"+b"".join(b"$"+str(len(x)).encode()+b"\r\n"+x+b"\r\n" for x in parts)
        with socket.create_connection(("127.0.0.1",16379),timeout=5) as connection:
            connection.sendall(wire);response=connection.makefile("rb").readline(64)
        require(response in (b":0\r\n",b":1\r\n"),"unexpected_redis_cleanup_response")
        return response
    command("DEL")
    require(command("EXISTS")==b":0\r\n","synthetic_cart_key_still_present")
    return {"cleanup":"passed","exact_synthetic_key_removed":True,"other_keys_modified":False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("capacity","runtime","signals","journey","cleanup"))
    for name in ("candidate","configuration-revision","deployment-revision","snapshot","since","frontend","output-dir","session","redis"):parser.add_argument("--"+name)
    args=parser.parse_args()
    try:
        c.reviewed(args.configuration_revision)
        record=c.r.read(args.candidate)
        with c.r.fetched(c.r.AML,c.r.REVISION) as source:value=c.plans(source);refs=c.references(source,value)
        c.validate_candidate(record,args.configuration_revision,refs)
        cloud=c.r.Cloud()
        if args.action=="capacity":result=w.capacity(c.r.read(args.snapshot),w.render(record,args.deployment_revision,refs))
        elif args.action=="runtime":result=runtime(c.r.read(args.snapshot),record,args.deployment_revision,value,refs,cloud)
        elif args.action=="signals":result=signals(c.r.read(args.snapshot),record,args.since,value,refs,cloud)
        else:
            guard(record,value,refs,cloud)
            result=cleanup_redis(args.session,args.redis) if args.action=="cleanup" else journey(args.frontend,args.output_dir)
        print(json.dumps(result,sort_keys=True));return 3 if result.get("capacity_ready") is False else 0
    except (OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.SubprocessError):
        print(json.dumps({"status":"failed","reason":"complete_acceptance_evidence_missing_or_inconsistent"}));return 3

if __name__=="__main__":raise SystemExit(main())
