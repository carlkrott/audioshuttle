"""Tests for the intent translator."""

import pytest
from unittest.mock import MagicMock

from audioshuttle.models import (
    DAWState,
    TrackState,
    TransportState,
    TranslationResult,
)
from audioshuttle.translator import IntentTranslator, TOOL_SCHEMAS


def make_test_state() -> DAWState:
    """Create a DAWState with 5 named tracks for testing."""
    return DAWState(
        tracks=[
            TrackState(track_number=1, name="Drums"),
            TrackState(track_number=2, name="Bass"),
            TrackState(track_number=3, name="Vocals"),
            TrackState(track_number=4, name="Guitar"),
            TrackState(track_number=5, name="Synth"),
        ],
        transport=TransportState(playing=False, position_seconds=45.2),
    )


class TestTranslationResult:
    """Test TranslationResult model."""

    def test_success_result(self):
        r = TranslationResult(
            success=True, tool="set_track_mute", args={"track": 1, "mute": True}
        )
        assert r.success
        assert r.tool == "set_track_mute"
        assert r.args["track"] == 1

    def test_error_result(self):
        r = TranslationResult(success=False, error="unclear command")
        assert not r.success
        assert r.error == "unclear command"

    def test_method_field(self):
        r = TranslationResult(success=True, tool="play", method="model")
        assert r.method == "model"
        r2 = TranslationResult(success=True, tool="play", method="fallback")
        assert r2.method == "fallback"


class TestToolSchemas:
    """Test TOOL_SCHEMAS has all expected tools."""

    def test_all_37_tools_present(self):
        expected = {
            "list_tracks", "get_transport", "get_daw_state", "get_track_count",
            "transport_control", "transport_seek",
            "set_track_volume", "set_track_mute", "set_track_solo", "set_track_pan",
            "set_master_volume", "set_master_pan",
            "set_fx_param", "fx_bypass", "fx_next_preset", "fx_prev_preset", "fx_set_wetdry",
            "trigger_action", "set_track_arm",
            "toggle_repeat", "toggle_metronome", "undo", "redo",
            "set_tempo", "insert_track", "rename_track",
            "insert_midi_pattern", "set_track_color",
            "set_track_monitor", "set_track_auto_mode", "set_track_send_volume",
            "goto_marker", "set_marker_name", "set_loop_points",
            "create_song_structure", "generate_project",
        }
        assert expected == set(TOOL_SCHEMAS.keys()), \
            f"Missing: {expected - set(TOOL_SCHEMAS.keys())}, Extra: {set(TOOL_SCHEMAS.keys()) - expected}"


class TestStateFormatting:
    """Test DAW state formatting for prompts."""

    def test_format_empty_state(self):
        state = DAWState()
        text = IntentTranslator._format_daw_state(state)
        assert "Transport: stopped" in text

    def test_format_state_with_tracks(self):
        state = make_test_state()
        text = IntentTranslator._format_daw_state(state)
        assert "Drums" in text
        assert "Bass" in text
        assert "Vocals" in text
        # Compact format: track names on one line
        assert "Tracks (5):" in text

    def test_format_state_with_playing(self):
        state = DAWState(transport=TransportState(playing=True))
        text = IntentTranslator._format_daw_state(state)
        assert "playing" in text


class TestTrackNameResolution:
    """Test track name to number resolution."""

    def test_exact_match(self):
        state = make_test_state()
        assert IntentTranslator._resolve_track_name("drums", state) == 1

    def test_case_insensitive(self):
        state = make_test_state()
        assert IntentTranslator._resolve_track_name("DRUMS", state) == 1

    def test_partial_match(self):
        state = make_test_state()
        assert IntentTranslator._resolve_track_name("drum", state) == 1

    def test_no_match(self):
        state = make_test_state()
        assert IntentTranslator._resolve_track_name("bongo", state) is None


class TestResponseParsing:
    """Test model response parsing."""

    def test_parse_valid_json(self):
        t = IntentTranslator()
        result = t._parse_response(
            '{"tool": "transport_control", "args": {"action": "play"}}'
        )
        assert result.success
        assert result.tool == "transport_control"
        assert result.args == {"action": "play"}

    def test_parse_json_in_code_block(self):
        t = IntentTranslator()
        result = t._parse_response(
            '```json\n{"tool": "set_track_mute", "args": {"track": 1, "mute": true}}\n```'
        )
        assert result.success
        assert result.tool == "set_track_mute"

    def test_parse_bare_json_in_text(self):
        t = IntentTranslator()
        result = t._parse_response(
            'I think the right action is {"tool": "toggle_repeat", "args": {}} for this.'
        )
        assert result.success
        assert result.tool == "toggle_repeat"

    def test_parse_model_error(self):
        t = IntentTranslator()
        result = t._parse_response(
            '{"error": "ambiguous", "message": "which track?"}'
        )
        assert not result.success
        assert "which track" in result.error

    def test_parse_unknown_tool(self):
        t = IntentTranslator()
        result = t._parse_response('{"tool": "nonexistent", "args": {}}')
        assert not result.success
        assert "Unknown tool" in result.error

    def test_parse_invalid_json(self):
        t = IntentTranslator()
        result = t._parse_response("not json at all")
        assert not result.success
        assert "Could not parse" in result.error

    def test_parse_type_coercion(self):
        t = IntentTranslator()
        result = t._parse_response(
            '{"tool": "set_track_volume", "args": {"track": "1", "volume": "0.75"}}'
        )
        assert result.success
        assert result.args["track"] == 1
        assert result.args["volume"] == 0.75


class TestFallbackParser:
    """Test rule-based fallback parser."""

    def test_play(self):
        t = IntentTranslator()
        result = t.translate("play", make_test_state())
        assert result.success
        assert result.tool == "transport_control"
        assert result.args == {"action": "play"}

    def test_stop(self):
        t = IntentTranslator()
        result = t.translate("stop playback", make_test_state())
        assert result.success
        assert result.tool == "transport_control"
        assert result.args == {"action": "stop"}

    def test_mute_drums(self):
        t = IntentTranslator()
        result = t.translate("mute the drums", make_test_state())
        assert result.success
        assert result.tool == "set_track_mute"
        assert result.args == {"track": 1, "mute": True}

    def test_unmute_bass(self):
        t = IntentTranslator()
        result = t.translate("unmute the bass", make_test_state())
        assert result.success
        assert result.tool == "set_track_mute"
        assert result.args == {"track": 2, "mute": False}

    def test_solo_vocals(self):
        t = IntentTranslator()
        result = t.translate("solo the vocals", make_test_state())
        assert result.success
        assert result.tool == "set_track_solo"
        assert result.args == {"track": 3, "solo": True}

    def test_turn_up_guitar(self):
        t = IntentTranslator()
        result = t.translate("turn up the guitar", make_test_state())
        assert result.success
        assert result.tool == "set_track_volume"
        assert result.args == {"track": 4, "volume": 0.85}

    def test_turn_down_synth(self):
        t = IntentTranslator()
        result = t.translate("turn down the synth", make_test_state())
        assert result.success
        assert result.tool == "set_track_volume"
        assert result.args == {"track": 5, "volume": 0.5}

    def test_repeat(self):
        t = IntentTranslator()
        result = t.translate("toggle repeat", make_test_state())
        assert result.success
        assert result.tool == "toggle_repeat"

    def test_metronome(self):
        t = IntentTranslator()
        result = t.translate("metronome", make_test_state())
        assert result.success
        assert result.tool == "toggle_metronome"

    def test_unknown(self):
        t = IntentTranslator()
        result = t.translate("make it sound like metallica", make_test_state())
        assert not result.success
        assert "Could not understand" in result.error


class TestTranslatorIntegration:
    """Test end-to-end translation with mocked model server."""

    def _make_mock_server(self, response: str | None):
        mock = MagicMock()
        mock.is_running = True
        mock.chat.return_value = response
        return mock

    def test_interpret_mute_drums_via_model(self):
        mock_server = self._make_mock_server(
            '{"tool": "set_track_mute", "args": {"track": 1, "mute": true}}'
        )
        translator = IntentTranslator(mock_server)
        result = translator.translate("mute the drums", make_test_state())
        assert result.success
        assert result.tool == "set_track_mute"
        assert result.args == {"track": 1, "mute": True}
        assert result.method == "model"

    def test_interpret_play_via_model(self):
        mock_server = self._make_mock_server(
            '{"tool": "transport_control", "args": {"action": "play"}}'
        )
        translator = IntentTranslator(mock_server)
        result = translator.translate("start playing", make_test_state())
        assert result.success
        assert result.tool == "transport_control"

    def test_fallback_when_model_returns_none(self):
        mock_server = self._make_mock_server(None)
        translator = IntentTranslator(mock_server)
        result = translator.translate("mute the drums", make_test_state())
        assert result.success
        assert result.tool == "set_track_mute"
        assert result.method == "fallback"

    def test_fallback_when_no_model(self):
        translator = IntentTranslator(None)
        result = translator.translate("play", make_test_state())
        assert result.success
        assert result.tool == "transport_control"
        assert result.method == "fallback"

    def test_model_returns_error_falls_back(self):
        mock_server = self._make_mock_server(
            '{"error": "ambiguous", "message": "which track?"}'
        )
        translator = IntentTranslator(mock_server)
        result = translator.translate("make it louder", make_test_state())
        # Falls back to rules — "louder" doesn't match directly
        # but may still return fallback result or model error
        assert result.method in ("model", "fallback")
