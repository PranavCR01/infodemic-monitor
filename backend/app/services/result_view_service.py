"""Read-side views of a stored result for the API (target design §12, §17; T26).

Builds the typed models in ``app.api.result_models`` from rows that are already stored
(``results``, the claim-level tables from T11, ``human_reviews`` from T09/T22). Reads
only: nothing here writes, calls a model or changes a label.

- **Modality** of a claim (speech / screen / both) comes from its
  ``source_segment_ids``: ids found in the job's ``transcript_segments`` are speech,
  in ``ocr_segments`` screen. Ids not stored (older rows) fall back to the extractor's
  naming (``t*`` transcript, ``o*`` OCR, §4); anything else is ignored.
- **Stance quotes** are the stored segments named by the stance's
  ``segment_ids``: the words the stance is based on, with timestamps.
- **Source kind** of a paper is its ``source`` (``pubmed`` / ``reference`` /
  ``library``); any other value is ``other``.
- **Review** is returned whenever a case exists, open or resolved (the fix the frontend
  session asked for: it used to become null once the case was resolved).
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.api.result_models import (
    ClaimContextView,
    ContextItemView,
    ClaimSeverityView,
    ClaimView,
    CriticView,
    EvidenceView,
    JobResultResponse,
    ReviewView,
    SegmentView,
    StudyTypeCountView,
)
from app.core.retrieval.rerank import StudyType, classify_study
from app.core.retrieval.schemas import EvidenceRecord
from app.core.speaker_quote import QuoteSegment, best_overlap_quote
from app.core.user_text import clean_title, source_name, user_text
from app.core.schemas.pipeline import display_label
from app.core.schemas.search_trail import SearchTrailView
from app.db.models.claim import (
    ClaimEvidenceRow,
    ClaimRow,
    EvidenceRecordRow,
    OcrSegmentRow,
    TranscriptSegmentRow,
)
from app.db.models.job import Job
from app.db.models.result import Result
from app.db.models.review import HumanReview, ReviewAction, ReviewCaseStatus
from app.db.models.video import Video
from app.services.review_reasons import parse_reasons

ABSTRACT_SNIPPET_CHARS = 300
SOURCE_KINDS = frozenset({"pubmed", "reference", "library", "journal_doi"})
# T65 (f): per-claim journal / publication date, stored inside the claim's search_trail
# JSON (no new column; ``SearchTrailView`` ignores the key, so it is not in search_trail).
SOURCE_META_KEY = "source_meta"


# ------------------------------------------------------------------ segments


def segments(db: Session, job_id: str) -> tuple[list[SegmentView], list[SegmentView]]:
    transcript = [
        SegmentView(segment_id=s.segment_id, source="speech", start_seconds=s.start_seconds,
                    end_seconds=s.end_seconds, text=s.text)
        for s in db.query(TranscriptSegmentRow).filter(TranscriptSegmentRow.job_id == job_id)
        .order_by(TranscriptSegmentRow.start_seconds, TranscriptSegmentRow.segment_id)
    ]
    ocr = [
        SegmentView(segment_id=s.segment_id, source="screen", start_seconds=s.start_seconds,
                    end_seconds=s.end_seconds, text=s.text, confidence=s.confidence)
        for s in db.query(OcrSegmentRow).filter(OcrSegmentRow.job_id == job_id)
        .order_by(OcrSegmentRow.start_seconds, OcrSegmentRow.segment_id)
    ]
    return transcript, ocr


def _source_of(segment_id: str, index: dict[str, SegmentView]) -> Optional[str]:
    if segment_id in index:
        return index[segment_id].source
    if segment_id[:1] == "t":
        return "speech"
    if segment_id[:1] == "o":
        return "screen"
    return None


def modality(segment_ids: Iterable[str], index: dict[str, SegmentView]) -> Optional[str]:
    kinds = {k for k in (_source_of(s, index) for s in segment_ids) if k}
    if kinds == {"speech", "screen"}:
        return "both"
    return next(iter(kinds)) if kinds else None


# ------------------------------------------------------------------ evidence


def abstract_snippet(text: Optional[str], limit: int = ABSTRACT_SNIPPET_CHARS) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(" ,;:.") + "…"


def study_type_of(ev: EvidenceRecordRow) -> str:
    """The one study type a source has, for the source list and the counts alike
    (T65 c): the reranker's stored type; for a row stored without one, the same
    classifier run on the stored PubMed metadata; ``unknown`` if that finds nothing."""
    if ev.study_type:
        return ev.study_type
    try:
        rec = EvidenceRecord(
            evidence_id=ev.evidence_id, source=ev.source if ev.source in SOURCE_KINDS else "pubmed",
            title=ev.title or "", abstract=ev.abstract or "",
            publication_type=[str(t) for t in (ev.publication_type or [])])
        return classify_study(rec).value
    except ValueError:
        return StudyType.UNKNOWN.value


def _source_meta(meta: Optional[dict], ev: EvidenceRecordRow) -> tuple[Optional[str], Optional[str]]:
    """Journal and publication date: from the claim's stored source metadata (T65 f,
    kept with the search trail), else the journal_doi record's journal and the year."""
    m = (meta or {}).get(ev.evidence_id) or {}
    journal = m.get("journal") or (ev.publisher if ev.source == "journal_doi" else None)
    pub_date = m.get("pub_date") or (str(ev.publication_year) if ev.publication_year else None)
    return journal, pub_date


def evidence_view(link: ClaimEvidenceRow, meta: Optional[dict] = None) -> EvidenceView:
    ev = link.evidence
    journal, pub_date = _source_meta(meta, ev)
    return EvidenceView(
        evidence_id=ev.evidence_id, title=clean_title(ev.title), pmid=ev.pmid, url=ev.source_url,
        study_type=study_type_of(ev), relation=link.relation, journal=journal, pub_date=pub_date,
        source_kind=ev.source if ev.source in SOURCE_KINDS else "other",
        doi=ev.doi, year=ev.publication_year, publisher=ev.publisher,
        publication_type=list(ev.publication_type or []), abstract_snippet=abstract_snippet(ev.abstract),
        relevance_score=link.relevance_score, rank=link.rank, retrieved_at=ev.retrieved_at,
        snapshot_sha256=ev.snapshot_sha256,
    )


def source_meta_of(claim: ClaimRow) -> dict:
    trail = claim.search_trail if isinstance(claim.search_trail, dict) else {}
    meta = trail.get(SOURCE_META_KEY)
    return meta if isinstance(meta, dict) else {}


def evidence_views(claim: ClaimRow, *, cited_only: bool) -> list[EvidenceView]:
    links = sorted(claim.evidence_links, key=lambda l: l.rank or 0)
    meta = source_meta_of(claim)
    return [evidence_view(l, meta) for l in links if not cited_only or l.relation != "CONSIDERED"]


def study_type_counts(evidence: Iterable[EvidenceView]) -> list[StudyTypeCountView]:
    counts: dict[tuple[str, str], int] = {}
    for e in evidence:
        if e.relation in ("SUPPORTS", "CONTRADICTS"):
            key = (e.study_type or StudyType.UNKNOWN.value, e.relation)
            counts[key] = counts.get(key, 0) + 1
    return [StudyTypeCountView(study_type=t, relation=r, count=n)
            for (t, r), n in sorted(counts.items(), key=lambda kv: (kv[0][1], -kv[1], kv[0][0]))]


def source_names(claim: ClaimRow) -> dict[str, Optional[str]]:
    """Every source shown to the verifier for this claim, by evidence id → its name in
    user-facing text (short title, else PMID; T65 a)."""
    return {l.evidence.evidence_id: source_name(l.evidence.title, l.evidence.pmid) for l in claim.evidence_links}


def speaker_quote(c: ClaimRow, index: dict[str, SegmentView]):
    speech = [QuoteSegment(s.segment_id, s.start_seconds, s.end_seconds, s.text)
              for s in index.values() if s.source == "speech"]
    return best_overlap_quote(c.text, speech, c.start_seconds, c.end_seconds, c.source_segment_ids or [])


def screen_quote(c: ClaimRow, index: dict[str, SegmentView]):
    """T70 (f): a screen-only claim's quote, from the on-screen segments it cites."""
    ids = set(c.source_segment_ids or [])
    screen = [QuoteSegment(s.segment_id, s.start_seconds, s.end_seconds, s.text)
              for s in index.values() if s.source == "screen" and s.segment_id in ids]
    return best_overlap_quote(c.text, screen, c.start_seconds, c.end_seconds, list(ids))


def _split_trail(raw: Optional[dict]) -> tuple[Optional[dict], Optional[dict]]:
    """T70: the stored search-trail JSON may carry the claim's context next to the trail."""
    if not isinstance(raw, dict) or "claim_context" not in raw:
        return raw, None
    trail = {k: v for k, v in raw.items() if k != "claim_context"}
    return (trail or None), raw.get("claim_context")


def claim_context_view(payload: Optional[dict], limitations: Iterable[str]) -> Optional[ClaimContextView]:
    from app.core.graph import claim_context as cx
    from app.core.graph import routing as rt

    ctx, topic = cx.payload_context(payload)
    if ctx is None and topic is None:
        return None
    items = [ContextItemView(field=f, label=cx.FIELD_LABELS[f], text=i.text, segment_ids=list(i.segment_ids))
             for f, i in (ctx.items() if ctx is not None else [])]
    facets = [x for x in (payload or {}).get("search_facets") or [] if isinstance(x, dict)]
    return ClaimContextView(
        scope=ctx.scope if ctx is not None else "universal", items=items,
        dropped=list(ctx.dropped) if ctx is not None else [], video_topic=topic.text if topic else None,
        setting_match=cx.setting_match_of(limitations), softened=rt.SOFTENED_LIMITATION in list(limitations),
        search_facets=[{"field": str(x.get("field")), "facet": str(x.get("facet"))} for x in facets],
    )


# ------------------------------------------------------------------ severity


def claim_severity_view(claim_id: str, entry: Optional[dict]) -> Optional[ClaimSeverityView]:
    if not entry:
        return None
    override = entry.get("override")
    public_override = (
        {k: v for k, v in override.items() if k != "reviewer_id"} if isinstance(override, dict) else None
    )
    return ClaimSeverityView(
        claim_id=claim_id,
        severity=(override or {}).get("severity") or entry.get("severity"),
        table_severity=entry.get("severity"),
        basis=list(entry.get("basis") or []),
        misinfo_relevant=bool(entry.get("misinfo_relevant")),
        override=public_override,
    )


# ------------------------------------------------------------------ claims


def claim_views(db: Session, job_id: str, case: Optional[HumanReview] = None,
                index: Optional[dict[str, SegmentView]] = None) -> list[ClaimView]:
    if index is None:
        transcript, ocr = segments(db, job_id)
        index = {s.segment_id: s for s in (*transcript, *ocr)}
    severities = (case.claim_severities or {}) if case is not None else {}
    rows = (db.query(ClaimRow).filter(ClaimRow.job_id == job_id)
            .order_by(ClaimRow.start_seconds, ClaimRow.claim_id).all())
    return [claim_view(c, index, severities.get(c.claim_id)) for c in rows]


def _search_trail(raw: Optional[dict]) -> Optional[SearchTrailView]:
    """The stored trail, or None. A row that no longer parses (written by a later
    version) is left out rather than failing the whole result."""
    if not raw:
        return None
    try:
        return SearchTrailView.model_validate(raw)
    except ValueError:
        return None


def claim_view(c: ClaimRow, index: dict[str, SegmentView], severity: Optional[dict] = None) -> ClaimView:
    from app.core.graph import claim_context as cx
    from app.core.graph import routing as rt

    stance_ids = list(c.stance.segment_ids) if c.stance else []
    names = source_names(c)
    evidence = evidence_views(c, cited_only=True)
    quote = speaker_quote(c, index)
    trail_raw, context_raw = _split_trail(c.search_trail)
    raw_limitations = list(c.verification.limitations or []) if c.verification else []
    # T69/T70 structured codes are for code, not readers (absent unless a switch was on).
    shown_limitations = [x for x in raw_limitations if not cx.is_context_code(x)]
    t70: dict = {}
    if rt.CLAIM_CONTEXT or context_raw is not None:
        context = claim_context_view(context_raw, raw_limitations)
        t70["context"] = context
        t70["context_text"] = cx.context_line(cx.payload_context(context_raw)[0])
        claim_modality = modality(c.source_segment_ids or [], index)
        if claim_modality == "screen":
            # T70 (f): never "The speaker says" for words only shown on screen.
            sq = screen_quote(c, index)
            quote = None
            t70["quote_source"] = "screen"
            t70["screen_quote"] = sq.text if sq else None
        elif quote is not None:
            t70["quote_source"] = "speech"
    return ClaimView(
        claim_id=c.claim_id, text=c.text, category=c.category,
        start_seconds=c.start_seconds, end_seconds=c.end_seconds, label=c.label, deciding=c.deciding,
        stance=c.stance.stance if c.stance else None,
        verdict=c.verification.verdict if c.verification else None,
        verdict_explanation=user_text(c.verification.explanation, names) if c.verification else "",
        limitations=([t for t in (user_text(x, names) for x in shown_limitations) if t]
                     if c.verification else []),
        evidence=evidence,
        id=c.id, claim_kind=c.claim_kind, requires_verification=c.requires_verification,
        source_segment_ids=list(c.source_segment_ids or []),
        modality=modality(c.source_segment_ids or [], index),
        stance_rationale=c.stance.rationale if c.stance else "",
        stance_segment_ids=stance_ids,
        stance_quotes=[index[s] for s in stance_ids if s in index],
        retrieval_attempts=c.verification.retrieval_attempts if c.verification else None,
        critic=(CriticView(decision=c.critic.decision, issues=list(c.critic.issues or []),
                           requires_review=c.critic.requires_review) if c.critic else None),
        severity=claim_severity_view(c.claim_id, severity),
        search_trail=_search_trail(trail_raw),
        speaker_quote=quote.text if quote else None,
        speaker_quote_segment_ids=list(quote.segment_ids) if quote else [],
        study_type_counts=study_type_counts(evidence),
        **t70,
    )


# ------------------------------------------------------------------ review


def review_status(case: HumanReview) -> str:
    if case.status == ReviewCaseStatus.OPEN:
        return "REVIEW_REQUIRED"
    if case.status == ReviewCaseStatus.SUPERSEDED:
        return "SUPERSEDED"
    action = ReviewAction(case.action) if case.action else None
    if action == ReviewAction.APPROVE:
        return "VERIFIED"
    if action in (ReviewAction.CORRECT, ReviewAction.MARK_INSUFFICIENT):
        return "CORRECTED"
    if action == ReviewAction.REJECT:
        return "REJECTED"
    return "REANALYSIS_REQUESTED"


def review_case(db: Session, job_id: str) -> Optional[HumanReview]:
    return db.query(HumanReview).filter(HumanReview.job_id == job_id).one_or_none()


def review_view(case: Optional[HumanReview]) -> Optional[ReviewView]:
    if case is None:
        return None
    resolved = case.status == ReviewCaseStatus.RESOLVED
    return ReviewView(
        status=review_status(case),
        reasons=list(case.reasons or []),
        review_id=case.id,
        case_status=ReviewCaseStatus(case.status).value,
        resolved=resolved,
        action=ReviewAction(case.action).value if case.action else None,
        reason_details=parse_reasons(case.reasons),
        rules_fired=list(case.rules_fired or []),
        severity=case.severity,
        claim_severities=[v for cid, e in (case.claim_severities or {}).items()
                          if (v := claim_severity_view(cid, e)) is not None],
        severity_table_version=case.severity_table_version,
        proposed_label=case.proposed_label,
        corrected_label=case.corrected_label,
        decision_reason=case.decision_reason,
        created_at=case.created_at,
        decided_at=case.decided_at,
        superseded_by_job_id=case.superseded_by_job_id,
    )


# ------------------------------------------------------------------ whole result


def job_source_names(db: Session, job_id: str) -> dict[str, Optional[str]]:
    rows = db.query(EvidenceRecordRow).filter(EvidenceRecordRow.job_id == job_id).all()
    return {r.evidence_id: source_name(r.title, r.pmid) for r in rows}


def job_result(db: Session, job: Job, result: Result) -> JobResultResponse:
    video = db.get(Video, job.video_id) if job.video_id else None
    case = review_case(db, job.id)
    transcript, ocr = segments(db, job.id)
    index = {s.segment_id: s for s in (*transcript, *ocr)}
    return JobResultResponse(
        job_id=job.id,
        filename=video.filename if video else None,
        label=result.label,
        confidence=result.confidence,
        explanation=user_text(result.explanation, job_source_names(db, job.id)),
        evidence_snippets=list(result.evidence_snippets or []),
        citations=result.citations,
        provider=result.provider,
        model_used=result.model_used,
        latency_ms=result.latency_ms,
        submitted_at=job.created_at,
        created_at=result.created_at,
        pipeline=result.pipeline,
        fallback_reason=result.fallback_reason,
        review=review_view(case),
        claims=claim_views(db, job.id, case, index),
        video_id=job.video_id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        pipeline_version=result.pipeline_version,
        decision_rule=result.decision_rule,
        deciding_claim_ids=list(result.deciding_claim_ids or []),
        misinfo_basis=result.misinfo_basis,
        label_display=display_label(result.label, result.misinfo_basis),
        routing_snapshot=result.routing_snapshot,
        transcript_segments=transcript,
        ocr_segments=ocr,
        submitted_by=job.user_id,
        **_versions(db, job),
    )


def _versions(db: Session, job: Job) -> dict:
    """T55: the other versions of this video's result (``reanalysis_service``)."""
    from app.api.result_models import LatestJobView, PreviousJobView
    from app.services.job_events import effective_state
    from app.services.reanalysis_service import result_versions

    v = result_versions(db, job)
    latest = v.latest_job
    return {
        "previous_jobs": [
            PreviousJobView(job_id=j.id, finished_at=r.created_at, label=r.label,
                            label_display=display_label(r.label, r.misinfo_basis),
                            pipeline_version=r.pipeline_version, status=j.status.value)
            for j, r in v.previous
        ],
        "previous_job_id": job.previous_job_id,
        "current_job_id": v.current_job_id,
        "is_current": v.current_job_id in (None, job.id),
        "latest_job": (LatestJobView(job_id=latest.id, status=latest.status.value,
                                     state=effective_state(latest), error_code=latest.error_code,
                                     created_at=latest.created_at)
                       if latest is not None else None),
    }
