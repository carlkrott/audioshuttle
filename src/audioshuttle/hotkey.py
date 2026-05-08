"""AudioShuttle global voice hotkey — Alt+Space for push-to-talk."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class VoiceHotkey:
    """System-wide voice recording hotkey.

    Registers Alt+Space (configurable) as a global shortcut.
    Hold to record, release to process.

    Platform support:
    - KDE Wayland: xdg-desktop-portal GlobalShortcuts (best-effort)
    - X11: keyboard library fallback
    - Unsupported: web-only voice recording
    """

    def __init__(
        self,
        voice_pipeline: Any,
        callback: Callable[[dict], None] | None = None,
        hotkey: str = "alt+space",
        sample_rate: int = 16000,
    ) -> None:
        self._pipeline = voice_pipeline
        self._callback = callback
        self._hotkey = hotkey
        self._sample_rate = sample_rate
        self._running = False
        self._recording = False
        self._audio_chunks: list[bytes] = []
        self._thread: threading.Thread | None = None
        self._recording_thread: threading.Thread | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Start the global hotkey listener.

        Returns True if hotkey registration succeeded.
        Returns False if platform unsupported — caller should fall back to web recording.
        """
        if self._running:
            return True

        # Try xdg-desktop-portal GlobalShortcuts (Wayland)
        try:
            return self._start_portal()
        except Exception as e:
            logger.debug("Portal GlobalShortcuts not available: %s", e)

        # Try keyboard library (X11 / root)
        try:
            return self._start_keyboard()
        except Exception as e:
            logger.debug("keyboard library not available: %s", e)

        logger.warning(
            "Global hotkey not available on this platform. "
            "Use browser voice recording instead."
        )
        return False

    def stop(self) -> None:
        """Stop the hotkey listener and clean up."""
        self._running = False
        if self._recording:
            self._stop_recording()

        # Clean up keyboard hooks if used
        try:
            import keyboard

            keyboard.unhook_all_hotkeys()
        except (ImportError, Exception):
            pass

    def _start_portal(self) -> bool:
        """Register hotkey via xdg-desktop-portal GlobalShortcuts D-Bus."""
        import subprocess

        # Check if xdg-desktop-portal is running
        result = subprocess.run(
            ["busctl", "--user", "list", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if "org.freedesktop.portal.Desktop" not in (result.stdout or ""):
            raise RuntimeError("xdg-desktop-portal not running")

        # Portal GlobalShortcuts requires a graphical session and user interaction
        # This is complex D-Bus — for now, mark as available and handle gracefully
        logger.info(
            "xdg-desktop-portal detected. GlobalShortcuts requires "
            "user permission dialog — using keyboard fallback."
        )
        raise RuntimeError("Portal GlobalShortcuts needs interactive setup")

    def _start_keyboard(self) -> bool:
        """Register hotkey via keyboard library (X11 or root)."""
        import keyboard

        def on_press():
            self._start_recording()

        def on_release():
            self._stop_recording()

        keyboard.add_hotkey(
            self._hotkey,
            on_press,
            args=(),
            trigger_on_press=True,
        )
        keyboard.add_hotkey(
            self._hotkey,
            on_release,
            args=(),
            trigger_on_release=True,
        )

        self._running = True
        logger.info("Global hotkey '%s' registered via keyboard library", self._hotkey)
        return True

    def _start_recording(self) -> None:
        """Start recording audio from default microphone."""
        if self._recording:
            return
        self._recording = True
        self._audio_chunks = []

        try:
            import sounddevice as sd

            def callback(indata, frames, time_info, status):
                if self._recording:
                    self._audio_chunks.append(indata.tobytes())

            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                callback=callback,
            )
            self._stream.start()
            logger.debug("Recording started at %d Hz", self._sample_rate)
        except ImportError:
            logger.warning("sounddevice not installed — cannot record from mic")
            self._recording = False
        except Exception as e:
            logger.error("Failed to start recording: %s", e)
            self._recording = False

    def _stop_recording(self) -> None:
        """Stop recording and process the audio."""
        if not self._recording:
            return
        self._recording = False

        try:
            if hasattr(self, "_stream") and self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        except Exception:
            pass

        if not self._audio_chunks:
            logger.debug("No audio recorded")
            return

        # Combine chunks into WAV bytes
        audio_data = b"".join(self._audio_chunks)
        wav_bytes = self._pcm_to_wav(audio_data, self._sample_rate)

        logger.debug("Recorded %d bytes of audio", len(wav_bytes))

        # Process in background thread
        import asyncio

        def process():
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    self._pipeline.process_audio(
                        wav_bytes, filename="hotkey.wav", cleanup=True
                    )
                )
                if self._callback:
                    self._callback(result)
            except Exception as e:
                logger.error("Voice pipeline error: %s", e)
            finally:
                loop.close()

        self._recording_thread = threading.Thread(
            target=process, daemon=True
        )
        self._recording_thread.start()

        self._audio_chunks = []

    @staticmethod
    def _pcm_to_wav(pcm_data: bytes, sample_rate: int) -> bytes:
        """Convert raw PCM int16 data to WAV format."""
        import struct
        import wave
        import io

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        return buf.getvalue()
