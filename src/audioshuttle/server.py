"""AudioShuttle MCP server — exposes DAW control tools."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

from audioshuttle.config import Settings
from audioshuttle.models import CommandResult
from audioshuttle.osc_bridge import ReaperOSC

logger = logging.getLogger(__name__)


def create_server(settings: Settings | None = None) -> FastMCP:
    """Create an MCP server with DAW control tools.

    Args:
        settings: Configuration. Uses defaults if not provided.

    Returns:
        FastMCP server instance with tools registered.
    """
    if settings is None:
        settings = Settings()

    mcp = FastMCP(
        "AudioShuttle",
        instructions=(
            "DAW control server for Reaper. Control tracks (volume, mute, solo, pan, "
            "record arm), transport (play, stop, record, pause, seek), master volume/pan, "
            "FX parameters and bypass, trigger Reaper actions, toggle repeat and metronome. "
            "Track numbers start at 1. Volume is 0.0-1.0. Pan is -1.0 (left) to 1.0 (right). "
            "FX and parameter indices are 0-based."
        ),
    )

    bridge = ReaperOSC(
        host=settings.reaper_host,
        send_port=settings.reaper_port,
        feedback_port=settings.reaper_feedback_port,
    )

    # ── State discovery tools ──────────────────────────────────

    @mcp.tool()
    def list_tracks() -> dict[str, Any]:
        """List all tracks in the current Reaper project with their state.

        Returns track number, name, volume, pan, mute, and solo status.
        """
        bridge.refresh_state()
        tracks = [
            {
                "number": t.track_number,
                "name": t.name,
                "volume": t.volume,
                "pan": t.pan,
                "mute": t.mute,
                "solo": t.solo,
            }
            for t in bridge.state.tracks
        ]
        return {"tracks": tracks, "count": len(tracks)}

    @mcp.tool()
    def get_transport() -> dict[str, Any]:
        """Get current Reaper transport state (playback, recording, position)."""
        t = bridge.state.transport
        return {
            "playing": t.playing,
            "recording": t.recording,
            "position_seconds": t.position_seconds,
            "tempo": t.tempo,
            "time_signature": t.time_signature,
        }

    @mcp.tool()
    def get_daw_state() -> dict[str, Any]:
        """Get full DAW state snapshot — all tracks, transport, and project info."""
        bridge.refresh_state()
        return {
            "tracks": [
                {
                    "number": t.track_number,
                    "name": t.name,
                    "volume": t.volume,
                    "pan": t.pan,
                    "mute": t.mute,
                    "solo": t.solo,
                }
                for t in bridge.state.tracks
            ],
            "transport": {
                "playing": bridge.state.transport.playing,
                "recording": bridge.state.transport.recording,
                "position_seconds": bridge.state.transport.position_seconds,
                "tempo": bridge.state.transport.tempo,
            },
            "track_count": bridge.state.track_count,
            "master_volume": bridge.state.master_volume,
            "master_pan": bridge.state.master_pan,
            "project_name": bridge.state.project_name,
            "connected": bridge.is_connected,
        }

    # ── Transport tools ────────────────────────────────────────

    @mcp.tool()
    def transport_control(action: str) -> dict[str, Any]:
        """Control Reaper transport (play, stop, record, pause).

        Args:
            action: One of: play, stop, record, pause
        """
        action = action.lower().strip()
        valid = {"play", "stop", "record", "pause"}
        if action not in valid:
            return {
                "success": False,
                "error": f"Invalid action '{action}'. Must be one of: {', '.join(sorted(valid))}",
            }

        result = getattr(bridge, f"transport_{action}")()
        return {"success": result.success, "action": action}

    # ── Track control tools ─────────────────────────────────────

    @mcp.tool()
    def set_track_volume(track: int, volume: float) -> dict[str, Any]:
        """Set a track's volume level.

        Args:
            track: Track number (starts at 1)
            volume: Volume level from 0.0 (silent) to 1.0 (max)
        """
        volume = max(0.0, min(1.0, volume))
        result = bridge.set_track_volume(track, volume)
        return {
            "success": result.success,
            "track": track,
            "volume": volume,
            "error": result.error,
        }

    @mcp.tool()
    def set_track_mute(track: int, mute: bool) -> dict[str, Any]:
        """Mute or unmute a track.

        Args:
            track: Track number (starts at 1)
            mute: True to mute, False to unmute
        """
        result = bridge.set_track_mute(track, mute)
        return {
            "success": result.success,
            "track": track,
            "muted": mute,
            "error": result.error,
        }

    @mcp.tool()
    def set_track_solo(track: int, solo: bool) -> dict[str, Any]:
        """Solo or unsolo a track.

        Args:
            track: Track number (starts at 1)
            solo: True to solo, False to unsolo
        """
        result = bridge.set_track_solo(track, solo)
        return {
            "success": result.success,
            "track": track,
            "soloed": solo,
            "error": result.error,
        }

    @mcp.tool()
    def set_track_pan(track: int, pan: float) -> dict[str, Any]:
        """Set a track's pan position.

        Args:
            track: Track number (starts at 1)
            pan: Pan from -1.0 (full left) to 1.0 (full right), 0.0 is center
        """
        pan = max(-1.0, min(1.0, pan))
        result = bridge.set_track_pan(track, pan)
        return {
            "success": result.success,
            "track": track,
            "pan": pan,
            "error": result.error,
        }

    # ── Transport seek ──────────────────────────────────────────

    @mcp.tool()
    def transport_seek(position_seconds: float) -> dict[str, Any]:
        """Seek to a specific position in the timeline.

        Args:
            position_seconds: Position in seconds from the start
        """
        if position_seconds < 0:
            return {
                "success": False,
                "error": f"Position must be >= 0, got {position_seconds}",
            }
        result = bridge.transport_seek(position_seconds)
        return {
            "success": result.success,
            "position_seconds": position_seconds,
            "error": result.error,
        }

    # ── Track discovery ─────────────────────────────────────────

    @mcp.tool()
    def get_track_count() -> dict[str, Any]:
        """Get the number of tracks in the current Reaper project."""
        count = bridge.get_track_count_real()
        return {"track_count": count}

    # ── Master control ──────────────────────────────────────────

    @mcp.tool()
    def set_master_volume(volume: float) -> dict[str, Any]:
        """Set the master track volume.

        Args:
            volume: Volume from 0.0 (silent) to 1.0 (max)
        """
        volume = max(0.0, min(1.0, volume))
        result = bridge.set_master_volume(volume)
        return {
            "success": result.success,
            "volume": volume,
            "error": result.error,
        }

    @mcp.tool()
    def set_master_pan(pan: float) -> dict[str, Any]:
        """Set the master track pan position.

        Args:
            pan: Pan from -1.0 (full left) to 1.0 (full right), 0.0 is center
        """
        pan = max(-1.0, min(1.0, pan))
        result = bridge.set_master_pan(pan)
        return {
            "success": result.success,
            "pan": pan,
            "error": result.error,
        }

    # ── FX control ──────────────────────────────────────────────

    @mcp.tool()
    def set_fx_param(track: int, fx: int, param: int, value: float) -> dict[str, Any]:
        """Set an FX plugin parameter value. FX and param indices are 0-based.

        Args:
            track: Track number (starts at 1)
            fx: FX plugin index on the track (starts at 0)
            param: Parameter index within the FX (starts at 0)
            value: Parameter value from 0.0 to 1.0
        """
        result = bridge.set_fx_param(track, fx, param, value)
        return {
            "success": result.success,
            "track": track,
            "fx": fx,
            "param": param,
            "value": max(0.0, min(1.0, value)),
            "error": result.error,
        }

    @mcp.tool()
    def fx_bypass(track: int, fx: int, bypass: bool) -> dict[str, Any]:
        """Bypass or enable an FX plugin on a track.

        Args:
            track: Track number (starts at 1)
            fx: FX index on the track (starts at 0)
            bypass: True to bypass, False to enable
        """
        result = bridge.fx_bypass(track, fx, bypass)
        return {
            "success": result.success,
            "track": track,
            "fx": fx,
            "bypassed": bypass,
            "error": result.error,
        }

    # ── Action triggering ───────────────────────────────────────

    @mcp.tool()
    def trigger_action(command_id: int) -> dict[str, Any]:
        """Trigger a Reaper action by its command ID. Use this for any Reaper action not covered by other tools.

        Args:
            command_id: Reaper action command ID (positive integer, e.g. 40025 for 'Go to marker 1')
        """
        if command_id <= 0:
            return {
                "success": False,
                "error": f"command_id must be > 0, got {command_id}",
            }
        result = bridge.trigger_action(command_id)
        return {
            "success": result.success,
            "action_id": command_id,
            "error": result.error,
        }

    # ── Track arm ───────────────────────────────────────────────

    @mcp.tool()
    def set_track_arm(track: int, arm: bool) -> dict[str, Any]:
        """Arm or disarm a track for recording.

        Args:
            track: Track number (starts at 1)
            arm: True to arm for recording, False to disarm
        """
        result = bridge.set_track_recarm(track, arm)
        return {
            "success": result.success,
            "track": track,
            "armed": arm,
            "error": result.error,
        }

    # ── Toggles ─────────────────────────────────────────────────

    @mcp.tool()
    def toggle_repeat() -> dict[str, Any]:
        """Toggle repeat on/off in Reaper."""
        result = bridge.toggle_repeat()
        return {
            "success": result.success,
            "toggled": "repeat",
            "error": result.error,
        }

    @mcp.tool()
    def toggle_metronome() -> dict[str, Any]:
        """Toggle the metronome/click on/off."""
        result = bridge.toggle_metronome()
        return {
            "success": result.success,
            "toggled": "metronome",
            "error": result.error,
        }

    return mcp
