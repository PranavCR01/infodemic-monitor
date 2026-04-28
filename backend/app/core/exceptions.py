from __future__ import annotations


class InfodemicError(Exception):
    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause

    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "cause": str(self.cause) if self.cause else None,
        }


class StorageError(InfodemicError):
    def __init__(self, storage_key: str, cause: Exception | None = None):
        super().__init__(f"Storage operation failed for key: {storage_key}", cause)
        self.storage_key = storage_key


class TranscriptionError(InfodemicError):
    def __init__(self, provider: str, cause: Exception | None = None):
        super().__init__(f"Transcription failed (provider={provider})", cause)
        self.provider = provider


class InferenceProviderError(InfodemicError):
    def __init__(self, provider: str, cause: Exception | None = None):
        super().__init__(f"Inference failed (provider={provider})", cause)
        self.provider = provider


class GroundingError(InfodemicError):
    pass


class PipelineError(InfodemicError):
    pass
