import sys
import types

from app.core.extraction import transcription


class FakeWhisperModel:
    created = 0

    def __init__(self, *args, **kwargs):
        FakeWhisperModel.created += 1


def test_whisper_model_is_loaded_once(monkeypatch):
    fake_module = types.ModuleType("faster_whisper")
    fake_module.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    monkeypatch.setattr(transcription, "_whisper_model", None)
    monkeypatch.setattr(transcription, "_cuda_available", lambda: False)
    FakeWhisperModel.created = 0

    first = transcription.get_whisper_model()
    second = transcription.get_whisper_model()

    assert first is second
    assert FakeWhisperModel.created == 1
