"""Gemma 4 E4B native multimodal audio transcription engine.

Sends audio directly to E4B via llama.cpp's input_audio API.
E4B has native audio understanding through its mmproj — no spectrogram needed.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class GemmaAudioEngine:
    """Uses E4B multimodal audio capabilities to transcribe speech."""

    def __init__(self, model_server: Any) -> None:
        self._model_server = model_server

    @property
    def is_available(self) -> bool:
        return self._model_server is not None and getattr(self._model_server, "is_running", False)

    def transcribe(self, audio_path: str, context_hints: list[str] | None = None) -> str:
        """Transcribe audio via E4B's native audio understanding.

        Sends the raw audio file (WAV, WebM, etc.) directly to the model
        using the OpenAI-compatible input_audio content format.

        Args:
            audio_path: Path to audio file.
            context_hints: Optional list of expected words/phrases (e.g. track names)
                           to improve recognition accuracy.

        Returns:
            Transcribed text, or empty string on failure.
        """
        if not self.is_available:
            return ""

        try:
            # 1. Read and base64-encode the audio file
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("ascii")

            # 2. Detect format from extension
            ext = os.path.splitext(audio_path)[1].lower().lstrip(".")
            fmt_map = {"webm": "webm", "wav": "wav", "mp3": "mp3", "ogg": "ogg",
                       "flac": "flac", "m4a": "m4a", "aac": "aac"}
            audio_format = fmt_map.get(ext, "wav")

            # 3. Build transcription prompt with optional context hints
            prompt = (
                "Transcribe the speech in this audio clip. "
                "This is a DAW control command. "
                "Use standard music/audio notation: "
                "dB for decibels (e.g. '6 dB', 'minus 3 dB'), "
                "BPM for tempo, track numbers as digits. "
            )
            if context_hints:
                # Give E4B the track names so it can disambiguate similar-sounding words
                # e.g. "guitars bus" vs "bass", "rhythm guitar 1" vs "lead guitar"
                hints_str = ", ".join(context_hints[:30])  # cap at 30 to avoid prompt bloat
                prompt += (
                    f"The project has these tracks/buses: {hints_str}. "
                    "Match what you hear to these names when possible. "
                )
            prompt += (
                "Output ONLY the exact words spoken, nothing else. "
                "If there is no speech, output nothing."
            )

            # 4. Send to E4B via input_audio content type
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_b64,
                                "format": audio_format,
                            },
                        },
                    ],
                }
            ]

            result = self._model_server.chat_multimodal(messages, temperature=0.1)
            if result:
                text = result.strip()
                logger.info("E4B audio transcription: %s", text[:200])
                return text

        except Exception as e:
            logger.error("GemmaAudioEngine audio transcription failed: %s", e)

        return ""
