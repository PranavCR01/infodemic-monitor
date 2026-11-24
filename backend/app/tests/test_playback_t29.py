"""T29: signed playback URL for the result page's video player.

Storage is a fake in memory and the Supabase client is a mock; no storage or network
calls. Per-user ownership: the owner column is T27's (queue), so the "other user"
tests install an owner rule through ``app.api.ownership.can_view_job``, the single
hook every result read uses, and check that the playback route obeys it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import ownership
from app.api.routers import playback
from app.api.routers.playback import get_storage
from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.storage import LocalBackend, SignedUrlUnsupported
from app.core.storage.supabase_backend import SupabaseBackend
from app.db.base import Base
from app.db.models.job import Job, JobStatus
from app.db.models.video import Video
from app.db.session import get_db

app = FastAPI()
app.include_router(playback.router)

OWNER = {"sub": "user-a"}
OTHER = {"sub": "user-b"}
KEY = "uploads/user-a/0123456789abcdef0123456789abcdef/clip.mp4"


class FakeStorage:
    def __init__(self):
        self.calls: list[tuple[str, int]] = []
        self.fail: Exception | None = None
        self.url = "https://storage.test/object/sign/videos/{key}?token=secret-token"

    def create_signed_download_url(self, key, expires_in):
        self.calls.append((key, expires_in))
        if self.fail:
            raise self.fail
        return self.url.format(key=key)


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        s.add(Video(id="v1", filename="clip.mp4", file_path=KEY, file_size=10, storage_key=KEY))
        s.add(Video(id="v-local", filename="old.mp4", file_path="/app/storage/old.mp4", file_size=10))
        s.add(Job(id="j1", video_id="v1", status=JobStatus.SUCCESS))
        s.add(Job(id="j-review", video_id="v1", status=JobStatus.REVIEW_REQUIRED))
        s.add(Job(id="j-local", video_id="v-local", status=JobStatus.SUCCESS))
        s.commit()

    storage = FakeStorage()
    state = {"user": OWNER, "storage": storage}

    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_storage] = lambda: state["storage"]
    # Owner rule as T27 will enforce it: every seeded job belongs to user-a.
    owners = {"j1": "user-a", "j-review": "user-a", "j-local": "user-a"}
    monkeypatch.setattr(ownership, "can_view_job", lambda job, user: bool(user) and owners.get(job.id) == user.get("sub"))
    state["client"] = TestClient(app)
    yield state
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ owner


def test_owner_gets_short_lived_signed_url(env):
    before = datetime.now(timezone.utc)
    r = env["client"].get("/v1/jobs/j1/playback")
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == "j1" and body["video_id"] == "v1"
    assert body["url"].startswith("https://storage.test/object/sign/videos/" + KEY)
    assert body["filename"] == "clip.mp4"
    ttl = settings.PLAYBACK_URL_TTL_SECONDS
    assert body["expires_in_seconds"] == ttl
    assert env["storage"].calls == [(KEY, ttl)]
    expires = datetime.fromisoformat(body["expires_at"])
    assert before + timedelta(seconds=ttl) <= expires <= datetime.now(timezone.utc) + timedelta(seconds=ttl)


def test_ttl_is_short_and_configurable(env, monkeypatch):
    assert settings.PLAYBACK_URL_TTL_SECONDS <= 900  # short-lived (§15), not the 1 h legacy URL
    monkeypatch.setattr(settings, "PLAYBACK_URL_TTL_SECONDS", 120)
    r = env["client"].get("/v1/jobs/j1/playback")
    assert r.json()["expires_in_seconds"] == 120
    assert env["storage"].calls[-1] == (KEY, 120)


def test_response_is_not_cacheable(env):
    r = env["client"].get("/v1/jobs/j1/playback")
    assert r.headers["cache-control"] == "no-store"


def test_new_url_minted_per_request(env):
    env["client"].get("/v1/jobs/j1/playback")
    env["client"].get("/v1/jobs/j1/playback")
    assert len(env["storage"].calls) == 2


def test_job_in_review_is_playable_by_owner(env):
    assert env["client"].get("/v1/jobs/j-review/playback").status_code == 200


# ------------------------------------------------------------------ access


def test_other_user_gets_404_and_no_url_is_signed(env):
    env["user"] = OTHER
    r = env["client"].get("/v1/jobs/j1/playback")
    assert r.status_code == 404
    assert r.json()["detail"] == "Job not found"  # same answer as a missing job
    assert "url" not in r.json()
    assert env["storage"].calls == []


def test_other_users_denial_matches_missing_job(env):
    env["user"] = OTHER
    denied = env["client"].get("/v1/jobs/j1/playback")
    missing = env["client"].get("/v1/jobs/does-not-exist/playback")
    assert (denied.status_code, denied.json()) == (missing.status_code, missing.json())


def test_unknown_job_404(env):
    r = env["client"].get("/v1/jobs/nope/playback")
    assert r.status_code == 404
    assert env["storage"].calls == []


def test_route_goes_through_shared_ownership_hook(env, monkeypatch):
    seen = []
    monkeypatch.setattr(ownership, "can_view_job", lambda job, user: seen.append((job.id, user["sub"])) or True)
    env["client"].get("/v1/jobs/j1/playback")
    assert seen == [("j1", "user-a")]


def test_requires_authentication(env, monkeypatch):
    app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr(settings, "REQUIRE_AUTH", True)
    r = env["client"].get("/v1/jobs/j1/playback")
    assert r.status_code == 401
    assert env["storage"].calls == []


# ------------------------------------------------------------------ failures


def test_video_without_storage_object_404(env):
    r = env["client"].get("/v1/jobs/j-local/playback")
    assert r.status_code == 404
    assert r.json()["detail"] == "No playable video for this job"
    assert env["storage"].calls == []


def test_local_backend_answers_501(env):
    env["storage"] = LocalBackend()
    r = env["client"].get("/v1/jobs/j1/playback")
    assert r.status_code == 501


def test_storage_error_is_503_and_url_never_logged(env, caplog):
    env["storage"].fail = StorageError(KEY, RuntimeError("down"))
    with caplog.at_level(logging.WARNING):
        r = env["client"].get("/v1/jobs/j1/playback")
    assert r.status_code == 503
    assert "token" not in caplog.text


def test_empty_url_from_storage_is_503(env):
    env["storage"].url = ""
    assert env["client"].get("/v1/jobs/j1/playback").status_code == 503


def test_success_does_not_log_signed_url(env, caplog):
    with caplog.at_level(logging.DEBUG):
        env["client"].get("/v1/jobs/j1/playback")
    assert "secret-token" not in caplog.text


# ------------------------------------------------------------------ storage backends


def _supabase_with(result):
    backend = SupabaseBackend()
    client = MagicMock()
    client.storage.from_.return_value.create_signed_url.return_value = result
    backend._client = client  # no create_client, no network
    return backend, client


@pytest.mark.parametrize(
    "result",
    [{"signedURL": "https://s/x"}, {"signedUrl": "https://s/x"}, {"signed_url": "https://s/x"}],
)
def test_supabase_signed_download_url_shapes(result):
    backend, client = _supabase_with(result)
    assert backend.create_signed_download_url("k", 300) == "https://s/x"
    client.storage.from_.assert_called_with(settings.SUPABASE_STORAGE_BUCKET)
    client.storage.from_.return_value.create_signed_url.assert_called_once_with(path="k", expires_in=300)


def test_supabase_object_result():
    obj = MagicMock(spec=["signed_url"])
    obj.signed_url = "https://s/y"
    backend, _ = _supabase_with(obj)
    assert backend.create_signed_download_url("k", 60) == "https://s/y"


def test_supabase_failure_is_storage_error():
    backend, client = _supabase_with(None)
    client.storage.from_.return_value.create_signed_url.side_effect = RuntimeError("boom")
    with pytest.raises(StorageError):
        backend.create_signed_download_url("k", 60)


def test_legacy_get_download_url_keeps_one_hour():
    backend, client = _supabase_with({"signedURL": "https://s/z"})
    assert backend.get_download_url("k") == "https://s/z"
    client.storage.from_.return_value.create_signed_url.assert_called_once_with(path="k", expires_in=3600)


def test_local_backend_has_no_signed_read_url():
    with pytest.raises(SignedUrlUnsupported):
        LocalBackend().create_signed_download_url("k", 60)


def test_mounted_in_main_app():
    import importlib.util

    if importlib.util.find_spec("greenlet") is None:
        # app.main imports the async health check; assert the include line instead.
        import pathlib

        src = (pathlib.Path(__file__).resolve().parents[1] / "main.py").read_text()
        assert "app.include_router(playback.router)" in src
        return
    from app.main import app as main_app

    assert any(getattr(r, "path", "") == "/v1/jobs/{job_id}/playback" for r in main_app.routes)
