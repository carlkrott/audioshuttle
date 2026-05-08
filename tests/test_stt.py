"""Tests for STT engine — all mocked, no actual model download."""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from audioshuttle.stt import STTEngine


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset STTEngine singleton between tests."""
    STTEngine.reset()
    yield
    STTEngine.reset()


def _create_test_wav(path: Path, duration_sec: float = 0.1, sample_rate: int = 16000) -> Path:
    """Create a tiny silent WAV file for testing."""
    n_samples = int(sample_rate * duration_sec)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))
    return path


class TestSTTEngineAvailability:
    def test_available_property_reflects_import(self):
        """available is True when faster_whisper can be imported."""
        # In our test env, faster_whisper may or may not be installed
        engine = STTEngine()
        # Just check it returns a bool
        assert isinstance(engine.available, bool)

    def test_available_false_when_import_fails(self):
        """available is False when faster_whisper is not importable."""
        with patch("audioshuttle.stt._WHISPER_AVAILABLE", False):
            engine = STTEngine()
            assert engine.available is False


class TestSTTEngineTranscription:
    def test_transcribe_with_mock_model(self, tmp_path):
        """transcribe() returns text from mocked WhisperModel."""
        wav_path = _create_test_wav(tmp_path / "test.wav")

        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "  hello world  "
        mock_info = MagicMock()
        mock_info.duration = 0.5
        mock_model.transcribe.return_value = (iter([mock_segment]), mock_info)

        with patch("audioshuttle.stt._WHISPER_AVAILABLE", True), \
             patch("audioshuttle.stt.WhisperModel", return_value=mock_model):
            engine = STTEngine()
            result = engine.transcribe(str(wav_path))
            assert result == "hello world"

    def test_transcribe_raises_when_not_installed(self, tmp_path):
        """transcribe() raises RuntimeError when faster_whisper not installed."""
        wav_path = _create_test_wav(tmp_path / "test.wav")

        with patch("audioshuttle.stt._WHISPER_AVAILABLE", False):
            engine = STTEngine()
            with pytest.raises(RuntimeError, match="faster-whisper not installed"):
                engine.transcribe(str(wav_path))

    def test_transcribe_raises_on_missing_file(self):
        """transcribe() raises FileNotFoundError for non-existent files."""
        with patch("audioshuttle.stt._WHISPER_AVAILABLE", True), \
             patch("audioshuttle.stt.WhisperModel", return_value=MagicMock()):
            engine = STTEngine()
            with pytest.raises(FileNotFoundError):
                engine.transcribe("/nonexistent/audio.wav")


class TestSTTEngineSingleton:
    def test_singleton_returns_same_instance(self):
        """Multiple constructions return the same instance."""
        a = STTEngine(model_size="tiny")
        b = STTEngine(model_size="base")
        assert a is b
        # First init wins — model_size stays "tiny"
        assert a._model_size == "tiny"

    def test_reset_clears_singleton(self):
        """reset() allows a fresh instance."""
        a = STTEngine(model_size="tiny")
        STTEngine.reset()
        b = STTEngine(model_size="base")
        assert a is not b
        assert b._model_size == "base"

    def test_thread_safety(self):
        """Concurrent access to singleton is safe."""
        import threading

        results: list[STTEngine] = []
        errors: list[Exception] = []

        def create_engine():
            try:
                results.append(STTEngine(model_size="tiny"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_engine) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert all(r is results[0] for r in results)
