"""Pick the 20% blind subset for inter-annotator agreement (section 14: "Two
independent labellers per item, with agreement measured (Cohen's kappa)").

Deterministic: the seed is fixed and recorded in REVIEW.md, so anyone can
reproduce exactly the same subset. Selection is over video_index.csv -- every
video is eligible, including ones that end up with no claims, because "this
video has no checkable health claims" is itself a judgement a second labeller
should confirm.
"""
import argparse
import csv
import random
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1]
INDEX = DATASET / "video_index.csv"

SEED = 20261121   # recorded in REVIEW.md; do not change without re-recording


def pick(fraction=0.20, seed=SEED):
    with open(INDEX, encoding="utf-8-sig", newline="") as f:
        ids = [r["video_id"] for r in csv.DictReader(f)]
    ids.sort()
    n = max(1, round(len(ids) * fraction))
    rng = random.Random(seed)
    return sorted(rng.sample(ids, n)), len(ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fraction", type=float, default=0.20)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    subset, total = pick(args.fraction, args.seed)
    print("seed=%d  fraction=%.2f  %d of %d videos"
          % (args.seed, args.fraction, len(subset), total))
    print(";".join(subset))


if __name__ == "__main__":
    main()
