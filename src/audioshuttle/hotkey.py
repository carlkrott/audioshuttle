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
        self._recording_mode = None  # 'sounddevice' or 'arecord'
        self._arecord_proc = None

        # Show overlay (thread-safe via signals)
        if self._overlay:
            try:
                self._overlay.signals.show_listening.emit()
            except Exception:
                pass

        # Try sounddevice first (works when PulseAudio/PipeWire exposes mic)
        try:
            import sounddevice as sd

            # Check if any PortAudio input device exists
            has_input = False
            for dev in sd.query_devices():
                if dev.get("max_input_channels", 0) > 0:
                    has_input = True
                    break

            if has_input:
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
                self._recording_mode = "sounddevice"
                logger.debug("Recording via sounddevice at %d Hz", self._sample_rate)
                return
        except ImportError:
            logger.debug("sounddevice not installed")
        except Exception as e:
            logger.debug("sounddevice capture failed: %s", e)

        # Fallback: use arecord subprocess for raw ALSA capture
        try:
            alsa_dev = self._find_alsa_capture_device()
            if alsa_dev:
                import subprocess
                self._arecord_proc = subprocess.Popen(
                    [
                        "arecord",
                        "-D", alsa_dev,
                        "-f", "S16_LE",     # 16-bit
                        "-c", "1",           # mono
                        "-r", str(self._sample_rate),
                        "--buffer-size=16000",
                        "-",                 # stdout
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                self._recording_mode = "arecord"

                # Read arecord output in a background thread
                def read_arecord():
                    try:
                        while self._recording and self._arecord_proc:
                            chunk = self._arecord_proc.stdout.read(3200)  # 100ms at 16kHz mono 16-bit
                            if not chunk:
                                break
                            self._audio_chunks.append(chunk)
                    except Exception:
                        pass

                t = threading.Thread(target=read_arecord, daemon=True)
                t.start()
                logger.info("Recording via arecord on %s at %d Hz", alsa_dev, self._sample_rate)
                return
        except Exception as e:
            logger.error("arecord capture also failed: %s", e)

        # Nothing worked
        self._recording = False
        logger.error("No microphone available (sounddevice and arecord both failed)")
        if self._overlay:
            try:
                self._overlay.signals.show_error.emit("No mic found", 3000)
            except Exception:
                pass

    @staticmethod
    def _find_alsa_capture_device() -> str | None:
        """Find an ALSA hw capture device via arecord -l.

        Returns device string like 'hw:2,0' or None.
        """
        import subprocess
        import re
        try:
            result = subprocess.run(
                ["arecord", "-l"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "card" in line and "device" in line:
                    m = re.match(r"card (\d+): .+ device (\d+):", line)
                    if m:
                        return f"hw:{m.group(1)},{m.group(2)}"
        except Exception as e:
            logger.debug("arecord scan failed: %s", e)
        return None

    def _stop_recording(self) -> None:
        """Stop recording and process the audio."""
        if not self._recording:
            return
        self._recording = False

        # Stop the appropriate recording backend
        if self._recording_mode == "sounddevice":
            try:
                if hasattr(self, "_stream") and self._stream:
                    self._stream.stop()
                    self._stream.close()
                    self._stream = None
            except Exception:
                pass
        elif self._recording_mode == "arecord":
            try:
                if self._arecord_proc:
                    self._arecord_proc.terminate()
                    self._arecord_proc.wait(timeout=2)
                    # Read any remaining data
                    remaining = self._arecord_proc.stdout.read()
                    if remaining:
                        self._audio_chunks.append(remaining)
                    self._arecord_proc = None
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
        # If there's a state summary (from list_tracks/get_daw_state), show it
        state_summary = result.get("state_summary")
        if state_summary:
            return f"📋 {state_summary}"

        commands = result.get("commands", [])

        # Show transcription + what was done
        heard = result.get("heard", "")
        formatted = result.get("cleaned", "")

        if not commands:
            text = formatted or heard
            if text:
                return f'"{text[:40]}" — no action'
            return "No command detected"

        parts = []
        for cmd in commands[:4]:
            tool = cmd.get("tool", "")
            args = cmd.get("args", {})
            if tool in ("list_tracks", "get_daw_state", "get_transport", "get_track_count"):
                continue  # Handled via state_summary above
            elif tool == "set_tempo":
                parts.append(f"BPM → {args.get('bpm', '?')}")
            elif tool == "transport_play":
                parts.append("▶ Play")
            elif tool == "transport_stop":
                parts.append("■ Stop")
            elif tool == "insert_track":
                parts.append("+ Track")
            elif tool == "rename_track":
                parts.append(f"T{args.get('track', '?')} → {args.get('name', '?')}")
            elif tool == "set_track_color":
                parts.append(f"T{args.get('track', '?')} {args.get('color', '?')}")
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
            elif tool == "goto_marker":
                parts.append(f"→ Marker {args.get('marker', '?')}")
            elif tool == "set_marker_name":
                parts.append(f"Marker {args.get('marker', '?')} → {args.get('name', '?')}")
            elif tool == "fx_next_preset":
                parts.append(f"T{args.get('track', '?')} FX preset →")
            elif tool == "fx_set_wetdry":
                parts.append(f"T{args.get('track', '?')} wet={args.get('value', '?')}")
            elif tool == "undo":
                parts.append("↩ Undo")
            elif tool == "redo":
                parts.append("↪ Redo")
            elif tool == "set_loop_points":
                parts.append(f"Loop {args.get('start', '?')}-{args.get('end', '?')}s")
            elif tool == "set_track_auto_mode":
                parts.append(f"T{args.get('track', '?')} auto={args.get('mode', '?')}")
            elif tool == "set_track_send_volume":
                parts.append(f"T{args.get('track', '?')}→S{args.get('send', '?')}")
            elif tool == "set_track_monitor":
                mode_names = {0: "off", 1: "on", 2: "tape"}
                m = mode_names.get(args.get("mode", "?"), "?")
                parts.append(f"T{args.get('track', '?')} monitor={m}")
            else:
                parts.append(tool.replace("_", " ").title())

        summary = " | ".join(parts)
        if len(commands) > 4:
            summary += f" +{len(commands) - 4} more"
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
