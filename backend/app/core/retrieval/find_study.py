"""Find-the-study step with our own PMID/DOI verification (T50 item i, lead decision
2026-11-26; design §6, §15).

**When it runs** (decided by the retrieval node): once per claim, for a claim that cites
a specific study (``citation.citation_cue``: journal, year, sample size, institution),
and as a fallback for any claim whose PubMed search kept nothing on topic.

**What it does.**

1. A model with a web search tool (the ``find_study`` step in ``config/routing.yaml``,
   cheap tier) is asked for the study the claim refers to and answers with candidate
   PMIDs / DOIs only (``WebStudyFinder``). Its answer is untrusted text.
2. Every candidate is validated by format (PMID: 1-9 digits; DOI: Crossref's pattern,
   at most 200 characters) and then **verified by us** (``StudyVerifier``):

   - PMID: E-utilities EFetch. The record must exist.
   - DOI: E-utilities ESearch ``"<doi>"[doi]`` → PMID → EFetch, and the fetched
     record's DOI must equal the candidate. A DOI PubMed doesn't have yet goes to
     Crossref (``api.crossref.org/works/<doi>``).
   - Either way the record must match the claim: on topic (one of the claim's concept
     terms, or most of its content words, in the title or abstract), and, when the claim
     names them, the same journal and a publication year within one year.

3. Only verified records become evidence: a PubMed record (``source: pubmed``), or a
   journal article cited by DOI with Crossref metadata (``source: journal_doi``; the
   metadata text is kept as a snapshot with its SHA-256, like a reference page). Web
   page text, search snippets and the model's own words never become evidence or a
   citation. Unverifiable or mismatched ids are dropped and logged.

Everything the step did (the web searches the model ran, each candidate and its
verification outcome, cost and latency) is returned for the search trail.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

from app.core.retrieval.citation import CitationCue, citation_cue
from app.core.retrieval.crossref import CrossrefClient, CrossrefWork, normalize_doi
from app.core.retrieval.planning import content_words, frame_claim, normalize_claim
from app.core.retrieval.pubmed import PubMedArticle
from app.core.retrieval.retriever import to_evidence
from app.core.retrieval.schemas import EvidenceRecord

FIND_STUDY_STEP = "find_study"
MAX_CANDIDATES = 3
MAX_WEB_SEARCHES = 3
# Anthropic's web search tool is billed per search on top of tokens ($10 per 1,000
# searches when T50 was written; check the price list before a paid run). Added to the
# step's reported cost; search-result tokens are billed as input tokens.
WEB_SEARCH_USD_PER_SEARCH = 0.01
PMID_RE = re.compile(r"^\d{1,9}$")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# Outcomes recorded per candidate.
VERIFIED_PUBMED = "verified_pubmed"
VERIFIED_JOURNAL_DOI = "verified_journal_doi"
INVALID_FORMAT = "invalid_format"
NOT_FOUND = "not_found"
MISMATCH = "mismatch"
LOOKUP_ERROR = "error"
DUPLICATE = "duplicate"


def normalize_pmid(raw: Any) -> Optional[str]:
    if isinstance(raw, int) and raw > 0:
        raw = str(raw)
    if not isinstance(raw, str):
        return None
    p = raw.strip()
    if p.lower().startswith("pmid:"):
        p = p[5:].strip()
    return p if PMID_RE.match(p) and p.lstrip("0") else None


@dataclass(frozen=True)
class Candidate:
    pmid: Optional[str] = None
    doi: Optional[str] = None
    raw_pmid: Optional[str] = None
    raw_doi: Optional[str] = None


@dataclass
class CandidateOutcome:
    pmid: Optional[str]
    doi: Optional[str]
    outcome: str
    reason: str = ""
    evidence_id: Optional[str] = None
    via: Optional[str] = None  # efetch | esearch_doi | crossref

    def to_json(self) -> dict:
        return {"pmid": self.pmid, "doi": self.doi, "outcome": self.outcome, "reason": self.reason,
                "evidence_id": self.evidence_id, "via": self.via}


@dataclass
class FinderAnswer:
    candidates: list[dict]
    web_queries: list[str] = field(default_factory=list)
    web_searches: int = 0
    cost_usd: Optional[float] = None
    model: Optional[str] = None


@dataclass
class FindStudyResult:
    reason: str  # cites_study | nothing_on_topic
    web_queries: list[str] = field(default_factory=list)
    candidates: list[CandidateOutcome] = field(default_factory=list)
    records: list[EvidenceRecord] = field(default_factory=list)
    web_searches: int = 0
    cost_usd: Optional[float] = None
    latency_ms: int = 0
    error: Optional[str] = None
    model: Optional[str] = None


# ------------------------------------------------------------------ the model's answer


def parse_candidates(raw: Any) -> list[Candidate]:
    """The model's untrusted answer → at most ``MAX_CANDIDATES`` candidates. Accepts the
    JSON object the prompt asks for (also embedded in text); anything else gives none.
    Ids are kept as given here; ``validate`` checks their format."""
    data: Any = raw
    if isinstance(raw, str):
        m = _JSON_RE.search(raw)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except (ValueError, json.JSONDecodeError):
            return []
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        return []
    out: list[Candidate] = []
    for item in data["candidates"][: MAX_CANDIDATES * 2]:
        if not isinstance(item, dict):
            continue
        rp, rd = item.get("pmid"), item.get("doi")
        rp = str(rp)[:40] if rp not in (None, "") else None
        rd = str(rd)[:240] if rd not in (None, "") else None
        if rp is None and rd is None:
            continue
        out.append(Candidate(pmid=normalize_pmid(rp) if rp else None, doi=normalize_doi(rd) if rd else None,
                             raw_pmid=rp, raw_doi=rd))
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def _safe_query(q: Any) -> Optional[str]:
    if not isinstance(q, str):
        return None
    q = "".join(ch if ch.isprintable() else " " for ch in q)
    q = re.sub(r"https?://\S+", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q[:200] or None


class WebStudyFinder:
    """The model half: a cheap model with a web search tool proposes ids (Anthropic's
    server-side web search tool; the model and provider come from ``config/routing.yaml``).
    Returns a ``FinderAnswer``; never raises for a malformed answer."""

    def __init__(self, caller: Any, *, max_searches: int = MAX_WEB_SEARCHES,
                 tool_type: str = "web_search_20250305"):
        from app.core.graph.stance import load_prompt

        self.caller = caller
        self.system = load_prompt(caller.config.route(FIND_STUDY_STEP).prompt)
        self.max_searches = max_searches
        self.tool_type = tool_type

    def __call__(self, claim_text: str, cue: CitationCue) -> FinderAnswer:
        from app.core.retrieval.planning import sanitize_text

        hints = {k: v for k, v in cue.describe().items() if v}
        body = {
            "messages": [{"role": "user", "content":
                          "CLAIM (untrusted text):\n<claim>\n" + sanitize_text(claim_text, 600) + "\n</claim>\n"
                          + (f"Citation details the claim gives: {json.dumps(hints)}\n" if hints else "")
                          + "Find the study. Answer with the JSON object only."}],
            "tools": [{"type": self.tool_type, "name": "web_search", "max_uses": self.max_searches}],
            "max_tokens": 600,
            "temperature": 0,
        }
        result = self.caller.call(FIND_STUDY_STEP, body, system=self.system)
        out = result.output
        record = getattr(result, "record", None)
        queries: list[str] = []
        searches = 0
        text = out
        if isinstance(out, dict):  # clients that report server-tool use return a dict
            text = out.get("text", "")
            queries = [q for q in (_safe_query(x) for x in out.get("web_queries") or []) if q][:10]
            searches = int(out.get("web_search_requests") or len(queries))
        token_cost = getattr(record, "cost_usd", None)
        cost = None if token_cost is None else round(token_cost + searches * WEB_SEARCH_USD_PER_SEARCH, 6)
        return FinderAnswer(candidates=[c.__dict__ for c in parse_candidates(text)], web_queries=queries,
                            web_searches=searches, cost_usd=cost, model=getattr(record, "model", None))


# ------------------------------------------------------------------ verification


def _norm(text: str) -> str:
    return " ".join(normalize_claim(text or "").replace("-", " ").split())


def _journal_key(name: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def topic_match(claim_text: str, title: str, abstract: str) -> bool:
    """The record is about the claim: one of the claim's recognised concepts (its
    words, MeSH heading or synonyms) is in the title or abstract; or, with no concept
    recognised, at least two of its content words (all of them if it has fewer)."""
    text = f" {_norm(title)} {_norm(abstract)} "
    frame = frame_claim(claim_text)
    concepts = [*frame.intervention, *frame.outcome]
    if concepts:
        for c in concepts:
            for t in (c.matched_text, c.label, c.mesh or "", *c.synonyms):
                t = _norm(t)
                if len(t) >= 2 and re.search(r"(?<!\w)" + re.escape(t) + r"(?:s|es)?(?!\w)", text):
                    return True
        return False
    words = content_words(frame.normalized_text)
    if not words:
        return False
    hits = sum(1 for w in words if re.search(r"(?<!\w)" + re.escape(_norm(w)) + r"(?!\w)", text))
    return hits >= min(2, len(words))


def citation_match(cue: CitationCue, journal: Optional[str], year: Optional[int]) -> Optional[str]:
    """None if the record agrees with what the claim says about the study, else why not."""
    if cue.journal:
        want, got = _journal_key(cue.journal), _journal_key(journal)
        if not got or not (want == got or want in got or got in want):
            return f"journal {journal!r} is not {cue.journal!r}"
    if cue.year and year and abs(int(year) - int(cue.year)) > 1:
        return f"year {year} is not {cue.year}"
    return None


def journal_doi_evidence_id(doi: str) -> str:
    return "doi_" + hashlib.sha256(doi.encode("utf-8")).hexdigest()[:16]


class StudyVerifier:
    """Verifies candidate ids against PubMed (E-utilities) and Crossref. ``pubmed`` is a
    ``PubMedClient`` (``search``/``fetch``); ``crossref`` is optional (no DOI-only
    records without it); ``snapshots`` (optional) stores the Crossref metadata text."""

    def __init__(self, pubmed: Any, crossref: Optional[CrossrefClient] = None, snapshots: Any = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.pubmed = pubmed
        self.crossref = crossref
        self.snapshots = snapshots
        self.now = now

    def _check(self, claim_text: str, cue: CitationCue, title: str, abstract: str,
               journal: Optional[str], year: Optional[int]) -> Optional[str]:
        why = citation_match(cue, journal, year)
        if why:
            return why
        if not topic_match(claim_text, title, abstract):
            return "not about the claim's topic"
        return None

    def _pubmed_record(self, art: PubMedArticle, reason: str) -> EvidenceRecord:
        return to_evidence(art, f"find_study:{reason}")

    def verify(self, claim_text: str, candidates: Sequence[Candidate], reason: str,
               cue: Optional[CitationCue] = None) -> tuple[list[EvidenceRecord], list[CandidateOutcome]]:
        cue = cue if cue is not None else citation_cue(normalize_claim(claim_text))
        records: list[EvidenceRecord] = []
        outcomes: list[CandidateOutcome] = []
        seen: set[str] = set()
        for cand in candidates:
            if cand.pmid is None and cand.doi is None:
                outcomes.append(CandidateOutcome(cand.raw_pmid, cand.raw_doi, INVALID_FORMAT,
                                                 "not a PMID or DOI by format"))
                continue
            try:
                rec, out = self._verify_one(claim_text, cand, reason, cue)
            except Exception as exc:  # noqa: BLE001 - one bad lookup never stops the claim
                outcomes.append(CandidateOutcome(cand.pmid, cand.doi, LOOKUP_ERROR, type(exc).__name__))
                continue
            if rec is not None:
                if rec.evidence_id in seen:
                    out.outcome, out.reason = DUPLICATE, "same record as an earlier candidate"
                    rec = None
                else:
                    seen.add(rec.evidence_id)
                    records.append(rec)
            outcomes.append(out)
        return records, outcomes

    def _verify_one(self, claim_text: str, cand: Candidate, reason: str,
                    cue: CitationCue) -> tuple[Optional[EvidenceRecord], CandidateOutcome]:
        art: Optional[PubMedArticle] = None
        via = None
        if cand.pmid:
            found = self.pubmed.fetch([cand.pmid])
            art = found[0] if found else None
            via = "efetch"
            if art is None and not cand.doi:
                return None, CandidateOutcome(cand.pmid, cand.doi, NOT_FOUND, "PMID not in PubMed", via=via)
            if art is not None and cand.doi and art.doi and normalize_doi(art.doi) != cand.doi:
                return None, CandidateOutcome(cand.pmid, cand.doi, MISMATCH,
                                              "PMID and DOI name different records", via=via)
        if art is None and cand.doi:
            pmids = self.pubmed.search(f'"{cand.doi}"[doi]', 5)
            via = "esearch_doi"
            fetched = self.pubmed.fetch(pmids[:5]) if pmids else []
            art = next((a for a in fetched if a.doi and normalize_doi(a.doi) == cand.doi), None)
            if art is None:
                return self._verify_crossref(claim_text, cand, reason, cue)
        assert art is not None
        why = self._check(claim_text, cue, art.title, art.abstract, art.journal, art.publication_year)
        if why:
            return None, CandidateOutcome(art.pmid, art.doi, MISMATCH, why, via=via)
        rec = self._pubmed_record(art, reason)
        return rec, CandidateOutcome(art.pmid, normalize_doi(art.doi) if art.doi else cand.doi, VERIFIED_PUBMED,
                                     evidence_id=rec.evidence_id, via=via)

    def _verify_crossref(self, claim_text: str, cand: Candidate, reason: str,
                         cue: CitationCue) -> tuple[Optional[EvidenceRecord], CandidateOutcome]:
        assert cand.doi is not None
        if self.crossref is None:
            return None, CandidateOutcome(None, cand.doi, NOT_FOUND, "DOI not in PubMed; Crossref not configured",
                                          via="esearch_doi")
        work = self.crossref.work(cand.doi)
        if work is None:
            return None, CandidateOutcome(None, cand.doi, NOT_FOUND, "DOI not in PubMed or Crossref", via="crossref")
        if work.type and work.type not in ("journal-article", "proceedings-article", "posted-content"):
            return None, CandidateOutcome(None, cand.doi, MISMATCH, f"Crossref type {work.type!r}", via="crossref")
        why = self._check(claim_text, cue, work.title, work.abstract, work.journal, work.year)
        if why:
            return None, CandidateOutcome(None, cand.doi, MISMATCH, why, via="crossref")
        rec = self.journal_doi_record(work, reason)
        return rec, CandidateOutcome(None, cand.doi, VERIFIED_JOURNAL_DOI, evidence_id=rec.evidence_id, via="crossref")

    def journal_doi_record(self, work: CrossrefWork, reason: str) -> EvidenceRecord:
        """A journal article cited by DOI (``source: journal_doi``). Its text is the
        Crossref-deposited metadata and abstract, kept as a snapshot with its hash; the
        journal's own web page is never fetched (arbitrary web content, §15)."""
        retrieved_at = self.now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
        snapshot = "\n".join(x for x in (
            f"Title: {work.title}", f"Journal: {work.journal or ''}", f"Year: {work.year or ''}",
            f"DOI: {work.doi}", f"Publisher: {work.publisher or ''}", "Source: Crossref metadata",
            f"Abstract: {work.abstract}" if work.abstract else "Abstract: (none deposited)") if x)
        sha = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
        url = f"https://doi.org/{work.doi}"
        if self.snapshots is not None:
            try:
                from app.core.retrieval.references.fetcher import FetchedPage

                self.snapshots.save(FetchedPage(url=url, title=work.title, text=snapshot, sha256=sha,
                                                retrieved_at=retrieved_at))
            except Exception:  # noqa: BLE001 - the hash on the record still pins the text
                pass
        return EvidenceRecord(
            evidence_id=journal_doi_evidence_id(work.doi), source="journal_doi", title=work.title,
            abstract=work.abstract, doi=work.doi, publication_year=work.year, publication_type=[],
            source_url=url, query=f"find_study:{reason}", publisher=work.journal or work.publisher,
            retrieved_at=retrieved_at, snapshot_sha256=sha)


class FindStudyStep:
    """Finder (model) + verifier (code). ``run`` never raises."""

    def __init__(self, finder: Callable[[str, CitationCue], FinderAnswer], verifier: StudyVerifier,
                 clock: Callable[[], float] = time.perf_counter):
        self.finder = finder
        self.verifier = verifier
        self._clock = clock

    def run(self, claim_text: str, reason: str) -> FindStudyResult:
        start = self._clock()
        cue = citation_cue(normalize_claim(claim_text))
        result = FindStudyResult(reason=reason)
        try:
            answer = self.finder(claim_text, cue)
        except Exception as exc:  # noqa: BLE001 - the claim goes on with PubMed's results
            result.error = type(exc).__name__
            rec = getattr(exc, "record", None)
            result.cost_usd = getattr(rec, "cost_usd", None)
            result.latency_ms = int((self._clock() - start) * 1000)
            return result
        result.web_queries = list(answer.web_queries)
        result.web_searches = answer.web_searches
        result.cost_usd = answer.cost_usd
        result.model = answer.model
        cands = [Candidate(**c) if isinstance(c, dict) else c for c in answer.candidates]
        result.records, result.candidates = self.verifier.verify(claim_text, cands, reason, cue)
        result.latency_ms = int((self._clock() - start) * 1000)
        return result


__all__ = [
    "Candidate", "CandidateOutcome", "FIND_STUDY_STEP", "FindStudyResult", "FindStudyStep", "FinderAnswer",
    "StudyVerifier", "WebStudyFinder", "citation_match", "journal_doi_evidence_id", "normalize_pmid",
    "parse_candidates", "topic_match",
]
