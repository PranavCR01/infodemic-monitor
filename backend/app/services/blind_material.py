"""What a blind reviewer judges from (lead's decision D7 Q1; target design §12; T40).

While a reviewer is blind on an open HIGH case (``app.services.blind_review``) the
result, claims and evidence routes answer 403 ``PRE_REVEAL_REQUIRED``, and the case
view shows only each claim's text, category and times. This module builds the rest of
what a person needs to form their own stance and verdict, and nothing of what the
system concluded:

- per claim: its text, category, start/end and the segment ids the extractor quoted
  (``claims.source_segment_ids``, not the stance's segments, which the stance step
  chose);
- the transcript and on-screen text segments with timestamps;
- per claim, the papers and references retrieval put in front of the verifier, in
  retrieval (rerank) order: title, year, publisher, study type, abstract snippet, URL,
  PMID, DOI. Library documents by title only.

**Never in the response:** relation (supports / contradicts / considered), cited or
deciding markers, verdict, stance, labels, reasons, rules fired, critic notes,
confidence, relevance scores, severity, or any ``search_trail`` field.

**Which papers.** ``claim_evidence`` holds the reranked set the verifier saw (ranks
1..K, in rerank order) followed by any *cited* record from the retrieval or library
pools that the reranker did not keep (``pipeline_result_service._evidence_for_claim``).
Those trailing rows exist only because the verifier cited them, so showing them would
leak a citation. K is the trail's ``counts.kept`` (``len(reranked_evidence)``), so rows
ranked above K are left out. Rows stored before T31 have no trail; then every stored
row is shown (the boundary is unknown) — see context/MULTI_AGENT.md for this residual.

Ordering never uses relation or citation: claims by start time then claim id; papers
by stored rank then evidence id; segments by start time then segment id.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.result_models import SegmentView, SourceKind
from app.db.models.claim import ClaimEvidenceRow, ClaimRow
from app.db.models.job import Job
from app.db.models.review import HumanReview
from app.services.result_view_service import SOURCE_KINDS, abstract_snippet, segments

NOT_BLIND = "BLIND_STEP_NOT_ACTIVE"


class BlindReferenceView(BaseModel):
    """A paper or reference retrieval found for the claim. No relation, no score."""

    evidence_id: str
    source_kind: SourceKind
    rank: int  # 1-based position in retrieval order
    title: str
    # Null for library documents (title only) and when not known.
    year: Optional[int] = None
    publisher: Optional[str] = None
    study_type: Optional[str] = None
    abstract_snippet: str = ""
    url: Optional[str] = None
    pmid: Optional[str] = None
    doi: Optional[str] = None


class BlindClaimView(BaseModel):
    claim_id: str
    text: Optional[str] = None
    category: Optional[str] = None
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    source_segment_ids: list[str] = Field(default_factory=list)
    references: list[BlindReferenceView] = Field(default_factory=list)


class BlindMaterialResponse(BaseModel):
    review_id: str
    job_id: str
    video_id: Optional[str] = None
    material: Literal["blind"] = "blind"
    claims: list[BlindClaimView] = Field(default_factory=list)
    transcript_segments: list[SegmentView] = Field(default_factory=list)
    ocr_segments: list[SegmentView] = Field(default_factory=list)


def _kept_count(row: ClaimRow) -> Optional[int]:
    """How many of the stored links are the reranked set, from the search trail."""
    trail = row.search_trail
    if not isinstance(trail, dict):
        return None
    counts = trail.get("counts")
    kept = counts.get("kept") if isinstance(counts, dict) else None
    return kept if isinstance(kept, int) and not isinstance(kept, bool) and kept >= 0 else None


def _shown_links(row: ClaimRow) -> list[ClaimEvidenceRow]:
    links = sorted(row.evidence_links,
                   key=lambda l: (l.rank if l.rank is not None else float("inf"), l.evidence.evidence_id))
    kept = _kept_count(row)
    if kept is not None:
        # Rows past the reranked block are there only because they were cited.
        links = [l for l in links if l.rank is not None and l.rank <= kept]
    return links


def _reference(link: ClaimEvidenceRow, position: int) -> BlindReferenceView:
    ev = link.evidence
    kind = ev.source if ev.source in SOURCE_KINDS else "other"
    if kind == "library":
        return BlindReferenceView(evidence_id=ev.evidence_id, source_kind=kind, rank=position, title=ev.title)
    return BlindReferenceView(
        evidence_id=ev.evidence_id, source_kind=kind, rank=position, title=ev.title,
        year=ev.publication_year, publisher=ev.publisher, study_type=ev.study_type,
        abstract_snippet=abstract_snippet(ev.abstract), url=ev.source_url, pmid=ev.pmid, doi=ev.doi,
    )


def blind_material(db: Session, case: HumanReview) -> BlindMaterialResponse:
    """The material for ``case``. The caller checks access and blindness first."""
    from app.services.review_service import claim_ids_of

    job = db.get(Job, case.job_id)
    rows = {r.claim_id: r for r in db.query(ClaimRow).filter(ClaimRow.job_id == case.job_id).all()}
    # The claims the reviewer must judge (pre-reveal needs every one) plus any stored row;
    # only the ids are used from claim_ids_of, never the stance/verdict it carries.
    ids = set(claim_ids_of(db, case)) | set(rows)

    def order(cid: str) -> tuple[float, str]:
        row = rows.get(cid)
        return (row.start_seconds if row is not None else float("inf"), cid)

    claims = []
    for cid in sorted(ids, key=order):
        row = rows.get(cid)
        if row is None:
            claims.append(BlindClaimView(claim_id=cid))
            continue
        claims.append(BlindClaimView(
            claim_id=cid, text=row.text, category=row.category,
            start_seconds=row.start_seconds, end_seconds=row.end_seconds,
            source_segment_ids=list(row.source_segment_ids or []),
            references=[_reference(l, i) for i, l in enumerate(_shown_links(row), start=1)],
        ))
    transcript, ocr = segments(db, case.job_id)
    return BlindMaterialResponse(
        review_id=case.id, job_id=case.job_id, video_id=job.video_id if job is not None else None,
        claims=claims, transcript_segments=transcript, ocr_segments=ocr,
    )
