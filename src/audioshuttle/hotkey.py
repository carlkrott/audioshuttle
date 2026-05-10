"""AudioShuttle global voice hotkey with visual overlay — Alt+Space for push-to-talk."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class VoiceHotkey:
    """System-wide voice recording hotkey with overlay feedback.

    Registers Alt+Space (configurable) as a global shortcut.
    Hold to record, release to process.

    When recording starts, shows a green pulsing overlay border.
    When processing, switches to blue. Shows result briefly, then fades.

    Platform support:
    - X11 / root: keyboard library (primary)
    - KDE Wayland: keyboard library via XWayland
    - Unsupported: web-only voice recording
    """

    def __init__(
        self,
        voice_pipeline: Any,
        callback: Callable[[dict], None] | None = None,
        hotkey: str = "alt+space",
        sample_rate: int = 16000,
        overlay: Any | None = None,
    ) -> None:
        self._pipeline = voice_pipeline
        self._callback = callback
        self._hotkey = hotkey
        self._sample_rate = sample_rate
        self._overlay = overlay
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

        # Try keyboard library (X11/XWayland/root)
        try:
            return self._start_keyboard()
        except Exception as e:
            logger.debug("keyboard library not available: %s", e)
            logger.info("Keyboard hotkey attempt failed: %s", e)

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

    def _start_keyboard(self) -> bool:
        """Register hotkey via keyboard library (X11 or root)."""
        import keyboard

        def on_press():
            self._start_recording()

        def on_release():
            self._stop_recording()

        # Use key event hooks instead of add_hotkey with trigger_on_press
        # (not all keyboard library versions support trigger_on_press)
        self._key_pressed = False
        self._hotkey_keys = keyboard.parse_hotkey(self._hotkey)

        def on_key_event(event):
            if event.event_type == keyboard.KEY_DOWN and not self._key_pressed:
                # Check if the hotkey combo is active
                if keyboard.is_pressed(self._hotkey):
                    self._key_pressed = True
                    on_press()
            elif event.event_type == keyboard.KEY_UP and self._key_pressed:
                # Check if any of the hotkey keys were released
                self._key_pressed = False
                on_release()

        keyboard.hook(on_key_event)

        self._running = True
        logger.info("Global hotkey '%s' registered via keyboard library", self._hotkey)
        return True

    def _start_recording(self) -> None:
        """Start recording audio from default microphone."""
        if self._recording:
            return
        self._recording = True
        self._audio_chunks = []

        # Show overlay (thread-safe via signals)
        if self._overlay:
            try:
                self._overlay.signals.show_listening.emit()
            except Exception:
                pass

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
            if self._overlay:
                try:
                    self._overlay.signals.show_error.emit("No mic access", 3000)
                except Exception:
                    pass
        except Exception as e:
            logger.error("Failed to start recording: %s", e)
            self._recording = False
            if self._overlay:
                try:
                    self._overlay.signals.show_error.emit(str(e), 3000)
                except Exception:
                    pass

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
            if self._overlay:
                try:
                    self._overlay.signals.hide_overlay.emit()
                except Exception:
                    pass
            return

        # Combine chunks into WAV bytes
        audio_data = b"".join(self._audio_chunks)
        wav_bytes = self._pcm_to_wav(audio_data, self._sample_rate)

        logger.debug("Recorded %d bytes of audio", len(wav_bytes))

        # Show processing state
        if self._overlay:
            try:
                self._overlay.signals.show_processing.emit()
            except Exception:
                pass

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

                # Show result on overlay
                if self._overlay and result:
                    try:
                        summary = self._result_summary(result)
                        self._overlay.signals.show_result.emit(summary, 3000)
                    except Exception:
                        pass

                if self._callback:
                    self._callback(result)
            except Exception as e:
                logger.error("Voice pipeline error: %s", e)
                if self._overlay:
                    try:
                        self._overlay.signals.show_error.emit(str(e), 4000)
                    except Exception:
                        pass
            finally:
                loop.close()

        self._recording_thread = threading.Thread(
            target=process, daemon=True
        )
        self._recording_thread.start()

        self._audio_chunks = []

    @staticmethod
    def _result_summary(result: dict) -> str:
        """Create a short summary of the voice command result for the overlay."""
        commands = result.get("commands", [])
        if not commands:
            text = result.get("cleaned", result.get("heard", ""))
            if text:
                return text[:60]
            return "No command detected"

        parts = []
        for cmd in commands[:3]:
            tool = cmd.get("tool", "")
            args = cmd.get("args", {})
            if tool == "set_tempo":
                parts.append(f"BPM → {args.get('bpm', '?')}")
            elif tool == "transport_play":
                parts.append("▶ Play")
            elif tool == "transport_stop":
                parts.append("■ Stop")
            elif tool == "insert_track":
                parts.append("+ Track")
            elif tool == "set_track_mute":
                track = args.get("track", "?")
                mute = "Mute" if args.get("mute") else "Unmute"
                parts.append(f"{mute} T{track}")
            elif tool == "set_track_volume":
                track = args.get("track", "?")
                vol = args.get("volume", "?")
                parts.append(f"T{track} vol → {vol}")
            elif tool == "insert_midi_pattern":
                parts.append(f"MIDI {args.get('role', '?')}")
            else:
                parts.append(tool.replace("_", " ").title())

        summary = " | ".join(parts)
        if len(commands) > 3:
            summary += f" +{len(commands) - 3} more"
        return summary

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


def run_overlay_in_thread() -> "VoiceOverlay":
    """Create and run a VoiceOverlay in its own QApplication thread.

    Returns the overlay widget (thread-safe via Qt signals).
    """
    from audioshuttle.overlay import VoiceOverlay
    from PyQt6.QtWidgets import QApplication

    overlay_ref = [None]
    ready = threading.Event()

    def run_qt():
        import sys
        # Create QApplication if none exists
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        overlay = VoiceOverlay()
        overlay_ref[0] = overlay
        ready.set()
        # Keep event loop running
        app.exec()

    t = threading.Thread(target=run_qt, daemon=True)
    t.start()
    ready.wait(timeout=5.0)
    return overlay_ref[0]
