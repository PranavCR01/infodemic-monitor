"""T70 gate harness: replay production fixtures with claim context off and on, offline.

No model or network calls. What is REAL code and what is MOCKED:

- REAL: the extractor node's prompt, tool schema, parsing, claim grounding, context
  grounding (ungrounded items dropped) and topic grounding; the query planner (rules);
  the verifier node's prompt, tool schema, parsing, citation checks, T49/T64 guards and
  the T70 code derivation (setting_match, softened_by_context, T69's mismatch code,
  universal-scope guardrail); the judge (§9) and the review policy (§11).
- RECORDED: every claim's text, sources, stance and kept evidence, and every verdict,
  explanation and citation, from the production rows in the fixture.
- MOCKED (hand-written, so they show what the code does with such a reply, never what a
  model would reply): the extract_v5 context items and video topic, and the verify_v4
  structured answers (``evidence_context``, ``contradicted_as_stated``) and, per
  scenario, the skin claim's verdict as meant.
- NOT RUN: PubMed. The verifier sees the evidence production kept; the context rungs the
  planner adds are recorded but not searched.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

from app.core.graph import claims as cl
from app.core.graph import judge as jg
from app.core.graph import review_policy as rp
from app.core.graph import routing as rt
from app.core.graph import verifier as vf
from app.core.graph.claim_context import planner_hint
from app.core.graph.state import (
    EvidenceRecord,
    FusedSegment,
    GraphClaim,
    OcrSegment,
    Stance,
    StanceResult,
    TranscriptSegment,
    initial_state,
)
from app.core.graph.validation import validate
from app.core.retrieval.planning import QueryPlanner

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
V135 = {job: FIXTURES / f"prod_{job}" / "benzene_v135.real.json" for job in ("cf2ea579", "f85f2daa", "008c97a3")}
VITAMIN_K = {"5cc07f48": FIXTURES / "prod_5cc07f48" / "vitamin_k_job.real.json",
             "d2bf4179": FIXTURES / "prod_d2bf4179" / "vitamin_k_rerun.real.json"}
SKIN = "Benzene doesn't get through skin easily"


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


# ------------------------------------------------------------------ fixture -> pieces


def _types(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        out = ast.literal_eval(raw or "[]")
    except (ValueError, SyntaxError):
        return []
    return [str(x) for x in out] if isinstance(out, (list, tuple)) else []


def evidence_of(c: dict) -> list[EvidenceRecord]:
    out = []
    for e in c.get("evidence") or []:
        year = e.get("year")
        out.append(EvidenceRecord(
            evidence_id=e.get("evidence_id") or f"ev_{e['pmid']}", source=e.get("source") or "pubmed",
            pmid=e.get("pmid"), title=e.get("title") or "", abstract=e.get("abstract") or "",
            publication_year=int(year) if year and str(year).isdigit() else None,
            publication_type=_types(e.get("publication_type")), study_type=e.get("study_type") or None))
    return out


def stored_answer(c: dict) -> Optional[dict]:
    """The stored verdict as the verifier's answer (None: nothing kept, no model call)."""
    ev = evidence_of(c)
    if not ev:
        return None
    rel = lambda x: [r.evidence_id for r, e in zip(ev, c["evidence"]) if e.get("relation") == x]  # noqa: E731
    return {"verdict": c["verdict"], "supporting_evidence_ids": rel("SUPPORTS"),
            "contradicting_evidence_ids": rel("CONTRADICTS"), "explanation": c.get("explanation") or "",
            "limitations": [x for x in (c.get("limitations") or []) if x != "no evidence was retrieved for this claim"],
            "raw_confidence": c.get("raw_confidence") if c.get("raw_confidence") is not None else 0.6}


def segments(fx: dict) -> tuple[list[TranscriptSegment], list[OcrSegment], list[FusedSegment], dict[str, str]]:
    """Transcript, OCR and a 1:1 fused timeline (one block per piece; the production
    fusion merged some, which only changes block grouping). Returns piece -> block ID."""
    ts = [TranscriptSegment(segment_id=t["segment_id"], start=float(t["start_seconds"]),
                            end=float(t["end_seconds"]), text=t["text"]) for t in fx.get("transcript_segments") or []]
    os_ = [OcrSegment(segment_id=o["segment_id"], start=float(o["start_seconds"]), end=float(o["end_seconds"]),
                      text=o["text"], confidence=float(o.get("confidence") or 1.0)) for o in fx.get("ocr_segments") or []]
    fused, block = [], {}
    for i, t in enumerate(ts, start=1):
        fused.append(FusedSegment(segment_id=f"f{i}", start=t.start, end=t.end, spoken=t.text, sources=[t.segment_id]))
        block[t.segment_id] = f"f{i}"
    for j, o in enumerate(os_, start=len(ts) + 1):
        fused.append(FusedSegment(segment_id=f"f{j}", start=o.start, end=o.end, on_screen=[o.text],
                                  sources=[o.segment_id]))
        block[o.segment_id] = f"f{j}.screen1"
    return ts, os_, fused, block


def sources_of(fx: dict, c: dict) -> list[str]:
    """The claim's stored source pieces; for fixtures exported without them (the vitamin
    K jobs), the transcript segments its time span overlaps."""
    known = {t["segment_id"] for t in fx.get("transcript_segments") or []} | {
        o["segment_id"] for o in fx.get("ocr_segments") or []}
    src = [s for s in (c.get("source_segment_ids") or []) if s in known]
    if src:
        return src
    a, b = float(c["start_seconds"]), float(c["end_seconds"])
    return [t["segment_id"] for t in fx.get("transcript_segments") or []
            if float(t["start_seconds"]) < b - 1e-6 and float(t["end_seconds"]) > a + 1e-6]


def stored_claims(fx: dict) -> list[GraphClaim]:
    out = []
    for c in fx["claims"]:
        src = sources_of(fx, c) or [f"t_{c['claim_id']}"]
        out.append(GraphClaim(claim_id=c["claim_id"], claim_text=c["text"], claim_category=c["category"],
                              claim_kind=c.get("claim_kind") or "research_question", source_segment_ids=src,
                              start_seconds=float(c["start_seconds"]), end_seconds=float(c["end_seconds"]),
                              requires_verification=c.get("requires_verification", True)))
    return out


# ------------------------------------------------------------------ mocked model callers


class MockExtractor:
    """Answers extract_claims with a fixed reply and records the requests."""

    def __init__(self, reply: dict, version: str):
        self.reply, self.version, self.requests = reply, version, []

    def route(self, step):
        return SimpleNamespace(prompt=self.version)

    def call(self, step, input, *, system=None):
        self.requests.append({"input": input, "system": system})
        return SimpleNamespace(output=self.reply, record=SimpleNamespace(model="mock", prompt_version=self.version))


class RecordedVerifier:
    """Answers verify_claims per claim ID from a table; records the requests."""

    def __init__(self, answers: dict[str, dict], version: str):
        self.answers, self.version, self.requests = answers, version, []

    def route(self, step):
        return SimpleNamespace(prompt=self.version)

    def call(self, step, input, *, system=None):
        cid = re.search(r"Judge claim (\S+) ", input["messages"][0]["content"]).group(1)
        self.requests.append({"claim_id": cid, "input": input, "system": system})
        return SimpleNamespace(output=self.answers[cid], record=SimpleNamespace(model="recorded",
                                                                                 prompt_version=self.version))


def extract_reply(fx: dict, block: dict[str, str], contexts: dict[str, dict],
                  topic: Optional[dict] = None) -> dict:
    """An extract_v5 reply: every stored claim verbatim with its stored sources (as
    blocks), plus the given ``contexts`` (claim text -> context with piece IDs) and topic."""
    def blocks(ids):
        return list(dict.fromkeys(block[i] for i in ids if i in block))

    def item(x):
        return {"text": x["text"], "source_segment_ids": blocks(x["segment_ids"])}

    claims = []
    for c in fx["claims"]:
        src = blocks(sources_of(fx, c))
        if not src:
            continue
        entry = {"claim_text": c["text"], "claim_category": c["category"], "source_segment_ids": src,
                 "claim_kind": c.get("claim_kind") or "research_question"}
        spec = contexts.get(c["text"])
        if spec is not None:
            ctx = {"scope": spec.get("scope", "specific")}
            for f in ("subject", "exposure", "amount", "population", "outcome"):
                if f in spec:
                    ctx[f] = item(spec[f])
            entry["context"] = ctx
        claims.append(entry)
    out: dict = {"claims": claims}
    if topic is not None:
        out["video_topic"] = item(topic)
    return out


# ------------------------------------------------------------------ one run


@dataclass
class Run:
    label: str
    basis: str
    rule: str
    deciding_text: list[str]
    review: bool
    reasons: list[str]
    verdicts: dict[str, str]  # claim text -> verdict
    limitations: dict[str, list[str]] = field(default_factory=dict)
    contexts: dict[str, dict] = field(default_factory=dict)
    topic: Optional[str] = None
    plans: dict[str, list[dict]] = field(default_factory=dict)
    extract_requests: list[dict] = field(default_factory=list)
    verify_requests: list[dict] = field(default_factory=list)
    dropped_claims: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {"label": self.label, "basis": self.basis, "rule": self.rule, "deciding": self.deciding_text,
                "review": self.review, "reasons": self.reasons}


def judge_and_route(state: dict) -> dict:
    final, _ = jg.judge(state)
    state = {**state, "final_result": final}
    state["validation_errors"] = [str(i) for i in validate(state)]
    state["validation_attempts"] = 1
    decision = rp.evaluate(state)
    return {"final": final, "review": decision.requires_review, "reasons": list(decision.reasons)}


def run(fx: dict, *, flag_on: bool, contexts: Optional[dict[str, dict]] = None, topic: Optional[dict] = None,
        answer_for: Optional[Callable[[dict, GraphClaim, Optional[dict], bool], Optional[dict]]] = None) -> Run:
    """One replay. ``answer_for(fixture_claim, claim, stored_answer, in_context)`` may
    rewrite a claim's verifier answer (mocked scenarios); by default the stored answer,
    plus ``evidence_context: matches`` and, in context, ``contradicted_as_stated`` = the
    stored verdict is CONTRADICTED (the answer that changes nothing)."""
    old = rt.CLAIM_CONTEXT
    rt.CLAIM_CONTEXT = flag_on
    try:
        return _run(fx, flag_on, contexts or {}, topic, answer_for)
    finally:
        rt.CLAIM_CONTEXT = old


def _run(fx, flag_on, contexts, topic, answer_for) -> Run:
    ts, os_, fused, block = segments(fx)
    by_text = {c["text"]: c for c in fx["claims"]}
    s = initial_state(job_id=fx.get("job_id_prefix", "fx"), video_id="v", media_uri="mem://v", pipeline_version="t70")
    s.update(transcript_segments=ts, ocr_segments=os_, fused_segments=fused)
    extract_requests: list[dict] = []
    if flag_on:
        caller = MockExtractor(extract_reply(fx, block, contexts, topic), "extract_v5")
        out = cl.make_extract_claims(caller, prompt_version="extract_v5")(s)
        extract_requests = caller.requests
        s.update({k: v for k, v in out.items() if k != "errors"})
        s["errors"] = list(out.get("errors") or [])
    else:
        s["claims"] = stored_claims(fx)
    claims = s["claims"]
    dropped = sorted(set(by_text) - {c.claim_text for c in claims})
    fxc = {c.claim_id: by_text[c.claim_text] for c in claims}
    s["stance_results"] = {cid: StanceResult(claim_id=cid, stance=Stance(c["stances"][0]["stance"]),
                                             stance_segment_ids=list(c["stances"][0].get("segment_ids") or []))
                           for cid, c in fxc.items() if c.get("stances")}
    ev = {cid: evidence_of(c) for cid, c in fxc.items()}
    s.update(retrieved_evidence=ev, reranked_evidence=ev,
             retrieval_attempts={cid: int(c.get("retrieval_attempts") or 1) for cid, c in fxc.items()})
    # Planner (real rules), with the claim's grounded context when the switch is on.
    from app.core.graph.claim_context import context_of

    planner, plans = QueryPlanner(), {}
    for c in claims:
        hint = planner_hint(context_of(s, c.claim_id)) if flag_on else ()
        p = planner.plan(c.claim_text, claim_kind=c.claim_kind, context=[x.claim_text for x in claims],
                         claim_context=hint)
        plans[c.claim_text] = [{"kind": r.kind, "query": r.query} for r in p.rungs]
    # Verifier (real node, recorded / mocked answers).
    answers = {}
    for c in claims:
        a = stored_answer(fxc[c.claim_id])
        in_ctx = flag_on and context_of(s, c.claim_id) is not None
        if a is not None and flag_on:
            a = {**a, "evidence_context": "matches"}
            if in_ctx:
                a["contradicted_as_stated"] = a["verdict"] == "CONTRADICTED"
        if answer_for is not None:
            a = answer_for(fxc[c.claim_id], c, a, in_ctx)
        if a is not None:
            answers[c.claim_id] = a
    verifier = RecordedVerifier(answers, "verify_v4" if flag_on else "verify_v3")
    out = vf.make_verify_claims(verifier, prompt_version="verify_v4" if flag_on else "verify_v3")(s)
    s.update(verification_results=out["verification_results"], verification_revisions=out["verification_revisions"])
    s["errors"] = [*s.get("errors", []), *(out.get("errors") or [])]
    jr = judge_and_route(s)
    final = jr["final"]
    text = {c.claim_id: c.claim_text for c in claims}
    vr = s["verification_results"]
    return Run(
        label=final.classification.value, basis=final.misinfo_basis or "", rule=final.decision_rule or "",
        deciding_text=[text[c] for c in final.claim_ids], review=jr["review"], reasons=jr["reasons"],
        verdicts={text[cid]: v.verdict.value for cid, v in vr.items()},
        limitations={text[cid]: list(v.limitations) for cid, v in vr.items()},
        contexts={text[cid]: x.model_dump() for cid, x in (s.get("claim_contexts") or {}).items()},
        topic=s["video_topic"].text if s.get("video_topic") else None, plans=plans,
        extract_requests=extract_requests, verify_requests=verifier.requests, dropped_claims=dropped)


def stored_replay(fx: dict) -> dict:
    """The fixture's stored verdicts and critic reviews straight into the judge (as shipped
    today): reproduces the production label."""
    from app.core.graph.state import CriticDecision, CriticResult, VerificationResult, Verdict

    s = initial_state(job_id="fx", video_id="v", media_uri="mem://v", pipeline_version="t70")
    ts, os_, fused, _ = segments(fx)
    claims = stored_claims(fx)
    s.update(transcript_segments=ts, ocr_segments=os_, fused_segments=fused, claims=claims)
    s["stance_results"] = {c["claim_id"]: StanceResult(claim_id=c["claim_id"], stance=Stance(c["stances"][0]["stance"]),
                                                       stance_segment_ids=list(c["stances"][0].get("segment_ids") or []))
                           for c in fx["claims"] if c.get("stances")}
    ev = {c["claim_id"]: evidence_of(c) for c in fx["claims"]}
    vr, critics, rev = {}, {}, {}
    for c in fx["claims"]:
        a = stored_answer(c) or {"verdict": c["verdict"], "supporting_evidence_ids": [],
                                 "contradicting_evidence_ids": [], "explanation": c.get("explanation") or "",
                                 "limitations": list(c.get("limitations") or [])}
        vr[c["claim_id"]] = VerificationResult(claim_id=c["claim_id"], verdict=Verdict(a["verdict"]),
                                               supporting_evidence_ids=a["supporting_evidence_ids"],
                                               contradicting_evidence_ids=a["contradicting_evidence_ids"],
                                               explanation=a["explanation"], limitations=list(c.get("limitations") or []))
        rev[c["claim_id"]] = int(c.get("revisions") or 0)
        for cr in c.get("critic_reviews") or []:
            critics[c["claim_id"]] = CriticResult(claim_id=c["claim_id"], decision=CriticDecision(cr["decision"]),
                                                  issues=list(cr.get("issues") or []),
                                                  requires_review=bool(cr.get("requires_review")),
                                                  reviewed_attempt=int(c.get("retrieval_attempts") or 1),
                                                  reviewed_revision=rev[c["claim_id"]])
    s.update(retrieved_evidence=ev, reranked_evidence=ev, verification_results=vr, critic_results=critics,
             verification_revisions=rev,
             retrieval_attempts={c["claim_id"]: int(c.get("retrieval_attempts") or 1) for c in fx["claims"]})
    jr = judge_and_route(s)
    f = jr["final"]
    text = {c.claim_id: c.claim_text for c in claims}
    return {"label": f.classification.value, "basis": f.misinfo_basis or "", "rule": f.decision_rule or "",
            "deciding": [text[c] for c in f.claim_ids], "review": jr["review"], "reasons": jr["reasons"]}


# ------------------------------------------------------------------ the mocked context (v135)


def v135_context(fx: dict) -> tuple[dict[str, dict], dict]:
    """The hand-written extract_v5 context for the skin claim and the video topic, built
    only from segments that exist in this fixture (cf2ea579 / f85f2daa have no OCR), plus
    one deliberately ungrounded item (dropped by code) and one universal claim."""
    ocr = {o["segment_id"]: o["text"] for o in fx.get("ocr_segments") or []}
    skin = {"scope": "specific"}
    if "o10" in ocr and "Benzoyl peroxide" in ocr["o10"]:
        skin["subject"] = {"text": "Benzoyl peroxide", "segment_ids": ["o10"]}
        skin["exposure"] = {"text": "1 application = 0.5-1.0 g (1-2 finger tip units)", "segment_ids": ["o10"]}
        skin["amount"] = {"text": "10-20 µg in 1 application of 20 ppm product", "segment_ids": ["o10"]}
    else:
        skin["subject"] = {"text": "acne products", "segment_ids": ["t1"]}
        skin["amount"] = {"text": "a few might have about 20 parts per million", "segment_ids": ["t6"]}
    # Not in the cited segment: code must drop it.
    skin["population"] = {"text": "teenagers using prescription retinoids", "segment_ids": ["t18"]}
    contexts = {SKIN: skin}
    for c in fx["claims"]:
        if c["text"].startswith("it is a known carcinogen"):
            contexts[c["text"]] = {"scope": "universal"}
    topic = {"text": "how much benzene acne products give off compared to other sources",
             "segment_ids": ["t1", "t17"]}
    return contexts, topic


def skin_scenario(name: str):
    """Mocked verify_v4 answers for the skin claim. Other claims keep their stored answer."""
    def answer_for(fc: dict, claim: GraphClaim, a: Optional[dict], in_ctx: bool) -> Optional[dict]:
        if a is None or claim.claim_text != SKIN:
            return a
        con = a["contradicting_evidence_ids"]
        if name == "as_meant":  # judged as meant: the reviews test another exposure
            return {**a, "verdict": "INSUFFICIENT_EVIDENCE", "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": [],
                    "explanation": "The reviews study occupational solvent exposure of the skin, not one thin "
                                   "layer of an acne cream with a few ppm benzene; nothing tests that.",
                    "evidence_context": "different_exposure_setting", "contradicted_as_stated": True}
        if name == "contradicted_flagged":  # still CONTRADICTED, setting flagged
            return {**a, "verdict": "CONTRADICTED", "contradicting_evidence_ids": con,
                    "evidence_context": "different_exposure_setting", "contradicted_as_stated": True}
        if name == "ignores_context":  # the failure mode: context read but not applied
            return {**a, "verdict": "CONTRADICTED", "contradicting_evidence_ids": con,
                    "evidence_context": "matches", "contradicted_as_stated": True}
        raise ValueError(name)
    return answer_for


SCENARIOS = ("as_meant", "contradicted_flagged", "ignores_context")

VAGUE = "vitamin K is a vitamin that helps prevent a potentially devastating condition"


def vitamin_k_context(fx: dict) -> tuple[dict[str, dict], dict]:
    """Hand-written extract_v5 context for the vague vitamin K claim (T64(d)'s case): the
    condition and population the video states elsewhere."""
    contexts = {VAGUE: {"scope": "specific",
                        "outcome": {"text": "potentially life threatening bleeding", "segment_ids": ["t1", "t2"]},
                        "population": {"text": "newborn babies", "segment_ids": ["t1"]}}}
    topic = {"text": "newborn babies suffering bleeding because fewer parents give a vitamin K injection",
             "segment_ids": ["t1", "t2", "t3"]}
    return contexts, topic
