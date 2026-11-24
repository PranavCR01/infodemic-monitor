"""The blind step on routes outside the review router (T34; D7; design §12, §15).

A reviewer who hasn't given their own judgement on an open HIGH case can't read the
job's result, claims or evidence, or its label in the job list (or probe it with a
label filter). Uses test_ownership_t33's whole-app fixture: alice's, bob's and a legacy
HIGH case, with pre-reveals already recorded for its callers; ``rhea`` is a reviewer
with none. No network, no models.
"""
from __future__ import annotations

import pytest

from app.tests import test_ownership_t33 as t33
from app.tests.test_ownership_t33 import env, pg_engine  # noqa: F401  (fixtures)


def _no_system_view(text: str) -> None:
    for word in ("CONTRADICTED", "ENDORSES", "MISINFO"):
        assert word not in text, word


RHEA = t33.auth("rhea", "reviewer", email="rhea@example.org")
RESULT_ROUTES = ("/v1/videos/vid-alice/results", "/v1/videos/vid-alice/claims",
                 "/v1/claims/claim-alice/evidence", "/jobs/job-alice/result")


def test_result_routes_refuse_a_blind_reviewer(env):
    c = env["client"]
    for path in RESULT_ROUTES:
        r = c.get(path, headers=RHEA)
        assert r.status_code == 403, (path, r.status_code)
        assert r.json()["detail"]["code"] == "PRE_REVEAL_REQUIRED" and r.json()["detail"]["review_id"] == "rev-alice"
        _no_system_view(r.text)
        # The owner, and a reviewer who has given their judgement, still read it.
        assert c.get(path, headers=t33.CALLERS["owner"]).status_code == 200
        assert c.get(path, headers=t33.CALLERS["reviewer"]).status_code == 200
        # Someone who may not see the job still gets 404, not a hint.
        assert c.get(path, headers=t33.CALLERS["other"]).status_code == 404
    r = c.post("/v1/reviews/rev-alice/pre-reveal", headers=RHEA,
               json={"claims": [{"claim_id": "c1", "stance": "ENDORSES", "verdict": "CONTRADICTED"}]})
    assert r.status_code == 201
    for path in RESULT_ROUTES:
        assert c.get(path, headers=RHEA).status_code == 200, path


@pytest.mark.parametrize("path", ["/v1/jobs", "/jobs"])
def test_job_list_hides_labels_of_blind_jobs_and_label_filters_skip_them(env, path):
    c = env["client"]

    def rows(headers, **params):
        body = c.get(path, headers=headers, params=params).json()
        return {r["job_id"]: r for r in (body["items"] if isinstance(body, dict) else body)}

    seen = rows(RHEA)
    assert set(seen) == {"job-alice", "job-bob"}
    for job in seen.values():
        assert job["label"] is job["confidence"] is job["label_display"] is job["misinfo_basis"] is None
    assert rows(RHEA, label="MISINFO") == {}
    assert rows(t33.CALLERS["owner"])["job-alice"]["label"] == "MISINFO"
    assert set(rows(t33.CALLERS["reviewer"], label="MISINFO")) == {"job-alice", "job-bob"}
    c.post("/v1/reviews/rev-bob/pre-reveal", headers=RHEA,
           json={"claims": [{"claim_id": "c1", "stance": "ENDORSES", "verdict": "CONTRADICTED"}]})
    assert rows(RHEA)["job-bob"]["label"] == "MISINFO" and rows(RHEA)["job-alice"]["label"] is None
    assert set(rows(RHEA, label="MISINFO")) == {"job-bob"}
