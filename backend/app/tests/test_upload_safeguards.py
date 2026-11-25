"""T20: upload safeguards and the §1 signed-upload endpoints.

Storage is a fake in memory; no Supabase calls. Durations come from a stub probe
except where the real MP4 ``mvhd`` reader is under test.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.guardrails.config import load_guardrails
from app.core.guardrails.limits import DailyQuota, InputRejected, RateLimiter
from app.core.guardrails.media_probe import ffprobe_duration, iso_duration, probe_duration
from app.core.storage import LocalBackend, SignedUploadUnsupported
from app.db.base import Base
from app.db.models.video import Video
from app.db.session import get_db
from fastapi import FastAPI

from app.api.routers import videos as videos_router
from app.api.routers.videos import get_storage
from app.services.upload_service import UploadGuard, get_upload_guard, owns_key, storage_key_for


# The video routers alone, as app.main mounts them (app.main also pulls in the
# async health check, which needs greenlet; not installed in the test image).
app = FastAPI()
app.include_router(videos_router.router)
app.include_router(videos_router.v1_router)


# ------------------------------------------------------------------ media bytes


def _box(kind: bytes, body: bytes) -> bytes:
    return (8 + len(body)).to_bytes(4, "big") + kind + body


def _mvhd(seconds: float, timescale: int = 1000, version: int = 0) -> bytes:
    if version == 1:
        body = bytes([1, 0, 0, 0]) + b"\x00" * 16 + timescale.to_bytes(4, "big") + int(seconds * timescale).to_bytes(8, "big")
    else:
        body = bytes(4) + b"\x00" * 8 + timescale.to_bytes(4, "big") + int(seconds * timescale).to_bytes(4, "big")
    return _box(b"mvhd", body + b"\x00" * 80)


def mp4(seconds: float = 30.0, payload: bytes = b"\x00" * 64, version: int = 0) -> bytes:
    return (
        _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2mp41")
        + _box(b"moov", _mvhd(seconds, version=version))
        + _box(b"mdat", payload)
    )


WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 8 + b"webm" + b"\x00" * 64


# ------------------------------------------------------------------ fixtures


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.signed: list[str] = []
        self.deleted: list[str] = []
        self.fail_sign = False

    def create_signed_upload_url(self, key):
        if self.fail_sign:
            raise StorageError(key, RuntimeError("down"))
        self.signed.append(key)
        return {"signed_url": f"https://storage.test/upload/{key}?token=t", "token": "t", "path": key}

    def download(self, key):
        if key not in self.objects:
            raise StorageError(key, FileNotFoundError(key))
        return self.objects[key]

    def delete(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)

    def upload(self, local_path, key):  # pragma: no cover - not used by these routes
        return key

    def get_download_url(self, key):  # pragma: no cover
        return key


def _guard(**overrides):
    base = load_guardrails().input.model_dump()
    base.update(overrides)
    limits = type(load_guardrails().input).model_validate(base)
    clock = [0.0]
    g = UploadGuard(
        limits=limits,
        probe=lambda content, container: 30.0,
        rate_limiter=RateLimiter(limits.rate_limit.requests, limits.rate_limit.window_seconds, clock=lambda: clock[0]),
        quota=DailyQuota(limits.uploads_per_user_per_day, clock=lambda: datetime(2026, 11, 23, tzinfo=timezone.utc)),
    )
    return g


USER = {"sub": "user-a"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    storage = FakeStorage()
    state = {"user": USER, "guard": _guard(), "storage": storage}

    def db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_upload_guard] = lambda: state["guard"]
    app.dependency_overrides[get_storage] = lambda: state["storage"]
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    state["client"] = TestClient(app)
    state["Session"] = Session
    yield state
    app.dependency_overrides.clear()


def _sign(env, filename="clip.mp4", **extra):
    return env["client"].post("/v1/videos/uploads", json={"filename": filename, **extra})


def _upload_and_register(env, content, filename="clip.mp4"):
    r = _sign(env, filename, size_bytes=len(content) or None)
    assert r.status_code == 201, r.text
    key = r.json()["storage_key"]
    env["storage"].objects[key] = content
    return key, env["client"].post("/v1/videos", json={"storage_key": key})


# ------------------------------------------------------------ signed URL endpoint


def test_signed_upload_returns_a_url_under_the_callers_prefix(env):
    r = _sign(env, size_bytes=1000, content_type="video/mp4")
    assert r.status_code == 201
    body = r.json()
    assert body["storage_key"].startswith("uploads/user-a/")
    assert body["storage_key"].endswith("/clip.mp4")
    assert body["signed_url"].startswith("https://storage.test/upload/")
    assert body["max_bytes"] == load_guardrails().input.max_file_bytes
    assert env["storage"].signed == [body["storage_key"]]


@pytest.mark.parametrize("payload,status,code", [
    ({"filename": "big.mp4", "size_bytes": 10**12}, 413, "file_too_large"),
    ({"filename": "empty.mp4", "size_bytes": 0}, 422, "empty_file"),
    ({"filename": "doc.pdf"}, 415, "unsupported_media"),
    ({"filename": "clip.mp4", "content_type": "application/pdf"}, 415, "unsupported_media"),
])
def test_signed_upload_rejects_declared_limits(env, payload, status, code):
    r = env["client"].post("/v1/videos/uploads", json=payload)
    assert r.status_code == status
    assert r.json()["detail"]["code"] == code
    assert env["storage"].signed == []


def test_signed_upload_filename_is_sanitised(env):
    key = _sign(env, filename="../../etc/pa ss.mp4").json()["storage_key"]
    assert ".." not in key and " " not in key
    assert key.count("/") == 3


def test_signed_upload_rate_limit_and_quota(env):
    env["guard"] = _guard(rate_limit={"requests": 2, "window_seconds": 60})
    assert _sign(env).status_code == 201
    assert _sign(env).status_code == 201
    r = _sign(env)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"

    env["guard"] = _guard(uploads_per_user_per_day=1)
    assert _sign(env).status_code == 201
    r = _sign(env)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "quota_exceeded"
    env["user"] = {"sub": "user-b"}  # quotas are per user
    assert _sign(env).status_code == 201


def test_signed_upload_storage_errors(env):
    env["storage"].fail_sign = True
    assert _sign(env).status_code == 503
    env["storage"] = LocalBackend()
    assert _sign(env).status_code == 501


def test_local_backend_cannot_sign():
    with pytest.raises(SignedUploadUnsupported):
        LocalBackend().create_signed_upload_url("uploads/u/x/a.mp4")


# ------------------------------------------------------------ register endpoint


def test_register_valid_upload(env):
    key, r = _upload_and_register(env, mp4())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["duplicate"] is False
    assert body["container"] == "mp4"
    assert body["duration_seconds"] == 30.0
    s = env["Session"]()
    video = s.get(Video, body["video_id"])
    assert video.storage_key == key and video.file_size == len(mp4())
    assert len(video.file_hash) == 64


def test_register_reuses_a_known_file_and_drops_the_copy(env):
    _, first = _upload_and_register(env, mp4())
    key2, second = _upload_and_register(env, mp4())
    assert second.status_code == 201
    assert second.json()["duplicate"] is True
    assert second.json()["video_id"] == first.json()["video_id"]
    assert key2 in env["storage"].deleted


def test_register_missing_object_is_404(env):
    key = _sign(env).json()["storage_key"]
    r = env["client"].post("/v1/videos", json={"storage_key": key})
    assert r.status_code == 404


@pytest.mark.parametrize("key", [
    "uploads/user-b/" + "0" * 32 + "/clip.mp4",      # someone else's
    "uploads/user-a/../user-b/" + "0" * 32 + "/x.mp4",  # traversal
    "videos/abc/clip.mp4",                              # outside the upload area
    "uploads/user-a/not-an-id/clip.mp4",
])
def test_register_refuses_keys_the_caller_does_not_own(env, key):
    env["storage"].objects[key] = mp4()
    r = env["client"].post("/v1/videos", json={"storage_key": key})
    assert r.status_code == 404
    assert env["storage"].deleted == []


@pytest.mark.parametrize("content,filename,status,code", [
    (b"%PDF-1.4" + b"\x00" * 64, "clip.mp4", 415, "unsupported_media"),
    (mp4()[:-10], "clip.mp4", 422, "corrupt_media"),              # cut off mid-transfer
    (WEBM, "clip.mp4", 415, "media_mismatch"),
    (b"", "clip.mp4", 422, "empty_file"),
])
def test_register_rejects_bad_files_and_deletes_them(env, content, filename, status, code):
    key, r = _upload_and_register(env, content, filename)
    assert r.status_code == status, r.text
    assert r.json()["detail"]["code"] == code
    assert key in env["storage"].deleted
    assert env["Session"]().query(Video).count() == 0


def test_register_checks_the_real_size_not_the_declared_one(env):
    env["guard"] = _guard(max_file_bytes=200)
    key, r = _upload_and_register(env, mp4(payload=b"\x00" * 10))
    assert r.status_code == 201
    r = _sign(env, size_bytes=100)
    key = r.json()["storage_key"]
    env["storage"].objects[key] = mp4(payload=b"\x00" * 500)  # lied about the size
    r = env["client"].post("/v1/videos", json={"storage_key": key})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "file_too_large"


@pytest.mark.parametrize("seconds,status,code", [
    (5000.0, 422, "too_long"),
    (0.2, 422, "too_short"),
    (None, 422, "corrupt_media"),
])
def test_register_applies_the_duration_limit(env, seconds, status, code):
    env["guard"]._probe = lambda content, container: seconds
    _, r = _upload_and_register(env, mp4())
    assert r.status_code == status and r.json()["detail"]["code"] == code


def test_register_uses_the_real_mvhd_duration(env):
    env["guard"]._probe = probe_duration
    _, r = _upload_and_register(env, mp4(seconds=900))  # over the 180 s limit
    assert r.json()["detail"]["code"] == "too_long"
    _, r = _upload_and_register(env, mp4(seconds=42, payload=b"\x01" * 64))
    assert r.status_code == 201 and r.json()["duration_seconds"] == 42.0


# ------------------------------------------------------------ legacy route


def _legacy(env, content, filename="clip.mp4"):
    return env["client"].post("/videos/upload", files={"file": (filename, content, "video/mp4")})


def test_legacy_upload_unchanged_when_flag_off(env, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_SAFEGUARDS", False)
    r = _legacy(env, b"not a video at all", "notes.txt")
    assert r.status_code == 200
    assert set(r.json()) == {"video_id", "filename", "file_size"}


def test_legacy_upload_enforces_limits_when_flag_on(env, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_SAFEGUARDS", True)
    r = _legacy(env, b"not a video at all", "notes.txt")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "unsupported_media"
    r = _legacy(env, mp4()[:-10])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "corrupt_media"
    env["guard"]._probe = lambda c, k: 4000.0
    assert _legacy(env, mp4()).json()["detail"]["code"] == "too_long"
    env["guard"]._probe = lambda c, k: 30.0
    r = _legacy(env, mp4())
    assert r.status_code == 200 and set(r.json()) == {"video_id", "filename", "file_size"}


def test_legacy_upload_rate_limit_and_quota_when_flag_on(env, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_SAFEGUARDS", True)
    env["guard"] = _guard(uploads_per_user_per_day=1)
    assert _legacy(env, mp4()).status_code == 200
    r = _legacy(env, mp4(payload=b"\x02" * 64))
    assert r.status_code == 429 and r.json()["detail"]["code"] == "quota_exceeded"


# ------------------------------------------------------------ helpers


def test_iso_duration_reads_mvhd_versions():
    assert iso_duration(mp4(seconds=12.5)) == 12.5
    assert iso_duration(mp4(seconds=70, version=1)) == 70.0
    no_mvhd = _box(b"ftyp", b"isom") + _box(b"moov", b"\x00" * 16)
    assert iso_duration(no_mvhd) is None
    assert iso_duration(b"garbage") is None


def test_ffprobe_failure_reads_as_no_duration():
    # Garbage bytes: ffprobe (if installed) fails; if not installed, also None.
    assert ffprobe_duration(b"\x00" * 32, ".mkv") is None
    assert probe_duration(WEBM, "webm") is None


def test_ffprobe_missing_reads_as_no_duration(monkeypatch):
    import app.core.guardrails.media_probe as mp
    monkeypatch.setattr(mp.shutil, "which", lambda name: None)
    assert mp.ffprobe_duration(WEBM, ".webm") is None


def test_owns_key_and_storage_key_for():
    key = storage_key_for({"sub": "u/1"}, "a" * 32, "x y.mp4")
    assert key == "uploads/u_1/" + "a" * 32 + "/x_y.mp4"
    assert owns_key({"sub": "u/1"}, key)
    assert not owns_key({"sub": "u_2"}, key)


def test_guard_raises_input_rejected_directly():
    g = _guard()
    with pytest.raises(InputRejected):
        g.check_declared("a.exe", None)
