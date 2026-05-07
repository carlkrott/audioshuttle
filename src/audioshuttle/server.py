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
            "DAW control server for Reaper. Use these tools to control "
            "track volumes, mute/solo, pan, transport, and read DAW state. "
            "Track numbers start at 1. Volume is 0.0-1.0 float. "
            "Pan is -1.0 (left) to 1.0 (right)."
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

    return mcp
