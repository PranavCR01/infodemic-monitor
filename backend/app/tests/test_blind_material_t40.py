"""Blind-step material for HIGH review cases (T40; D7 Q1; design §12, §15, §17).

``GET /v1/reviews/{review_id}/blind-material`` gives a reviewer who is blind on an open
HIGH case the claims, transcript / on-screen text and retrieved papers, with nothing of
what the system concluded. Checked here:

- access: only a reviewer/admin who is blind on the case (analysts 403 before lookup;
  not-yours 404 as in T33; non-blind callers 403 ``BLIND_STEP_NOT_ACTIVE``);
- shape: the fields asked for, library documents by title only;
- no leak: two cases identical except for verdicts, stances, relations, labels,
  deciding/cited markers, critic notes, confidence and reasons give byte-identical
  responses, and no forbidden key or value appears.

Real HS256 tokens through the real ``get_current_user``; SQLite (and Postgres in CI via
test_ownership_t33's fixture). No network, no models.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
from app.tests import test_ownership_t33 as t33
from app.tests.test_ownership_t33 import env, pg_engine  # noqa: F401  (fixtures)

RHEA = t33.auth("rhea", "reviewer")      # reviewer, no pre-reveal anywhere: blind
ADA = t33.auth("ada", "admin")           # admin, no pre-reveal anywhere: blind
PATH = "/v1/reviews/{}/blind-material"

FORBIDDEN_KEYS = {
    "relation", "verdict", "stance", "label", "deciding", "cited", "critic", "issues",
    "confidence_score", "raw_confidence", "relevance_score", "reasons", "rules_fired",
    "search_trail", "severity", "explanation", "limitations", "rationale", "proposed_label",
    "misinfo_relevant", "stance_segment_ids", "decision",
}
FORBIDDEN_VALUES = ("SUPPORTS", "CONTRADICTS", "CONSIDERED", "CONTRADICTED", "SUPPORTED",
                    "ENDORSES", "REFUTES", "MISINFO", "INSUFFICIENT", "judge:", "critic")


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _assert_no_system_view(body: dict, text: str) -> None:
    leaked = FORBIDDEN_KEYS & set(_keys(body))
    assert not leaked, leaked
    for word in FORBIDDEN_VALUES:
        assert word not in text, word


# ------------------------------------------------------------------ material


def _add_material(s, job_id: str, claim_pk: str, *, variant: str, library: bool = True,
                  trail: bool = True) -> None:
    """Segments, a second claim and papers for ``job_id``. ``variant`` "a" / "b" set
    everything the system concluded differently; what retrieval found is the same,
    except that "a" also stores a cited paper the reranker did not keep (rank 4)."""
    a = variant == "a"
    s.add_all([
        TranscriptSegmentRow(job_id=job_id, segment_id="t1", start_seconds=0.0, end_seconds=2.5,
                             text="Drink hot water every hour."),
        TranscriptSegmentRow(job_id=job_id, segment_id="t2", start_seconds=2.5, end_seconds=5.0,
                             text="It kills the flu virus."),
        OcrSegmentRow(job_id=job_id, segment_id="o1", start_seconds=1.0, end_seconds=4.0,
                      text="FLU GONE IN 24H", confidence=0.91),
    ])
    claim = s.get(ClaimRow, claim_pk)
    claim.source_segment_ids = ["t1", "t2", "o1"]
    claim.label = "MISINFO" if a else "NOT_MISINFO"
    claim.deciding = a
    claim.stance.stance = "ENDORSES" if a else "REFUTES"
    claim.stance.segment_ids = ["t2"] if a else ["t1"]
    claim.stance.rationale = "says it cures" if a else "debunks it"
    claim.verification.verdict = "CONTRADICTED" if a else "SUPPORTED"
    claim.verification.explanation = "trials show no effect" if a else "fine"
    claim.verification.raw_confidence = 0.93 if a else 0.41
    claim.critic = CriticReviewRow(decision="ACCEPT" if a else "REVISE", issues=["x"] if a else [],
                                   checks=[], requires_review=not a)
    claim.search_trail = ({"version": 1, "recorded": "graph", "pubmed_queries": [], "references": [],
                           "library": None, "counts": {"retrieved": 9, "screened": 5, "kept": 3 if library else 2},
                           "budget": {"rounds_used": 1, "rounds_max": 3, "exhausted": False,
                                      "evidence_cap": 8}} if trail else None)

    papers = [
        dict(evidence_id="pmid:111", source="pubmed", pmid="111", doi="10.1/a", title="Hydration and influenza",
             abstract="A randomised trial of fluid intake in adults with influenza. " * 12,
             publication_type=["Randomized Controlled Trial"], publication_year=2019,
             source_url="https://pubmed.ncbi.nlm.nih.gov/111/", study_type="rct"),
        dict(evidence_id="ref:who-flu", source="reference", title="Influenza (seasonal) fact sheet",
             abstract="Most people recover within a week without medical care.", publication_type=[],
             publication_year=2023, source_url="https://www.who.int/flu", publisher="WHO",
             study_type="guideline", retrieved_at="2026-11-01T00:00:00Z", snapshot_sha256="f" * 64),
        dict(evidence_id="lib:doc7:p3", source="library", title="Clinical virology handbook",
             abstract="Passage text from the library that must not be shown.", publication_type=[],
             publication_year=2015, source_url="library://doc7", publisher="Lib Press", study_type="review"),
        dict(evidence_id="pmid:999", source="pubmed", pmid="999", title="Cited but not reranked",
             abstract="x", publication_type=[], publication_year=2001),
    ]
    if not library:
        papers.pop(2)
    rows = []
    for p in papers:
        row = EvidenceRecordRow(job_id=job_id, quality_score=0.9 if a else 0.2, **p)
        s.add(row)
        rows.append(row)
    s.flush()
    # Relations differ between the variants, and so would an order by relation.
    rel_a = ["CONSIDERED", "CONTRADICTS", "SUPPORTS"]
    rel_b = ["SUPPORTS", "CONSIDERED", "CONTRADICTS"]
    kept = rows[:3] if library else rows[:2]
    for rank, (ev, rel) in enumerate(zip(kept, rel_a if a else rel_b), start=1):
        s.add(ClaimEvidenceRow(claim_pk=claim_pk, evidence_pk=ev.id, relation=rel,
                               relevance_score=(0.9 - rank / 10) if a else 0.1 * rank, rank=rank))
    if a:  # cited outside the reranked set: stored only because the verifier cited it
        s.add(ClaimEvidenceRow(claim_pk=claim_pk, evidence_pk=rows[-1].id, relation="SUPPORTS",
                               relevance_score=0.05, rank=len(kept) + 1))
    # A second claim, earlier in the video, with no papers.
    c2 = ClaimRow(id=f"{claim_pk}-2", job_id=job_id, claim_id="c0", text="Flu is caused by a virus.",
                  category="disease_cause", start_seconds=0.0, end_seconds=0.5,
                  source_segment_ids=["t1"], label="NOT_MISINFO" if a else "MISINFO", deciding=not a)
    c2.stance = ClaimStanceRow(stance="ENDORSES" if a else "NEUTRAL", segment_ids=[], rationale="")
    c2.verification = VerificationResultRow(verdict="SUPPORTED" if a else "CONTRADICTED", explanation="",
                                            limitations=[], retrieval_attempts=1)
    s.add(c2)


def _decorate_case(s, review_id: str, *, variant: str) -> None:
    a = variant == "a"
    case = s.get(HumanReview, review_id)
    case.reasons = ["judge:mixed_video"] if a else ["critic:requires_review:c1", "low_confidence"]
    case.rules_fired = [{"rule": "judge"}] if a else [{"rule": "critic"}, {"rule": "confidence"}]
    case.proposed_label = "MISINFO" if a else "NOT_MISINFO"
    case.proposed_result = {"classification": case.proposed_label, "confidence": 0.9 if a else 0.3}
    case.claim_severities = {
        "c1": {"severity": "HIGH", "basis": ["treatment"], "stance": "ENDORSES" if a else "REFUTES",
               "verdict": "CONTRADICTED" if a else "SUPPORTED", "misinfo_relevant": a},
        "c0": {"severity": "LOW", "basis": [], "stance": "ENDORSES" if a else "NEUTRAL",
               "verdict": "SUPPORTED" if a else "CONTRADICTED", "misinfo_relevant": not a},
    }


def _seed_alice(Session, variant="a", **kw):
    s = Session()
    _add_material(s, "job-alice", "claim-alice", variant=variant, **kw)
    _decorate_case(s, "rev-alice", variant=variant)
    s.commit()
    s.close()


# ------------------------------------------------------------------ access


def test_blind_reviewer_gets_the_material(env):
    _seed_alice(env["Session"])
    r = env["client"].get(PATH.format("rev-alice"), headers=RHEA)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["review_id"] == "rev-alice" and body["job_id"] == "job-alice" and body["video_id"] == "vid-alice"
    assert [c["claim_id"] for c in body["claims"]] == ["c0", "c1"]  # by start time
    c1 = body["claims"][1]
    assert c1 == {**c1, "text": "Hot water cures flu.", "category": "treatment_efficacy",
                  "start_seconds": 0.0, "end_seconds": 1.0, "source_segment_ids": ["t1", "t2", "o1"]}
    assert [s["segment_id"] for s in body["transcript_segments"]] == ["t1", "t2"]
    assert body["transcript_segments"][0] == {"segment_id": "t1", "source": "speech", "start_seconds": 0.0,
                                              "end_seconds": 2.5, "text": "Drink hot water every hour.",
                                              "confidence": None}
    assert body["ocr_segments"][0]["text"] == "FLU GONE IN 24H" and body["ocr_segments"][0]["start_seconds"] == 1.0
    refs = c1["references"]
    # Retrieval order; the cited paper the reranker didn't keep is not shown.
    assert [x["evidence_id"] for x in refs] == ["pmid:111", "ref:who-flu", "lib:doc7:p3"]
    assert [x["rank"] for x in refs] == [1, 2, 3]
    pub, ref, lib = refs
    assert pub["title"] == "Hydration and influenza" and pub["year"] == 2019 and pub["study_type"] == "rct"
    assert pub["pmid"] == "111" and pub["doi"] == "10.1/a" and pub["url"] == "https://pubmed.ncbi.nlm.nih.gov/111/"
    assert pub["source_kind"] == "pubmed" and pub["abstract_snippet"].startswith("A randomised trial")
    assert len(pub["abstract_snippet"]) <= 301 and pub["abstract_snippet"].endswith("…")
    assert ref["publisher"] == "WHO" and ref["year"] == 2023 and ref["source_kind"] == "reference"
    assert ref["url"] == "https://www.who.int/flu"
    # Library documents by title only.
    assert lib == {"evidence_id": "lib:doc7:p3", "source_kind": "library", "rank": 3,
                   "title": "Clinical virology handbook", "year": None, "publisher": None, "study_type": None,
                   "abstract_snippet": "", "url": None, "pmid": None, "doi": None}
    assert "must not be shown" not in r.text
    assert body["claims"][0]["references"] == []
    _assert_no_system_view(body, r.text)


def test_blind_admin_gets_the_material_also_on_legacy_cases(env):
    c = env["client"]
    assert c.get(PATH.format("rev-alice"), headers=ADA).status_code == 200
    assert c.get(PATH.format("rev-legacy"), headers=ADA).status_code == 200
    # A reviewer may not see a legacy (NULL-owner) job at all: 404, as in T33.
    assert c.get(PATH.format("rev-legacy"), headers=RHEA).status_code == 404


def test_non_blind_callers_get_403(env):
    c = env["client"]
    # Reviewer and admin who have recorded their judgement (seeded in T33's fixture).
    for who in ("reviewer", "admin"):
        r = c.get(PATH.format("rev-alice"), headers=t33.CALLERS[who])
        assert r.status_code == 403, who
        assert r.json()["detail"]["code"] == "BLIND_STEP_NOT_ACTIVE"
    # Rhea stops being blind once she posts her own judgement.
    assert c.get(PATH.format("rev-alice"), headers=RHEA).status_code == 200
    r = c.post("/v1/reviews/rev-alice/pre-reveal", headers=RHEA,
               json={"claims": [{"claim_id": "c1", "stance": "ENDORSES", "verdict": "CONTRADICTED"}]})
    assert r.status_code == 201, r.text
    r = c.get(PATH.format("rev-alice"), headers=RHEA)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "BLIND_STEP_NOT_ACTIVE"


def test_reviewer_on_their_own_video_is_not_blind_and_gets_403(env):
    alice_reviewer = t33.auth("alice", "reviewer")
    r = env["client"].get(PATH.format("rev-alice"), headers=alice_reviewer)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "BLIND_STEP_NOT_ACTIVE"


def test_non_high_and_resolved_cases_have_no_blind_material(env):
    c = env["client"]
    s = env["Session"]()
    case = s.get(HumanReview, "rev-alice")
    case.severity = "MEDIUM"
    case.claim_severities = {"c1": {"severity": "MEDIUM", "basis": []}}
    bob = s.get(HumanReview, "rev-bob")
    bob.status = ReviewCaseStatus.RESOLVED
    s.commit()
    s.close()
    for rid in ("rev-alice", "rev-bob"):
        r = c.get(PATH.format(rid), headers=RHEA)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "BLIND_STEP_NOT_ACTIVE", rid


def test_analysts_get_403_before_lookup_and_unknown_cases_404(env):
    c = env["client"]
    for who in ("owner", "other"):
        for rid in ("rev-alice", "rev-missing"):
            r = c.get(PATH.format(rid), headers=t33.CALLERS[who])
            assert r.status_code == 403 and r.json()["detail"] == "requires the reviewer role", (who, rid)
    assert c.get(PATH.format("rev-missing"), headers=RHEA).status_code == 404
    assert c.get(PATH.format("rev-alice")).status_code == 401


def test_claims_without_a_row_still_listed_by_id(env):
    """A claim the reviewer must judge (in the case) but with no stored row."""
    s = env["Session"]()
    case = s.get(HumanReview, "rev-alice")
    case.claim_severities = {**case.claim_severities, "c9": {"severity": "HIGH", "stance": "ENDORSES",
                                                             "verdict": "CONTRADICTED"}}
    s.commit()
    s.close()
    body = env["client"].get(PATH.format("rev-alice"), headers=RHEA).json()
    assert body["claims"][-1] == {"claim_id": "c9", "text": None, "category": None, "start_seconds": None,
                                  "end_seconds": None, "source_segment_ids": [], "references": []}


def test_rows_without_a_search_trail_show_every_stored_paper_in_rank_order(env):
    """Pre-T31 rows: the reranked boundary is unknown, so every stored link is shown
    (documented residual), still in rank order and still without relations."""
    _seed_alice(env["Session"], trail=False)
    body = env["client"].get(PATH.format("rev-alice"), headers=RHEA).json()
    refs = body["claims"][1]["references"]
    assert [x["evidence_id"] for x in refs] == ["pmid:111", "ref:who-flu", "lib:doc7:p3", "pmid:999"]
    assert [x["rank"] for x in refs] == [1, 2, 3, 4]
    assert not FORBIDDEN_KEYS & set(_keys(body))


# ------------------------------------------------------------------ no leak


def _variant_client(monkeypatch, variant: str, **kw) -> TestClient:
    """A fresh database holding one HIGH case whose system view is ``variant``."""
    import app.db.models  # noqa: F401
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    t33.seed(Session, tags=("alice",))
    _seed_alice(Session, variant=variant, **kw)
    s = Session()
    res = s.query(Result).filter(Result.job_id == "job-alice").one()
    res.label = "MISINFO" if variant == "a" else "NOT_MISINFO"
    res.confidence = 0.93 if variant == "a" else 0.2
    res.explanation = "system explanation " + variant
    s.commit()
    s.close()

    def db():
        sess = Session()
        try:
            yield sess
        finally:
            sess.close()

    app.dependency_overrides[get_db] = db
    return TestClient(app)


@pytest.mark.parametrize("library", [True, False])
def test_responses_are_byte_identical_whatever_the_system_concluded(monkeypatch, library):
    """Two cases identical except for verdicts, stances, relations (and so citation and
    any order by relation), labels, deciding markers, critic notes, confidence, scores
    and reasons: the blind material is the same bytes."""
    from app.main import app

    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", t33.SECRET)
    bodies = []
    try:
        for variant in ("a", "b"):
            client = _variant_client(monkeypatch, variant, library=library)
            # Sanity: the system's view really differs between the two.
            s_ok = client.get("/v1/reviews/rev-alice", headers=t33.CALLERS["reviewer"]).json()
            assert s_ok["proposed_label"] == ("MISINFO" if variant == "a" else "NOT_MISINFO")
            r = client.get(PATH.format("rev-alice"), headers=RHEA)
            assert r.status_code == 200, r.text
            _assert_no_system_view(r.json(), r.text)
            bodies.append(r.content)
    finally:
        app.dependency_overrides.clear()
    assert bodies[0] == bodies[1]
    refs = json.loads(bodies[0])["claims"][1]["references"]
    assert len(refs) == (3 if library else 2)


def test_response_model_has_no_system_fields():
    """The schema itself has no field that could carry the system's view."""
    from app.services.blind_material import BlindClaimView, BlindMaterialResponse, BlindReferenceView

    fields = (set(BlindMaterialResponse.model_fields) | set(BlindClaimView.model_fields)
              | set(BlindReferenceView.model_fields))
    assert not FORBIDDEN_KEYS & fields
