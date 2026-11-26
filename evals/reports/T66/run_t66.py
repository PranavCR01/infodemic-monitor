"""T66: run the full graph on the golden set's TUNE split through the evaluation runner.

Report-only helper (no product code changes). Three subcommands, run from ``backend/``:

    python ../evals/reports/T66/run_t66.py materialize --out <dir>
        Copies the tune split ONLY (videos.csv/claims.csv rows whose split is "tune",
        their transcripts, reference_citations rows) from the golden-set git ref into
        <dir>. Test-split rows are dropped as the CSVs are read; no test transcript is
        ever read. ``app.evaluation.dataset.load_dataset`` then loads <dir>.

    python ../evals/reports/T66/run_t66.py dryrun --data <dir>
        No model calls. Per-video expected cost and upper bound (see ``estimate``).

    python ../evals/reports/T66/run_t66.py run --data <dir> --max-usd X --order order.json
        PAID. The production graph wiring (``build_graph_provider``'s, with references on
        as in T18, an in-memory snapshot store and no Redis), every provider client wrapped
        in the routing experiment's ``SpendGuard`` (plus the web-search fees of the
        find-the-study step), run by ``app.evaluation.runner.run_evaluation`` over the
        videos in the pre-declared order. Each finished video's full graph state is
        written as soon as it finishes to ``videos/<video_id>.json``.

A video counts as NOT RUN (never as wrong) when the guard refused any call during it,
when the account reported a credit/billing error, or when the budget left before it was
below the per-video reserve. The single-call fallback is NOT called: when the graph
fails, the outcome is recorded with ``pipeline = graph_fallback`` and its reason, and the
report lists those videos separately.

Keys: Anthropic from EVAL_ANTHROPIC_API_KEY (passed to the SDK, never printed or
written); OpenAI through the environment's proxy (a dummy key).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")

GOLDEN_REF = "92a731e7f9548221635c8b9b99e098cbe0e6699a"  # origin/data/golden-label-set at start
GOLDEN_BASE = "research/claim-level/dataset"
ORDER_SEED = 66
VIDEOS_DIR = HERE / "videos"
BILLING_MARKERS = ("credit balance", "billing", "insufficient_quota", "payment")


# ------------------------------------------------------------------ materialize


def _git_show(path: str) -> str:
    return subprocess.run(["git", "show", f"{GOLDEN_REF}:{GOLDEN_BASE}/{path}"], cwd=REPO,
                          capture_output=True, check=True).stdout.decode("utf-8")


def _filter_csv(text: str, keep) -> str:
    reader = csv.DictReader(io.StringIO(text))
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=reader.fieldnames, lineterminator="\n")
    w.writeheader()
    for row in reader:
        if keep(row):
            w.writerow(row)
    return out.getvalue()


def materialize(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    videos_text = _git_show("videos.csv")
    tune = {r["video_id"] for r in csv.DictReader(io.StringIO(videos_text)) if (r.get("split") or "").strip() == "tune"}
    (out / "videos.csv").write_text(_filter_csv(videos_text, lambda r: r["video_id"] in tune))
    del videos_text
    (out / "claims.csv").write_text(_filter_csv(_git_show("claims.csv"), lambda r: r["video_id"] in tune))
    (out / "reference_citations.csv").write_text(
        _filter_csv(_git_show("reference_citations.csv"), lambda r: r.get("video_id") in tune))
    (out / "transcripts").mkdir(exist_ok=True)
    for vid in sorted(tune):
        (out / "transcripts" / f"{vid}.json").write_text(_git_show(f"transcripts/{vid}.json"))
    return {"golden_ref": GOLDEN_REF, "tune_videos": len(tune), "dir": str(out)}


def load_tune(data: Path):
    from app.evaluation.dataset import load_dataset

    ds = load_dataset(data, version=f"golden@{GOLDEN_REF[:7]}+tune-only", name="golden-tune")
    assert all(v.split == "tune" for v in ds.videos + ds.excluded), "non-tune video in the tune copy"
    return ds


def fixed_order(ds) -> list[str]:
    ids = sorted(v.video_id for v in ds.videos)
    random.Random(ORDER_SEED).shuffle(ids)
    return ids


# ------------------------------------------------------------------ dry run


def _tok(chars: int) -> float:
    return chars / 4.0


def estimate(ds) -> dict:
    """Per-video cost, no calls. Token counts are chars/4 (x1.25 for the upper bound,
    the SpendGuard's own input margin). The claim count is the golden claim count for
    the expected figure and max(2x gold, gold+4, 4) for the upper bound (used for
    budgeting only). Expected: every step once, outputs at ~half their cap, find-study on
    half the claims with 2 searches. Upper bound: every cap hit, every repair and the
    critic's revision used (verify x4, critic x4, stance x2, extract x2, judge x2), find-study on
    every claim with 3 searches and 30k tokens of search results."""
    from app.core.routing.config import load_routing

    routing = load_routing()
    price = {k: routing.price(v.model) for k, v in routing.steps.items()}
    prm = BACKEND / "app/core/graph/prompts"
    sys_chars = {s: (prm / f"{routing.route(s).prompt}.md").stat().st_size for s in
                 ("extract_claims", "analyze_stance", "verify_claims", "critique", "judge_explanation", "find_study")}

    def usd(step, tin, tout):
        p = price[step]
        return (tin * p.input + tout * p.output) / 1e6

    rows = {}
    for v in ds.videos:
        fusion = ds.inputs[v.video_id].fusion
        content = len(fusion.combined_content)
        n_gold = len(v.claims)
        n_hi = max(2 * n_gold, n_gold + 4, 4)
        ctx = min(content, 40_000)
        e_in = _tok(sys_chars["extract_claims"] + content + 1500)
        st_in = _tok(sys_chars["analyze_stance"] + ctx + 800)
        ver_in = _tok(sys_chars["verify_claims"] + 10 * 1800 + 1000)
        cr_in = _tok(sys_chars["critique"] + 10 * 1800 + 2500)
        fs_in_exp, fs_in_hi = 12_000, 30_000

        def per_video(n, m, cap_mult, fs_frac, searches, fs_in, judge_in):
            per_claim = (usd("analyze_stance", st_in * m, 512 * cap_mult["stance_out"]) * cap_mult["stance"]
                         + usd("verify_claims", ver_in * m, 1024 * cap_mult["verify_out"]) * cap_mult["verify"]
                         + usd("critique", cr_in * m, 1024 * cap_mult["critic_out"]) * cap_mult["critic"]
                         + fs_frac * (usd("find_study", fs_in, 600) + 0.01 * searches))
            return (usd("extract_claims", e_in * m, 2048 * cap_mult["extract_out"]) * cap_mult["extract"]
                    + n * per_claim + usd("judge_explanation", judge_in * m, 600) * cap_mult["judge"])

        exp = per_video(n_gold, 1.0, {"stance": 1, "verify": 1, "critic": 1, "extract": 1, "judge": 1,
                                      "stance_out": 0.5, "verify_out": 0.6, "critic_out": 0.3, "extract_out": 0.5},
                        0.5, 2, fs_in_exp, _tok(sys_chars["judge_explanation"] + 4000))
        hi = per_video(n_hi, 1.25, {"stance": 2, "verify": 4, "critic": 4, "extract": 2, "judge": 2,
                                    "stance_out": 1, "verify_out": 1, "critic_out": 1, "extract_out": 1},
                       1.0, 3, fs_in_hi, _tok(sys_chars["judge_explanation"] + 8000))
        rows[v.video_id] = {"content_chars": content, "gold_claims": n_gold, "claims_assumed_upper": n_hi,
                            "expected_usd": round(exp, 4), "upper_usd": round(hi, 4)}
    tot_e = sum(r["expected_usd"] for r in rows.values())
    tot_h = sum(r["upper_usd"] for r in rows.values())
    return {"n_videos": len(rows), "total_expected_usd": round(tot_e, 2), "total_upper_usd": round(tot_h, 2),
            "per_video": rows, "routing": routing.versions()}


# ------------------------------------------------------------------ guarded wiring


class StopRun(RuntimeError):
    """Raised by the system to mark a video NOT RUN (budget or billing)."""


def build_system(max_usd: float, already_spent: float):
    from app.core.config import settings
    from app.core.inference.providers.graph_provider import GraphProvider
    from app.core.retrieval.pubmed import PubMedClient, shared_rate_limiter
    from app.core.retrieval.references import ReferenceSearcher, load_reference_config
    from app.core.retrieval.references.snapshots import InMemorySnapshotStore
    from app.core.retrieval.retriever import EvidenceRetriever
    from app.core.routing.clients import default_clients
    from app.core.routing.config import load_routing
    from app.core.routing.router import ModelRouter
    from app.core.routing.version import analysis_version, routing_snapshot
    from app.core.schemas.pipeline import ClassificationResult, MisinfoLabel
    from app.evaluation.records import PredictedClaim, VideoPrediction
    from app.evaluation.routing_experiment.cost import GuardedClient, SpendCapError, SpendGuard, experiment_pricing

    routing = load_routing()
    guard = SpendGuard(cap_usd=max_usd, pricing=experiment_pricing(routing), spent_usd=already_spent)
    flags = {"billing": None}

    class FeeGuardedClient(GuardedClient):
        """SpendGuard plus the find-the-study web-search fee ($0.01/search, reserved at
        max_uses before the call, booked at the reported count after)."""

        def complete(self, model, request):
            if flags["billing"]:
                raise SpendCapError("stopped: the account reported a credit/billing error earlier")
            body = request.input if isinstance(request.input, dict) else {}
            max_fee = 0.01 * sum(int(t.get("max_uses") or 0) for t in body.get("tools") or []
                                 if isinstance(t, dict) and str(t.get("type", "")).startswith("web_search"))
            if max_fee and guard.spent_usd + max_fee > guard.cap_usd:
                guard.refused += 1
                guard.exhausted = True
                raise SpendCapError(f"spend cap: web-search fees could cross ${guard.cap_usd:.2f}")
            try:
                resp = super().complete(model, request)
            except Exception as exc:
                if any(m in str(exc).lower() for m in BILLING_MARKERS):
                    flags["billing"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                raise
            out = resp.output
            if max_fee and isinstance(out, dict):
                fee = 0.01 * int(out.get("web_search_requests") or len(out.get("web_queries") or []))
                guard.spent_usd += fee
                guard.by_model["web_search_fees"] = guard.by_model.get("web_search_fees", 0.0) + fee
            return resp

    clients = default_clients(anthropic_api_key=os.environ["EVAL_ANTHROPIC_API_KEY"],
                              openai_api_key="sk-proxy-injects-the-real-key",
                              timeout=settings.GRAPH_MODEL_TIMEOUT_SECONDS)
    router = ModelRouter(routing, {k: FeeGuardedClient(c, guard) for k, c in clients.items()})
    limiter = shared_rate_limiter(bool(settings.NCBI_API_KEY))
    retriever = EvidenceRetriever(
        PubMedClient(api_key=settings.NCBI_API_KEY, email=settings.NCBI_EMAIL, rate_limiter=limiter),
        None, max_results=settings.RETRIEVAL_MAX_RESULTS_PER_QUERY)
    references = ReferenceSearcher(load_reference_config(), snapshots=InMemorySnapshotStore(), rate_limiter=limiter)

    class NoFallback:
        """The single call is not the system under test: record the fallback, call nothing."""

        def classify(self, fusion):
            return ClassificationResult(label=MisinfoLabel.CANNOT_RECOGNIZE, confidence=0.0,
                                        explanation="graph fell back; single call not run (T66)",
                                        provider="none", model_used="none", latency_ms=0)

    graph = GraphProvider(caller=router, retriever=retriever, fallback=NoFallback(), references=references,
                          timeout_seconds=settings.GRAPH_TIMEOUT_SECONDS,
                          pipeline_version=analysis_version(settings.GRAPH_PIPELINE_VERSION, routing),
                          routing_snapshot=routing_snapshot(routing))

    class GraphSystem:
        name = "graph"

        def __init__(self):
            self.reserve = 0.0  # per-video budget needed before starting (set by caller)
            self.status: dict[str, str] = {}

        def versions(self):
            return {"routing": routing.versions(), "pipeline_version": graph.pipeline_version,
                    "routing_snapshot": graph.routing_snapshot}

        def predict(self, video):
            vid = video.video_id
            if flags["billing"]:
                self.status[vid] = "not_run:billing"
                raise StopRun(f"not run: billing error earlier ({flags['billing']})")
            if guard.exhausted or guard.cap_usd - guard.spent_usd < self.reserve:
                self.status[vid] = "not_run:budget"
                raise StopRun(f"not run: ${guard.cap_usd - guard.spent_usd:.2f} left < reserve ${self.reserve:.2f}")
            spent0, refused0, calls0 = guard.spent_usd, guard.refused, guard.calls
            t0 = time.perf_counter()
            outcome = graph.run(video.fusion, job_id=f"t66-{vid}", video_id=vid)
            latency = int(round((time.perf_counter() - t0) * 1000))
            cost = guard.spent_usd - spent0
            if flags["billing"]:
                status = "not_run:billing"
            elif guard.refused > refused0:
                status = "not_run:budget_mid_video"
            elif outcome.fallback_used:
                status = "graph_fallback"
            else:
                status = "finished"
            self.status[vid] = status
            save_video(vid, outcome, status, cost, latency, guard.calls - calls0)
            write_spend(guard, flags)
            if status.startswith("not_run"):
                raise StopRun(f"{status}: {flags['billing'] or 'guard refused a call'}")
            st = outcome.state or {}
            fr = st.get("final_result")
            verdicts = st.get("verification_results") or {}
            stances = st.get("stance_results") or {}

            def _v(x):
                return None if x is None else str(getattr(x, "value", x))

            try:  # the saved video file is the source of truth; this summary must not lose a paid run
                claims = [PredictedClaim(
                    claim_id=c.claim_id, claim_text=c.claim_text, source_segment_ids=list(c.source_segment_ids),
                    stance=_v(getattr(stances.get(c.claim_id), "stance", None)),
                    verdict=_v(getattr(verdicts.get(c.claim_id), "verdict", None)),
                ) for c in st.get("claims") or []]
            except Exception as exc:  # noqa: BLE001
                print(f"{vid}: claim summary failed ({exc}); see videos/{vid}.json", file=sys.stderr)
                claims = None
            return VideoPrediction(
                video_id=vid, label=outcome.classification.label,
                confidence=outcome.classification.confidence, explanation=outcome.classification.explanation,
                claims=claims, review_required=outcome.requires_human_review,
                review_reasons=list(st.get("review_reasons") or []), latency_ms=latency, cost_usd=round(cost, 6),
                model_calls=list(outcome.model_calls),
                trace=[{"pipeline": outcome.pipeline, "fallback_reason": outcome.fallback_reason,
                        "decision_rule": getattr(fr, "decision_rule", None),
                        "misinfo_basis": getattr(fr, "misinfo_basis", None)}],
                error=None if status == "finished" else f"graph_fallback: {outcome.fallback_reason}",
            )

    return GraphSystem(), guard, flags, routing


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return _jsonable(obj.model_dump(mode="json"))
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "value") and not isinstance(obj, (str, int, float)):
        return obj.value
    return obj


OMIT = ("transcript_segments", "ocr_segments", "fused_segments")  # golden-set text, kept in the golden set


def save_video(vid: str, outcome, status: str, cost: float, latency_ms: int, n_calls: int) -> None:
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    st = dict(outcome.state or {})
    seg_counts = {k: len(st.get(k) or []) for k in OMIT}
    for k in OMIT:
        st.pop(k, None)
    rec = {
        "video_id": vid, "status": status, "pipeline": outcome.pipeline,
        "fallback_reason": outcome.fallback_reason,
        "label": outcome.classification.label.value, "cost_usd": round(cost, 6), "latency_ms": latency_ms,
        "guarded_calls": n_calls, "pipeline_version": outcome.pipeline_version,
        "segment_counts_omitted": seg_counts,
        "model_calls": _jsonable(outcome.model_calls), "state": _jsonable(st),
    }
    (VIDEOS_DIR / f"{vid}.json").write_text(json.dumps(rec, indent=1, default=str))


def write_spend(guard, flags) -> None:
    (HERE / "spend.json").write_text(json.dumps({**guard.summary(), "billing_error": flags["billing"]}, indent=2))


# ------------------------------------------------------------------ main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("materialize"); m.add_argument("--out", required=True)
    d = sub.add_parser("dryrun"); d.add_argument("--data", required=True)
    r = sub.add_parser("run")
    r.add_argument("--data", required=True)
    r.add_argument("--max-usd", type=float, required=True)
    r.add_argument("--already-spent", type=float, default=0.0)
    r.add_argument("--reserve", type=float, required=True, help="skip (not run) a video when less than this is left")
    r.add_argument("--order", required=True)
    r.add_argument("--only", nargs="*", help="run only these ids (in the declared order)")
    a = ap.parse_args(argv)

    if a.cmd == "materialize":
        print(json.dumps(materialize(Path(a.out)), indent=2))
        return 0
    ds = load_tune(Path(a.data))
    if a.cmd == "dryrun":
        est = estimate(ds)
        est["dataset_hash"] = ds.hash
        est["declared_order"] = fixed_order(ds)
        print(json.dumps(est, indent=2))
        return 0

    from app.evaluation.runner import DatasetRef, PipelineRef, RunConfig, run_evaluation

    order = json.loads(Path(a.order).read_text())["order"]
    assert order == fixed_order(ds), "order file differs from the declared order"
    if a.only:
        order = [v for v in order if v in set(a.only)]
    done = {p.stem for p in VIDEOS_DIR.glob("*.json")
            if json.loads(p.read_text())["status"] in ("finished", "graph_fallback")}
    order = [v for v in order if v not in done]  # a finished video is never paid for twice
    if not order:
        print("nothing left to run"); return 0
    by_id = {v.video_id: v for v in ds.videos}
    ds_run = ds.model_copy(update={"videos": [by_id[v] for v in order]})
    system, guard, flags, routing = build_system(a.max_usd, a.already_spent)
    system.reserve = a.reserve
    cfg = RunConfig(benchmark="T66-graph-tune", dataset=DatasetRef(path=str(a.data), version=ds.version, hash=ds.hash),
                    split="tune", pipeline=PipelineRef(system="graph", routing="config/routing.yaml"),
                    metrics=["accuracy", "macro_f1"], output_dir=str(HERE / "runs"))
    record = run_evaluation(cfg, system, dataset=ds_run, routing=routing, output_dir=HERE / "runs")
    (HERE / "runs" / record.run_id / "status.json").write_text(json.dumps(system.status, indent=2))
    write_spend(guard, flags)
    print(json.dumps({"run_id": record.run_id, "n_videos": record.n_videos, "n_errors": record.n_errors,
                      "status_counts": {s: list(system.status.values()).count(s) for s in set(system.status.values())},
                      "spend": guard.summary(), "billing_error": flags["billing"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
