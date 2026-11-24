"""Persisting a graph-pipeline outcome (T11, issue #38; design §1 idempotency, §12, §17).

``persist_outcome`` writes, in one transaction:

- the video-level ``results`` row (also for a fallback, with ``pipeline`` and
  ``fallback_reason`` set), the same columns the single-call path fills;
- when the graph produced the result: the claim-level rows (segments, claims,
  stances, evidence, claim–evidence links, verdicts, critic reviews);
- one ``model_runs`` row per routed model call;
- the job's final state: ``REVIEW_REQUIRED`` with a ``human_reviews`` case when the
  review rule fired (``review_service.open_review_case``), otherwise ``SUCCESS``.

**Idempotent per job.** Celery delivers at least once, so this may run twice for the
same job. Every row is keyed by the job: an existing result is updated in place and
the job's claim-level rows are replaced, so a second run leaves one copy. The graph's
``persist_result`` node stays reference-only; the worker persists here so the graph
path and its fallback share one transaction and the graph state never holds a DB
session (context/MULTI_AGENT.md §7k).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.schemas.pipeline import FusionResult
from app.db.models.claim import (
    ClaimEvidenceRow,
    ClaimRow,
    ClaimStanceRow,
    CriticReviewRow,
    EvidenceRecordRow,
    ModelRunRow,
    OcrSegmentRow,
    TranscriptSegmentRow,
    VerificationResultRow,
)
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result

_PER_JOB = (ModelRunRow, TranscriptSegmentRow, OcrSegmentRow)


def _clear_claim_level(db: Session, job_id: str) -> None:
    claims = db.query(ClaimRow).filter(ClaimRow.job_id == job_id).all()
    for c in claims:
        db.delete(c)  # cascades to stance, verdict, critic review, evidence links
    db.flush()
    db.query(EvidenceRecordRow).filter(EvidenceRecordRow.job_id == job_id).delete(synchronize_session=False)
    for model in _PER_JOB:
        db.query(model).filter(model.job_id == job_id).delete(synchronize_session=False)
    db.flush()


def _upsert_result(db: Session, job_id: str, fusion: FusionResult, outcome: Any, pipeline_version: Optional[str]) -> Result:
    c = outcome.classification
    final = (outcome.state or {}).get("final_result") if not outcome.fallback_used else None
    values = dict(
        label=c.label.value,
        confidence=c.confidence,
        explanation=c.explanation,
        evidence_snippets=list(c.evidence_snippets),
        citations=[x.model_dump() for x in c.citations] if c.citations else None,
        combined_content=fusion.combined_content,
        provider=c.provider,
        model_used=c.model_used[:128],
        latency_ms=c.latency_ms,
        pipeline=outcome.pipeline,
        pipeline_version=pipeline_version,
        fallback_reason=outcome.fallback_reason,
        decision_rule=getattr(final, "decision_rule", None),
        deciding_claim_ids=list(final.claim_ids) if final is not None else None,
        misinfo_basis=getattr(final, "misinfo_basis", None),
    )
    result = db.query(Result).filter(Result.job_id == job_id).one_or_none()
    if result is None:
        result = Result(job_id=job_id, **values)
        db.add(result)
    else:
        for k, v in values.items():
            setattr(result, k, v)
    return result


def _evidence_for_claim(state: dict, cid: str) -> list:
    """The records the verifier saw (reranked), plus any cited library passage."""
    seen: dict[str, Any] = {}
    for rec in (state.get("reranked_evidence") or {}).get(cid, []):
        seen.setdefault(rec.evidence_id, rec)
    for pool in ("retrieved_evidence", "library_evidence"):
        v = (state.get("verification_results") or {}).get(cid)
        cited = set(v.supporting_evidence_ids + v.contradicting_evidence_ids) if v else set()
        for rec in (state.get(pool) or {}).get(cid, []):
            if rec.evidence_id in cited:
                seen.setdefault(rec.evidence_id, rec)
    return list(seen.values())


def _write_claim_level(db: Session, job_id: str, state: dict) -> None:
    from app.core.graph.judge import claim_label
    from app.services.search_trail import build_search_trail

    for s in state.get("transcript_segments") or []:
        db.add(TranscriptSegmentRow(job_id=job_id, segment_id=s.segment_id, start_seconds=s.start,
                                    end_seconds=s.end, text=s.text))
    for s in state.get("ocr_segments") or []:
        db.add(OcrSegmentRow(job_id=job_id, segment_id=s.segment_id, start_seconds=s.start,
                             end_seconds=s.end, text=s.text, confidence=s.confidence))

    final = state.get("final_result")
    deciding = set(final.claim_ids) if final is not None else set()
    stances = state.get("stance_results") or {}
    verdicts = state.get("verification_results") or {}
    critics = state.get("critic_results") or {}
    revisions = state.get("verification_revisions") or {}
    attempts = state.get("retrieval_attempts") or {}
    evidence_rows: dict[str, EvidenceRecordRow] = {}

    for claim in state.get("claims") or []:
        cid = claim.claim_id
        stance, verdict, critic = stances.get(cid), verdicts.get(cid), critics.get(cid)
        row = ClaimRow(
            job_id=job_id, claim_id=cid, text=claim.claim_text, category=claim.claim_category,
            start_seconds=claim.start_seconds, end_seconds=claim.end_seconds,
            source_segment_ids=list(claim.source_segment_ids),
            requires_verification=claim.requires_verification,
            claim_kind=claim.claim_kind,
            label=claim_label(stance.stance if stance else None, verdict.verdict).value if verdict else None,
            deciding=cid in deciding,
            search_trail=build_search_trail(state, cid),
        )
        db.add(row)
        if stance is not None:
            row.stance = ClaimStanceRow(
                stance=stance.stance.value, segment_ids=list(stance.stance_segment_ids),
                rationale=stance.rationale, model=stance.model, prompt_version=stance.prompt_version)
        if verdict is not None:
            row.verification = VerificationResultRow(
                verdict=verdict.verdict.value, explanation=verdict.explanation,
                limitations=list(verdict.limitations), raw_confidence=verdict.raw_confidence,
                revisions=int(revisions.get(cid, 0)), retrieval_attempts=int(attempts.get(cid, 0)),
                model=verdict.model, prompt_version=verdict.prompt_version)
        if critic is not None:
            row.critic = CriticReviewRow(
                decision=critic.decision.value, issues=list(critic.issues), checks=list(critic.checks),
                requires_review=critic.requires_review, model=critic.model,
                prompt_version=critic.prompt_version)
        supporting = set(verdict.supporting_evidence_ids) if verdict else set()
        contradicting = set(verdict.contradicting_evidence_ids) if verdict else set()
        for rank, rec in enumerate(_evidence_for_claim(state, cid), start=1):
            ev = evidence_rows.get(rec.evidence_id)
            if ev is None:
                ev = EvidenceRecordRow(
                    job_id=job_id, evidence_id=rec.evidence_id, source=rec.source, pmid=rec.pmid,
                    doi=rec.doi, title=rec.title, abstract=rec.abstract or "",
                    publication_type=list(rec.publication_type or []),
                    publication_year=rec.publication_year, source_url=rec.source_url,
                    study_type=rec.study_type, quality_score=rec.quality_score,
                    publisher=rec.publisher, retrieved_at=rec.retrieved_at,
                    snapshot_sha256=rec.snapshot_sha256)
                db.add(ev)
                evidence_rows[rec.evidence_id] = ev
            relation = ("SUPPORTS" if rec.evidence_id in supporting else
                        "CONTRADICTS" if rec.evidence_id in contradicting else "CONSIDERED")
            row.evidence_links.append(ClaimEvidenceRow(
                evidence=ev, relation=relation, relevance_score=rec.relevance_score, rank=rank))


def _write_model_runs(db: Session, job_id: str, calls: list) -> None:
    for seq, rec in enumerate(calls, start=1):
        db.add(ModelRunRow(
            job_id=job_id, seq=seq, step=rec.step, provider=rec.provider, model=rec.model,
            prompt_version=rec.prompt_version, attempts=rec.attempts, fallback_used=rec.fallback_used,
            fallback_reason=rec.fallback_reason, latency_ms=rec.latency_ms,
            input_tokens=rec.input_tokens, output_tokens=rec.output_tokens, cost_usd=rec.cost_usd,
            error=rec.error))


def persist_outcome(db: Session, job_id: str, fusion: FusionResult, outcome: Any) -> Result:
    """Write one graph-pipeline outcome for ``job_id`` (see module docstring)."""
    job = db.get(Job, job_id)
    if job is None:
        raise ValueError(f"job {job_id!r} not found")
    state = outcome.state or {}
    pipeline_version = state.get("pipeline_version")
    try:
        _clear_claim_level(db, job_id)
        result = _upsert_result(db, job_id, fusion, outcome, pipeline_version)
        if not outcome.fallback_used and state:
            _write_claim_level(db, job_id, state)
        _write_model_runs(db, job_id, list(outcome.model_calls or []))
        job.updated_at = datetime.now(timezone.utc)
        if outcome.requires_human_review:
            from app.services.review_service import open_review_case

            open_review_case(db, job_id, state)  # sets REVIEW_REQUIRED and commits
        else:
            job.status = JobStatus.SUCCESS
            db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(result)
    return result


def claim_level_view(db: Session, job_id: str) -> list[dict]:
    """Claims with stance, verdict and papers, for the results API (§17
    ``/videos/{id}/claims``). Empty for single-call and fallback results. Since T26 the
    dicts carry more fields (see ``app.api.result_models.ClaimView``); the T11 keys are
    unchanged."""
    from app.services.result_view_service import claim_views

    return [c.model_dump() for c in claim_views(db, job_id)]
