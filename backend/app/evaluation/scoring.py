"""Score a set of predictions against the gold dataset.

``score_predictions`` computes every metric it can from what the system
produced; metrics the system can't support (the baseline has no claims) come
back as ``None``. Tracked failure modes are counted and listed by item, never
averaged into another number (section 14).
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from app.evaluation import metrics as m
from app.evaluation.dataset import GoldClaim, GoldVideo
from app.evaluation.records import PredictedClaim, VideoPrediction

RETRIEVAL_K = 5

# Names a run config may request. Lower-is-better metrics are listed so the
# comparison knows which direction is an improvement.
METRIC_NAMES = (
    "macro_f1", "accuracy", "per_class_precision", "per_class_recall", "per_class_f1",
    "confusion_matrix", "false_misinfo_on_debunking",
    "claim_precision", "claim_recall", "claim_f1", "claim_source_accuracy",
    "stance_macro_f1", "stance_debunk_recall",
    "verification_prf", "verification_macro_f1",
    "retrieval_recall_at_k", "retrieval_ndcg_at_k",
    "citation_validity", "citation_support",
    "calibration_error", "reliability_diagram",
    "review_share", "review_overturn_rate",
    "critic_errors_caught", "critic_unnecessary_retries",
    "latency", "latency_median_ms", "latency_p95_ms", "cost", "cost_per_video", "error_rate",
)
LOWER_IS_BETTER = frozenset({
    "false_misinfo_on_debunking", "calibration_error", "critic_unnecessary_retries",
    "latency_median_ms", "latency_p95_ms", "cost_per_video", "error_rate", "review_overturn_rate",
})

TRACKED_FAILURES = (
    "debunking_as_promotion",
    "citation_laundering",
    "insufficient_called_contradicted",
    "speech_screen_disagreement",
    "prompt_injection",
    "critic_ignored",
)


def score_predictions(
    videos: Sequence[GoldVideo],
    predictions: dict[str, VideoPrediction],
    *,
    claim_match_threshold: float = 0.5,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (metrics, tracked_failures) for the given gold videos."""
    preds = [predictions[v.video_id] for v in videos]
    gold_labels = [v.label.value for v in videos]
    pred_labels = [p.label.value for p in preds]

    out: dict[str, Any] = {name: None for name in METRIC_NAMES}
    if videos:
        prf = m.per_class_prf(gold_labels, pred_labels, m.LABELS)
        out.update(
            macro_f1=m.macro_f1(gold_labels, pred_labels, m.LABELS),
            accuracy=m.accuracy(gold_labels, pred_labels),
            per_class_precision={k: v["precision"] for k, v in prf.items()},
            per_class_recall={k: v["recall"] for k, v in prf.items()},
            per_class_f1={k: v["f1"] for k, v in prf.items()},
            confusion_matrix=m.confusion_matrix(gold_labels, pred_labels, m.LABELS),
            error_rate=sum(1 for p in preds if p.error) / len(preds),
        )
        debunk = [p for v, p in zip(videos, preds) if v.label.value == "DEBUNKING"]
        if debunk:
            out["false_misinfo_on_debunking"] = sum(p.label.value == "MISINFO" for p in debunk) / len(debunk)

    # Confidence calibration on the video label.
    conf = [(p.confidence, g == p.label.value) for g, p in zip(gold_labels, preds) if p.confidence is not None]
    if conf:
        cs, ok = [c for c, _ in conf], [o for _, o in conf]
        out["calibration_error"] = m.expected_calibration_error(cs, ok)
        out["reliability_diagram"] = m.reliability_bins(cs, ok)

    # Review.
    rv = m.review_metrics([p.review_required for p in preds], [p.review_overturned for p in preds])
    out["review_share"], out["review_overturn_rate"] = rv["review_share"], rv["overturn_rate"]

    # Operations.
    lat = [p.latency_ms for p in preds if p.latency_ms is not None]
    if lat:
        out["latency"] = m.latency_summary(lat)
        out["latency_median_ms"], out["latency_p95_ms"] = out["latency"]["median_ms"], out["latency"]["p95_ms"]
    costs = [p.cost_usd for p in preds]
    known = [c for c in costs if c is not None]
    out["cost"] = {
        "total_usd": sum(known) if known else None,
        "videos_with_unknown_cost": len(costs) - len(known),
    }
    out["cost_per_video"] = sum(known) / len(known) if known else None

    pairs = _claim_pairs(videos, preds, claim_match_threshold)
    out.update(_claim_metrics(videos, preds, pairs))

    return out, _tracked_failures(videos, preds, pairs)


# --- claims -----------------------------------------------------------------

def _claim_pairs(videos, preds, threshold) -> list[tuple[GoldVideo, GoldClaim, PredictedClaim]]:
    pairs = []
    for v, p in zip(videos, preds):
        if not p.claims:
            continue
        for gi, pi, _ in m.match_claims([c.claim_text for c in v.claims], [c.claim_text for c in p.claims], threshold):
            pairs.append((v, v.claims[gi], p.claims[pi]))
    return pairs


def _claim_metrics(videos, preds, pairs) -> dict[str, Any]:
    out: dict[str, Any] = {}
    with_claims = [(v, p) for v, p in zip(videos, preds) if p.claims is not None]
    if not with_claims:
        return out  # system produces no claims: claim-level metrics are not applicable

    n_gold = sum(len(v.claims) for v, _ in with_claims)
    n_pred = sum(len(p.claims) for _, p in with_claims)
    ext = m.extraction_prf(len(pairs), n_gold, n_pred)
    out.update(claim_precision=ext["precision"], claim_recall=ext["recall"], claim_f1=ext["f1"])

    src = [(g.source, c.source) for _, g, c in pairs if g.source and c.source]
    out["claim_source_accuracy"] = m.accuracy([a for a, _ in src], [b for _, b in src]) if src else None

    st = [(g.stance, c.stance or "UNCLEAR") for _, g, c in pairs]
    if st:
        gs, ps = [a for a, _ in st], [b for _, b in st]
        out["stance_macro_f1"] = m.macro_f1(gs, ps, m.STANCE_LABELS)
        out["stance_debunk_recall"] = m.per_class_prf(gs, ps, m.STANCE_LABELS)["REFUTES"]["recall"]

    ver = [(g.verdict, c.verdict) for _, g, c in pairs if c.verdict]
    if ver:
        gs, ps = [a for a, _ in ver], [b for _, b in ver]
        out["verification_prf"] = m.per_class_prf(gs, ps, m.VERDICTS)
        out["verification_macro_f1"] = m.macro_f1(gs, ps, m.VERDICTS)

    rec, ndcg = [], []
    for _, g, c in pairs:
        if g.relevant_pmids and c.retrieved:
            ranked = [e.pmid for e in c.retrieved if e.pmid]
            rec.append(m.recall_at_k(g.relevant_pmids, ranked, RETRIEVAL_K))
            ndcg.append(m.ndcg_at_k(g.relevant_pmids, ranked, RETRIEVAL_K))
    out["retrieval_recall_at_k"] = _mean(rec)
    out["retrieval_ndcg_at_k"] = _mean(ndcg)

    valid = total = 0
    for _, p in with_claims:
        for c in p.claims:
            v, t = m.citation_validity(c.cited_evidence_ids, [e.evidence_id for e in c.retrieved])
            valid, total = valid + v, total + t
    out["citation_validity"] = valid / total if total else None

    sup = [ok for _, _, ok in _citation_support_items(pairs)]
    out["citation_support"] = sum(sup) / len(sup) if sup else None

    crit = [
        ((c.initial_verdict or c.verdict) != g.verdict, any(d != "APPROVE" for d in c.critic_decisions))
        for _, g, c in pairs if c.critic_decisions and (c.initial_verdict or c.verdict)
    ]
    if crit:
        cm = m.critic_metrics(crit)
        out["critic_errors_caught"] = cm["errors_caught"]
        out["critic_unnecessary_retries"] = cm["unnecessary_retry_rate"]
    return out


def _citation_support_items(pairs):
    """(claim key, evidence id, supported?) for cited papers on claims with gold relevant PMIDs.

    Until per-citation support labels exist, "supports" is approximated as
    "is one of the papers the labellers recorded as bearing on this claim".
    IDs that were never retrieved are excluded: those are citation-validity
    failures, counted there, not laundering of a real paper.
    """
    for v, g, c in pairs:
        if not g.relevant_pmids:
            continue
        by_id = {e.evidence_id: e.pmid for e in c.retrieved}
        for eid in c.cited_evidence_ids:
            if eid not in by_id:
                continue
            yield f"{v.video_id}/{g.claim_id}", eid, by_id.get(eid) in set(g.relevant_pmids)


# --- tracked failure modes ----------------------------------------------------

def _tracked_failures(videos, preds, pairs) -> dict[str, Any]:
    def bucket(items: list[str], of: Optional[int]) -> dict:
        return {"count": len(items), "of": of, "items": items}

    debunk_claims = [f"{v.video_id}/{g.claim_id}" for v, g, c in pairs
                     if g.stance == "REFUTES" and c.stance == "ENDORSES"]
    debunk_videos = [v.video_id for v, p in zip(videos, preds)
                     if v.label.value == "DEBUNKING" and p.label.value == "MISINFO"]
    n_refutes = sum(1 for _, g, _ in pairs if g.stance == "REFUTES")
    n_debunk = sum(1 for v in videos if v.label.value == "DEBUNKING")

    laundering = [f"{k}:{eid}" for k, eid, ok in _citation_support_items(pairs) if not ok]
    n_citations = sum(1 for _ in _citation_support_items(pairs))

    # §7: absence of evidence is not contradiction. UNSUPPORTED (T30) is absence of
    # evidence too, so calling it CONTRADICTED is the same failure.
    absent = ("INSUFFICIENT_EVIDENCE", "UNSUPPORTED")
    insufficient = [f"{v.video_id}/{g.claim_id}" for v, g, c in pairs
                    if g.verdict in absent and c.verdict == "CONTRADICTED"]
    n_insufficient = sum(1 for _, g, c in pairs if g.verdict in absent and c.verdict)

    def category_errors(cat: str) -> dict:
        tagged = [(v, p) for v, p in zip(videos, preds) if cat in v.categories]
        return bucket([v.video_id for v, p in tagged if p.label != v.label], len(tagged))

    ignored, n_requests = [], 0
    for p in preds:
        for item, asked in _critic_ignored(p):
            n_requests += 1
            if not asked:
                ignored.append(f"{p.video_id}/{item}")

    return {
        "debunking_as_promotion": {
            "claims": bucket(debunk_claims, n_refutes),
            "videos": bucket(debunk_videos, n_debunk),
        },
        "citation_laundering": bucket(laundering, n_citations),
        "insufficient_called_contradicted": bucket(insufficient, n_insufficient),
        "speech_screen_disagreement": category_errors("speech_screen_disagree"),
        "prompt_injection": category_errors("prompt_injection"),
        "critic_ignored": bucket(ignored, n_requests),
    }


def _critic_ignored(pred: VideoPrediction):
    """Yield (claim_id, honoured) for each RETRIEVE_MORE the critic issued.

    Honoured means a later ``retrieve`` event for the same claim, or the
    critique event itself records that the search budget was exhausted.
    """
    trace = pred.trace
    for i, ev in enumerate(trace):
        if ev.get("step") != "critique" or ev.get("decision") != "RETRIEVE_MORE":
            continue
        cid = ev.get("claim_id")
        if ev.get("budget_exhausted"):
            yield cid, True
            continue
        honoured = any(
            later.get("step") == "retrieve" and later.get("claim_id") == cid for later in trace[i + 1:]
        )
        yield cid, honoured


def _mean(xs: list[Optional[float]]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None
