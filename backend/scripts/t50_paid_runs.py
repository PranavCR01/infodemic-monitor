"""T50: dry-run cost estimate, and the capped paid runs the lead can approve.

The model parts of T50 (search assistant ``plan_search``, translator ``translate_claim``,
find-the-study ``find_study`` with web search) are not run by the build. This script

- ``estimate`` (default; **no model call, no network**): reads a rules-only T50 record
  (``t50_search_recall.py record``) and the routing table, decides which claims would
  call each model step, and prints the expected cost and an upper bound per claim and in
  total for (1) the 13-claim vitamin K regression fixture (find-the-study forced on
  c2-c5, as the regression test asks) and (2) the tune split recall measurement;
- ``run --live --max-usd <cap>``: the paid run. Refuses without both flags. Every
  model call goes through a cap that stops the run before a call that could exceed it.
  Writes a record in the same format as the rules-only one, so
  ``t50_search_recall.py score before.json paid.json`` compares them.

Token counts in the estimate are characters / 4 of the real prompts and claims (no
tokenizer call); web search is billed per search (``WEB_SEARCH_USD_PER_SEARCH``) and its
results as input tokens. Prices come from ``config/routing.yaml``.

    python scripts/t50_paid_runs.py estimate --record <after.json>
    python scripts/t50_paid_runs.py run --target vitamin_k --live --max-usd 1 --out vitk_paid.json
    python scripts/t50_paid_runs.py run --target tune --live --max-usd 5 --out tune_paid.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.graph.state import EvidenceRecord, GraphClaim  # noqa: E402
from app.core.retrieval.assist import PLAN_SEARCH_STEP, SEARCH_TOOL, TRANSLATE_STEP  # noqa: E402
from app.core.retrieval.find_study import (  # noqa: E402
    FIND_STUDY_STEP, MAX_WEB_SEARCHES, WEB_SEARCH_USD_PER_SEARCH,
)
from app.core.retrieval.language import detect_language, is_english  # noqa: E402
from app.core.retrieval.planning import QueryPlanner  # noqa: E402
from app.core.routing.config import load_routing  # noqa: E402

HERE = Path(__file__).resolve().parent
PROMPTS = HERE.parent / "app" / "core" / "graph" / "prompts"
VITK = HERE.parent / "app" / "tests" / "fixtures" / "prod_5cc07f48" / "vitamin_k_job.real.json"
FORCED_FIND_STUDY = ("c2", "c3", "c4", "c5")  # the lead's regression: must land on the JAMA paper

# Output tokens per call: (expected, cap). Caps are the nodes' max_tokens.
OUTPUT_TOKENS = {PLAN_SEARCH_STEP: (150, 400), TRANSLATE_STEP: (60, 200), FIND_STUDY_STEP: (250, 600)}
# Web search: searches per call (expected, max_uses) and result tokens per search
# (expected, upper). Search results are billed as input tokens.
SEARCHES = (2, MAX_WEB_SEARCHES)
TOKENS_PER_SEARCH = (3000, 8000)
# Attempts per call: the router retries once on timeout / 5xx; the upper bound assumes
# every call is retried once on the primary model.
ATTEMPTS_UPPER = 2


def tok(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class StepCost:
    calls: int = 0
    expected: float = 0.0
    upper: float = 0.0


def _price(routing, step):
    route = routing.route(step)
    p = routing.price(route.model)
    if p is None:
        raise SystemExit(f"no price for {route.model} in routing.yaml")
    return route.model, p


def call_cost(routing, step: str, claim_text: str) -> tuple[float, float]:
    """(expected, upper) USD for one call of ``step`` on ``claim_text``."""
    _, p = _price(routing, step)
    system = (PROMPTS / f"{routing.route(step).prompt}.md").read_text()
    base_in = tok(system) + tok(claim_text) + 60
    if step == PLAN_SEARCH_STEP:
        base_in += tok(json.dumps(SEARCH_TOOL))
    out_e, out_u = OUTPUT_TOKENS[step]
    in_e = in_u = base_in
    fee_e = fee_u = 0.0
    if step == FIND_STUDY_STEP:
        in_e += SEARCHES[0] * TOKENS_PER_SEARCH[0] + 400  # tool definition and turn overhead
        in_u += SEARCHES[1] * TOKENS_PER_SEARCH[1] + 400
        fee_e, fee_u = SEARCHES[0] * WEB_SEARCH_USD_PER_SEARCH, SEARCHES[1] * WEB_SEARCH_USD_PER_SEARCH
    exp = (in_e * p.input + out_e * p.output) / 1e6 + fee_e
    up = ATTEMPTS_UPPER * ((in_u * p.input + out_u * p.output) / 1e6 + fee_u)
    return exp, up


def triggers(claim: dict, context: list[str], kept: list[EvidenceRecord], forced: bool) -> dict:
    """Which model steps this claim would call (rules decide; no model is consulted)."""
    from app.core.graph.retrieval_nodes import _find_study_reason

    plan = QueryPlanner().plan(claim["text"], claim_kind=claim.get("kind", "research_question"), context=context)
    lang = detect_language(claim["text"])
    rule_kinds = {r.kind for r in plan.rungs} - {"keywords", "citation"}
    gc = GraphClaim(claim_id="c", claim_text=claim["text"], claim_category="other", source_segment_ids=["s"],
                    start_seconds=0, end_seconds=1)
    reason = _find_study_reason(gc, kept, tuple(context), None)
    return {"translate": not is_english(lang), "assistant": not rule_kinds,
            "find_study": forced or reason is not None, "find_study_reason": "forced" if forced else reason}


def estimate(record_path: Optional[Path], vitk_record: Optional[Path]) -> str:
    routing = load_routing()
    lines = ["# T50 dry-run cost estimate (no model was called)", "",
             f"Routing: `{routing.version}`; plan_search {routing.route(PLAN_SEARCH_STEP).model}, "
             f"translate_claim {routing.route(TRANSLATE_STEP).model}, find_study "
             f"{routing.route(FIND_STUDY_STEP).model} with web search "
             f"(${WEB_SEARCH_USD_PER_SEARCH:.3f}/search, max {MAX_WEB_SEARCHES} searches per claim).", "",
             "Expected: one attempt, typical output, "
             f"{SEARCHES[0]} searches x {TOKENS_PER_SEARCH[0]} result tokens. Upper bound: every call retried "
             f"once, output at its cap, {SEARCHES[1]} searches x {TOKENS_PER_SEARCH[1]} result tokens. "
             "The router's fallback model (gpt-4o) is not in the bound: it is only used after the primary "
             "times out or fails twice, and the paid run's cap still applies.", ""]
    targets = []
    vitk = json.loads(VITK.read_text())
    vrec = json.loads(vitk_record.read_text()) if vitk_record else None
    vclaims = []
    for c in vitk["claims"]:
        kept = []
        if vrec:
            row = next((r for r in vrec if r["claim"] == c["claim_id"]), None)
            kept = [EvidenceRecord(evidence_id=f"k{i}", source="pubmed", title=t, abstract="")
                    for i, t in enumerate(row["first_kept"])] if row else []
        vclaims.append(({"text": c["text"], "kind": c["claim_kind"], "id": c["claim_id"]}, kept,
                        c["claim_id"] in FORCED_FIND_STUDY))
    targets.append(("vitamin K job (13 claims; find-the-study forced on c2-c5)", vclaims,
                    [c["text"] for c in vitk["claims"]]))
    if record_path:
        data = json.loads(record_path.read_text())
        by_video: dict[str, list[str]] = {}
        for key, c in data["claims"].items():
            by_video.setdefault(key.split(":")[0], []).append(c["text"])
        tclaims = []
        for key, c in data["claims"].items():
            kept = [EvidenceRecord(evidence_id=i, source="pubmed", title=c["records"][i]["title"],
                                   abstract=c["records"][i]["abstract"]) for i in c["kept"] if i in c["records"]]
            tclaims.append(({"text": c["text"], "kind": c["kind"], "id": key, "video": key.split(":")[0]}, kept, False))
        targets.append((f"tune split recall ({len(tclaims)} claims)", tclaims, None, ) + (by_video,))
    out_json = {}
    for t in targets:
        name, claims, context = t[0], t[1], t[2]
        by_video = t[3] if len(t) > 3 else None
        steps = {PLAN_SEARCH_STEP: StepCost(), TRANSLATE_STEP: StepCost(), FIND_STUDY_STEP: StepCost()}
        per_claim = []
        for claim, kept, forced in claims:
            ctx = context if context is not None else by_video[claim["video"]]
            tr = triggers(claim, ctx, kept, forced)
            ce = cu = 0.0
            for step, on in ((TRANSLATE_STEP, tr["translate"]), (PLAN_SEARCH_STEP, tr["assistant"]),
                             (FIND_STUDY_STEP, tr["find_study"])):
                if on:
                    e, u = call_cost(routing, step, claim["text"])
                    steps[step].calls += 1
                    steps[step].expected += e
                    steps[step].upper += u
                    ce, cu = ce + e, cu + u
            per_claim.append({"claim": claim["id"], **tr, "expected_usd": round(ce, 5), "upper_usd": round(cu, 5)})
        te = sum(s.expected for s in steps.values())
        tu = sum(s.upper for s in steps.values())
        n = len(claims)
        lines += [f"## {name}", "", "| step | calls | expected USD | upper bound USD |", "| --- | --- | --- | --- |"]
        for step, s in steps.items():
            lines.append(f"| {step} | {s.calls} | {s.expected:.4f} | {s.upper:.4f} |")
        lines += [f"| **total** | {sum(s.calls for s in steps.values())} | **{te:.4f}** | **{tu:.4f}** |", "",
                  f"Per claim: expected {te / n:.5f} USD, upper {tu / n:.5f} USD on average; "
                  f"max upper for one claim {max(p['upper_usd'] for p in per_claim):.5f} USD.", ""]
        fs = [p for p in per_claim if p["find_study"]]
        if fs:
            reasons: dict[str, int] = {}
            for p in fs:
                reasons[p["find_study_reason"]] = reasons.get(p["find_study_reason"], 0) + 1
            lines += [f"find_study triggers: {reasons}.", ""]
        out_json[name] = {"steps": {k: vars(v) for k, v in steps.items()}, "expected_usd": te, "upper_usd": tu,
                          "per_claim": per_claim}
    lines += ["## Latency (expected, per claim that calls the step)", "",
              "- translate_claim, plan_search: one cheap-model call each, about 1-2 s.",
              "- find_study: one model turn with up to 3 server-side searches, about 5-15 s; then our "
              "verification, about 0.4 s per candidate on E-utilities (2.5 requests/s, 1-3 requests each) "
              "and up to 0.5 s per Crossref lookup.", ""]
    return "\n".join(lines) + "\n", out_json


# ------------------------------------------------------------------ the paid run


class BudgetExceeded(RuntimeError):
    pass


class CappedCaller:
    """Wraps the router: refuses a call when what was spent plus the step's worst case
    would pass the cap. Spend = router-reported token cost + web search fees."""

    def __init__(self, router, max_usd: float):
        self.router = router
        self.config = router.config
        self.max_usd = max_usd
        self.spent = 0.0
        self.records = router.records

    def call(self, step: str, input: Any, *, system: Optional[str] = None):
        _, worst = call_cost(self.config, step, json.dumps(input)[:2000])
        if self.spent + worst > self.max_usd:
            raise BudgetExceeded(f"cap {self.max_usd} USD: spent {self.spent:.4f}, next call up to {worst:.4f}")
        before = len(self.router.records)
        try:
            return self.router.call(step, input, system=system)
        finally:
            for rec in self.router.records[before:]:
                self.spent += rec.cost_usd or 0.0

    def add_fee(self, usd: float) -> None:
        self.spent += usd


def check_live(live: bool, max_usd: Optional[float]) -> None:
    if not live:
        raise SystemExit("refused: a paid run needs --live (the lead approves paid runs and sets the cap)")
    if max_usd is None or not (max_usd > 0):
        raise SystemExit("refused: a paid run needs --max-usd <positive cap in USD>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("estimate")
    e.add_argument("--record", help="rules-only T50 record of the tune split (after.json)")
    e.add_argument("--vitamin-k", help="vitamin_k.json from t50_vitamin_k_regression.py")
    e.add_argument("--out")
    r = sub.add_parser("run")
    r.add_argument("--target", choices=("vitamin_k", "tune"), required=True)
    r.add_argument("--live", action="store_true")
    r.add_argument("--max-usd", type=float)
    r.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        check_live(args.live, args.max_usd)
        from t50_paid_run_live import run_live  # noqa: E402  (kept apart: the only module that builds real clients)

        run_live(args.target, args.max_usd, Path(args.out))
        return 0
    text, data = estimate(Path(args.record) if getattr(args, "record", None) else None,
                          Path(args.vitamin_k) if getattr(args, "vitamin_k", None) else None)
    print(text)
    if getattr(args, "out", None):
        Path(args.out).write_text(text)
        Path(args.out).with_suffix(".json").write_text(json.dumps(data, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
