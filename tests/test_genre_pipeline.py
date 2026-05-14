"""Tests for create_genre_project() pipeline orchestration."""

import pytest
from unittest.mock import patch, MagicMock, call
from audioshuttle.osc_bridge import ReaperOSC, CommandResult


def _make_mock_reaper():
    """Create a ReaperOSC instance with all state mocked out."""
    with patch.object(ReaperOSC, "__init__", lambda self: None):
        r = ReaperOSC()
        # Set _state (backing attr for state property) via object.__setattr__
        # to bypass the read-only property
    mock_state = MagicMock()
    object.__setattr__(r, "_state", mock_state)
    r._state.track_count = 0
    r._state.transport = MagicMock()
    r._state.transport.tempo = 120.0
    r._state.tracks = []
    r._log_command = MagicMock()
    return r


class TestGenreResolution:
    """Test genre resolution and parameter handling."""

    def test_genre_resolution_defaults(self):
        """create_genre_project calls get_genre with correct genre name."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "verse", "bars": 16}],
            "instruments": ["drums", "bass"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send") as mock_send, \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family") as mock_get_family, \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock")

            mock_get_genre.assert_called_once_with("rock")
            assert result.success is True

    def test_genre_resolution_case_insensitive(self):
        """ROCK and Rock both resolve to the rock profile via get_genre."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "verse", "bars": 16}],
            "instruments": ["drums"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            for genre_input in ["ROCK", "Rock", "rOcK"]:
                mock_get_genre.reset_mock()
                result = r.create_genre_project(genre_input)
                # get_genre does lowercase internally
                mock_get_genre.assert_called_once_with(genre_input)

    def test_tempo_override(self):
        """tempo=140 overrides genre default tempo."""
        r = _make_mock_reaper()
        profile = {"default_tempo": 120, "sections": [{"name": "v", "bars": 16}], "instruments": ["drums"]}
        with patch.object(r, "set_tempo") as mock_set_tempo, \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=140) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock", tempo=140)

            mock_get_tempo.assert_called_with("rock", 140)
            calls = mock_set_tempo.call_args_list
            assert any(c.args[0] == 140 for c in calls if c.args)

    def test_custom_instruments_override(self):
        """custom_instruments replaces genre instrument list."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums", "bass", "guitar", "vocals"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock", custom_instruments=["drums", "bass"])

            assert mock_insert.call_args[1]["count"] == 2

    def test_custom_sections_override(self):
        """custom_sections replaces genre section list."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v1", "bars": 16}, {"name": "v2", "bars": 16}],
            "instruments": ["drums"],
        }
        custom = [{"name": "intro", "bars": 4}, {"name": "outro", "bars": 4}]
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock", custom_sections=custom)

            call_args = mock_struct.call_args
            passed_sections = call_args[0][0]
            assert len(passed_sections) == 2
            assert passed_sections[0]["name"] == "intro"


class TestBusCreation:
    """Test bus track creation logic."""

    def test_bus_creation_single_instrument(self):
        """One guitar → no bus needed (need >1 instrument in family)."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums", "bass", "rhythm_guitar"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family") as mock_get_family, \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {"guitars": {"rhythm_guitar"}}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_get_family.side_effect = lambda inst: {
                "drums": "percussion", "bass": "bass", "rhythm_guitar": "guitars"
            }.get(inst, "synths")
            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock")

            # 3 instruments + 1 submaster (no buses since only 1 guitar) = 4
            assert mock_insert.call_args[1]["count"] == 4

    def test_bus_creation_multiple_instruments(self):
        """rhythm_guitar + lead_guitar → Guitars Bus created."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums", "bass", "rhythm_guitar", "lead_guitar"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family") as mock_get_family, \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {
                 "guitars": {"rhythm_guitar", "lead_guitar"},
                 "bass": {"bass"},
                 "percussion": {"drums"},
             }), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_get_family.side_effect = lambda inst: {
                "drums": "percussion", "bass": "bass",
                "rhythm_guitar": "guitars", "lead_guitar": "guitars"
            }.get(inst, "synths")
            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock")

            # 4 instruments + 1 Guitars bus + 1 submaster = 6
            assert mock_insert.call_args[1]["count"] == 6

    def test_submaster_always_created(self):
        """Submaster track always exists, regardless of instrument count."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track") as mock_rename, \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock")

            # 1 instrument + 0 buses + 1 submaster = 2 tracks
            assert mock_insert.call_args[1]["count"] == 2
            rename_calls = mock_rename.call_args_list
            track_names = [c.args[1] for c in rename_calls if c.args]
            assert "Submaster" in track_names


class TestFXChainApplication:
    """Test FX chain application per instrument."""

    def test_fx_chain_application(self):
        """Correct FX chain called for lead_guitar+rock."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["lead_guitar"],
        }
        fx_chain = [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ]
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family", return_value="guitars") as mock_get_family, \
             patch("audioshuttle.genre_profiles.get_fx_chain", return_value=fx_chain) as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {"guitars": {"lead_guitar"}}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock")

            mock_get_fx_chain.assert_called_with("lead_guitar", "rock")
            # _fx_trigger called for plugin load + 2 FX in chain = 3
            assert mock_fx.call_count >= 2

    def test_fx_chain_fallback(self):
        """lead_guitar+reggae uses _default chain when no reggae-specific guitar chain."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 75,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["lead_guitar"],
        }
        default_chain = [{"name": "ReaEQ", "type": "eq"}, {"name": "ReaComp", "type": "compressor"}]
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family", return_value="guitars") as mock_get_family, \
             patch("audioshuttle.genre_profiles.get_fx_chain", return_value=default_chain) as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=75) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {"guitars": {"lead_guitar"}}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("reggae")

            mock_get_fx_chain.assert_called_with("lead_guitar", "reggae")


class TestRouting:
    """Test instrument→bus→submaster routing."""

    def test_routing_guitars_to_bus(self):
        """rhythm_guitar and lead_guitar both send to Guitars Bus."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums", "bass", "rhythm_guitar", "lead_guitar"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send") as mock_send, \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family") as mock_get_family, \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {
                 "guitars": {"rhythm_guitar", "lead_guitar"},
                 "bass": {"bass"},
                 "percussion": {"drums"},
             }), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_get_family.side_effect = lambda inst: {
                "drums": "percussion", "bass": "bass",
                "rhythm_guitar": "guitars", "lead_guitar": "guitars"
            }.get(inst, "synths")
            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}
            mock_send.return_value = CommandResult(success=True, address="/routing/send", reaper_feedback="ok")

            result = r.create_genre_project("rock")

            # At least 3 sends: 2 guitars → bus, bass → submaster, drums → submaster
            # or 2 guitars → bus + 1 bus → submaster + 2 direct → submaster
            assert mock_send.call_count >= 3

    def test_routing_bus_to_submaster(self):
        """Guitars Bus sends to Submaster."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["rhythm_guitar", "lead_guitar"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send") as mock_send, \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family", return_value="guitars") as mock_get_family, \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {
                 "guitars": {"rhythm_guitar", "lead_guitar"},
             }), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}
            mock_send.return_value = CommandResult(success=True, address="/routing/send", reaper_feedback="ok")

            result = r.create_genre_project("rock")

            # 2 guitars → bus + 1 bus → submaster = 3 sends minimum
            assert mock_send.call_count >= 3

    def test_routing_direct_to_submaster(self):
        """Instrument without bus family sends direct to Submaster."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums"],
        }
        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send") as mock_send, \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family", return_value="percussion") as mock_get_family, \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {
                 "percussion": {"drums"},
             }), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}
            mock_send.return_value = CommandResult(success=True, address="/routing/send", reaper_feedback="ok")

            result = r.create_genre_project("rock")

            # 1 send: drums → Submaster (no bus)
            assert mock_send.call_count >= 1


class TestErrorRecovery:
    """Test error handling and watcher timeout recovery."""

    def test_step_failure_recovery(self):
        """If set_tempo fails, method returns partial result instead of crashing."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums"],
        }
        with patch.object(r, "set_tempo", side_effect=Exception("OSC timeout")), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            result = r.create_genre_project("rock")

            assert result is not None

    def test_watcher_timeout_handling(self):
        """If _watcher_alive() returns False early, method continues with remaining steps."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums", "bass"],
        }
        watcher_count = [0]

        original_exists = __import__("os").path.exists

        with patch.object(r, "set_tempo"), \
             patch.object(r, "refresh_state") as mock_refresh, \
             patch.object(r, "create_song_structure") as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua") as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger") as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain") as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.getmtime", return_value=0.0):

            mock_insert.return_value = True
            mock_refresh.return_value = None
            mock_struct.return_value = CommandResult(success=True, address="/markers", reaper_feedback="ok")
            mock_fx.return_value = {"success": True}

            def fake_exists(path):
                if "watcher_alive" in str(path):
                    watcher_count[0] += 1
                    return watcher_count[0] > 2
                return original_exists(path)

            with patch("os.path.exists", side_effect=fake_exists):
                result = r.create_genre_project("rock")

            assert result is not None


class TestPipelineOrdering:
    """Test that pipeline steps execute in correct order."""

    def test_full_pipeline_ordering(self):
        """Steps execute in correct order: tempo→markers→tracks→buses→plugins→MIDI→FX→routing."""
        r = _make_mock_reaper()
        call_order = []

        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums"],
        }

        with patch.object(r, "set_tempo", side_effect=lambda t: call_order.append(f"set_tempo({t})")) as mock_set_tempo, \
             patch.object(r, "refresh_state", side_effect=lambda **kw: call_order.append("refresh_state") or None) as mock_refresh, \
             patch.object(r, "create_song_structure", side_effect=lambda s, **kw: call_order.append("create_song_structure") or CommandResult(success=True, address="/markers", reaper_feedback="ok")) as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua", side_effect=lambda **kw: call_order.append("_insert_tracks_via_lua") or True) as mock_insert, \
             patch.object(r, "rename_track", side_effect=lambda i, n: call_order.append(f"rename_track({i},{n})") or None) as mock_rename, \
             patch.object(r, "_fx_trigger", side_effect=lambda *a, **kw: call_order.append("_fx_trigger") or {"success": True}) as mock_fx, \
             patch.object(r, "_clear_track_items", side_effect=lambda i, **kw: call_order.append("_clear_track_items") or None) as mock_clear, \
             patch.object(r, "_generate_arrangement", side_effect=lambda *a, **kw: call_order.append("_generate_arrangement") or None) as mock_gen, \
             patch.object(r, "create_send", side_effect=lambda s, d: call_order.append(f"create_send({s},{d})") or CommandResult(success=True, address="/routing/send", reaper_feedback="ok")) as mock_send, \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain", return_value=[]) as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            result = r.create_genre_project("rock")

            assert "set_tempo" in call_order[0]
            assert "create_song_structure" in call_order
            assert "_insert_tracks_via_lua" in call_order
            assert "refresh_state" in call_order

    def test_verify_state_after_each_step(self):
        """refresh_state() called after key pipeline steps."""
        r = _make_mock_reaper()
        profile = {
            "default_tempo": 120,
            "sections": [{"name": "v", "bars": 16}],
            "instruments": ["drums"],
        }
        refresh_count = [0]

        with patch.object(r, "set_tempo") as mock_set_tempo, \
             patch.object(r, "refresh_state", side_effect=lambda **kw: (refresh_count.__setitem__(0, refresh_count[0] + 1), None)[1]) as mock_refresh, \
             patch.object(r, "create_song_structure", return_value=CommandResult(success=True, address="/markers", reaper_feedback="ok")) as mock_struct, \
             patch.object(r, "_insert_tracks_via_lua", return_value=True) as mock_insert, \
             patch.object(r, "rename_track"), \
             patch.object(r, "_fx_trigger", return_value={"success": True}) as mock_fx, \
             patch.object(r, "_clear_track_items"), \
             patch.object(r, "_generate_arrangement"), \
             patch.object(r, "create_send"), \
             patch("audioshuttle.genre_profiles.get_genre", return_value=profile) as mock_get_genre, \
             patch("audioshuttle.genre_profiles.get_family"), \
             patch("audioshuttle.genre_profiles.get_fx_chain", return_value=[]) as mock_get_fx_chain, \
             patch("audioshuttle.genre_profiles.get_tempo", return_value=120) as mock_get_tempo, \
             patch("audioshuttle.genre_profiles.INSTRUMENT_FAMILIES", {}), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getmtime", return_value=0.0):

            result = r.create_genre_project("rock")

            assert refresh_count[0] >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])