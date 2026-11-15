"""Recorded catalog acceptance consistency; raw cloud evidence stays private."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('accepted_catalog_workflow', ROOT / 'deploy/online-shop/workflow.py')
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
r = w.r


class AcceptedCatalogTests(unittest.TestCase):
    def test_policy_preserves_verified_producer_original_transport_and_signer(self):
        evidence = r.read(ROOT / 'cloudbuild/online-shop/catalog-acceptance-validation.json')
        accepted = w.accepted_catalog()
        self.assertEqual(accepted, evidence['accepted_release'])
        self.assertEqual(accepted['configuration_revision'], evidence['configuration_revision'])
        self.assertEqual(evidence['source_revision'], r.REVISION)
        self.assertEqual(evidence['producing_build']['id'], accepted['build_id'])
        self.assertEqual(evidence['signing_build']['id'], accepted['signing_build_id'])
        self.assertEqual(evidence['verification']['signature_validation'], 'VERIFIED')
        self.assertIs(evidence['temporaryHold'], True)
        self.assertNotIn('readback_generation', accepted)
        uri = ('gs://' + r.binding()['candidate_bucket'] + '/online-shop/catalog-v1/'
               + accepted['configuration_revision'] + '/' + accepted['build_id']
               + '/candidate.json#' + accepted['candidate_generation'])
        request = r.signing_request(r.policy(), accepted['configuration_revision'], uri,
                                   accepted['candidate_transport_sha256'])
        self.assertEqual(r.fingerprint(request), evidence['signing_request_sha256'])
        self.assertEqual(request['timeout'], str(evidence['signing_build']['timeout_seconds']) + 's')
        self.assertLessEqual(int(request['timeout'][:-1]), evidence['signing_build']['authorized_maximum_seconds'])
        self.assertEqual(evidence['artifact'], r.policy()['registry'] + '/online-shop-productcatalogservice@' + accepted['manifest_digest'])
        self.assertNotEqual(request['serviceAccount'], r.policy()['producer'])

    def test_missing_or_mixed_acceptance_still_fails_closed(self):
        document = w.policy()
        for field, bad in [('candidate_generation', True), ('candidate_generation', 1.0),
                           ('candidate_generation', '0'), ('candidate_transport_sha256', 'unknown'),
                           ('binding', 'foreign-binding'), ('project', 'foreign-project'),
                           ('signing_build_id', 'pending')]:
            altered = copy.deepcopy(document); altered['accepted_release'][field] = bad
            with self.subTest(field=field, value=bad), patch.object(w, 'policy', return_value=altered), self.assertRaises(ValueError):
                w.accepted_catalog()
        pending = copy.deepcopy(document); pending['accepted_release'] = None
        with patch.object(w, 'policy', return_value=pending), self.assertRaisesRegex(ValueError, 'accepted_catalog_pending'):
            w.accepted_catalog()


if __name__ == '__main__':
    unittest.main()
