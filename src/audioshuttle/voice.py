"""AudioShuttle voice pipeline — STT → optional formatting → command translation."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger(__name__)


def _execute_tool(bridge: Any, tool: str, args: dict) -> Any:
    """Execute a translated tool call on the OSC bridge.

    Maps tool names from TranslationResult to bridge method calls.
    Returns the CommandResult from the bridge, or None for discovery tools.
    """
    action = args.get("action", "")
    tool_map = {
        "transport_control": lambda: (
            bridge.transport_play() if action == "play"
            else bridge.transport_stop() if action == "stop"
            else bridge.transport_record() if action == "record"
            else bridge.transport_pause() if action == "pause"
            else None
        ),
        "transport_seek": lambda: bridge.transport_seek(
            float(args.get("position_seconds", 0))
        ),
        "set_track_volume": lambda: bridge.set_track_volume(
            int(args["track"]), float(args["volume"])
        ),
        "set_track_mute": lambda: bridge.set_track_mute(
            int(args["track"]), bool(args["mute"])
        ),
        "set_track_solo": lambda: bridge.set_track_solo(
            int(args["track"]), bool(args["solo"])
        ),
        "set_track_pan": lambda: bridge.set_track_pan(
            int(args["track"]), float(args["pan"])
        ),
        "set_master_volume": lambda: bridge.set_master_volume(
            float(args["volume"])
        ),
        "set_master_pan": lambda: bridge.set_master_pan(
            float(args["pan"])
        ),
        "set_fx_param": lambda: bridge.set_fx_param(
            int(args["track"]), int(args["fx"]),
            int(args["param"]), float(args["value"]),
        ),
        "fx_bypass": lambda: bridge.fx_bypass(
            int(args["track"]), int(args["fx"]), bool(args["bypass"]),
        ),
        "trigger_action": lambda: bridge.trigger_action(
            int(args["command_id"])
        ),
        "set_track_arm": lambda: bridge.set_track_recarm(
            int(args["track"]), bool(args["arm"]),
        ),
        "toggle_repeat": lambda: bridge.toggle_repeat(),
        "toggle_metronome": lambda: bridge.toggle_metronome(),
        "set_tempo": lambda: bridge.set_tempo(float(args["bpm"])),
        "insert_track": lambda: bridge.insert_track(),
        "rename_track": lambda: bridge.rename_track(
            int(args["track"]), str(args["name"]),
        ),
        "insert_midi_pattern": lambda: bridge.insert_midi_pattern(
            str(args.get("role", "drums")),
        ),
    }

    # Discovery tools — no bridge call needed
    if tool in ("list_tracks", "get_transport", "get_daw_state", "get_track_count"):
        return None

    fn = tool_map.get(tool)
    if fn:
        return fn()
    return None


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

            # Step 3: Translate to DAW command(s)
            commands: list[dict] = []
            if self._translator:
                try:
                    from audioshuttle.models import DAWState
                    results = self._translator.translate_multi(final_text, DAWState())
                    for r in results:
                        if r.success:
                            commands.append({
                                "tool": r.tool,
                                "args": r.args,
                                "method": r.method,
                                "delay_ms": r.delay_ms,
                            })
                        else:
                            return {
                                "transcription": raw_text,
                                "formatted": formatted,
                                "commands": commands or None,
                                "command": commands[0] if commands else None,
                                "success": False,
                                "error": f"Could not understand: {r.error}",
                            }
                except Exception as e:
                    return {
                        "transcription": raw_text,
                        "formatted": formatted,
                        "commands": None,
                        "command": None,
                        "success": False,
                        "error": f"Translation failed: {e}",
                    }

            # Step 4: Execute command chain via bridge
            if commands and self._bridge:
                try:
                    # Check if Reaper is connected (is_connected is a property, not a method)
                    reaper_online = (
                        hasattr(self._bridge, 'is_connected')
                        and self._bridge.is_connected
                    )
                    if not reaper_online:
                        # Try a probe to detect Reaper
                        if hasattr(self._bridge, 'probe'):
                            reaper_online = self._bridge.probe(timeout=0.5)

                    for i, cmd in enumerate(commands):
                        # Apply delay before this command (except the first)
                        if i > 0 and cmd.get("delay_ms", 0) > 0:
                            await asyncio.sleep(cmd["delay_ms"] / 1000.0)
                        logger.info(
                            "Executing command %d/%d: %s(%s)",
                            i + 1, len(commands), cmd["tool"], cmd["args"],
                        )
                        result = _execute_tool(self._bridge, cmd["tool"], cmd["args"])
                        logger.info(
                            "Command %d result: success=%s",
                            i + 1,
                            result.success if result and hasattr(result, 'success') else result,
                        )

                    if not reaper_online:
                        logger.warning("Commands sent but Reaper appears offline")

                    return {
                        "transcription": raw_text,
                        "formatted": formatted,
                        "commands": commands,
                        "command": commands[0],  # First command for backwards compat
                        "success": True,
                        "error": None,
                        "warning": "Reaper may be offline — commands sent but not confirmed" if not reaper_online else None,
                    }
                except Exception as e:
                    return {
                        "transcription": raw_text,
                        "formatted": formatted,
                        "commands": commands,
                        "command": commands[0] if commands else None,
                        "success": False,
                        "error": f"Execution failed: {e}",
                    }

            # Translation succeeded but no bridge to execute
            return {
                "transcription": raw_text,
                "formatted": formatted,
                "commands": commands or None,
                "command": commands[0] if commands else None,
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
        import re

        prompt = (
            "Clean up this voice transcription. Remove filler words (um, uh, like), "
            "fix false starts. Output ONLY the cleaned sentence, nothing else.\n\n"
            f'Raw: "{raw_text}"'
        )
        result = self._model_server.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=128,
        )
        if not result:
            return raw_text

        cleaned = result.strip()

        # Detect E2B thinking leak — any numbered step, markdown, or structured output
        # means the model put reasoning in content instead of the actual answer
        if re.match(r'^\d+[\.\)]\s', cleaned):
            # Numbered step leaked through — fall back to raw
            return raw_text

        # Detect markdown formatting (thinking output uses bold, headers, etc.)
        if '**' in cleaned or cleaned.startswith('#') or cleaned.startswith('```'):
            return raw_text

        # Detect thinking keywords
        if any(kw in cleaned.lower() for kw in ('thinking process', 'step ', 'analysis', 'reasoning')):
            return raw_text

        # If suspiciously long for a cleaned sentence, fall back
        if len(cleaned) > len(raw_text) * 1.5 or len(cleaned) > 150:
            return raw_text

        return cleaned

    def process_text_only(self, text: str, cleanup: bool = True) -> dict:
        """Process text input through translation (skip STT).

        Useful for testing the pipeline without audio.
        """
        if not text.strip():
            return {
                "transcription": text,
                "formatted": None,
                "commands": None,
                "command": None,
                "success": False,
                "error": "Empty text",
            }

        # Step 1: Optional formatting (synchronous for text-only)
        formatted = None
        final_text = text

        # Step 2: Translate
        commands: list[dict] = []
        if self._translator:
            try:
                from audioshuttle.models import DAWState
                results = self._translator.translate_multi(final_text, DAWState())
                for r in results:
                    if r.success:
                        commands.append({
                            "tool": r.tool,
                            "args": r.args,
                            "method": r.method,
                            "delay_ms": r.delay_ms,
                        })
                    else:
                        return {
                            "transcription": text,
                            "formatted": formatted,
                            "commands": commands or None,
                            "command": commands[0] if commands else None,
                            "success": False,
                            "error": f"Could not understand: {r.error}",
                        }
            except Exception as e:
                return {
                    "transcription": text,
                    "formatted": formatted,
                    "commands": None,
                    "command": None,
                    "success": False,
                    "error": f"Translation failed: {e}",
                }

        # Step 3: Execute (synchronous — no delays in text-only mode)
        if commands and self._bridge:
            try:
                for cmd in commands:
                    _execute_tool(self._bridge, cmd["tool"], cmd["args"])
                return {
                    "transcription": text,
                    "formatted": formatted,
                    "commands": commands,
                    "command": commands[0],
                    "success": True,
                    "error": None,
                }
            except Exception as e:
                return {
                    "transcription": text,
                    "formatted": formatted,
                    "commands": commands,
                    "command": commands[0] if commands else None,
                    "success": False,
                    "error": f"Execution failed: {e}",
                }

        return {
            "transcription": text,
            "formatted": formatted,
            "commands": commands or None,
            "command": commands[0] if commands else None,
            "success": True,
            "error": None,
        }
