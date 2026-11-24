"""Golden-set side of the T43 analysis, tune split only, no predictions needed.

- ``gold_diff``: what changed for tune items between two golden-set commits (e.g. the
  T38 run's 0fbc68a and the adjudicated dcf77b0): videos joining/leaving the tune
  split, scope changes, claims added/removed, claim text, source, stance and verdict
  changes, and transcripts that changed. Each change is mapped to the T38 step items it
  touches.
- ``blind_ceiling``: the blind re-label's second pass (``blind/model_relabel_claims.csv``)
  scored as if it were a model's extraction against the first pass, with the strict and
  the meaning-based matcher. Two careful labelling passes disagreeing this much is a
  ceiling on what any extractor can score against one of them.

Both read through ``TuneSet``; the re-label CSV covers tune and test videos, so its rows
are filtered to tune video ids as they are parsed, before anything else sees them.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Any, Optional

from app.evaluation.error_analysis import matching as mt
from app.evaluation.routing_experiment.golden import GoldenSetError, TuneSet
from app.evaluation.routing_experiment.items import STANCE_LABELS, VERDICT_LABELS

BLIND_CLAIMS = "blind/model_relabel_claims.csv"


def _transcript_hash(tune: TuneSet, vid: str) -> Optional[str]:
    try:
        return hashlib.sha256(json.dumps(tune.transcript(vid), sort_keys=True).encode()).hexdigest()
    except GoldenSetError:
        return None


def gold_diff(old: TuneSet, new: TuneSet, *, check_transcripts: bool = True) -> dict[str, Any]:
    old_ids, new_ids = set(old.videos), set(new.videos)
    out: dict[str, Any] = {
        "old": old.source.describe(), "new": new.source.describe(),
        "left_tune": sorted(old_ids - new_ids), "joined_tune": sorted(new_ids - old_ids),
        "scope_changed": [], "transcript_changed": [], "claims": [],
        "items_touched": {"extract_claims": set(), "analyze_stance": set(), "verify_claims": set()},
    }
    touched = out["items_touched"]
    for vid in sorted(old_ids & new_ids, key=lambda v: (len(v), v)):
        a, b = old.videos[vid], new.videos[vid]
        if a.out_of_scope != b.out_of_scope:
            out["scope_changed"].append({"video_id": vid, "old_out_of_scope": a.out_of_scope,
                                         "new_out_of_scope": b.out_of_scope})
            touched["extract_claims"].add(vid)
        if check_transcripts and _transcript_hash(old, vid) != _transcript_hash(new, vid):
            out["transcript_changed"].append(vid)
            touched["extract_claims"].add(vid)
        ca = {c.claim_id: c for c in a.claims}
        cb = {c.claim_id: c for c in b.claims}
        in_scope = not (a.out_of_scope and b.out_of_scope)
        for cid in sorted(set(ca) | set(cb), key=lambda c: (len(c), c)):
            x, y = ca.get(cid), cb.get(cid)
            key = f"{vid}:{cid}"
            fields = []
            if x is None or y is None:
                fields = ["added" if x is None else "removed"]
            else:
                for f in ("text", "source", "stance", "verdict"):
                    if getattr(x, f) != getattr(y, f):
                        fields.append(f)
            if not fields:
                continue
            rec = {"key": key, "changed": fields,
                   "old": None if x is None else {"text": x.text, "source": x.source, "stance": x.stance,
                                                  "verdict": x.verdict},
                   "new": None if y is None else {"text": y.text, "source": y.source, "stance": y.stance,
                                                  "verdict": y.verdict}}
            out["claims"].append(rec)
            if not in_scope:
                continue
            if set(fields) & {"added", "removed", "text"}:
                touched["extract_claims"].add(vid)
            if set(fields) & {"added", "removed", "text", "source", "stance"}:
                if (x and x.stance in STANCE_LABELS) or (y and y.stance in STANCE_LABELS):
                    touched["analyze_stance"].add(key)
            if set(fields) & {"added", "removed", "text", "verdict"}:
                if (x and x.verdict in VERDICT_LABELS) or (y and y.verdict in VERDICT_LABELS):
                    touched["verify_claims"].add(key)
    out["items_touched"] = {k: sorted(v) for k, v in touched.items()}
    return out


def _tune_rows(tune: TuneSet, relpath: str) -> list[dict]:
    """Rows of a CSV that covers both splits, keeping tune videos only (as parsed)."""
    rows = []
    for row in csv.DictReader(io.StringIO(tune.source.read(relpath))):
        vid = row.get("video_id", "")
        if vid not in tune.videos:
            continue  # not a tune video: dropped before use
        rows.append(row)
    return rows


def _f(raw: str) -> Optional[float]:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def blind_ceiling(first: TuneSet, blind_source: Optional[TuneSet] = None) -> dict[str, Any]:
    """Score the blind second pass against ``first``'s claims on the tune videos both
    cover, counting only videos ``first`` treats as in scope (as T38 does).

    ``blind_source`` is the TuneSet whose source holds the re-label CSV (default:
    ``first``)."""
    src = blind_source or first
    rows = _tune_rows(src, BLIND_CLAIMS)
    second: dict[str, list[dict]] = {}
    for r in rows:
        second.setdefault(r["video_id"], []).append(r)
    vids = sorted((v for v in second if v in first.videos and not first.videos[v].out_of_scope),
                  key=lambda v: (len(v), v))
    totals = {"strict": 0, "meaning": 0}
    n_gold = n_pred = 0
    per_video = []
    for vid in vids:
        gold = first.videos[vid].claims
        g_text = [c.text for c in gold]
        p_text = [r["claim_text"].strip() for r in second[vid]]
        g_span = [(c.start, c.end) for c in gold]
        p_span = []
        for r in second[vid]:
            s, e = _f(r.get("start_seconds")), _f(r.get("end_seconds"))
            p_span.append((s, e if e is not None else s) if s is not None else None)
        ns = len(mt.strict_match(g_text, p_text))
        nm = len(mt.meaning_match(g_text, p_text, g_span, p_span))
        totals["strict"] += ns
        totals["meaning"] += nm
        n_gold += len(g_text)
        n_pred += len(p_text)
        per_video.append({"video_id": vid, "first": len(g_text), "second": len(p_text),
                          "strict_matched": ns, "meaning_matched": nm})
    return {
        "first": first.source.describe(), "videos": len(vids), "first_claims": n_gold, "second_claims": n_pred,
        "strict": {"matched": totals["strict"], **mt.prf(totals["strict"], n_gold, n_pred)},
        "meaning": {"matched": totals["meaning"], **mt.prf(totals["meaning"], n_gold, n_pred)},
        "per_video": per_video,
    }
