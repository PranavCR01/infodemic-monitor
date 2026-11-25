"""Real-model smoke run (T18): the graph and the single-call baseline on a few videos.

Goal: find integration bugs and measure real cost and latency per video. NOT accuracy:
this script never reads labels and reports no accuracy numbers.

    cd backend
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... \\
      python scripts/smoke_run.py <transcripts_dir> --videos v07 v12 --out /tmp/smoke \\
        --stop-at 12.0 --spent-so-far 0.0

``<transcripts_dir>`` holds the golden set's ``transcripts/vNN.json`` files (branch
``data/golden-label-set``, ``research/claim-level/dataset/transcripts``). Only the
speech transcript is used, as the live worker does today (OCR is off in production).

Per video it runs the baseline (``get_provider()``: the live single-call provider) and
the graph (``build_graph_provider``'s wiring, with references on and an in-memory
snapshot store instead of Postgres). Cost comes from the token usage the APIs return,
priced with ``config/routing.yaml``'s ``pricing``. Before each video the running total
is checked against ``--stop-at``; the run stops there, so a retry cannot cross the cap.

Writes ``results.jsonl`` (one object per video and system, with every model call) and
prints a Markdown table. Never prints or writes a key.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")

from app.core.schemas.pipeline import FusionResult  # noqa: E402


# ------------------------------------------------------------------ inputs

def _field(obj: Any) -> Any:
    """The golden set stores nested objects as Python reprs inside JSON strings."""
    if isinstance(obj, str):
        try:
            return json.loads(obj)
        except ValueError:
            return ast.literal_eval(obj)
    return obj


def fusion_from_transcript(path: Path, max_chars: int = 128_000) -> FusionResult:
    """The FusionResult the live worker would build (speech only, OCR off), with the
    Whisper segments kept as the graph path's ``fuse(keep_segments=True)`` does."""
    data = json.loads(path.read_text())
    tr = _field(data.get("transcript") or {}) or {}
    segments = [
        {"start": float(s.get("start", 0.0)), "end": float(s.get("end", 0.0)), "text": str(s.get("text", "")).strip()}
        for s in tr.get("segments", []) if str(s.get("text", "")).strip()
    ]
    transcript = " ".join(s["text"] for s in segments)
    combined = f"[AUDIO TRANSCRIPT]\n{transcript}" if transcript else ""
    if len(combined) > max_chars:
        raise ValueError(f"{path.name}: transcript longer than {max_chars} chars")
    return FusionResult(
        transcript=transcript, visual_text="", combined_content=combined,
        metadata={
            "audio_length_chars": len(transcript), "visual_length_chars": 0,
            "frames_processed": 0, "ocr_detection_count": 0, "ocr_disabled": True,
            "transcript_segments": segments,
            "duration_seconds": tr.get("duration_seconds"),
        },
    )


# ------------------------------------------------------------------ costing

class CostingProvider:
    """Wraps a single-call provider and records each call's usage and cost, so the
    baseline (and the graph's fallback, which is the same provider) are both costed."""

    def __init__(self, inner: Any, pricing: Any):
        self.inner = inner
        self.pricing = pricing
        self.calls: list[dict] = []

    def classify(self, fusion: FusionResult):
        t0 = time.perf_counter()
        try:
            return self.inner.classify(fusion)
        finally:
            usage = getattr(self.inner, "last_usage", None) or {}
            self.inner.last_usage = None
            self.calls.append({
                "model": usage.get("model"),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cost_usd": price_of(self.pricing, usage.get("model"),
                                     usage.get("input_tokens", 0), usage.get("output_tokens", 0)),
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            })


def price_of(routing: Any, model: Optional[str], tin: int, tout: int) -> Optional[float]:
    if not model:
        return 0.0 if not (tin or tout) else None
    price = routing.price(model)
    if price is None:
        return None
    return (tin * price.input + tout * price.output) / 1_000_000


def total(costs: list[Optional[float]]) -> tuple[float, bool]:
    """Sum, and whether any part was unpriced (then the sum is a lower bound)."""
    return sum(c for c in costs if c is not None), any(c is None for c in costs)


# ------------------------------------------------------------------ wiring

def build(args) -> tuple[Any, CostingProvider, Any]:
    from app.core.config import settings
    from app.core.inference import get_provider
    from app.core.inference.providers.graph_provider import GraphProvider
    from app.core.retrieval.pubmed import PubMedClient, shared_rate_limiter
    from app.core.retrieval.references import ReferenceSearcher, load_reference_config
    from app.core.retrieval.references.snapshots import InMemorySnapshotStore
    from app.core.retrieval.retriever import EvidenceRetriever
    from app.core.routing.clients import default_clients
    from app.core.routing.config import load_routing
    from app.core.routing.router import ModelRouter

    routing = load_routing()
    router = ModelRouter(routing, default_clients(
        anthropic_api_key=settings.ANTHROPIC_API_KEY, openai_api_key=settings.OPENAI_API_KEY,
        timeout=settings.GRAPH_MODEL_TIMEOUT_SECONDS,
    ))
    baseline = CostingProvider(get_provider(), routing)
    limiter = shared_rate_limiter(bool(settings.NCBI_API_KEY))  # 2.5/s without a key
    retriever = EvidenceRetriever(
        PubMedClient(api_key=settings.NCBI_API_KEY, email=settings.NCBI_EMAIL, rate_limiter=limiter),
        None, max_results=settings.RETRIEVAL_MAX_RESULTS_PER_QUERY,
    )
    references = None
    if not args.no_references:
        references = ReferenceSearcher(load_reference_config(), snapshots=InMemorySnapshotStore(),
                                       rate_limiter=limiter)
    graph = GraphProvider(
        caller=router, retriever=retriever, fallback=baseline, references=references,
        timeout_seconds=settings.GRAPH_TIMEOUT_SECONDS, pipeline_version=settings.GRAPH_PIPELINE_VERSION,
    )
    return graph, baseline, routing


def summarize_state(state: Optional[dict]) -> dict:
    if not state:
        return {}
    claims = state.get("claims") or []
    out = {
        "n_claims": len(claims),
        "n_evidence": sum(len(v) for v in (state.get("reranked_evidence") or {}).values()),
        "verdicts": {k: str(getattr(v, "verdict", v))[:40] for k, v in (state.get("verification_results") or {}).items()},
        "validation_errors": state.get("validation_errors") or [],
        "errors": [str(e)[:300] for e in (state.get("errors") or [])],
        "requires_human_review": state.get("requires_human_review"),
        "review_reasons": state.get("review_reasons") or [],
    }
    final = state.get("final_result")
    if final is not None:
        f = final if isinstance(final, dict) else getattr(final, "model_dump", lambda: {})()
        out["decision_rule"] = f.get("decision_rule")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts_dir")
    ap.add_argument("--videos", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stop-at", type=float, default=12.0, help="stop before a video once this much is spent")
    ap.add_argument("--spent-so-far", type=float, default=0.0, help="spend from earlier invocations")
    ap.add_argument("--no-references", action="store_true")
    ap.add_argument("--skip-baseline", action="store_true")
    args = ap.parse_args()

    graph, baseline, routing = build(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    spent = args.spent_so_far
    rows = []
    with (out / "results.jsonl").open("a") as fh:
        for vid in args.videos:
            if spent >= args.stop_at:
                print(f"stopping before {vid}: spent ${spent:.4f} >= ${args.stop_at:.2f}", file=sys.stderr)
                break
            fusion = fusion_from_transcript(Path(args.transcripts_dir) / f"{vid}.json")
            row = {"video_id": vid, "transcript_chars": len(fusion.transcript),
                   "duration_s": fusion.metadata.get("duration_seconds")}

            if not args.skip_baseline:
                baseline.calls.clear()
                t0 = time.perf_counter()
                err = None
                try:
                    res = baseline.classify(fusion)
                    blabel = res.label.value
                except Exception as exc:  # noqa: BLE001
                    blabel, err = None, f"{type(exc).__name__}: {str(exc)[:300]}"
                cost, unpriced = total([c["cost_usd"] for c in baseline.calls])
                rec = {"video_id": vid, "system": "baseline", "latency_ms": int((time.perf_counter() - t0) * 1000),
                       "cost_usd": cost, "cost_lower_bound": unpriced, "error": err,
                       "label": blabel, "calls": list(baseline.calls)}
                fh.write(json.dumps(rec) + "\n"); fh.flush()
                spent += cost
                row.update(baseline_cost=cost, baseline_ms=rec["latency_ms"], baseline_error=err)

            baseline.calls.clear()
            t0 = time.perf_counter()
            err = None
            outcome = None
            try:
                outcome = graph.run(fusion, job_id=f"smoke-{vid}-{time.time_ns()}", video_id=vid,
                                    video_duration_seconds=fusion.metadata.get("duration_seconds"))
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {str(exc)[:300]}"
            latency = int((time.perf_counter() - t0) * 1000)
            calls = [c.model_dump() for c in (outcome.model_calls if outcome else [])]
            fb_calls = list(baseline.calls)
            cost, unpriced = total([c["cost_usd"] for c in calls] + [c["cost_usd"] for c in fb_calls])
            rec = {
                "video_id": vid, "system": "graph", "latency_ms": latency, "cost_usd": cost,
                "cost_lower_bound": unpriced, "error": err,
                "pipeline": outcome.pipeline if outcome else None,
                "fallback_reason": outcome.fallback_reason if outcome else None,
                "label": outcome.classification.label.value if outcome else None,
                "state": summarize_state(outcome.state if outcome else None),
                "calls": calls, "fallback_calls": fb_calls,
            }
            fh.write(json.dumps(rec, default=str) + "\n"); fh.flush()
            spent += cost
            row.update(graph_cost=cost, graph_ms=latency, graph_pipeline=rec["pipeline"],
                       fallback_reason=rec["fallback_reason"], n_calls=len(calls),
                       call_errors=sum(1 for c in calls if c.get("error")))
            rows.append(row)
            print(json.dumps({**row, "spent_total": round(spent, 4)}), flush=True)

    print(f"\nTOTAL SPENT (incl. --spent-so-far): ${spent:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
