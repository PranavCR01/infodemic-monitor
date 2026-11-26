"""A study the video cites, offered to the video's other claims (T57, design §6).

In the vitamin K paid run (``evals/reports/T50/paid_run.md``), find_study verified the
JAMA 2026 paper (PMID 42986716) for c2 ("a JAMA study ... 5.2 million infants") and c4,
but never proposed it for c3 ("... more than doubled from 3.1% in 2017 to 6.8% in
2025") or c5: those claims don't name the journal, and the finder only sees each
claim's own text. The video cites one study, and several claims report its numbers.

**What is shared.** A record some claim of the video already holds *as a verified
record for a cited study*:

- every record find_study verified (``found_study_evidence``; our own PMID/DOI checks,
  never the model's word), and
- the citation lookup's best record (``"JAMA"[ta] AND 2026[dp] AND (topic)``, §6): for a
  claim whose citation cue names a journal or a year, the highest-ranked record from
  that lookup that the claim's own reranker kept, that is on the claim's topic
  (``find_study.topic_match``) and, when a year is given, within a year of it. One per
  citing claim: the lookup can return many papers from that journal, and only the best
  match stands for "the study the video cites".

**Who decides.** Nothing is pinned. Each other claim is offered the shared records as
extra candidates, and a record joins the claim's evidence only if

1. the claim's reranker keeps it (relevance threshold and cap of 10, scored against the
   claim's own records like any paper), and
2. it is on topic for the claim by the T49 check (``unproven_guard.on_topic_ids``: the
   claim's intervention terms in the title or abstract), and
3. when the claim itself names a journal or a year, the record agrees with it.

A record that fails any of these is not added. No model call and no web search:
the step is code over records the run already holds.

**Deterministic.** The pool is gathered in claim-id order (natural order: c2 before
c10), so the result never depends on the order claims were processed in, and
``shared_from`` is the first claim, in that order, that holds the record.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from app.core.graph.state import EvidenceRecord, GraphClaim, SearchRound, SharedStudy
from app.core.retrieval.citation import CitationCue, citation_cue
from app.core.retrieval.planning import normalize_claim

KEPT = "kept"
NOT_KEPT = "not_kept_by_reranker"
OFF_TOPIC = "off_topic"
CITATION_MISMATCH = "citation_mismatch"

__all__ = [
    "CITATION_MISMATCH", "KEPT", "NOT_KEPT", "OFF_TOPIC", "SharedCandidate", "claim_order",
    "share_cited_studies", "shared_pool",
]


def claim_order(cid: str) -> tuple:
    """Natural sort key for claim ids: c2 < c10."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.findall(r"\d+|\D+", cid))


@dataclass(frozen=True)
class SharedCandidate:
    record: EvidenceRecord
    shared_from: str
    journal: Optional[str]  # what the source claim's verification established, if anything


def _keys(rec: EvidenceRecord) -> set[str]:
    keys = {f"id:{rec.evidence_id}"}
    if rec.pmid:
        keys.add(f"pmid:{rec.pmid}")
    if rec.doi:
        keys.add(f"doi:{rec.doi.lower()}")
    return keys


def _cue(claim: GraphClaim) -> CitationCue:
    return citation_cue(normalize_claim(claim.claim_text))


def _citation_lookup_record(claim: GraphClaim, kept: Sequence[EvidenceRecord],
                            rounds: Sequence[SearchRound]) -> Optional[EvidenceRecord]:
    """The citing claim's best record from its own citation lookup, or None."""
    from app.core.retrieval.find_study import topic_match

    cue = _cue(claim)
    if not (cue.cites_study and (cue.journal or cue.year)):
        return None
    queries = {rnd.pubmed_query for rnd in rounds
               if getattr(rnd, "query_kind", None) == "citation" and rnd.pubmed_query}
    if not queries:
        return None
    for rec in kept:  # best first, as the claim's reranker ordered them
        if rec.query not in queries:
            continue
        if cue.year and rec.publication_year and abs(int(rec.publication_year) - int(cue.year)) > 1:
            continue
        if cue.year and not rec.publication_year:
            continue
        if topic_match(claim.claim_text, rec.title, rec.abstract):
            return rec
    return None


def shared_pool(
    claims: Mapping[str, GraphClaim],
    found: Mapping[str, Sequence[EvidenceRecord]],
    reranked: Mapping[str, Sequence[EvidenceRecord]],
    search_trail: Mapping[str, Sequence[SearchRound]],
) -> list[SharedCandidate]:
    """Every verified cited-study record the video's claims hold, deduplicated by
    PMID / DOI / evidence id, in claim-id order (the first holder is ``shared_from``)."""
    pool: list[SharedCandidate] = []
    seen: set[str] = set()

    def add(rec: EvidenceRecord, cid: str, journal: Optional[str]) -> None:
        keys = _keys(rec)
        if keys & seen:
            return
        seen.update(keys)
        pool.append(SharedCandidate(rec, cid, journal))

    for cid in sorted(set(found) | set(reranked), key=claim_order):
        claim = claims.get(cid)
        if claim is None:
            continue
        cue = _cue(claim)
        for rec in found.get(cid, []):
            # find_study checked the journal only when the claim named one (§6).
            add(rec, cid, rec.publisher if rec.source == "journal_doi" else cue.journal)
        rec = _citation_lookup_record(claim, reranked.get(cid, []), search_trail.get(cid, []))
        if rec is not None:
            add(rec, cid, cue.journal)
    return pool


def _journal_key(name: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _citation_conflict(claim: GraphClaim, cand: SharedCandidate) -> Optional[str]:
    """Why the record can't be the study this claim names, or None."""
    cue = _cue(claim)
    if cue.journal:
        want, got = _journal_key(cue.journal), _journal_key(cand.journal)
        if not got or not (want == got or want in got or got in want):
            return f"claim names {cue.journal!r}; the shared record's journal is {cand.journal or 'unknown'!r}"
    year = cand.record.publication_year
    if cue.year and (not year or abs(int(year) - int(cue.year)) > 1):
        return f"claim names {cue.year}; the shared record is from {year or 'an unknown year'}"
    return None


def share_cited_studies(
    claims: Mapping[str, GraphClaim],
    reranked: dict[str, list[EvidenceRecord]],
    retrieved: Mapping[str, Sequence[EvidenceRecord]],
    found: Mapping[str, Sequence[EvidenceRecord]],
    search_trail: Mapping[str, Sequence[SearchRound]],
    rerank,
    on_error=None,
) -> dict[str, list[SharedStudy]]:
    """Offer the pool to every claim (see the module docstring). Updates ``reranked`` in
    place for claims that keep a shared record and returns the per-claim trail.

    ``rerank(claim, records) -> list[EvidenceRecord]`` is the claim's reranker (kept
    records, best first). If it raises for a claim, that claim keeps its own evidence,
    gets no trail entry, and ``on_error(claim_id, exc)`` is called."""
    from app.core.graph.unproven_guard import on_topic_ids

    pool = shared_pool(claims, found, reranked, search_trail)
    trail: dict[str, list[SharedStudy]] = {}
    if not pool:
        return trail
    for cid in sorted(reranked, key=claim_order):
        claim = claims.get(cid)
        if claim is None:
            continue
        held: set[str] = set()
        for rec in [*retrieved.get(cid, []), *found.get(cid, []), *reranked.get(cid, [])]:
            held |= _keys(rec)
        offered = [c for c in pool if c.shared_from != cid and not (_keys(c.record) & held)]
        if not offered:
            continue
        entries: list[SharedStudy] = []
        eligible: list[SharedCandidate] = []
        for c in offered:
            why = _citation_conflict(claim, c)
            if why:
                entries.append(_entry(c, CITATION_MISMATCH, why))
            elif not on_topic_ids(claim, [c.record]):
                entries.append(_entry(c, OFF_TOPIC, "not on topic for this claim's intervention (T49 check)"))
            else:
                eligible.append(c)
        if eligible:
            try:
                kept = rerank(claim, [*reranked.get(cid, []), *(c.record for c in eligible)])
            except Exception as exc:  # noqa: BLE001 - the claim goes on with its own evidence
                if on_error is not None:
                    on_error(cid, exc)
                continue
            kept_ids = {r.evidence_id: r for r in kept}
            for c in eligible:
                rec = kept_ids.get(c.record.evidence_id)
                if rec is None:
                    entries.append(_entry(c, NOT_KEPT, "below the relevance threshold or outside the cap of 10"))
                else:
                    entries.append(_entry(c, KEPT, "", rec.relevance_score))
            if any(e.outcome == KEPT for e in entries):
                reranked[cid] = list(kept)
        entries.sort(key=lambda e: next(i for i, c in enumerate(pool) if c.record.evidence_id == e.evidence_id))
        trail[cid] = entries
    return trail


def _entry(c: SharedCandidate, outcome: str, reason: str, relevance: Optional[float] = None) -> SharedStudy:
    r = c.record
    return SharedStudy(evidence_id=r.evidence_id, pmid=r.pmid, doi=r.doi, title=(r.title or "")[:300],
                       shared_from=c.shared_from, outcome=outcome, reason=reason, relevance_score=relevance)
