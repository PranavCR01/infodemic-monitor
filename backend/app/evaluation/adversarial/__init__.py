"""Adversarial evaluation (design doc §15 "Tested"; issue #37).

- ``cases``: the case set schema; the set itself is ``research/adversarial/adversarial_v1.yaml``.
- ``unsafe``: the written definition of an unsafe result (``UNSAFE_DEFINITION``).
- ``simulated``: the worst-case simulated model and today's single-call classifier around it.
- ``graph_system``: the guarded graph as a system under test.
- ``run``: runs both systems and reports "N unsafe out of M".

Run with ``python -m app.evaluation.adversarial``. (Nothing is imported here so that
``__main__`` can set its defaults before app settings load.)
"""
