"""Natural language to DAW command translator."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from audioshuttle.models import DAWState, TranslationResult

if TYPE_CHECKING:
    from audioshuttle.model_server import ModelServer

logger = logging.getLogger(__name__)

# Known tool names and their parameter schemas
TOOL_SCHEMAS: dict[str, dict[str, type]] = {
    "list_tracks": {},
    "get_transport": {},
    "get_daw_state": {},
    "get_track_count": {},
    "transport_control": {"action": str},
    "transport_seek": {"position_seconds": float},
    "set_track_volume": {"track": int, "volume": float},
    "set_track_mute": {"track": int, "mute": bool},
    "set_track_solo": {"track": int, "solo": bool},
    "set_track_pan": {"track": int, "pan": float},
    "set_master_volume": {"volume": float},
    "set_master_pan": {"pan": float},
    "set_fx_param": {"track": int, "fx": int, "param": int, "value": float},
    "fx_bypass": {"track": int, "fx": int, "bypass": bool},
    "trigger_action": {"command_id": int},
    "set_track_arm": {"track": int, "arm": bool},
    "toggle_repeat": {},
    "toggle_metronome": {},
    "set_tempo": {"bpm": float},
    "insert_track": {},
    "rename_track": {"track": int, "name": str},
    "insert_midi_pattern": {"role": str},
    "set_track_color": {"track": int, "color": str},
}

SYSTEM_PROMPT = """You translate natural language DAW commands into structured JSON tool calls.

You can output a SINGLE command or MULTIPLE commands in sequence.
For multiple commands, output a JSON array. For a single command, output a JSON object.

Single command format:
{"tool": "<tool_name>", "args": {<key>: <value>}}

Multiple commands format (use when the user's request involves sequential actions):
[
  {"tool": "<tool_name>", "args": {<key>: <value>}, "delay_ms": 0},
  {"tool": "<tool_name>", "args": {<key>: <value>}, "delay_ms": 1000}
]

The "delay_ms" field is optional — use it when commands need timing gaps
(e.g., "play for a few seconds then stop" → play with 3000ms delay before stop).

Available tools:
- transport_control — args: {"action": "play" or "stop" or "record" or "pause"}
- transport_seek — args: {"position_seconds": float}
- set_track_volume — args: {"track": int, "volume": float 0.0-1.0}
- set_track_mute — args: {"track": int, "mute": bool}
- set_track_solo — args: {"track": int, "solo": bool}
- set_track_pan — args: {"track": int, "pan": float -1.0 to 1.0}
- set_master_volume — args: {"volume": float}
- set_master_pan — args: {"pan": float}
- set_fx_param — args: {"track": int, "fx": int, "param": int, "value": float}
- fx_bypass — args: {"track": int, "fx": int, "bypass": bool}
- trigger_action — args: {"command_id": int}
- set_track_arm — args: {"track": int, "arm": bool}
- toggle_repeat — args: {}
- toggle_metronome — args: {}
- list_tracks — args: {}
- get_transport — args: {}
- get_daw_state — args: {}
- get_track_count — args: {}
- set_tempo — args: {"bpm": float}
- insert_track — args: {}
- rename_track — args: {"track": int, "name": str}
- set_track_color — args: {"track": int, "color": str} — hex color like "#ff0000" or named color like "red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"
- insert_midi_pattern — args: {"role": str} — generates a 4-bar MIDI pattern and imports into Reaper.
  Roles: "drums" (kick/snare/hihat), "bass" (root notes), "chords" (C major pads)
  CRITICAL: Always pair with insert_track. The pattern needs a track to land on.
  Correct: [{"tool":"insert_track","args":{}},{"tool":"insert_midi_pattern","args":{"role":"drums"}}]
  The system auto-inserts a track if you forget, but explicit is better.

TRACK NUMBERING FOR NEW TRACKS (CRITICAL):
When inserting new tracks, they are added at the BOTTOM of the track list.
If the DAW state shows N tracks, the FIRST insert_track creates track N+1,
the SECOND creates track N+2, etc.
Use the DAW state's track count to calculate the correct track numbers.
Example: If DAW has 4 tracks and user says "add 2 tracks named guitar and bass":
  [{"tool":"insert_track","args":{}},{"tool":"insert_track","args":{}},{"tool":"rename_track","args":{"track":5,"name":"guitar"}},{"tool":"rename_track","args":{"track":6,"name":"bass"}}]

Multi-command examples:
  "add a drum track" → [{"tool":"insert_track","args":{}},{"tool":"insert_midi_pattern","args":{"role":"drums"}}]
  "add 3 tracks and set tempo to 140" → [{"tool":"insert_track","args":{}},{"tool":"insert_track","args":{}},{"tool":"insert_track","args":{}},{"tool":"set_tempo","args":{"bpm":140}}]
  "add a bass track and name it bass" (DAW has 3 tracks) → [{"tool":"insert_track","args":{}},{"tool":"rename_track","args":{"track":4,"name":"bass"}}]
  "add drums and mute track 3" → [{"tool":"insert_track","args":{}},{"tool":"insert_midi_pattern","args":{"role":"drums"}},{"tool":"set_track_mute","args":{"track":3,"mute":true}}]
  "add this sequence" or "import this midi" → [{"tool":"insert_track","args":{}},{"tool":"insert_midi_pattern","args":{"role":"drums"}}]

Rules:
- Match track NAMES to find track NUMBER from the DAW state
- For NEW tracks: count existing tracks from DAW state, new tracks get N+1, N+2, etc.
- "mute X" means mute=true, "unmute X" means mute=false
- Volume: "turn up/increase" ≈ 0.85, "turn down/decrease" ≈ 0.5, "normal" ≈ 0.75
- "down by N dB" ≈ subtract N*0.01 from current volume (rough approximation)
- "up by N dB" ≈ add N*0.01 to current volume
- Track numbers start at 1
- FX and parameter indices are 0-based
- Use multiple commands when the user says sequential things like "play then stop" or "mute drums then unmute bass"
- Estimate delay_ms from natural language: "a few seconds" ≈ 3000, "then" ≈ 500, "after a moment" ≈ 1000
"""

# Immutable original — used by reset endpoint
_DEFAULT_PROMPT = SYSTEM_PROMPT


def update_system_prompt(new_prompt: str) -> None:
    """Update the module-level SYSTEM_PROMPT used by IntentTranslator."""
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = new_prompt


class IntentTranslator:
    """Translates natural language commands to structured DAW tool calls."""

    def __init__(self, model_server: ModelServer | None = None) -> None:
        self._model_server = model_server

    def translate(self, user_input: str, daw_state: DAWState) -> TranslationResult:
        """Translate a natural language command to a single tool call.

        For multi-command support, use translate_multi() instead.
        """
        results = self.translate_multi(user_input, daw_state)
        if results:
            return results[0]
        return TranslationResult(
            success=False, error="No commands produced", method="fallback"
        )

    def translate_multi(
        self, user_input: str, daw_state: DAWState
    ) -> list[TranslationResult]:
        """Translate a natural language command to one or more tool calls.

        The model may return a single JSON object or an array of commands
        with optional delay_ms for sequencing.
        """
        # Try model-based translation
        model_available = False
        if self._model_server:
            if self._model_server.is_running:
                model_available = True
            elif hasattr(self._model_server, 'health_check') and self._model_server.health_check():
                model_available = True

        if model_available:
            results = self._translate_with_model_multi(user_input, daw_state)
            if results and all(r.success for r in results):
                return results
            if results:
                logger.info(
                    "Model translation had failures, trying fallback"
                )

        # Fallback to rule-based (single command only)
        fallback = self._translate_with_rules(user_input, daw_state)
        return [fallback] if fallback.success else [fallback]

    def _translate_with_model(
        self, user_input: str, daw_state: DAWState
    ) -> TranslationResult:
        """Use E2B model to translate command (single result)."""
        results = self._translate_with_model_multi(user_input, daw_state)
        if results:
            return results[0]
        return TranslationResult(
            success=False, error="Model returned no response", method="model"
        )

    def _translate_with_model_multi(
        self, user_input: str, daw_state: DAWState
    ) -> list[TranslationResult]:
        """Use E2B model to translate command (potentially multi-command)."""
        state_desc = self._format_daw_state(daw_state)

        # Debug: log what state the model receives
        logger.info(
            "Translating with DAW state: %d tracks, count=%d | state=%s",
            len(daw_state.tracks), daw_state.track_count,
            state_desc.replace('\n', ' | ')[:200],
        )

        # Single user message with everything — Gemma E2B works best this way
        messages = [
            {
                "role": "user",
                "content": (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"Current DAW state:\n{state_desc}\n\n"
                    f"User command: {user_input}\n\n"
                    f"Respond with only the JSON (object or array)."
                ),
            },
        ]

        raw = self._model_server.chat(
            messages, temperature=0.1, max_tokens=1024
        )
        if raw is None:
            return [TranslationResult(
                success=False,
                error="Model returned no response",
                method="model",
            )]

        logger.info("Model raw response: %s", raw[:500])
        return self._parse_response_multi(raw, method="model")

    def _translate_with_rules(
        self, user_input: str, daw_state: DAWState
    ) -> TranslationResult:
        """Rule-based fallback when model is unavailable."""
        text = user_input.lower().strip()

        # Transport commands (check "stop" before "play" to avoid "stop playback" matching "play")
        if any(w in text for w in ["stop", "halt", "pause"]):
            return TranslationResult(
                success=True,
                tool="transport_control",
                args={"action": "stop"},
                method="fallback",
            )
        if any(w in text.split() for w in ["play", "start"]) or "play" == text:
            return TranslationResult(
                success=True,
                tool="transport_control",
                args={"action": "play"},
                method="fallback",
            )
        if any(w in text for w in ["record", "rec"]):
            return TranslationResult(
                success=True,
                tool="transport_control",
                args={"action": "record"},
                method="fallback",
            )

        # Toggle commands
        if "repeat" in text:
            return TranslationResult(
                success=True, tool="toggle_repeat", args={}, method="fallback"
            )
        if any(w in text for w in ["metronome", "click", "metro"]):
            return TranslationResult(
                success=True,
                tool="toggle_metronome",
                args={},
                method="fallback",
            )

        # Track mute/unmute (check unmute FIRST — "unmute" contains "mute")
        unmute_match = re.search(r"unmute\s+(?:the\s+)?(\w+)", text)
        mute_match = re.search(r"(?<!un)mute\s+(?:the\s+)?(\w+)", text)
        if unmute_match or mute_match:
            is_mute = not bool(unmute_match)
            track_name = (unmute_match or mute_match).group(1)
            track_num = self._resolve_track_name(track_name, daw_state)
            if track_num:
                return TranslationResult(
                    success=True,
                    tool="set_track_mute",
                    args={"track": track_num, "mute": is_mute},
                    method="fallback",
                )

        # Track solo/unsolo
        solo_match = re.search(r"solo\s+(?:the\s+)?(\w+)", text)
        unsolo_match = re.search(r"unsolo\s+(?:the\s+)?(\w+)", text)
        if solo_match or unsolo_match:
            is_solo = bool(solo_match)
            track_name = (solo_match or unsolo_match).group(1)
            track_num = self._resolve_track_name(track_name, daw_state)
            if track_num:
                return TranslationResult(
                    success=True,
                    tool="set_track_solo",
                    args={"track": track_num, "solo": is_solo},
                    method="fallback",
                )

        # Volume up
        vol_match = re.search(
            r"(?:turn\s+up|increase|louder|boost)\s+(?:the\s+)?(\w+)", text
        )
        if vol_match:
            track_name = vol_match.group(1)
            track_num = self._resolve_track_name(track_name, daw_state)
            if track_num:
                return TranslationResult(
                    success=True,
                    tool="set_track_volume",
                    args={"track": track_num, "volume": 0.85},
                    method="fallback",
                )

        # Volume down
        vol_down_match = re.search(
            r"(?:turn\s+down|decrease|quieter|lower)\s+(?:the\s+)?(\w+)", text
        )
        if vol_down_match:
            track_name = vol_down_match.group(1)
            track_num = self._resolve_track_name(track_name, daw_state)
            if track_num:
                return TranslationResult(
                    success=True,
                    tool="set_track_volume",
                    args={"track": track_num, "volume": 0.5},
                    method="fallback",
                )

        return TranslationResult(
            success=False,
            error=f"Could not understand command: {user_input}",
            method="fallback",
        )

    @staticmethod
    def _normalize_args(tool: str, args: dict) -> dict:
        """Fix common model output mistakes with argument names/values."""
        # set_track_volume: model sometimes uses "value" instead of "volume"
        if tool == "set_track_volume" and "value" in args and "volume" not in args:
            args["volume"] = args.pop("value")
        # set_track_mute: model sometimes omits mute (default True for "mute")
        if tool == "set_track_mute" and "mute" not in args:
            args["mute"] = True
        # set_track_solo: model sometimes omits solo (default True for "solo")
        if tool == "set_track_solo" and "solo" not in args:
            args["solo"] = True
        # set_track_arm: model sometimes omits arm (default True for "arm")
        if tool == "set_track_arm" and "arm" not in args:
            args["arm"] = True
        # transport_control: model sometimes omits action
        if tool == "transport_control" and "action" not in args:
            args["action"] = "play"
        return args

    def _parse_response(
        self, raw: str, method: str = "model"
    ) -> TranslationResult:
        """Parse model response into a single TranslationResult."""
        results = self._parse_response_multi(raw, method)
        return results[0] if results else TranslationResult(
            success=False, error="Could not parse response", method=method
        )

    def _parse_response_multi(
        self, raw: str, method: str = "model"
    ) -> list[TranslationResult]:
        """Parse model response into one or more TranslationResults.

        Handles both single JSON objects and JSON arrays of commands.
        """
        data = None

        # Try direct JSON parse
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code block
            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.DOTALL
            )
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # Try finding first { ... } or [ ... ] in the text
            if data is None:
                brace_match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
                if brace_match:
                    try:
                        data = json.loads(brace_match.group(0))
                    except json.JSONDecodeError:
                        pass

            if data is None:
                return [TranslationResult(
                    success=False,
                    error="Could not parse JSON from response",
                    raw_response=raw,
                    method=method,
                )]

        # Normalize to list
        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            return [TranslationResult(
                success=False,
                error=f"Expected JSON object or array, got {type(data).__name__}",
                raw_response=raw,
                method=method,
            )]

        results = []
        for item in items:
            if not isinstance(item, dict):
                results.append(TranslationResult(
                    success=False,
                    error=f"Expected object in array, got {type(item).__name__}",
                    raw_response=raw,
                    method=method,
                ))
                continue

            # Check for model-reported errors
            if "error" in item:
                results.append(TranslationResult(
                    success=False,
                    error=item.get("message", item["error"]),
                    raw_response=raw,
                    method=method,
                ))
                continue

            tool = item.get("tool", "")
            if tool not in TOOL_SCHEMAS:
                results.append(TranslationResult(
                    success=False,
                    error=f"Unknown tool: {tool}",
                    raw_response=raw,
                    method=method,
                ))
                continue

            args = item.get("args", {})
            args = self._normalize_args(tool, args)

            # Basic arg type coercion
            expected = TOOL_SCHEMAS[tool]
            for key, expected_type in expected.items():
                if key in args:
                    try:
                        if expected_type == int:
                            args[key] = int(args[key])
                        elif expected_type == float:
                            args[key] = float(args[key])
                        elif expected_type == bool:
                            args[key] = bool(args[key])
                    except (ValueError, TypeError):
                        results.append(TranslationResult(
                            success=False,
                            error=f"Invalid type for {key}: expected {expected_type.__name__}",
                            raw_response=raw,
                            method=method,
                        ))
                        continue

            # Extract delay_ms for sequencing
            delay_ms = item.get("delay_ms", 0)

            result = TranslationResult(
                success=True,
                tool=tool,
                args=args,
                raw_response=raw,
                method=method,
                delay_ms=delay_ms,
            )
            results.append(result)

        return results

    @staticmethod
    def _format_daw_state(state: DAWState) -> str:
        """Format DAW state into a human-readable description for the prompt."""
        lines = []
        if state.tracks:
            lines.append("Tracks:")
            for t in state.tracks:
                name = t.name or f"Track {t.track_number}"
                lines.append(
                    f"  {t.track_number}. {name} "
                    f"(vol={t.volume:.2f}, pan={t.pan:.2f}, "
                    f"mute={t.mute}, solo={t.solo})"
                )
        elif state.track_count > 0:
            lines.append(f"Track count: {state.track_count} (names not available, use track numbers)")
        lines.append(
            f"Transport: {'playing' if state.transport.playing else 'stopped'}"
            f"{' (recording)' if state.transport.recording else ''}"
            f" at {state.transport.position_seconds:.1f}s"
        )
        lines.append(
            f"Master: vol={state.master_volume:.2f}, pan={state.master_pan:.2f}"
        )
        return "\n".join(lines)

    @staticmethod
    def _resolve_track_name(name: str, state: DAWState) -> int | None:
        """Resolve a track name (case-insensitive) to a track number.

        Tries exact match, then partial match, then ordinal words.
        Falls back to Nth track if name is a common track label (drums, bass, etc.)
        and there are tracks available.
        """
        name_lower = name.lower()

        # Exact match
        for t in state.tracks:
            if t.name and t.name.lower() == name_lower:
                return t.track_number

        # Partial match
        for t in state.tracks:
            if t.name and name_lower in t.name.lower():
                return t.track_number

        # Ordinal words: "first" = 1, "second" = 2, etc.
        ordinals = {
            "first": 1, "1st": 1,
            "second": 2, "2nd": 2,
            "third": 3, "3rd": 3,
            "fourth": 4, "4th": 4,
            "fifth": 5, "5th": 5,
            "sixth": 6, "6th": 6,
            "seventh": 7, "7th": 7,
            "eighth": 8, "8th": 8,
        }
        if name_lower in ordinals:
            track_num = ordinals[name_lower]
            if any(t.track_number == track_num for t in state.tracks):
                return track_num

        # Common instrument names -> position in a typical rock/pop project
        # Drums=1, Bass=2, Vocals=3, Guitar=4, Synth/Keys=5
        common_instruments = {
            "drums": 1, "drum": 1, "kick": 1,
            "bass": 2,
            "vocals": 3, "vocal": 3, "voice": 3, "singing": 3,
            "guitar": 4, "guitars": 4,
            "synth": 5, "synths": 5, "keys": 5, "keyboard": 5, "piano": 5,
        }
        if name_lower in common_instruments:
            track_num = common_instruments[name_lower]
            # Only use this if the track exists AND has no name (unnamed)
            for t in state.tracks:
                if t.track_number == track_num:
                    if not t.name or t.name.lower() == "unnamed":
                        return track_num
                    break  # Track has a real name, don't override

        return None
