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
