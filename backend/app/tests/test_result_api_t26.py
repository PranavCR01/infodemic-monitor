"""T26: result API fields for the frontend (target design §12, §17).

Covers: the new fields on ``GET /jobs/{id}/result`` and the §17 ``/v1`` reads, that
the existing fields keep their shape, that ``review`` stays set once a case is resolved,
structured reasons from one mapping table, and auth + per-user ownership on every
endpoint. Database is in-memory SQLite; no model, network or storage calls.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers import jobs as jobs_router
from app.api.routers import results as results_router
from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.db.base import Base
from app.db.models.claim import (
    ClaimEvidenceRow,
    ClaimRow,
    ClaimStanceRow,
    CriticReviewRow,
    EvidenceRecordRow,
    OcrSegmentRow,
    TranscriptSegmentRow,
    VerificationResultRow,
)
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.models.review import HumanReview, ReviewCaseStatus
from app.db.models.video import Video
from app.db.session import get_db
from app.services.review_reasons import REASON_TEXT, parse_reason

BACKEND = Path(__file__).resolve().parents[2]
ALICE = {"sub": "alice"}
BOB = {"sub": "bob"}
LONG_ABSTRACT = ("Background: hot water and influenza. " * 30).strip()
REASONS = [
    "weak_evidence:c2",
    "judge:possible_debunk:c1",
    "judge:mixed_video",
    "validation_failed:quotes:c1",
    "prompt_injection_suspected:transcript:t1",
    "guardrail:verify_claims:fabricated_citation:c2",
    "low_confidence",
]

# The fields the current frontend reads (frontend/app/jobs/[job_id]/JobDetailClient.tsx).
LEGACY_RESULT_KEYS = {"job_id", "filename", "label", "confidence", "explanation", "evidence_snippets",
                      "citations", "provider", "model_used", "latency_ms", "submitted_at", "created_at",
                      "pipeline", "fallback_reason", "review", "claims"}
LEGACY_CLAIM_KEYS = {"claim_id", "text", "category", "start_seconds", "end_seconds", "label", "deciding",
                     "stance", "verdict", "verdict_explanation", "limitations", "evidence"}
LEGACY_EVIDENCE_KEYS = {"evidence_id", "title", "pmid", "url", "study_type", "relation"}


# ------------------------------------------------------------------ fixtures


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    import app.db.models  # noqa: F401

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_graph_job(db, *, job_id="job-a", status=JobStatus.REVIEW_REQUIRED, review=True):
    if db.get(Video, "vid-1") is None:
        db.add(Video(id="vid-1", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1))
    db.add(Job(id=job_id, video_id="vid-1", status=status,
               created_at=datetime(2026, 11, 20, tzinfo=timezone.utc)))
    db.add(Result(job_id=job_id, label="MISINFO", confidence=0.8, explanation="because", evidence_snippets=["q"],
                  combined_content="", provider="langgraph", model_used="graph", latency_ms=5,
                  pipeline="graph", pipeline_version="graph_v1", decision_rule="endorsed_contradicted",
                  deciding_claim_ids=["c1"]))
    db.add_all([
        TranscriptSegmentRow(job_id=job_id, segment_id="t1", start_seconds=3.5, end_seconds=8.0,
                             text="Hot water cures the flu."),
        TranscriptSegmentRow(job_id=job_id, segment_id="t2", start_seconds=8.5, end_seconds=12.0,
                             text="Garlic stops colds, they say."),
        OcrSegmentRow(job_id=job_id, segment_id="o1", start_seconds=4.0, end_seconds=7.0,
                      text="HOT WATER = NO FLU", confidence=0.93),
    ])
    pub = EvidenceRecordRow(job_id=job_id, evidence_id="pmid_1", source="pubmed", pmid="1", doi="10.1/x",
                            title="Trial of hot water", abstract=LONG_ABSTRACT, publication_type=["RCT"],
                            publication_year=2019, source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
                            study_type="rct", publisher=None)
    ref = EvidenceRecordRow(job_id=job_id, evidence_id="ref_abc", source="reference", title="CDC flu page",
                            abstract="Influenza is a virus.", publication_type=[], publication_year=2024,
                            source_url="https://www.cdc.gov/flu", publisher="CDC",
                            retrieved_at="2026-11-23T00:00:00Z", snapshot_sha256="a" * 64)
    lib = EvidenceRecordRow(job_id=job_id, evidence_id="lib_9", source="library", title="Lab book chapter",
                            abstract="", publication_type=[], publication_year=None)
    c1 = ClaimRow(job_id=job_id, claim_id="c1", text="Hot water cures the flu.", category="treatment_efficacy",
                  start_seconds=3.5, end_seconds=8.0, source_segment_ids=["t1", "o1"], claim_kind="research_question",
                  label="MISINFO", deciding=True)
    c1.stance = ClaimStanceRow(stance="ENDORSES", segment_ids=["t1"], rationale="Speaker asserts it as fact.")
    c1.verification = VerificationResultRow(verdict="CONTRADICTED", explanation="RCT found no effect.",
                                            limitations=["small trial"], retrieval_attempts=1)
    c1.critic = CriticReviewRow(decision="APPROVE", issues=["quote is short"], checks=["code:quotes"],
                                requires_review=False)
    c1.evidence_links = [
        ClaimEvidenceRow(evidence=pub, relation="CONTRADICTS", relevance_score=0.9, rank=1),
        ClaimEvidenceRow(evidence=ref, relation="SUPPORTS", relevance_score=0.7, rank=2),
        ClaimEvidenceRow(evidence=lib, relation="CONSIDERED", relevance_score=0.1, rank=3),
    ]
    c2 = ClaimRow(job_id=job_id, claim_id="c2", text="Hot water means no flu.", category="prevention",
                  start_seconds=4.0, end_seconds=7.0, source_segment_ids=["o1"], label=None, deciding=False)
    c2.stance = ClaimStanceRow(stance="UNCLEAR", segment_ids=["o1", "missing"], rationale="")
    db.add_all([pub, ref, lib, c1, c2])
    if review:
        db.add(HumanReview(
            job_id=job_id, status=ReviewCaseStatus.OPEN, reasons=REASONS,
            rules_fired=[{"rule": "weak_evidence", "reasons": ["weak_evidence:c2"]}],
            proposed_label="MISINFO", policy_version="review_v1", severity="HIGH", severity_table_version="sev_v1",
            claim_severities={
                "c1": {"severity": "HIGH", "basis": ["category:treatment_efficacy"], "stance": "ENDORSES",
                       "verdict": "CONTRADICTED", "misinfo_relevant": True},
                "c2": {"severity": "LOW", "basis": ["default"], "stance": "UNCLEAR", "verdict": None,
                       "misinfo_relevant": False,
                       "override": {"severity": "MEDIUM", "reason": "children", "reviewer_id": "rev-7",
                                    "at": "2026-11-23T00:00:00+00:00"}},
            },
        ))
    db.commit()


@pytest.fixture()
def env(monkeypatch):
    db = _session()
    _seed_graph_job(db)
    app = FastAPI()
    app.include_router(jobs_router.router)
    app.include_router(results_router.router)
    state = {"user": ALICE}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    def as_user(user):
        state["user"] = user
        return client

    return {"db": db, "client": client, "as_user": as_user, "app": app}


def _claim_pk(db, claim_id="c1", job_id="job-a"):
    return db.query(ClaimRow).filter_by(job_id=job_id, claim_id=claim_id).one().id


# ------------------------------------------------------------------ fields


def test_legacy_result_keeps_its_fields_and_adds_t26(env):
    out = env["client"].get("/jobs/job-a/result").json()
    assert LEGACY_RESULT_KEYS <= set(out)
    assert out["label"] == "MISINFO" and out["filename"] == "v.mp4"
    assert out["review"]["status"] == "REVIEW_REQUIRED" and out["review"]["reasons"] == REASONS
    for c in out["claims"]:
        assert LEGACY_CLAIM_KEYS <= set(c)
        for e in c["evidence"]:
            assert LEGACY_EVIDENCE_KEYS <= set(e)
    # T26 additions at the top level
    assert out["video_id"] == "vid-1" and out["status"] == "REVIEW_REQUIRED"
    assert out["decision_rule"] == "endorsed_contradicted" and out["deciding_claim_ids"] == ["c1"]
    assert out["pipeline_version"] == "graph_v1"
    assert [s["segment_id"] for s in out["transcript_segments"]] == ["t1", "t2"]
    assert out["transcript_segments"][0] == {"segment_id": "t1", "source": "speech", "start_seconds": 3.5,
                                             "end_seconds": 8.0, "text": "Hot water cures the flu.",
                                             "confidence": None}
    assert out["ocr_segments"] == [{"segment_id": "o1", "source": "screen", "start_seconds": 4.0,
                                    "end_seconds": 7.0, "text": "HOT WATER = NO FLU", "confidence": 0.93}]


def test_claim_fields_stance_modality_critic_severity(env):
    claims = {c["claim_id"]: c for c in env["client"].get("/jobs/job-a/result").json()["claims"]}
    c1, c2 = claims["c1"], claims["c2"]
    assert c1["id"] == _claim_pk(env["db"])
    assert c1["source_segment_ids"] == ["t1", "o1"] and c1["modality"] == "both"
    assert c2["source_segment_ids"] == ["o1"] and c2["modality"] == "screen"
    assert c1["stance_rationale"] == "Speaker asserts it as fact."
    assert c1["stance_segment_ids"] == ["t1"]
    assert c1["stance_quotes"] == [{"segment_id": "t1", "source": "speech", "start_seconds": 3.5,
                                    "end_seconds": 8.0, "text": "Hot water cures the flu.", "confidence": None}]
    # an id that isn't stored is listed but has no quote
    assert c2["stance_segment_ids"] == ["o1", "missing"] and [q["segment_id"] for q in c2["stance_quotes"]] == ["o1"]
    assert c1["critic"] == {"decision": "APPROVE", "issues": ["quote is short"], "requires_review": False}
    assert c2["critic"] is None
    assert c1["claim_kind"] == "research_question" and c1["retrieval_attempts"] == 1
    assert c1["severity"]["severity"] == "HIGH" and c1["severity"]["misinfo_relevant"] is True
    # effective severity is the reviewer's override; who overrode it is not exposed
    assert c2["severity"]["severity"] == "MEDIUM" and c2["severity"]["table_severity"] == "LOW"
    assert c2["severity"]["override"] == {"severity": "MEDIUM", "reason": "children",
                                          "at": "2026-11-23T00:00:00+00:00"}


def test_evidence_fields_and_cited_only_on_claims(env):
    c1 = next(c for c in env["client"].get("/jobs/job-a/result").json()["claims"] if c["claim_id"] == "c1")
    ev = {e["evidence_id"]: e for e in c1["evidence"]}
    assert set(ev) == {"pmid_1", "ref_abc"}  # CONSIDERED papers aren't in the claim view (unchanged)
    pub, ref = ev["pmid_1"], ev["ref_abc"]
    assert pub["source_kind"] == "pubmed" and pub["year"] == 2019 and pub["doi"] == "10.1/x"
    assert pub["relation"] == "CONTRADICTS" and pub["publication_type"] == ["RCT"] and pub["rank"] == 1
    assert pub["abstract_snippet"].endswith("…") and len(pub["abstract_snippet"]) <= 301
    assert LONG_ABSTRACT.startswith(pub["abstract_snippet"][:-1])
    assert ref["source_kind"] == "reference" and ref["publisher"] == "CDC"
    assert ref["abstract_snippet"] == "Influenza is a virus." and ref["snapshot_sha256"] == "a" * 64


def test_claim_evidence_endpoint_lists_every_paper(env):
    pk = _claim_pk(env["db"])
    out = env["client"].get(f"/v1/claims/{pk}/evidence").json()
    assert out["claim_id"] == "c1" and out["id"] == pk and out["job_id"] == "job-a"
    assert [(e["evidence_id"], e["source_kind"], e["relation"]) for e in out["evidence"]] == [
        ("pmid_1", "pubmed", "CONTRADICTS"), ("ref_abc", "reference", "SUPPORTS"), ("lib_9", "library", "CONSIDERED")]


def test_review_details_and_structured_reasons(env):
    review = env["client"].get("/jobs/job-a/result").json()["review"]
    assert review["review_id"] == env["db"].query(HumanReview).one().id
    assert review["case_status"] == "OPEN" and review["resolved"] is False and review["action"] is None
    assert review["severity"] == "HIGH" and review["severity_table_version"] == "sev_v1"
    assert {c["claim_id"]: c["severity"] for c in review["claim_severities"]} == {"c1": "HIGH", "c2": "MEDIUM"}
    assert review["rules_fired"][0]["rule"] == "weak_evidence"
    details = review["reason_details"]
    assert [d["raw"] for d in details] == REASONS
    assert all(d["text"] for d in details)
    assert details[0] == {"code": "weak_evidence", "rule": "weak_evidence", "claim_id": "c2", "detail": None,
                          "text": REASON_TEXT["weak_evidence"].format(claim="claim c2"), "raw": "weak_evidence:c2"}


def test_v1_video_results_and_claims(env):
    client = env["client"]
    out = client.get("/v1/videos/vid-1/results").json()
    assert out["job_id"] == "job-a" and out["review"]["status"] == "REVIEW_REQUIRED"
    assert out == client.get("/jobs/job-a/result").json()
    claims = client.get("/v1/videos/vid-1/claims").json()
    assert claims["job_id"] == "job-a" and claims["video_id"] == "vid-1"
    assert [c["claim_id"] for c in claims["claims"]] == ["c1", "c2"]
    assert claims["claims"] == out["claims"]


def test_v1_video_results_uses_the_latest_owned_job(env):
    db = env["db"]
    db.add(Job(id="job-new", video_id="vid-1", status=JobStatus.PENDING,
               created_at=datetime(2026, 11, 22, tzinfo=timezone.utc)))
    db.commit()
    r = env["client"].get("/v1/videos/vid-1/results")
    assert r.status_code == 202
    db.get(Job, "job-new").status = JobStatus.FAILED
    db.get(Job, "job-new").error_code = "PIPELINE_ERROR"
    db.commit()
    r = env["client"].get("/v1/videos/vid-1/results")
    assert r.status_code == 409 and r.json()["detail"]["error_code"] == "PIPELINE_ERROR"


def test_single_call_result_has_empty_t26_fields():
    db = _session()
    db.add(Video(id="vid-s", filename="s.mp4", file_path="/tmp/s.mp4", file_size=1))
    db.add(Job(id="job-s", video_id="vid-s", status=JobStatus.SUCCESS))
    db.add(Result(job_id="job-s", label="NO_MISINFO", confidence=0.9, explanation="x", evidence_snippets=[],
                  combined_content="", provider="openai", model_used="m", latency_ms=1))
    db.commit()
    out = jobs_router.get_result("job-s", db=db, current_user=ALICE)
    assert out["review"] is None and out["claims"] == [] and out["pipeline"] is None
    assert out["transcript_segments"] == [] and out["ocr_segments"] == [] and out["deciding_claim_ids"] == []
    json.dumps(out, default=str)


# ------------------------------------------------------------------ resolved review


@pytest.mark.parametrize("action,kwargs,status,path", [
    ("APPROVE", {}, "VERIFIED", "/jobs/job-a/result"),
    ("CORRECT", {"corrected_label": "DEBUNKING"}, "CORRECTED", "/jobs/job-a/result"),
    ("MARK_INSUFFICIENT", {}, "CORRECTED", "/jobs/job-a/result"),
    ("REQUEST_REANALYSIS", {}, "REANALYSIS_REQUESTED", "/jobs/job-a/result"),
    # a rejected job is FAILED; the legacy route answers 202 for it, as before, and the
    # §17 route still shows the result and why
    ("REJECT", {}, "REJECTED", "/v1/videos/vid-1/results"),
])
def test_review_is_not_null_once_resolved(env, action, kwargs, status, path):
    from app.services.review_service import record_review_decision

    db = env["db"]
    case = db.query(HumanReview).one()
    record_review_decision(db, case.id, reviewer_id="rev-1", action=action, reason="checked", **kwargs)
    out = env["client"].get(path).json()
    review = out["review"]
    assert review is not None
    assert review["status"] == status and review["case_status"] == "RESOLVED" and review["resolved"] is True
    assert review["action"] == action and review["decision_reason"] == "checked"
    assert review["decided_at"] is not None and review["reasons"] == REASONS
    if action == "CORRECT":
        assert review["corrected_label"] == "DEBUNKING" and out["label"] == "DEBUNKING"
        assert review["proposed_label"] == "MISINFO"


def test_current_frontend_banner_only_for_open_cases():
    """The current result page showed "awaiting human review" whenever ``review`` was
    set; with ``review`` kept after resolution it must check the status."""
    src = (BACKEND.parent / "frontend" / "app" / "jobs" / "[job_id]" / "JobDetailClient.tsx").read_text()
    assert 'result.review?.status === "REVIEW_REQUIRED"' in src


# ------------------------------------------------------------------ reasons table


@pytest.mark.parametrize("raw,code,rule,claim_id,detail", [
    ("weak_evidence:c2", "weak_evidence", "weak_evidence", "c2", None),
    ("conflicting_evidence:c1", "conflicting_evidence", "conflicting_evidence", "c1", None),
    ("weak_study_types:c3", "weak_study_types", "weak_study_types", "c3", None),
    ("unclear_stance:c1", "unclear_stance", "unclear_stance", "c1", None),
    ("critic_escalated:c4", "critic_escalated", "critic_escalated", "c4", None),
    ("budget_exhausted:c4", "budget_exhausted", "budget_exhausted", "c4", None),
    ("high_risk_uncertain:c2", "high_risk_uncertain", "high_risk_uncertain", "c2", None),
    ("low_confidence", "low_confidence", "low_confidence", None, None),
    ("validation_failed:quotes:c1", "validation_failed", "validation_failed", "c1", "quotes"),
    ("validation_failed:source_ids", "validation_failed", "validation_failed", None, "source ids"),
    ("judge:mixed_video", "mixed_video", "judge_flags", None, None),
    ("judge:possible_debunk:c1", "possible_debunk", "judge_flags", "c1", None),
    ("judge:denies_supported:c3", "denies_supported", "judge_flags", "c3", None),
    ("prompt_injection_suspected:transcript:t1", "prompt_injection_suspected", "guardrails", None, "transcript"),
    ("guardrail:verify_claims:fabricated_citation:c2", "guardrail", "guardrails", "c2",
     "verify claims fabricated citation"),
])
def test_parse_reason(raw, code, rule, claim_id, detail):
    r = parse_reason(raw)
    assert (r.code, r.rule, r.claim_id, r.detail, r.raw) == (code, rule, claim_id, detail, raw)
    assert r.text and "{" not in r.text and not r.text.startswith("Flagged")
    if claim_id:
        assert f"claim {claim_id}" in r.text.lower()


def test_unknown_reason_gets_generic_text():
    r = parse_reason("brand_new_rule:c9")
    assert r.code == "brand_new_rule" and r.rule == "other" and r.text == "Flagged for review by rule 'brand_new_rule'."


def test_every_rule_and_judge_flag_has_plain_text():
    from app.core.graph import judge
    from app.core.graph.review_policy import REVIEW_RULES

    codes = (set(REVIEW_RULES) - {"judge_flags", "guardrails"}) | {
        getattr(judge, n) for n in dir(judge) if n.startswith("FLAG_")} | {"guardrail", "prompt_injection_suspected"}
    assert codes <= set(REASON_TEXT), codes - set(REASON_TEXT)


# ------------------------------------------------------------------ ownership and auth


def _endpoints(db):
    pk = _claim_pk(db)
    return ["/jobs/job-a", "/jobs/job-a/result", "/v1/videos/vid-1/results", "/v1/videos/vid-1/claims",
            f"/v1/claims/{pk}/evidence"]


def test_every_endpoint_goes_through_the_access_check(env, monkeypatch):
    """The owner column is T27's; T26 routes every read through ``app.api.ownership``.
    With a rule plugged in (only alice may see), each endpoint answers 404 to bob."""
    from sqlalchemy import false

    from app.api import ownership

    monkeypatch.setattr(ownership, "can_view_job", lambda job, user: (user or {}).get("sub") == "alice")
    monkeypatch.setattr(ownership, "visible_jobs",
                        lambda q, user: q if (user or {}).get("sub") == "alice" else q.filter(false()))
    for path in _endpoints(env["db"]):
        assert env["as_user"](ALICE).get(path).status_code == 200, path
        r = env["as_user"](BOB).get(path)
        assert r.status_code == 404, path
        assert "alice" not in r.text and "Hot water" not in r.text
    assert env["as_user"](ALICE).get("/v1/claims/no-such-claim/evidence").status_code == 404
    assert env["as_user"](ALICE).get("/v1/videos/no-such-video/results").status_code == 404
    assert env["as_user"](ALICE).get("/jobs/no-such-job/result").status_code == 404


def test_access_check_today_allows_authenticated_callers(env):
    """Until T27 adds owners, an authenticated caller sees existing objects (as before)."""
    for path in _endpoints(env["db"]):
        assert env["as_user"](BOB).get(path).status_code == 200, path


def test_every_endpoint_needs_auth(env, monkeypatch):
    app = env["app"]
    app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    client = TestClient(app)
    for path in _endpoints(env["db"]):
        assert client.get(path).status_code == 401, path


def test_openapi_documents_typed_models(env):
    schema = env["client"].get("/openapi.json").json()
    names = set(schema["components"]["schemas"])
    assert {"JobResultResponse", "ClaimView", "EvidenceView", "ReviewView", "ReasonView",
            "ClaimsResponse", "ClaimEvidenceResponse", "SegmentView"} <= names


# ------------------------------------------------------------------ end to end and migration


def test_persisted_graph_outcome_serves_quotes_and_modality():
    """Through the real persist path with the mocked graph (no model or network)."""
    from app.services.pipeline_result_service import persist_outcome
    from app.tests.test_graph_integration import fusion, make_provider

    db = _session()
    db.add(Video(id="vid-1", filename="v.mp4", file_path="/tmp/v.mp4", file_size=1))
    db.add(Job(id="job-1", video_id="vid-1", status=JobStatus.STARTED))
    db.commit()
    outcome = make_provider().run(fusion(), job_id="job-1", video_id="vid-1")
    outcome.state = {**outcome.state, "requires_human_review": True, "review_reasons": ["judge:mixed_video"]}
    persist_outcome(db, "job-1", fusion(), outcome)
    out = jobs_router.get_result("job-1", db=db, current_user=ALICE)
    assert out["transcript_segments"] and all(s["source"] == "speech" for s in out["transcript_segments"])
    for c in out["claims"]:
        assert c["modality"] == "speech" and c["source_segment_ids"]
        assert c["stance_quotes"] and all(q["text"] for q in c["stance_quotes"])
        assert all(e["source_kind"] == "pubmed" for e in c["evidence"])
    assert out["review"]["reason_details"][0]["code"] == "mixed_video"
    assert out["review"]["severity"] is not None
