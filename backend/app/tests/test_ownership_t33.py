"""Per-user ownership on every read (T33; design §15, §17).

The rule (``app.api.ownership``): owner, or reviewer/admin (roles from the verified JWT's
``app_metadata``); rows with no owner (legacy) are admin only; an object the caller may
not see answers 404 exactly like a missing one. Reviewers may not decide a case on
their own video.

The route table below must name every route the real app mounts (read from its OpenAPI
schema, so it works across FastAPI versions): a new route fails
``test_every_mounted_route_is_classified`` until someone decides how it is protected.
Each object route is then called by its owner, another analyst, a reviewer and an admin,
on the owner's object, a legacy (NULL-owner) object and a missing one.

Tokens are real HS256 JWTs checked by the real ``get_current_user``. Storage, the worker
queue and the re-analysis dispatcher are fakes. Runs on SQLite and, when
``LIBRARY_TEST_PG_DSN`` is set (CI), on a throwaway Postgres database.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.models.claim import ClaimRow, ClaimStanceRow, VerificationResultRow
from app.db.models.job import Job, JobStatus
from app.db.models.result import Result
from app.db.models.review import AuditEvent, HumanReview, ReviewCaseStatus, ReviewPreReveal
from app.db.models.video import Video
from app.db.session import get_db

BACKEND = Path(__file__).resolve().parents[2]
SECRET = "test-secret-not-real-t33-0123456789abcdef"
T0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def token(sub: str, role: Optional[str] = None, **extra) -> str:
    claims = {"sub": sub, "aud": "authenticated", "role": "authenticated",
              "exp": datetime.now(timezone.utc) + timedelta(hours=1), **extra}
    if role:
        claims["app_metadata"] = {"provider": "email", "role": role}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def auth(sub: str, role: Optional[str] = None, **extra) -> dict:
    return {"Authorization": f"Bearer {token(sub, role, **extra)}"}


CALLERS = {
    "owner": auth("alice"),                 # analyst who owns the "alice" objects
    "other": auth("bob"),                   # another analyst
    "reviewer": auth("rita", "reviewer"),
    "admin": auth("adam", "admin"),
}
PRE_REVEALED = ("rita", "adam", "alice", "bob")  # T34: see seed()


# ------------------------------------------------------------------ database


PG_DSN = os.environ.get("LIBRARY_TEST_PG_DSN")
_TABLES = [t for t in Base.metadata.tables]  # the app's tables (no library/vector tables)


@pytest.fixture(scope="module")
def pg_engine():
    if not PG_DSN:
        pytest.skip("set LIBRARY_TEST_PG_DSN to a throwaway Postgres database with pgvector")
    from sqlalchemy.engine import make_url

    import app.db.models  # noqa: F401

    name = f"t33_{uuid.uuid4().hex[:12]}"
    admin = create_engine(PG_DSN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    engine = create_engine(make_url(PG_DSN).set(database=name))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
    admin.dispose()


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def create_signed_upload_url(self, key):
        return {"signed_url": f"https://storage.test/upload/{key}", "token": "t", "path": key}

    def create_signed_download_url(self, key, ttl):
        return f"https://storage.test/read/{key}?ttl={ttl}"

    def download(self, key):
        from app.core.exceptions import StorageError

        if key not in self.objects:
            raise StorageError(key, FileNotFoundError(key))
        return self.objects[key]

    def delete(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)

    def upload(self, local_path, key):  # pragma: no cover
        return key


class FakeTask:
    id = "celery-task-t33"


@pytest.fixture(params=["sqlite", "postgres"])
def env(request, monkeypatch, tmp_path):
    import app.db.models  # noqa: F401
    from app.api.routers import jobs as jobs_router
    from app.api.routers import reviews as reviews_router
    from app.api.routers import videos as videos_router
    from app.main import app

    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "UPLOAD_SAFEGUARDS", False)
    monkeypatch.setattr(jobs_router.process_video_task, "delay", lambda *a, **k: FakeTask())

    if request.param == "sqlite":
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
    else:
        engine = request.getfixturevalue("pg_engine")
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE " + ", ".join(_TABLES) + " CASCADE"))
    Session = sessionmaker(bind=engine)

    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    storage = FakeStorage()
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[videos_router.get_storage] = lambda: storage
    app.dependency_overrides[reviews_router.get_reanalysis_dispatcher] = lambda: (lambda job_id, key: "task-r")
    try:  # T29's playback route, if merged
        from app.api.routers import playback as playback_router

        app.dependency_overrides[playback_router.get_storage] = lambda: storage
    except ImportError:
        pass
    seed(Session)
    yield {"client": TestClient(app), "Session": Session, "app": app, "storage": storage}
    app.dependency_overrides.clear()


def seed(Session, tags=("alice", "bob", "legacy")):
    """For each owner tag: a video, a finished job in review with a result, one claim
    (c1, HIGH) and an open review case. ``legacy`` rows have no owner (NULL)."""
    s = Session()
    for tag in tags:
        owner = None if tag == "legacy" else tag
        s.add(Video(id=f"vid-{tag}", filename=f"{tag}.mp4", file_path=f"/x/{tag}.mp4", file_size=1,
                    file_hash=f"{tag:0<64}"[:64], storage_key=f"uploads/{tag}/x.mp4", user_id=owner))
        s.flush()
        s.add(Job(id=f"job-{tag}", video_id=f"vid-{tag}", status=JobStatus.REVIEW_REQUIRED, user_id=owner,
                  created_at=T0))
        s.flush()
        s.add(Result(job_id=f"job-{tag}", label="MISINFO", confidence=0.5, explanation="x", evidence_snippets=[],
                     combined_content="", provider="langgraph", model_used="graph", latency_ms=1, pipeline="graph"))
        claim = ClaimRow(id=f"claim-{tag}", job_id=f"job-{tag}", claim_id="c1", text="Hot water cures flu.",
                         category="treatment_efficacy", start_seconds=0.0, end_seconds=1.0,
                         source_segment_ids=[], label="MISINFO", deciding=True)
        claim.stance = ClaimStanceRow(stance="ENDORSES", segment_ids=[], rationale="")
        claim.verification = VerificationResultRow(verdict="CONTRADICTED", explanation="no", limitations=[],
                                                   retrieval_attempts=1)
        s.add(claim)
        s.add(HumanReview(
            id=f"rev-{tag}", job_id=f"job-{tag}", status=ReviewCaseStatus.OPEN, reasons=["judge:mixed_video"],
            rules_fired=[{"rule": "judge", "reasons": ["judge:mixed_video"]}], validation_errors=[],
            proposed_label="MISINFO", proposed_result={"classification": "MISINFO"}, policy_version="p1",
            created_at=T0, severity="HIGH", severity_table_version="sev-1",
            claim_severities={"c1": {"severity": "HIGH", "basis": [], "stance": "ENDORSES",
                                     "verdict": "CONTRADICTED", "misinfo_relevant": True}},
        ))
        s.flush()
        # T34: these cases are HIGH, so deciding needs each reviewer's blind judgement
        # first (tested in test_review_blind_t34). Recorded here so this file keeps
        # testing ownership only.
        for sub in PRE_REVEALED:
            s.add(ReviewPreReveal(review_id=f"rev-{tag}", reviewer_id=sub,
                                  claims={"c1": {"stance": "ENDORSES", "verdict": "CONTRADICTED"}}))
    s.commit()
    s.close()


# ------------------------------------------------------------------ route table


@dataclass(frozen=True)
class ObjectRoute:
    """A route that reads or acts on one object. ``path``/``body`` build the request for
    the object of an owner tag ("alice", "legacy", or "missing"); ``ok`` are the statuses
    a caller allowed to see it gets; ``role`` is the minimum role the route itself needs
    (analysts get 403 before any lookup)."""

    method: str
    path: Callable[[str], str]
    ok: tuple[int, ...] = (200,)
    body: Optional[Callable[[str], dict]] = None
    role: Optional[str] = None


PUBLIC = "public"           # no auth, no per-user data
SELF = "self"               # only the caller's own identity
CREATE = "create"           # makes a new object owned by the caller; no id in the request
LIST = "list"               # filtered by visible_jobs (tested in test_lists_*)
REVIEWER_LIST = "reviewer_list"
STORAGE_KEY = "storage_key"  # register: the key must be under the caller's prefix (tested below)
# T55: the video's owner or an admin; a reviewer who can see the video gets 403, anyone
# who can't gets 404 (tested in test_reanalysis_t55).
OWNER_OR_ADMIN = "owner_or_admin"
# T63: admin only, no per-user data (401/403 tested in test_eval_registry_t63).
ADMIN_ONLY = "admin_only"

DECISION = {"action": "APPROVE", "reason": "checked the papers", "reason_code": "SYSTEM_CORRECT"}

ROUTES: dict[tuple[str, str], object] = {
    ("GET", "/health"): PUBLIC,
    ("GET", "/v1/me"): SELF,
    ("POST", "/videos/upload"): CREATE,
    ("POST", "/v1/videos/uploads"): CREATE,
    ("POST", "/v1/videos"): STORAGE_KEY,
    ("POST", "/v1/videos/{video_id}/reanalyse"): OWNER_OR_ADMIN,
    ("GET", "/jobs"): LIST,
    ("GET", "/v1/jobs"): LIST,
    ("GET", "/v1/reviews"): REVIEWER_LIST,
    ("GET", "/v1/admin/evals"): ADMIN_ONLY,
    ("POST", "/jobs/create"): ObjectRoute("POST", lambda t: "/jobs/create", body=lambda t: {"video_id": f"vid-{t}"}),
    ("GET", "/jobs/{job_id}"): ObjectRoute("GET", lambda t: f"/jobs/job-{t}"),
    ("GET", "/jobs/{job_id}/result"): ObjectRoute("GET", lambda t: f"/jobs/job-{t}/result"),
    ("GET", "/v1/jobs/{job_id}"): ObjectRoute("GET", lambda t: f"/v1/jobs/job-{t}"),
    ("GET", "/v1/jobs/{job_id}/events"): ObjectRoute("GET", lambda t: f"/v1/jobs/job-{t}/events"),
    ("GET", "/v1/videos/{video_id}/results"): ObjectRoute("GET", lambda t: f"/v1/videos/vid-{t}/results"),
    ("GET", "/v1/videos/{video_id}/claims"): ObjectRoute("GET", lambda t: f"/v1/videos/vid-{t}/claims"),
    ("GET", "/v1/claims/{claim_id}/evidence"): ObjectRoute("GET", lambda t: f"/v1/claims/claim-{t}/evidence"),
    ("GET", "/v1/reviews/{review_id}"): ObjectRoute("GET", lambda t: f"/v1/reviews/rev-{t}", role="reviewer"),
    ("POST", "/v1/reviews/{review_id}/decision"): ObjectRoute(
        "POST", lambda t: f"/v1/reviews/rev-{t}/decision", body=lambda t: DECISION, role="reviewer"),
    # T34: the seeded pre-reveals make an allowed caller's second one a 409; what this
    # matrix checks is 404 / 403 versus allowed.
    ("POST", "/v1/reviews/{review_id}/pre-reveal"): ObjectRoute(
        "POST", lambda t: f"/v1/reviews/rev-{t}/pre-reveal", ok=(201, 409),
        body=lambda t: {"claims": [{"claim_id": "c1", "stance": "REFUTES", "verdict": "SUPPORTED"}]},
        role="reviewer"),
    # T40: only for a caller still blind on the case. The seeded pre-reveals make every
    # allowed caller here non-blind (403); the blind 200 is in test_blind_material_t40.
    ("GET", "/v1/reviews/{review_id}/blind-material"): ObjectRoute(
        "GET", lambda t: f"/v1/reviews/rev-{t}/blind-material", ok=(200, 403), role="reviewer"),
    ("POST", "/v1/reviews/{review_id}/claims/{claim_id}/severity"): ObjectRoute(
        "POST", lambda t: f"/v1/reviews/rev-{t}/claims/c1/severity",
        body=lambda t: {"severity": "LOW", "reason": "adult audience"}, role="reviewer"),
    # Open PRs that use ownership.owned_job_or_404; checked when they are mounted.
    ("GET", "/v1/jobs/{job_id}/playback"): ObjectRoute("GET", lambda t: f"/v1/jobs/job-{t}/playback"),
    ("POST", "/v1/jobs/{job_id}/review-request"): ObjectRoute(
        "POST", lambda t: f"/v1/jobs/job-{t}/review-request", ok=(200, 201),
        body=lambda t: {"note": "please check"}),
}


def mounted_routes(app) -> set[tuple[str, str]]:
    out = set()
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            out.add((method.upper(), path))
    return out


def _object_routes(app) -> list[tuple[str, str]]:
    return sorted(k for k in mounted_routes(app) if isinstance(ROUTES.get(k), ObjectRoute))


def test_every_mounted_route_is_classified():
    from app.main import app

    app.openapi_schema = None
    unclassified = mounted_routes(app) - set(ROUTES)
    assert not unclassified, f"classify these routes in ROUTES (T33): {sorted(unclassified)}"
    # The schema hides nothing: every API route is in it.
    from fastapi.routing import APIRoute

    def walk(routes):
        for r in routes:
            if isinstance(r, APIRoute):
                yield r
            sub = getattr(r, "original_router", None) or getattr(r, "router", None)
            if sub is not None and sub is not r and hasattr(sub, "routes"):
                yield from walk(sub.routes)

    assert all(r.include_in_schema for r in walk(app.router.routes))


def _expected(route: ObjectRoute, caller: str, tag: str) -> str:
    """'ok', 404 or 403 for ``caller`` on the object of owner ``tag``."""
    if route.role == "reviewer" and caller in ("owner", "other"):
        return "403"  # the role gate runs before any lookup, for every target
    if tag == "missing":
        return "404"
    if tag == "legacy":
        return "ok" if caller == "admin" else "404"
    return "404" if caller == "other" else "ok"


def _call(client, route: ObjectRoute, tag: str, headers: dict):
    kw = {"headers": headers}
    if route.body is not None:
        kw["json"] = route.body(tag)
    return client.request(route.method, route.path(tag), **kw)


@pytest.mark.parametrize("caller", list(CALLERS))
@pytest.mark.parametrize("tag", ["alice", "legacy", "missing"])
def test_object_routes_cross_user_matrix(env, caller, tag):
    """Every object route: owner and reviewer/admin see the owner's object, another
    analyst gets 404; legacy (NULL-owner) objects only admins; missing is 404."""
    client = env["client"]
    routes = _object_routes(env["app"])
    assert len(routes) >= 11
    for key in routes:
        route = ROUTES[key]
        # A fresh copy of the data for each route (decisions and job creation change it).
        r = _call(client, route, tag, CALLERS[caller])
        want = _expected(route, caller, tag)
        if want == "ok":
            assert r.status_code in route.ok, (key, caller, tag, r.status_code, r.text)
        else:
            assert r.status_code == int(want), (key, caller, tag, r.status_code, r.text)
        _reset(env)


def _reset(env):
    s = env["Session"]()
    for t in ("job_events", "audit_events", "claim_stances", "verification_results", "claims",
              "review_pre_reveals", "users", "human_reviews", "results", "jobs", "videos"):
        s.execute(text(f"DELETE FROM {t}"))
    s.commit()
    s.close()
    seed(env["Session"])


def test_hidden_object_looks_exactly_like_a_missing_one(env):
    """Same status and body for another user's object as for one that doesn't exist."""
    client = env["client"]
    for key in _object_routes(env["app"]):
        route = ROUTES[key]
        if route.role:
            continue
        hidden = _call(client, route, "alice", CALLERS["other"])
        missing = _call(client, route, "missing", CALLERS["other"])
        assert hidden.status_code == missing.status_code == 404, key
        assert hidden.json() == missing.json(), key


def test_reviewer_routes_refuse_analysts_before_lookup(env):
    client = env["client"]
    for key in _object_routes(env["app"]):
        route = ROUTES[key]
        if route.role != "reviewer":
            continue
        for tag in ("alice", "missing"):
            r = _call(client, route, tag, CALLERS["owner"])
            assert r.status_code == 403, (key, tag)
    assert client.get("/v1/reviews", headers=CALLERS["owner"]).status_code == 403


def test_unauthenticated_calls_are_401(env):
    client = env["client"]
    for key in _object_routes(env["app"]):
        route = ROUTES[key]
        assert _call(client, route, "alice", {}).status_code == 401, key
    for path in ("/jobs", "/v1/jobs", "/v1/reviews", "/v1/me"):
        assert client.get(path).status_code == 401, path


# ------------------------------------------------------------------ lists


def _ids(client, path, headers, **params):
    r = client.get(path, headers=headers, params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    rows = body if isinstance(body, list) else body["items"]
    return {row["job_id"] for row in rows}, r


@pytest.mark.parametrize("path", ["/jobs", "/v1/jobs"])
def test_lists_show_only_what_the_caller_may_see(env, path):
    c = env["client"]
    assert _ids(c, path, CALLERS["owner"])[0] == {"job-alice"}
    assert _ids(c, path, CALLERS["other"])[0] == {"job-bob"}
    assert _ids(c, path, CALLERS["reviewer"])[0] == {"job-alice", "job-bob"}
    assert _ids(c, path, CALLERS["admin"])[0] == {"job-alice", "job-bob", "job-legacy"}
    # Totals match the rows, so the count doesn't leak other users' jobs either.
    _, r = _ids(c, path, CALLERS["other"])
    total = int(r.headers["X-Total-Count"]) if path == "/jobs" else r.json()["total"]
    assert total == 1
    # A search for someone else's job id finds nothing.
    assert _ids(c, path, CALLERS["other"], q="job-alice")[0] == set()


@pytest.mark.parametrize("path", ["/jobs", "/v1/jobs"])
def test_lists_mine_filter_and_submitted_by(env, path):
    c = env["client"]
    assert _ids(c, path, CALLERS["admin"], mine="true")[0] == set()
    assert _ids(c, path, CALLERS["owner"], mine="true")[0] == {"job-alice"}
    _, r = _ids(c, path, CALLERS["reviewer"])
    rows = r.json() if path == "/jobs" else r.json()["items"]
    assert {row["job_id"]: row["submitted_by"] for row in rows} == {"job-alice": "alice", "job-bob": "bob"}


def test_review_queue_reviewer_sees_owned_cases_admin_also_legacy(env):
    c = env["client"]

    def queue(who):
        r = c.get("/v1/reviews", headers=CALLERS[who], params={"status": "ALL"})
        assert r.status_code == 200
        return r.json()

    rv = queue("reviewer")
    assert {i["review_id"] for i in rv["items"]} == {"rev-alice", "rev-bob"} and rv["total"] == 2
    assert {i["review_id"]: i["submitted_by"] for i in rv["items"]} == {"rev-alice": "alice", "rev-bob": "bob"}
    ad = queue("admin")
    assert {i["review_id"] for i in ad["items"]} == {"rev-alice", "rev-bob", "rev-legacy"} and ad["total"] == 3
    legacy = next(i for i in ad["items"] if i["review_id"] == "rev-legacy")
    assert legacy["submitted_by"] is None
    # Reason filter (runs in Python) applies the same visibility.
    r = c.get("/v1/reviews", headers=CALLERS["reviewer"], params={"reason": "judge"}).json()
    assert r["total"] == 2


# ------------------------------------------------------------------ submitted_by


def test_submitted_by_on_results_and_review_cases(env):
    c = env["client"]
    for path in ("/jobs/job-alice/result", "/v1/videos/vid-alice/results"):
        assert c.get(path, headers=CALLERS["owner"]).json()["submitted_by"] == "alice"
        assert c.get(path, headers=CALLERS["reviewer"]).json()["submitted_by"] == "alice"
    assert c.get("/jobs/job-alice", headers=CALLERS["owner"]).json()["submitted_by"] == "alice"
    case = c.get("/v1/reviews/rev-alice", headers=CALLERS["reviewer"]).json()
    assert case["submitted_by"] == "alice" and case["decision"] is None
    d = c.post("/v1/reviews/rev-alice/decision", headers=CALLERS["reviewer"], json=DECISION).json()
    assert d["case"]["submitted_by"] == "alice" and d["case"]["decision"]["reviewer_id"] == "rita"
    assert c.get("/v1/reviews/rev-legacy", headers=CALLERS["admin"]).json()["submitted_by"] is None


# ------------------------------------------------------------------ own video


@pytest.mark.parametrize("role", ["reviewer", "admin"])
def test_nobody_decides_a_case_on_their_own_video(env, role):
    c = env["client"]
    me = auth("alice", role)
    assert c.get("/v1/reviews/rev-alice", headers=me).status_code == 200  # can read it
    r = c.post("/v1/reviews/rev-alice/decision", headers=me, json=DECISION)
    assert r.status_code == 403 and "own video" in r.json()["detail"]
    r = c.post("/v1/reviews/rev-alice/claims/c1/severity", headers=me,
               json={"severity": "LOW", "reason": "mine"})
    assert r.status_code == 403
    s = env["Session"]()
    case = s.get(HumanReview, "rev-alice")
    assert case.status == ReviewCaseStatus.OPEN and case.reviewer_id is None
    assert case.claim_severities["c1"].get("override") is None
    assert s.query(AuditEvent).count() == 0
    s.close()
    # Someone else's case is fine.
    assert c.post("/v1/reviews/rev-bob/decision", headers=me, json=DECISION).status_code == 200


def test_own_video_counts_even_when_someone_else_submitted_the_job(env):
    """A re-analysis job keeps its owner; a case is still "own" if the caller owns the
    video (e.g. a job submitted by someone else on the caller's video)."""
    s = env["Session"]()
    s.get(Job, "job-bob").user_id = "carol"
    s.commit()
    s.close()
    r = env["client"].post("/v1/reviews/rev-bob/decision", headers=auth("bob", "reviewer"), json=DECISION)
    assert r.status_code == 403


def test_role_and_identity_only_from_the_verified_token(env):
    c = env["client"]
    # user_metadata and the top-level role claim are ignored.
    forged = auth("bob", None, user_metadata={"role": "admin"})
    assert c.get("/jobs/job-alice", headers=forged).status_code == 404
    forged = {"Authorization": f"Bearer {jwt.encode({'sub': 'bob', 'aud': 'authenticated', 'role': 'admin', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)}, SECRET, algorithm='HS256')}"}  # noqa: E501
    assert c.get("/jobs/job-alice", headers=forged).status_code == 404
    # A token signed with another key is refused.
    bad = {"Authorization": f"Bearer {jwt.encode({'sub': 'alice', 'app_metadata': {'role': 'admin'}}, 'other-key-0123456789abcdef0123456789', algorithm='HS256')}"}  # noqa: E501
    assert c.get("/jobs/job-alice", headers=bad).status_code == 401
    # Extra body fields can't name a reviewer.
    r = c.post("/v1/reviews/rev-bob/decision", headers=CALLERS["reviewer"],
               json={**DECISION, "reviewer_id": "alice"})
    assert r.status_code == 422
    # A token with a role but no subject sees nothing. (T48: tokens need aud=authenticated.)
    nosub = {"Authorization": f"Bearer {jwt.encode({'app_metadata': {'role': 'admin'}, 'aud': 'authenticated', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)}, SECRET, algorithm='HS256')}"}  # noqa: E501
    assert c.get("/jobs/job-legacy", headers=nosub).status_code == 404
    assert c.get("/v1/jobs", headers=nosub).json()["total"] == 0


# ------------------------------------------------------------------ uploads and jobs


def test_upload_sets_owner_and_dedup_is_per_user(env):
    c = env["client"]
    content = b"\x00\x00\x00\x18ftypisom" + b"same bytes" * 10
    a1 = c.post("/videos/upload", headers=CALLERS["owner"], files={"file": ("a.mp4", content, "video/mp4")})
    a2 = c.post("/videos/upload", headers=CALLERS["owner"], files={"file": ("a2.mp4", content, "video/mp4")})
    b1 = c.post("/videos/upload", headers=CALLERS["other"], files={"file": ("b.mp4", content, "video/mp4")})
    assert a1.status_code == a2.status_code == b1.status_code == 200
    assert a1.json()["video_id"] == a2.json()["video_id"]            # own duplicate reused
    assert b1.json()["video_id"] != a1.json()["video_id"]             # never another user's
    assert b1.json()["filename"] == "b.mp4"
    s = env["Session"]()
    assert s.get(Video, a1.json()["video_id"]).user_id == "alice"
    assert s.get(Video, b1.json()["video_id"]).user_id == "bob"
    s.close()
    # Bob can't start a job on Alice's upload; Alice can.
    assert c.post("/jobs/create", headers=CALLERS["other"], json={"video_id": a1.json()["video_id"]}).status_code == 404
    j = c.post("/jobs/create", headers=CALLERS["owner"], json={"video_id": a1.json()["video_id"]})
    assert j.status_code == 200
    assert c.get(f"/jobs/{j.json()['job_id']}", headers=CALLERS["other"]).status_code == 404


def test_register_sets_owner_and_dedup_is_per_user(env, monkeypatch):
    from app.api.routers import videos as videos_router
    from app.services.upload_service import storage_key_for
    from app.tests.test_upload_safeguards import _guard, mp4

    guard = _guard()
    env["app"].dependency_overrides[videos_router.get_upload_guard] = lambda: guard
    c = env["client"]
    content = mp4(10.0)
    out = {}
    for who, sub in (("owner", "alice"), ("other", "bob")):
        key = storage_key_for({"sub": sub}, uuid.uuid4().hex, "clip.mp4")
        env["storage"].objects[key] = content
        r = c.post("/v1/videos", headers=CALLERS[who], json={"storage_key": key})
        assert r.status_code == 201, r.text
        out[sub] = r.json()
    assert out["alice"]["video_id"] != out["bob"]["video_id"] and not out["bob"]["duplicate"]
    s = env["Session"]()
    assert s.get(Video, out["alice"]["video_id"]).user_id == "alice"
    assert s.get(Video, out["bob"]["video_id"]).user_id == "bob"
    s.close()
    # Registering someone else's storage key looks like a missing upload.
    akey = storage_key_for({"sub": "alice"}, uuid.uuid4().hex, "x.mp4")
    env["storage"].objects[akey] = content
    assert c.post("/v1/videos", headers=CALLERS["other"], json={"storage_key": akey}).status_code == 404
    # Alice registering the same bytes again reuses her video.
    r = c.post("/v1/videos", headers=CALLERS["owner"], json={"storage_key": akey})
    assert r.status_code == 201 and r.json()["duplicate"] and r.json()["video_id"] == out["alice"]["video_id"]


def test_create_job_reuses_only_the_callers_own_job(env):
    c = env["client"]
    s = env["Session"]()
    s.get(Job, "job-alice").status = JobStatus.SUCCESS
    s.commit()
    s.close()
    mine = c.post("/jobs/create", headers=CALLERS["owner"], json={"video_id": "vid-alice"}).json()
    assert mine["job_id"] == "job-alice"
    theirs = c.post("/jobs/create", headers=CALLERS["reviewer"], json={"video_id": "vid-alice"}).json()
    assert theirs["job_id"] != "job-alice"
    s = env["Session"]()
    assert s.get(Job, theirs["job_id"]).user_id == "rita"
    s.close()


def test_legacy_shared_video_job_owners_keep_their_results(env):
    """Before T33 duplicates were global, so two users can have jobs on one NULL-owner
    video. Each still reaches their own results by video; nobody sees the other's."""
    s = env["Session"]()
    s.add(Job(id="job-bob-on-legacy", video_id="vid-legacy", status=JobStatus.REVIEW_REQUIRED, user_id="bob",
              created_at=T0 + timedelta(hours=1)))
    s.add(Result(job_id="job-bob-on-legacy", label="UNCERTAIN", confidence=0.1, explanation="b",
                 evidence_snippets=[], combined_content="", provider="p", model_used="m", latency_ms=1))
    s.add(Job(id="job-alice-on-legacy", video_id="vid-legacy", status=JobStatus.REVIEW_REQUIRED,
              user_id="alice", created_at=T0 + timedelta(hours=2)))
    s.add(Result(job_id="job-alice-on-legacy", label="MISINFO", confidence=0.1, explanation="a",
                 evidence_snippets=[], combined_content="", provider="p", model_used="m", latency_ms=1))
    s.commit()
    s.close()
    c = env["client"]
    assert c.get("/v1/videos/vid-legacy/results", headers=CALLERS["other"]).json()["job_id"] == "job-bob-on-legacy"
    assert c.get("/v1/videos/vid-legacy/results", headers=CALLERS["owner"]).json()["job_id"] == "job-alice-on-legacy"
    assert c.get("/v1/videos/vid-legacy/results", headers=auth("carol")).status_code == 404


def test_local_dev_mode_keeps_legacy_rows_visible(env, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_AUTH", False)
    c = env["client"]
    assert c.get("/jobs/job-legacy").status_code == 200
    assert c.get("/jobs/job-alice").status_code == 404   # the dev user is not alice
    assert {r["job_id"] for r in c.get("/jobs").json()} == {"job-legacy"}


# ------------------------------------------------------------------ ownership unit rules


@pytest.mark.parametrize("user,row_owner,visible", [
    ({"sub": "a"}, "a", True),
    ({"sub": "a"}, "b", False),
    ({"sub": "a"}, None, False),
    ({"sub": "r", "app_metadata": {"role": "reviewer"}}, "b", True),
    ({"sub": "r", "app_metadata": {"role": "reviewer"}}, None, False),
    ({"sub": "x", "app_metadata": {"role": "admin"}}, None, True),
    ({"sub": "x", "app_metadata": {"roles": ["reviewer", "admin"]}}, "b", True),
    ({"sub": "x", "user_metadata": {"role": "admin"}}, None, False),
    ({"app_metadata": {"role": "admin"}}, None, False),
    (None, "a", False),
    ({}, None, False),
])
def test_can_view_job_rule(monkeypatch, user, row_owner, visible):
    from app.api import ownership

    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    assert ownership.can_view_job(Job(id="j", video_id="v", user_id=row_owner), user) is visible


# ------------------------------------------------------------------ migration


def _alembic(url, monkeypatch):
    from alembic.config import Config

    monkeypatch.setenv("DATABASE_URL_SYNC", url)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "app" / "db" / "migrations"))
    return cfg


def test_alembic_has_one_head(monkeypatch, tmp_path):
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic(f"sqlite:///{tmp_path / 'x.db'}", monkeypatch))
    assert len(script.get_heads()) == 1


def test_migration_backfills_video_owner_and_makes_dedup_per_user(monkeypatch, tmp_path):
    from alembic import command

    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = _alembic(url, monkeypatch)
    command.upgrade(cfg, "0012")
    engine = create_engine(url)
    with engine.begin() as conn:
        for vid, h in (("v-one", "1"), ("v-two", "2"), ("v-none", "3"), ("v-legacy", "4")):
            conn.execute(text("INSERT INTO videos (id, filename, file_path, file_size, file_hash, created_at) "
                              "VALUES (:i, 'f', 'p', 1, :h, CURRENT_TIMESTAMP)"), {"i": vid, "h": h * 64})
        for jid, vid, owner in (("j1", "v-one", "alice"), ("j2", "v-one", "alice"), ("j3", "v-two", "alice"),
                                ("j4", "v-two", "bob"), ("j5", "v-legacy", None)):
            conn.execute(text("INSERT INTO jobs (id, video_id, status, user_id, attempts, created_at, updated_at) "
                              "VALUES (:j, :v, 'SUCCESS', :o, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"), {"j": jid, "v": vid, "o": owner})
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        owners = dict(conn.execute(text("SELECT id, user_id FROM videos")).all())
    assert owners == {"v-one": "alice", "v-two": None, "v-none": None, "v-legacy": None}
    insp = inspect(engine)
    assert "user_id" in {c["name"] for c in insp.get_columns("videos")}
    assert any(ix["name"] == "ix_videos_user_id" for ix in insp.get_indexes("videos"))
    # The same file for two users is allowed now; twice for one user is not.
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO videos (id, filename, file_path, file_size, file_hash, user_id, created_at) "
                          "VALUES ('v-bob', 'f', 'p', 1, :h, 'bob', CURRENT_TIMESTAMP)"), {"h": "1" * 64})
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO videos (id, filename, file_path, file_size, file_hash, user_id, created_at) "
                              "VALUES ('v-bob2', 'f', 'p', 1, :h, 'bob', CURRENT_TIMESTAMP)"), {"h": "1" * 64})
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM videos WHERE id = 'v-bob'"))
    command.downgrade(cfg, "0012")
    assert "user_id" not in {c["name"] for c in inspect(create_engine(url)).get_columns("videos")}
    command.upgrade(cfg, "head")


def test_migration_on_postgres(monkeypatch):
    if not PG_DSN:
        pytest.skip("set LIBRARY_TEST_PG_DSN to a throwaway Postgres database with pgvector")
    from alembic import command
    from sqlalchemy.engine import make_url

    name = f"t33m_{uuid.uuid4().hex[:12]}"
    admin = create_engine(PG_DSN, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    try:
        url = make_url(PG_DSN).set(database=name).render_as_string(hide_password=False)
        cfg = _alembic(url, monkeypatch)
        command.upgrade(cfg, "0012")
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO videos (id, filename, file_path, file_size, file_hash, created_at) "
                              "VALUES ('v', 'f', 'p', 1, :h, CURRENT_TIMESTAMP)"), {"h": "a" * 64})
            conn.execute(text("INSERT INTO jobs (id, video_id, status, user_id, attempts, created_at, updated_at) "
                              "VALUES ('j', 'v', 'SUCCESS', 'alice', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT user_id FROM videos")).scalar() == "alice"
        command.downgrade(cfg, "0012")
        command.upgrade(cfg, "head")
        engine.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        admin.dispose()


# ------------------------------------------------------------------ legacy owner script


def _script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("assign_owners", BACKEND / "scripts" / "assign_owners.py")
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules["assign_owners"] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


def test_assign_owners_script_dry_run_then_apply(env, capsys):
    mod = _script()
    S = env["Session"]
    # dry run: nothing changes
    s = S()
    assert mod.main(["set", "--user", "alice", "--video", "vid-legacy", "--with-jobs", "--actor", "ops"], db=s) == 0
    s.close()
    s = S()
    assert s.get(Job, "job-legacy").user_id is None and s.get(Video, "vid-legacy").user_id is None
    s.close()
    assert "would set" in capsys.readouterr().out
    # apply
    s = S()
    mod.main(["set", "--user", "alice", "--video", "vid-legacy", "--with-jobs", "--actor", "ops", "--apply"], db=s)
    s.close()
    s = S()
    assert s.get(Job, "job-legacy").user_id == "alice" and s.get(Video, "vid-legacy").user_id == "alice"
    events = s.query(AuditEvent).filter(AuditEvent.action == "owner_assigned").all()
    assert {(e.entity_type, e.entity_id) for e in events} == {("video", "vid-legacy"), ("job", "job-legacy")}
    assert all(e.actor_id == "admin-script:ops" and e.details == {"from": None, "to": "alice"} for e in events)
    s.close()
    # now the owner sees it, others still don't
    c = env["client"]
    assert c.get("/jobs/job-legacy", headers=CALLERS["owner"]).status_code == 200
    assert c.get("/jobs/job-legacy", headers=CALLERS["other"]).status_code == 404
    # an existing owner isn't replaced without --force
    s = S()
    mod.main(["set", "--user", "bob", "--job", "job-alice", "--actor", "ops", "--apply"], db=s)
    s.close()
    assert "--force" in capsys.readouterr().out
    s = S()
    assert s.get(Job, "job-alice").user_id == "alice"
    s.close()


def test_assign_owners_infer_and_csv(env, tmp_path, capsys):
    mod = _script()
    S = env["Session"]
    s = S()
    s.add(Video(id="vid-n", filename="n.mp4", file_path="/n", file_size=1))
    s.flush()
    s.add(Job(id="job-n1", video_id="vid-n", status=JobStatus.SUCCESS, user_id="carol"))
    s.add(Job(id="job-n2", video_id="vid-n", status=JobStatus.SUCCESS))
    s.commit()
    s.close()
    s = S()
    mod.main(["infer", "--actor", "ops", "--apply"], db=s)
    s.close()
    s = S()
    assert s.get(Video, "vid-n").user_id == "carol" and s.get(Job, "job-n2").user_id == "carol"
    assert s.get(Job, "job-legacy").user_id is None    # nothing to infer from
    s.close()
    f = tmp_path / "owners.csv"
    f.write_text("kind,id,user_id\njob,job-legacy,dave\nvideo,vid-legacy,dave\nfile,x,y\njob,nope,dave\n")
    s = S()
    mod.main(["csv", str(f), "--actor", "ops", "--apply"], db=s)
    s.close()
    out = capsys.readouterr().out
    assert "kind must be job or video" in out and "not found" in out
    s = S()
    assert s.get(Job, "job-legacy").user_id == "dave" and s.get(Video, "vid-legacy").user_id == "dave"
    s.close()
    s = S()
    mod.main(["list"], db=s)
    s.close()
    assert "0 jobs and 0 videos have no owner" in capsys.readouterr().out
