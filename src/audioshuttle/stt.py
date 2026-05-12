"""AudioShuttle STT engine — optional Whisper-based speech-to-text."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Graceful import — faster_whisper is an optional dependency
try:
    from faster_whisper import WhisperModel

    _WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None  # type: ignore[assignment,misc]
    _WHISPER_AVAILABLE = False


class STTEngine:
    """Speech-to-text engine using faster-whisper (optional dependency).

    Thread-safe singleton. Lazy-loads the Whisper model on first transcribe call.
    Gracefully degrades when faster-whisper is not installed.
    """

    _instance: STTEngine | None = None
    _lock = threading.Lock()

    def __new__(
        cls,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> STTEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        if self._initialized:
            return
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: WhisperModel | None = None
        self._model_lock = threading.Lock()
        self._initialized = True

    @property
    def available(self) -> bool:
        """True if faster_whisper is installed and importable."""
        return _WHISPER_AVAILABLE

    def _load_model(self) -> WhisperModel:
        """Lazy-load the Whisper model. Raises RuntimeError if not installed."""
        if not _WHISPER_AVAILABLE:
            raise RuntimeError(
                "faster-whisper not installed. "
                "Install with: pip install audioshuttle[stt]"
            )
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    logger.info(
                        "Loading Whisper model '%s' on %s (%s)...",
                        self._model_size,
                        self._device,
                        self._compute_type,
                    )
                    self._model = WhisperModel(
                        self._model_size,
                        device=self._device,
                        compute_type=self._compute_type,
                    )
                    logger.info("Whisper model loaded.")
        return self._model

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.).

        Returns:
            Transcribed text.

        Raises:
            RuntimeError: If faster-whisper is not installed.
            FileNotFoundError: If audio file doesn't exist.
        """
        import os

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        model = self._load_model()
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language="en",  # Force English for DAW commands
            no_speech_threshold=0.6,  # Filter out non-speech
            condition_on_previous_text=False,  # Each utterance is independent
            hotwords="DAW command: mute solo arm record play stop track volume tempo",
        )
        text = " ".join(segment.text.strip() for segment in segments)
        logger.debug(
            "Transcribed '%s' (%.1fs): %s",
            audio_path,
            info.duration,
            text[:100],
        )
        return text

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        with cls._lock:
            cls._instance = None
