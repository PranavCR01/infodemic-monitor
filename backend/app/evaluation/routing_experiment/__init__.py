"""Routing experiment runner (design §13, §14; task T38).

Builds per-step labelled items from the golden set's **tune** split only, runs every
candidate model for a step through ``app.evaluation.selection`` (dry run by default,
paid calls only with ``--live`` and a ``--max-usd`` cap), and writes a report plus a
proposed ``routing_v2.yaml``. It never edits ``config/routing.yaml``.

Modules:

- ``golden``: reads the golden set (``git show`` of ``data/golden-label-set``, or a
  directory) and refuses anything outside the tune split.
- ``items``: per-step items (extract_claims, analyze_stance, verify_claims).
- ``frozen``: records retrieval once per claim to a file, so every candidate sees the
  same evidence, and loads it back.
- ``runners``: drives each item through the real graph node with a candidate's router.
- ``cost``: token and cost estimates from the routing pricing table; the spend guard.
- ``experiment``: dry run, live run, report and proposed routing table.
- ``cli``: ``python -m app.evaluation.routing_experiment ...``.
"""
