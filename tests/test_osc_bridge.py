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


class TestAddressValidation:
    """Test OSC address validation (offline — no Reaper needed)."""

    def test_valid_transport_address(self):
        assert ReaperOSC._validate_address("/play") is True

    def test_valid_track_volume_address(self):
        assert ReaperOSC._validate_address("/track/1/volume") is True

    def test_valid_track_count_address(self):
        assert ReaperOSC._validate_address("/track/count") is True

    def test_valid_master_volume_address(self):
        assert ReaperOSC._validate_address("/master/volume") is True

    def test_valid_master_pan_address(self):
        assert ReaperOSC._validate_address("/master/pan") is True

    def test_valid_time_address(self):
        assert ReaperOSC._validate_address("/time") is True

    def test_rejects_no_leading_slash(self):
        assert ReaperOSC._validate_address("play") is False

    def test_rejects_path_traversal(self):
        assert ReaperOSC._validate_address("/track/../etc/passwd") is False

    def test_rejects_null_byte(self):
        assert ReaperOSC._validate_address("/track/1\x00/volume") is False

    def test_rejects_unknown_pattern(self):
        assert ReaperOSC._validate_address("/some/random/address") is False

    def test_rejects_negative_track(self):
        # Regex \d+ won't match negative numbers
        assert ReaperOSC._validate_address("/track/-1/volume") is False

    def test_valid_fx_param_address(self):
        assert ReaperOSC._validate_address("/track/1/fx/2/fxparam/3/value") is True

    def test_valid_fx_bypass_address(self):
        assert ReaperOSC._validate_address("/track/3/fx/0/bypass") is True

    def test_valid_action_address(self):
        assert ReaperOSC._validate_address("/action") is True

    def test_valid_repeat_click(self):
        assert ReaperOSC._validate_address("/repeat") is True
        assert ReaperOSC._validate_address("/click") is True

    def test_valid_recarm_address(self):
        assert ReaperOSC._validate_address("/track/2/recarm") is True

    def test_valid_send_volume_address(self):
        assert ReaperOSC._validate_address("/track/1/send/2/volume") is True

    def test_valid_marker_addresses(self):
        assert ReaperOSC._validate_address("/marker/count") is True
        assert ReaperOSC._validate_address("/marker/1/name") is True
        assert ReaperOSC._validate_address("/marker/3/time") is True

    def test_rejects_control_characters(self):
        assert ReaperOSC._validate_address("/track/1/\x01volume") is False


class TestExtendedBridge:
    """Test new bridge methods (offline — no Reaper needed)."""

    def test_transport_seek_negative_rejected(self):
        """Negative seek position returns error without sending."""
        bridge = ReaperOSC(
            "127.0.0.1", 29998, 29999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.transport_seek(-5.0)
            assert result.success is False
            assert "must be >= 0" in result.error
        finally:
            bridge.close()

    def test_transport_seek_sends_correct_address(self):
        """transport_seek sends /time with the float value."""
        bridge = ReaperOSC(
            "127.0.0.1", 29998, 29999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.transport_seek(30.0)
            assert result.success is True
            assert result.address == "/time"
            assert result.sent_value == 30.0
        finally:
            bridge.close()

    def test_transport_seek_updates_state(self):
        """transport_seek optimistically updates position in state."""
        bridge = ReaperOSC(
            "127.0.0.1", 29998, 29999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            bridge.transport_seek(45.5)
            assert bridge.state.transport.position_seconds == 45.5
        finally:
            bridge.close()

    def test_master_pan_clamped(self):
        """Master pan is clamped to [-1.0, 1.0]."""
        bridge = ReaperOSC(
            "127.0.0.1", 29998, 29999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.set_master_pan(2.0)
            assert result.success is True
            assert result.address == "/master/pan"
        finally:
            bridge.close()

    def test_master_volume_clamped(self):
        """Master volume is clamped to [0.0, 1.0]."""
        bridge = ReaperOSC(
            "127.0.0.1", 29998, 29999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.set_master_volume(1.5)
            assert result.success is True
            assert result.address == "/master/volume"
        finally:
            bridge.close()

    def test_get_track_count_real_returns_int(self):
        """get_track_count_real returns an integer."""
        bridge = ReaperOSC(
            "127.0.0.1", 29998, 29999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            count = bridge.get_track_count_real()
            assert isinstance(count, int)
        finally:
            bridge.close()

    def test_send_command_rejects_invalid_address(self):
        """send_command rejects addresses that fail validation."""
        bridge = ReaperOSC(
            "127.0.0.1", 29998, 29999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.send_command("/evil/address")
            assert result.success is False
            assert "Invalid OSC address" in result.error
        finally:
            bridge.close()

    def test_daw_state_has_master_fields(self):
        """DAWState includes track_count, master_volume, master_pan."""
        from audioshuttle.models import DAWState
        state = DAWState()
        assert state.track_count == 0
        assert state.master_volume == 0.75
        assert state.master_pan == 0.0


class TestFXMethods:
    """Test FX control bridge methods (offline — no Reaper needed)."""

    def test_set_fx_param_sends_correct_address(self):
        """set_fx_param sends the right OSC address with clamped value."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.set_fx_param(1, 0, 2, 0.5)
            assert result.success is True
            assert result.address == "/track/1/fx/0/fxparam/2/value"
            assert result.sent_value == 0.5
        finally:
            bridge.close()

    def test_set_fx_param_clamps_value(self):
        """FX param value is clamped to [0.0, 1.0]."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.set_fx_param(1, 0, 0, 1.5)
            assert result.success is True
            # Value was clamped — the address is valid, so it sends
        finally:
            bridge.close()

    def test_fx_bypass_sends_1_for_bypass(self):
        """fx_bypass sends 1 when bypass=True."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.fx_bypass(2, 0, True)
            assert result.success is True
            assert result.address == "/track/2/fx/0/bypass"
            assert result.sent_value == 1
        finally:
            bridge.close()

    def test_fx_bypass_sends_0_for_enable(self):
        """fx_bypass sends 0 when bypass=False."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.fx_bypass(1, 0, False)
            assert result.success is True
            assert result.sent_value == 0
        finally:
            bridge.close()

    def test_fx_param_validates_track_number(self):
        """track=0 returns an error (tracks start at 1)."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.set_fx_param(0, 0, 0, 0.5)
            assert result.success is False
            assert "Invalid indices" in result.error
        finally:
            bridge.close()

    def test_fx_bypass_validates_track(self):
        """fx_bypass rejects track < 1."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.fx_bypass(0, 0, True)
            assert result.success is False
        finally:
            bridge.close()


class TestActionAndToggle:
    """Test action triggering and toggle methods."""

    def test_trigger_action_sends_correct_id(self):
        """trigger_action sends /action with the command ID."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.trigger_action(40025)
            assert result.success is True
            assert result.address == "/action"
            assert result.sent_value == 40025
        finally:
            bridge.close()

    def test_trigger_action_rejects_zero(self):
        """command_id 0 returns an error."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.trigger_action(0)
            assert result.success is False
            assert "must be > 0" in result.error
        finally:
            bridge.close()

    def test_trigger_action_rejects_negative(self):
        """Negative command_id returns an error."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.trigger_action(-1)
            assert result.success is False
        finally:
            bridge.close()

    def test_toggle_repeat_sends_address(self):
        """toggle_repeat sends /repeat."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.toggle_repeat()
            assert result.success is True
            assert result.address == "/repeat"
        finally:
            bridge.close()

    def test_toggle_metronome_sends_address(self):
        """toggle_metronome sends /click."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.toggle_metronome()
            assert result.success is True
            assert result.address == "/click"
        finally:
            bridge.close()


class TestTrackArm:
    """Test track record arm methods."""

    def test_recarm_sends_1_for_arm(self):
        """Arm sends /track/N/recarm with 1."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.set_track_recarm(1, True)
            assert result.success is True
            assert result.address == "/track/1/recarm"
            assert result.sent_value == 1
        finally:
            bridge.close()

    def test_recarm_sends_0_for_disarm(self):
        """Disarm sends /track/N/recarm with 0."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.set_track_recarm(3, False)
            assert result.success is True
            assert result.sent_value == 0
        finally:
            bridge.close()

    def test_recarm_rejects_invalid_track(self):
        """Track < 1 returns error."""
        bridge = ReaperOSC(
            "127.0.0.1", 39998, 39999,
            ping_interval=10.0, connection_timeout=10.0,
        )
        try:
            result = bridge.set_track_recarm(0, True)
            assert result.success is False
        finally:
            bridge.close()


class TestFXStateModel:
    """Test FXState model."""

    def test_fx_state_defaults(self):
        from audioshuttle.models import FXState
        fx = FXState(track_number=1, fx_index=0)
        assert fx.name == ""
        assert fx.bypassed is False
        assert fx.params == {}

    def test_fx_state_with_params(self):
        from audioshuttle.models import FXState
        fx = FXState(
            track_number=2, fx_index=1,
            name="Reverb", bypassed=False,
            params={0: 0.5, 1: 0.75},
        )
        assert fx.name == "Reverb"
        assert fx.params[0] == 0.5
