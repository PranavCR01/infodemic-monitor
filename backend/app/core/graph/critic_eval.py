"""Critic test set runner and metrics (target design §8, §14; issue #34).

Runs the real ``critique_verification`` node over the labelled examples in
``app/tests/fixtures/critic/examples.jsonl``. Each example is a claim, its evidence and a
*proposed* verdict; half the verdicts carry a planted defect (animal- or lab-only
evidence, absence called contradiction, a fabricated citation, "relieves" judged as
"cures", wrong population, an ignored meta-analysis, an off-topic citation), half are
right. Reported, as §14 asks for the critic:

- **defect detection** (``errors_caught``): share of wrong verdicts the critic challenged
  (any decision other than APPROVE);
- **unnecessary-retry rate**: share of the critic's challenges that hit a right verdict;
- decision accuracy against the labelled decision, and results per defect type.

The set is small (16 claims), synthetic ("Synthetic." abstracts, fake PMIDs) and
labelled by the build agent, not two people. It exercises the node and the metrics; it
is not evidence of model quality.

Offline callers (no API keys here):

- ``code``: the critic with no model (``caller=None``), i.e. its deterministic checks.
  Its numbers are real for the code layer and are the floor a model must add to.
- ``oracle``: replays the labelled decisions; checks the harness (should score 1.0 / 0.0).
- ``always``: challenges everything; shows what the unnecessary-retry rate penalises.

    python -m app.core.graph.critic_eval --caller code [--out results.json]

A real model run, once keys exist: ``run_examples(ModelRouter(load_routing(), clients))``.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from app.core.graph.critic import make_critique_verification
from app.core.graph.state import (
    CriticDecision,
    CriticResult,
    EvidenceRecord,
    GraphClaim,
    Stance,
    StanceResult,
    Verdict,
    VerificationResult,
    initial_state,
)
from app.evaluation.metrics import accuracy, critic_metrics

EXAMPLES_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "critic" / "examples.jsonl"


class CriticExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str  # "defect" or "correct"
    defect: Optional[str] = None
    claim: GraphClaim
    stance: Stance
    evidence: list[EvidenceRecord]
    verification: VerificationResult
    verifier_wrong: bool
    gold_verdict: Verdict
    gold_decision: CriticDecision

    def state(self) -> dict:
        cid = self.claim.claim_id
        s = initial_state(job_id=f"critic-{self.id}", video_id=self.id, media_uri="", pipeline_version="eval")
        s.update(
            claims=[self.claim],
            stance_results={cid: StanceResult(claim_id=cid, stance=self.stance, stance_segment_ids=["t1"])},
            retrieved_evidence={cid: self.evidence},
            reranked_evidence={cid: self.evidence},
            retrieval_attempts={cid: 1},
            verification_results={cid: self.verification},
        )
        return s


def load_examples(path: Path | str = EXAMPLES_PATH) -> list[CriticExample]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [CriticExample.model_validate_json(line) for line in lines if line.strip()]


# --------------------------------------------------------------- offline callers


@dataclass
class _Result:
    output: Any
    record: Any = None


def _claim_id(request: dict) -> str:
    return re.search(r"Review the verdict on claim (\S+) ", request["messages"][0]["content"]).group(1)


class OracleCaller:
    """Answers each example with its labelled decision. Harness check only."""

    def __init__(self, examples: Sequence[CriticExample]):
        self._by_claim = {e.claim.claim_id: e for e in examples}

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> _Result:
        e = self._by_claim[_claim_id(input)]
        d = e.gold_decision
        return _Result({
            "decision": d.value,
            "issues": [] if d == CriticDecision.APPROVE else [f"oracle: {e.defect}"],
            "suggested_queries": [e.claim.claim_text] if d == CriticDecision.RETRIEVE_MORE else [],
            "requires_review": d == CriticDecision.ESCALATE,
        })


class AlwaysChallengeCaller:
    """Asks for a revision every time."""

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> _Result:
        return _Result({"decision": "REVISE_VERIFICATION", "issues": ["always"], "suggested_queries": [],
                        "requires_review": False})


# ---------------------------------------------------------------------- metrics


def score(examples: Sequence[CriticExample], results: dict[str, CriticResult]) -> dict:
    items = [(e.verifier_wrong, results[e.id].decision != CriticDecision.APPROVE) for e in examples]
    cm = critic_metrics(items)
    by_defect: dict[str, dict] = defaultdict(lambda: {"n": 0, "challenged": 0})
    for e in examples:
        key = e.defect or "none (correct verdict)"
        by_defect[key]["n"] += 1
        by_defect[key]["challenged"] += results[e.id].decision != CriticDecision.APPROVE
    return {
        "n": len(examples),
        "n_wrong_verdicts": sum(w for w, _ in items),
        "defect_detection_rate": cm["errors_caught"],
        "unnecessary_retry_rate": cm["unnecessary_retry_rate"],
        "interventions": sum(i for _, i in items),
        "decision_accuracy": accuracy(
            [e.gold_decision.value for e in examples], [results[e.id].decision.value for e in examples]
        ),
        "by_defect": dict(by_defect),
        "predictions": [
            {"id": e.id, "defect": e.defect, "gold": e.gold_decision.value,
             "pred": results[e.id].decision.value, "checks": results[e.id].checks,
             "issues": results[e.id].issues}
            for e in examples
        ],
    }


def run_examples(caller: Any, examples: Sequence[CriticExample] | None = None, **node_kwargs) -> dict:
    """Run the real node over every example with ``caller`` (``None`` = code checks only)."""
    examples = list(examples) if examples is not None else load_examples()
    node = make_critique_verification(caller, **node_kwargs)
    results = {e.id: node(e.state())["critic_results"][e.claim.claim_id] for e in examples}
    return score(examples, results)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--caller", choices=["code", "oracle", "always"], default="code")
    ap.add_argument("--examples", default=str(EXAMPLES_PATH))
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    examples = load_examples(args.examples)
    caller = {"code": None, "oracle": OracleCaller(examples), "always": AlwaysChallengeCaller()}[args.caller]
    report = run_examples(caller, examples)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
