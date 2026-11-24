"""Frozen retrieval for the verify_claims experiment (§6, §13).

Every candidate verifier must judge a claim against **identical** evidence, otherwise
the comparison measures PubMed's mood that day, not the model. So retrieval runs once
per claim, before any model call, and its results are written to a JSON file; the
experiment only ever reads that file.

Recording (free: PubMed E-utilities at <= 2.5 requests/second through the backend's
shared limiter, plus the §6 reference allow-list; no model is called):

- **retrieved**: the pipeline's own §6 retrieval with the full search budget spent:
  every rung of the planner's ladder up to ``Budgets.max_retrieval_attempts`` rounds,
  merged; for a ``fact_of_record`` claim the allow-listed references are searched once
  too; then the §6 reranker (relevance threshold, cap of 10). Any retrieval error is
  recorded, and makes the claim ineligible for UNSUPPORTED, as in the graph
  (``routing.unproven_eligible``).
- **cited**: the papers and reference passages the gold label rests on
  (``evidence_supporting`` / ``evidence_contradicting`` and ``reference_citations.csv``),
  fetched from PubMed / taken from the quoted passage. Which side they were cited for is
  never stored in the record the model sees.

Two evidence modes when loading:

- ``retrieved+cited`` (default): the retrieved set plus the cited items, re-scored by
  the reranker and capped at 10 with every cited item kept. The verification metric
  then measures *verification*: the evidence the human label rests on is in front of
  the model (§14 scores retrieval separately).
- ``retrieved``: exactly what the pipeline's retrieval found; measures retrieval and
  verification together.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

from app.core.graph.routing import DEFAULT_BUDGETS, UNPROVEN_CATEGORIES, Budgets
from app.core.graph.state import EvidenceRecord
from app.core.retrieval.planning import QueryPlanner
from app.core.retrieval.rerank import MAX_EVIDENCE_PER_CLAIM, Reranker
from app.core.retrieval.retriever import merge_evidence, to_evidence
from app.evaluation.routing_experiment.golden import GoldClaimRow, TuneSet
from app.evaluation.routing_experiment.items import efficacy_category, in_scope_video_ids

FORMAT = "t38_frozen_evidence_v1"
MODES: tuple[str, ...] = ("retrieved+cited", "retrieved")
DEFAULT_MODE = "retrieved+cited"


class FrozenEvidenceError(ValueError):
    pass


# ------------------------------------------------------------------ recording


@dataclass
class ClaimRecording:
    key: str
    claim_text: str
    claim_kind: str
    claim_category: str
    queries: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    retrieved_total: int = 0
    retrieved: list[EvidenceRecord] = field(default_factory=list)
    cited: list[EvidenceRecord] = field(default_factory=list)
    cited_missing: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "claim_text": self.claim_text, "claim_kind": self.claim_kind,
            "claim_category": self.claim_category, "queries": self.queries, "errors": self.errors,
            "retrieved_total": self.retrieved_total,
            "retrieved": [r.model_dump(exclude_none=True) for r in self.retrieved],
            "cited": [r.model_dump(exclude_none=True) for r in self.cited],
            "cited_missing": self.cited_missing,
        }


def _pmid(ref: str) -> Optional[str]:
    ref = ref.strip()
    if ref.upper().startswith("PMID:"):
        digits = ref.split(":", 1)[1].strip()
        return digits if digits.isdigit() else None
    return None


def _reference_record(row: dict) -> Optional[EvidenceRecord]:
    passage = (row.get("quoted_passage") or "").strip()
    eid = (row.get("evidence_id") or "").strip()
    if not passage or not eid:
        return None
    return EvidenceRecord(
        evidence_id=eid if eid.startswith("ref_") else f"ref_{eid}", source="reference",
        title=(row.get("source_org") or "Reference").strip(), abstract=passage,
        source_url=(row.get("url") or "").strip() or None, publisher=(row.get("source_org") or "").strip() or None,
        retrieved_at=(row.get("retrieved_at") or "").strip() or None,
        snapshot_sha256=(row.get("snapshot_sha256") or "").strip() or None,
    )


class Recorder:
    """Records retrieval for tune claims. ``retriever`` is an ``EvidenceRetriever``
    (``retrieve(query)``, ``articles(pmids)``); ``references`` a ``ReferenceSearcher``
    or ``None``. Tests inject fakes; the CLI builds the real ones."""

    def __init__(
        self,
        retriever: Any,
        references: Any = None,
        *,
        planner: Optional[QueryPlanner] = None,
        reranker: Optional[Reranker] = None,
        budgets: Budgets = DEFAULT_BUDGETS,
        log: Callable[[str], None] = lambda _m: None,
    ):
        self.retriever = retriever
        self.references = references
        self.planner = planner or QueryPlanner()
        self.reranker = reranker or Reranker()
        self.budgets = budgets
        self.log = log

    def record_claim(self, row: GoldClaimRow, reference_rows: Sequence[dict] = ()) -> ClaimRecording:
        rec = ClaimRecording(key=row.key, claim_text=row.text, claim_kind=row.kind,
                             claim_category=efficacy_category(row.text))
        found: list[EvidenceRecord] = []
        if self.references is not None and row.kind == "fact_of_record":
            try:
                res = self.references.search(row.text)
                found = merge_evidence(found, res.records)
                rec.errors += [f"reference degraded: {e}" for e in getattr(res, "errors", [])][:5]
            except Exception as exc:  # noqa: BLE001 - recorded, as the graph does
                rec.errors.append(f"reference search failed: {type(exc).__name__}: {exc}"[:300])
        for _ in range(self.budgets.max_retrieval_attempts):
            q = self.planner.next_query(row.text, rec.queries)
            if q is None:
                break
            rec.queries.append(q)
            try:
                result = self.retriever.retrieve(q)
            except Exception as exc:  # noqa: BLE001
                rec.errors.append(f"PubMed retrieval failed for {q!r}: {type(exc).__name__}: {exc}"[:300])
                continue
            found = merge_evidence(found, result.records)
        rec.retrieved_total = len(found)
        rec.retrieved = self.reranker.rerank(row.text, found, row.kind).kept

        pmids = [p for p in (_pmid(x) for x in (*row.supporting, *row.contradicting)) if p]
        if pmids:
            try:
                arts = {a.pmid: a for a in self.retriever.articles(pmids)}
            except Exception as exc:  # noqa: BLE001
                arts = {}
                rec.errors.append(f"cited fetch failed: {type(exc).__name__}: {exc}"[:300])
            for p in pmids:
                if p in arts:
                    rec.cited = merge_evidence(rec.cited, [to_evidence(arts[p], "gold-cited")])
                else:
                    rec.cited_missing.append(f"PMID:{p}")
        urls = [x for x in (*row.supporting, *row.contradicting) if not _pmid(x)]
        by_url = {(r.get("url") or "").strip(): r for r in reference_rows}
        for u in urls:
            ref = _reference_record(by_url[u]) if u in by_url else None
            if ref is None:
                rec.cited_missing.append(u)
            else:
                rec.cited = merge_evidence(rec.cited, [ref])
        return rec

    def record(self, tune: TuneSet, *, only: Optional[Sequence[str]] = None,
               existing: Optional[dict] = None) -> dict:
        """Record every in-scope tune claim. Claims in ``existing`` (a previous file's
        ``claims``) are kept without new requests, so an interrupted recording resumes;
        a kept claim whose search failed is recorded again, and its ``claim_category``
        is re-derived (a fixed rule, no request)."""
        refs = tune.reference_passages()
        claims: dict[str, dict] = dict(existing or {})
        for vid in in_scope_video_ids(tune, only):
            for row in tune.videos[vid].claims:
                old = claims.get(row.key)
                if (old is not None and old.get("claim_text") == row.text
                        and not any("failed" in e for e in old.get("errors", []))):
                    claims[row.key] = {**old, "claim_category": efficacy_category(row.text)}
                    continue
                t0 = time.monotonic()
                claims[row.key] = self.record_claim(row, refs.get(row.key, [])).to_json()
                self.log(f"{row.key}: {len(claims[row.key]['retrieved'])} retrieved, "
                         f"{len(claims[row.key]['cited'])} cited ({time.monotonic() - t0:.1f}s)")
        return claims


def git_revision(repo: Optional[Path] = None) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                              check=True).stdout.decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def write_frozen(path: Path, claims: dict, *, golden: str, budgets: Budgets = DEFAULT_BUDGETS) -> None:
    payload = {
        "format": FORMAT,
        "split": "tune",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "golden_source": golden,
        "code_revision": git_revision(),
        "budgets": {"max_retrieval_attempts": budgets.max_retrieval_attempts},
        "claims": dict(sorted(claims.items())),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ loading


@dataclass(frozen=True)
class FrozenEntry:
    key: str
    claim_category: str
    evidence: tuple[EvidenceRecord, ...]
    allow_unsupported: bool
    errors: tuple[str, ...] = ()


def compose(claim_text: str, kind: str, retrieved: Sequence[EvidenceRecord],
            cited: Sequence[EvidenceRecord], reranker: Optional[Reranker] = None,
            cap: int = MAX_EVIDENCE_PER_CLAIM) -> list[EvidenceRecord]:
    """Retrieved + cited, re-scored together, capped, with every cited item kept."""
    if not cited:
        return list(retrieved)[:cap]
    union = merge_evidence(list(retrieved), list(cited))
    cited_keys = {c.pmid or c.evidence_id for c in cited}
    scored = (reranker or Reranker()).score(claim_text, union, kind)
    is_cited = lambda r: (r.pmid or r.evidence_id) in cited_keys  # noqa: E731
    must = [s.record for s in scored if is_cited(s.record)][:cap]
    rest = [s.record for s in scored if not is_cited(s.record)]
    keep_ids = {r.evidence_id for r in must} | {r.evidence_id for r in rest[: max(0, cap - len(must))]}
    return [s.record for s in scored if s.record.evidence_id in keep_ids]


class FrozenEvidence:
    def __init__(self, data: dict, mode: str = DEFAULT_MODE):
        if data.get("format") != FORMAT:
            raise FrozenEvidenceError(f"not a frozen-evidence file (format {data.get('format')!r}, want {FORMAT!r})")
        if data.get("split") != "tune":
            raise FrozenEvidenceError("frozen evidence must be recorded from the tune split")
        if mode not in MODES:
            raise FrozenEvidenceError(f"unknown evidence mode {mode!r}; use one of {MODES}")
        self.mode = mode
        self.meta = {k: v for k, v in data.items() if k != "claims"}
        self.claims: dict[str, dict] = data.get("claims") or {}
        self._reranker = Reranker()

    @classmethod
    def load(cls, path: Path, mode: str = DEFAULT_MODE) -> "FrozenEvidence":
        try:
            data = json.loads(Path(path).read_text())
        except FileNotFoundError:
            raise FrozenEvidenceError(f"frozen evidence file not found: {path}") from None
        return cls(data, mode)

    def entry(self, key: str, claim_text: Optional[str] = None) -> FrozenEntry:
        raw = self.claims.get(key)
        if raw is None:
            raise FrozenEvidenceError(
                f"claim {key} has no frozen evidence; record retrieval first (freeze-evidence)")
        if claim_text is not None and raw.get("claim_text") != claim_text:
            raise FrozenEvidenceError(f"claim {key} text changed since the evidence was recorded")
        retrieved = [EvidenceRecord.model_validate(r) for r in raw.get("retrieved", [])]
        cited = [EvidenceRecord.model_validate(r) for r in raw.get("cited", [])]
        evidence = retrieved if self.mode == "retrieved" else compose(
            raw.get("claim_text", ""), raw.get("claim_kind") or "research_question", retrieved, cited, self._reranker)
        # As in the graph (routing.retrieval_incomplete): any search error, including a
        # degraded reference source, makes the claim ineligible for UNSUPPORTED.
        errors = tuple(e for e in raw.get("errors", []) if not e.startswith("cited"))
        category = raw.get("claim_category") or "other"
        return FrozenEntry(
            key=key, claim_category=category, evidence=tuple(evidence),
            allow_unsupported=category in UNPROVEN_CATEGORIES and not errors, errors=errors,
        )

    def keys(self) -> Iterable[str]:
        return self.claims.keys()
