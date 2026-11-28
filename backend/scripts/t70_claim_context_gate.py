"""T70 gate: claim context (switch ``routing.CLAIM_CONTEXT``), offline, no model calls, $0.

What runs and what is mocked is spelled out in ``app.evaluation.claim_context_gate``.
In short: real code end to end (extraction parsing and grounding, planner, verifier node,
judge, review policy) on recorded production rows; the model's context items and its
structured verify_v4 answers are hand-written, so this shows what the code does with such
replies, never what a model would reply.

Inputs (tune split only; the test split is never read):
1. v135 production fixtures (jobs cf2ea579, f85f2daa, 008c97a3).
2. Vitamin K production fixtures (5cc07f48, d2bf4179 real rows; 3d48e75e report rows).
3. A: the 18 finished T66 tune videos' stored states (``--t66``), and B: the golden set's
   own claims for the 48 in-scope tune videos (both as T69's replay).

Configurations for A and B (judge + review replay on stored verdicts):
- ``off``: as shipped (T64; T67 change 1 on, 2 off, 3 on; T69 off; T70 off).
- ``on``: T70 switch on, stored verdicts. No stored verdict carries a T70 code, so this
  shows only that turning the switch on changes nothing by itself.
- ``upper_soft``: T70 on, assuming EVERY endorsed / refuted CONTRADICTED claim had grounded
  specific context and the verifier, judging it as meant, softened it to
  INSUFFICIENT_EVIDENCE (``softened_by_context``). The worst case for "a MISINFO video
  softened to a milder label".
- ``upper_mismatch``: T70 on, assuming the verifier flagged a different setting on every
  CONTRADICTED verdict in context (T69's code; = T69's ``upper``).

    python scripts/t70_claim_context_gate.py --t66 ../evals/reports/T66/videos \\
        --out ../evals/reports/T70/results.json --report ../evals/reports/T70/gate.md
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import t67_label_rules_replay as t67  # noqa: E402
import t69_context_mismatch_replay as t69  # noqa: E402

from app.core.graph import claims as cl  # noqa: E402
from app.core.graph import judge as jg  # noqa: E402
from app.core.graph import routing as rt  # noqa: E402
from app.core.graph.stance import load_prompt  # noqa: E402
from app.core.graph.state import Stance, Verdict  # noqa: E402
from app.evaluation import claim_context_gate as g  # noqa: E402

CONFIGS = ("off", "on", "upper_soft", "upper_mismatch")
CONFIG_NAMES = {
    "off": "as shipped (T70 off)",
    "on": "T70 on, stored verdicts",
    "upper_soft": "T70 on, every endorsed/refuted CONTRADICTED claim softened as meant (upper bound)",
    "upper_mismatch": "T70 on, different setting flagged on every CONTRADICTED verdict (upper bound)",
}
SOFT = "judge:" + jg.FLAG_SOFTENED_BY_CONTEXT
MISMATCH = "judge:" + jg.FLAG_CONTEXT_MISMATCH
CHARS_PER_TOKEN = 4.0  # estimate: no tokenizer is available offline


@contextmanager
def config(name: str):
    old = (rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE, jg.ANALYSIS_INCOMPLETE_RULE,
           rt.CONTEXT_MISMATCH_RULE, rt.CLAIM_CONTEXT, jg.context_mismatch_kind)
    rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE, jg.ANALYSIS_INCOMPLETE_RULE = (
        True, False, True)
    rt.CONTEXT_MISMATCH_RULE = False
    rt.CLAIM_CONTEXT = name != "off"
    if name == "upper_mismatch":
        jg.context_mismatch_kind = (
            lambda v: "different_exposure_setting" if v.verdict == Verdict.CONTRADICTED else None)
    try:
        yield
    finally:
        (rt.KEEP_VERDICT_WHEN_CRITIC_BUDGET_EXHAUSTED, jg.THIN_CONTRADICTION_RULE, jg.ANALYSIS_INCOMPLETE_RULE,
         rt.CONTEXT_MISMATCH_RULE, rt.CLAIM_CONTEXT, jg.context_mismatch_kind) = old


def soften_all(state: dict) -> dict:
    """``upper_soft``: every ENDORSES / REFUTES + CONTRADICTED verdict becomes
    INSUFFICIENT_EVIDENCE with ``softened_by_context`` (what verify_v4 records when the
    claim is contradicted as stated but not as meant)."""
    stances = state.get("stance_results") or {}
    out = {}
    for cid, v in (state.get("verification_results") or {}).items():
        st = stances.get(cid)
        if v.verdict == Verdict.CONTRADICTED and st is not None and st.stance in (Stance.ENDORSES, Stance.REFUTES):
            v = v.model_copy(update={"verdict": Verdict.INSUFFICIENT_EVIDENCE, "supporting_evidence_ids": [],
                                     "contradicting_evidence_ids": [],
                                     "limitations": [*v.limitations, "setting_match:different",
                                                     rt.SOFTENED_LIMITATION]})
        out[cid] = v
    return {**state, "verification_results": out}


def replay(states):
    rows = []
    for vid, gold, state in states:
        row = {"video_id": vid, "gold": gold}
        for name in CONFIGS:
            with config(name):
                row[name] = t67.run_judge(soften_all(state) if name == "upper_soft" else state)
        rows.append(row)
    return rows


def softened_rows(rows):
    """Per video: was a MISINFO label (ours, off) turned into a milder one, and was it
    sent to review with a T70/T69 reason?"""
    out = []
    for r in rows:
        if r["off"]["label"] != "MISINFO" and r["gold"] != "MISINFO":
            continue
        entry = {"video_id": r["video_id"], "gold": r["gold"], "off": r["off"]["label"]}
        for k in ("on", "upper_soft", "upper_mismatch"):
            x = r[k]
            entry[k] = {"label": x["label"],
                        "softened": r["off"]["label"] == "MISINFO" and x["label"] != "MISINFO",
                        "reviewed_with_reason": x["review"] and any(y.startswith((SOFT, MISMATCH)) for y in x["reasons"])}
        out.append(entry)
    return out


def section(title, rows):
    lines = [f"### {title}: {len(rows)} videos", ""]
    summary = {}
    for key in CONFIGS:
        m, ok = t67.matrix(rows, key)
        reviewed = sum(r[key]["review"] for r in rows)
        changed = [r["video_id"] for r in rows if r[key]["label"] != r["off"]["label"]]
        worse = [r["video_id"] for r in rows if t67.worse(r["gold"], r["off"]["label"], r[key]["label"])]
        summary[key] = {"correct": ok, "n": len(rows), "accuracy": round(ok / len(rows), 4) if rows else None,
                        "reviewed": reviewed, "changed": changed, "worse": worse}
        lines.append(f"**{CONFIG_NAMES[key]}**: {ok}/{len(rows)} correct; sent to review {reviewed}/{len(rows)}; "
                     f"label changed vs off: {', '.join(changed) or 'none'}; worse vs gold: {', '.join(worse) or 'none'}")
        lines.append("")
    lines += ["| video | gold | " + " | ".join(CONFIGS) + " |", "|---|---|" + "---|" * len(CONFIGS)]
    for r in rows:
        cells = []
        for key in CONFIGS:
            x = r[key]
            mark = (" ✱" if any(y.startswith((SOFT, MISMATCH)) for y in x["reasons"]) else "") + (
                " ▼" if t67.worse(r["gold"], r["off"]["label"], x["label"]) else "")
            cells.append(f"{t67.lab(x)}{' (review)' if x['review'] else ''}{mark}")
        lines.append(f"| {r['video_id']} | {r['gold']} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines, summary


# ------------------------------------------------------------------ fixtures


def v135_section():
    out, lines = {}, ["## 1. v135 production fixtures (golden NO_MISINFO)", ""]
    lines += ["| job | stored (prod) | off, re-run | on: as meant | on: contradicted, setting flagged | "
              "on: model ignores context (failure mode) |", "|---|---|---|---|---|---|"]
    for job, path in sorted(g.V135.items()):
        fx = g.load(path)
        stored = g.stored_replay(fx)
        off = g.run(fx, flag_on=False)
        contexts, topic = g.v135_context(fx)
        ons = {sc: g.run(fx, flag_on=True, contexts=contexts, topic=topic, answer_for=g.skin_scenario(sc))
               for sc in g.SCENARIOS}
        out[job] = {"stored": stored, "off": off.summary(), **{f"on_{k}": v.summary() for k, v in ons.items()},
                    "skin_context": ons["as_meant"].contexts.get(g.SKIN), "topic": ons["as_meant"].topic,
                    "skin_plan_off": off.plans.get(g.SKIN), "skin_plan_on": ons["as_meant"].plans.get(g.SKIN),
                    "dropped_claims_on": ons["as_meant"].dropped_claims,
                    "skin_limitations_on": {k: v.limitations.get(g.SKIN) for k, v in ons.items()}}

        def cell(x):
            d = " ← skin claim decides" if g.SKIN in x["deciding"] else ""
            flags = [y.split(":")[1] for y in x["reasons"] if y.startswith((SOFT, MISMATCH))]
            return f"{x['label']}{' (review: ' + ', '.join(flags) + ')' if flags else (' (review)' if x['review'] else '')}{d}"
        lines.append(f"| {job} | {cell(stored)} | {cell(off.summary())} | " +
                     " | ".join(cell(ons[s].summary()) for s in g.SCENARIOS) + " |")
    lines.append("")
    return out, lines


def vitamin_k_section():
    out, lines = {}, ["## 2. Vitamin K production fixtures", "",
                      "| job | prod | off, re-run | on (mocked context on the vague claim) | same? |", "|---|---|---|---|---|"]
    for job, path in sorted(g.VITAMIN_K.items()):
        fx = g.load(path)
        off = g.run(fx, flag_on=False)
        contexts, topic = g.vitamin_k_context(fx)
        on = g.run(fx, flag_on=True, contexts=contexts, topic=topic)
        out[job] = {"prod": fx["result"]["label"], "off": off.summary(), "on": on.summary(),
                    "vague_plan_on": on.plans.get(g.VAGUE), "vague_context": on.contexts.get(g.VAGUE)}
        lines.append(f"| {job} | {fx['result']['label']} ({fx['result'].get('misinfo_basis') or ''}) | "
                     f"{off.label} | {on.label} | {'yes' if on.summary() == off.summary() else 'NO'} |")
    from app.tests.test_label_rules_t67 import state_from_3d48e75e

    s, _ = state_from_3d48e75e()
    res = {}
    for name in ("off", "on"):
        with config(name):
            res[name] = t67.run_judge(s)
    out["3d48e75e"] = res
    lines.append(f"| 3d48e75e (report rows, judge only) | NO_MISINFO | {res['off']['label']} | {res['on']['label']} | "
                 f"{'yes' if res['on'] == res['off'] else 'NO'} |")
    lines.append("")
    return out, lines


# ------------------------------------------------------------------ token increase


def est(text) -> float:
    return len(text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)) / CHARS_PER_TOKEN


def token_section():
    """Requests as built by the real code for the 008c97a3 and cf2ea579 fixtures."""
    out, lines = {}, ["## 4. Token increase per claim (estimate: characters / 4; no tokenizer offline)", ""]
    lines += ["| job | claims | extraction input +tok/claim | extraction output +tok/claim (mocked reply) | "
              "verifier input +tok/claim (in context / as stated) | verifier output +tok/claim |",
              "|---|---|---|---|---|---|"]
    for job in ("008c97a3", "cf2ea579"):
        fx = g.load(g.V135[job])
        contexts, topic = g.v135_context(fx)
        on = g.run(fx, flag_on=True, contexts=contexts, topic=topic, answer_for=g.skin_scenario("as_meant"))
        off = g.run(fx, flag_on=False)
        ts, os_, fused, block = g.segments(fx)
        piece_ids = {t.segment_id for t in ts} | {o.segment_id for o in os_}
        blocks = cl.block_sources(fused, piece_ids)
        v4 = load_prompt("extract_v4")
        prompt = cl.build_prompt(fused, blocks, v4)
        req_off = cl.build_request(prompt, cl.extract_tool(cl.categories_for("extract_v4")))
        req_on = on.extract_requests[0]
        ext_in = (est(req_on["input"]) + est(req_on["system"])) - (est(req_off) + est(prompt.system))
        reply = g.extract_reply(fx, block, contexts, topic)
        plain = {"claims": [{k: v for k, v in c.items() if k != "context"} for c in reply["claims"]]}
        ext_out = est(reply) - est(plain)
        n = len(on.verdicts) or 1
        vin_ctx, vin_plain = [], []
        off_by = {q["claim_id"]: q for q in off.verify_requests}
        ctx_ids = {q["claim_id"] for q in on.verify_requests if ":context" in q["input"]["messages"][0]["content"]}
        for q in on.verify_requests:
            # claim IDs line up: extract_v5 keeps the stored claims in the same time order
            base = off_by.get(q["claim_id"])
            if base is None:
                continue
            d = (est(q["input"]) + est(q["system"])) - (est(base["input"]) + est(base["system"]))
            (vin_ctx if q["claim_id"] in ctx_ids else vin_plain).append(d)
        vout = est({"evidence_context": "different_exposure_setting", "contradicted_as_stated": True})
        base_v = [est(q["input"]) + est(q["system"]) for q in off.verify_requests]
        sys_delta = est(on.verify_requests[0]["system"]) - est(off.verify_requests[0]["system"]) if base_v else 0
        out[job] = {"claims": len(reply["claims"]), "extraction_input_per_claim": round(ext_in / n, 1),
                    "extraction_output_per_claim": round(ext_out / n, 1),
                    "verifier_input_in_context": round(sum(vin_ctx) / len(vin_ctx), 1) if vin_ctx else None,
                    "verifier_input_as_stated": round(sum(vin_plain) / len(vin_plain), 1) if vin_plain else None,
                    "verifier_output_per_claim_max": round(vout, 1),
                    "extraction_input_total": round(ext_in), "verifier_calls": len(on.verify_requests),
                    "extraction_input_base_total": round(est(req_off) + est(prompt.system)),
                    "verifier_input_base_mean": round(sum(base_v) / len(base_v), 1) if base_v else None,
                    "verifier_system_prompt_delta": round(sys_delta, 1)}
        o = out[job]
        lines.append(f"| {job} | {o['claims']} | {o['extraction_input_per_claim']} | {o['extraction_output_per_claim']} | "
                     f"{o['verifier_input_in_context']} / {o['verifier_input_as_stated']} | ≤ {o['verifier_output_per_claim_max']} |")
    lines.append("")
    for job, o in out.items():
        lines.append(f"- {job}: extraction request {o['extraction_input_base_total']} → "
                     f"{o['extraction_input_base_total'] + o['extraction_input_total']} tokens per video "
                     f"(+{100 * o['extraction_input_total'] / o['extraction_input_base_total']:.0f}%); verifier request "
                     f"{o['verifier_input_base_mean']} tokens on average per claim; the longer verify_v4 system "
                     f"prompt alone adds {o['verifier_system_prompt_delta']} to every call "
                     f"(+{100 * o['verifier_input_as_stated'] / o['verifier_input_base_mean']:.0f}% as stated, "
                     f"+{100 * o['verifier_input_in_context'] / o['verifier_input_base_mean']:.0f}% in context).")
    lines.append("")
    return out, lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--t66", required=True)
    ap.add_argument("--frozen")
    ap.add_argument("--out")
    ap.add_argument("--report")
    args = ap.parse_args(argv)

    v135, l1 = v135_section()
    vk, l2 = vitamin_k_section()
    gold, claims = t67.tune_rows()
    a_states, excluded = t69.t66_states(args.t66, gold)
    b_states, missing = t69.golden_states(gold, claims, t67.load_frozen(args.frozen))
    a_rows, b_rows = replay(a_states), replay(b_states)
    la, sa = section("A. T66 stored states (tune)", a_rows)
    lb, sb = section("B. Golden claims (tune, in scope)", b_rows)
    soft_a, soft_b = softened_rows(a_rows), softened_rows(b_rows)
    tok, l4 = token_section()
    rev = t67.code_revision()

    def soft_table(name, entries):
        out = [f"**{name}**: every video whose label is MISINFO today (off) or in gold.", "",
               "| video | gold | off | on (stored) | upper_soft | upper_mismatch |", "|---|---|---|---|---|---|"]
        for e in entries:
            def c(k):
                x = e[k]
                tag = "SOFTENED" if x["softened"] else "kept"
                return f"{x['label']} ({tag}{', reviewed with T70/T69 reason' if x['softened'] and x['reviewed_with_reason'] else ''})"
            out.append(f"| {e['video_id']} | {e['gold']} | {e['off']} | {c('on')} | {c('upper_soft')} | {c('upper_mismatch')} |")
        return out + [""]

    head = [
        "# T70 gate: claim context (offline, no model calls, $0)", "",
        f"Code: `{rev}`. Tune split only. Baseline = as shipped (T64; T67 change 1 on, 2 off, 3 on; T69 off).",
        f"A excluded: {', '.join(excluded) or 'none'}. B evidence IDs not in the offline cache: {len(missing)}.", "",
        "**Mocked:** the extract_v5 context items and topic, and the verify_v4 structured answers and the skin "
        "claim's verdict as meant are hand-written. **Recorded:** claims, stances, kept evidence, stored verdicts. "
        "**Real code:** extraction parsing and grounding, planner, verifier node, judge, review policy. PubMed is "
        "not called. None of this shows what a model would answer.", "",
    ]
    l3 = ["## 3. T66 recorded videos (A) and golden claims (B)", ""] + la + lb + [
        "### MISINFO videos softened to a milder label, per video", ""] + soft_table("A", soft_a) + soft_table("B", soft_b)
    text = "\n".join(head + l1 + l2 + l3 + l4) + "\n"
    results = {"code_revision": rev, "mocked": "context items, topic, verify_v4 structured answers (see header)",
               "v135": v135, "vitamin_k": vk, "summary": {"A": sa, "B": sb},
               "softened": {"A": soft_a, "B": soft_b}, "tokens": tok, "excluded": excluded,
               "missing_evidence": missing, "A": a_rows, "B": b_rows}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(results, indent=1, default=str, ensure_ascii=False) + "\n")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text)
    print(json.dumps({"A": sa, "B": sb, "tokens": tok,
                      "v135": {j: {k: v["label"] for k, v in d.items() if isinstance(v, dict) and "label" in v}
                               for j, d in v135.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
