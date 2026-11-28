"""T72: offline error analysis of the T66 tune videos under the shipped label rules.

No model or API calls, no spend. Inputs (all already in the repo):

- ``evals/reports/T66/videos/<id>.json``: stored final graph states (18 finished videos;
  v21 is excluded, it was cut off by the spend cap).
- ``evals/reports/T67/results.json``: per-video labels under the T67 replay configurations.
  The shipped configuration is "b" (T64 guard + change 1: keep the verdict when the critic
  budget runs out; changes 2 and 3 off, T69 context-mismatch rule off).
- ``research/claim-level/dataset/{videos,claims}.csv``: golden set (identical to
  ``origin/data/golden-label-set`` @ 92a731e; checked by the caller). Only the 18 T66 videos
  are read, all of them ``split == tune``; the script asserts that no test row is used.

The script re-applies, exactly as ``backend/scripts/t67_label_rules_replay.py`` does, the
T64 guard to the stored verdicts and runs the repo's own ``judge.judge`` and
``review_policy.evaluate`` under config b, asserts that this reproduces results.json's "b"
label for every video, and then runs counterfactuals by editing the state (dropping
claims, substituting gold verdicts / stances) and re-running the same judge.

Claim matching (system claim -> gold claim, same video, many-to-one allowed):
  match if  token Jaccard >= 0.30   (T66's threshold, on all word tokens)
        or  content-token containment >= 0.80 with >= 3 content tokens in the shorter text
  The best-scoring gold claim (by Jaccard, then containment) is the system claim's match.
  A gold claim counts as found if any system claim matches it (any score above threshold).
  ``MANUAL_OVERRIDES`` (off for the headline numbers) adds 4 pairs that were judged the same
  claim by eye but fall below the threshold; the counterfactuals are reported both ways.

Run from ``backend/``:
    python ../evals/reports/T72_error_analysis/analyze_t72.py
"""
from __future__ import annotations

import csv
import difflib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.graph import routing as rt  # noqa: E402
from app.core.graph.state import Stance, Verdict  # noqa: E402
from app.core.retrieval.find_study import topic_match  # noqa: E402
from app.core.graph import unproven_guard as ug  # noqa: E402
from app.core.text_tokens import word_tokens  # noqa: E402

_spec = importlib.util.spec_from_file_location("t67", BACKEND / "scripts" / "t67_label_rules_replay.py")
t67 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t67)

DATASET = REPO / "research" / "claim-level" / "dataset"
T66 = REPO / "evals" / "reports" / "T66" / "videos"
T67_RESULTS = REPO / "evals" / "reports" / "T67" / "results.json"
CONFIG_B = t67.CONFIGS["b"]  # (change1=True, change2=False, change3=False)

JACCARD_MIN = 0.30
CONTAIN_MIN = 0.80
CONTAIN_MIN_TOKENS = 3
STOP = set(
    "the a an of to and or is are was were be been it its this that these those in on for with as at by from "
    "you your we our they their i me my he she his her them not no do does did can could will would have has "
    "had so if but than then there here what which who just about into out up very more most also really all "
    "any some one like get got".split()
) | set("el la los las de del y o es son que en un una por para con se lo al le su sus no más muy".split())

# Pairs judged by eye to be the same claim but below the automatic threshold. Used only in
# the "auto + manual" sensitivity rows. (video, system claim) -> gold claim.
MANUAL_OVERRIDES = {
    ("v71", "c4"): "c2",   # "[biggest trigger of a clot] is the inhalation of smoke from cigarettes" = gold c2
    ("v122", "c5"): "c4",  # "... trae demencia" = gold c4 "[las estatinas] trae demencia"
    ("v65", "c5"): "c3",   # spot urine sodium "not the most accurate way" is inside gold c3
    ("v120", "c3"): "c1",  # "los minerales del agua de mar pueden eliminar esos metales pesados" ~ gold c1
}

VERDICTS = [v.value for v in Verdict]
STANCES = [s.value for s in Stance]


# ------------------------------------------------------------------ matching


def content_tokens(text: str) -> set[str]:
    return {w for w in word_tokens(text) if w not in STOP}


def similarity(a: str, b: str) -> dict:
    ta, tb = set(word_tokens(a)), set(word_tokens(b))
    jac = len(ta & tb) / max(1, len(ta | tb))
    ca, cb = content_tokens(a), content_tokens(b)
    n = min(len(ca), len(cb))
    cont = len(ca & cb) / max(1, n)
    dl = difflib.SequenceMatcher(None, " ".join(sorted(ca)), " ".join(sorted(cb))).ratio()
    ok = jac >= JACCARD_MIN or (cont >= CONTAIN_MIN and n >= CONTAIN_MIN_TOKENS)
    return {"jaccard": round(jac, 3), "containment": round(cont, 3), "difflib": round(dl, 3),
            "min_content_tokens": n, "match": ok}


def match_video(vid: str, sys_claims: list, gold_claims: list[dict], manual: bool) -> dict:
    """{system cid: {"gold": gold cid or None, "all": [gold cids above threshold], "score": {...}}}"""
    out = {}
    for c in sys_claims:
        scored = [(similarity(c.claim_text, g["claim_text"]), g["claim_id"]) for g in gold_claims]
        hits = [(s, gid) for s, gid in scored if s["match"]]
        best = max(scored, key=lambda x: (x[0]["jaccard"], x[0]["containment"]), default=(None, None))
        best_hit = max(hits, key=lambda x: (x[0]["jaccard"], x[0]["containment"]), default=(None, None))
        rec = {"gold": best_hit[1], "all": [gid for _, gid in hits],
               "score": best_hit[0] or best[0], "nearest": best[1], "manual": False}
        if manual and (vid, c.claim_id) in MANUAL_OVERRIDES and rec["gold"] is None:
            gid = MANUAL_OVERRIDES[(vid, c.claim_id)]
            rec.update(gold=gid, all=[gid], manual=True)
        out[c.claim_id] = rec
    return out


# ------------------------------------------------------------------ §9 on gold claims


def gold_section9(rows: list[dict]) -> tuple[str, str, list[str]]:
    """docs/target-system-design.md §9 pseudocode on raw gold stance/verdict (no T64 guard)."""
    def sel(st, verdicts):
        return [r["claim_id"] for r in rows if r["speaker_stance"] == st and r["claim_verdict"] in verdicts]
    ef = sel("ENDORSES", {"CONTRADICTED"})
    dt = sel("REFUTES", {"SUPPORTED"})
    up = sel("ENDORSES", {"UNSUPPORTED"})
    rf = sel("REFUTES", {"CONTRADICTED"})
    jd = [r["claim_id"] for r in rows if r["claim_verdict"] in ("SUPPORTED", "CONTRADICTED")]
    ro = sel("REFUTES", {"MIXED", "INSUFFICIENT_EVIDENCE"})
    if ef:
        return "MISINFO", "endorsed_contradicted", ef
    if dt:
        return "MISINFO", "refuted_supported", dt
    if up:
        return "MISINFO", "unproven", up
    if rf:
        return "DEBUNKING", "refuted_contradicted", rf
    if jd:
        return "NO_MISINFO", "judged_nothing_false_endorsed", jd
    if ro:
        return "CANNOT_RECOGNIZE", "refuted_unsettled", ro
    return "CANNOT_RECOGNIZE", "nothing_judged" if rows else "no_claims", []


# ------------------------------------------------------------------ state edits


def keep_only(state: dict, keep: set[str]) -> dict:
    s = dict(state)
    s["claims"] = [c for c in state.get("claims") or [] if c.claim_id in keep]
    for key in ("stance_results", "verification_results", "critic_results", "verification_revisions",
                "retrieval_attempts"):
        if state.get(key) is not None:
            s[key] = {k: v for k, v in state[key].items() if k in keep}
    return s


def substitute(state: dict, mapping: dict, gold_by_id: dict, *, verdict=True, stance=False) -> dict:
    """Replace matched claims' verdict (and optionally stance) with the matched gold claim's.

    The substituted verdict cites nothing (system citations are dropped, since they were
    chosen for a different verdict) and the claim's critic result is removed, so the §8
    budget logic does not touch it. ``verdicts_for_judge``'s T30 gate (UNSUPPORTED only for
    efficacy claims whose search budget was spent) still applies."""
    s = dict(state)
    vr = dict(state["verification_results"])
    sr = dict(state["stance_results"])
    cr = dict(state.get("critic_results") or {})
    for cid, m in mapping.items():
        g = m["gold"]
        if g is None or cid not in vr:
            continue
        gold = gold_by_id[g]
        if verdict:
            vr[cid] = vr[cid].model_copy(update={"verdict": Verdict(gold["claim_verdict"]),
                                                 "supporting_evidence_ids": [], "contradicting_evidence_ids": []})
            cr.pop(cid, None)
        if stance and cid in sr:
            sr[cid] = sr[cid].model_copy(update={"stance": Stance(gold["speaker_stance"])})
    s["verification_results"], s["stance_results"], s["critic_results"] = vr, sr, cr
    return s


def _norm_eid(eid: str) -> str:
    eid = eid.strip()
    return "ev_" + eid.split(":", 1)[1] if eid.upper().startswith("PMID:") else eid


def gold_cited_presence(g: dict, cid: str, state: dict) -> dict:
    """Which evidence IDs the gold claim cites are in the system claim's retrieved / kept pool
    (PMID:x == ev_x; reference URLs are compared verbatim and almost never match)."""
    cited = [x for x in (g["evidence_supporting"] + ";" + g["evidence_contradicting"]).split(";") if x.strip()]
    pool_r = {e.evidence_id for key in ("retrieved_evidence", "library_evidence", "found_study_evidence")
              for e in (state.get(key) or {}).get(cid) or []}
    pool_k = {e.evidence_id for e in (state.get("reranked_evidence") or {}).get(cid) or []}
    return {"gold_cited": cited, "in_retrieved": [x for x in cited if _norm_eid(x) in pool_r | pool_k],
            "in_kept": [x for x in cited if _norm_eid(x) in pool_k]}


def judge_b(state: dict) -> dict:
    with t67.config(*CONFIG_B):
        return t67.run_judge(state)


def effective_verdicts(state: dict) -> dict:
    with t67.config(*CONFIG_B):
        return rt.verdicts_for_judge(state)


# ------------------------------------------------------------------ main


def main() -> int:
    videos = {r["video_id"]: r for r in csv.DictReader(open(DATASET / "videos.csv", encoding="utf-8"))}
    t67res = json.loads(T67_RESULTS.read_text())
    t67_b = {r["video_id"]: r for r in t67res["A"]}
    ids = sorted(t67_b, key=lambda x: int(x[1:]))
    assert len(ids) == 18
    assert all(videos[v]["split"] == "tune" for v in ids), "a test-split video slipped in"
    gold_claims: dict[str, list[dict]] = {v: [] for v in ids}
    for r in csv.DictReader(open(DATASET / "claims.csv", encoding="utf-8")):
        if r["video_id"] in gold_claims:  # only the 18 tune videos are ever read
            gold_claims[r["video_id"]].append(r)

    out = {"inputs": {"t67_results": str(T67_RESULTS.relative_to(REPO)), "config": "b",
                      "matching": {"jaccard_min": JACCARD_MIN, "containment_min": CONTAIN_MIN,
                                   "containment_min_tokens": CONTAIN_MIN_TOKENS,
                                   "manual_overrides": {f"{k[0]}:{k[1]}": v for k, v in MANUAL_OVERRIDES.items()}}},
           "videos": {}}
    for vid in ids:
        rec = json.loads((T66 / f"{vid}.json").read_text())
        assert rec["status"] == "finished"
        state = t67.apply_t64_guard(t67._STATE.validate_python(rec["state"]))
        base = judge_b(state)
        ref = t67_b[vid]["b"]
        assert (base["label"], base["rule"], base["deciding"]) == (ref["label"], ref["rule"], ref["deciding"]), vid
        eff = effective_verdicts(state)
        stored = state["verification_results"]
        stances = state["stance_results"]
        claims = list(state["claims"])
        gold = gold_claims[vid]
        gold_by_id = {g["claim_id"]: g for g in gold}
        g_label, g_rule, g_dec = gold_section9(gold)
        evidence = {}
        for key in ("retrieved_evidence", "reranked_evidence", "library_evidence", "found_study_evidence"):
            for cid, recs in (state.get(key) or {}).items():
                for e in recs or []:
                    evidence.setdefault(cid, {}).setdefault(e.evidence_id, e)

        v_out = {"gold": videos[vid]["video_level_label"], "gold_basis": videos[vid]["misinfo_basis"] or None,
                 "gold_review_status": videos[vid]["review_status"], "gold_confidence": videos[vid]["confidence"],
                 "gold_notes": videos[vid]["notes"], "gold_reviewer_notes": videos[vid]["reviewer_notes"],
                 "case_tags": videos[vid]["case_tags"], "topic": videos[vid]["topic"],
                 "text_type": videos[vid]["text_type"],
                 "gold_section9": {"label": g_label, "rule": g_rule, "deciding": g_dec},
                 "system": base, "n_system_claims": len(claims), "n_gold_claims": len(gold)}
        assert g_label == v_out["gold"], (vid, g_label)

        for manual in (False, True):
            tag = "manual" if manual else "auto"
            m = match_video(vid, claims, gold, manual)
            matched = {cid for cid, x in m.items() if x["gold"]}
            found = {g for x in m.values() for g in x["all"]}
            cf1 = judge_b(keep_only(state, matched))
            cf2 = judge_b(substitute(state, m, gold_by_id, verdict=True))
            cf2s = judge_b(substitute(state, m, gold_by_id, verdict=True, stance=True))
            cf3 = judge_b(keep_only(substitute(state, m, gold_by_id, verdict=True, stance=True), matched))
            v_out[tag] = {"match": m, "n_matched_system": len(matched), "gold_found": sorted(found),
                          "cf_central_only": cf1, "cf_gold_verdicts": cf2,
                          "cf_gold_verdicts_and_stances": cf2s, "cf_central_gold_verdicts_and_stances": cf3}

        m = v_out["auto"]["match"]
        rows = []
        for c in claims:
            cid = c.claim_id
            e, s0 = eff.get(cid), stored.get(cid)
            cited = [*(e.supporting_evidence_ids if e else []), *(e.contradicting_evidence_ids if e else [])]
            cited_recs = [evidence.get(cid, {}).get(x) for x in cited]
            g = gold_by_id.get(m[cid]["gold"]) if m[cid]["gold"] else None
            rows.append({
                "claim_id": cid, "text": c.claim_text, "category": c.claim_category, "kind": c.claim_kind,
                "stance": stances[cid].stance.value if cid in stances else None,
                "stored_verdict": s0.verdict.value if s0 else None,
                "effective_verdict": e.verdict.value if e else None,
                "supporting": list(e.supporting_evidence_ids) if e else [],
                "contradicting": list(e.contradicting_evidence_ids) if e else [],
                "n_retrieved": len((state.get("retrieved_evidence") or {}).get(cid) or []),
                "n_kept": len((state.get("reranked_evidence") or {}).get(cid) or []),
                "cited": [{"id": x, "title": r.title if r else None,
                           "study_type": ug._study_type(r) if r else None,
                           "publication_type": list(r.publication_type or []) if r else None,
                           "year": r.publication_year if r else None,
                           "topic_match": bool(topic_match(c.claim_text, r.title or "", r.abstract or "")) if r else None}
                          for x, r in zip(cited, cited_recs)],
                "explanation": (s0.explanation if s0 else ""),
                "limitations": list(e.limitations) if e else [],
                "gold_match": m[cid]["gold"], "gold_all": m[cid]["all"], "match_score": m[cid]["score"],
                "nearest_gold": m[cid]["nearest"],
                "gold_stance": g["speaker_stance"] if g else None, "gold_verdict": g["claim_verdict"] if g else None,
                "gold_cited_in_system_pool": gold_cited_presence(g, cid, state) if g else None,
            })
        v_out["claims"] = rows
        v_out["gold_claims"] = [{"claim_id": g["claim_id"], "text": g["claim_text"], "stance": g["speaker_stance"],
                                 "verdict": g["claim_verdict"], "supporting": g["evidence_supporting"],
                                 "contradicting": g["evidence_contradicting"], "review_status": g["review_status"],
                                 "notes": g["notes"],
                                 "system_matches": [r["claim_id"] for r in rows if g["claim_id"] in r["gold_all"]]}
                                for g in gold]
        out["videos"][vid] = v_out

    # ------------------------------------------------------------ aggregates
    agg = {}
    V = out["videos"]
    for tag in ("auto", "manual"):
        n_sys = sum(v["n_system_claims"] for v in V.values())
        n_gold = sum(v["n_gold_claims"] for v in V.values())
        n_m = sum(v[tag]["n_matched_system"] for v in V.values())
        n_f = sum(len(v[tag]["gold_found"]) for v in V.values())
        a = {"system_claims": n_sys, "gold_claims": n_gold, "system_matched": n_m, "gold_found": n_f,
             "precision_proxy": round(n_m / n_sys, 3), "recall_proxy": round(n_f / n_gold, 3)}
        for cf in ("cf_central_only", "cf_gold_verdicts", "cf_gold_verdicts_and_stances",
                   "cf_central_gold_verdicts_and_stances"):
            ok = [vid for vid, v in V.items() if v[tag][cf]["label"] == v["gold"]]
            a[cf] = {"correct": len(ok), "n": len(V), "correct_ids": ok,
                     "labels": {vid: v[tag][cf]["label"] for vid, v in V.items()}}
        agg[tag] = a
    agg["system_correct"] = [vid for vid, v in V.items() if v["system"]["label"] == v["gold"]]

    allc = [c for v in V.values() for c in v["claims"]]
    allg = [g for v in V.values() for g in v["gold_claims"]]
    agg["verdict_share"] = {
        "system_effective": dict(Counter(c["effective_verdict"] for c in allc)),
        "system_stored": dict(Counter(c["stored_verdict"] for c in allc)),
        "gold": dict(Counter(g["verdict"] for g in allg)),
        "system_effective_matched_only": dict(Counter(c["effective_verdict"] for c in allc if c["gold_match"])),
        "system_effective_unmatched_only": dict(Counter(c["effective_verdict"] for c in allc if not c["gold_match"])),
    }
    matched = [c for c in allc if c["gold_match"]]
    agg["matched"] = {
        "n": len(matched),
        "verdict_agree": sum(c["effective_verdict"] == c["gold_verdict"] for c in matched),
        "stance_agree": sum(c["stance"] == c["gold_stance"] for c in matched),
        "verdict_confusion": dict(Counter(f"{c['gold_verdict']}->{c['effective_verdict']}" for c in matched)),
        "stance_confusion": dict(Counter(f"{c['gold_stance']}->{c['stance']}" for c in matched)),
    }
    # gold claims with a decisive verdict (SUPPORTED / CONTRADICTED) that the system made INSUFFICIENT
    dec = [(c["gold_verdict"], c["effective_verdict"]) for c in matched if c["gold_verdict"] in ("SUPPORTED", "CONTRADICTED")]
    agg["matched"]["gold_decisive_n"] = len(dec)
    agg["matched"]["gold_decisive_system_insufficient"] = sum(e == "INSUFFICIENT_EVIDENCE" for _, e in dec)
    agg["matched"]["gold_decisive_system_same"] = sum(g == e for g, e in dec)
    miss = [c for c in matched if c["gold_verdict"] in ("SUPPORTED", "CONTRADICTED")
            and c["effective_verdict"] == "INSUFFICIENT_EVIDENCE"]
    agg["matched"]["decisive_to_insufficient_detail"] = [
        {"video": vid, "claim": c["claim_id"], "gold": c["gold_match"], "gold_verdict": c["gold_verdict"],
         "n_kept": c["n_kept"], **c["gold_cited_in_system_pool"]}
        for vid, v in V.items() for c in v["claims"] if c in miss]
    pres = [d for d in agg["matched"]["decisive_to_insufficient_detail"] if d["gold_cited"]]
    agg["matched"]["decisive_to_insufficient_gold_evidence"] = {
        "with_gold_citations": len(pres),
        "some_gold_record_retrieved": sum(bool(d["in_retrieved"]) for d in pres),
        "some_gold_record_kept": sum(bool(d["in_kept"]) for d in pres)}
    # right label, right reason? (system deciding claims matched to a gold deciding claim)
    agg["deciding_overlap"] = {}
    for vid, v in V.items():
        gd = set(v["gold_section9"]["deciding"])
        sd = v["system"]["deciding"]
        mt = {c["claim_id"]: c["gold_all"] for c in v["claims"]}
        agg["deciding_overlap"][vid] = {
            "correct": v["system"]["label"] == v["gold"], "system_deciding": sd, "gold_deciding": sorted(gd),
            "system_deciding_matching_gold_deciding": [c for c in sd if set(mt.get(c, [])) & gd],
            "system_deciding_unmatched": [c for c in sd if not mt.get(c)]}
    out["aggregate"] = agg
    (HERE / "analysis.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")

    # ------------------------------------------------------------ material for reading
    L = ["# T72 per-video material (generated by analyze_t72.py; auto matching)", ""]
    for vid, v in V.items():
        s = v["system"]
        L += [f"## {vid}: gold {v['gold']} ({v['gold_basis']}) vs system {s['label']} ({s['basis'] or '-'})"
              f" {'OK' if s['label'] == v['gold'] else 'WRONG'}",
              f"- system rule `{s['rule']}` deciding {s['deciding']}",
              f"- gold §9 `{v['gold_section9']['rule']}` deciding {v['gold_section9']['deciding']}; "
              f"review_status {v['gold_review_status']}; tags {v['case_tags']}",
              f"- gold notes: {v['gold_notes']}", f"- reviewer notes: {v['gold_reviewer_notes']}",
              f"- CF central-only: {v['auto']['cf_central_only']['label']} ({v['auto']['cf_central_only']['rule']} "
              f"{v['auto']['cf_central_only']['deciding']}); CF gold verdicts: {v['auto']['cf_gold_verdicts']['label']} "
              f"({v['auto']['cf_gold_verdicts']['rule']} {v['auto']['cf_gold_verdicts']['deciding']}); "
              f"CF gold verdicts+stances: {v['auto']['cf_gold_verdicts_and_stances']['label']}; "
              f"manual-match CF1/CF2: {v['manual']['cf_central_only']['label']}/{v['manual']['cf_gold_verdicts']['label']}",
              "", "Gold claims:"]
        for g in v["gold_claims"]:
            L.append(f"- {g['claim_id']} [{g['stance']}/{g['verdict']}] sys={g['system_matches']} "
                     f"sup={g['supporting']} con={g['contradicting']} :: {g['text'][:200]}  // {g['notes'][:250]}")
        L += ["", "System claims:"]
        for c in v["claims"]:
            sc = c["match_score"] or {}
            L.append(f"- {c['claim_id']} [{c['stance']}/{c['effective_verdict']} (stored {c['stored_verdict']})] "
                     f"cat={c['category']} kept={c['n_kept']} gold={c['gold_match']} (nearest {c['nearest_gold']} "
                     f"j={sc.get('jaccard')} c={sc.get('containment')}) gold={c['gold_stance']}/{c['gold_verdict']} :: "
                     f"{c['text'][:200]}")
            if c["claim_id"] in s["deciding"]:
                for e in c["cited"]:
                    L.append(f"    - cited {e['id']} [{e['study_type']}; {e['year']}; topic_match={e['topic_match']}] {e['title']}")
                L.append(f"    - explanation: {c['explanation'][:600]}")
                L.append(f"    - limitations: {[x[:200] for x in c['limitations']]}")
        L.append("")
    (HERE / "material.md").write_text("\n".join(L) + "\n")
    print(json.dumps(agg, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
