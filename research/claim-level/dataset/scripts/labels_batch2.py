"""Batch 2 of the golden label set: v83 onward (scripts/add_batch2.py).

Same rules, fields and evidence discipline as labels.py; read its docstring.
The labels are split across labels_b2_*.py so they could be written in
parallel. This module only collects them, in video_id order.

Batch-2 additions per video (all optional):
  external_reason  why the derived label differs from what the source's own
                   label implies (compare_external.py requires one for every
                   disagreement, like compare_collectors.py does)
Claims in another language keep the speaker's words verbatim in that
language (README: quote, don't invent), with an English gloss at the start of
notes as  'EN: ...'.

Each labels_b2_*.py may also define CITATIONS, in the format of
cite_references.CITATIONS, for the section 6 reference URLs it cites.
"""
import importlib
from pathlib import Path

LABELS = []
CITATIONS = []
for _p in sorted(Path(__file__).resolve().parent.glob("labels_b2_*.py")):
    _m = importlib.import_module(_p.stem)
    LABELS += _m.LABELS
    CITATIONS += getattr(_m, "CITATIONS", [])
LABELS.sort(key=lambda v: int(v["video_id"][1:]))

_ids = [v["video_id"] for v in LABELS]
if len(_ids) != len(set(_ids)):
    raise SystemExit("labels_batch2: a video_id is labelled twice")
