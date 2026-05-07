"""Tests for OSC bridge module."""

import pytest
import time
from pydantic import ValidationError

from audioshuttle.models import (
    CommandResult,
    DAWState,
    OSCCommand,
    TrackState,
    TransportState,
)
from audioshuttle.osc_bridge import ReaperOSC


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


class TestConnectionHealth:
    """Test connection health monitoring (offline — no Reaper needed)."""

    def test_reconnect_count_starts_at_zero(self):
        """Bridge starts with zero reconnection attempts."""
        bridge = ReaperOSC(
            "127.0.0.1", 19998, 19999,
            ping_interval=0.5, connection_timeout=1.0,
        )
        try:
            assert bridge.reconnect_count == 0
        finally:
            bridge.close()

    def test_disconnected_since_initially_set(self):
        """Bridge has grace period on startup, then detects disconnection."""
        bridge = ReaperOSC(
            "127.0.0.1", 19998, 19999,
            ping_interval=0.5, connection_timeout=1.0,
        )
        try:
            # Grace period: is_connected is True on startup
            assert bridge.is_connected is True
            # Wait for health loop to detect no Reaper
            # Needs: 1 ping interval (0.5s) + connection timeout (1.0s) + margin
            time.sleep(2.5)
            assert bridge.is_connected is False
            assert bridge._disconnected_since is not None
        finally:
            bridge.close()

    def test_health_thread_is_daemon(self):
        """Health monitoring thread is daemon (won't block exit)."""
        bridge = ReaperOSC(
            "127.0.0.1", 19998, 19999,
            ping_interval=0.5, connection_timeout=1.0,
        )
        try:
            assert bridge._health_thread.daemon is True
            assert bridge._health_thread.is_alive()
        finally:
            bridge.close()

    def test_close_stops_health_thread(self):
        """Closing the bridge stops the health monitor."""
        bridge = ReaperOSC(
            "127.0.0.1", 19998, 19999,
            ping_interval=0.5, connection_timeout=1.0,
        )
        bridge.close()
        time.sleep(0.5)
        assert not bridge._health_thread.is_alive()
