from __future__ import annotations

import logging

from app.core.config import settings
from app.core.exceptions import StorageError

logger = logging.getLogger(__name__)


class SupabaseBackend:
    def __init__(self) -> None:
        self._client = None  # lazy init

    def _get_client(self):
        if self._client is None:
            from supabase import create_client
            self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        return self._client

    def upload(self, local_path: str, destination_key: str) -> str:
        try:
            client = self._get_client()
            with open(local_path, "rb") as f:
                content = f.read()
            client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
                path=destination_key,
                file=content,
                file_options={"upsert": "true"},
            )
            return destination_key
        except Exception as exc:
            raise StorageError(destination_key, exc) from exc

    def get_download_url(self, storage_key: str) -> str:
        try:
            client = self._get_client()
            result = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(
                path=storage_key,
                expires_in=3600,
            )
            # supabase-py v2 returns an object; older versions return a dict
            if hasattr(result, "signed_url"):
                return result.signed_url
            if isinstance(result, dict):
                return result.get("signedURL") or result.get("signed_url", "")
            return str(result)
        except Exception as exc:
            raise StorageError(storage_key, exc) from exc

    def delete(self, storage_key: str) -> None:
        try:
            client = self._get_client()
            client.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([storage_key])
        except Exception as exc:
            logger.warning("Failed to delete storage key '%s': %s", storage_key, exc)
