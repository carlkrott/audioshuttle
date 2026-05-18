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
            int(args["track"]), float(args.get("value", args.get("volume", 1.0)))
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
            float(args.get("value", args.get("volume", 1.0)))
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
        "fx_next_preset": lambda: bridge.fx_next_preset(
            int(args["track"]), int(args["fx"]),
        ),
        "fx_prev_preset": lambda: bridge.fx_prev_preset(
            int(args["track"]), int(args["fx"]),
        ),
        "fx_set_wetdry": lambda: bridge.fx_set_wetdry(
            int(args["track"]), int(args["fx"]), float(args["value"]),
        ),
        "trigger_action": lambda: bridge.trigger_action(
            int(args["command_id"])
        ),
        "set_track_arm": lambda: bridge.set_track_recarm(
            int(args["track"]), bool(args["arm"]),
        ),
        "toggle_repeat": lambda: bridge.toggle_repeat(),
        "toggle_metronome": lambda: bridge.toggle_metronome(),
        "undo": lambda: bridge.undo(),
        "redo": lambda: bridge.redo(),
        "set_tempo": lambda: bridge.set_tempo(float(args["bpm"])),
        "wipe_project": lambda: bridge.wipe_project(),
        "create_genre_project": lambda: bridge.create_genre_project(
            genre=str(args.get("genre", "rock")),
            tempo=int(args["tempo"]) if "tempo" in args else None,
            key=str(args.get("key", "C")),
            scale=str(args.get("scale", "major")),
        ),
        "insert_track": lambda: bridge.insert_track(),
        "rename_track": lambda: bridge.rename_track(
            int(args["track"]), str(args["name"]),
        ),
        "insert_midi_pattern": lambda: bridge.insert_midi_pattern(
            str(args.get("role", "drums")),
            track=int(args["track"]) if "track" in args else None,
        ),
        "create_song_structure": lambda: bridge.create_song_structure(
            list(args["sections"]),
            bpm=int(args["bpm"]) if "bpm" in args else None,
        ),
        "generate_project": lambda: bridge.generate_project(
            sections=list(args["sections"]),
            instruments=list(args["instruments"]),
            key=str(args.get("key", "C")),
            scale=str(args.get("scale", "major")),
            bpm=int(args.get("bpm", 120)),
        ),
        "assess_arrangement": lambda: bridge.assess_arrangement(
            key=str(args.get("key", "C")),
            scale=str(args.get("scale", "major")),
            bpm=int(args.get("bpm", 120)),
            sections=list(args.get("sections", [])),
            instruments=list(args.get("instruments", [])),
        ),
        "set_track_color": lambda: bridge.set_track_color(
            int(args["track"]), str(args["color"]),
        ),
        "set_track_monitor": lambda: bridge.set_track_monitor(
            int(args["track"]), int(args["mode"]),
        ),
        "set_track_auto_mode": lambda: bridge.set_track_auto_mode(
            int(args["track"]), str(args["mode"]),
        ),
        "set_track_send_volume": lambda: bridge.set_track_send_volume(
            int(args["track"]), int(args["send"]),
            float(args.get("value", args.get("volume", 1.0))),
        ),
        "goto_marker": lambda: bridge.goto_marker(int(args["marker"])),
        "set_marker_name": lambda: bridge.set_marker_name(
            int(args["marker"]), str(args["name"]),
        ),
        "set_loop_points": lambda: bridge.set_loop_points(
            float(args["start"]), float(args["end"]),
        ),
        # Plugin/FX management
        "load_plugin": lambda: bridge.load_plugin(
            int(args["track"]), str(args["plugin_name"]),
        ),
        "remove_plugin": lambda: bridge.remove_plugin(
            int(args["track"]), int(args["fx"]),
        ),
        "set_plugin_preset": lambda: bridge.set_plugin_preset(
            int(args["track"]), int(args["fx"]), str(args["preset_name"]),
        ),
        "get_plugin_params": lambda: bridge.get_plugin_params(
            int(args["track"]), int(args["fx"]),
        ),
        "list_track_fx": lambda: bridge.list_track_fx(
            int(args["track"]),
        ),
        "list_available_plugins": lambda: bridge.list_available_plugins(),
        # Routing
        "create_send": lambda: bridge.create_send(
            int(args["source_track"]), int(args["dest_track"]),
        ),
        "delete_send": lambda: bridge.delete_send(
            int(args["track"]), int(args["send"]),
        ),
        # Track extras
        "set_track_input": lambda: bridge.set_track_input(
            int(args["track"]), int(args["input_code"]),
        ),
        "select_track": lambda: bridge.select_track(int(args["track"])),
        "move_track": lambda: bridge.move_track(
            int(args["track"]), int(args["new_position"]),
        ),
        # Playback extras
        "set_playrate": lambda: bridge.set_playrate(float(args["rate"])),
        "solo_reset": lambda: bridge.solo_reset(),
        "open_fx_ui": lambda: bridge.open_fx_ui(
            int(args["track"]), int(args["fx"]),
        ),
        # Vision & Audio Analysis (multimodal)
        "look_and_analyze": lambda: bridge.look_and_analyze(
            str(args.get("question", "Describe what you see"))
        ),
        "listen_and_analyze": lambda: bridge.listen_and_analyze(
            track=int(args["track"]) if args.get("track") is not None else None,
            start_sec=float(args.get("start_sec", 0)),
            duration_sec=float(args.get("duration_sec", 30)),
            question=str(args.get("question", "Describe the audio quality and mix")),
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
        from audioshuttle.audio_engine_e4b import GemmaAudioEngine
        self._stt = stt_engine
        self._model_server = model_server
        self._bridge = bridge
        self._translator = translator
        self._gemma_audio = GemmaAudioEngine(model_server)

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
            raw_text = ""
            try:
                # Build context hints from current DAW state (track names)
                context_hints = None
                if self._bridge and hasattr(self._bridge, 'state'):
                    state = self._bridge.state
                    if hasattr(state, 'tracks') and state.tracks:
                        context_hints = [
                            t.name for t in state.tracks if t.name
                        ]

                if hasattr(self, "_gemma_audio") and self._gemma_audio.is_available:
                    raw_text = self._gemma_audio.transcribe(tmp_path, context_hints=context_hints)
                    if raw_text:
                        logger.info("E4B transcription: %r", raw_text)
                
                if not raw_text and self._stt is not None:
                    raw_text = self._stt.transcribe(tmp_path)
                    logger.info("Whisper transcription: %r", raw_text)
            except Exception as e:
                logger.error("STT failed: %s", e)
                if not raw_text:
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
                    if formatted != raw_text:
                        logger.info("Formatted: %r → %r", raw_text, formatted)
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
                    # Get live DAW state for context (track names, count, etc.)
                    daw_state = DAWState()
                    if self._bridge and hasattr(self._bridge, 'refresh_state'):
                        try:
                            daw_state = self._bridge.refresh_state(wait=0.3)
                        except Exception as e:
                            logger.warning("State refresh failed, using empty state: %s", e)
                    results = self._translator.translate_multi(final_text, daw_state)
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

                    # Smart command sequencing:
                    # - Group related commands for proper timing
                    # - Insert appropriate delays between dependent commands
                    # - Verify MIDI imports have tracks to land on
                    sequenced = self._sequence_commands(commands)

                    # Handle discovery commands: replace with state summary
                    discovery_tools = {"list_tracks", "get_daw_state", "get_transport", "get_track_count"}
                    discovery_cmds = [c for c in sequenced if c["tool"] in discovery_tools]
                    action_cmds = [c for c in sequenced if c["tool"] not in discovery_tools]

                    # Build spoken state summary for discovery commands
                    state_summary = None
                    if discovery_cmds:
                        state = self._bridge.state if hasattr(self._bridge, 'state') else DAWState()
                        parts = []
                        if state.tracks:
                            for t in state.tracks:
                                name = t.name or f"Track {t.track_number}"
                                flags = []
                                if t.mute: flags.append("muted")
                                if t.solo: flags.append("solo")
                                flag_str = f" ({', '.join(flags)})" if flags else ""
                                parts.append(f"{name}{flag_str}")
                        if not parts:
                            parts.append(f"{state.track_count} tracks (names unknown)")
                        state_summary = " | ".join(parts)
                        logger.info("State summary for overlay: %s", state_summary)

                    # Execute action commands (skip discovery ones)
                    for i, cmd in enumerate(action_cmds):
                        # Delay between commands based on sequencing rules
                        if i > 0:
                            delay = cmd.get("_delay_ms", 0)
                            if delay > 0:
                                await asyncio.sleep(delay / 1000.0)
                        logger.info(
                            "Executing command %d/%d: %s(%s)",
                            i + 1, len(action_cmds), cmd["tool"], cmd.get("args", {}),
                        )
                        result = _execute_tool(self._bridge, cmd["tool"], cmd.get("args", {}))
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
                        "state_summary": state_summary,  # Spoken state for overlay
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

        Contextual correction: fix DAW-specific mishearings, remove fillers,
        resolve ambiguity. The model knows the DAW domain vocabulary.
        Does NOT convert to OSC or interpret the command.
        """
        import re

        # Build context about current DAW state for disambiguation
        state_context = ""
        if self._bridge and hasattr(self._bridge, 'state'):
            state = self._bridge.state
            if state.tracks:
                track_names = [f"T{t.track_number}={t.name or 'unnamed'}" for t in state.tracks[:8]]
                state_context = f"\nCurrent tracks: {', '.join(track_names)}"

        prompt = (
            "Fix DAW voice transcription errors. Output ONLY the corrected sentence.\n"
            "Fixes: moved→mute, right mode→write mode, this arm→disarm, "
            "charge→arm, going to charge→arm, base→bass, so low→solo, "
            "on mute→unmute, mood→mute, ride mode→latch mode, much mode→touch mode, "
            "temple→tempo, mark her→marker, pre set→preset, monument→monitor, "
            "ought a mission→automation, reeve erb→reverb, on do→undo, "
            "rain ame→rename, loupe→loop, truck→track, "
            "won't→1 (when after 'track'), oh I'm→arm, going to→(remove), "
            "ability to track→a melody track, add a melody→add a melody, "
            "medley→melody, melo→melody, riddum→rhythm, middy→midi, "
            "mid if→midi, base→bass, bas→bass, cords→chords.\n"
            "IMPORTANT: Use track/bus names from the context list below. "
            "If the raw text mentions a track that sounds similar to one in the context, "
            "use the exact name from context. "
            "e.g. 'bass' near 'guitars bus' → 'guitars bus', "
            "'lead guitar' when context has 'rhythm guitar 1' → 'rhythm guitar 1', "
            "'base' → check context for 'bass' track name first.\n"
            f"{state_context}\n\n"
            f"Raw: '{raw_text}'"
        )
        result = self._model_server.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=1024,        )
        if not result:
            return raw_text

        cleaned = result.strip()

        # E2B thinking mode: the actual answer is often at the very end
        # of reasoning_content, after all the "Thinking Process:" steps.
        # Try to extract the final line that looks like the corrected sentence.
        if 'Thinking Process' in cleaned or cleaned.startswith('1.') or cleaned.startswith('Step'):
            # The model put reasoning in content — extract the last meaningful line
            lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
            # Look for lines that look like actual transcribed sentences
            # (not reasoning steps, not bullet points, not explanations)
            candidates = []
            for line in lines:
                # Skip reasoning artifacts
                if any(line.lower().startswith(p) for p in (
                    'thinking', 'step', 'analyze', 'however', 'overall',
                    'given', 'based on', 'finally', 'therefore', 'i would',
                    'note:', 'the ', 'this is', 'original:', 'correction:',
                    'result:', 'output:', 'draft', 'review',
                )):
                    continue
                # Skip lines starting with * (bullet points)
                if line.startswith('*'):
                    continue
                # Skip lines that look like numbered steps
                if re.match(r'^\d+[\.\)]\s', line):
                    continue
                # Skip markdown
                if line.startswith('#') or line.startswith('```') or line.startswith('**'):
                    continue
                # Skip very short fragments
                if len(line) < 5:
                    continue
                # Skip lines that are just arrow mappings
                if '→' in line or '->' in line:
                    continue
                candidates.append(line)

            if candidates:
                cleaned = candidates[-1]
            else:
                return raw_text

        # Detect markdown formatting
        if '**' in cleaned or cleaned.startswith('#') or cleaned.startswith('```'):
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
                # Get live DAW state for context
                daw_state = DAWState()
                if self._bridge and hasattr(self._bridge, 'refresh_state'):
                    try:
                        daw_state = self._bridge.refresh_state(wait=0.3)
                    except Exception as e:
                        logger.warning("State refresh failed, using empty state: %s", e)
                results = self._translator.translate_multi(final_text, daw_state)
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

    @staticmethod
    def _sequence_commands(commands: list[dict]) -> list[dict]:
        """Smart command sequencing with proper delays and dependency resolution.

        Rules:
        1. Group track operations: insert_track + rename_track → same track
        2. MIDI insert needs a track: auto-prepend insert_track if needed
        3. insert_midi_pattern always gets 800ms delay (watcher + track settle)
        4. Transport changes get 200ms gap
        5. Respect model-provided delay_ms
        """
        if not commands:
            return commands

        sequenced = []
        for i, cmd in enumerate(commands):
            entry = dict(cmd)  # shallow copy
            entry.setdefault("args", {})

            # Calculate delay for this command
            delay = cmd.get("delay_ms", 0)

            # Auto-delay rules (only when no explicit delay_ms set)
            if delay == 0 and i > 0:
                tool = cmd["tool"]

                if tool == "insert_midi_pattern":
                    # MIDI import needs: Reaper track to settle + watcher to poll
                    delay = 800
                elif tool == "rename_track":
                    # Rename needs the track to exist first
                    delay = 300
                elif tool in ("transport_play", "transport_stop", "transport_record"):
                    # Transport changes: small gap for Reaper to process
                    delay = 150
                elif tool.startswith("set_track_") and "track" in entry.get("args", {}):
                    # Track modifications: give Reaper a moment
                    delay = 100

            entry["_delay_ms"] = delay
            sequenced.append(entry)

        # Dependency check: insert_midi_pattern needs a track
        # If no insert_track precedes it AND no target track specified, auto-prepend one
        has_insert_before_midi = False
        for i, cmd in enumerate(sequenced):
            if cmd["tool"] == "insert_track":
                has_insert_before_midi = True
            elif cmd["tool"] == "insert_midi_pattern" and not has_insert_before_midi:
                # Check if a target track was specified (existing track)
                if "track" in cmd.get("args", {}):
                    # Target track exists — no need to insert a new one
                    # Just ensure the MIDI delay is sufficient for track selection
                    cmd["_delay_ms"] = max(cmd.get("_delay_ms", 0), 800)
                else:
                    # No target track — add one before the MIDI pattern
                    track_insert = {"tool": "insert_track", "args": {}, "_delay_ms": 0}
                    sequenced.insert(i, track_insert)
                    # Ensure the MIDI pattern still has its delay
                    sequenced[i + 1]["_delay_ms"] = max(sequenced[i + 1].get("_delay_ms", 0), 800)
                break  # Only fix the first MIDI without track

        return sequenced
