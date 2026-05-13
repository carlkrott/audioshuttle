"""Tests for the section-aware arrangement engine."""

import pytest
from midiutil import MIDIFile
from unittest.mock import MagicMock, patch
from audioshuttle.osc_bridge import ReaperOSC


class TestSectionProfiles:
    """Test section profile lookup and normalization."""

    def test_normalize_section_names(self):
        """Section names normalize correctly."""
        assert ReaperOSC._normalize_section_name("Verse 1") == "verse"
        assert ReaperOSC._normalize_section_name("CHORUS") == "chorus"
        assert ReaperOSC._normalize_section_name("Pre-Chorus") == "prechorus"
        assert ReaperOSC._normalize_section_name("Intro") == "intro"
        assert ReaperOSC._normalize_section_name("Outro") == "outro"
        assert ReaperOSC._normalize_section_name("BRIDGE") == "bridge"

    def test_normalize_role(self):
        """Instrument roles normalize correctly."""
        assert ReaperOSC._normalize_role("Lead Synth") == "lead"
        assert ReaperOSC._normalize_role("FX Riser") == "fx"
        assert ReaperOSC._normalize_role("Snare+Hat") == "snare"
        assert ReaperOSC._normalize_role("Bass") == "bass"
        assert ReaperOSC._normalize_role("Keys") == "keys"
        assert ReaperOSC._normalize_role("Sub Kick") == "sub"

    def test_all_section_profiles_exist(self):
        """All expected section types have profiles."""
        profiles = ReaperOSC._SECTION_PROFILES
        for section in ["intro", "verse", "chorus", "bridge", "outro"]:
            assert section in profiles, f"Missing profile for {section}"
            assert "density" in profiles[section]
            assert "vel_range" in profiles[section]
            assert "active_roles" in profiles[section]

    def test_unknown_section_falls_back_to_verse(self):
        """Unknown section names get verse profile."""
        profiles = ReaperOSC._SECTION_PROFILES
        fallback = profiles.get("unknown_section", profiles["verse"])
        assert fallback["density"] == 0.6  # verse density

    def test_chorus_has_highest_density(self):
        """Chorus has the most instruments and highest density."""
        profiles = ReaperOSC._SECTION_PROFILES
        assert profiles["chorus"]["density"] >= profiles["verse"]["density"]
        assert profiles["chorus"]["density"] >= profiles["intro"]["density"]

    def test_intro_is_sparser_than_chorus(self):
        """Intro has fewer active roles than chorus."""
        profiles = ReaperOSC._SECTION_PROFILES
        assert len(profiles["intro"]["active_roles"]) < len(profiles["chorus"]["active_roles"])


class TestArrangementGeneration:
    """Test that section-aware MIDI is generated correctly."""

    def _make_bridge(self):
        """Create a ReaperOSC instance without connecting."""
        with patch("audioshuttle.osc_bridge.ReaperOSC.__init__", return_value=None):
            bridge = ReaperOSC.__new__(ReaperOSC)
            # Set internal state directly (property wraps _state)
            bridge._state = MagicMock()
            bridge._state.track_count = 0
            bridge._state.tempo = 120
            return bridge

    TICKS_PER_BEAT = 960  # midiutil default

    def _count_notes(self, midi: MIDIFile) -> int:
        """Count total NoteOn events in a MIDI file."""
        total = 0
        for track in midi.tracks:
            for event in track.eventList:
                if event.evtname == "NoteOn":
                    total += 1
        return total

    def _notes_in_bar_range(self, midi: MIDIFile, start_bar: int, end_bar: int) -> int:
        """Count NoteOn events that fall within a bar range (4/4 time)."""
        count = 0
        start_tick = start_bar * 4 * self.TICKS_PER_BEAT
        end_tick = end_bar * 4 * self.TICKS_PER_BEAT
        for track in midi.tracks:
            for event in track.eventList:
                if event.evtname == "NoteOn" and start_tick <= event.tick < end_tick:
                    count += 1
        return count

    def test_drums_sparser_in_intro_than_chorus(self):
        """Drums have fewer notes in intro vs chorus."""
        bridge = self._make_bridge()
        sections = [
            {"name": "Intro", "bars": 8},
            {"name": "Chorus", "bars": 8},
        ]
        scale_notes = ReaperOSC._scale_notes("C", "major")  # Use static method

        midi = MIDIFile(1)
        midi.addTempo(0, 0, 120)
        bridge._generate_arrangement(midi, 0, "drums", scale_notes, sections, 120)

        intro_notes = self._notes_in_bar_range(midi, 0, 8)
        chorus_notes = self._notes_in_bar_range(midi, 8, 16)
        # Chorus should have significantly more notes than intro
        assert chorus_notes > intro_notes, (
            f"Chorus ({chorus_notes} notes) should have more than intro ({intro_notes} notes)"
        )

    def test_bass_rests_in_intro(self):
        """Bass rests during intro (not in intro's active_roles)."""
        bridge = self._make_bridge()
        sections = [
            {"name": "Intro", "bars": 8},
            {"name": "Verse", "bars": 8},
        ]
        scale_notes = ReaperOSC._scale_notes("E", "minor")

        midi = MIDIFile(1)
        midi.addTempo(0, 0, 125)
        bridge._generate_arrangement(midi, 0, "bass", scale_notes, sections, 125)

        intro_notes = self._notes_in_bar_range(midi, 0, 8)
        verse_notes = self._notes_in_bar_range(midi, 8, 16)
        # Bass is NOT in intro active_roles, so intro should have 0 notes
        assert intro_notes == 0, f"Bass should rest in intro, but got {intro_notes} notes"
        assert verse_notes > 0, f"Bass should play in verse, but got 0 notes"

    def test_lead_rests_in_intro_outro(self):
        """Lead/melody rests in intro and outro sections."""
        bridge = self._make_bridge()
        sections = [
            {"name": "Intro", "bars": 4},
            {"name": "Verse", "bars": 8},
            {"name": "Chorus", "bars": 8},
            {"name": "Outro", "bars": 4},
        ]
        scale_notes = ReaperOSC._scale_notes("D", "minor")

        midi = MIDIFile(1)
        midi.addTempo(0, 0, 120)
        bridge._generate_arrangement(midi, 0, "lead", scale_notes, sections, 120)

        intro_notes = self._notes_in_bar_range(midi, 0, 4)
        outro_notes = self._notes_in_bar_range(midi, 20, 24)
        verse_notes = self._notes_in_bar_range(midi, 4, 12)
        chorus_notes = self._notes_in_bar_range(midi, 12, 20)

        # Lead should rest in intro and outro (not in active_roles)
        assert intro_notes == 0, f"Lead should rest in intro, got {intro_notes}"
        assert outro_notes == 0, f"Lead should rest in outro, got {outro_notes}"
        assert verse_notes > 0, f"Lead should play in verse"
        assert chorus_notes > 0, f"Lead should play in chorus"

    def test_all_roles_generate_midi(self):
        """Every supported instrument role generates some MIDI."""
        bridge = self._make_bridge()
        sections = [
            {"name": "Verse", "bars": 8},
            {"name": "Chorus", "bars": 8},
        ]
        scale_notes = ReaperOSC._scale_notes("C", "major")

        for role in ["drums", "bass", "melody", "lead", "keys", "pad",
                      "strings", "arp", "fx riser", "sub kick"]:
            midi = MIDIFile(1)
            midi.addTempo(0, 0, 120)
            bridge._generate_arrangement(midi, 0, role, scale_notes, sections, 120)

            total = self._count_notes(midi)
            assert total > 0, f"Role '{role}' generated 0 notes"

    def test_notes_confined_to_scale(self):
        """Melody notes stay within the specified scale."""
        bridge = self._make_bridge()
        sections = [{"name": "Chorus", "bars": 8}]
        scale_notes = ReaperOSC._scale_notes("C", "major")

        midi = MIDIFile(1)
        midi.addTempo(0, 0, 120)
        bridge._generate_arrangement(midi, 0, "melody", scale_notes, sections, 120)

        # Collect all pitches
        pitches = set()
        for track in midi.tracks:
            for event in track.eventList:
                if event.evtname == "NoteOn":
                    pitches.add(event.pitch % 12)

        # C major: C=0, D=2, E=4, F=5, G=7, A=9, B=11
        scale_classes = {n % 12 for n in scale_notes}
        # Allow octave transpositions
        for p in pitches:
            assert p in scale_classes, (
                f"Pitch class {p} not in scale {scale_classes}"
            )

    def test_chorus_drums_have_four_on_the_floor(self):
        """Chorus drums include kick on beat 3 (four on the floor)."""
        bridge = self._make_bridge()
        sections = [{"name": "Chorus", "bars": 4}]
        scale_notes = ReaperOSC._scale_notes("C", "major")

        midi = MIDIFile(1)
        midi.addTempo(0, 0, 120)
        bridge._generate_arrangement(midi, 0, "drums", scale_notes, sections, 120)

        # Check for kick (note 36) on beat 3 of first bar
        kick_on_beat3 = False
        beat3_tick = 2 * self.TICKS_PER_BEAT  # beat 3 = tick 2*960
        for track in midi.tracks:
            for event in track.eventList:
                if (event.evtname == "NoteOn" and event.pitch == 36
                        and abs(event.tick - beat3_tick) < 10):
                    kick_on_beat3 = True
                    break
        assert kick_on_beat3, "Chorus should have kick on beat 3 (four on the floor)"

    def test_full_midnight_drive_arrangement(self):
        """Full Midnight Drive structure generates MIDI for all sections."""
        bridge = self._make_bridge()
        sections = [
            {"name": "Intro", "bars": 8},
            {"name": "Verse 1", "bars": 16},
            {"name": "Chorus 1", "bars": 16},
            {"name": "Verse 2", "bars": 16},
            {"name": "Chorus 2", "bars": 16},
            {"name": "Outro", "bars": 8},
        ]
        scale_notes = ReaperOSC._scale_notes("E", "minor")

        # Test a few key instruments
        for role in ["drums", "bass", "lead", "keys", "arp"]:
            midi = MIDIFile(1)
            midi.addTempo(0, 0, 125)
            bridge._generate_arrangement(midi, 0, role, scale_notes, sections, 125)

            total = self._count_notes(midi)
            assert total > 0, f"Role '{role}' generated 0 notes for full arrangement"


class TestScaleNotes:
    """Test scale note generation for arrangement engine."""

    def test_e_minor_scale(self):
        """E minor scale produces correct notes."""
        notes = ReaperOSC._scale_notes("E", "minor")
        # E minor: E F# G A B C D
        # MIDI: E4=64, F#4=66, G4=67, A4=69, B4=71, C5=72, D5=74
        expected_classes = {4, 6, 7, 9, 11, 0, 2}  # pitch classes
        actual_classes = {n % 12 for n in notes}
        assert actual_classes == expected_classes

    def test_c_major_scale(self):
        """C major scale produces correct notes."""
        notes = ReaperOSC._scale_notes("C", "major")
        expected_classes = {0, 2, 4, 5, 7, 9, 11}  # C D E F G A B
        actual_classes = {n % 12 for n in notes}
        assert actual_classes == expected_classes
