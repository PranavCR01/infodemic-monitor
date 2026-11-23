"""Request review on a result the review rule didn't send to a person (T32; §11, §12, §17).

``POST /v1/jobs/{job_id}/review-request`` with a required note. Real HS256 JWTs checked
by the real ``get_current_user`` (the T27 test helpers); SQLite and, in CI, Postgres. No
model or network calls.
"""
from __future__ import annotations

import pytest

from app.api import ownership
from app.auth.roles import Role, has_role
from app.services.review_reasons import parse_reason
from app.tests.test_review_api import (  # noqa: F401  (pytest fixtures)
    ADMIN, ANALYST, REVIEWER, add_case, auth, env, pg_engine, token,
)

OWNER = ANALYST  # sub "analyst-1"
OTHER = auth(token("analyst-2"))
NOTE = "The speaker's claim about vitamin C looks wrong to me."


def add_job(env, job_id, *, status="SUCCESS", with_result=True, label="BENIGN", claims=()):
    """A finished job, optionally with stored claim rows: (claim_id, text, category,
    stance, verdict)."""
    from app.db.models.claim import ClaimRow, ClaimStanceRow, VerificationResultRow
    from app.db.models.job import Job, JobStatus
    from app.db.models.result import Result
    from app.db.models.video import Video

    s = env["Session"]()
    s.add(Video(id=f"vid-{job_id}", filename=f"{job_id}.mp4", file_path="/x", file_size=1,
                storage_key=f"uploads/u/{job_id}.mp4"))
    s.flush()
    s.add(Job(id=job_id, video_id=f"vid-{job_id}", status=JobStatus(status)))
    s.flush()
    if with_result:
        s.add(Result(job_id=job_id, label=label, confidence=0.82, explanation="No false claims found.",
                     evidence_snippets=[], combined_content="", provider="graph", model_used="none",
                     latency_ms=1, pipeline="graph", pipeline_version="graph-v1",
                     decision_rule="no_misinfo", deciding_claim_ids=[c[0] for c in claims]))
    for cid, text, category, stance, verdict in claims:
        row = ClaimRow(job_id=job_id, claim_id=cid, text=text, category=category,
                       start_seconds=0.0, end_seconds=1.0, source_segment_ids=["t1"])
        s.add(row)
        s.flush()
        if stance:
            s.add(ClaimStanceRow(claim_pk=row.id, stance=stance, segment_ids=["t1"]))
        if verdict:
            s.add(VerificationResultRow(claim_pk=row.id, verdict=verdict, limitations=[]))
    s.commit()
    s.close()


def post(env, job_id, headers, body=None):
    return env["client"].post(f"/v1/jobs/{job_id}/review-request", headers=headers,
                              json={"note": NOTE} if body is None else body)


def db_state(env, job_id):
    from app.db.models.job import Job
    from app.db.models.review import AuditEvent, HumanReview

    s = env["Session"]()
    try:
        job = s.get(Job, job_id)
        cases = s.query(HumanReview).filter(HumanReview.job_id == job_id).all()
        events = s.query(AuditEvent).filter(AuditEvent.job_id == job_id).all()
        return (job.status.value if job else None, cases,
                [(e.action, e.actor_id, e.reason, dict(e.details)) for e in events])
    finally:
        s.close()


@pytest.fixture
def owners(monkeypatch):
    """Stand-in for the owner check T28/T33 put in ``app.api.ownership``: the owner, or
    a reviewer/admin. The route must go through ``ownership`` for this to bite."""
    table: dict[str, str] = {}

    def can_view_job(job, user):
        return has_role(user, Role.REVIEWER) or table.get(job.id) == (user or {}).get("sub")

    monkeypatch.setattr(ownership, "can_view_job", can_view_job)
    return table


# ------------------------------------------------------------------ creating a case


def test_owner_opens_a_case_with_reason_note_and_audit(env, owners):
    owners["j1"] = "analyst-1"
    add_job(env, "j1")
    r = post(env, "j1", OWNER)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] is True and body["job_id"] == "j1"
    assert body["case_status"] == "OPEN" and body["job_status"] == "REVIEW_REQUIRED"
    assert body["reasons"] == ["user_requested"]
    detail = body["reason_details"][0]
    assert detail["code"] == "user_requested" and detail["rule"] == "user_requested"
    # Plain wording for analysts: no rule code, no node names.
    assert detail["text"] == "Someone asked for a person to check this result."
    assert body["request"]["requested_by"] == "analyst-1" and body["request"]["note"] == NOTE
    # The requester sees neither the proposed result nor the audit trail.
    assert "proposed_result" not in body and "audit_trail" not in body

    status, cases, events = db_state(env, "j1")
    assert status == "REVIEW_REQUIRED" and len(cases) == 1
    case = cases[0]
    assert case.id == body["review_id"] and case.reasons == ["user_requested"]
    assert case.rules_fired == [{"rule": "user_requested", "reasons": ["user_requested"]}]
    assert case.proposed_label == "BENIGN" and case.proposed_result["classification"] == "BENIGN"
    assert case.proposed_result["source"] == "stored_result" and case.pipeline_version == "graph-v1"
    assert case.policy_version and case.reviewer_id is None and case.action is None
    assert events == [("review_requested", "analyst-1", NOTE, {
        "review_id": case.id, "requester_role": "analyst", "job_status_before": "SUCCESS",
        "proposed_label": "BENIGN"})]


def test_note_is_stripped(env):
    add_job(env, "j1")
    r = post(env, "j1", OWNER, {"note": f"  {NOTE}\n "})
    assert r.status_code == 201 and r.json()["request"]["note"] == NOTE


def test_reviewer_sees_the_request_in_the_queue_and_case(env):
    add_job(env, "j1")
    rid = post(env, "j1", OWNER).json()["review_id"]
    c = env["client"]
    queue = c.get("/v1/reviews?reason=user_requested", headers=REVIEWER).json()
    assert [i["review_id"] for i in queue["items"]] == [rid]
    assert queue["items"][0]["rules_fired"] == [{"rule": "user_requested", "reasons": ["user_requested"]}]
    case = c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()
    assert case["request"]["requested_by"] == "analyst-1" and case["request"]["note"] == NOTE
    assert [e["action"] for e in case["audit_trail"]] == ["review_requested"]
    assert case["audit_trail"][0]["reason"] == NOTE


def test_rule_opened_cases_have_no_request_info(env):
    rid = add_case(env, "j1")
    case = env["client"].get(f"/v1/reviews/{rid}", headers=REVIEWER).json()
    assert case["request"] is None


def test_reviewer_decision_resolves_a_requested_case(env):
    add_job(env, "j1", label="BENIGN")
    rid = post(env, "j1", OWNER).json()["review_id"]
    r = env["client"].post(f"/v1/reviews/{rid}/decision", headers=REVIEWER,
                           json={"action": "CORRECT", "reason": "Claim is false", "corrected_label": "MISINFO"})
    assert r.status_code == 200, r.text
    status, cases, events = db_state(env, "j1")
    assert status == "SUCCESS" and cases[0].corrected_label == "MISINFO"
    assert [e[0] for e in events] == ["review_requested", "review_decision"]


def test_severity_comes_from_the_stored_claims(env):
    add_job(env, "hi", claims=[
        ("c1", "Vitamin C cures cancer", "treatment_efficacy", "ENDORSES", "CONTRADICTED"),
        ("c2", "Walking is good for you", "lifestyle", "ENDORSES", "SUPPORTED"),
    ])
    add_job(env, "plain")  # single-call path: no claim rows, no severity
    assert post(env, "hi", OWNER).status_code == 201
    assert post(env, "plain", OWNER).status_code == 201
    _, (case,), _ = db_state(env, "hi")
    assert case.severity == "HIGH" and case.severity_table_version
    assert case.claim_severities["c1"]["misinfo_relevant"] is True
    assert case.claim_severities["c2"]["misinfo_relevant"] is False
    assert case.claim_severities["c1"]["stance"] == "ENDORSES"
    _, (plain,), _ = db_state(env, "plain")
    assert plain.severity is None and plain.claim_severities is None
    queue = env["client"].get("/v1/reviews", headers=REVIEWER).json()
    assert [i["job_id"] for i in queue["items"]] == ["hi", "plain"]


def test_unknown_stored_verdict_does_not_break_the_request(env):
    add_job(env, "j1", claims=[("c1", "Something", "other", "ENDORSES", "SOME_NEW_VERDICT")])
    assert post(env, "j1", OWNER).status_code == 201
    _, (case,), _ = db_state(env, "j1")
    assert case.claim_severities["c1"]["misinfo_relevant"] is False


# ------------------------------------------------------------------ idempotency


def test_second_request_returns_the_same_case(env):
    add_job(env, "j1")
    first = post(env, "j1", OWNER).json()
    again = post(env, "j1", OWNER, {"note": "another note"})
    assert again.status_code == 200
    body = again.json()
    assert body["created"] is False and body["review_id"] == first["review_id"]
    assert body["request"]["note"] == NOTE  # the first request's note stands
    by_reviewer = post(env, "j1", REVIEWER)
    assert by_reviewer.status_code == 200 and by_reviewer.json()["review_id"] == first["review_id"]
    _, cases, events = db_state(env, "j1")
    assert len(cases) == 1 and len(events) == 1


def test_case_opened_by_the_review_rule_is_returned_unchanged(env):
    rid = add_case(env, "j1", reasons=("weak_evidence:c1",))
    r = post(env, "j1", OWNER)
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is False and body["review_id"] == rid
    assert body["reasons"] == ["weak_evidence:c1"] and body["request"] is None
    status, cases, events = db_state(env, "j1")
    assert status == "REVIEW_REQUIRED" and cases[0].reasons == ["weak_evidence:c1"] and events == []


def test_resolved_case_is_returned_not_reopened(env):
    rid = add_case(env, "j1", status="RESOLVED")
    r = post(env, "j1", OWNER)
    assert r.status_code == 200
    assert r.json()["review_id"] == rid and r.json()["case_status"] == "RESOLVED"
    _, cases, events = db_state(env, "j1")
    assert len(cases) == 1 and cases[0].status.value == "RESOLVED" and events == []


# ------------------------------------------------------------------ the note


@pytest.mark.parametrize("body", [
    {}, {"note": ""}, {"note": "   \n\t"}, {"note": None}, {"note": "x" * 2001},
    {"note": NOTE, "requester_id": "someone-else"},  # the requester comes from the token
    {"note": NOTE, "role": "admin"},
])
def test_note_is_required_and_limited(env, body):
    add_job(env, "j1")
    r = post(env, "j1", OWNER, body)
    assert r.status_code == 422
    status, cases, events = db_state(env, "j1")
    assert status == "SUCCESS" and cases == [] and events == []


def test_note_at_the_limit_is_accepted(env):
    add_job(env, "j1")
    assert post(env, "j1", OWNER, {"note": "x" * 2000}).status_code == 201


# ------------------------------------------------------------------ access


def test_requires_sign_in(env):
    add_job(env, "j1")
    assert env["client"].post("/v1/jobs/j1/review-request", json={"note": NOTE}).status_code == 401
    assert db_state(env, "j1")[1] == []


def test_another_user_gets_404_and_nothing_changes(env, owners):
    owners["j1"] = "analyst-1"
    add_job(env, "j1")
    r = post(env, "j1", OTHER)
    assert r.status_code == 404
    # Same answer as for a job that doesn't exist.
    assert post(env, "missing", OTHER).status_code == 404
    status, cases, events = db_state(env, "j1")
    assert status == "SUCCESS" and cases == [] and events == []
    # Nor can they learn about an existing case through the idempotent path.
    post(env, "j1", OWNER)
    assert post(env, "j1", OTHER).status_code == 404


@pytest.mark.parametrize("headers,sub,role", [(REVIEWER, "reviewer-1", "reviewer"), (ADMIN, "admin-1", "admin")])
def test_reviewer_and_admin_may_request_on_others_jobs(env, owners, headers, sub, role):
    owners["j1"] = "analyst-1"
    add_job(env, "j1")
    r = post(env, "j1", headers)
    assert r.status_code == 201 and r.json()["request"]["requested_by"] == sub
    assert db_state(env, "j1")[2][0][3]["requester_role"] == role


# ------------------------------------------------------------------ job state


def test_missing_job_is_404(env):
    assert post(env, "nope", OWNER).status_code == 404


@pytest.mark.parametrize("status,with_result", [
    ("PENDING", False), ("STARTED", False), ("FAILED", False), ("SUCCESS", False), ("FAILED", True),
])
def test_job_without_a_finished_result_is_409(env, status, with_result):
    add_job(env, "j1", status=status, with_result=with_result)
    r = post(env, "j1", OWNER)
    assert r.status_code == 409
    st, cases, events = db_state(env, "j1")
    assert st == status and cases == [] and events == []


# ------------------------------------------------------------------ reasons and service


def test_user_requested_reason_wording():
    v = parse_reason("user_requested")
    assert v.code == "user_requested" and v.rule == "user_requested" and v.claim_id is None
    assert "user_requested" not in v.text and "rule" not in v.text.lower()


def test_service_rejects_blank_note_and_missing_requester(env):
    from app.db.models.job import Job
    from app.services import review_service as rs

    add_job(env, "j1")
    s = env["Session"]()
    try:
        job = s.get(Job, "j1")
        with pytest.raises(rs.ReviewError, match="note"):
            rs.request_review(s, job, requester_id="u", note="  ")
        with pytest.raises(rs.ReviewError, match="longer"):
            rs.request_review(s, job, requester_id="u", note="x" * (rs.REQUEST_NOTE_MAX + 1))
        with pytest.raises(rs.ReviewError, match="requester"):
            rs.request_review(s, job, requester_id="", note=NOTE)
    finally:
        s.close()


def test_service_returns_the_winner_when_a_concurrent_insert_lands_first(env, monkeypatch):
    """Two requests race: the loser's insert hits the unique job_id and gets the case
    the winner opened, not an error and not a second case."""
    from app.db.models.job import Job
    from app.db.models.review import HumanReview
    from app.services import review_service as rs

    add_job(env, "j1")
    winner_id = post(env, "j1", OWNER).json()["review_id"]
    s = env["Session"]()
    try:
        job = s.get(Job, "j1")
        from app.db.models.job import JobStatus
        job.status = JobStatus.SUCCESS  # as the loser saw it before the winner committed
        real_query = s.query
        calls = {"n": 0}

        def query(model, *a, **k):
            q = real_query(model, *a, **k)
            if model is HumanReview and calls["n"] == 0:
                calls["n"] += 1
                return real_query(HumanReview).filter(HumanReview.id == "__none__")
            return q

        monkeypatch.setattr(s, "query", query)
        case, created = rs.request_review(s, job, requester_id="analyst-1", note=NOTE)
        assert created is False and case.id == winner_id
    finally:
        s.close()
    _, cases, events = db_state(env, "j1")
    assert len(cases) == 1 and len(events) == 1
