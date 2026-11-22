"""Stance test set runner and metrics (target design §5, §14; issue #30).

Runs the real ``analyze_stance`` node over the labelled examples in
``app/tests/fixtures/stance/examples.jsonl`` and scores it. Metrics (§14 "Stance"):
macro F1 over the five stances, per-class precision/recall/F1, and **debunking recall
reported separately** (recall on gold REFUTES), plus the count of debunking claims read
as ENDORSES, the failure the design exists to prevent. Citation checks: every stance
cites at least one segment ID present in the input, and how often the cited IDs overlap
the labelled deciding segments.

Which model answers is up to the caller passed in. Without API keys this repo only runs
two offline callers, neither of which is a measurement of an LLM:

- ``keyword``: a deterministic keyword heuristic (roughly the T02 stub), the floor any
  model must beat. Its numbers are real, for that heuristic.
- ``oracle``: replays the gold labels; checks the harness itself, should score 1.0.

    python -m app.core.graph.stance_eval --caller keyword [--out results.json]

A real model run, once keys exist: ``run_examples(ModelRouter(load_routing(), clients))``.

Metric functions are local (written before T01's ``app.evaluation.metrics`` merged);
fold them into it later.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from app.core.graph.state import GraphClaim, OcrSegment, Stance, TranscriptSegment, initial_state
from app.core.graph.stance import make_analyze_stance

EXAMPLES_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "stance" / "examples.jsonl"
LABELS: tuple[str, ...] = tuple(s.value for s in Stance)


class StanceExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    transcript: list[TranscriptSegment]
    ocr: list[OcrSegment]
    claim: GraphClaim
    gold_stance: Stance
    gold_segment_ids: list[str]

    def state(self) -> dict:
        s = initial_state(job_id=f"stance-{self.id}", video_id=self.id, media_uri="", pipeline_version="eval")
        s.update(transcript_segments=self.transcript, ocr_segments=self.ocr, claims=[self.claim])
        return s

    @property
    def segment_ids(self) -> set[str]:
        return {t.segment_id for t in self.transcript} | {o.segment_id for o in self.ocr}


def load_examples(path: Path | str = EXAMPLES_PATH) -> list[StanceExample]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [StanceExample.model_validate_json(line) for line in lines if line.strip()]


# --------------------------------------------------------------- offline callers


@dataclass
class _Result:
    output: Any
    record: Any = None


class OracleCaller:
    """Answers each example with its gold label. Harness check only."""

    def __init__(self, examples: Sequence[StanceExample]):
        self._by_claim = {e.claim.claim_id: e for e in examples}

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> _Result:
        content = input["messages"][0]["content"]
        claim_id = re.match(r"CLAIM \(id ([^)]+)\)", content).group(1)
        e = self._by_claim[claim_id]
        return _Result({"stance": e.gold_stance.value, "stance_segment_ids": e.gold_segment_ids,
                        "rationale": "oracle"})


_NEGATION = re.compile(r"\b(myth|false|fake|not true|isn't true|doesn't|does not|won't|no link|retracted)\b|❌|✗", re.I)
_REPORT = re.compile(r"\b(says?|swears|claim(s|ing)?|according to|heard|comments)\b", re.I)
_HEDGE = re.compile(r"\b(studying|might|may|more research|mixed|question of)\b", re.I)


class KeywordCaller:
    """Deterministic keyword heuristic: the floor an LLM has to beat. No sarcasm
    handling, no speaker handling; that's the point of measuring it."""

    def call(self, step: str, input: Any, *, system: Optional[str] = None) -> _Result:
        content = input["messages"][0]["content"]
        block = content.split("<video_segments>\n", 1)[1].split("\n</video_segments>", 1)[0]
        segs = [json.loads(line) for line in block.splitlines() if line.strip()]
        for pattern, stance in ((_NEGATION, "REFUTES"), (_REPORT, "QUOTES"), (_HEDGE, "NEUTRAL")):
            hits = [s["id"] for s in segs if pattern.search(s["text"])]
            if hits:
                return _Result({"stance": stance, "stance_segment_ids": hits, "rationale": "keyword"})
        return _Result({"stance": "ENDORSES", "stance_segment_ids": [segs[0]["id"]], "rationale": "keyword"})


# ---------------------------------------------------------------------- metrics


def _div(a: float, b: float) -> Optional[float]:
    return a / b if b else None


def per_class(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str] = LABELS) -> dict:
    out = {}
    for lab in labels:
        tp = sum(g == lab and p == lab for g, p in zip(gold, pred))
        fp = sum(g != lab and p == lab for g, p in zip(gold, pred))
        fn = sum(g == lab and p != lab for g, p in zip(gold, pred))
        prec, rec = _div(tp, tp + fp), _div(tp, tp + fn)
        if tp == 0:
            f1 = 0.0 if (fp or fn) else None  # missed or wrongly predicted class scores 0
        else:
            f1 = 2 * prec * rec / (prec + rec)
        out[lab] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return out


def macro_f1(classes: dict) -> Optional[float]:
    """Mean F1 over classes present in gold; a present class with no predictions scores 0."""
    scores = [c["f1"] or 0.0 for c in classes.values() if c["support"]]
    return sum(scores) / len(scores) if scores else None


def score(examples: Sequence[StanceExample], results: dict[str, Any]) -> dict:
    gold = [e.gold_stance.value for e in examples]
    pred = [results[e.id].stance.value for e in examples]
    classes = per_class(gold, pred)
    debunk = [(e, results[e.id]) for e in examples if e.gold_stance == Stance.REFUTES]
    valid_cite = sum(
        bool(r.stance_segment_ids) and set(r.stance_segment_ids) <= e.segment_ids
        for e in examples for r in [results[e.id]]
    )
    overlap = sum(bool(set(results[e.id].stance_segment_ids) & set(e.gold_segment_ids)) for e in examples)
    return {
        "n": len(examples),
        "accuracy": _div(sum(g == p for g, p in zip(gold, pred)), len(gold)),
        "macro_f1": macro_f1(classes),
        "debunk_recall": classes[Stance.REFUTES.value]["recall"],
        "debunk_read_as_endorses": sum(r.stance == Stance.ENDORSES for _, r in debunk),
        "citation_validity": _div(valid_cite, len(examples)),
        "cites_gold_segment": _div(overlap, len(examples)),
        "per_class": classes,
        "predictions": [
            {"id": e.id, "category": e.category, "gold": e.gold_stance.value,
             "pred": results[e.id].stance.value, "cited": results[e.id].stance_segment_ids}
            for e in examples
        ],
    }


def run_examples(caller: Any, examples: Sequence[StanceExample] | None = None, **node_kwargs) -> dict:
    """Run the real node over every example with ``caller`` and score it."""
    examples = list(examples) if examples is not None else load_examples()
    node = make_analyze_stance(caller, **node_kwargs)
    results = {e.id: node(e.state())["stance_results"][e.claim.claim_id] for e in examples}
    return score(examples, results)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--caller", choices=["keyword", "oracle"], default="keyword")
    ap.add_argument("--examples", default=str(EXAMPLES_PATH))
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    examples = load_examples(args.examples)
    caller = KeywordCaller() if args.caller == "keyword" else OracleCaller(examples)
    report = run_examples(caller, examples)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
