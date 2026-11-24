"""Error analysis of routing-experiment outputs (T43; design §13, §14).

No model calls anywhere in this package. It works from what a routing run saved:

- ``matching``: the strict claim matcher the experiment scores with (token Jaccard
  >= 0.5) and a documented, deterministic meaning-based matcher (content-word overlap
  coefficient, the blind re-label's rule), so a reworded claim is not counted twice
  as a miss.
- ``bootstrap``: 95% bootstrap CIs over items for each step metric and a paired CI for
  the winner's margin.
- ``extraction``: sorts unmatched gold and predicted claims into error categories.
- ``goldset``: tune-only diff of two golden-set commits, and the ceiling implied by the
  blind re-label's two-pass agreement.
- ``analyze``: all of the above over a run's ``per_item.json``.

Everything reads the tune split only, through ``routing_experiment.golden.TuneSet``,
which drops test-split rows before anything sees them.
"""
