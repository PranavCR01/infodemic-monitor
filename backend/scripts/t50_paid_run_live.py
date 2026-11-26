"""The T50 paid run (``t50_paid_runs.py run --live --max-usd``). Never run by the build.

The only T50 module that builds real provider clients. Keys are read from the
environment at call time by ``routing_experiment.experiment.default_client_factory``
and handed to the SDKs; they are never printed, logged or written.

For each claim: plan with the search assistant and translator (capped), search live
PubMed for the full budget, rerank, then the find-the-study step where the rules say
it fires (forced on c2-c5 for the vitamin K target). Writes a record in the
``t50_search_recall.py`` format plus the plan, find-the-study outcome and spend.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.graph.retrieval_nodes import _find_study_reason  # noqa: E402
from app.core.graph.state import GraphClaim  # noqa: E402
from app.core.retrieval.assist import ModelSearchAssistant, ModelTranslator  # noqa: E402
from app.core.retrieval.crossref import CrossrefClient  # noqa: E402
from app.core.retrieval.find_study import FindStudyStep, StudyVerifier, WebStudyFinder  # noqa: E402
from app.core.retrieval.planning import QueryPlanner  # noqa: E402
from app.core.retrieval.pubmed import PubMedClient  # noqa: E402
from app.core.retrieval.rerank import Reranker  # noqa: E402
from app.core.retrieval.retriever import EvidenceRetriever, merge_evidence  # noqa: E402
from app.core.routing.config import load_routing  # noqa: E402
from app.core.routing.router import ModelRouter  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from t50_paid_runs import FORCED_FIND_STUDY, VITK, BudgetExceeded, CappedCaller  # noqa: E402


def _claims(target: str) -> list[dict]:
    if target == "vitamin_k":
        sys.path.insert(0, str(HERE.parent))
        from app.tests.vitamin_k_fixture import claims_as_job

        job = {"claims": claims_as_job(json.loads(VITK.read_text()))}
        ctx = [c["text"] for c in job["claims"]]
        return [{"key": c["claim_id"], "text": c["text"], "kind": c["claim_kind"], "context": ctx,
                 "golden_cited": [], "force": c["claim_id"] in FORCED_FIND_STUDY} for c in job["claims"]]
    from app.evaluation.routing_experiment.golden import DirSource, TuneSet

    tune = TuneSet(DirSource(HERE.parents[1] / "research" / "claim-level" / "dataset"))  # tune split only
    out = []
    for vid in tune.video_ids:
        ctx = [c.text for c in tune.videos[vid].claims]
        for row in tune.videos[vid].claims:
            out.append({"key": row.key, "text": row.text, "kind": row.kind, "context": ctx,
                        "golden_cited": [*row.supporting, *row.contradicting], "force": False})
    return out


def run_live(target: str, max_usd: float, out: Path) -> None:  # pragma: no cover - paid path
    from app.evaluation.routing_experiment.experiment import default_client_factory

    router = ModelRouter(load_routing(), default_client_factory())
    caller = CappedCaller(router, max_usd)
    planner = QueryPlanner(assistant=ModelSearchAssistant(caller), translator=ModelTranslator(caller))
    pubmed = PubMedClient()
    retriever = EvidenceRetriever(pubmed)
    finder = WebStudyFinder(caller)

    def capped_finder(text, cue):
        ans = finder(text, cue)
        caller.add_fee(ans.web_searches * 0.01)
        return ans

    step = FindStudyStep(capped_finder, StudyVerifier(pubmed, CrossrefClient()))
    reranker = Reranker()
    claims_out, stopped = {}, None

    def _write() -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"split": "tune" if target == "tune" else "vitamin_k_fixture", "rounds": 3,
                                   "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   "spent_usd": round(caller.spent, 4), "cap_usd": max_usd, "stopped": stopped,
                                   "calls": [r.model_dump() for r in router.records], "claims": claims_out},
                                  ensure_ascii=False))

    try:
        _run_claims(target, planner, retriever, step, reranker, claims_out)
    except _Stop as exc:
        stopped = str(exc)
    except Exception as exc:  # noqa: BLE001 - keep what was paid for; the record says why it stopped
        stopped = f"crashed: {type(exc).__name__}: {exc}"[:300]
    _write()
    print(f"spent {caller.spent:.4f} USD of {max_usd}; {len(claims_out)} claims; stopped: {stopped}")


class _Stop(Exception):
    pass


def _run_claims(target, planner, retriever, step, reranker, claims_out) -> None:  # pragma: no cover - paid path
    stopped = None
    for c in _claims(target):
        t0 = time.perf_counter()
        try:
            plan = planner.plan(c["text"], claim_kind=c["kind"], context=c["context"])
        except BudgetExceeded as exc:
            raise _Stop(str(exc)) from exc
        evidence, rounds, already = [], [], []
        for i in range(1, 4):
            q = planner.next_query(c["text"], already, plan=plan)
            if q is None:
                rounds.append({"round": i, "stopped": "ladder_exhausted"})
                break
            already.append(q)
            try:
                res = retriever.retrieve(q)
            except Exception as exc:  # noqa: BLE001 - as in record(): one failed round never stops the run
                rounds.append({"round": i, "query": q, "error": type(exc).__name__})
                continue
            evidence = merge_evidence(evidence, res.records)
            rounds.append({"round": i, "query": q, "hits": res.pmids_found, "ids": [r.evidence_id for r in res.records]})
        kept = reranker.rerank(c["text"], evidence, c["kind"]).kept if evidence else []
        gc = GraphClaim(claim_id="c", claim_text=c["text"], claim_category="other", source_segment_ids=["s"],
                        start_seconds=0, end_seconds=1)
        reason = "forced" if c["force"] else _find_study_reason(gc, kept, tuple(c["context"]), planner)
        study = None
        if reason:
            res = step.run(c["text"], reason)
            if res.error == "BudgetExceeded":
                stopped = "budget"
            kept = merge_evidence(res.records, kept)[:10]
            evidence = merge_evidence(evidence, res.records)
            study = {"reason": reason, "web_queries": res.web_queries, "web_searches": res.web_searches,
                     "candidates": [x.to_json() for x in res.candidates], "cost_usd": res.cost_usd,
                     "latency_ms": res.latency_ms, "error": res.error}
        claims_out[c["key"]] = {
            "text": c["text"], "kind": c["kind"], "golden_cited": c["golden_cited"], "plan": plan.describe(),
            "rounds": rounds, "find_study": study, "latency_ms": int((time.perf_counter() - t0) * 1000),
            "records": {r.evidence_id: {"title": r.title, "abstract": r.abstract[:3000], "pmid": r.pmid,
                                        "year": r.publication_year} for r in evidence},
            "kept": [r.evidence_id for r in kept]}
        if stopped:
            raise _Stop(stopped)
