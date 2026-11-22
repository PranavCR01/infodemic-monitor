"""Evaluation framework (design doc section 14) and routing harness (section 13).

- ``dataset``: the shared, versioned, two-level labelled set; splits; agreement.
- ``metrics``: per-step metric functions.
- ``scoring``: score a run's predictions; tracked failure modes.
- ``runner``: run configuration, run records (hashes, revisions, predictions, traces).
- ``baseline``: today's single-call classifier as a system under test.
- ``compare``: does a candidate beat the baseline without regressing the guards?
- ``selection``: per-step model selection for the routing table.
"""
