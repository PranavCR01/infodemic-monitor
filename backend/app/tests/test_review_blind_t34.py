"""Review decision completeness (T34; lead's decision D7; design §12, §15, §17).

(a) reason codes next to a 10-character note; (b) the blind "your judgement first" step
on HIGH cases, enforced by the server on the case view, the queue, the result routes,
the job list and the decision; (c) names and ``is_own`` on review views.

Tokens are real HS256 JWTs checked by the real ``get_current_user``; nothing calls
Supabase (names come from the verified tokens) or any model. Uses the fixtures of
test_review_api (review router only) and test_ownership_t33 (the whole app).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.models.review import AuditEvent, HumanReview, ReviewCaseStatus, ReviewPreReveal
from app.db.models.user import User
from app.tests import test_ownership_t33 as t33
from app.tests.test_review_api import (  # noqa: F401  (fixtures)
    ADMIN,
    ANALYST,
    REVIEWER,
    REVIEWER2,
    add_case,
    auth,
    env,
    pg_engine,
    token,
)

BLIND = ()  # add_case(revealed=BLIND): nobody has given their judgement yet
PRE = {"claims": [{"claim_id": "c1", "stance": "REFUTES", "verdict": "SUPPORTED"},
                  {"claim_id": "c2", "stance": "QUOTES", "verdict": "INSUFFICIENT_EVIDENCE"}]}
APPROVE = {"action": "APPROVE", "reason": "papers check out", "reason_code": "SYSTEM_CORRECT"}


def _events(env, action=None):
    s = env["Session"]()
    q = s.query(AuditEvent)
    if action:
        q = q.filter(AuditEvent.action == action)
    out = [(e.actor_id, e.action, e.reason, dict(e.details or {})) for e in q.order_by(AuditEvent.created_at).all()]
    s.close()
    return out


# ------------------------------------------------------------------ (a) reason codes


def test_reason_code_is_stored_on_the_case_the_view_and_the_audit_trail(env):
    c = env["client"]
    rid = add_case(env, "j1", severity="MEDIUM")
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json={
        "action": "CORRECT", "reason": "speaker is debunking the claim", "reason_code": "STANCE_MISREAD",
        "claim_corrections": [{"claim_id": "c1", "stance": "REFUTES"}]})
    assert r.status_code == 200, r.text
    d = r.json()["case"]["decision"]
    assert d["reason_code"] == "STANCE_MISREAD" and d["reason"] == "speaker is debunking the claim"
    s = env["Session"]()
    assert s.get(HumanReview, rid).reason_code == "STANCE_MISREAD"
    s.close()
    [(actor, _, reason, details)] = _events(env, "review_decision")
    assert (actor, reason, details["reason_code"]) == ("reviewer-1", "speaker is debunking the claim", "STANCE_MISREAD")
    assert "reason_code_defaulted" not in details
    trail = c.get(f"/v1/reviews/{rid}", headers=ADMIN).json()["audit_trail"]
    assert trail[-1]["details"]["reason_code"] == "STANCE_MISREAD"


@pytest.mark.parametrize("code", ["CLAIM_OVERGENERALISED", "EVIDENCE_MISREAD", "STANCE_MISREAD",
                                  "MISSING_SOURCE", "OTHER"])
def test_every_code_is_accepted(env, code):
    rid = add_case(env, "j1", severity="LOW")
    r = env["client"].post(f"/v1/reviews/{rid}/decision", headers=REVIEWER,
                           json={"action": "REJECT", "reason": "not a health video", "reason_code": code})
    assert r.status_code == 200 and r.json()["case"]["decision"]["reason_code"] == code


def test_a_client_without_reason_code_gets_other_flagged_as_defaulted(env):
    """Backward compatibility: decision clients written before T34 keep working."""
    rid = add_case(env, "j1", severity="LOW")
    r = env["client"].post(f"/v1/reviews/{rid}/decision", headers=REVIEWER,
                           json={"action": "APPROVE", "reason": "papers check out"})
    assert r.status_code == 200 and r.json()["case"]["decision"]["reason_code"] == "OTHER"
    [(_, _, _, details)] = _events(env, "review_decision")
    assert details["reason_code"] == "OTHER" and details["reason_code_defaulted"] is True


@pytest.mark.parametrize("body", [
    {"action": "APPROVE", "reason": "too short", "reason_code": "OTHER"},           # 9 characters
    {"action": "APPROVE", "reason": "   short    ", "reason_code": "OTHER"},        # trimmed
    {"action": "APPROVE", "reason": "papers check out", "reason_code": "WRONG"},
    {"action": "REJECT", "reason": "papers check out", "reason_code": "SYSTEM_CORRECT"},
    {"action": "CORRECT", "reason": "papers check out", "reason_code": "SYSTEM_CORRECT",
     "corrected_label": "NO_MISINFO"},
])
def test_bad_reason_or_code_is_refused_and_nothing_changes(env, body):
    rid = add_case(env, "j1", severity="LOW")
    r = env["client"].post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=body)
    assert r.status_code == 422, r.text
    s = env["Session"]()
    assert s.get(HumanReview, rid).status == ReviewCaseStatus.OPEN
    s.close()
    assert _events(env) == []


def test_ten_character_note_is_enough(env):
    rid = add_case(env, "j1", severity="LOW")
    r = env["client"].post(f"/v1/reviews/{rid}/decision", headers=REVIEWER,
                           json={"action": "APPROVE", "reason": "  0123456789 ", "reason_code": "SYSTEM_CORRECT"})
    assert r.status_code == 200


# ------------------------------------------------------------------ (b) blind step: the case view


def _no_system_view(text: str) -> None:
    for word in ("CONTRADICTED", "ENDORSES", "MISINFO", "mixed_video", "INSUFFICIENT_EVIDENCE"):
        assert word not in text, word


def test_high_case_withholds_the_system_view_until_pre_reveal(env):
    c = env["client"]
    rid = add_case(env, "j1", revealed=BLIND)
    r = c.get(f"/v1/reviews/{rid}", headers=REVIEWER)
    assert r.status_code == 200
    case = r.json()
    assert case["blind_step_required"] is True and case["system_view_withheld"] is True
    assert case["proposed_label"] is None and case["proposed_result"] is None
    assert case["reasons"] == [] and case["rules_fired"] == [] and case["validation_errors"] == []
    assert case["severity"] == "HIGH"  # the queue priority stays visible
    assert case["claim_severities"]["c1"] == {"severity": "HIGH", "basis": ["topic:cancer"]}
    assert {cl["claim_id"]: (cl["stance"], cl["verdict"]) for cl in case["claims"]} == {
        "c1": (None, None), "c2": (None, None)}
    assert case["pre_reveal"] is None
    _no_system_view(r.text)

    # Giving one's own judgement reveals it, in the same response.
    r = c.post(f"/v1/reviews/{rid}/pre-reveal", headers=REVIEWER, json={**PRE, "note": "looks like a debunk"})
    assert r.status_code == 201, r.text
    case = r.json()
    assert case["system_view_withheld"] is False and case["proposed_label"] == "MISINFO"
    assert case["reasons"] == ["judge:mixed_video"]
    assert {cl["claim_id"]: (cl["stance"], cl["verdict"]) for cl in case["claims"]} == {
        "c1": ("ENDORSES", "CONTRADICTED"), "c2": ("QUOTES", "INSUFFICIENT_EVIDENCE")}
    assert case["pre_reveal"]["claims"] == {"c1": {"stance": "REFUTES", "verdict": "SUPPORTED"},
                                            "c2": {"stance": "QUOTES", "verdict": "INSUFFICIENT_EVIDENCE"}}
    assert case["pre_reveal"]["reviewer_id"] == "reviewer-1" and case["pre_reveal"]["created_at"]
    assert c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()["system_view_withheld"] is False

    # Each reviewer is blind until they give their own.
    r = c.get(f"/v1/reviews/{rid}", headers=REVIEWER2)
    assert r.json()["system_view_withheld"] is True and r.json()["pre_reveal"] is None
    _no_system_view(r.text)  # reviewer-1's judgement (in the audit trail) is withheld too


def test_pre_reveal_is_audited_with_a_server_timestamp_and_kept(env):
    c = env["client"]
    rid = add_case(env, "j1", revealed=BLIND)
    # The client can't set the time, the reviewer or anything else.
    for extra in ({"created_at": "2020-01-01T00:00:00Z"}, {"reviewer_id": "reviewer-2"}):
        assert c.post(f"/v1/reviews/{rid}/pre-reveal", headers=REVIEWER, json={**PRE, **extra}).status_code == 422
    from datetime import datetime, timezone

    before = datetime.now(timezone.utc)
    assert c.post(f"/v1/reviews/{rid}/pre-reveal", headers=REVIEWER, json=PRE).status_code == 201
    s = env["Session"]()
    row = s.query(ReviewPreReveal).one()
    at = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    assert at >= before and row.reviewer_id == "reviewer-1" and row.case_severity == "HIGH"
    s.close()
    [(actor, action, _, details)] = _events(env, "review_pre_reveal")
    assert actor == "reviewer-1" and details["pre_reveal_id"] == row.id
    assert details["claims"]["c1"] == {"stance": "REFUTES", "verdict": "SUPPORTED"}
    # One per reviewer per case: it can't be redone after seeing the system's view.
    r = c.post(f"/v1/reviews/{rid}/pre-reveal", headers=REVIEWER, json=PRE)
    assert r.status_code == 409
    # After the decision both stay in the audit trail.
    c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=APPROVE)
    trail = c.get(f"/v1/reviews/{rid}", headers=ADMIN).json()["audit_trail"]
    assert [e["action"] for e in trail] == ["review_pre_reveal", "review_decision"]


@pytest.mark.parametrize("claims,status", [
    ([{"claim_id": "c1", "stance": "REFUTES", "verdict": "SUPPORTED"}], 422),            # c2 missing
    (PRE["claims"] + [{"claim_id": "c9", "stance": "REFUTES", "verdict": "SUPPORTED"}], 422),
    (PRE["claims"] + [PRE["claims"][0]], 422),                                          # twice
    ([{"claim_id": "c1", "stance": "MAYBE", "verdict": "SUPPORTED"}, PRE["claims"][1]], 422),
    ([{"claim_id": "c1", "stance": "REFUTES"}, PRE["claims"][1]], 422),                 # no verdict
    ([], 422),
])
def test_pre_reveal_needs_a_stance_and_verdict_for_every_claim(env, claims, status):
    rid = add_case(env, "j1", revealed=BLIND)
    r = env["client"].post(f"/v1/reviews/{rid}/pre-reveal", headers=REVIEWER, json={"claims": claims})
    assert r.status_code == status, r.text
    assert _events(env) == []


def test_pre_reveal_only_on_open_high_cases(env):
    c = env["client"]
    medium = add_case(env, "m", severity="MEDIUM", revealed=BLIND,
                      claims={"c1": {"severity": "MEDIUM", "basis": [], "stance": "ENDORSES",
                                     "verdict": "CONTRADICTED", "misinfo_relevant": True}})
    assert c.post(f"/v1/reviews/{medium}/pre-reveal", headers=REVIEWER,
                  json={"claims": [PRE["claims"][0]]}).status_code == 409
    done = add_case(env, "d", status="RESOLVED", revealed=BLIND)
    assert c.post(f"/v1/reviews/{done}/pre-reveal", headers=REVIEWER, json=PRE).status_code == 409
    # A resolved case is not blind: the decision has been made.
    assert c.get(f"/v1/reviews/{done}", headers=REVIEWER).json()["system_view_withheld"] is False


def test_pre_reveal_access_rules(env):
    c = env["client"]
    rid = add_case(env, "j1", revealed=BLIND)
    assert c.post(f"/v1/reviews/{rid}/pre-reveal", headers=ANALYST, json=PRE).status_code == 403
    assert c.post("/v1/reviews/missing/pre-reveal", headers=ANALYST, json=PRE).status_code == 403
    assert c.post("/v1/reviews/missing/pre-reveal", headers=REVIEWER, json=PRE).status_code == 404
    legacy = add_case(env, "legacy", owner=None, revealed=BLIND)  # T33: admins only
    assert c.post(f"/v1/reviews/{legacy}/pre-reveal", headers=REVIEWER, json=PRE).status_code == 404
    assert c.post(f"/v1/reviews/{legacy}/pre-reveal", headers=ADMIN, json=PRE).status_code == 201
    mine = add_case(env, "mine", owner="reviewer-1", revealed=BLIND)
    r = c.post(f"/v1/reviews/{mine}/pre-reveal", headers=REVIEWER, json=PRE)
    assert r.status_code == 403 and "own video" in r.json()["detail"]
    # Their own video isn't hidden from them (they already see their own results).
    assert c.get(f"/v1/reviews/{mine}", headers=REVIEWER).json()["system_view_withheld"] is False


# ------------------------------------------------------------------ (b) blind step: decisions


def test_decision_on_high_case_without_pre_reveal_is_rejected(env):
    c = env["client"]
    rid = add_case(env, "j1", revealed=BLIND)
    for body in (APPROVE, {"action": "REJECT", "reason": "not a health video", "reason_code": "OTHER"},
                 {"action": "REQUEST_REANALYSIS", "reason": "retrieval terms fixed", "reason_code": "MISSING_SOURCE"}):
        r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=body)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "PRE_REVEAL_REQUIRED"
    # Another reviewer's pre-reveal doesn't count for this one.
    assert c.post(f"/v1/reviews/{rid}/pre-reveal", headers=REVIEWER2, json=PRE).status_code == 201
    assert c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=APPROVE).status_code == 409
    s = env["Session"]()
    case = s.get(HumanReview, rid)
    assert case.status == ReviewCaseStatus.OPEN and case.reviewer_id is None
    s.close()
    assert env["dispatched"] == []
    assert [a for _, a, _, _ in _events(env)] == ["review_pre_reveal"]


def test_decision_after_pre_reveal_links_it_and_records_agreement(env):
    c = env["client"]
    rid = add_case(env, "j1", revealed=BLIND)
    c.post(f"/v1/reviews/{rid}/pre-reveal", headers=REVIEWER, json=PRE)
    r = c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json={
        "action": "CORRECT", "reason": "the speaker refutes the claim", "reason_code": "STANCE_MISREAD",
        "corrected_label": "DEBUNKING"})
    assert r.status_code == 200, r.text
    [(_, _, _, details)] = _events(env, "review_decision")
    s = env["Session"]()
    pre = s.query(ReviewPreReveal).one()
    s.close()
    assert details["pre_reveal_id"] == pre.id and details["pre_reveal_at"]
    assert details["pre_reveal_agreement"] == {"c1": {"stance": False, "verdict": False},
                                               "c2": {"stance": True, "verdict": True}}


def test_overriding_severity_down_does_not_skip_the_blind_step(env):
    c = env["client"]
    rid = add_case(env, "j1", revealed=BLIND)
    r = c.post(f"/v1/reviews/{rid}/claims/c1/severity", headers=REVIEWER,
               json={"severity": "LOW", "reason": "small audience"})
    assert r.status_code == 200 and r.json()["severity"] == "LOW"
    assert r.json()["system_view_withheld"] is True  # the override response is blind too
    _no_system_view(r.text)
    assert c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()["system_view_withheld"] is True
    assert c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=APPROVE).status_code == 409
    assert c.post(f"/v1/reviews/{rid}/pre-reveal", headers=REVIEWER, json=PRE).status_code == 201
    assert c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=APPROVE).status_code == 200


def test_overriding_severity_up_to_high_starts_the_blind_step(env):
    c = env["client"]
    claims = {"c1": {"severity": "MEDIUM", "basis": [], "stance": "ENDORSES", "verdict": "CONTRADICTED",
                     "misinfo_relevant": True}}
    rid = add_case(env, "j1", severity="MEDIUM", claims=claims, revealed=BLIND)
    assert c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()["system_view_withheld"] is False
    c.post(f"/v1/reviews/{rid}/claims/c1/severity", headers=REVIEWER2, json={"severity": "HIGH", "reason": "children"})
    assert c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()["system_view_withheld"] is True
    assert c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=APPROVE).status_code == 409


def test_cases_below_high_need_no_pre_reveal(env):
    c = env["client"]
    for sev in ("MEDIUM", "LOW", None):
        claims = {"c1": {"severity": sev or "LOW", "basis": [], "stance": "QUOTES", "verdict": "SUPPORTED",
                         "misinfo_relevant": sev is not None}}
        rid = add_case(env, f"j-{sev}", severity=sev, claims=claims, revealed=BLIND)
        case = c.get(f"/v1/reviews/{rid}", headers=REVIEWER).json()
        assert case["blind_step_required"] is False and case["proposed_label"] == "MISINFO"
        assert c.post(f"/v1/reviews/{rid}/decision", headers=REVIEWER, json=APPROVE).status_code == 200


# ------------------------------------------------------------------ (b) blind step: the queue


def test_queue_withholds_blind_items_and_the_reason_filter_cannot_probe_them(env):
    c = env["client"]
    add_case(env, "blind", revealed=BLIND, reasons=("weak_evidence:c1",))
    add_case(env, "seen", revealed=("reviewer-1",), reasons=("weak_evidence:c1",))
    items = {i["review_id"]: i for i in c.get("/v1/reviews", headers=REVIEWER).json()["items"]}
    assert items["rev-blind"]["system_view_withheld"] is True
    assert items["rev-blind"]["reasons"] == [] and items["rev-blind"]["rules_fired"] == []
    assert items["rev-blind"]["proposed_label"] is None and items["rev-blind"]["severity"] == "HIGH"
    assert items["rev-seen"]["system_view_withheld"] is False and items["rev-seen"]["proposed_label"] == "MISINFO"
    for reason in ("weak_evidence", "weak_evidence:c1"):
        r = c.get("/v1/reviews", headers=REVIEWER, params={"reason": reason}).json()
        assert [i["review_id"] for i in r["items"]] == ["rev-seen"] and r["total"] == 1
    # reviewer-2 has given neither.
    assert c.get("/v1/reviews", headers=REVIEWER2, params={"reason": "weak_evidence"}).json()["total"] == 0


# ------------------------------------------------------------------ (c) names and is_own


def _named(sub, role=None, name=None, email=None):
    extra = {}
    if email:
        extra["email"] = email
    if name:
        extra["user_metadata"] = {"full_name": name}
    claims_role = {"app_role": role} if role else {}
    return auth(token(sub, **claims_role, **extra))


def test_me_records_the_user_from_the_verified_token(env):
    c = env["client"]
    me = c.get("/v1/me", headers=_named("reviewer-1", "reviewer", "Rita Reviewer", "rita@example.org")).json()
    assert me["display_name"] == "Rita Reviewer" and me["email"] == "rita@example.org"
    # A later token without the claims doesn't erase them; a changed name updates the row.
    c.get("/v1/me", headers=REVIEWER)
    c.get("/v1/me", headers=_named("reviewer-1", "reviewer", "Rita R."))
    s = env["Session"]()
    row = s.get(User, "reviewer-1")
    assert (row.display_name, row.email) == ("Rita R.", "rita@example.org")
    assert not hasattr(row, "role")  # roles only ever come from the token
    s.close()


def test_names_on_queue_items_decisions_and_audit_trail(env):
    c = env["client"]
    c.get("/v1/me", headers=_named("submitter-1", None, None, "sam@example.org"))  # analyst, no display name
    rita = _named("reviewer-1", "reviewer", "Rita Reviewer", "rita@example.org")
    rid = add_case(env, "j1", severity="LOW")
    mine = add_case(env, "mine", severity="LOW", owner="reviewer-1")
    c.post(f"/v1/reviews/{rid}/decision", headers=rita, json=APPROVE)
    items = {i["review_id"]: i for i in c.get("/v1/reviews", headers=REVIEWER, params={"status": "ALL"}).json()["items"]}
    item = items[rid]
    assert item["submitted_by"] == "submitter-1"
    assert item["submitted_by_name"] == "sam@example.org"  # no display name: the email
    assert item["submitted_by_email"] == "sam@example.org"
    assert item["is_own"] is False and items[mine]["is_own"] is True
    assert item["decision"]["reviewer_name"] == "Rita Reviewer"
    assert item["decision"]["reviewer_email"] == "rita@example.org"
    trail = c.get(f"/v1/reviews/{rid}", headers=ADMIN).json()["audit_trail"]
    assert (trail[-1]["actor_name"], trail[-1]["actor_email"]) == ("Rita Reviewer", "rita@example.org")
    assert items[mine]["submitted_by_name"] == "Rita Reviewer"
    # A user the API has never seen has no name, only the id.
    ghost = add_case(env, "ghost", severity="LOW", owner="ghost-1")
    item = c.get(f"/v1/reviews/{ghost}", headers=REVIEWER).json()
    assert item["submitted_by"] == "ghost-1" and item["submitted_by_name"] is item["submitted_by_email"] is None


def test_an_analyst_never_sees_another_users_email(env):
    """The review-request route (T32) is open to the job's owner: it shows who asked,
    by display name only."""
    from datetime import datetime, timezone

    c = env["client"]
    c.get("/v1/me", headers=_named("reviewer-1", "reviewer", None, "rita@example.org"))   # no display name
    c.get("/v1/me", headers=_named("reviewer-2", "reviewer", "Rex", "rex@example.org"))
    owner = _named("submitter-1", None, "Sam", "sam@example.org")
    for job, who in (("j1", "reviewer-1"), ("j2", "reviewer-2"), ("j3", "submitter-1")):
        add_case(env, job, severity="LOW")
        s = env["Session"]()
        s.add(AuditEvent(actor_id=who, action="review_requested", entity_type="human_review",
                         entity_id=f"rev-{job}", job_id=job, reason="please check this",
                         details={}, created_at=datetime.now(timezone.utc)))
        s.commit()
        s.close()

    def request(job, headers):
        r = c.post(f"/v1/jobs/{job}/review-request", headers=headers, json={"note": "again please"})
        assert r.status_code == 200, r.text
        return r.json()["request"]

    req = request("j1", owner)
    assert req["requested_by"] == "reviewer-1" and req["requested_by_name"] is None
    assert req["requested_by_email"] is None and "rita@example.org" not in str(req)
    req = request("j2", owner)
    assert req["requested_by_name"] == "Rex" and req["requested_by_email"] is None
    req = request("j3", owner)  # their own: they may see their own email
    assert req["requested_by_name"] == "Sam" and req["requested_by_email"] == "sam@example.org"
    # A reviewer sees the email.
    assert request("j1", REVIEWER2)["requested_by_email"] == "rita@example.org"


def test_remember_never_fails_the_request():
    from app.services import users_service

    class Broken:
        def get(self, *a):
            raise RuntimeError("db down")

        def rollback(self):
            self.rolled_back = True

    db = Broken()
    users_service.remember(db, {"sub": "x", "email": "x@example.org"})
    assert db.rolled_back
    users_service.remember(db, {})  # no subject: nothing to do


def test_display_name_is_cleaned():
    from app.services.users_service import profile_from_token

    email, name = profile_from_token({"email": "a@b.c", "user_metadata": {"full_name": "  Dr\n Who \t" + "x" * 300}})
    assert email == "a@b.c" and name.startswith("Dr Who x") and len(name) == 200
    assert profile_from_token({"user_metadata": {"name": 7}}) == (None, None)


# ------------------------------------------------------------------ migration


def test_migration_0016_upgrades_and_downgrades(monkeypatch, tmp_path):
    from alembic import command
    from alembic.script import ScriptDirectory

    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = t33._alembic(url, monkeypatch)
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    insp = inspect(engine)
    assert "reason_code" in {c["name"] for c in insp.get_columns("human_reviews")}
    assert {"id", "review_id", "reviewer_id", "claims", "note", "case_severity", "created_at"} == {
        c["name"] for c in insp.get_columns("review_pre_reveals")}
    assert {"id", "email", "display_name", "created_at", "updated_at"} == {c["name"] for c in insp.get_columns("users")}
    command.downgrade(cfg, "0015")
    insp = inspect(engine)
    assert "users" not in insp.get_table_names() and "review_pre_reveals" not in insp.get_table_names()
    assert "reason_code" not in {c["name"] for c in insp.get_columns("human_reviews")}
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    engine.dispose()
