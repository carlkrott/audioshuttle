"""AudioShuttle voice pipeline — STT → optional formatting → command translation."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


class VoicePipeline:
    """End-to-end voice command pipeline.

    Flow: audio bytes → STT → (optional E2B formatting) → translator → bridge
    """

    def __init__(
        self,
        stt_engine: Any | None = None,
        model_server: Any | None = None,
        bridge: Any | None = None,
        translator: Any | None = None,
    ) -> None:
        self._stt = stt_engine
        self._model_server = model_server
        self._bridge = bridge
        self._translator = translator

    async def process_audio(
        self,
        audio_bytes: bytes,
        filename: str = "voice.webm",
        cleanup: bool = True,
    ) -> dict:
        """Process audio bytes through the full voice pipeline.

        Args:
            audio_bytes: Raw audio data.
            filename: Original filename (used for extension detection).
            cleanup: If True, run E2B formatting pass on transcription.

        Returns:
            Dict with transcription, formatted text, command, success, error.
        """
        tmp_path: str | None = None
        try:
            # Write audio to temp file
            suffix = os.path.splitext(filename)[1] or ".webm"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            # Step 1: STT
            if self._stt is None:
                return {
                    "transcription": None,
                    "formatted": None,
                    "command": None,
                    "success": False,
                    "error": "STT engine not available",
                }

            try:
                raw_text = self._stt.transcribe(tmp_path)
            except Exception as e:
                return {
                    "transcription": None,
                    "formatted": None,
                    "command": None,
                    "success": False,
                    "error": f"Transcription failed: {e}",
                }

            if not raw_text.strip():
                return {
                    "transcription": "",
                    "formatted": None,
                    "command": None,
                    "success": False,
                    "error": "No speech detected",
                }

            # Step 2: Optional formatting
            formatted = None
            final_text = raw_text

            if cleanup:
                if self._model_server is None:
                    return {
                        "transcription": raw_text,
                        "formatted": None,
                        "command": None,
                        "success": False,
                        "error": (
                            "Model server required for voice formatting. "
                            "The model is integral to this system."
                        ),
                    }
                try:
                    formatted = await self._format_text(raw_text)
                    final_text = formatted
                except Exception as e:
                    logger.warning("Formatting failed, using raw text: %s", e)
                    formatted = None
                    final_text = raw_text

            # Step 3: Translate to DAW command
            command = None
            if self._translator:
                try:
                    from audioshuttle.models import DAWState
                    command = self._translator.translate(final_text, DAWState())
                except Exception as e:
                    return {
                        "transcription": raw_text,
                        "formatted": formatted,
                        "command": None,
                        "success": False,
                        "error": f"Translation failed: {e}",
                    }

            # Step 4: Execute via bridge
            if command and self._bridge:
                try:
                    result = self._bridge.execute_command(command)
                    return {
                        "transcription": raw_text,
                        "formatted": formatted,
                        "command": command,
                        "success": True,
                        "error": None,
                    }
                except Exception as e:
                    return {
                        "transcription": raw_text,
                        "formatted": formatted,
                        "command": command,
                        "success": False,
                        "error": f"Execution failed: {e}",
                    }

            # Translation succeeded but no bridge to execute
            return {
                "transcription": raw_text,
                "formatted": formatted,
                "command": command,
                "success": True,
                "error": None,
            }

        finally:
            # Clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    async def _format_text(self, raw_text: str) -> str:
        """Clean up voice transcription via E2B model.

        Light normalization: remove fillers, fix false starts, normalize language.
        Does NOT convert to OSC or interpret the command.
        """
        prompt = (
            "Clean up this voice transcription for DAW command processing. "
            "Remove filler words (um, uh, like), fix false starts, "
            "normalize to clear instruction language. "
            "Output ONLY the cleaned text, nothing else.\n\n"
            f'Raw: "{raw_text}"'
        )
        result = self._model_server.chat(prompt)
        if result:
            return result.strip()
        return raw_text

    def process_text_only(self, text: str, cleanup: bool = True) -> dict:
        """Process text input through translation (skip STT).

        Useful for testing the pipeline without audio.
        """
        if not text.strip():
            return {
                "transcription": text,
                "formatted": None,
                "command": None,
                "success": False,
                "error": "Empty text",
            }

        # Step 1: Optional formatting (synchronous for text-only)
        formatted = None
        final_text = text

        # Step 2: Translate
        command = None
        if self._translator:
            try:
                from audioshuttle.models import DAWState
                command = self._translator.translate(final_text, DAWState())
            except Exception as e:
                return {
                    "transcription": text,
                    "formatted": formatted,
                    "command": None,
                    "success": False,
                    "error": f"Translation failed: {e}",
                }

        # Step 3: Execute
        if command and self._bridge:
            try:
                self._bridge.execute_command(command)
                return {
                    "transcription": text,
                    "formatted": formatted,
                    "command": command,
                    "success": True,
                    "error": None,
                }
            except Exception as e:
                return {
                    "transcription": text,
                    "formatted": formatted,
                    "command": command,
                    "success": False,
                    "error": f"Execution failed: {e}",
                }

        return {
            "transcription": text,
            "formatted": formatted,
            "command": command,
            "success": True,
            "error": None,
        }
