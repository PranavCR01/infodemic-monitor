"""T43 analysis over a routing run's ``per_item.json`` (written by the runner since T43).

For each step and candidate: the step metric re-computed from the saved outputs (must
equal report.json's score on the run's own golden commit), a 95% bootstrap CI, the
winner's paired margin CI, and the error breakdown (extraction categories; stance and
verify confusion matrices and every error). ``rescore`` does the same against another
golden commit: items whose claim was removed are dropped, claims added since the run
have no output and are listed as not run (never guessed).
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from app.evaluation import metrics as m
from app.evaluation.error_analysis import bootstrap as bs
from app.evaluation.error_analysis import extraction as ext
from app.evaluation.error_analysis import matching as mt
from app.evaluation.routing_experiment.golden import TuneSet
from app.evaluation.routing_experiment.items import STANCE_LABELS, VERDICT_LABELS, video_input
from app.evaluation.selection import label_macro_f1

LABELS = {"analyze_stance": list(STANCE_LABELS), "verify_claims": list(VERDICT_LABELS)}
TIE_MARGIN = 0.01


# ------------------------------------------------------------------ gold per item


def extraction_gold(tune: TuneSet, vid: str) -> list[ext.Claim]:
    return [ext.Claim(text=c.text, start=c.start, end=c.end, source=c.source) for c in tune.videos[vid].claims]


def label_gold(tune: TuneSet, step: str, key: str) -> Optional[str]:
    vid, _, cid = key.partition(":")
    v = tune.videos.get(vid)
    if v is None or v.out_of_scope:
        return None
    for c in v.claims:
        if c.claim_id == cid:
            g = c.stance if step == "analyze_stance" else c.verdict
            return g if g in LABELS[step] else None
    return None


def _pred_claims(output: Any) -> Optional[list[ext.Claim]]:
    if output is None:
        return None
    out = []
    for c in output:
        if isinstance(c, str):
            out.append(ext.Claim(text=c))
        else:
            out.append(ext.Claim(text=c.get("text", ""), start=c.get("start"), end=c.get("end"),
                                 source_segment_ids=tuple(c.get("source_segment_ids") or ())))
    return out


# ------------------------------------------------------------------ metrics on index sets


def _extract_metric(rows: Sequence[tuple[int, int, int]]):
    """rows: (matched, n_gold, n_pred) per item."""
    def f(idx: Sequence[int]) -> Optional[float]:
        a = sum(rows[i][0] for i in idx)
        g = sum(rows[i][1] for i in idx)
        p = sum(rows[i][2] for i in idx)
        if g and not p:
            return 0.0
        return mt.prf(a, g, p)["f1"]
    return f


def _label_metric(step: str, gold: Sequence[str], pred: Sequence[Optional[str]]):
    scorer = label_macro_f1(LABELS[step])

    def f(idx: Sequence[int]) -> Optional[float]:
        return scorer([gold[i] for i in idx], [pred[i] for i in idx])
    return f


# ------------------------------------------------------------------ per step


def _extract_rows(tune: TuneSet, items: list[dict], matcher: str) -> tuple[list[str], list[tuple[int, int, int]]]:
    ids, rows = [], []
    for it in items:
        vid = it["item_id"]
        v = tune.videos.get(vid)
        if v is None or v.out_of_scope:
            continue
        gold = extraction_gold(tune, vid)
        pred = _pred_claims(it.get("output")) or []
        g_text, p_text = [c.text for c in gold], [c.text for c in pred]
        if matcher == "strict":
            n = len(mt.strict_match(g_text, p_text))
        else:
            n = len(mt.meaning_match(g_text, p_text, [c.span for c in gold], [c.span for c in pred]))
        ids.append(vid)
        rows.append((n, len(gold), len(pred)))
    return ids, rows


def step_scores(step: str, per_cand: dict[str, list[dict]], tune: TuneSet, *, n: int = bs.DEFAULT_RESAMPLES,
                matcher: str = "strict") -> dict[str, Any]:
    """Score, CI, and the winner's paired margin CI over the items common to every
    candidate and present in ``tune``."""
    metrics: dict[str, Any] = {}
    item_ids: Optional[list[str]] = None
    not_run: list[str] = []
    for cand, items in per_cand.items():
        if step == "extract_claims":
            ids, rows = _extract_rows(tune, items, matcher)
            metrics[cand] = _extract_metric(rows)
        else:
            ids, gold, pred = [], [], []
            for it in items:
                g = label_gold(tune, step, it["item_id"])
                if g is None:
                    continue
                ids.append(it["item_id"])
                gold.append(g)
                pred.append(None if it.get("output") is None else str(it["output"]).upper())
            metrics[cand] = _label_metric(step, gold, pred)
        if item_ids is None:
            item_ids = ids
        elif ids != item_ids:
            raise ValueError(f"{step}: candidates were scored on different items; cannot pair them")
    item_ids = item_ids or []
    if step != "extract_claims":
        ran = set(item_ids)
        for vid, v in tune.videos.items():
            if v.out_of_scope:
                continue
            for c in v.claims:
                if label_gold(tune, step, f"{vid}:{c.claim_id}") and f"{vid}:{c.claim_id}" not in ran:
                    not_run.append(f"{vid}:{c.claim_id}")
    k = len(item_ids)
    res = {cand: bs.bootstrap_ci(k, f, n=n) for cand, f in metrics.items()}
    ranked = sorted(res, key=lambda c: -(res[c]["point"] if res[c]["point"] is not None else -1))
    out: dict[str, Any] = {"n_items": k, "candidates": res, "ranked": ranked, "not_run": sorted(not_run)}
    if len(ranked) >= 2:
        w, r = ranked[0], ranked[1]
        out["winner"] = w
        out["runner_up"] = r
        out["margin"] = bs.paired_margin_ci(k, metrics[w], metrics[r], n=n)
        out["tie"] = (out["margin"]["point"] or 0.0) <= TIE_MARGIN
    elif ranked:
        out["winner"] = ranked[0]
    return out


def extraction_errors(items: list[dict], tune: TuneSet) -> tuple[dict, list[ext.VideoErrors], dict]:
    videos, texts = [], {}
    for it in items:
        vid = it["item_id"]
        v = tune.videos.get(vid)
        if v is None or v.out_of_scope:
            continue
        vi = video_input(tune, vid)
        tr = " ".join(s.text for s in vi.transcript)
        sc = " ".join(s.text for s in vi.ocr)
        gold = extraction_gold(tune, vid)
        pred = _pred_claims(it.get("output")) or []
        videos.append(ext.categorise(vid, gold, pred, transcript_text=tr, screen_text=sc))
        texts[vid] = (gold, pred)
    return ext.summarise(videos), videos, texts


def label_errors(step: str, items: list[dict], tune: TuneSet) -> dict[str, Any]:
    gold, pred, errors = [], [], []
    for it in items:
        g = label_gold(tune, step, it["item_id"])
        if g is None:
            continue
        p = None if it.get("output") is None else str(it["output"]).upper()
        gold.append(g)
        pred.append(p or "__none__")
        if p != g:
            vid, _, cid = it["item_id"].partition(":")
            text = next((c.text for c in tune.videos[vid].claims if c.claim_id == cid), "")
            errors.append({"key": it["item_id"], "gold": g, "pred": p, "text": text})
    labels = LABELS[step]
    out = {"confusion": m.confusion_matrix(gold, pred, labels), "errors": errors, "n": len(gold)}
    if step == "analyze_stance":
        out["refutes_errors"] = [e for e in errors if e["gold"] == "REFUTES"]
        out["n_refutes"] = sum(g == "REFUTES" for g in gold)
    else:
        out["insufficient_called_contradicted"] = [
            e for e in errors if e["gold"] in ("INSUFFICIENT_EVIDENCE", "UNSUPPORTED") and e["pred"] == "CONTRADICTED"]
    return out


def analyze(per_item: dict, tune: TuneSet, *, rescore_tune: Optional[TuneSet] = None,
            n: int = bs.DEFAULT_RESAMPLES) -> dict[str, Any]:
    """Everything T43 asks for, from a per_item.json payload."""
    steps = per_item.get("steps") or {}
    out: dict[str, Any] = {"golden": tune.source.describe(), "steps": {}}
    for step, per_cand in steps.items():
        s: dict[str, Any] = {"scores": step_scores(step, per_cand, tune, n=n)}
        if step == "extract_claims":
            s["scores_meaning"] = step_scores(step, per_cand, tune, n=n, matcher="meaning")
            s["errors"] = {c: extraction_errors(items, tune)[0] for c, items in per_cand.items()}
        else:
            s["errors"] = {c: label_errors(step, items, tune) for c, items in per_cand.items()}
        if rescore_tune is not None:
            s["rescore"] = step_scores(step, per_cand, rescore_tune, n=n)
            s["rescore_golden"] = rescore_tune.source.describe()
            s["winner_changes"] = s["rescore"].get("winner") != s["scores"].get("winner")
        out["steps"][step] = s
    return out
