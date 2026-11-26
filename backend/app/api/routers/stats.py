"""``GET /v1/stats``: research-dashboard aggregates (T62; design §12, §16, §17).

Any signed-in user (analyst, reviewer or admin) sees the same totals across all users;
the response holds counts, shares and medians only, never a video, job, claim, review or
user id, and every count goes through small-cell suppression
(``app.services.stats_service``). Unauthenticated callers get 401. Cached per window for
``STATS_CACHE_SECONDS`` (60 s).
"""
from __future__ import annotations

from typing import Literal, Optional, Union

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.roles import user_id_of
from app.core.config import settings
from app.db.session import get_db
from app.services import stats_service

router = APIRouter(prefix="/v1", tags=["stats"])

# An exact count (5 or more) or "<5".
Cell = Union[int, Literal["<5"]]


class WeekBucket(BaseModel):
    week_start: str  # ISO date of the Monday (UTC)
    videos: Cell


class VideoStats(BaseModel):
    total: Cell
    per_week: list[WeekBucket]


class JobStats(BaseModel):
    pending_now: Cell
    running_now: Cell
    failed: Cell


class MisinfoBasis(BaseModel):
    contradicted: Cell
    unproven: Cell
    denies_supported: Cell
    unspecified: Cell


class LabelStats(BaseModel):
    MISINFO: Cell
    NO_MISINFO: Cell
    DEBUNKING: Cell
    CANNOT_RECOGNIZE: Cell
    misinfo_basis: MisinfoBasis


class ReviewStats(BaseModel):
    backlog_now: Cell
    decisions: Cell
    changed_label: Cell
    kept_label: Cell
    changed_label_share: Optional[float]
    median_hours_to_decision: Optional[float]


class CategoryCount(BaseModel):
    category: str
    videos: int


class StatsResponse(BaseModel):
    window: Literal["7d", "30d", "90d", "all"]
    window_start: Optional[str]
    window_end: str
    generated_at: str
    cache_seconds: int
    min_cell: int
    note: str
    videos: VideoStats
    jobs: JobStats
    labels: LabelStats
    reviews: ReviewStats
    top_categories: list[CategoryCount]


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    response: Response,
    window: Literal["7d", "30d", "90d", "all"] = Query("30d"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id_of(current_user)  # a token without a subject is refused (401)
    response.headers["Cache-Control"] = f"private, max-age={max(0, settings.STATS_CACHE_SECONDS)}"
    return stats_service.get_stats(db, window)
