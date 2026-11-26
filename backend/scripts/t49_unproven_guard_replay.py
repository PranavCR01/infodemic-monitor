"""T49: replay the unproven guard over the tune split's frozen evidence (design §7).

For every **tune** video the golden set labels MISINFO (unproven), each golden
UNSUPPORTED claim is checked against the T38 frozen evidence for that claim (what the
pipeline's own retrieval kept, with the full search budget): does at least one record
pass the on-topic check (``app.core.graph.unproven_guard``)? If not, the claim becomes
INSUFFICIENT_EVIDENCE, and the backend judge is run on the video's golden stances and
verdicts to see whether the label stays MISINFO (unproven).

No model calls and no network. Test split never read: videos.csv rows are filtered to
``split == tune`` before anything else (``TuneSet`` does the same for claims), and the
frozen file is tune-only by construction (``FrozenEvidence`` refuses anything else).

Run from backend/:

    git fetch origin data/t38-frozen-evidence
    python scripts/t49_unproven_guard_replay.py --out ../evals/reports/T49
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.graph.state import GraphClaim, Verdict, VerificationResult  # noqa: E402
from app.core.graph.unproven_guard import (  # noqa: E402
    apply_unproven_guard, intervention_terms, on_topic_ids,
)
from app.evaluation import judge_crosscheck as xc  # noqa: E402
from app.evaluation.routing_experiment.frozen import MODES, FrozenEvidence  # noqa: E402
from app.evaluation.routing_experiment.golden import DirSource, TuneSet  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "research" / "claim-level" / "dataset"
FROZEN_REF = "origin/data/t38-frozen-evidence:frozen_evidence_tune.json"


def load_frozen(path: str | None) -> Path:
    if path:
        return Path(path)
    out = subprocess.run(["git", "show", FROZEN_REF], cwd=REPO, capture_output=True, check=True)
    tmp = Path(tempfile.mkdtemp()) / "frozen_evidence_tune.json"
    tmp.write_bytes(out.stdout)
    return tmp


def tune_unproven_ids(tune: TuneSet) -> list[str]:
    rows = csv.DictReader(io.StringIO((DATASET / "videos.csv").read_text(encoding="utf-8")))
    ids = [r["video_id"] for r in rows if (r.get("split") or "").strip() == "tune"
           and (r.get("misinfo_basis") or "").strip() == "unproven"]
    for vid in ids:
        tune.check_tune(vid)
    return [v for v in tune.video_ids if v in ids]


def replay(tune: TuneSet, frozen_path: Path, mode: str) -> dict:
    frozen = FrozenEvidence.load(frozen_path, mode)
    videos = []
    for vid in tune_unproven_ids(tune):
        video = tune.videos[vid]
        claims, details = [], []
        for row in video.claims:
            verdict = row.verdict
            if verdict == "UNSUPPORTED":
                raw = frozen.claims.get(row.key)
                evidence = list(frozen.entry(row.key).evidence) if raw is not None else []
                gc = GraphClaim(claim_id=row.claim_id, claim_text=row.text, claim_category="treatment_efficacy",
                                source_segment_ids=["s"], start_seconds=row.start, end_seconds=row.end)
                res = apply_unproven_guard(gc, evidence, VerificationResult(claim_id=row.claim_id, verdict=Verdict.UNSUPPORTED))
                terms = intervention_terms(row.text)
                details.append({
                    "claim": row.key, "text": row.text, "frozen": raw is not None,
                    "kept_records": len(evidence), "terms": list(terms.terms), "terms_source": terms.source,
                    "require_all": terms.require_all, "on_topic_ids": on_topic_ids(gc, evidence),
                    "after_guard": res.verdict.value,
                    "titles": [e.title[:120] for e in evidence[:5]],
                })
                verdict = res.verdict.value
            claims.append(xc.GoldenClaim(row.claim_id, row.stance, verdict,
                                         row.supporting, row.contradicting, "treatment_efficacy"))
        gv = xc.GoldenVideo(video_id=vid, out_of_scope=False, recorded_label="MISINFO",
                            recorded_review_reasons=(), claims=tuple(claims), recorded_basis="unproven")
        out = xc.run_backend(gv)
        videos.append({
            "video_id": vid, "label_after": out.label, "basis_after": out.basis,
            "kept": out.label == "MISINFO" and out.basis == "unproven",
            "reasons_after": sorted(out.reasons), "unsupported_claims": details,
        })
    return {"mode": mode, "videos": videos, "kept": sum(v["kept"] for v in videos), "total": len(videos)}


def render(results: list[dict], frozen_meta: dict) -> str:
    lines = ["# T49: unproven guard on the tune split's frozen evidence", "",
             f"Frozen evidence: `{FROZEN_REF}` (recorded {frozen_meta.get('created_at')}, "
             f"code {str(frozen_meta.get('code_revision'))[:12]}). Golden set: in-repo "
             "`research/claim-level/dataset`, tune split only. No model calls.", "",
             "The golden set has 12 MISINFO (unproven) videos in total; 5 are in the tune split. "
             "The other 7 are in the test split, which this task must not read.", ""]
    for res in results:
        lines += [f"## Evidence mode `{res['mode']}`: {res['kept']}/{res['total']} tune videos keep MISINFO (unproven)", "",
                  "| video | label after | basis | UNSUPPORTED claims → after guard |", "| --- | --- | --- | --- |"]
        for v in res["videos"]:
            cl = "; ".join(
                f"{d['claim'].split(':')[1]} → {d['after_guard']}"
                + ("" if d["frozen"] else " (no frozen record)")
                + f" ({d['kept_records']} kept, {len(d['on_topic_ids'])} on topic)"
                for d in v["unsupported_claims"])
            lines.append(f"| {v['video_id']} | {v['label_after']} | {v['basis_after'] or '-'} | {cl} |")
        lines.append("")
    lines += ["## Why the labels change", "",
              "- **Empty search** (v22 c2 eggs / macular degeneration; v120 c1 seawater, Spanish): the "
              "pipeline's retrieval kept 0 records. In `retrieved+cited` v22 also sees the golden-cited "
              "lutein review, which mentions egg yolks but not antioxidants in eggs, so it is not on topic.",
              "- **Condition-only search** (v141, v143: French 'a soap that treats/prevents skin cancer'): "
              "the planner recognised only 'cancer' and kept 10 generic cancer papers (pancreatic cancer, "
              "cachexia, angiogenesis). None mentions a soap; this is the same failure as the vitamin K c11.",
              "- **No recorded search** (v36 c6/c7/c10/c14: sea moss, burdock root): the T38 frozen file "
              "recorded only v36 c1-c5, so these claims replay as an empty search. Their real outcome "
              "depends on what retrieval finds for 'Irish sea moss' / 'burdock root'.",
              "- Where a video has other SUPPORTED claims (v22, v141) it becomes NO_MISINFO; otherwise "
              "CANNOT_RECOGNIZE with `nothing_judged` (v36, v120, v143).",
              "", "## Per claim (mode `retrieved`)", ""]
    for v in results[-1]["videos"]:
        for d in v["unsupported_claims"]:
            lines.append(f"- **{d['claim']}** \"{d['text'][:100]}\": terms {d['terms']} "
                         f"({d['terms_source']}, {'all' if d['require_all'] else 'any'}); "
                         f"{d['kept_records']} kept; on topic {d['on_topic_ids'] or 'none'}"
                         + (f"; first titles: {d['titles'][:3]}" if d["titles"] else ""))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--frozen", help="frozen_evidence_tune.json (default: git show from the data branch)")
    ap.add_argument("--out", help="directory for report.md and results.json")
    args = ap.parse_args(argv)
    tune = TuneSet(DirSource(DATASET))
    path = load_frozen(args.frozen)
    results = [replay(tune, path, m) for m in MODES]
    meta = FrozenEvidence.load(path).meta
    text = render(results, meta)
    print(text)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(text)
        (out / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
