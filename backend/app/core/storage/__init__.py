from __future__ import annotations

import os
import shutil
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.core.exceptions import StorageError


@runtime_checkable
class StorageBackend(Protocol):
    def upload(self, local_path: str, destination_key: str) -> str: ...
    def get_download_url(self, storage_key: str) -> str: ...
    def delete(self, storage_key: str) -> None: ...
    # Signed direct uploads (T20, design §1). The browser PUTs the file to the
    # returned URL; the API then downloads it once to validate and hash it.
    def create_signed_upload_url(self, storage_key: str) -> dict: ...
    def download(self, storage_key: str) -> bytes: ...
    # Short-lived read URL for the result page's video player (T29, design §15
    # "short-lived signed URLs"). Only issued after the job ownership check.
    def create_signed_download_url(self, storage_key: str, expires_in: int) -> str: ...


class SignedUploadUnsupported(StorageError):
    """The configured backend can't issue signed upload URLs (local storage)."""


class SignedUrlUnsupported(StorageError):
    """The configured backend can't issue signed read URLs (local storage)."""


class LocalBackend:
    def upload(self, local_path: str, destination_key: str) -> str:
        try:
            dest = os.path.join(settings.LOCAL_STORAGE_ROOT, destination_key)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.abspath(local_path) != os.path.abspath(dest):
                shutil.copy2(local_path, dest)
            return destination_key
        except Exception as exc:
            raise StorageError(destination_key, exc) from exc

    def get_download_url(self, storage_key: str) -> str:
        return os.path.join(settings.LOCAL_STORAGE_ROOT, storage_key)

    def create_signed_upload_url(self, storage_key: str) -> dict:
        # Local storage has no URL a browser could upload to; dev clients keep
        # using POST /videos/upload.
        raise SignedUploadUnsupported(storage_key)

    def create_signed_download_url(self, storage_key: str, expires_in: int) -> str:
        # A filesystem path is not a URL a browser may fetch; no playback in local dev.
        raise SignedUrlUnsupported(storage_key)

    def download(self, storage_key: str) -> bytes:
        try:
            with open(os.path.join(settings.LOCAL_STORAGE_ROOT, storage_key), "rb") as f:
                return f.read()
        except Exception as exc:
            raise StorageError(storage_key, exc) from exc

    def delete(self, storage_key: str) -> None:
        try:
            path = os.path.join(settings.LOCAL_STORAGE_ROOT, storage_key)
            if os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass


def get_storage_backend() -> StorageBackend:
    if settings.STORAGE_BACKEND == "supabase":
        from .supabase_backend import SupabaseBackend
        return SupabaseBackend()
    return LocalBackend()
