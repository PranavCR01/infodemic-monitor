"""Pipeline progress reporting for the frontend's stepper (T28; design §1, §16).

The pipeline announces which step it is starting with ``report_step(step)``. Nothing
happens unless a reporter is installed with ``reporting(fn)`` (the Celery worker installs
one that writes ``job_events``), so tests, evaluation runs and scripts are unaffected.

Reporting never changes a result: a reporter that raises is logged and ignored.
"""
from __future__ import annotations

import contextlib
import logging
from contextvars import ContextVar
from typing import Callable, Iterator, Optional

logger = logging.getLogger(__name__)

# The stepper's steps, in display order. Keys are stable API values; labels are the
# plain-language text the frontend may show (it can also use its own copy).
UPLOADED = "uploaded"
TRANSCRIBING = "transcribing"
READING_ON_SCREEN_TEXT = "reading_on_screen_text"
FINDING_CLAIMS = "finding_claims"
CHECKING_STANCE = "checking_stance"
SEARCHING_EVIDENCE = "searching_evidence"
VERIFYING = "verifying"
FINAL_CHECKS = "final_checks"

STEP_LABELS: dict[str, str] = {
    UPLOADED: "Uploaded",
    TRANSCRIBING: "Transcribing",
    READING_ON_SCREEN_TEXT: "Reading on-screen text",
    FINDING_CLAIMS: "Finding claims",
    CHECKING_STANCE: "Checking stance",
    SEARCHING_EVIDENCE: "Searching evidence",
    VERIFYING: "Verifying",
    FINAL_CHECKS: "Final checks",
}
STEPS: tuple[str, ...] = tuple(STEP_LABELS)

# Which steps each pipeline goes through. The single call (USE_GRAPH_PIPELINE off)
# transcribes, makes one model call (shown as "verifying") and, for MISINFO/DEBUNKING
# only, searches PubMed afterwards. It has no claim, stance or on-screen-text step.
PIPELINE_STEPS: dict[str, tuple[str, ...]] = {
    "single_call": (UPLOADED, TRANSCRIBING, VERIFYING, SEARCHING_EVIDENCE),
    "graph": STEPS,
}

# Graph node (app.core.graph.routing) -> stepper step. Nodes not listed (load_artifacts,
# fuse_modalities) don't move the stepper. The critic's loop back to retrieval moves the
# stepper back to "searching evidence", which is what is happening.
NODE_STEPS: dict[str, str] = {
    "transcribe_audio": TRANSCRIBING,
    "extract_ocr": READING_ON_SCREEN_TEXT,
    "extract_claims": FINDING_CLAIMS,
    "analyze_stance": CHECKING_STANCE,
    "plan_retrieval": SEARCHING_EVIDENCE,
    "retrieve_evidence": SEARCHING_EVIDENCE,
    "rerank_evidence": SEARCHING_EVIDENCE,
    "verify_claims": VERIFYING,
    "critique_verification": VERIFYING,
    "judge_classification": FINAL_CHECKS,
    "validate_result": FINAL_CHECKS,
    "route_for_review": FINAL_CHECKS,
    "human_review": FINAL_CHECKS,
    "persist_result": FINAL_CHECKS,
}

Reporter = Callable[[str], None]

_reporter: ContextVar[Optional[Reporter]] = ContextVar("pipeline_progress_reporter", default=None)


@contextlib.contextmanager
def reporting(reporter: Optional[Reporter]) -> Iterator[None]:
    """Install ``reporter`` for the code run inside the block (this thread/context)."""
    token = _reporter.set(reporter)
    try:
        yield
    finally:
        _reporter.reset(token)


def current_reporter() -> Optional[Reporter]:
    return _reporter.get()


def report_step(step: str) -> None:
    """Announce that ``step`` is starting. A no-op without a reporter; never raises."""
    reporter = _reporter.get()
    if reporter is None:
        return
    try:
        reporter(step)
    except Exception:  # noqa: BLE001 - progress must never break a run
        logger.warning("progress reporter failed for step %s", step, exc_info=True)


def report_node(node_name: str) -> None:
    """Announce a graph node starting, as its stepper step (if it has one)."""
    step = NODE_STEPS.get(node_name)
    if step:
        report_step(step)
