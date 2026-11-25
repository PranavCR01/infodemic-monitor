"""The routing experiment: dry run, guarded live run, report and proposed routing table.

A **dry run** (the default) makes no model call: it builds the items, renders every
request each candidate would send and prices it from the routing table.

A **live run** needs all of: ``live=True``, a positive ``max_usd``, every candidate
priced, and an expected cost under the cap. Then it wraps every provider client in a
``SpendGuard`` and runs ``selection.evaluate_candidate`` for each candidate of each
step; the guard refuses any call that could cross the cap and the run stops there.

Outputs (``out_dir``): ``report.json``, ``report.md`` and, after a live run,
``routing_v2.yaml``, the current routing table with each step's measured winner
applied. ``config/routing.yaml`` is never written.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import yaml
from pydantic import BaseModel, Field, field_validator

from app.core.graph.stance import PromptNotFoundError, load_prompt
from app.core.pipeline_options import DEFAULT_OPTIONS, PipelineOptions
from app.core.routing.config import DEFAULT_ROUTING_PATH, ReasoningEffort, RoutingConfig, dump_routing
from app.evaluation.routing_experiment import cost as c
from app.evaluation.routing_experiment.frozen import FrozenEvidence
from app.evaluation.routing_experiment.golden import TuneSet
from app.evaluation.routing_experiment.items import (
    STEPS,
    VideoInput,
    extraction_items,
    extraction_view,
    in_scope_video_ids,
    stance_items,
    verify_items,
    video_input,
)
from app.evaluation.routing_experiment.runners import EXTRAS, RUNNERS, SCORERS, max_repairs, requests_for
from app.evaluation.selection import (
    STEP_METRICS,
    Budget,
    Candidate,
    CandidateResult,
    Selection,
    StepItem,
    apply_selection,
    evaluate_candidate,
    select_model,
)

DEFAULT_CANDIDATES_PATH = DEFAULT_ROUTING_PATH.parent / "routing_experiment.yaml"
PROPOSED_VERSION = "routing_v2"

# Used for the verify_claims estimate when no frozen evidence file exists yet:
# a full reranked set (10 abstracts) of this many characters each.
ASSUMED_ABSTRACT_CHARS = 1800


class ExperimentError(ValueError):
    pass


class LiveRunRefused(ExperimentError):
    pass


# ------------------------------------------------------------------ candidates file


class ExperimentCandidate(Candidate):
    """A candidate plus its expected hidden reasoning tokens per call (GPT-5-class
    models bill them as output), used only for the cost estimate."""

    reasoning_tokens: int = Field(default=0, ge=0)
    # Reasoning effort sent for this candidate (T39). None: the model's reasoning_effort
    # in routing.yaml, else "medium". Always sent explicitly for a reasoning model.
    reasoning_effort: Optional[ReasoningEffort] = None

    @property
    def placeholder(self) -> bool:
        return "todo" in self.model.lower()


class CandidatesFile(BaseModel):
    version: str = "routing_experiment"
    tie_margin: float = 0.01
    budget: dict[str, Budget] = Field(default_factory=dict)
    candidates: dict[str, list[ExperimentCandidate]]

    @field_validator("candidates")
    @classmethod
    def _steps_known(cls, v: dict[str, list[ExperimentCandidate]]) -> dict[str, list[ExperimentCandidate]]:
        unknown = sorted(set(v) - set(STEPS))
        if unknown:
            raise ValueError(f"unknown steps {unknown}; this experiment covers {list(STEPS)}")
        for step, cands in v.items():
            if not cands:
                raise ValueError(f"step {step!r} has no candidates")
            for cand in cands:
                cand.ref  # pinned-id check (ModelRef)
        return v


def load_candidates(path: Path | str = DEFAULT_CANDIDATES_PATH) -> CandidatesFile:
    try:
        data = yaml.safe_load(Path(path).read_text())
    except FileNotFoundError:
        raise ExperimentError(f"candidates file not found: {path}") from None
    try:
        cf = CandidatesFile.model_validate(data)
    except ValueError as exc:
        raise ExperimentError(f"invalid candidates file {path}: {exc}") from None
    for step, cands in cf.candidates.items():
        for cand in cands:
            try:
                load_prompt(cand.prompt)
            except PromptNotFoundError as exc:
                raise ExperimentError(f"{step}: {exc}") from None
    return cf


def candidate_key(cand: Candidate) -> str:
    effort = getattr(cand, "reasoning_effort", None)
    return f"{cand.provider}/{cand.model}@{cand.prompt}" + (f"~{effort}" if effort else "")


def experiment_base(routing: RoutingConfig) -> RoutingConfig:
    """The routing table candidates are evaluated against, with fallbacks off: an answer
    from the fallback model doesn't measure the candidate (selection counts it as a
    failure), so paying for it would be waste."""
    data = routing.model_dump()
    data["fallback"]["use"] = None
    for step in data["steps"].values():
        step["fallback"] = None
    return RoutingConfig.model_validate(data)


# ------------------------------------------------------------------ items


@dataclass
class Plan:
    steps: list[str]
    items: dict[str, list[StepItem]]
    candidates: CandidatesFile
    routing: RoutingConfig
    golden: str
    evidence_mode: Optional[str] = None
    evidence_assumed: bool = False
    notes: list[str] = field(default_factory=list)
    pipeline_options: PipelineOptions = DEFAULT_OPTIONS


def build_plan(
    tune: TuneSet,
    candidates: CandidatesFile,
    routing: RoutingConfig,
    *,
    steps: Optional[Sequence[str]] = None,
    frozen: Optional[FrozenEvidence] = None,
    videos: Optional[Sequence[str]] = None,
    allow_assumed_evidence: bool = False,
    pipeline_options: PipelineOptions = DEFAULT_OPTIONS,
) -> Plan:
    chosen = [s for s in (steps or STEPS) if s in candidates.candidates]
    ids = in_scope_video_ids(tune, videos)  # refuses non-tune ids
    plan = Plan(steps=chosen, items={}, candidates=candidates, routing=routing, golden=tune.source.describe(),
                pipeline_options=pipeline_options)
    inputs: dict[str, VideoInput] = {}
    if {"extract_claims", "analyze_stance"} & set(chosen):
        inputs = {vid: video_input(tune, vid) for vid in ids}
    if "extract_claims" in chosen:
        # use_ocr (config/pipeline.yaml) changes extraction's input only; stance keeps OCR.
        plan.items["extract_claims"] = extraction_items(
            tune, {vid: extraction_view(v, pipeline_options) for vid, v in inputs.items()}, ids)
    if "analyze_stance" in chosen:
        plan.items["analyze_stance"] = stance_items(tune, inputs, ids)
    if "verify_claims" in chosen:
        if frozen is not None:
            plan.items["verify_claims"] = verify_items(tune, frozen, ids)
            plan.evidence_mode = frozen.mode
        elif allow_assumed_evidence:
            plan.items["verify_claims"] = verify_items(tune, _AssumedEvidence(), ids)
            plan.evidence_assumed = True
            plan.notes.append(
                "verify_claims: no frozen evidence file given, so the estimate assumes every claim has "
                f"10 papers of {ASSUMED_ABSTRACT_CHARS} characters (an upper-end guess). Record the "
                "evidence (freeze-evidence) for an exact count.")
        else:
            raise ExperimentError("verify_claims needs a frozen evidence file (--frozen-evidence)")
    return plan


class _AssumedEvidence:
    def entry(self, key: str, claim_text: Optional[str] = None) -> Any:
        from app.core.graph.state import EvidenceRecord
        from app.evaluation.routing_experiment.frozen import FrozenEntry

        ev = tuple(
            EvidenceRecord(evidence_id=f"ev_assumed{i}", source="pubmed", title="x" * 120,
                           abstract="x" * ASSUMED_ABSTRACT_CHARS, publication_year=2020,
                           publication_type=["Journal Article"])
            for i in range(10)
        )
        return FrozenEntry(key=key, claim_category="other", evidence=ev, allow_unsupported=False)


# ------------------------------------------------------------------ dry run


def estimate(plan: Plan) -> dict:
    """Item counts, estimated tokens and cost per candidate per step. No calls."""
    steps: dict[str, Any] = {}
    total_expected = 0.0
    total_upper = 0.0
    unpriced: list[str] = []
    for step in plan.steps:
        items = plan.items[step]
        per_prompt: dict[str, dict] = {}
        rows = []
        for cand in plan.candidates.candidates[step]:
            if cand.prompt not in per_prompt:
                calls = in_tok = max_out = 0
                for item in items:
                    for system, body in requests_for(step, item, cand.prompt):
                        calls += 1
                        in_tok += c.estimate_input_tokens(system, body)
                        max_out += c.max_output_tokens(body)
                exp_out = calls * c.EXPECTED_OUTPUT_TOKENS.get(step, 400)
                per_prompt[cand.prompt] = {"calls": calls, "input_tokens": in_tok,
                                           "expected_output_tokens": exp_out, "max_output_tokens": max_out}
            t = dict(per_prompt[cand.prompt])
            reasoning = getattr(cand, "reasoning_tokens", 0) * t["calls"]
            t["reasoning_tokens"] = reasoning
            # Output cap per call as the router will send it (T39): a reasoning model gets
            # the step's reasoning_allowance on top of the node's visible cap. A candidate
            # that declares reasoning tokens but isn't marked in routing.yaml yet (the TODO
            # ids) is estimated as one; a live run refuses that mismatch (check_live).
            reasoning_model = plan.routing.is_reasoning(cand.model) or getattr(cand, "reasoning_tokens", 0) > 0
            allowance = plan.routing.reasoning_allowance.get(step, 0) if reasoning_model else 0
            t["output_cap_tokens"] = t["max_output_tokens"] + allowance * t["calls"]
            price = plan.routing.price(cand.model)
            expected = c.price_usd(price, t["input_tokens"], t["expected_output_tokens"] + reasoning)
            rep = 1 + max_repairs(step)
            # Upper bound: every call writes its whole cap (hidden reasoning included, billed
            # as output), or the expected reasoning + answer if a candidate declares more.
            worst_out = max(t["output_cap_tokens"], t["expected_output_tokens"] + reasoning)
            t["upper_bound_input_tokens"] = int(math.ceil(t["input_tokens"] * rep * 1.25))
            t["upper_bound_output_tokens"] = worst_out * rep
            upper = c.price_usd(price, t["input_tokens"] * rep * 1.25, worst_out * rep)
            if expected is None:
                unpriced.append(candidate_key(cand))
            else:
                total_expected += expected
                total_upper += upper or 0.0
            rows.append({
                "candidate": candidate_key(cand), "provider": cand.provider, "model": cand.model,
                "prompt": cand.prompt, **t,
                "expected_usd": None if expected is None else round(expected, 4),
                "upper_bound_usd": None if upper is None else round(upper, 4),
                "priced": price is not None,
                "placeholder_id": getattr(cand, "placeholder", False),
            })
        steps[step] = {"items": len(items), "metric": STEP_METRICS.get(step), "candidates": rows}
    return {
        "mode": "dry_run", "golden": plan.golden, "split": "tune",
        "evidence_mode": plan.evidence_mode, "evidence_assumed": plan.evidence_assumed,
        "use_ocr": plan.pipeline_options.extraction.use_ocr,
        "steps": steps, "total_expected_usd": round(total_expected, 4),
        "total_upper_bound_usd": round(total_upper, 4), "unpriced_candidates": unpriced,
        "placeholder_candidates": sorted({candidate_key(x) for s in plan.steps
                                          for x in plan.candidates.candidates[s] if getattr(x, "placeholder", False)}),
        "critic_provider_warnings": critic_provider_warnings(plan),
        "reasoning_config_problems": reasoning_config_problems(plan),
        "notes": plan.notes,
    }


def reasoning_config_problems(plan: Plan) -> list[str]:
    """Candidates whose reasoning setup disagrees with routing.yaml (T39). A candidate
    that expects reasoning tokens must be marked ``reasoning: true`` under ``models:``,
    or the client would send ``max_tokens`` (a 400 from GPT-5-class models) with no
    room for reasoning; a step with a reasoning candidate needs a reasoning_allowance."""
    problems: list[str] = []
    for step in plan.steps:
        for cand in plan.candidates.candidates[step]:
            declared = getattr(cand, "reasoning_tokens", 0) > 0
            marked = plan.routing.is_reasoning(cand.model)
            if declared and not marked:
                problems.append(
                    f"{step}: {candidate_key(cand)} expects reasoning tokens but routing.yaml has no "
                    f"`models: {{{cand.model}: {{reasoning: true}}}}` entry")
            if getattr(cand, "reasoning_effort", None) and not marked:
                problems.append(f"{step}: {candidate_key(cand)} sets reasoning_effort but routing.yaml "
                                f"doesn't mark {cand.model} as a reasoning model (the effort would not be sent)")
            if (declared or marked) and step not in plan.routing.reasoning_allowance:
                problems.append(f"{step}: {candidate_key(cand)} is a reasoning model but routing.yaml "
                                f"has no reasoning_allowance for {step}")
    return problems


def critic_provider_warnings(plan: Plan) -> list[str]:
    """§13: the critic should come from a different provider than the verifier. Flags
    every verify_claims candidate that shares the configured critic's provider."""
    if "verify_claims" not in plan.steps:
        return []
    critic = plan.routing.route("critique")
    return [
        f"verify_claims candidate {candidate_key(x)} shares the critic's provider ({critic.provider}, "
        f"{critic.model}); if it wins, change the critic to another provider (§13)"
        for x in plan.candidates.candidates["verify_claims"] if x.provider == critic.provider
    ]


# ------------------------------------------------------------------ live run


ClientFactory = Callable[[], dict[str, Any]]


def default_client_factory() -> dict[str, Any]:  # pragma: no cover - paid path, never run in tests
    """Real provider clients. Keys are read from the environment here, at the moment of
    a live run, and passed straight to the SDKs; they are never logged or written."""
    from app.core.routing.clients import default_clients

    return default_clients(
        anthropic_api_key=os.environ.get("EVAL_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", ""),
        openai_api_key=os.environ.get("EVAL_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
    )


def check_live(plan: Plan, *, live: bool, max_usd: Optional[float], est: dict) -> None:
    """Every condition a paid run needs; raises ``LiveRunRefused`` before any call."""
    if not live:
        raise LiveRunRefused("a paid run needs --live")
    if max_usd is None:
        raise LiveRunRefused("a paid run needs --max-usd <cap in USD>")
    if not (max_usd > 0):
        raise LiveRunRefused("--max-usd must be a positive number")
    if plan.evidence_assumed:
        raise LiveRunRefused("verify_claims needs recorded (frozen) evidence for a paid run")
    if est.get("placeholder_candidates"):
        raise LiveRunRefused(f"placeholder (TODO) model ids must be replaced with pinned ids first: "
                             f"{est['placeholder_candidates']}")
    if est.get("reasoning_config_problems"):
        raise LiveRunRefused(f"reasoning model settings missing in routing.yaml: {est['reasoning_config_problems']}")
    if est["unpriced_candidates"]:
        raise LiveRunRefused(f"candidates without a price in the routing table: {est['unpriced_candidates']}")
    if est["total_expected_usd"] > max_usd:
        raise LiveRunRefused(
            f"estimated cost ${est['total_expected_usd']:.2f} exceeds the cap ${max_usd:.2f}; "
            "raise the cap or run fewer steps/candidates")


def live_run(
    plan: Plan,
    *,
    live: bool,
    max_usd: Optional[float],
    client_factory: ClientFactory = default_client_factory,
    clock: Optional[Callable[[], float]] = None,
) -> dict:
    est = estimate(plan)
    check_live(plan, live=live, max_usd=max_usd, est=est)
    assert max_usd is not None
    guard = c.SpendGuard(cap_usd=float(max_usd), pricing=dict(plan.routing.pricing))
    clients = {name: guard.wrap(client) for name, client in client_factory().items()}
    base = experiment_base(plan.routing)

    results: dict[str, list[CandidateResult]] = {}
    extras: dict[str, dict[str, dict]] = {}
    selections: list[Selection] = []
    per_item: dict[str, dict[str, list[dict]]] = {}
    stopped: Optional[str] = None
    for step in plan.steps:
        items = plan.items[step]
        results[step] = []
        extras[step] = {}
        per_item[step] = {}
        for cand in plan.candidates.candidates[step]:
            outputs: list[Any] = []

            def after(item: StepItem, output: Any) -> None:
                outputs.append(output)
                guard.check()

            try:
                res = evaluate_candidate(
                    step, cand, items, base_config=base, clients=clients, scorer=SCORERS[step],
                    run_item=RUNNERS[step], after_item=after, **({"clock": clock} if clock else {}),
                )
            except c.SpendCapReached as exc:
                stopped = f"{step} / {candidate_key(cand)} after {len(outputs)} of {len(items)} items: {exc}"
                break
            results[step].append(res)
            per_item[step][candidate_key(cand)] = [
                {"item_id": i.item_id, "gold": i.gold, "output": item_output(o),
                 **({"node_errors": o.errors} if getattr(o, "errors", None) else {})}
                for i, o in zip(items, outputs)]
            if step in EXTRAS:
                extras[step][candidate_key(cand)] = EXTRAS[step]([i.gold for i in items], outputs)
        if stopped:
            break
        budget = plan.candidates.budget.get(step, Budget(max_failure_rate=0.05))
        selections.append(select_model(results[step], budget, tie_margin=plan.candidates.tie_margin))

    proposed = apply_selection(plan.routing, selections, version=PROPOSED_VERSION) if selections else None
    critic = plan.routing.route("critique")
    same_provider = None
    for sel in selections:
        if sel.step == "verify_claims" and sel.winner and sel.winner.candidate.provider == critic.provider:
            same_provider = (f"chosen verifier {candidate_key(sel.winner.candidate)} and the configured critic "
                             f"{critic.provider}/{critic.model} come from the same provider; §13 wants them "
                             "from different providers: change the critic before adopting routing_v2")
    return {
        "critic_same_provider": same_provider,
        "response_model_notes": response_model_notes(results),
        "mode": "live", "golden": plan.golden, "split": "tune", "evidence_mode": plan.evidence_mode,
        "estimate": est, "spend": guard.summary(), "stopped": stopped,
        "steps": {
            step: {
                "items": len(plan.items[step]),
                "results": [r.model_dump() for r in results.get(step, [])],
                "extras": extras.get(step, {}),
                "selection": next((s.model_dump() for s in selections if s.step == step), None),
            }
            for step in plan.steps
        },
        "proposed_routing": proposed.to_yaml_dict() if proposed else None,
        "pipeline_options": plan.pipeline_options.model_dump(),
        "_proposed": proposed,
        # T43: what each candidate answered per item, written to per_item.json (not
        # report.json) so the error analysis and bootstrap CIs need no new paid calls.
        "_per_item": per_item,
    }


def response_model_notes(results: dict[str, list[CandidateResult]]) -> list[str]:
    """Flag candidates whose responses named a different model than requested (an alias
    resolved to a snapshot), named several models (the alias moved during the run), or
    named none. Informational: the per-call ids are in report.json either way."""
    notes = []
    for step, rs in results.items():
        for r in rs:
            ids = sorted(r.response_models)
            key = candidate_key(r.candidate)
            if "unreported" in ids:
                notes.append(f"{step}: {key}: {r.response_models['unreported']} calls reported no model id")
            named = [i for i in ids if i != "unreported"]
            if len(named) > 1:
                notes.append(f"{step}: {key}: responses named {len(named)} models {named}; "
                             "the alias changed during the run")
            elif named and named[0] != r.candidate.model:
                notes.append(f"{step}: {key}: served by {named[0]}")
    return notes


def item_output(output: Any) -> Any:
    """An item's output as JSON: extraction keeps each claim's text, time span, source
    pieces and category (``runners.ExtractedClaims.details``); labels stay strings."""
    details = getattr(output, "details", None)
    if details is not None:
        return list(details)
    return output


# ------------------------------------------------------------------ outputs


def _protected(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_ROUTING_PATH.resolve()
    except OSError:
        return False


def write_outputs(report: dict, out_dir: Path | str) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    proposed: Optional[RoutingConfig] = report.pop("_proposed", None)
    per_item: Optional[dict] = report.pop("_per_item", None)
    report = {**report, "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    paths = {"report_json": out / "report.json", "report_md": out / "report.md"}
    if per_item is not None:
        paths["per_item_json"] = out / "per_item.json"
    if proposed is not None:
        paths["routing_v2"] = out / f"{PROPOSED_VERSION}.yaml"
    for p in paths.values():
        if _protected(p):
            raise ExperimentError(f"refusing to write {p}: the runner never edits config/routing.yaml")
    paths["report_json"].write_text(json.dumps(report, indent=2, default=str))
    paths["report_md"].write_text(render_markdown(report))
    if per_item is not None:
        paths["per_item_json"].write_text(json.dumps(
            {"golden": report.get("golden"), "split": report.get("split"),
             "pipeline_options": report.get("pipeline_options"), "steps": per_item},
            indent=1, ensure_ascii=False, default=str))
    if proposed is not None:
        dump_routing(proposed, paths["routing_v2"])
        header = ("# PROPOSED by the routing experiment (T38). Not in use: review it, then copy the\n"
                  "# winners into config/routing.yaml by hand and evaluate against the baseline (§14).\n")
        paths["routing_v2"].write_text(header + paths["routing_v2"].read_text())
    return {k: str(v) for k, v in paths.items()}


def _usd(x: Optional[float]) -> str:
    return "unpriced" if x is None else f"${x:,.2f}"


def _f(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.4f}"


def render_claim_matchers(extras: dict[str, dict]) -> list[str]:
    """T45: strict (selection metric) and meaning-based claim P/R/F1 per candidate."""
    lines = ["", "Claim matching, strict (token Jaccard >= 0.5; the selection metric) next to "
             "meaning-based (T43 content-word overlap; text only):", "",
             "| candidate | strict P | strict R | strict F1 | meaning P | meaning R | meaning F1 | gold | predicted |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key, e in extras.items():
        s, mm = e.get("strict") or {}, e.get("meaning") or {}
        lines.append(f"| {key} | {_f(s.get('precision'))} | {_f(s.get('recall'))} | {_f(s.get('f1'))} | "
                     f"{_f(mm.get('precision'))} | {_f(mm.get('recall'))} | {_f(mm.get('f1'))} | "
                     f"{s.get('n_gold', 'n/a')} | {s.get('n_pred', 'n/a')} |")
    return lines


def render_markdown(report: dict) -> str:
    est = report["estimate"] if report.get("mode") == "live" else report
    lines = [f"# Routing experiment ({report.get('mode')})", "",
             f"Golden set: `{report.get('golden')}`, split **tune** only.",
             f"Evidence mode (verify_claims): `{est.get('evidence_mode') or 'n/a'}`"
             + (" (assumed sizes, no frozen file)" if est.get("evidence_assumed") else ""), ""]
    if est.get("use_ocr") is False:
        lines += ["**extract_claims ran WITHOUT on-screen text** (`extraction.use_ocr: false`, "
                  "config/pipeline.yaml ablation). Stance still sees OCR.", ""]
    if report.get("mode") == "live":
        s = report["spend"]
        lines += [f"Spend: **${s['spent_usd']:.4f}** of cap ${s['cap_usd']:.2f} in {s['calls']} calls"
                  + (f"; STOPPED: {report['stopped']}" if report.get("stopped") else ""), ""]
        for note in report.get("response_model_notes") or []:
            lines += [f"Model id: {note}", ""]
        if report.get("critic_same_provider"):
            lines += [f"**WARNING:** {report['critic_same_provider']}", ""]
        for step, d in report["steps"].items():
            sel = d.get("selection") or {}
            winner = (sel.get("winner") or {}).get("candidate")
            lines += [f"## {step} ({d['items']} items)", "",
                      f"Chosen: **{candidate_key(ExperimentCandidate(**winner)) if winner else 'none'}**"
                      f" ({sel.get('reason', 'not selected')})", "",
                      "| candidate | metric | score | failed | cost/item | p95 latency ms | reported model ids (calls) | reasoning tokens |",
                      "|---|---|---|---|---|---|---|---|"]
            for r in d["results"]:
                score = "n/a" if r["score"] is None else f"{r['score']:.4f}"
                cpi = "n/a" if r["cost_per_item"] is None else f"${r['cost_per_item']:.5f}"
                reported = ", ".join(f"{k} ({v})" for k, v in sorted((r.get("response_models") or {}).items())) or "n/a"
                lines.append(f"| {candidate_key(ExperimentCandidate(**r['candidate']))} | {r['metric']} | {score} | "
                             f"{r['n_failed']}/{r['n_items']} | {cpi} | {r['latency_p95_ms']} | {reported} | "
                             f"{r.get('reasoning_tokens', 0):,} |")
            if step == "extract_claims" and d.get("extras"):
                lines += render_claim_matchers(d["extras"])
            else:
                for k, v in (d.get("extras") or {}).items():
                    lines.append(f"\n{k}: {json.dumps(v)}")
            if sel.get("excluded"):
                lines.append(f"\nExcluded: {json.dumps(sel['excluded'])}")
            lines.append("")
        lines += ["## Estimate before the run", ""]
    lines += ["| step | items | candidate | calls | input tokens | expected output | reasoning (as output) | output cap | expected cost | upper bound |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for step, d in est["steps"].items():
        for r in d["candidates"]:
            lines.append(f"| {step} | {d['items']} | {r['candidate']} | {r['calls']} | {r['input_tokens']:,} | "
                         f"{r['expected_output_tokens']:,} | {r.get('reasoning_tokens', 0):,} | "
                         f"{r.get('output_cap_tokens', r.get('max_output_tokens', 0)):,} | "
                         f"{_usd(r['expected_usd'])} | {_usd(r['upper_bound_usd'])} |")
    for step, d in est["steps"].items():
        priced = [r["expected_usd"] for r in d["candidates"] if r["expected_usd"] is not None]
        lines.append(f"\n{step}: {d['items']} items; priced candidates total {_usd(sum(priced))}")
    lines += ["", f"Total expected (priced candidates): **{_usd(est['total_expected_usd'])}**; "
              f"upper bound (every call at its output cap, every repair fired): {_usd(est['total_upper_bound_usd'])}."]
    if est.get("unpriced_candidates"):
        lines.append(f"\nUnpriced (not in the total; a live run refuses them): {', '.join(est['unpriced_candidates'])}")
    if est.get("reasoning_config_problems"):
        lines.append("\nReasoning-model settings missing in routing.yaml (a live run refuses these):\n"
                     + "\n".join(f"- {x}" for x in est["reasoning_config_problems"]))
    if est.get("placeholder_candidates"):
        lines.append(f"\nTODO placeholder model ids (replace with pinned dated ids and add prices before a paid run): "
                     f"{', '.join(est['placeholder_candidates'])}")
    for w in est.get("critic_provider_warnings") or []:
        lines.append(f"\nWarning: {w}")
    for n in est.get("notes") or []:
        lines.append(f"\nNote: {n}")
    return "\n".join(lines) + "\n"
