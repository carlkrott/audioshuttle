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
    # Discovery
    "list_tracks": {},
    "get_transport": {},
    "get_daw_state": {},
    "get_track_count": {},
    # Transport
    "transport_control": {"action": str},
    "transport_seek": {"position_seconds": float},
    "toggle_repeat": {},
    "toggle_metronome": {},
    "undo": {},
    "redo": {},
    # Tempo
    "set_tempo": {"bpm": float},
    # Track controls
    "set_track_volume": {"track": int, "volume": float},
    "set_track_mute": {"track": int, "mute": bool},
    "set_track_solo": {"track": int, "solo": bool},
    "set_track_pan": {"track": int, "pan": float},
    "set_track_color": {"track": int, "color": str},
    "set_track_arm": {"track": int, "arm": bool},
    "set_track_monitor": {"track": int, "mode": int},
    "set_track_auto_mode": {"track": int, "mode": str},
    "set_track_send_volume": {"track": int, "send": int, "volume": float},
    # Master
    "set_master_volume": {"volume": float},
    "set_master_pan": {"pan": float},
    # Track management
    "insert_track": {},
    "rename_track": {"track": int, "name": str},
    "insert_midi_pattern": {"role": str, "track": int | None},
    # Song structure & project generation
    "create_song_structure": {"sections": list, "bpm": int | None},
    "generate_project": {"sections": list, "instruments": list, "key": str, "scale": str, "bpm": int},
    "assess_arrangement": {"key": str, "scale": str, "bpm": int, "sections": list, "instruments": list},
    "create_genre_project": {
        "genre": str,
        "tempo": int | None,
        "key": str,
        "scale": str,
        "custom_instruments": list | None,
        "custom_sections": list | None,
    },
    # FX
    "set_fx_param": {"track": int, "fx": int, "param": int, "value": float},
    "fx_bypass": {"track": int, "fx": int, "bypass": bool},
    "fx_next_preset": {"track": int, "fx": int},
    "fx_prev_preset": {"track": int, "fx": int},
    "fx_set_wetdry": {"track": int, "fx": int, "value": float},
    "load_plugin": {"track": int, "plugin_name": str},
    "remove_plugin": {"track": int, "fx": int},
    "set_plugin_preset": {"track": int, "fx": int, "preset_name": str},
    "get_plugin_params": {"track": int, "fx": int},
    "list_track_fx": {"track": int},
    "list_available_plugins": {},
    # Routing
    "create_send": {"source_track": int, "dest_track": int},
    "delete_send": {"track": int, "send": int},
    # Project management
    "wipe_project": {},
    # Track management extras
    "set_track_input": {"track": int, "input_code": int},
    "select_track": {"track": int},
    "move_track": {"track": int, "new_position": int},
    # Playback extras
    "set_playrate": {"rate": float},
    "solo_reset": {},
    "open_fx_ui": {"track": int, "fx": int},
    # Markers
    "goto_marker": {"marker": int},
    "set_marker_name": {"marker": int, "name": str},
    # Loop
    "set_loop_points": {"start": float, "end": float},
    # Actions
    "trigger_action": {"command_id": int},
    # Vision & Audio Analysis (multimodal — E2B sees/screenshots/hears spectrograms)
    "look_and_analyze": {"question": str},
    "listen_and_analyze": {"track": int | None, "start_sec": float, "duration_sec": float, "question": str},
}

SYSTEM_PROMPT = """Translate DAW commands to JSON. Output ONLY {"tool":...} or [{"tool":...}].

Discovery (return current state — use when user asks "what tracks", "show me", "current"):
- list_tracks: {} — list all tracks with names, volumes, FX
- get_transport: {} — play/stop/record state + position
- get_daw_state: {} — full state snapshot
- get_track_count: {} — just the number of tracks
- list_track_fx: {"track": int} — list FX/plugins on a specific track
- list_available_plugins: {} — list all available VST/JSFX plugins
- get_plugin_params: {"track": int, "fx": int} — dump all params with names/values. USE before set_fx_param to discover what to set.

Transport:
- transport_control: {"action": "play"/"stop"/"record"/"pause"}
- transport_seek: {"position_seconds": float}
- set_tempo: {"bpm": float}
- toggle_repeat, toggle_metronome, undo, redo: {}
- set_track_volume: {"track": int, "volume": 0.0-1.0}
- set_track_mute: {"track": int, "mute": bool}
- set_track_solo: {"track": int, "solo": bool}
- set_track_pan: {"track": int, "pan": -1.0 to 1.0}
- set_track_color: {"track": int, "color": "#hex" or "red"/"blue"/"green" etc}
- set_track_arm: {"track": int, "arm": bool}
- set_track_monitor: {"track": int, "mode": 0=off/1=normal/2=tape}
- set_track_auto_mode: {"track": int, "mode": "trim"/"read"/"latch"/"touch"/"write"}
- set_track_send_volume: {"track": int, "send": int, "volume": float}
- set_master_volume: {"volume": float}, set_master_pan: {"pan": float}
- insert_track: {}
- rename_track: {"track": int, "name": str}
- insert_midi_pattern: {"role": "drums"/"bass"/"chords"/"melody", "track": int|optional}
- generate_project: {"sections": [{"name": str, "bars": int}], "instruments": ["drums","bass","melody","keys","strings","lead","pad","arp","fx","sub"], "key": str, "scale": "major"/"minor"/"pentatonic"/"blues", "bpm": int}
  Creates full project: markers + tracks + section-aware MIDI arrangement. SINGLE command, do NOT split.
  Section-aware: intro=sparsedrums+keys, verse=drums+bass+keys+melody, chorus=ALL instruments loud, bridge=keys+pad+strings, outro=winding down.
- create_genre_project: {"genre": str, "tempo": int|null, "key": str, "scale": str, "custom_instruments": list[str]|null, "custom_sections": list|null, "modifiers": dict|null}
   Creates a complete genre-aware project with auto-routing, doubled instruments, layered sections, buses, FX chains per track, and per-section MIDI.
   PREFER this over generate_project when user mentions a genre or wants a complete project setup.

   Genre detection — pass the exact genre name the user said:
   Available genres: rock, metal, pop, electronic, hiphop, jazz, orchestral,
   ambient, funk, blues, reggae, worship, country, latin, soul, punk
   - "make a metal track" → genre="metal"  (NOT rock)
   - "create a pop song" → genre="pop"     (NOT rock — pop has its own profile)
   - "EDM banger" → genre="electronic"
   - If user says a multi-word genre like "hip hop" → genre="hiphop"
   - If user mentions a music style not in the list, use genre="rock" as default
   - Do NOT guess — use the exact genre name. Each genre has a unique profile
     with custom instruments, sections, tempo, FX chains, AND doubling config.

   Tempo detection — extract BPM if user specifies:
   - "at 140 bpm", "140 bpm", "tempo 140" → tempo=140
   - If not specified, use genre's default tempo

   Instrument overrides — respect user requests:
   - "with piano and strings" → custom_instruments=["keys", "strings"]
   - "just drums and bass" → custom_instruments=["drums", "bass"]
   - If not specified, use genre's default instruments

   Section overrides — respect user requests:
   - "intro verse chorus" → custom_sections=[{"name":"Intro","bars":4},{"name":"Verse","bars":16},{"name":"Chorus","bars":8}]
   - If not specified, use genre's default sections

   SINGLE command — do NOT split into multiple calls. This tool handles everything: tempo, markers, tracks, plugins, MIDI, buses, FX chains, and routing.

   Modifier system (genre adaptation):
   - You can adapt an existing genre by adding a "modifiers" field to create_genre_project
   - The modifiers dict supports:
     - "vibe": str — descriptive mood ("heavy", "chill", "epic", "stripped_back", "anthemic", "dark", "bright")
       Example: "heavy metal" → vibe="heavy"
     - "energy": str — overall energy level ("low", "medium", "high", "ballad", "banger")
       Example: "chill pop" → energy="low"
     - "emphasis": list[str] — instruments to feature/prominence ("cowbell", "lead_guitar", "vocals", "drums")
       Each emphasized instrument gets a density_mod boost of +0.2
       Example: "more cowbell" → emphasis=["cowbell"]
     - "plugin_overrides": {"role": "plugin_name"} — override default instrument plugins
       Example: {"lead_guitar": "JS: Distortion"} for heavier guitar tone
     - "midi_modifiers": {"role": {"density_mod": float, "complexity": str}}
       density_mod: -0.3 (sparser) to +0.3 (denser). complexity: "simple", "standard", "lead_melody", "chord_strum", "arpeggio"
       Example: {"drums": {"density_mod": 0.1, "complexity": "standard"}, "lead_guitar": {"density_mod": 0.2, "complexity": "lead_melody"}}
     - "fx_modifiers": {"role": ["plugin_name", ...]} — add extra FX beyond standard chain
       Example: {"lead_guitar": ["JS: Delay"]} for a delay effect on the lead
     - "section_changes": [{"name": str, "bars": int, "action": "add"|"modify"}] — change song structure
       Example: {"name": "Solo", "bars": 8, "action": "add"} for a guitar solo section after chorus
   - Use modifiers when the user asks for specific adaptations:
     "more solos" → add a Solo section, emphasis=["lead_guitar"], increase lead guitar density
     "heavier sound" → vibe="heavy", add distortion on guitars, increase drums density
     "longer intro" → increase intro bars
     "with piano" → add keys to custom_instruments
     "more cowbell" → emphasis=["cowbell"], cowbell density_mod +0.3
     "layered strings" → emphasis=["strings"], strings get density boost
     "anthemic" → vibe="anthemic", energy="high", emphasize vocals and pad
   - SINGLE command — do NOT split into multiple calls

- assess_arrangement: {"key": str, "scale": str, "bpm": int, "sections": list, "instruments": list} — Ask E2B model to rate the arrangement quality and suggest improvements.
- create_song_structure: {"sections": [{"name": str, "bars": int}], "bpm": int}
- set_fx_param: {"track": int, "fx": int, "param": int, "value": float}
- fx_bypass: {"track": int, "fx": int, "bypass": bool}
- fx_next_preset, fx_prev_preset: {"track": int, "fx": int}
- fx_set_wetdry: {"track": int, "fx": int, "value": 0.0-1.0}
- load_plugin: {"track": int, "plugin_name": str} — load VST/JSFX plugin by name. Instruments: ReaSynth, ReaSynDr, ReaSamplOmatic5000. Effects: ReaEQ, ReaComp, ReaDelay, ReaVerb, ReaGate, ReaLimit, ReaPitch, etc. JSFX: "JS: Delay", "JS: Chorus", "JS: Distortion", "JS: MIDI Arpeggiator", etc.
- remove_plugin: {"track": int, "fx": int} — remove plugin by FX index
- set_plugin_preset: {"track": int, "fx": int, "preset_name": str}
- create_send: {"source_track": int, "dest_track": int} — route audio from one track to another
- delete_send: {"track": int, "send": int} — remove a send
- set_track_input: {"track": int, "input_code": int} — set recording input. -1=none, 0=MIDI, 256=mono input 1, 6400=stereo input 1
- select_track: {"track": int}
- move_track: {"track": int, "new_position": int}
- set_playrate: {"rate": float} — playback speed (1.0=normal, changes pitch)
- solo_reset: {} — unsolo all tracks
- open_fx_ui: {"track": int, "fx": int} — show plugin window
- goto_marker: {"marker": int}
- set_marker_name: {"marker": int, "name": str}
- set_loop_points: {"start": float, "end": float}
- trigger_action: {"command_id": int}

Vision & Audio Analysis (E2B multimodal — captures screen/spectrogram):
- look_and_analyze: {"question": str} — Capture Reaper screenshot and ask E2B to analyze it. Use when user says "look at", "show me", "does this look", "check the arrangement", "how does it look", "what do you see".
- listen_and_analyze: {"track": int|null, "start_sec": float, "duration_sec": float, "question": str} — Render audio, convert to spectrogram, ask E2B to analyze. Use when user says "how does it sound", "listen to", "check the mix", "how's the bass". Default: track=null (full mix), start=0, duration=30.

Rules:
- New tracks go at bottom. If N tracks exist, first insert = N+1.
- "mute" = mute:true, "unmute" = mute:false
- "turn up" ≈ 0.85, "turn down" ≈ 0.5, "normal" ≈ 0.75
- "arm for recording" → arm=true + monitor mode=1
- "create project"/"generate project"/"new project"/"set up song" AND genre mentioned → create_genre_project (prefer over generate_project)
- "create project"/"generate project" WITHOUT genre → create_genre_project with genre="rock" (default)
- "add markers"/"song structure" → create_song_structure
- MULTI-STEP PROJECT CREATION: when user asks for a new project, FIRST wipe the old one, THEN create:
  "delete current project" / "wipe the project" / "clean slate" / "clear everything" / "start fresh" / "reset project" → wipe_project THEN create_genre_project
  For any "create X project" command in an existing project: automatically prepend wipe_project to the tool calls.
- Multiple commands use array with optional delay_ms
- Track numbers start at 1. FX/send indices are 0-based.

Examples:
  "play" → {"tool":"transport_control","args":{"action":"play"}}
  "mute drums and solo bass" (drums=T1,bass=T2) → [{"tool":"set_track_mute","args":{"track":1,"mute":true}},{"tool":"set_track_solo","args":{"track":2,"solo":true}}]
  "add drum track" → [{"tool":"insert_track","args":{}},{"tool":"insert_midi_pattern","args":{"role":"drums"}}]
  "create a track called Electric Guitar" (N tracks exist) → [{"tool":"insert_track","args":{}},{"tool":"rename_track","args":{"track":N+1,"name":"Electric Guitar"}}]
  "make a new track named Bass" (N tracks exist) → [{"tool":"insert_track","args":{}},{"tool":"rename_track","args":{"track":N+1,"name":"Bass"}}]
  "create a rock project" → {"tool":"create_genre_project","args":{"genre":"rock"}}
   "make me a jazz track at 140 bpm" → {"tool":"create_genre_project","args":{"genre":"jazz","tempo":140}}
   "create an EDM banger" → {"tool":"create_genre_project","args":{"genre":"electronic"}}
   "new project with drums and bass" → {"tool":"create_genre_project","args":{"genre":"rock","custom_instruments":["drums","bass"]}}
   "create a pop song with piano and strings at 100 bpm" → {"tool":"create_genre_project","args":{"genre":"pop","tempo":100,"custom_instruments":["keys","strings"]}}
   "create a metal project with a longer intro and more solos" → {"tool":"create_genre_project","args":{"genre":"metal","modifiers":{"vibe":"heavy","emphasis":["lead_guitar"],"midi_modifiers":{"lead_guitar":{"density_mod":0.2,"complexity":"lead_melody"}},"section_changes":[{"name":"Solo","bars":8,"action":"add"}]}}}
   "create a pop song with layered strings" → {"tool":"create_genre_project","args":{"genre":"pop","modifiers":{"vibe":"anthemic","emphasis":["strings","vocals"]}}}
   "heavy metal with more cowbell at 180bpm" → {"tool":"create_genre_project","args":{"genre":"metal","tempo":180,"custom_instruments":["cowbell"],"modifiers":{"vibe":"heavy","emphasis":["cowbell","lead_guitar"],"midi_modifiers":{"cowbell":{"density_mod":0.3,"complexity":"standard"}}}}}
   "chill ambient track" → {"tool":"create_genre_project","args":{"genre":"ambient","modifiers":{"vibe":"chill","energy":"low"}}}
   "anthemic rock" → {"tool":"create_genre_project","args":{"genre":"rock","modifiers":{"vibe":"anthemic","energy":"high","emphasis":["vocals","lead_guitar"]}}}
   "create project in D minor with drums bass melody, verse chorus verse" → {"tool":"generate_project","args":{"sections":[{"name":"Verse","bars":16},{"name":"Chorus","bars":8},{"name":"Verse","bars":16}],"instruments":["drums","bass","melody"],"key":"D","scale":"minor","bpm":120}}
  "set tempo 140 and play" → [{"tool":"set_tempo","args":{"bpm":140}},{"tool":"transport_control","args":{"action":"play"}}]
  "more reverb on track 2" → {"tool":"fx_set_wetdry","args":{"track":2,"fx":0,"value":0.8}}
  "put reasyndr on drums track" (drums=T1) → {"tool":"load_plugin","args":{"track":1,"plugin_name":"ReaSynDr"}}
  "add EQ to bass track" (bass=T2) → {"tool":"load_plugin","args":{"track":2,"plugin_name":"ReaEQ"}}
  "load reverb on track 3 and set to 80% wet" → [{"tool":"load_plugin","args":{"track":3,"plugin_name":"ReaVerb"}},{"tool":"fx_set_wetdry","args":{"track":3,"fx":0,"value":0.8}}]
  "what plugins are on track 2" → {"tool":"list_track_fx","args":{"track":2}}
  "show available plugins" → {"tool":"list_available_plugins","args":{}}
  "route drums to reverb" (drums=T1,reverb=T3) → {"tool":"create_send","args":{"source_track":1,"dest_track":3}}
  "what parameters does EQ on track 2 have" → {"tool":"get_plugin_params","args":{"track":2,"fx":0}}

CRITICAL: Output ONLY JSON. No explanations. No markdown. No thinking. Just {"tool":...} or [{"tool":...}].
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

        # Single user message — avoids Jinja template issues with system role
        messages = [
            {
                "role": "user",
                "content": (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"DAW: {state_desc}\n\n"
                    f"Command: {user_input}\n\n"
                    f"Respond with only the JSON (object or array)."
                ),
            },
        ]

        # Emit STT event for the thinking stream
        try:
            from audioshuttle.thinking_stream import ThinkingStream
            ThinkingStream.instance().emit_stt(user_input)
        except Exception:
            pass

        raw = self._model_server.chat(
            messages, temperature=0.1, max_tokens=4096
        )
        if raw is None:
            return [TranslationResult(
                success=False,
                error="Model returned no response",
                method="model",
            )]

        logger.info("Model raw response: %s", raw[:500])

        # Emit tool calls to thinking stream
        results = self._parse_response_multi(raw, method="model")
        try:
            from audioshuttle.thinking_stream import ThinkingStream
            ts = ThinkingStream.instance()
            for r in results:
                if r.success:
                    ts.emit_tool_call(r.tool, r.args)
        except Exception:
            pass

        return results

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
        # set_track_volume: bridge uses "value", not "volume"
        if tool == "set_track_volume" and "volume" in args:
            args["value"] = args.pop("volume")
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
        """Format DAW state into a compact description for the prompt."""
        lines = []
        if state.tracks:
            # Compact: just track number and name (model doesn't need vol/pan details)
            names = [f"{t.track_number}.{t.name or 'unnamed'}" for t in state.tracks]
            lines.append(f"Tracks ({len(state.tracks)}): " + ", ".join(names))
        elif state.track_count > 0:
            lines.append(f"Track count: {state.track_count} (names not available)")
        lines.append(
            f"Transport: {'playing' if state.transport.playing else 'stopped'}"
            f"{' (recording)' if state.transport.recording else ''}"
            f" at {state.transport.position_seconds:.1f}s"
        )
        if state.transport.tempo > 0:
            lines.append(f"Tempo: {state.transport.tempo:.0f} BPM")
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
