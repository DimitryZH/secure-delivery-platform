"""Full shop contract regressions; cloud/registry/signing fakes stay offline."""
import copy
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import importlib.util
import io
import http.server
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=load('complete_release_test',ROOT/'cloudbuild/online-shop/complete.py')
w=load('complete_deploy_test',ROOT/'deploy/online-shop/complete.py')
a=load('complete_accept_test',ROOT/'deploy/online-shop/complete-acceptance.py')
REV='d'*40
RESOURCE='projects/'+c.r.policy()['project']+'/locations/us-central1/deliveryPipelines/catalog-dev/releases/complete-review-1'
CONTEXT={'release_resource':RESOURCE,'target_resource':'projects/'+c.r.policy()['project']+'/locations/us-central1/targets/dev'}

class CompleteTests(unittest.TestCase):
    def setUp(self):
        self.plans={};self.refs={};rows=[]
        accepted=c.legacy.policy()['accepted_release']
        for i,identity in enumerate(c.APPS):
            context=c.profile()['build_contexts'][identity]
            arguments={'SOURCE_REVISION':c.r.REVISION}
            if identity in ('frontend','checkoutservice','productcatalogservice','shippingservice'):arguments['SKAFFOLD_GO_GCFLAGS']=''
            self.plans[identity]={'components':[{'id':identity,'buildContext':context,'dockerfile':context+'/Dockerfile','buildArguments':arguments,'inputs':[]}]}
            self.refs[identity]={'sha256':'sha256:'+'1'*64,'inputs_sha256':'sha256:'+'2'*64,'planner_sha256':'sha256:'+'3'*64,
                'contract_sha256':'sha256:'+'4'*64,'uri':'git+'+c.r.AML+'@'+c.r.REVISION+'#'+c.r.WORKLOAD+'/build_plan.py'}
            build=accepted['build_id'] if identity=='productcatalogservice' else '11111111-2222-3333-4444-'+str(i).zfill(12)
            digest=accepted['manifest_digest'] if identity=='productcatalogservice' else 'sha256:'+format(i+1,'x')*64
            rows.append(c.app_record(identity,accepted['configuration_revision'] if identity=='productcatalogservice' else REV,self.refs[identity],build,digest,'sha256:'+'f'*64))
        self.record=c.candidate(REV,rows)
        # No registry/Git/network calls from full-shop API fixtures. The official
        # source/content verifier has separate positive/negative and real-byte tests.
        for release in (c,w.c,a.c):
            gate=patch.object(release.redis,'verify_chain',side_effect=ValueError('redis_publication_chain_pending'))
            gate.start();self.addCleanup(gate.stop)

    def signal_fixture(self):
        stamp=datetime.now(timezone.utc).isoformat().replace('+00:00','Z');trace='a'*32
        spans=[];logs=[];metrics=[]
        operations={'cartservice':'/hipstershop.CartService/GetCart',
                    'emailservice':'hipstershop.EmailService/SendOrderConfirmation',
                    'recommendationservice':'hipstershop.RecommendationService/ListRecommendations'}
        for i,row in enumerate(self.record['components']):
            identity=row['id'];version=c.r.REVISION if identity in c.APPS else c.redis_policy()['redis_version']
            labels={'service.name':identity,'service.version':version,'deployment.environment.name':'dev',
                    'release_set_id':self.record['release_set_id'],'component_digest':row['digest']}
            metrics.append({'metric':{'type':'workload.googleapis.com/'+('redis.commands' if identity=='redis-cart' else 'online_shop.transport.requests'),
                'labels':{**{k.replace('.','_'):v for k,v in labels.items()},'kind':'server'}},
                'points':[{'interval':{'endTime':stamp},'value':{'int64Value':'1'}}]})
            if identity=='redis-cart':continue
            span={'spanId':str(i+1),'parentSpanId':str(i) if i else '', 'labels':labels,'startTime':stamp}
            body={'event':'request.completed','trace_id':trace,'span_id':format(i+1,'016x')}
            if identity in operations:
                body.update(event='operation.completed',category='application',operation=operations[identity])
                span.update(kind='RPC_SERVER',name=operations[identity])
                if identity=='cartservice':
                    parent={**span,'spanId':str(1000+i),'name':operations[identity].removeprefix('/')}
                    spans.append(parent);span.update(kind='SPAN_KIND_UNSPECIFIED',name='cart.GetCart',parentSpanId=parent['spanId'])
            spans.append(span)
            logs.append({'labels':labels,'spanId':body['span_id'],'trace':'projects/'+c.r.policy()['project']+'/traces/'+trace,
                'timestamp':stamp,'logName':'projects/'+c.r.policy()['project']+'/logs/online-shop%2Fcatalog',
                'resource':{'type':'k8s_container','labels':{'namespace_name':'dev'}},'jsonPayload':body})
        return stamp,{'journey':{'version':1,'kind':'issue100-shopping-journey','completed':True,'session':'issue100-'+'a'*32,'trace_id':trace,'since':stamp},'trace':{'traceId':trace,'spans':spans},'logs':{'entries':logs},'metrics':{'timeSeries':metrics},
                      'original_stdout_duplicate_entries':0,'sink_review_no_duplicates':True}

    def runtime_fixture(self,revision):
        docs=w.render(self.record,revision,self.refs);pods=[]
        for d in docs:
            d['metadata']['generation']=1
            if d['kind'] not in ('Deployment','DaemonSet'):continue
            pod=copy.deepcopy(d['spec']['template']);pod['metadata'].update(name=d['metadata']['name']+'-fixture',namespace='dev')
            pod['spec']['nodeName']='node';container=pod['spec']['containers'][0]
            pod['status']={'phase':'Running','conditions':[{'type':'Ready','status':'True'}],
                'containerStatuses':[{'name':container['name'],'imageID':container['image'],'ready':True}]};pods.append(pod)
            if d['kind']=='Deployment':d['status']={'observedGeneration':1,'replicas':1,'updatedReplicas':1,'readyReplicas':1,'availableReplicas':1}
            else:d['status']={'observedGeneration':1,'desiredNumberScheduled':1,'updatedNumberScheduled':1,'numberReady':1,'numberAvailable':1}
        return {'pods':{'items':pods},'deployments':{'items':[d for d in docs if d['kind']=='Deployment']},
                'daemonsets':{'items':[d for d in docs if d['kind']=='DaemonSet']}}

    def preflight_fixture(self,revision):
        now=datetime.now(timezone.utc);stamp=now.isoformat().replace('+00:00','Z')
        snapshot={'request':{'release_set_id':self.record['release_set_id'],'deployment_revision':revision,'target':'dev','action':'deploy','clouddeploy_release':RESOURCE}}
        sections={'release':['independently_verified','all_eleven_signatures_verified','redis_provenance_approved','collector_independently_verified'],
            'admission':['cluster_enforced','exact_attestor_required','no_bypass'],
            'target':['snapshot_matches_current','capacity_bin_packing_passed','metadata_and_wif_ready','all_stdout_exclusions_ready','no_duplicate_sinks','no_rollout_conflict','sample_baseline_preserved'],
            'caller':['rollout_create','deployment_act_as'],'review':['continue']}
        binding={'observed_at':stamp,'evidence_ref':'private-readback','release_set_id':self.record['release_set_id'],'deployment_revision':revision}
        for section,flags in sections.items():snapshot[section]={**binding,**{key:True for key in flags}}
        snapshot['clouddeploy']={**binding,**CONTEXT,'release_snapshot_matches_current':True}
        snapshot['rendered_documents']=w.rendered(self.record,revision,self.refs,CONTEXT)
        snapshot['release_annotations']={'rendered_inventory_sha256':c.r.sha(c.r.canonical(snapshot['rendered_documents'])),'source_sha256':'a'*64}
        snapshot['artifacts']={key:{**binding,'uri':'gs://'+c.r.policy()['project']+'-clouddeploy/'+key+'#12',
            'retention_expires_at':(now+timedelta(hours=2)).isoformat().replace('+00:00','Z'),'available':True,'live_generation':True,
            'actual_sha256':'a'*64,'expected_sha256':'a'*64} for key in ('source','rendered','resolved_skaffold')}
        return now,snapshot

    @contextmanager
    def producer_sources(self,release,bad_file=None,unmerged=False):
        calls=[]
        class Source:
            def git(inner,*args):
                calls.append(args)
                if args[0]=='merge-base' and unmerged:raise subprocess.CalledProcessError(1,args)
                return b''
            def blob(inner,name):
                if name in w.DEPLOYMENT_CODE:raise AssertionError('producer must not require old deployment executables')
                raw=(ROOT/name).read_bytes().replace(b'\r\n',b'\n')
                return raw+b'changed' if name==bad_file else raw
        @contextmanager
        def fetched(repository,revision):
            if repository==release.r.SDP:
                self.assertEqual(revision,REV);yield Source()
            else:
                self.assertEqual((repository,revision),(release.r.AML,release.r.REVISION));yield Mock()
        with patch.object(release.r,'fetched',side_effect=fetched):yield calls

    def build(self,identity):
        row=next(x for x in self.record['components'] if x['id']==identity)
        value=c.build_request(identity,REV,self.plans[identity])
        value.update(id=row['build']['id'],projectId=c.r.policy()['project'],name=c.r.build_url(c.r.policy(),row['build']['id']),status='SUCCESS',finishTime='2026-11-01T12:00:00Z',
            sourceProvenance={'resolvedGitSource':value['source']['gitSource']},results={'images':[{'name':value['images'][0],'digest':row['digest']}]})
        for step in value['steps']:step['status']='SUCCESS'
        return value

    def test_exact_ten_plus_redis_collector_separate_loadgen_excluded(self):
        c.validate_candidate(self.record,REV,self.refs)
        self.assertEqual(len(self.record['components']),11)
        self.assertEqual(c.profile()['required_dependencies'],['redis-cart'])
        self.assertEqual(c.profile()['supporting_images'],['collector'])
        for mutation in (lambda r:r['components'].pop(),lambda r:r['components'].append(r['components'][0]),
                         lambda r:r['components'].reverse(),lambda r:r['components'][0].update(id='loadgenerator'),
                         lambda r:r.update(unexpected=True),lambda r:r.update(profile='catalog-v1')):
            record=copy.deepcopy(self.record);mutation(record);record['release_set_id']=c.r.fingerprint({k:v for k,v in record.items() if k!='release_set_id'})
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):c.validate_candidate(record,REV,self.refs)

    def test_supplied_identity_exact_version_types_and_component_sources(self):
        for value in (True,2.0,1,False):
            record=copy.deepcopy(self.record);record['version']=value
            for recompute in (False,True):
                if recompute:record['release_set_id']=c.r.fingerprint({k:v for k,v in record.items() if k!='release_set_id'})
                with self.subTest(value=value,recompute=recompute),self.assertRaises(ValueError):c.validate_candidate(record,REV,self.refs)
        for mutation in (lambda r:r['components'][0]['source'].update(revision='e'*40),
                         lambda r:r['components'][0].update(repository='elsewhere/image'),
                         lambda r:r['components'][0]['plan'].update(sha256='sha256:'+'0'*64),
                         lambda r:r['components'][-1]['build'].update(producing_build='made-up')):
            record=copy.deepcopy(self.record);mutation(record);record['release_set_id']=c.r.fingerprint({k:v for k,v in record.items() if k!='release_set_id'})
            with self.assertRaises(ValueError):c.validate_candidate(record,REV,self.refs)

    def test_no_application_calls_or_signing_for_unverified_redis_chain(self):
        cloud=Mock();helper=Mock()
        with self.assertRaisesRegex(ValueError,'redis_publication'):c.verify(self.record,REV,self.plans,self.refs,cloud)
        cloud.assert_not_called();cloud.build.assert_not_called();cloud.request.assert_not_called()
        with patch.object(c.support,'signer_identity'),patch.object(c.r,'attestation_helper',return_value=helper):
            with self.assertRaises(ValueError):c.attest(self.record,REV,self.plans,self.refs,cloud)
        helper.sign_and_create.assert_not_called()
        self.assertEqual(c.redis_policy()['version'],2)
        self.assertEqual(c.redis_policy()['upstream_repository'],'docker.io/library/redis')
        self.assertEqual(c.redis_policy()['admission_decision'],'requires_verified_official_canonical_registry_chain')

    def test_component_specific_builds_args_results_and_mutations(self):
        for identity in c.APPS:
            if identity=='productcatalogservice':
                with self.assertRaisesRegex(ValueError,'reuse'):c.build_request(identity,REV,self.plans[identity])
                continue
            build=self.build(identity);row=next(x for x in self.record['components'] if x['id']==identity)
            self.assertEqual(c.check_build(build,identity,REV,self.plans[identity],row['build']['id']),row['digest'])
            args=build['steps'][1]['args']
            self.assertIn('SOURCE_REVISION='+c.r.REVISION,args)
            self.assertEqual('SKAFFOLD_GO_GCFLAGS=' in args,identity in ('frontend','checkoutservice','shippingservice'))
            for mutation in (lambda b:b.update(serviceAccount=c.r.policy()['signer']),lambda b:b['source']['gitSource'].update(revision='0'*40),
                             lambda b:b['results']['images'][0].update(name='elsewhere/image'),lambda b:b.update(options={'logging':'NONE'}),
                             lambda b:b['steps'][1]['args'].append('--target=unreviewed'),lambda b:b.update(substitutions={'_IMAGE':'injected'})):
                altered=copy.deepcopy(build);mutation(altered)
                with self.subTest(identity=identity),self.assertRaises(ValueError):c.check_build(altered,identity,REV,self.plans[identity],row['build']['id'])

    def test_independent_component_mismatch_rejected_with_recomputed_identity(self):
        cloud=Mock(token='offline-only');cloud.build.side_effect=lambda p,bid:self.build(next(x['id'] for x in self.record['components'][:-1] if x['build']['id']==bid))
        cloud.image.return_value='sha256:'+'f'*64
        catalog={'components':[{'config_digest':'sha256:'+'f'*64}]}
        # This is a verified dependency-chain fake, never a production
        # override: actual unpublished/unverified mirrors cannot pass the production chain.
        with patch.object(c,'redis_admission'),patch.object(c,'catalog_candidate',return_value=catalog),patch.object(c.redis,'verify_chain',return_value={'status':'redis_chain_verified'}):
            self.assertEqual(c.verify(self.record,REV,self.plans,self.refs,cloud)['status'],'passed')
            changed=copy.deepcopy(self.record);changed['components'][0]['digest']='sha256:'+'0'*64
            changed['release_set_id']=c.r.fingerprint({k:v for k,v in changed.items() if k!='release_set_id'})
            with self.assertRaisesRegex(ValueError,'binding'):c.verify(changed,REV,self.plans,self.refs,cloud)

    def test_catalog_reuse_is_not_replaced_by_new_profile(self):
        altered=copy.deepcopy(self.record);row=next(x for x in altered['components'] if x['id']=='productcatalogservice')
        row['digest']='sha256:'+'0'*64
        altered['release_set_id']=c.r.fingerprint({k:v for k,v in altered.items() if k!='release_set_id'})
        with self.assertRaisesRegex(ValueError,'catalog_reuse'):c.validate_candidate(altered,REV,self.refs)
        self.assertEqual(c.r.PROFILE['id'] if 'id' in c.r.PROFILE else c.r.PROFILE.get('profile'),'catalog-v1')

    def test_signing_transport_and_exact_separate_identity(self):
        uri='gs://'+c.r.policy()['project']+'-attestation-source/complete-shop-v1/review/candidate.json#12'
        request=c.signing_request(REV,uri,'sha256:'+'a'*64)
        self.assertEqual(request['serviceAccount'],c.r.policy()['signer'])
        self.assertNotEqual(request['serviceAccount'],c.r.policy()['producer'])
        self.assertIn('sha256sum -c',request['steps'][0]['args'][1])
        for invalid in (uri.split('#')[0],uri.replace('#12','#0'),uri.replace('complete-shop-v1','catalog-v1'),uri+"'untrusted"):
            with self.assertRaises(ValueError):c.signing_request(REV,invalid,'sha256:'+'a'*64)

    def test_signer_never_emits_partial_trust_and_reuses_existing_occurrences(self):
        outcomes=[{'id':x['id'],'artifact':x['repository']+'@'+x['digest'],'status':'passed'} for x in self.record['components']]
        helper=Mock();cloud=Mock(token='offline-only')
        with patch.object(c.support,'signer_identity'),patch.object(c,'verify',return_value={'status':'passed','components':outcomes}),\
             patch.object(c.r,'attestation_helper',return_value=helper),patch.object(c,'existing_occurrences',return_value={x['artifact']:['projects/p/occurrences/x'] for x in outcomes}):
            result=c.attest(self.record,REV,self.plans,self.refs,cloud)
            self.assertEqual(len(result['components']),11);self.assertEqual(result['status'],'trusted');helper.sign_and_create.assert_not_called()
        with patch.object(c.support,'signer_identity'),patch.object(c,'verify',return_value={'status':'passed','components':outcomes}),\
             patch.object(c.r,'attestation_helper',return_value=helper),patch.object(c,'existing_occurrences',return_value={x['artifact']:[] for x in outcomes}):
            helper.sign_and_create.side_effect=OSError('uncertain create')
            with self.assertRaisesRegex(ValueError,'uncertain'):c.attest(self.record,REV,self.plans,self.refs,cloud)
            self.assertEqual(helper.sign_and_create.call_count,1)

    def test_existing_build_and_uncertain_submission_do_not_resubmit(self):
        request=c.build_request('adservice',REV,self.plans['adservice']);cloud=Mock()
        value=copy.deepcopy(request);value.update(id='existing',status='FAILURE')
        cloud.request.return_value=c.r.canonical({'builds':[value]})
        self.assertEqual(c.submit_once(cloud,request)['status'],'existing_builds')
        self.assertTrue(all(len(call.args)==1 for call in cloud.request.call_args_list))
        cloud=Mock();cloud.request.side_effect=[b'{}',OSError('unknown response'),c.r.canonical({'builds':[value]})]
        self.assertEqual(c.submit_once(cloud,request)['status'],'recovered_builds')
        self.assertEqual(sum(len(call.args)==2 for call in cloud.request.call_args_list),1)

    def test_complete_render_all_services_dependency_and_runtime_contract(self):
        docs=w.render(self.record,REV,self.refs);self.assertEqual(w.inventory(docs,self.record,REV,self.refs)['applications'],10)
        deployments={d['metadata']['name']:d for d in docs if d['kind']=='Deployment' and d['metadata']['name'] in c.MEMBERS}
        self.assertEqual(set(deployments),set(c.MEMBERS));self.assertEqual(len(docs),39)
        redis=deployments['redis-cart'];self.assertEqual(redis['spec']['strategy'],{'type':'Recreate'})
        self.assertEqual(redis['spec']['template']['spec']['containers'][0]['command'],['redis-server','--save','','--appendonly','no'])
        for identity,d in deployments.items():
            pod=d['spec']['template']['spec'];container=pod['containers'][0]
            self.assertFalse(pod['automountServiceAccountToken']);self.assertNotIn('initContainers',pod)
            self.assertTrue(container['securityContext']['readOnlyRootFilesystem'])
            self.assertEqual(pod['nodeSelector']['kubernetes.io/arch'],'amd64')
            self.assertGreaterEqual(pod['terminationGracePeriodSeconds'],15 if identity=='redis-cart' else 30)
            if identity!='redis-cart':
                env={e['name']:e['value'] for e in container['env']}
                self.assertEqual(env['ONLINE_SHOP_VERSION'],c.r.REVISION);self.assertNotIn('ENABLE_PROFILER',env)
                self.assertNotIn('PACKAGING_SERVICE_URL',env)
        frontend={e['name']:e['value'] for e in deployments['frontend']['spec']['template']['spec']['containers'][0]['env']}
        self.assertEqual(frontend['ENABLE_ASSISTANT'],'false');self.assertEqual(frontend['SHOPPING_ASSISTANT_SERVICE_ADDR'],'127.0.0.1:1')
        checkout={e['name']:e['value'] for e in deployments['checkoutservice']['spec']['template']['spec']['containers'][0]['env']}
        self.assertEqual(checkout['EMAIL_SERVICE_ADDR'],'emailservice:5000')
        email=next(d for d in docs if d['kind']=='Service' and d['metadata']['name']=='emailservice')
        self.assertEqual(email['spec']['ports'][0]['targetPort'],8080)

    def test_rendered_labels_are_scoped_and_all_other_mutations_fail(self):
        docs=w.rendered(self.record,REV,self.refs,CONTEXT);w.inventory(docs,self.record,REV,self.refs,CONTEXT)
        for d in docs:
            if d['kind'] in ('ServiceAccount','ConfigMap'):self.assertNotIn('labels',d['metadata'])
        changes=[lambda ds:ds.pop(),lambda ds:ds.append(copy.deepcopy(ds[0])),
            lambda ds:next(d for d in ds if d['kind']=='Deployment')['spec']['template']['spec']['containers'][0].update(image='image:tag'),
            lambda ds:next(d for d in ds if d['kind']=='ConfigMap')['data'].update({'config.json':'changed'}),
            lambda ds:next(d for d in ds if d['kind']=='Service')['spec'].update(type='LoadBalancer'),
            lambda ds:next(d for d in ds if d['kind']=='Deployment')['metadata']['labels'].update({'deploy.cloud.google.com/target-id':'stage'}),
            lambda ds:next(d for d in ds if d['kind']=='Deployment')['spec']['template']['metadata']['annotations'].update({'alpha.image-policy.k8s.io/break-glass':'true'})]
        for change in changes:
            altered=copy.deepcopy(docs);change(altered)
            with self.assertRaises(ValueError):w.inventory(altered,self.record,REV,self.refs,CONTEXT)

    def test_collector_component_version_digest_mapping_and_no_native_redis_traces(self):
        config=w.collector_config(self.record)
        self.assertEqual(len([x for x in config['service']['pipelines'] if x.startswith('traces/')]),10)
        self.assertNotIn('traces/redis-cart',config['service']['pipelines'])
        self.assertNotIn('redis',config['receivers'])
        metrics=w.redis_metrics_config(self.record)
        self.assertEqual(metrics['receivers']['redis']['endpoint'],'redis-cart.dev.svc.cluster.local:6379')
        self.assertEqual(list(metrics['service']['pipelines']),['metrics/redis-cart'])
        paths=[]
        for row in self.record['components']:
            attrs={x['key']:x['value'] for x in config['processors']['resource/'+row['id']]['attributes']}
            self.assertEqual(attrs['component_digest'],row['digest']);self.assertEqual(attrs['service.name'],row['id'])
            self.assertEqual(attrs['release_set_id'],self.record['release_set_id'])
            paths+=config['receivers']['file_log/'+row['id']]['include']
        self.assertEqual(len(set(paths)),11)
        text=json.dumps(config)
        for forbidden in ('MONITOR','SLOWLOG','docker.sock','/var/log/pods/*/'):
            self.assertNotIn(forbidden,text)

    def test_no_prepare_bundle_for_unresolved_dependency(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(w.c,'reviewed'):
            with self.assertRaisesRegex(ValueError,'redis_publication'):
                w.prepare(self.record,REV,self.refs,self.plans,RESOURCE,Path(tmp)/'bundle',Mock())
            self.assertFalse((Path(tmp)/'bundle').exists())

    def test_runtime_signals_guard_precedes_evidence_for_old_and_recomputed_identity(self):
        class MustNotRead:
            def __getitem__(self,key):raise AssertionError('evidence read before guard')
        for candidate in (self.record,):
            with self.assertRaisesRegex(ValueError,'redis_publication'):a.runtime(MustNotRead(),candidate,REV,self.plans,self.refs,Mock())
            with self.assertRaisesRegex(ValueError,'redis_publication'):a.signals(MustNotRead(),candidate,'not-a-time',self.plans,self.refs,Mock())
        altered=copy.deepcopy(self.record);altered['components'][0]['digest']='sha256:'+'0'*64
        with self.assertRaisesRegex(ValueError,'identity'):a.runtime(MustNotRead(),altered,REV,self.plans,self.refs,Mock())

    def test_capacity_uses_overlap_singleton_and_per_node_requests(self):
        docs=w.render(self.record,REV,self.refs)
        node={'metadata':{'name':'node','labels':{'kubernetes.io/os':'linux','kubernetes.io/arch':'amd64','iam.gke.io/gke-metadata-server-enabled':'true'}},
            'spec':{},'status':{'allocatable':{'cpu':'1930m','memory':'6025Mi','pods':'110'},'conditions':[{'type':'Ready','status':'True'}]}}
        snapshot={'nodes':{'items':[node]},'pods':{'items':[]}}
        self.assertFalse(w.capacity(snapshot,docs)['capacity_ready'])
        node['status']['allocatable']['cpu']='6';node['status']['allocatable']['memory']='16Gi'
        result=w.capacity(snapshot,docs);self.assertTrue(result['capacity_ready']);self.assertEqual(result['redis_overlap_replicas'],1)
        pending={'metadata':{'name':'waiting','namespace':'other'},'spec':{},'status':{'phase':'Pending'}}
        snapshot['pods']['items']=[pending];self.assertFalse(w.capacity(snapshot,docs)['capacity_ready'])

    def test_cleanup_only_exact_synthetic_session_loopback(self):
        for session,endpoint in [('production-key','127.0.0.1:16379'),('issue100-'+'a'*32,'redis:6379'),('issue100-'+('a'*32)+'\r\nFLUSHALL','127.0.0.1:16379')]:
            with patch.object(a.socket,'create_connection') as connection,self.assertRaises(ValueError):a.cleanup_redis(session,endpoint)
            connection.assert_not_called()
        with patch.object(a.socket,'create_connection') as connection:
            connection.return_value.__enter__.return_value.makefile.return_value.readline.side_effect=[b':1\r\n',b':0\r\n']
            self.assertEqual(a.cleanup_redis('issue100-'+'a'*32,'127.0.0.1:16379')['cleanup'],'passed')
            wire=b''.join(call.args[0] for call in connection.return_value.__enter__.return_value.sendall.call_args_list)
            self.assertNotIn(b'FLUSH',wire);self.assertIn(b'DEL',wire)

    def cleanup_receipt(self, path):
        record={'version':1,'kind':'issue100-shopping-journey','session':'issue100-'+'a'*32,
            'completed':False,'cleanup_target':a.CLEANUP_TARGET,'cleanup_endpoint':a.CLEANUP_ENDPOINT}
        path.write_text(json.dumps(record),encoding='utf-8')
        return record

    def cleanup_cli(self, path, record, **overrides):
        values={'session-record':str(path),'session':record['session'],'redis':a.CLEANUP_ENDPOINT,'redis-target':a.CLEANUP_TARGET,**overrides}
        argv=['complete-acceptance.py','cleanup']
        for key,value in values.items():
            if value is not None:argv += ['--'+key,value]
        output=io.StringIO()
        with patch.object(sys,'argv',argv),patch('sys.stdout',output):code=a.main()
        return code,json.loads(output.getvalue())

    def test_cleanup_cli_survives_verification_outage_without_release_or_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'session.private.json';record=self.cleanup_receipt(path)
            with patch.object(a.c,'verify',side_effect=OSError('temporary verification outage')) as verification,\
                 patch.object(a.c,'reviewed',side_effect=OSError('main unavailable')) as reviewed,\
                 patch.object(a.c.r,'fetched',side_effect=OSError('AML unavailable')) as fetched,\
                 patch.object(a.c,'validate_candidate',side_effect=ValueError('release blocked')) as candidate,\
                 patch.object(a.c.r,'Cloud',side_effect=OSError('credentials unavailable')) as cloud,\
                 patch.object(a.socket,'create_connection') as connection:
                # Reproduce verification failure after journey; cleanup must still
                # reach the bounded Redis commands without retrying the trust chain.
                with self.assertRaises(OSError):a.guard(self.record,self.plans,self.refs,Mock())
                verification.reset_mock()
                connection.return_value.__enter__.return_value.makefile.return_value.readline.side_effect=[b':1\r\n',b':0\r\n']
                code,result=self.cleanup_cli(path,record)
                self.assertEqual(code,0);self.assertEqual(result['cleanup'],'passed')
                for unused in (verification,reviewed,fetched,candidate,cloud):unused.assert_not_called()
                for call in connection.call_args_list:self.assertEqual(call.args,(('127.0.0.1',16379),))
                key=record['session'].encode()
                expected=[b'*2\r\n$'+str(len(command)).encode()+b'\r\n'+command+b'\r\n$'+str(len(key)).encode()+b'\r\n'+key+b'\r\n' for command in (b'DEL',b'EXISTS')]
                actual=[call.args[0] for call in connection.return_value.__enter__.return_value.sendall.call_args_list]
                self.assertEqual(actual,expected)

    def test_cleanup_cli_rejects_foreign_session_target_or_missing_ownership_before_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'session.private.json';record=self.cleanup_receipt(path)
            for overrides in ({'session':'foreign-session'},{'session':'issue100-'+'b'*32},
                {'session':record['session']+'\r\nFLUSHALL'},{'redis':'redis-cart:6379'},
                {'redis':'127.0.0.1:6379'},{'redis-target':a.CLEANUP_TARGET.replace('/dev/','/prod/')},
                {'redis-target':a.CLEANUP_TARGET.replace('sre-platform-staging-507220','other-project')},
                {'redis-target':a.CLEANUP_TARGET.replace('/redis-cart','/other-redis')},
                {'redis-target':None},{'session-record':str(Path(tmp)/'missing.json')}):
                with self.subTest(overrides=overrides),patch.object(a.socket,'create_connection') as connection:
                    self.assertEqual(self.cleanup_cli(path,record,**overrides)[0],3);connection.assert_not_called()
            for mutate in (lambda r:r.update(version=True),lambda r:r.update(kind='foreign-run'),
                           lambda r:r.update(cleanup_target=a.CLEANUP_TARGET.replace('/dev/','/stage/')),
                           lambda r:r.update(cleanup_endpoint='127.0.0.1:6379')):
                altered=copy.deepcopy(record);mutate(altered);path.write_text(json.dumps(altered),encoding='utf-8')
                with patch.object(a.socket,'create_connection') as connection:
                    self.assertEqual(self.cleanup_cli(path,record)[0],3);connection.assert_not_called()

    def test_cleanup_cli_requires_exists_zero_and_handles_already_absent_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'session.private.json';record=self.cleanup_receipt(path)
            for replies,code in (([b':0\r\n',b':0\r\n'],0),([b':1\r\n',b':1\r\n'],3),([b'+OK\r\n'],3)):
                with self.subTest(replies=replies),patch.object(a.socket,'create_connection') as connection:
                    connection.return_value.__enter__.return_value.makefile.return_value.readline.side_effect=replies
                    self.assertEqual(self.cleanup_cli(path,record)[0],code)
                    self.assertEqual(connection.return_value.__enter__.return_value.sendall.call_count,len(replies))

    def test_failed_journey_preserves_local_session_scope_before_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'failed-journey'
            def fail(*args,**kwargs):
                record=json.loads((out/'session.private.json').read_text(encoding='utf-8'))
                self.assertEqual(record['cleanup_target'],a.CLEANUP_TARGET);self.assertFalse(record['completed'])
                raise OSError('frontend unavailable')
            with patch.object(a.urllib.request,'build_opener') as opener:
                opener.return_value.open.side_effect=fail
                with self.assertRaises(OSError):a.journey('http://127.0.0.1:8080',out)
            record=json.loads((out/'session.private.json').read_text(encoding='utf-8'))
            self.assertEqual(record['version'],1);self.assertEqual(record['kind'],'issue100-shopping-journey')
            self.assertRegex(record['session'],r'^issue100-[a-f0-9]{32}$');self.assertEqual(record['cleanup_endpoint'],a.CLEANUP_ENDPOINT)

    def test_redis_actual_content_hash_size_and_platform_negatives(self):
        def run(arch='amd64',bad_size=False,bad_hash=False):
            cfg=c.r.canonical({'os':'linux','architecture':arch,'config':{'WorkingDir':'/data','Cmd':['redis-server'],'Entrypoint':['docker-entrypoint.sh'],'Env':['REDIS_VERSION='+c.redis_policy()['redis_version']]}});layer=b'compressed fixture'
            config={'digest':'sha256:'+c.r.sha(cfg),'size':len(cfg)}
            desc={'digest':'sha256:'+c.r.sha(layer),'size':len(layer)+(1 if bad_size else 0)}
            raw=c.r.canonical({'schemaVersion':2,'config':config,'layers':[desc]})
            policy={**c.redis_policy(),'manifest_digest':'sha256:'+c.r.sha(raw),'config_digest':config['digest']}
            read=Mock();read.get.side_effect=[raw,cfg,b'corrupt' if bad_hash else layer]
            return c.redis.content(read,policy)
        self.assertEqual(run()['layers_verified'],1)
        for kwargs in ({'arch':'arm64'},{'bad_size':True},{'bad_hash':True}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):run(**kwargs)

    def test_full_preflight_positive_fixture_and_security_failures(self):
        now,snapshot=self.preflight_fixture(REV);stamp=now.isoformat().replace('+00:00','Z')
        snapshot['release']['redis_provenance_approved']=False
        self.assertEqual(w.evaluate(snapshot,self.record,REV,self.refs,RESOURCE,now)['decision'],'BLOCKED')
        snapshot['release']['redis_provenance_approved']=True
        with patch.object(w.c,'redis_admission'):
            self.assertEqual(w.evaluate(snapshot,self.record,REV,self.refs,RESOURCE,now)['decision'],'READY')
            for mutate in (lambda s:s['artifacts']['source'].update(actual_sha256='b'*64),
                lambda s:s['clouddeploy'].update(target_resource=CONTEXT['target_resource'].replace('/dev','/prod')),
                lambda s:s['target'].update(observed_at=(now-timedelta(minutes=6)).isoformat().replace("+00:00","Z")),
                lambda s:s['artifacts']['rendered'].update(retention_expires_at=stamp),
                lambda s:s['release_annotations'].update(rendered_inventory_sha256='b'*64)):
                altered=copy.deepcopy(snapshot);mutate(altered)
                self.assertEqual(w.evaluate(altered,self.record,REV,self.refs,RESOURCE,now)['decision'],'BLOCKED')

    def test_reused_producer_requires_main_ancestry_and_all_shared_trust_bytes(self):
        deployment='e'*40
        with patch.object(w.c,'reviewed') as current,self.producer_sources(w.c) as calls:
            w.reviewed(self.record,deployment);current.assert_called_once_with(deployment)
            self.assertIn(('merge-base','--is-ancestor',REV,'FETCH_HEAD'),calls)
        with patch.object(w.c,'reviewed'),self.producer_sources(w.c,unmerged=True):
            with self.assertRaises(subprocess.CalledProcessError):w.reviewed(self.record,deployment)
        for name in set(w.c.TRUST_FILES)-set(w.DEPLOYMENT_CODE):
            with self.subTest(file=name),patch.object(w.c,'reviewed'),self.producer_sources(w.c,bad_file=name):
                with self.assertRaisesRegex(ValueError,'incompatible_producing_trust_files'):w.reviewed(self.record,deployment)
        with patch.object(w.c,'reviewed',side_effect=ValueError('unreviewed_complete_files')),patch.object(w.c.r,'fetched') as source:
            with self.assertRaisesRegex(ValueError,'unreviewed'):w.reviewed(self.record,deployment)
            source.assert_not_called()
        with patch.object(w.c,'reviewed') as current,patch.object(w.c.r,'fetched') as source:
            w.reviewed(self.record,REV);current.assert_called_once_with(REV);source.assert_not_called()

    def test_prepare_and_preflight_cli_reuse_original_candidate_with_new_deployment(self):
        deployment='e'*40;original=c.r.canonical(self.record)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);candidate=root/'candidate.json';candidate.write_bytes(original)
            _,snapshot=self.preflight_fixture(deployment);snapshot_path=root/'snapshot.json';snapshot_path.write_text(json.dumps(snapshot))
            for action in ('prepare','preflight'):
                args=['complete.py',action,'--candidate',str(candidate),'--deployment-revision',deployment,
                      '--clouddeploy-release',RESOURCE,'--output-dir',str(root/'bundle'),'--snapshot',str(snapshot_path)]
                with self.subTest(action=action),patch.object(sys,'argv',args),patch('sys.stdout',new_callable=io.StringIO) as stdout,\
                     patch.object(w.c,'reviewed') as reviewed,self.producer_sources(w.c),\
                     patch.object(w.c,'plans',return_value=self.plans),patch.object(w.c,'references',return_value=self.refs),\
                     patch.object(w.c,'verify',return_value={'status':'passed'}) as verify,\
                     patch.object(w.c,'attest',return_value={'status':'trusted'}) as attest,\
                     patch.object(w.legacy,'verify_support'),patch.object(w.c.r,'Cloud'),patch.object(w.c,'redis_admission'):
                    self.assertEqual(w.main(),0,stdout.getvalue())
                    self.assertTrue(all(x.args==(deployment,) for x in reviewed.call_args_list))
                    self.assertEqual(verify.call_args.args[1],REV)
                    if action=='prepare':self.assertTrue(attest.call_args.kwargs['inspect'])
                    else:self.assertEqual(json.loads(stdout.getvalue())['decision'],'READY')
                with patch.object(sys,'argv',args),patch('sys.stdout',new_callable=io.StringIO),\
                     patch.object(w.c,'reviewed',side_effect=ValueError('unreviewed deployment')),patch.object(w.c.r,'Cloud') as cloud:
                    self.assertEqual(w.main(),3);cloud.assert_not_called()
            self.assertEqual(candidate.read_bytes(),original)
            bundle=json.loads((root/'bundle/rendered/dev/shop.json').read_text())['items']
            for d in bundle:
                if d['kind']=='Deployment':self.assertEqual(d['spec']['template']['metadata']['annotations']['release.secure-delivery.dev/deployment-configuration'],deployment)

    def test_acceptance_cli_reviews_deployment_and_verifies_original_producer(self):
        deployment='e'*40;stamp,signals=self.signal_fixture()
        outcomes=[{'id':r['id'],'artifact':r['repository']+'@'+r['digest']} for r in self.record['components']]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);candidate=root/'candidate.json';candidate.write_text(json.dumps(self.record));snapshot=root/'snapshot.json'
            for action in ('runtime','signals','journey','capacity'):
                snapshot.write_text(json.dumps(signals if action=='signals' else self.runtime_fixture(deployment)))
                args=['acceptance',action,'--candidate',str(candidate),'--configuration-revision',REV,'--deployment-revision',deployment,
                      '--snapshot',str(snapshot),'--since',stamp,'--frontend','http://127.0.0.1:8080','--output-dir',str(root/'journey')]
                with self.subTest(action=action),patch.object(sys,'argv',args),patch('sys.stdout',new_callable=io.StringIO) as stdout,\
                     patch.object(a.c,'reviewed') as reviewed,self.producer_sources(a.c),\
                     patch.object(a.c,'plans',return_value=self.plans),patch.object(a.c,'references',return_value=self.refs),\
                     patch.object(a.c,'verify',return_value={'status':'passed','components':outcomes}) as verify,\
                     patch.object(a.c,'existing_occurrences',return_value={r['artifact']:['existing'] for r in outcomes}),\
                     patch.object(a.w.legacy,'verify_support'),patch.object(a.c.r,'Cloud'),\
                     patch.object(a,'journey',return_value={'journey':'passed'}),patch.object(a.w,'capacity',return_value={'capacity_ready':True}):
                    self.assertEqual(a.main(),0,stdout.getvalue());reviewed.assert_called_once_with(deployment)
                    if action!='capacity':self.assertEqual(verify.call_args.args[1],REV)
                with patch.object(sys,'argv',args),patch('sys.stdout',new_callable=io.StringIO),\
                     patch.object(a.c,'reviewed',side_effect=ValueError('unreviewed deployment')),patch.object(a.c.r,'Cloud') as cloud:
                    self.assertEqual(a.main(),3);cloud.assert_not_called()
                wrong=args.copy();wrong[wrong.index('--configuration-revision')+1]=deployment
                with patch.object(sys,'argv',wrong),patch('sys.stdout',new_callable=io.StringIO),\
                     patch.object(a.w,'reviewed'),patch.object(a.c.r,'fetched'),\
                     patch.object(a.c,'plans',return_value=self.plans),patch.object(a.c,'references',return_value=self.refs),patch.object(a.c.r,'Cloud') as cloud:
                    self.assertEqual(a.main(),3);cloud.assert_not_called()

    def test_runtime_positive_and_coherent_tamper_guard(self):
        docs=w.render(self.record,REV,self.refs);pods=[]
        for d in docs:
            if d['kind'] not in ('Deployment','DaemonSet'):continue
            template=copy.deepcopy(d['spec']['template']);template['metadata'].update(name=d['metadata']['name']+'-fixture',namespace='dev')
            template['spec']['nodeName']='node'
            app=template['spec']['containers'][0]
            template['status']={'phase':'Running','conditions':[{'type':'Ready','status':'True'}],'containerStatuses':[{'name':app['name'],'imageID':app['image'],'ready':True}]}
            pods.append(template)
        for d in docs:
            d['metadata']['generation']=1
            if d['kind']=='Deployment':d['status']={'observedGeneration':1,'replicas':1,'updatedReplicas':1,'readyReplicas':1,'availableReplicas':1}
            if d['kind']=='DaemonSet':d['status']={'observedGeneration':1,'desiredNumberScheduled':1,'updatedNumberScheduled':1,'numberReady':1,'numberAvailable':1}
        snapshot={'pods':{'items':pods},'deployments':{'items':[d for d in docs if d['kind']=='Deployment']},'daemonsets':{'items':[d for d in docs if d['kind']=='DaemonSet']}}
        with patch.object(a,'guard'):
            self.assertEqual(a.runtime(snapshot,self.record,REV,self.plans,self.refs,Mock())['runtime'],'passed')
            altered=copy.deepcopy(snapshot);altered['pods']['items'][0]['spec']['containers'][0]['image']='image:latest'
            with self.assertRaises(ValueError):a.runtime(altered,self.record,REV,self.plans,self.refs,Mock())
            altered=copy.deepcopy(snapshot);altered['deployments']['items'][0]['status']['availableReplicas']=0
            with self.assertRaises(ValueError):a.runtime(altered,self.record,REV,self.plans,self.refs,Mock())
        # Even coherent readbacks never turn a caller-controlled digest into trust.
        altered=copy.deepcopy(self.record);altered['components'][0]['digest']='sha256:'+'0'*64
        for recompute in (False,True):
            if recompute:altered['release_set_id']=c.r.fingerprint({k:v for k,v in altered.items() if k!='release_set_id'})
            with self.assertRaises(ValueError):a.runtime(snapshot,altered,REV,self.plans,self.refs,Mock())
            with self.assertRaises(ValueError):a.signals({},altered,'not-a-time',self.plans,self.refs,Mock())

    def test_signals_positive_full_component_and_missing_or_wrong_attribution(self):
        stamp,snapshot=self.signal_fixture()
        with patch.object(a,'guard'):
            self.assertEqual(a.signals(snapshot,self.record,stamp,self.plans,self.refs,Mock())['signals'],'passed')
            for mutate in (lambda s:s['trace']['spans'].pop(),lambda s:s['logs']['entries'][0]['labels'].update(component_digest='sha256:'+'0'*64),
                           lambda s:s.update(original_stdout_duplicate_entries=1),lambda s:s['metrics']['timeSeries'].pop()):
                altered=copy.deepcopy(snapshot);mutate(altered)
                with self.assertRaises(ValueError):a.signals(altered,self.record,stamp,self.plans,self.refs,Mock())

    def test_trace_clock_skew_and_recorded_journey_binding(self):
        stamp,snapshot=self.signal_fixture()
        with patch.object(a,'guard'):
            for seconds in (0,0.872361,2):
                altered=copy.deepcopy(snapshot)
                for span in altered['trace']['spans']:
                    span['startTime']=(datetime.fromisoformat(stamp.replace('Z','+00:00'))-timedelta(seconds=seconds)).isoformat().replace('+00:00','Z')
                self.assertEqual(a.signals(altered,self.record,stamp,self.plans,self.refs,Mock())['signals'],'passed')
            for mutate in (
                lambda s:s['trace']['spans'][0].update(startTime=(datetime.fromisoformat(stamp.replace('Z','+00:00'))-timedelta(seconds=2.000001)).isoformat().replace('+00:00','Z')),
                lambda s:s['trace'].update(traceId='f'*32),
                lambda s:s['journey'].update(since='2000-01-01T00:00:00Z'),
                lambda s:s['trace']['spans'][0]['labels'].update(component_digest='sha256:'+'0'*64),
                lambda s:s['trace']['spans'][0]['labels'].update(release_set_id='sha256:'+'0'*64)):
                altered=copy.deepcopy(snapshot);mutate(altered)
                with self.assertRaises(ValueError):a.signals(altered,self.record,stamp,self.plans,self.refs,Mock())

    def test_operation_completion_requires_component_server_not_dependency_or_internal(self):
        stamp,snapshot=self.signal_fixture()
        with patch.object(a,'guard'):
            for identity in a.RPC_COMPLETIONS:
                index=next(i for i,x in enumerate(snapshot['logs']['entries']) if x['labels']['service.name']==identity)
                for mutate in (
                    lambda e:e['jsonPayload'].update(category='dependency'),
                    lambda e:e['jsonPayload'].update(category='internal'),
                    lambda e:e['jsonPayload'].update(operation=identity+'.business'),
                    lambda e:e['jsonPayload'].update(operation='hipstershop.ProductCatalogService/ListProducts'),
                    lambda e:e['jsonPayload'].update(event='request.completed'),
                    lambda e:e.update(spanId='0'*16),
                    lambda e:e.update(trace='projects/wrong/traces/'+'a'*32),
                    lambda e:e['jsonPayload'].update(trace_id='b'*32),
                    lambda e:e['jsonPayload'].update(span_id='0'*16),
                    lambda e:e['labels'].update(component_digest='sha256:'+'0'*64)):
                    altered=copy.deepcopy(snapshot);mutate(altered['logs']['entries'][index])
                    with self.subTest(identity=identity,mutation=mutate),self.assertRaises(ValueError):
                        a.signals(altered,self.record,stamp,self.plans,self.refs,Mock())
                # Same operation/category is not enough without the native SERVER
                # span (or cart's exact interceptor child and SERVER parent).
                altered=copy.deepcopy(snapshot);entry=altered['logs']['entries'][index]
                span=next(x for x in altered['trace']['spans'] if format(int(x['spanId']),'016x')==entry['spanId'])
                if identity=='cartservice':span=next(x for x in altered['trace']['spans'] if x['spanId']==span['parentSpanId'])
                span['kind']='RPC_CLIENT'
                with self.assertRaises(ValueError):a.signals(altered,self.record,stamp,self.plans,self.refs,Mock())
            # Unrelated internal/dependency events are ignored, not accepted as
            # completion and not allowed to replace any required component.
            extra=copy.deepcopy(snapshot['logs']['entries'][2]);extra['jsonPayload'].update(event='operation.completed',category='dependency',operation='cache.read')
            snapshot['logs']['entries'].append(extra)
            self.assertEqual(a.signals(snapshot,self.record,stamp,self.plans,self.refs,Mock())['signals'],'passed')

    def test_bounded_local_shopping_journey_and_external_redirect_denied(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            evil=False;calls=[]
            def log_message(self,*args):pass
            def do_GET(self):self.reply()
            def do_POST(self):self.reply()
            def reply(self):
                Handler.calls.append(self.path)
                if self.command=='POST':self.rfile.read(int(self.headers.get('Content-Length','0')))
                if Handler.evil:
                    self.send_response(302);self.send_header('Location','https://outside.invalid/');self.end_headers();return
                self.send_response(200)
                if self.path=='/setCurrency':self.send_header('Set-Cookie','shop_currency=EUR; Path=/')
                self.end_headers()
                body='Your order is complete! Tracking # 11111111-2222-3333-4444-555555555555' if self.path=='/cart/checkout' else 'Your shopping cart is empty! /product/ABC ABC Quantity: 2'
                self.wfile.write(body.encode())
        server=http.server.ThreadingHTTPServer(('127.0.0.1',8080),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result=a.journey('http://127.0.0.1:8080',Path(tmp)/'ok')
                self.assertEqual(result['journey'],'passed');self.assertEqual(result['requests'],len(Handler.calls));self.assertLessEqual(result['requests'],20)
                self.assertEqual(Handler.calls[-1],'/cart/empty')
                Handler.evil=True
                with self.assertRaises(ValueError):a.journey('http://127.0.0.1:8080',Path(tmp)/'bad')
        finally:server.shutdown();server.server_close();thread.join()

    @unittest.skipUnless(os.environ.get('SDP_AML_REPOSITORY'),'immutable AML optional integration')
    def test_real_pinned_planner_all_ten_and_catalog_plan_reuse(self):
        source=c.r.Source(os.environ['SDP_AML_REPOSITORY'],c.r.REVISION)
        value=c.plans(source);self.assertEqual(set(value),set(c.APPS))
        self.assertEqual(value['productcatalogservice'],source.plan())
        for identity in c.APPS:
            if identity!='productcatalogservice':c.build_request(identity,REV,value[identity])
        with tempfile.TemporaryDirectory() as tmp:
            for identity in c.APPS:
                c.materialize(source,identity,c.r.fingerprint(value[identity]),Path(tmp)/identity)
                self.assertTrue((Path(tmp)/identity/'Dockerfile').is_file())
            with self.assertRaises(ValueError):c.materialize(source,'cartservice','sha256:'+'0'*64,Path(tmp)/'bad')

    @unittest.skipUnless(os.environ.get('SDP_COLLECTOR_EXECUTABLE'),'native Collector optional validation')
    def test_native_otlp_counter_conversion_preserves_data_and_leaves_histograms(self):
        executable=os.environ['SDP_COLLECTOR_EXECUTABLE']
        version=subprocess.run([executable,'--version'],capture_output=True,check=True)
        self.assertIn(c.legacy.policy()['collector']['version'],(version.stdout+version.stderr).decode())
        config=w.collector_config(self.record)
        self.assertEqual([k for k,v in config['service']['pipelines'].items() if 'transform/integer_counters' in v['processors']],
                         ['metrics/currencyservice','metrics/paymentservice'])
        resources=[];expected={}
        counter_names=('online_shop.transport.requests','online_shop.transport.errors','online_shop.business.operations')
        for identity in ('currencyservice','paymentservice','adservice'):
            scopes=[]
            for temporality in (1,2):
                metrics=[]
                for name in (*counter_names,'unrelated.counter'):
                    points=[]
                    cases={'positive':('asDouble',7.0),'zero':('asDouble',0.0),'fraction':('asDouble',1.25),
                           'negative':('asDouble',-1.0),'overflow':('asDouble',float(2**63)),
                           'already_int':('asInt','23'),'int_zero':('asInt','0'),'large_int':('asInt',str(2**63-1))}
                    for case,(kind,value) in cases.items():
                        point={'attributes':[{'key':'case','value':{'stringValue':case}},{'key':'outcome','value':{'stringValue':'error' if name.endswith('errors') else 'ok'}}],
                            'startTimeUnixNano':'1000000000','timeUnixNano':'2000000000','flags':1,kind:value,
                            'exemplars':[{'filteredAttributes':[{'key':'sample','value':{'stringValue':'retained'}}],
                                'timeUnixNano':'1500000000','asDouble':1.0}]}
                        points.append(point);want=copy.deepcopy(point)
                        if identity!='adservice' and name in counter_names and case in ('positive','zero'):
                            want.pop('asDouble');want['asInt']=str(int(value))
                        expected[(identity,str(temporality),name,case)]=want
                    metrics.append({'name':name,'description':'Preserve this description','unit':'{request}',
                        'sum':{'aggregationTemporality':temporality,'isMonotonic':True,'dataPoints':points}})
                # Neither a gauge with a counter name nor duration histograms
                # may change representation, buckets, sum, bounds or temporality.
                metrics += [{'name':'online_shop.transport.errors','gauge':{'dataPoints':[{
                    'attributes':[{'key':'case','value':{'stringValue':'gauge'}}],'asDouble':2.5,'timeUnixNano':'2000000000'}]}},
                    {'name':'online_shop.transport.duration','unit':'s','histogram':{'aggregationTemporality':temporality,'dataPoints':[{
                        'startTimeUnixNano':'1000000000','timeUnixNano':'2000000000','count':'2','sum':1.25,
                        'bucketCounts':['1','1'],'explicitBounds':[0.5],'min':0.25,'max':1.0}]}}]
                scopes.append({'scope':{'name':str(temporality),'version':'test','attributes':[{'key':'scope','value':{'stringValue':'preserved'}}]},'metrics':metrics})
            resources.append({'resource':{'attributes':[{'key':k,'value':{'stringValue':v}} for k,v in {
                'service.name':identity,'service.version':c.r.REVISION,'deployment.environment.name':'dev','custom.resource':'preserved'}.items()]},'scopeMetrics':scopes})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);port_socket=socket.socket();port_socket.bind(('127.0.0.1',0));port=port_socket.getsockname()[1];port_socket.close()
            output=root/'output.jsonl'
            native={'receivers':{'otlp':{'protocols':{'http':{'endpoint':'127.0.0.1:'+str(port)}}}},
                'processors':{k:v for k,v in config['processors'].items() if k.startswith(('filter/','resource/','transform/'))},
                'exporters':{'file':{'path':str(output)}},'service':{'telemetry':{'metrics':{'level':'none','readers':[]}},'pipelines':{}}}
            for identity in ('currencyservice','paymentservice','adservice'):
                pipeline=copy.deepcopy(config['service']['pipelines']['metrics/'+identity])
                pipeline['processors']=[x for x in pipeline['processors'] if x not in ('memory_limiter','batch')];pipeline['exporters']=['file']
                native['service']['pipelines']['metrics/'+identity]=pipeline
            path=root/'config.json';path.write_text(json.dumps(native),encoding='utf-8')
            with (root/'collector.log').open('wb') as log:
                child=subprocess.Popen([executable,'--config='+str(path)],stdout=log,stderr=log)
                try:
                    deadline=time.monotonic()+15
                    while True:
                        self.assertIsNone(child.poll(),(root/'collector.log').read_text(errors='replace'))
                        try:
                            with socket.create_connection(('127.0.0.1',port),timeout=0.2):break
                        except OSError:
                            self.assertLess(time.monotonic(),deadline);time.sleep(0.1)
                    request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/v1/metrics',data=json.dumps({'resourceMetrics':resources}).encode(),headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=10) as response:self.assertEqual(response.status,200)
                    observed={};histograms={};gauges={}
                    while time.monotonic()<deadline:
                        observed.clear();histograms.clear();gauges.clear()
                        for line in output.read_text().splitlines() if output.exists() else []:
                            for rm in json.loads(line)['resourceMetrics']:
                                attrs={x['key']:x['value']['stringValue'] for x in rm['resource']['attributes']}
                                identity=attrs['service.name'];self.assertEqual(attrs['custom.resource'],'preserved')
                                for sm in rm['scopeMetrics']:
                                    scope=sm['scope'];self.assertEqual(scope['attributes'],[{'key':'scope','value':{'stringValue':'preserved'}}])
                                    for metric in sm['metrics']:
                                        key=(identity,scope['name'],metric['name'])
                                        if 'histogram' in metric:histograms[key]=metric['histogram'];continue
                                        if 'gauge' in metric:gauges[key]=metric['gauge'];continue
                                        data=metric['sum'];self.assertEqual(data['aggregationTemporality'],int(scope['name']));self.assertTrue(data['isMonotonic'])
                                        self.assertEqual((metric['description'],metric['unit']),('Preserve this description','{request}'))
                                        for point in data['dataPoints']:
                                            # OTLP's asDouble is IEEE754 even when its
                                            # JSON spelling is an integer literal.
                                            if 'asDouble' in point:point['asDouble']=float(point['asDouble'])
                                            case=next(x['value']['stringValue'] for x in point['attributes'] if x['key']=='case');observed[(*key,case)]=point
                        if len(observed)==len(expected):break
                        time.sleep(0.1)
                    self.assertEqual(set(observed),set(expected))
                    for key in expected:self.assertEqual(observed[key],expected[key],str(key))
                    for rm in resources:
                        identity=rm['resource']['attributes'][0]['value']['stringValue']
                        for sm in rm['scopeMetrics']:
                            for metric in sm['metrics']:
                                key=(identity,sm['scope']['name'],metric['name'])
                                if 'histogram' in metric:self.assertEqual(histograms[key],metric['histogram'])
                                if 'gauge' in metric:self.assertEqual(gauges[key],metric['gauge'])
                finally:
                    child.terminate()
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)

    @unittest.skipUnless(os.environ.get('SDP_COLLECTOR_EXECUTABLE'),'native Collector optional validation')
    def test_real_collector_full_configuration_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            for config in (w.collector_config(self.record),w.redis_metrics_config(self.record)):
                path=Path(tmp)/'config.json';path.write_text(json.dumps(config),encoding='utf-8')
                result=subprocess.run([os.environ['SDP_COLLECTOR_EXECUTABLE'],'validate','--config='+str(path)],capture_output=True)
                self.assertEqual(result.returncode,0,(result.stdout+result.stderr).decode(errors='replace'))

if __name__=='__main__':unittest.main()
