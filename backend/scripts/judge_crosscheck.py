"""Judge cross-check against the golden set's judge (T24, target design §9, §14).

Reads the golden set straight from its branch with ``git show`` (the branch is never
checked out, merged or modified), runs the backend judge and the golden set's own
``scripts/judge.py`` on every video's claims, and prints the agreement table and every
difference with the side that matches §9. No model calls, no network (beyond an
optional ``git fetch`` you run yourself).

Run from backend/:

    git fetch origin data/golden-label-set
    python scripts/judge_crosscheck.py                       # report from the branch
    python scripts/judge_crosscheck.py --write-fixture       # refresh the offline test fixture
    python scripts/judge_crosscheck.py --fixture             # report from the committed fixture

``--write-fixture`` copies the claim-level fields (no transcripts, no claim text) to
``app/tests/fixtures/golden_judge/claims.json`` and the golden ``judge.py`` verbatim to
``app/tests/fixtures/golden_judge/judge.py``, so ``test_judge_crosscheck.py`` runs
offline without the branch.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.evaluation import judge_crosscheck as xc  # noqa: E402

REF = "origin/data/golden-label-set"
DATASET = "research/claim-level/dataset"
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "app" / "tests" / "fixtures" / "golden_judge"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def load_module(name: str, source: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    exec(compile(source, f"<{name}>", "exec"), mod.__dict__)  # pure functions, no imports
    return mod


def load_fixture_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("golden_judge", FIXTURE_DIR / "judge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default=REF)
    ap.add_argument("--fixture", action="store_true", help="read the committed fixture instead of the branch")
    ap.add_argument("--write-fixture", action="store_true")
    ap.add_argument("--out", help="also write the markdown report here")
    args = ap.parse_args()

    if args.fixture:
        meta = json.loads((FIXTURE_DIR / "claims.json").read_text())
        videos = xc.from_fixture(meta["videos"])
        golden = load_fixture_module()
        source = f"fixture ({meta['source']['ref']} @ {meta['source']['commit'][:10]})"
    else:
        commit = git("rev-parse", args.ref).strip()
        judge_src = git("show", f"{commit}:{DATASET}/scripts/judge.py")
        videos = xc.load_golden_csvs(git("show", f"{commit}:{DATASET}/videos.csv"),
                                     git("show", f"{commit}:{DATASET}/claims.csv"))
        golden = load_module("golden_judge", judge_src)
        source = f"{args.ref} @ {commit[:10]}"
        if args.write_fixture:
            FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
            (FIXTURE_DIR / "judge.py").write_text(judge_src)
            meta = {
                "source": {
                    "ref": args.ref.removeprefix("origin/"), "commit": commit,
                    "judge_path": f"{DATASET}/scripts/judge.py",
                    "judge_blob_sha": git_blob_sha(judge_src.encode()),
                    "videos_blob_sha": git("rev-parse", f"{commit}:{DATASET}/videos.csv").strip(),
                    "claims_blob_sha": git("rev-parse", f"{commit}:{DATASET}/claims.csv").strip(),
                    "note": "Claim-level fields only (stance, verdict, cited evidence IDs) and "
                            "the recorded video label / review_reasons. Labels are data under "
                            "human review (PR #62), not ground truth. Regenerate with "
                            "scripts/judge_crosscheck.py --write-fixture.",
                },
                "videos": xc.to_fixture(videos),
            }
            (FIXTURE_DIR / "claims.json").write_text(json.dumps(meta, indent=1) + "\n")
            print(f"wrote {FIXTURE_DIR}", file=sys.stderr)

    results = xc.compare_all(videos, golden.judge, golden.review_reasons)
    report = xc.render_markdown(results, source)
    print(report)
    if args.out:
        Path(args.out).write_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
