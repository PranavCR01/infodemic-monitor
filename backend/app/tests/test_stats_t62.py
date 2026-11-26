"""Research-dashboard aggregates, ``GET /v1/stats`` (T62; design §12, §16, §17).

- ``compute_stats`` on a hand-built fixture with a fixed ``now``: every figure checked.
- Small-cell suppression: primary ("<5", zero included) and secondary (no hidden cell
  can be recovered by subtracting from a published total), on fixed cases and on a
  seeded random sweep.
- The route through T33's fixtures (real HS256 tokens, real ``get_current_user``):
  analyst, reviewer and admin all get the same totals; the body carries no video, job,
  claim, review or user identifier; no token is 401.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.models.claim import ClaimRow
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.models.review import HumanReview, ReviewAction, ReviewCaseStatus
from app.db.models.video import Video
from app.services import stats_service as ss
from app.services.stats_service import SUPPRESSED, compute_stats, suppress_group
from app.tests import test_ownership_t33 as t33
from app.tests.test_ownership_t33 import CALLERS, PG_DSN, env, pg_engine  # noqa: F401 (fixtures)

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)  # a Thursday
THIS_WEEK = NOW - timedelta(days=1)                         # Wed 2026-11-25
LAST_WEEK = NOW - timedelta(days=8)                         # Wed 2026-11-18


@pytest.fixture(autouse=True)
def _fresh_cache():
    ss.clear_cache()
    yield
    ss.clear_cache()


# ------------------------------------------------------------------ fixture builder


class Builder:
    def __init__(self, Session):
        self.s = Session()
        self.n = 0
        self.tag = uuid.uuid4().hex[:8]

    def _id(self, prefix):
        self.n += 1
        return f"{prefix}-{self.tag}-{self.n:04d}"

    def video(self, owner="u1"):
        vid = self._id("vid")
        self.s.add(Video(id=vid, filename=f"{vid}.mp4", file_path=f"/x/{vid}", file_size=1,
                         file_hash=f"{vid:0<64}"[:64], user_id=owner))
        self.s.flush()
        return vid

    def job(self, vid, status=JobStatus.SUCCESS, state=None, at=THIS_WEEK, error_code=None):
        jid = self._id("job")
        self.s.add(Job(id=jid, video_id=vid, status=status, state=state, created_at=at,
                       error_code=error_code, user_id="u1"))
        self.s.flush()
        return jid

    def analysed(self, label, basis=None, at=THIS_WEEK, categories=(), vid=None):
        vid = vid or self.video()
        jid = self.job(vid, at=at)
        self.s.add(Result(job_id=jid, label=label, misinfo_basis=basis, confidence=0.9, explanation="x",
                          evidence_snippets=[], combined_content="", provider="langgraph", model_used="m",
                          latency_ms=1, created_at=at))
        for i, c in enumerate(categories):
            self.s.add(ClaimRow(job_id=jid, claim_id=f"c{i}", text="t", category=c, start_seconds=0,
                                end_seconds=1, source_segment_ids=[]))
        self.s.flush()
        return vid

    def review(self, status=ReviewCaseStatus.RESOLVED, created=None, decided=None, proposed="MISINFO",
               corrected=None, action=ReviewAction.APPROVE):
        jid = self.job(self.video(), status=JobStatus.SUCCESS)
        self.s.add(HumanReview(job_id=jid, status=status, reasons=[], rules_fired=[], validation_errors=[],
                               proposed_label=proposed, policy_version="p", created_at=created or THIS_WEEK,
                               decided_at=decided, corrected_label=corrected,
                               action=action if decided else None, reviewer_id="r1" if decided else None))
        self.s.flush()

    def done(self):
        self.s.commit()
        self.s.close()


@pytest.fixture
def Session():
    import app.db.models  # noqa: F401

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _stats(Session, window="30d"):
    s = Session()
    try:
        return compute_stats(s, window, now=NOW)
    finally:
        s.close()


def seed_main(Session):
    b = Builder(Session)
    # 29 videos in the 30-day window: 18 this week, 11 last week.
    # MISINFO 12 (6 contradicted, 5 unproven, 1 denies_supported), NO_MISINFO 7,
    # DEBUNKING 5, CANNOT_RECOGNIZE 6.
    plan = ([("MISINFO", "contradicted")] * 6 + [("MISINFO", "unproven")] * 5 + [("MISINFO", "denies_supported")]
            + [("NO_MISINFO", None)] * 6 + [("DEBUNKING", None)] * 5 + [("CANNOT_RECOGNIZE", None)] * 6)
    vids = []
    for i, (label, basis) in enumerate(plan):
        at = THIS_WEEK if i % 5 < 3 else LAST_WEEK  # 18 / 11 (the re-run adds one this week)
        cats = []
        if i < 6:
            cats = ["Treatment_Efficacy"] + (["treatment_efficacy"] * 2 if i == 0 else [])  # one video, 3 claims
        elif i < 10:
            cats = ["prevention"]
        vids.append(b.analysed(label, basis, at=at, categories=cats))
    # A re-analysed video: older MISINFO last week, newer NO_MISINFO this week; counts
    # once, as NO_MISINFO, in this week.
    v = b.analysed("MISINFO", "contradicted", at=LAST_WEEK - timedelta(days=1))
    b.analysed("NO_MISINFO", at=THIS_WEEK, vid=v)
    # One video, seven claims in a rare category: never listed (one upload).
    b.analysed("NO_MISINFO", at=NOW - timedelta(days=40), categories=["rare_thing"] * 7)  # outside 30d
    # Outside the window, and a non-canonical legacy label: left out.
    b.analysed("MISINFO", "contradicted", at=NOW - timedelta(days=45))
    b.analysed("MISLEADING", at=THIS_WEEK)

    # Jobs: 5 queued, 1 running, 6 failed in the window, 1 failed earlier, 1 rejected.
    for _ in range(5):
        b.job(b.video(), status=JobStatus.PENDING, state="QUEUED")
    b.job(b.video(), status=JobStatus.STARTED, state="RUNNING")
    for _ in range(6):
        b.job(b.video(), status=JobStatus.FAILED, state="FAILED", error_code="E")
    b.job(b.video(), status=JobStatus.FAILED, state="FAILED", at=NOW - timedelta(days=60))
    b.job(b.video(), status=JobStatus.FAILED, state="REJECTED", error_code="REVIEW_REJECTED")

    # Reviews: 3 open; 8 decided in the window (2 changed the label, 1 "corrected" to the
    # same label, 5 approved), taking 1..8 hours; 1 superseded; 1 decided before.
    for _ in range(3):
        b.review(status=ReviewCaseStatus.OPEN)
    base = NOW - timedelta(days=3)
    for h in range(1, 9):
        if h <= 2:
            kw = dict(corrected="NO_MISINFO", action=ReviewAction.CORRECT)
        elif h == 3:
            kw = dict(corrected="MISINFO", action=ReviewAction.CORRECT)
        else:
            kw = {}
        b.review(created=base, decided=base + timedelta(hours=h), **kw)
    b.review(status=ReviewCaseStatus.SUPERSEDED, created=base)
    b.review(created=NOW - timedelta(days=50), decided=NOW - timedelta(days=49), corrected="NO_MISINFO",
             action=ReviewAction.CORRECT)
    b.done()
    return vids


# ------------------------------------------------------------------ aggregates


def test_aggregates_on_the_fixture(Session):
    seed_main(Session)
    st = _stats(Session)

    assert st["window"] == "30d"
    assert st["window_start"] == (NOW - timedelta(days=30)).isoformat()
    assert st["note"].startswith("These figures describe videos uploaded to this tool")

    # 29 planned + the re-analysed video = 30; the re-run counts once.
    assert st["videos"]["total"] == 30
    assert st["labels"]["MISINFO"] == 12
    assert st["labels"]["NO_MISINFO"] == 7  # 6 planned + the re-run video
    assert st["labels"]["DEBUNKING"] == 5
    assert st["labels"]["CANNOT_RECOGNIZE"] == 6

    # Basis: denies_supported 1 and unspecified 0 are small; their sum (1) is still
    # under 5, so the next smallest (unproven, 5) is hidden too.
    assert st["labels"]["misinfo_basis"] == {
        "contradicted": 6, "unproven": SUPPRESSED, "denies_supported": SUPPRESSED, "unspecified": SUPPRESSED}

    # Weeks from the window start (Mon 2026-10-26) to this week.
    weeks = {w["week_start"]: w["videos"] for w in st["videos"]["per_week"]}
    assert list(weeks) == ["2026-10-26", "2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"]
    # 19 this week (18 + the re-run), 11 last week; the three empty weeks are hidden and
    # add up to 0, so last week is hidden as well.
    assert weeks["2026-11-23"] == 19
    assert all(weeks[w] == SUPPRESSED for w in ("2026-10-26", "2026-11-02", "2026-11-09", "2026-11-16"))

    assert st["jobs"] == {"pending_now": 5, "running_now": SUPPRESSED, "failed": 6}

    r = st["reviews"]
    assert r["backlog_now"] == SUPPRESSED  # 3 open
    assert r["decisions"] == 8
    # 2 changed, 6 kept: the 2 is hidden, and so is the 6 (else 8 - 6 = 2).
    assert r["changed_label"] == SUPPRESSED and r["kept_label"] == SUPPRESSED
    assert r["changed_label_share"] is None
    assert r["median_hours_to_decision"] == 4.5

    # Categories count videos, not claims, and are case-folded; "prevention" (4 videos)
    # and the one-video "rare_thing" are not listed.
    assert st["top_categories"] == [{"category": "treatment_efficacy", "videos": 6}]


def test_unsuppressed_figures_and_share(Session):
    b = Builder(Session)
    for label in ("MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"):
        for _ in range(5):
            b.analysed(label, "contradicted" if label == "MISINFO" else None, at=THIS_WEEK)
            b.analysed(label, "unproven" if label == "MISINFO" else None, at=LAST_WEEK)
    base = NOW - timedelta(days=2)
    for h in range(11):
        kw = dict(corrected="NO_MISINFO", action=ReviewAction.CORRECT) if h < 5 else {}
        b.review(created=base, decided=base + timedelta(hours=h), **kw)
    b.done()
    st = _stats(Session, "7d")
    # 7 days back from Thursday reaches last Thursday: only this week's 20 videos.
    assert st["videos"]["total"] == 20
    assert [w["week_start"] for w in st["videos"]["per_week"]] == ["2026-11-16", "2026-11-23"]
    assert st["labels"]["MISINFO"] == 5
    assert st["labels"]["misinfo_basis"]["contradicted"] == SUPPRESSED  # 5 of 5 but the rest are 0
    st = _stats(Session, "all")
    assert st["window_start"] is None
    assert {w["week_start"]: w["videos"] for w in st["videos"]["per_week"]} == {"2026-11-16": 20, "2026-11-23": 20}
    assert {k: st["labels"][k] for k in ss.LABELS} == {k: 10 for k in ss.LABELS}
    assert st["reviews"]["decisions"] == 11
    assert st["reviews"]["changed_label"] == 5 and st["reviews"]["kept_label"] == 6
    assert st["reviews"]["changed_label_share"] == round(5 / 11, 3)
    assert st["reviews"]["median_hours_to_decision"] == 5.0


def test_empty_database(Session):
    st = _stats(Session, "all")
    assert st["videos"]["total"] == SUPPRESSED
    assert all(w["videos"] == SUPPRESSED for w in st["videos"]["per_week"])
    assert all(st["labels"][k] == SUPPRESSED for k in ss.LABELS)
    assert st["reviews"]["median_hours_to_decision"] is None
    assert st["top_categories"] == []


def test_unknown_window_is_refused(Session):
    s = Session()
    with pytest.raises(ValueError):
        compute_stats(s, "365d", now=NOW)
    s.close()


# ------------------------------------------------------------------ suppression


def test_primary_suppression_includes_zero():
    assert ss.cell(0) == SUPPRESSED and ss.cell(4) == SUPPRESSED and ss.cell(5) == 5


def test_no_small_cells_no_suppression():
    assert suppress_group({"a": 5, "b": 9}, 14) == {"a": 5, "b": 9}


def test_single_small_cell_gets_a_complement():
    # Without secondary suppression: 20 - 9 - 8 = 3 recovers the hidden cell.
    assert suppress_group({"a": 9, "b": 8, "c": 3}, 20) == {"a": 9, "b": SUPPRESSED, "c": SUPPRESSED}


def test_two_small_cells_with_a_small_sum_get_a_third():
    # Hidden 1 + 0 = 1 would say "these two hold exactly one video".
    out = suppress_group({"a": 1, "b": 0, "c": 6, "d": 7}, 14)
    assert out == {"a": SUPPRESSED, "b": SUPPRESSED, "c": SUPPRESSED, "d": 7}


def test_two_small_cells_with_a_large_sum_are_enough():
    out = suppress_group({"a": 3, "b": 4, "c": 6}, 13)
    assert out == {"a": SUPPRESSED, "b": SUPPRESSED, "c": 6}


def test_small_total_hides_the_group():
    assert suppress_group({"a": 4, "b": 0}, 4) == {"a": SUPPRESSED, "b": SUPPRESSED}


def _check_group(cells, total, out):
    hidden = [k for k, v in out.items() if v == SUPPRESSED]
    shown = {k: v for k, v in out.items() if v != SUPPRESSED}
    assert all(v >= 5 for v in shown.values())
    assert all(cells[k] == v for k, v in shown.items())
    if total < 5:
        assert len(hidden) == len(cells)
    elif hidden:
        # The hidden cells' sum is total - shown: it must not pin down one cell, and
        # must not be a small cell itself.
        assert len(hidden) >= 2
        assert total - sum(shown.values()) >= 5


def test_differencing_sweep():
    rng = random.Random(62)
    for _ in range(3000):
        k = rng.randint(2, 8)
        cells = {f"c{i}": rng.choice([0, 0, 1, 2, 3, 4, 5, 6, 9, 20, 50]) for i in range(k)}
        total = sum(cells.values())
        _check_group(cells, total, suppress_group(cells, total))


def test_differencing_on_the_response(Session):
    """Every group in a real response satisfies the rule against its published total."""
    seed_main(Session)
    for window in ss.WINDOWS:
        st = _stats(Session, window)
        total = st["videos"]["total"]
        groups = [
            ([w["videos"] for w in st["videos"]["per_week"]], total),
            ([st["labels"][k] for k in ss.LABELS], total),
            (list(st["labels"]["misinfo_basis"].values()), st["labels"]["MISINFO"]),
            ([st["reviews"]["changed_label"], st["reviews"]["kept_label"]], st["reviews"]["decisions"]),
        ]
        for cells, tot in groups:
            hidden = [c for c in cells if c == SUPPRESSED]
            if tot == SUPPRESSED:
                assert len(hidden) == len(cells)
            elif hidden:
                assert len(hidden) >= 2
                assert tot - sum(c for c in cells if c != SUPPRESSED) >= 5


# ------------------------------------------------------------------ route


def test_route_is_classified_in_the_t33_table():
    assert t33.ROUTES.get(("GET", "/v1/stats")) == t33.AGGREGATE


def _seed_more(env, n=6, label="NO_MISINFO", categories=("prevention",)):
    b = Builder(env["Session"])
    vids = [b.analysed(label, at=datetime.now(timezone.utc) - timedelta(hours=1),
                       categories=list(categories)) for _ in range(n)]
    b.done()
    return vids


@pytest.mark.parametrize("caller", ["owner", "other", "reviewer", "admin"])
def test_every_role_sees_the_same_totals(env, caller):
    _seed_more(env)
    _seed_more(env, label="DEBUNKING", categories=())
    r = env["client"].get("/v1/stats?window=7d", headers=CALLERS[caller])
    assert r.status_code == 200, r.text
    body = r.json()
    # T33 seeds 3 MISINFO videos (alice, bob, legacy); plus 6 NO_MISINFO and 6
    # DEBUNKING here. MISINFO 3 + CANNOT_RECOGNIZE 0 sum to 3, so DEBUNKING (the
    # smaller of the two 6s by name) is hidden with them.
    assert body["videos"]["total"] == 15
    assert body["labels"]["NO_MISINFO"] == 6
    assert body["labels"]["MISINFO"] == SUPPRESSED and body["labels"]["DEBUNKING"] == SUPPRESSED
    assert body["top_categories"] == [{"category": "prevention", "videos": 6}]
    ss.clear_cache()
    other = env["client"].get("/v1/stats?window=7d", headers=CALLERS["owner"]).json()
    other.pop("generated_at"), other.pop("window_end"), other.pop("window_start")
    for k in ("generated_at", "window_end", "window_start"):
        body.pop(k)
    assert body == other  # not filtered by caller


def test_response_has_no_per_video_or_per_user_identifiers(env):
    vids = _seed_more(env)
    r = env["client"].get("/v1/stats?window=all", headers=CALLERS["owner"])
    assert r.status_code == 200
    text = r.text
    s = env["Session"]()
    ids = set(vids)
    for model, cols in ((Video, ("id", "filename", "file_path", "file_hash", "storage_key", "user_id")),
                        (Job, ("id", "user_id", "celery_task_id")),
                        (Result, ("id", "job_id")),
                        (HumanReview, ("id", "job_id")),
                        (ClaimRow, ("id", "claim_id", "text"))):
        for row in s.query(model):
            ids.update(str(getattr(row, c)) for c in cols if getattr(row, c, None))
    s.close()
    ids.update({"alice", "bob", "rita", "adam"})
    leaked = sorted(i for i in ids if i and len(i) > 2 and i in text)
    assert not leaked, leaked
    # Only the documented keys, recursively.
    body = r.json()
    assert set(body) == {"window", "window_start", "window_end", "generated_at", "cache_seconds", "min_cell",
                         "note", "videos", "jobs", "labels", "reviews", "top_categories"}


def test_unauthenticated_is_401(env):
    assert env["client"].get("/v1/stats").status_code == 401
    assert env["client"].get("/v1/stats", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_bad_window_is_422(env):
    assert env["client"].get("/v1/stats?window=365d", headers=CALLERS["owner"]).status_code == 422


def test_default_window_and_cache(env, monkeypatch):
    c = env["client"]
    first = c.get("/v1/stats", headers=CALLERS["owner"])
    assert first.status_code == 200 and first.json()["window"] == "30d"
    assert first.headers["Cache-Control"] == "private, max-age=60"
    assert first.json()["videos"]["total"] == SUPPRESSED  # 3 videos
    _seed_more(env)
    # Cached for STATS_CACHE_SECONDS: the same figures until it runs out.
    assert c.get("/v1/stats", headers=CALLERS["admin"]).json() == first.json()
    ss.clear_cache()
    assert c.get("/v1/stats", headers=CALLERS["owner"]).json()["videos"]["total"] == 9
    # 0 turns the cache off.
    monkeypatch.setattr(settings, "STATS_CACHE_SECONDS", 0)
    _seed_more(env, 1)
    assert c.get("/v1/stats", headers=CALLERS["owner"]).json()["videos"]["total"] == 10
