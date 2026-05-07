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
}

SYSTEM_PROMPT = """You are AudioShuttle, an AI assistant that translates natural language commands into DAW control actions for Reaper.

Given the current DAW state and a user command, output a JSON object with the tool to call and its arguments.

Output ONLY valid JSON, no markdown, no explanation:
{"tool": "<tool_name>", "args": {<key>: <value>}}

Available tools and their EXACT required arguments:
- transport_control: {"action": "play"|"stop"|"record"|"pause"}
- transport_seek: {"position_seconds": <float>}
- set_track_volume: {"track": <int>, "volume": <float 0.0-1.0>}
- set_track_mute: {"track": <int>, "mute": <bool>}
- set_track_solo: {"track": <int>, "solo": <bool>}
- set_track_pan: {"track": <int>, "pan": <float -1.0 to 1.0>}
- set_master_volume: {"volume": <float 0.0-1.0>}
- set_master_pan: {"pan": <float -1.0 to 1.0>}
- set_fx_param: {"track": <int>, "fx": <int>, "param": <int>, "value": <float>}
- fx_bypass: {"track": <int>, "fx": <int>, "bypass": <bool>}
- trigger_action: {"command_id": <int>}
- set_track_arm: {"track": <int>, "arm": <bool>}
- toggle_repeat: {}
- toggle_metronome: {}
- list_tracks: {} / get_transport: {} / get_daw_state: {} / get_track_count: {}

Rules:
- Match track NAMES case-insensitively to find the track NUMBER from the DAW state
- Include ALL required arguments for the chosen tool — do NOT omit any
- "mute X" means mute=True, "unmute X" means mute=False
- "solo X" means solo=True, "unsolo X" means solo=False
- Volume: "turn up/increase" = 0.85, "turn down/decrease" = 0.5, "normal" = 0.75
- Use the exact key names shown above (e.g. "volume" not "value" for set_track_volume)
- Track numbers start at 1
- For ambiguous commands: {"error": "ambiguous", "message": "what's unclear"}
- For unrecognized commands: {"error": "unclear", "message": "suggestion"}
- Do NOT output anything except the JSON object"""


def update_system_prompt(new_prompt: str) -> None:
    """Update the module-level SYSTEM_PROMPT used by IntentTranslator."""
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = new_prompt


class IntentTranslator:
    """Translates natural language commands to structured DAW tool calls."""

    def __init__(self, model_server: ModelServer | None = None) -> None:
        self._model_server = model_server

    def translate(self, user_input: str, daw_state: DAWState) -> TranslationResult:
        """Translate a natural language command to a tool call.

        Tries model-based translation first, falls back to rule-based.
        """
        # Try model-based translation
        # Check is_running OR health_check — the model server may be running
        # in a different process (e.g., started by the launcher)
        model_available = False
        if self._model_server:
            if self._model_server.is_running:
                model_available = True
            elif hasattr(self._model_server, 'health_check') and self._model_server.health_check():
                model_available = True

        if model_available:
            result = self._translate_with_model(user_input, daw_state)
            if result.success:
                return result
            logger.info(
                "Model translation failed, trying fallback: %s", result.error
            )

        # Fallback to rule-based
        return self._translate_with_rules(user_input, daw_state)

    def _translate_with_model(
        self, user_input: str, daw_state: DAWState
    ) -> TranslationResult:
        """Use E2B model to translate command."""
        state_desc = self._format_daw_state(daw_state)
        tools_list = ", ".join(sorted(TOOL_SCHEMAS.keys()))

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Current DAW state:\n{state_desc}\n\n"
                    f"Available tools: {tools_list}\n\n"
                    f"User command: {user_input}"
                ),
            },
        ]

        raw = self._model_server.chat(
            messages, temperature=0.1, max_tokens=256
        )
        if raw is None:
            return TranslationResult(
                success=False,
                error="Model returned no response",
                method="model",
            )

        return self._parse_response(raw, method="model")

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
        """Parse model response into TranslationResult."""
        data = None

        # Try direct JSON parse
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code block
            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL
            )
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # Try finding first { ... } in the text
            if data is None:
                brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
                if brace_match:
                    try:
                        data = json.loads(brace_match.group(0))
                    except json.JSONDecodeError:
                        pass

            if data is None:
                return TranslationResult(
                    success=False,
                    error="Could not parse JSON from response",
                    raw_response=raw,
                    method=method,
                )

        # Check for model-reported errors
        if "error" in data:
            return TranslationResult(
                success=False,
                error=data.get("message", data["error"]),
                raw_response=raw,
                method=method,
            )

        # Validate tool name
        tool = data.get("tool", "")
        if tool not in TOOL_SCHEMAS:
            return TranslationResult(
                success=False,
                error=f"Unknown tool: {tool}",
                raw_response=raw,
                method=method,
            )

        args = data.get("args", {})

        # Normalize common model mistakes with argument names
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
                    return TranslationResult(
                        success=False,
                        error=f"Invalid type for {key}: expected {expected_type.__name__}",
                        raw_response=raw,
                        method=method,
                    )

        return TranslationResult(
            success=True,
            tool=tool,
            args=args,
            raw_response=raw,
            method=method,
        )

    @staticmethod
    def _format_daw_state(state: DAWState) -> str:
        """Format DAW state into a human-readable description for the prompt."""
        lines = []
        if state.tracks:
            lines.append("Tracks:")
            for t in state.tracks:
                lines.append(
                    f"  {t.track_number}. {t.name or 'unnamed'} "
                    f"(vol={t.volume:.2f}, pan={t.pan:.2f}, "
                    f"mute={t.mute}, solo={t.solo})"
                )
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
        """Resolve a track name (case-insensitive) to a track number."""
        name_lower = name.lower()
        for t in state.tracks:
            if t.name.lower() == name_lower:
                return t.track_number
        # Partial match
        for t in state.tracks:
            if name_lower in t.name.lower():
                return t.track_number
        return None
