"""Synthetic accepted evidence for offline tests; never a deployable release."""
import copy


def accepted_policy(release):
    q = copy.deepcopy(release.read(release.ROOT / "deploy/online-shop/policy.json"))
    project = release.policy()["project"]
    q["accepted_release"] = {
        "binding": release.binding()["id"], "project": project,
        "configuration_revision": "c" * 40,
        "build_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "signing_build_id": "66666666-7777-8888-9999-000000000000",
        "release_set_id": "sha256:" + "a" * 64, "manifest_digest": "sha256:" + "b" * 64,
        "candidate_generation": "123456789", "candidate_transport_sha256": "sha256:" + "e" * 64,
        "occurrence": "projects/" + project + "/occurrences/catalog-fixture"}
    q["collector_occurrence"] = "projects/" + project + "/occurrences/collector-fixture"
    return q
