"""Admin-only routes (T63; design §13, §14, §15).

| Method | Path | Who |
|---|---|---|
| GET | ``/v1/admin/evals`` | admin: the evaluation registry, sorted by pipeline step |

The role check is ``require_role(Role.ADMIN)`` (``app.auth.roles``): no token is 401,
any signed-in caller below admin is 403, before the registry is read. Records come from
``evals/registry`` shipped in the backend image (``app.evaluation.registry``); they are
read on each request (a few dozen small files), so a new image is all a new record needs.

Each item carries ``report_url`` so the frontend can link to the report on GitHub; the
base is ``EVALS_REPORT_BASE_URL`` (default: the repo's ``langgraph-build`` tree).
"""
from __future__ import annotations

import logging
import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.auth.roles import Role, require_role
from app.evaluation.registry import (
    PIPELINE_STEPS,
    EvalRecord,
    RegistryError,
    load_registry,
    step_index,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin", tags=["admin"])

DEFAULT_REPORT_BASE_URL = "https://github.com/PranavCR01/infodemic-monitor/blob/langgraph-build/"


def report_base_url() -> str:
    base = os.environ.get("EVALS_REPORT_BASE_URL", "").strip() or DEFAULT_REPORT_BASE_URL
    return base if base.endswith("/") else base + "/"


class EvalItem(EvalRecord):
    model_config = ConfigDict(extra="forbid", title="EvalItem")

    step_index: int
    report_url: str


class StepGroup(BaseModel):
    step: str
    step_index: int
    count: int
    run_ids: list[str]


class EvalsResponse(BaseModel):
    total: int
    step_order: list[str]
    groups: list[StepGroup]
    items: list[EvalItem]


@router.get("/evals", response_model=EvalsResponse)
def list_evals(
    split: Optional[Literal["tune", "test", "none"]] = Query(
        None, description="tune, test, or none (records with no golden split)"),
    step: Optional[list[str]] = Query(None, description="pipeline step(s), repeated or comma-separated"),
    synthetic: Optional[bool] = Query(None),
    task: Optional[str] = Query(None, description="e.g. T38"),
    _admin: dict = Depends(require_role(Role.ADMIN)),
) -> EvalsResponse:
    steps: Optional[set[str]] = None
    if step:
        steps = {s.strip() for v in step for s in v.split(",") if s.strip()}
        unknown = steps - set(PIPELINE_STEPS)
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown step(s): {', '.join(sorted(unknown))}")
    try:
        records = load_registry()
    except RegistryError as exc:
        logger.error("Evaluation registry is invalid: %s", exc)
        raise HTTPException(status_code=500, detail="evaluation registry is invalid") from exc

    base = report_base_url()
    items: list[EvalItem] = []
    for r in records:
        if split is not None and (r.split or "none") != split:
            continue
        if steps is not None and r.pipeline_step not in steps:
            continue
        if synthetic is not None and r.synthetic != synthetic:
            continue
        if task is not None and r.task != task:
            continue
        items.append(EvalItem(**r.model_dump(), step_index=step_index(r.pipeline_step),
                              report_url=base + r.report_path))

    groups: list[StepGroup] = []
    for it in items:  # already sorted by step
        if not groups or groups[-1].step != it.pipeline_step:
            groups.append(StepGroup(step=it.pipeline_step, step_index=it.step_index, count=0, run_ids=[]))
        groups[-1].count += 1
        groups[-1].run_ids.append(it.run_id)
    return EvalsResponse(total=len(items), step_order=list(PIPELINE_STEPS), groups=groups, items=items)
