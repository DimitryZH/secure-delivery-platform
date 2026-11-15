"""Offline source activation boundaries; no SDK, API or credential access."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
OLD = '89fd1cde8285761cc2a35dfb22d145adb2eed980'
NEW = '67b6cd85ae01c698bbf86904d953d5145b7b5820'
BASE = 'd9585783aa52814b59add57af09cdb91a10411c4'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


c = load('source_adoption_complete', 'cloudbuild/online-shop/complete.py')
r = c.r


class SourceAdoptionTests(unittest.TestCase):
    def test_active_source_agrees_across_catalog_complete_and_runtime(self):
        self.assertEqual(r.REVISION, NEW)
        self.assertEqual(r.PROFILE['revision'], NEW)
        self.assertEqual(c.profile()['source']['revision'], NEW)
        runtime = r.read(ROOT / 'deploy/online-shop/complete-runtime-v1.json')
        self.assertEqual(runtime['aml_revision'], NEW)
        self.assertEqual(runtime['source_sha256'], c.profile()['contracts_sha256']['kubernetes/online-shop.yaml'])
        catalog_schema = r.read(ROOT / 'cloudbuild/online-shop/candidate-v1.schema.json')
        full_schema = r.read(ROOT / 'cloudbuild/online-shop/complete-candidate-v1.schema.json')
        self.assertEqual(catalog_schema['properties']['source']['properties']['revision']['const'], NEW)
        self.assertEqual(full_schema['$defs']['source']['properties']['revision']['const'], NEW)
        self.assertEqual(full_schema['properties']['profile_sha256']['const'], 'sha256:' + c.PROFILE_SHA)
        template = r.read(ROOT / 'deploy/online-shop/collector.json')
        versions = [x['value'] for x in template['processors']['resource/catalog']['attributes'] if x['key'] == 'service.version']
        self.assertEqual(versions, [NEW])
        self.assertEqual(len(runtime['documents']), 32)
        self.assertFalse(any(x['metadata']['name'] == 'loadgenerator' for x in runtime['documents']))

    def test_bootstrap_catalog_available_while_missing_acceptance_blocks_full_release(self):
        pending = copy.deepcopy(c.legacy.policy()); pending['accepted_release'] = None
        request = r.build_request(r.policy(), 'c' * 40, plan_hash='sha256:' + '1' * 64)
        self.assertEqual(request['timeout'], '1200s')
        self.assertIn('SOURCE_REVISION=' + NEW, request['steps'][1]['args'])
        with patch.object(c.legacy, 'policy', return_value=pending), self.assertRaisesRegex(ValueError, 'accepted_catalog_pending'):
            c.build_request('recommendationservice', 'c' * 40, {})

    def test_old_candidate_source_rejected_after_identity_recomputation(self):
        ref = {'sha256': 'sha256:' + '1' * 64}
        record = r.candidate(r.policy(), 'c' * 40, ref,
                             'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                             'sha256:' + '2' * 64, 'sha256:' + '3' * 64)
        record['source']['revision'] = OLD
        record['release_set_id'] = r.fingerprint({k:v for k,v in record.items() if k != 'release_set_id'})
        cloud = Mock()
        with self.assertRaisesRegex(ValueError, 'candidate_policy_or_identity_mismatch'):
            r.verify(record, r.policy(), 'c' * 40, {}, ref, cloud)
        self.assertEqual(cloud.mock_calls, [])

    def test_registry_revision_label_required_even_when_other_input_bytes_match(self):
        for revision in (OLD, NEW):
            config = r.canonical({'os':'linux', 'architecture':'amd64', 'config':{
                'Labels':{'org.opencontainers.image.revision':revision}}})
            manifest = r.canonical({'schemaVersion':2, 'config':{'digest':'sha256:' + r.sha(config)}})
            cloud = r.Cloud.__new__(r.Cloud)
            cloud.request = Mock(side_effect=[manifest, config])
            if revision == NEW:
                self.assertEqual(cloud.image(r.policy()['registry'] + '/online-shop-frontend', 'sha256:' + r.sha(manifest)), 'sha256:' + r.sha(config))
            else:
                with self.assertRaisesRegex(ValueError, 'registry_revision_label_mismatch'):
                    cloud.image(r.policy()['registry'] + '/online-shop-frontend', 'sha256:' + r.sha(manifest))

    def test_prior_acceptance_and_raw_evidence_remain_historical(self):
        source = r.Source(ROOT, BASE)
        before = json.loads(source.blob('deploy/online-shop/policy.json'))
        historical = r.read(ROOT / 'cloudbuild/online-shop/source-adoption-validation.json')['historical_accepted_catalog']
        self.assertEqual({k:historical[k] for k in before['accepted_release']}, before['accepted_release'])
        current = copy.deepcopy(c.legacy.policy())
        current['accepted_release'] = None
        before['accepted_release'] = None
        self.assertEqual(current, before)
        for name in ('cloudbuild/online-shop/validation.json', 'cloudbuild/online-shop/complete-execution-validation.json',
                     'deploy/online-shop/complete-validation.json'):
            self.assertEqual((ROOT / name).read_bytes().replace(b'\r\n', b'\n'), source.blob(name))

    @unittest.skipUnless(os.environ.get('SDP_AML_REPOSITORY'), 'requires local immutable AML Git objects')
    def test_full_intermediate_delta_and_all_ten_revision_arguments(self):
        import yaml
        repo = os.environ['SDP_AML_REPOSITORY']
        old, new = r.Source(repo, OLD), r.Source(repo, NEW)
        with self.assertRaisesRegex(ValueError, 'wrong_aml_revision'):
            c.plans(old)
        plans = c.plans(new)
        planner = types.ModuleType('old_immutable_planner')
        exec(compile(old.blob(r.WORKLOAD + '/build_plan.py'), '<old planner>', 'exec'), planner.__dict__)
        previous = planner.plan(repo, OLD, list(c.APPS), 'linux/amd64')
        for before in previous['components']:
            identity = before['id']
            after = plans[identity]['components'][0]
            self.assertEqual(after['buildArguments']['SOURCE_REVISION'], NEW)
            self.assertEqual(before['dockerfileSha256'], after['dockerfileSha256'])
            a = {x['path']:x['sha256'] for x in before['inputs']}
            b = {x['path']:x['sha256'] for x in after['inputs']}
            changed = {p for p in a.keys() | b.keys() if a.get(p) != b.get(p)}
            expected = {'src/recommendationservice/telemetry.py', 'src/recommendationservice/test_catalog_deadline.py'} if identity == 'recommendationservice' else set()
            self.assertEqual(changed, expected)
        self.assertEqual(plans['productcatalogservice'], new.plan())
        documents = [x for x in yaml.safe_load_all(new.blob(r.WORKLOAD + '/kubernetes/online-shop.yaml'))
                     if x and x['metadata']['name'] != 'loadgenerator']
        self.assertEqual(documents, r.read(ROOT / 'deploy/online-shop/complete-runtime-v1.json')['documents'])
        q = c.redis_policy()
        for name, digest in q['selection_contracts_sha256'].items():
            self.assertEqual('sha256:' + r.sha(new.blob(r.WORKLOAD + '/' + name)), digest)


if __name__ == '__main__':
    unittest.main()
