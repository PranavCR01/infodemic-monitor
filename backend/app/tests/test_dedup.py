import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models.video import Video
from app.services.video_service import save_video


def make_db():
    engine = create_engine("sqlite:///:memory:")
    Video.__table__.create(bind=engine)

    Session = sessionmaker(bind=engine)
    return Session()


def test_duplicate_video_reuses_existing_video(tmp_path, monkeypatch):
    db = make_db()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))

    content = b"same video bytes"

    first_video = save_video(db, content, "first.mp4")
    second_video = save_video(db, content, "second.mp4")

    assert first_video.id == second_video.id
    assert db.query(Video).count() == 1

    db.close()


def test_new_file_creates_new_video(tmp_path, monkeypatch):
    db = make_db()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))

    first_video = save_video(db, b"first video bytes", "first.mp4")
    second_video = save_video(db, b"different video bytes", "second.mp4")

    assert first_video.id != second_video.id
    assert db.query(Video).count() == 2

    db.close()


def test_file_hash_is_computed_correctly(tmp_path, monkeypatch):
    db = make_db()

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path))

    content = b"video bytes to hash"
    expected_hash = hashlib.sha256(content).hexdigest()

    video = save_video(db, content, "video.mp4")
    assert video.file_hash == expected_hash

    db.close()