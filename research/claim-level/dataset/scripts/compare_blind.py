"""Compare the blind model relabel (blind/model_relabel_*.csv) with the first
labelling pass (claims.csv / videos.csv) on the 41 blind-sample videos, and
write blind/model_relabel_comparison.md.

Claim matching rule (one-to-one, within a video):
  1. Tokenise each claim_text (lower-case, accents stripped, words of 3+
     letters, minus a stop-word list, bracketed editorial text kept).
  2. similarity = overlap coefficient |A & B| / min(|A|, |B|).
  3. time-compatible = the two [start, end] windows overlap once each is
     widened by 3 seconds.
  4. A pair is a candidate if time-compatible and similarity >= 0.34, or
     similarity >= 0.6 at any time.
  5. Candidates are accepted greedily, highest similarity first, each claim
     used at most once.
  6. MANUAL_MATCH / MANUAL_NOMATCH below then override the automatic result
     where the meaning says otherwise; each carries its reason.
Unmatched claims on either side count as extraction disagreements.

Model-model agreement between two Claude labelling passes. Not human
inter-annotator agreement; errors may be correlated.
"""
import csv, os, re, sys, unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.dirname(HERE)
BLIND = os.path.join(DS, "blind")
sys.path.insert(0, HERE)
import judge

STOP = set("""the and that this with your you are for from but not have has had
will can its it's into than then they them their there what when which who why
how all any just like really also very more most some such about over only one
two three been being was were our out get got going gonna lot much many those
these his her him she he que los las del una por con para como son mas pero sus
esta este esto puede pueden tus muy est les des une qui pour dans pas sur plus
ton tes elle ils avec cette vous tout""".split())

def toks(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return {w for w in re.findall(r"[a-z0-9]{3,}", s) if w not in STOP}

def sim(a, b):
    A, B = toks(a), toks(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))

def time_ok(a, b, tol=3.0):
    try:
        a0, a1 = float(a["start_seconds"]), float(a["end_seconds"])
        b0, b1 = float(b["start_seconds"]), float(b["end_seconds"])
    except ValueError:
        return False
    return a0 - tol <= b1 and b0 - tol <= a1

# (video, first-pass claim_id, model claim_id): reason
MANUAL_MATCH = {
    ("v20", "c2", "c2"): "same claim (decoction relieves bronchitis); bracket wording differs",
    ("v20", "c4", "c4"): "same claim (decoction improves sinusitis)",
    ("v24", "c1", "c1"): "same proposition phrased as negations: first pass 'Cheerios carry harmful glyphosate residues' (REFUTES), model 'Cheerios do not have high amounts' (ENDORSES)",
    ("v109", "c9", "c9"): "same claim (strokes from self-medicated Ozempic)",
    ("v109", "c11", "c11"): "same moment and topic (weight regain); different clause chosen",
    ("v141", "c1", "c1"): "same claim (soap treats / is a remedy for cancer)",
    ("v167", "c1", "c1"): "same claim (stage-four cancer reversed in 40 days); model folded the neem/turmeric diet into it",
    ("v167", "c2", "c2"): "same claim (deny cancer sugar/carbs and the cells die)",
}
MANUAL_NOMATCH = {}

def load(path, vids):
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["video_id"] in vids]

def kappa(pairs):
    n = len(pairs)
    if not n:
        return float("nan"), float("nan")
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    k = (po - pe) / (1 - pe) if pe < 1 else 1.0
    return po, k

def match(first, model):
    out, used_f, used_m = [], set(), set()
    vids = sorted({r["video_id"] for r in first} | {r["video_id"] for r in model})
    for (v, fc, mc), why in MANUAL_MATCH.items():
        f = next(r for r in first if r["video_id"] == v and r["claim_id"] == fc)
        m = next(r for r in model if r["video_id"] == v and r["claim_id"] == mc)
        out.append((f, m, sim(f["claim_text"], m["claim_text"]), "manual: " + why))
        used_f.add((v, fc)); used_m.add((v, mc))
    for v in vids:
        F = [r for r in first if r["video_id"] == v and (v, r["claim_id"]) not in used_f]
        M = [r for r in model if r["video_id"] == v and (v, r["claim_id"]) not in used_m]
        cand = []
        for f in F:
            for m in M:
                if (v, f["claim_id"], m["claim_id"]) in MANUAL_NOMATCH:
                    continue
                s = sim(f["claim_text"], m["claim_text"])
                if (time_ok(f, m) and s >= 0.34) or s >= 0.6:
                    cand.append((s, f, m))
        for s, f, m in sorted(cand, key=lambda x: -x[0]):
            if (v, f["claim_id"]) in used_f or (v, m["claim_id"]) in used_m:
                continue
            out.append((f, m, s, "auto"))
            used_f.add((v, f["claim_id"])); used_m.add((v, m["claim_id"]))
    uf = [r for r in first if (r["video_id"], r["claim_id"]) not in used_f]
    um = [r for r in model if (r["video_id"], r["claim_id"]) not in used_m]
    key = lambda r: (int(r["video_id"][1:]), int(r["claim_id"][1:]))
    out.sort(key=lambda x: key(x[0]))
    return out, sorted(uf, key=key), sorted(um, key=key)

if __name__ == "__main__":
    with open(os.path.join(BLIND, "model_relabel_videos.csv"), encoding="utf-8") as f:
        mv = list(csv.DictReader(f))
    vids = {r["video_id"] for r in mv}
    fv = load(os.path.join(DS, "videos.csv"), vids)
    fc = load(os.path.join(DS, "claims.csv"), vids)
    mc = load(os.path.join(BLIND, "model_relabel_claims.csv"), vids)
    pairs, uf, um = match(fc, mc)
    if "--dump" in sys.argv:
        for f, m, s, how in pairs:
            print(f"{f['video_id']} {f['claim_id']}~{m['claim_id']} {s:.2f} {how} | {f['claim_text'][:60]} || {m['claim_text'][:60]}")
        print("UNMATCHED first:", [(r['video_id'], r['claim_id'], r['claim_text'][:50]) for r in uf])
        print("UNMATCHED model:", [(r['video_id'], r['claim_id'], r['claim_text'][:50]) for r in um])
        sys.exit()
    import compare_blind_report
    compare_blind_report.write(fv, mv, fc, mc, pairs, uf, um, kappa,
                               os.path.join(BLIND, "model_relabel_comparison.md"))
