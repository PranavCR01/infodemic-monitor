"""Verification test set runner and metrics (target design §7, §14; issue #33).

Runs the real ``verify_claims`` node over the labelled examples in
``app/tests/fixtures/verify/examples.jsonl`` and scores it (§14 "Verification":
precision, recall and F1 for each verdict), plus the failure tracked separately in §14:
**insufficient evidence called contradiction**. Citation checks: share of cited IDs
that were retrieved (must be 1.0; the node rejects anything else) and agreement of the
cited IDs with the labelled deciding papers.

The set is small (20 claims), synthetic (abstracts written for the test, PMIDs fake,
marked "Synthetic.") and labelled by the build agent, not two people. It exercises the
node and the harness; it is not evidence of model quality.

Without API keys this repo only runs two offline callers, neither of which measures an
LLM:

- ``heuristic``: deterministic cue-word rules (negative vs positive findings, skipping
  animal/lab studies). The floor a model must beat; its numbers are real for it.
- ``oracle``: replays the gold labels; checks the harness, should score 1.0.

    python -m app.core.graph.verify_eval --caller heuristic [--out results.json]

A real model run, once keys exist: ``run_examples(ModelRouter(load_routing(), clients))``.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from app.core.graph.state import EvidenceRecord, GraphClaim, Verdict, VerificationResult, initial_state
from app.core.graph.verifier import make_verify_claims
from app.evaluation.metrics import accuracy, confusion_matrix, macro_f1, per_class_prf

EXAMPLES_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "verify" / "examples.jsonl"
LABELS: tuple[str, ...] = tuple(v.value for v in Verdict)


class VerifyExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    claim: GraphClaim
    evidence: list[EvidenceRecord]
    gold_verdict: Verdict
    gold_supporting: list[str] = []
    gold_contradicting: list[str] = []

    def state(self) -> dict:
        s = initial_state(job_id=f"verify-{self.id}", video_id=self.id, media_uri="", pipeline_version="eval")
        s.update(claims=[self.claim], reranked_evidence={self.claim.claim_id: self.evidence})
        return s


def load_examples(path: Path | str = EXAMPLES_PATH) -> list[VerifyExample]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [VerifyExample.model_validate_json(line) for line in lines if line.strip()]


# --------------------------------------------------------------- offline callers


@dataclass
class _Result:
    output: Any
    record: Any = None


_BLOCK = re.compile(
    r'<<<UNTRUSTED kind="(?P<kind>[a-z_]+)" id="(?P<id>[^"]+)"[^>]*>>>\n(?P<text>.*?)\n<<<END UNTRUSTED',
    re.S,
)


def parse_blocks(content: str) -> list[tuple[str, str, str]]:
    """``(kind, id, text)`` for each fenced block of a rendered prompt."""
    return [(m["kind"], m["id"], m["text"]) for m in _BLOCK.finditer(content)]


class OracleCaller:
    """Answers each example with its gold label. Harness check only."""

    def __init__(self, examples: Sequence[VerifyExample]):
        self._by_claim = {e.claim.claim_id: e for e in examples}

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> _Result:
        claim_id = re.search(r"Judge claim (\S+) ", input["messages"][0]["content"]).group(1)
        e = self._by_claim[claim_id]
        return _Result({
            "verdict": e.gold_verdict.value, "supporting_evidence_ids": e.gold_supporting,
            "contradicting_evidence_ids": e.gold_contradicting, "explanation": "oracle", "limitations": [],
        })


_SUBJECTIVE = re.compile(r"\b(feels?|amazing|best|connected|inner self|love|comfort)\b", re.I)
_INDIRECT = re.compile(r"\b(mice|rats?|in vitro|cultured|cells|case report|single patient)\b", re.I)
_NEGATIVE = re.compile(
    r"\b(no (significant )?(difference|association|benefit|effect)|not associated|did not|"
    r"no clinical benefit|not reduce)\b", re.I,
)
_POSITIVE = re.compile(r"\b(significantly (reduced|improved|greater|fewer)|reduced|increased risk|effective)\b", re.I)


class HeuristicCaller:
    """Cue-word floor: subjective claim → NOT_VERIFIABLE; animal/lab/case papers are
    skipped; negative-finding phrases contradict, positive ones support. No population
    matching, no "relieves vs cures" reasoning; that's the point of measuring it."""

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> _Result:
        blocks = parse_blocks(input["messages"][0]["content"])
        claim = next((t for k, _, t in blocks if k == "claim"), "")
        if _SUBJECTIVE.search(claim):
            return _Result(self._out("NOT_VERIFIABLE", [], []))
        sup, con = [], []
        for kind, eid, text in blocks:
            if kind != "evidence_abstract" or _INDIRECT.search(text):
                continue
            if _NEGATIVE.search(text):
                con.append(eid)
            elif _POSITIVE.search(text):
                sup.append(eid)
        verdict = (
            "MIXED" if sup and con else "CONTRADICTED" if con else "SUPPORTED" if sup else "INSUFFICIENT_EVIDENCE"
        )
        return _Result(self._out(verdict, sup, con))

    @staticmethod
    def _out(verdict: str, sup: list[str], con: list[str]) -> dict:
        return {"verdict": verdict, "supporting_evidence_ids": sup, "contradicting_evidence_ids": con,
                "explanation": "heuristic", "limitations": []}


# ---------------------------------------------------------------------- metrics


def _div(a: float, b: float) -> Optional[float]:
    return a / b if b else None


def score(examples: Sequence[VerifyExample], results: dict[str, VerificationResult]) -> dict:
    gold = [e.gold_verdict.value for e in examples]
    pred = [results[e.id].verdict.value for e in examples]
    cited = retrieved_ok = 0
    agree = 0
    for e in examples:
        res = results[e.id]
        ids = [*res.supporting_evidence_ids, *res.contradicting_evidence_ids]
        allowed = {x.evidence_id for x in e.evidence}
        cited += len(ids)
        retrieved_ok += sum(i in allowed for i in ids)
        agree += (set(res.supporting_evidence_ids) == set(e.gold_supporting)
                  and set(res.contradicting_evidence_ids) == set(e.gold_contradicting))
    insufficient = [i for i, g in enumerate(gold) if g == Verdict.INSUFFICIENT_EVIDENCE.value]
    return {
        "n": len(examples),
        "accuracy": accuracy(gold, pred),
        "macro_f1": macro_f1(gold, pred, LABELS),
        "per_class": per_class_prf(gold, pred, LABELS),
        "confusion": confusion_matrix(gold, pred, LABELS),
        # §14 "tracked separately": insufficient evidence called contradiction.
        "insufficient_called_contradicted": sum(pred[i] == Verdict.CONTRADICTED.value for i in insufficient),
        "citation_validity": _div(retrieved_ok, cited),
        "citations_match_gold": _div(agree, len(examples)),
        "predictions": [
            {"id": e.id, "category": e.category, "gold": g, "pred": p,
             "supporting": results[e.id].supporting_evidence_ids,
             "contradicting": results[e.id].contradicting_evidence_ids}
            for e, g, p in zip(examples, gold, pred)
        ],
    }


def run_examples(caller: Any, examples: Sequence[VerifyExample] | None = None, **node_kwargs) -> dict:
    """Run the real node over every example with ``caller`` and score it."""
    examples = list(examples) if examples is not None else load_examples()
    node = make_verify_claims(caller, **node_kwargs)
    results = {e.id: node(e.state())["verification_results"][e.claim.claim_id] for e in examples}
    return score(examples, results)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--caller", choices=["heuristic", "oracle"], default="heuristic")
    ap.add_argument("--examples", default=str(EXAMPLES_PATH))
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    examples = load_examples(args.examples)
    caller = HeuristicCaller() if args.caller == "heuristic" else OracleCaller(examples)
    report = run_examples(caller, examples)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
