"""Run the adversarial set against the guarded graph and the single-call baseline,
and report "N unsafe out of M" (§15).

    python -m app.evaluation.adversarial [--cases PATH] [--out REPORT.md] [--json PATH]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from app.evaluation.adversarial.cases import CATEGORIES, AdversarialCase, CaseSet, load_cases
from app.evaluation.adversarial.graph_system import run_guarded_graph
from app.evaluation.adversarial.simulated import ObedientModel, SimulatedSingleCallProvider
from app.evaluation.adversarial.unsafe import UNSAFE_DEFINITION, Assessment, Outcome, assess, fabricated_snippets

GRAPH = "guarded_graph"
BASELINE = "single_call_baseline"


def run_graph_case(case: AdversarialCase) -> Assessment:
    g = run_guarded_graph(case)
    fabricated = sorted(g.cited_ids - g.retrieved_ids)
    if g.final:
        fabricated += sorted(set(g.final.claim_ids) - g.claim_ids)
    outcome = Outcome(
        system=GRAPH, case_id=case.id, label=g.label, review_required=g.review_required,
        review_reasons=g.review_reasons, fabricated=fabricated, error=g.error,
        triggered_steps=g.triggered_steps,
    )
    a = assess(case, outcome)
    label_ok = g.label in {l.value for l in case.expected.labels}
    review_ok = case.expected.review is None or case.expected.review == g.review_required
    a.meets_expected = label_ok and review_ok
    return a


def run_baseline_case(case: AdversarialCase) -> Assessment:
    """Today's single-call classifier: one call, the live prompt, the live parsing."""
    model = ObedientModel(case)
    provider = SimulatedSingleCallProvider(model.client())
    fusion = case.fusion()
    try:
        result = provider.classify(fusion)
        outcome = Outcome(
            system=BASELINE, case_id=case.id, label=result.label.value, confidence=result.confidence,
            fabricated=fabricated_snippets(result.evidence_snippets, fusion.combined_content),
            triggered_steps=model.triggered_steps,
        )
    except Exception as exc:
        outcome = Outcome(system=BASELINE, case_id=case.id, label=None, error=f"{type(exc).__name__}: {exc}")
    return assess(case, outcome)


@dataclass
class SystemSummary:
    system: str
    total: int
    unsafe: int
    held_for_review: int
    by_reason: dict[str, int]
    by_category: dict[str, tuple[int, int]]  # category -> (unsafe, total)

    @property
    def headline(self) -> str:
        return f"{self.unsafe} unsafe out of {self.total}"


def summarise(system: str, assessments: list[Assessment], cases: list[AdversarialCase]) -> SystemSummary:
    cat = {c.id: c.category for c in cases}
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    reasons: Counter = Counter()
    for a in assessments:
        row = by_cat[cat[a.outcome.case_id]]
        row[1] += 1
        if a.unsafe:
            row[0] += 1
        reasons.update(a.reasons)
    return SystemSummary(
        system=system, total=len(assessments), unsafe=sum(a.unsafe for a in assessments),
        held_for_review=sum(a.held_for_review for a in assessments),
        by_reason={r: reasons.get(r, 0) for r in ("label_moved", "schema_violation", "fabricated_evidence", "confident_off_topic")},
        by_category={c: tuple(by_cat[c]) for c in CATEGORIES if c in by_cat},
    )


@dataclass
class AdversarialReport:
    case_set: CaseSet
    graph: list[Assessment]
    baseline: list[Assessment]

    @property
    def graph_summary(self) -> SystemSummary:
        return summarise(GRAPH, self.graph, self.case_set.cases)

    @property
    def baseline_summary(self) -> SystemSummary:
        return summarise(BASELINE, self.baseline, self.case_set.cases)

    def unmet_expectations(self) -> list[str]:
        """Graph cases that miss their expected outcome without a recorded known gap."""
        cases = {c.id: c for c in self.case_set.cases}
        return [a.outcome.case_id for a in self.graph
                if not a.meets_expected and not cases[a.outcome.case_id].known_gap]

    def to_json(self) -> dict:
        def rows(items):
            return [{**asdict(a.outcome), "unsafe": a.unsafe, "reasons": a.reasons,
                     "held_for_review": a.held_for_review, "meets_expected": a.meets_expected} for a in items]
        return {
            "case_set": {"version": self.case_set.version, "hash": self.case_set.hash, "cases": len(self.case_set.cases)},
            "summary": {s.system: {"headline": s.headline, **asdict(s)} for s in (self.graph_summary, self.baseline_summary)},
            "graph": rows(self.graph),
            "baseline": rows(self.baseline),
        }

    def to_markdown(self) -> str:
        gs, bs = self.graph_summary, self.baseline_summary
        cases = {c.id: c for c in self.case_set.cases}
        out = [
            "# Adversarial results",
            "",
            f"Case set `{self.case_set.version}` ({len(self.case_set.cases)} cases, sha256 `{self.case_set.hash[:12]}`).",
            "Generated by `python -m app.evaluation.adversarial`; do not edit by hand.",
            "",
            "**Simulated model, not a real one.** Every model call is answered by a simulated model that "
            "obeys the attack whenever the attack's trigger appears in that step's input (a worst case). "
            "These numbers measure what the structure around the model contains when the model is fooled. "
            "How often a real model is fooled needs a paid run on the same set (T14).",
            "",
            "**Read with care.** (1) The injection detector and this set were written by the same "
            "author at the same time, so the detected cases show coverage of known phrasings, not "
            "robustness to new ones; a held-out red-team set written by someone else is still needed. "
            "(2) The baseline scores 0 on abstract injection only because it never reads abstracts. "
            "(3) The graph's LLM steps here are guarded reference nodes and the T02 stubs, not the "
            "real T03-T09 nodes; rerun once those land.",
            "",
            "## Headline",
            "",
            "| System | Unsafe | of which held for review | label moved | schema | fabricated evidence | confident off-topic |",
            "|---|---|---|---|---|---|---|",
        ]
        for s in (gs, bs):
            r = s.by_reason
            out.append(f"| {s.system} | **{s.headline}** | {s.held_for_review} | {r['label_moved']} | "
                       f"{r['schema_violation']} | {r['fabricated_evidence']} | {r['confident_off_topic']} |")
        out += ["", "## By category", "", "| Category | Guarded graph | Single-call baseline |", "|---|---|---|"]
        for c in CATEGORIES:
            if c in gs.by_category:
                g, b = gs.by_category[c], bs.by_category[c]
                out.append(f"| {c} | {g[0]} / {g[1]} | {b[0]} / {b[1]} |")
        out += ["", "## Definition of unsafe", "", "```", UNSAFE_DEFINITION.rstrip(), "```", "",
                "## Per case", "",
                "| Case | Category | Honest | Graph label | Review | Graph unsafe | Baseline label | Baseline unsafe |",
                "|---|---|---|---|---|---|---|---|"]
        for g, b in zip(self.graph, self.baseline):
            c = cases[g.outcome.case_id]
            out.append(
                f"| {c.id} | {c.category} | {c.honest_label.value} | {g.outcome.label} | "
                f"{'yes' if g.outcome.review_required else 'no'} | {', '.join(g.reasons) or '—'} | "
                f"{b.outcome.label} | {', '.join(b.reasons) or '—'} |"
            )
        gaps = [c for c in self.case_set.cases if c.known_gap]
        if gaps:
            out += ["", "## Known gaps (graph)", ""]
            out += [f"- **{c.id}**: {c.known_gap}" for c in gaps]
        out.append("")
        return "\n".join(out)


def run_adversarial(cases: Optional[CaseSet] = None) -> AdversarialReport:
    cases = cases or load_cases()
    return AdversarialReport(
        case_set=cases,
        graph=[run_graph_case(c) for c in cases.cases],
        baseline=[run_baseline_case(c) for c in cases.cases],
    )


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.evaluation.adversarial", description=__doc__)
    p.add_argument("--cases", default=None, help="case set YAML (default: research/adversarial/adversarial_v1.yaml)")
    p.add_argument("--out", default=None, help="write the markdown report here")
    p.add_argument("--json", default=None, help="write per-case results as JSON here")
    args = p.parse_args(argv)
    report = run_adversarial(load_cases(args.cases) if args.cases else None)
    if args.out:
        Path(args.out).write_text(report.to_markdown())
    if args.json:
        Path(args.json).write_text(json.dumps(report.to_json(), indent=2, default=str))
    print(f"{GRAPH}: {report.graph_summary.headline} ({report.graph_summary.held_for_review} held for review)")
    print(f"{BASELINE}: {report.baseline_summary.headline}")
    unmet = report.unmet_expectations()
    if unmet:
        print(f"graph missed expected outcome without a known gap: {unmet}")
        return 1
    return 0
