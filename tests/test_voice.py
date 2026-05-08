"""Tests for VoicePipeline and VoiceHotkey."""

from __future__ import annotations

import asyncio
import io
import struct
import wave
from unittest.mock import MagicMock, patch

import pytest


def _make_wav(sample_rate: int = 16000, duration_ms: int = 100) -> bytes:
    """Create a minimal WAV file with silence for testing."""
    buf = io.BytesIO()
    num_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    return buf.getvalue()


class TestVoicePipeline:
    """Test VoicePipeline with mocked components."""

    def _make_pipeline(self, **overrides):
        from audioshuttle.voice import VoicePipeline

        defaults = {
            "stt_engine": MagicMock(),
            "model_server": None,
            "bridge": None,
            "translator": None,
        }
        defaults.update(overrides)
        return VoicePipeline(**defaults)

    def test_process_audio_basic(self):
        """Audio → STT → translate → execute."""
        from audioshuttle.models import TranslationResult

        stt = MagicMock()
        stt.transcribe.return_value = "play"

        translator = MagicMock()
        translator.translate_multi.return_value = [TranslationResult(
            success=True, tool="transport_control", args={"action": "play"}, method="model"
        )]

        bridge = MagicMock()

        pipeline = self._make_pipeline(
            stt_engine=stt, bridge=bridge, translator=translator
        )
        result = asyncio.run(
            pipeline.process_audio(_make_wav(), filename="test.wav", cleanup=False)
        )

        assert result["success"] is True
        assert result["transcription"] == "play"
        assert result["command"]["tool"] == "transport_control"
        stt.transcribe.assert_called_once()

    def test_process_audio_no_stt(self):
        """Returns error when STT engine missing."""
        pipeline = self._make_pipeline(stt_engine=None)
        result = asyncio.run(pipeline.process_audio(_make_wav()))

        assert result["success"] is False
        assert "STT engine not available" in result["error"]

    def test_process_audio_cleanup_with_model(self):
        """Cleanup pass calls model_server.chat()."""
        stt = MagicMock()
        stt.transcribe.return_value = "um play uh the drums"

        model_server = MagicMock()
        model_server.chat = MagicMock(return_value="play the drums")

        pipeline = self._make_pipeline(
            stt_engine=stt, model_server=model_server
        )
        result = asyncio.run(
            pipeline.process_audio(_make_wav(), cleanup=True)
        )

        assert result["success"] is True
        assert result["transcription"] == "um play uh the drums"
        assert result["formatted"] == "play the drums"

    def test_process_audio_cleanup_no_model(self):
        """Cleanup=True with no model returns error — no fallback."""
        stt = MagicMock()
        stt.transcribe.return_value = "play the drums"

        pipeline = self._make_pipeline(stt_engine=stt, model_server=None)
        result = asyncio.run(
            pipeline.process_audio(_make_wav(), cleanup=True)
        )

        assert result["success"] is False
        assert "Model server required" in result["error"]

    def test_process_audio_cleanup_false_no_model(self):
        """Cleanup=False works without model server."""
        from audioshuttle.models import TranslationResult

        stt = MagicMock()
        stt.transcribe.return_value = "play"

        translator = MagicMock()
        translator.translate_multi.return_value = [TranslationResult(
            success=True, tool="transport_control", args={"action": "play"}, method="fallback"
        )]

        pipeline = self._make_pipeline(
            stt_engine=stt, translator=translator, model_server=None
        )
        result = asyncio.run(
            pipeline.process_audio(_make_wav(), cleanup=False)
        )

        assert result["success"] is True
        assert result["formatted"] is None

    def test_process_audio_empty_speech(self):
        """Empty transcription returns error."""
        stt = MagicMock()
        stt.transcribe.return_value = "   "

        pipeline = self._make_pipeline(stt_engine=stt)
        result = asyncio.run(
            pipeline.process_audio(_make_wav(), cleanup=False)
        )

        assert result["success"] is False
        assert "No speech detected" in result["error"]

    def test_process_audio_transcription_fails(self):
        """STT failure returns error."""
        stt = MagicMock()
        stt.transcribe.side_effect = RuntimeError("Model not loaded")

        pipeline = self._make_pipeline(stt_engine=stt)
        result = asyncio.run(pipeline.process_audio(_make_wav()))

        assert result["success"] is False
        assert "Transcription failed" in result["error"]

    def test_temp_file_cleaned_up(self):
        """Pipeline completes without leaking temp files."""
        stt = MagicMock()
        stt.transcribe.return_value = "test"

        pipeline = self._make_pipeline(stt_engine=stt)
        result = asyncio.run(
            pipeline.process_audio(_make_wav(), cleanup=False)
        )

        assert result["success"] is True

    def test_process_text_only(self):
        """Text-only pipeline skips STT."""
        from audioshuttle.models import TranslationResult

        translator = MagicMock()
        translator.translate_multi.return_value = [TranslationResult(
            success=True, tool="transport_control", args={"action": "stop"}, method="fallback"
        )]

        bridge = MagicMock()

        pipeline = self._make_pipeline(bridge=bridge, translator=translator)
        result = pipeline.process_text_only("stop", cleanup=False)

        assert result["success"] is True
        assert result["transcription"] == "stop"
        assert result["command"]["tool"] == "transport_control"

    def test_process_text_only_empty(self):
        """Empty text returns error."""
        pipeline = self._make_pipeline()
        result = pipeline.process_text_only("", cleanup=False)

        assert result["success"] is False
        assert "Empty text" in result["error"]

    def test_process_text_only_translation_fails(self):
        """Translation failure returns error."""
        translator = MagicMock()
        translator.translate_multi.side_effect = RuntimeError("Model error")

        pipeline = self._make_pipeline(translator=translator)
        result = pipeline.process_text_only("play", cleanup=False)

        assert result["success"] is False
        assert "Translation failed" in result["error"]

    def test_process_audio_bridge_fails(self):
        """Bridge execution failure returns error."""
        from audioshuttle.models import TranslationResult

        stt = MagicMock()
        stt.transcribe.return_value = "play"

        translator = MagicMock()
        translator.translate_multi.return_value = [TranslationResult(
            success=True, tool="transport_control", args={"action": "play"}, method="model"
        )]

        bridge = MagicMock()
        bridge.transport_play.side_effect = RuntimeError("OSC error")

        pipeline = self._make_pipeline(
            stt_engine=stt, bridge=bridge, translator=translator
        )
        result = asyncio.run(
            pipeline.process_audio(_make_wav(), cleanup=False)
        )

        assert result["success"] is False
        assert "Execution failed" in result["error"]


class TestVoiceHotkey:
    """Test VoiceHotkey — only test non-platform-dependent parts."""

    def test_pcm_to_wav(self):
        """PCM to WAV conversion produces valid WAV."""
        from audioshuttle.hotkey import VoiceHotkey

        pcm = b"\x00\x00" * 1600  # 1 second of silence at 16kHz
        wav_data = VoiceHotkey._pcm_to_wav(pcm, 16000)

        # Verify it's a valid WAV
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 1600

    def test_initial_state(self):
        """Hotkey starts not running, not recording."""
        from audioshuttle.hotkey import VoiceHotkey

        hk = VoiceHotkey(MagicMock())
        assert hk.is_running is False
        assert hk.is_recording is False

    def test_stop_when_not_running(self):
        """Stop is safe when not running."""
        from audioshuttle.hotkey import VoiceHotkey

        hk = VoiceHotkey(MagicMock())
        hk.stop()  # Should not raise
