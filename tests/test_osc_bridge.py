"""Tests for OSC bridge module."""

import pytest
from pydantic import ValidationError

from audioshuttle.models import (
    CommandResult,
    DAWState,
    OSCCommand,
    TrackState,
    TransportState,
)


class TestModels:
    """Test data model creation and validation."""

    def test_track_state_defaults(self):
        t = TrackState(track_number=1)
        assert t.name == ""
        assert t.volume == 0.75
        assert t.pan == 0.0
        assert t.mute is False
        assert t.solo is False
        assert t.selected is False

    def test_track_state_custom(self):
        t = TrackState(
            track_number=3, name="Vocals", volume=0.9, pan=-0.3,
            mute=False, solo=True, selected=True
        )
        assert t.name == "Vocals"
        assert t.volume == 0.9
        assert t.pan == -0.3
        assert t.solo is True

    def test_track_volume_rejects_high(self):
        with pytest.raises(ValidationError):
            TrackState(track_number=1, volume=1.5)

    def test_track_volume_rejects_low(self):
        with pytest.raises(ValidationError):
            TrackState(track_number=1, volume=-0.5)

    def test_track_pan_rejects_out_of_range(self):
        with pytest.raises(ValidationError):
            TrackState(track_number=1, pan=2.0)
        with pytest.raises(ValidationError):
            TrackState(track_number=2, pan=-2.0)

    def test_transport_state_defaults(self):
        t = TransportState()
        assert t.playing is False
        assert t.recording is False
        assert t.tempo == 120.0
        assert t.time_signature == "4/4"

    def test_osc_command(self):
        cmd = OSCCommand(
            address="/track/1/volume",
            args=[0.75],
            description="Set track 1 volume to 75%"
        )
        assert cmd.address == "/track/1/volume"
        assert cmd.args == [0.75]

    def test_osc_command_no_args(self):
        cmd = OSCCommand(address="/play")
        assert cmd.args == []

    def test_command_result_success(self):
        r = CommandResult(success=True, address="/play", sent_value=1.0)
        assert r.success is True
        assert r.error is None

    def test_command_result_failure(self):
        r = CommandResult(success=False, address="/track/1/volume", error="timeout")
        assert r.success is False
        assert r.error == "timeout"

    def test_daw_state(self):
        state = DAWState(
            tracks=[TrackState(track_number=1, name="Drums")],
            transport=TransportState(playing=True),
            project_name="test",
        )
        assert len(state.tracks) == 1
        assert state.transport.playing is True
        assert state.project_name == "test"


class TestAddressFormatting:
    """Test OSC address construction."""

    def test_track_volume_address(self):
        track = 3
        assert f"/track/{track}/volume" == "/track/3/volume"

    def test_track_mute_address(self):
        track = 5
        assert f"/track/{track}/mute" == "/track/5/mute"

    def test_track_pan_address(self):
        track = 1
        assert f"/track/{track}/pan" == "/track/1/pan"

    def test_track_select_address(self):
        track = 2
        assert f"/track/{track}/select" == "/track/2/select"

    def test_fx_param_address(self):
        track, fx, param = 1, 2, 3
        assert f"/track/{track}/fx/{fx}/fxparam/{param}/value" == "/track/1/fx/2/fxparam/3/value"
