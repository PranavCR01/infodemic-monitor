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

# Each delivery is sampled on its own, so adding a batch never changes the
# subset already handed to a second labeller. Batch 1 is the collector bundle
# (v01-v82); batch 2 starts at v83 (scripts/add_batch2.py).
BATCHES = {"1": (1, 82), "2": (83, 10 ** 6)}


def batch_of(video_id):
    n = int(video_id[1:])
    for name, (lo, hi) in BATCHES.items():
        if lo <= n <= hi:
            return name
    raise ValueError(video_id)


def pick(fraction=0.20, seed=SEED, batch="1"):
    with open(INDEX, encoding="utf-8-sig", newline="") as f:
        ids = [r["video_id"] for r in csv.DictReader(f)
               if batch_of(r["video_id"]) == batch]
    ids.sort()
    n = max(1, round(len(ids) * fraction))
    rng = random.Random(seed)
    return sorted(rng.sample(ids, n), key=lambda v: int(v[1:])), len(ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fraction", type=float, default=0.20)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--batch", default="1", choices=sorted(BATCHES))
    args = ap.parse_args()
    subset, total = pick(args.fraction, args.seed, args.batch)
    print("batch %s  seed=%d  fraction=%.2f  %d of %d videos"
          % (args.batch, args.seed, args.fraction, len(subset), total))
    print(";".join(subset))


if __name__ == "__main__":
    main()
