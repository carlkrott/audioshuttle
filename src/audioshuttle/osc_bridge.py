"""OSC bridge module for Reaper communication."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from pythonosc import udp_client
from pythonosc import dispatcher as osc_dispatcher
from pythonosc import osc_server
import threading

from audioshuttle.models import (
    CommandResult,
    DAWState,
    TrackState,
    TransportState,
)

logger = logging.getLogger(__name__)


class ReaperOSC:
    """Bidirectional OSC bridge to Reaper DAW.

    Sends commands on send_port (default 8000) and listens
    for feedback on feedback_port (default 9000).
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        send_port: int = 8000,
        feedback_port: int = 9000,
    ) -> None:
        self._host = host
        self._send_port = send_port
        self._feedback_port = feedback_port

        # UDP client for sending commands
        self._client = udp_client.SimpleUDPClient(host, send_port)

        # Internal state
        self._state = DAWState()
        self._last_feedback_time: float = 0.0
        self._message_log: deque[tuple[str, Any]] = deque(maxlen=500)

        # Feedback listener
        self._dispatcher = osc_dispatcher.Dispatcher()
        self._dispatcher.set_default_handler(self._on_osc_message)
        self._server = osc_server.ThreadingOSCUDPServer(
            ("127.0.0.1", feedback_port), self._dispatcher
        )
        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._server_thread.start()
        logger.info(
            "ReaperOSC initialized: send=%s:%d, feedback=127.0.0.1:%d",
            host, send_port, feedback_port,
        )

    # ── Properties ──────────────────────────────────────────────

    @property
    def state(self) -> DAWState:
        """Current cached DAW state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """True if Reaper has sent feedback in the last 5 seconds."""
        return (time.time() - self._last_feedback_time) < 5.0

    @property
    def message_log(self) -> deque[tuple[str, Any]]:
        """Recent OSC messages received from Reaper."""
        return self._message_log

    # ── Low-level send ──────────────────────────────────────────

    def send_command(self, address: str, *args: Any) -> CommandResult:
        """Send a raw OSC command to Reaper."""
        try:
            self._client.send_message(address, list(args))
            logger.debug("Sent: %s %s", address, args)
            return CommandResult(
                success=True,
                address=address,
                sent_value=list(args) if len(args) > 1 else args[0] if args else None,
            )
        except Exception as e:
            logger.error("Failed to send %s: %s", address, e)
            return CommandResult(success=False, address=address, error=str(e))

    # ── Transport ───────────────────────────────────────────────

    def transport_play(self) -> CommandResult:
        """Start playback."""
        return self.send_command("/play", 1.0)

    def transport_stop(self) -> CommandResult:
        """Stop playback."""
        return self.send_command("/stop", 1.0)

    def transport_record(self) -> CommandResult:
        """Toggle recording."""
        return self.send_command("/record", 1.0)

    def transport_pause(self) -> CommandResult:
        """Pause playback."""
        return self.send_command("/pause", 1.0)

    # ── Track controls ──────────────────────────────────────────

    def select_track(self, track: int) -> CommandResult:
        """Select a track in Reaper (needed before some commands)."""
        return self.send_command(f"/track/{track}/select", 1)

    def set_track_volume(self, track: int, value: float) -> CommandResult:
        """Set track volume (0.0 to 1.0, clamped)."""
        value = max(0.0, min(1.0, value))
        return self.send_command(f"/track/{track}/volume", value)

    def set_track_mute(self, track: int, mute: bool) -> CommandResult:
        """Mute or unmute a track."""
        return self.send_command(f"/track/{track}/mute", 1 if mute else 0)

    def set_track_solo(self, track: int, solo: bool) -> CommandResult:
        """Solo or unsolo a track."""
        return self.send_command(f"/track/{track}/solo", 1 if solo else 0)

    def set_track_pan(self, track: int, pan: float) -> CommandResult:
        """Set track pan (-1.0 left to 1.0 right, clamped)."""
        pan = max(-1.0, min(1.0, pan))
        return self.send_command(f"/track/{track}/pan", pan)

    # ── Track controls (select-first approach) ──────────────────

    def set_track_volume_selected(self, track: int, value: float) -> list[CommandResult]:
        """Select track first, then set volume (works around some OSC issues)."""
        value = max(0.0, min(1.0, value))
        r1 = self.select_track(track)
        time.sleep(0.05)
        r2 = self.send_command("/track/volume", value)
        return [r1, r2]

    def set_track_mute_selected(self, track: int, mute: bool) -> list[CommandResult]:
        """Select track first, then mute (works around some OSC issues)."""
        r1 = self.select_track(track)
        time.sleep(0.05)
        r2 = self.send_command("/track/mute", 1 if mute else 0)
        return [r1, r2]

    def set_track_solo_selected(self, track: int, solo: bool) -> list[CommandResult]:
        """Select track first, then solo (works around some OSC issues)."""
        r1 = self.select_track(track)
        time.sleep(0.05)
        r2 = self.send_command("/track/solo", 1 if solo else 0)
        return [r1, r2]

    def set_track_pan_selected(self, track: int, pan: float) -> list[CommandResult]:
        """Select track first, then set pan (works around some OSC issues)."""
        pan = max(-1.0, min(1.0, pan))
        r1 = self.select_track(track)
        time.sleep(0.05)
        r2 = self.send_command("/track/pan", pan)
        return [r1, r2]

    # ── Master ──────────────────────────────────────────────────

    def set_master_volume(self, value: float) -> CommandResult:
        """Set master volume (0.0 to 1.0, clamped)."""
        value = max(0.0, min(1.0, value))
        return self.send_command("/master/volume", value)

    # ── State discovery ─────────────────────────────────────────

    def refresh_state(self) -> DAWState:
        """Probe Reaper for current state by requesting track info."""
        # Send requests that trigger Reaper feedback
        for i in range(1, 9):
            self.send_command(f"/track/{i}/name")
            self.send_command(f"/track/{i}/volume")
            self.send_command(f"/track/{i}/mute")
            self.send_command(f"/track/{i}/solo")
        self.send_command("/master/volume")
        return self._state

    def get_track_count(self) -> int:
        """Probe tracks until no response (heuristic)."""
        count = 0
        for i in range(1, 65):
            self.send_command(f"/track/{i}/name")
            time.sleep(0.01)
            count = i
        return count

    # ── Feedback handler ────────────────────────────────────────

    def _on_osc_message(self, address: str, *args: Any) -> None:
        """Handle incoming OSC messages from Reaper."""
        self._last_feedback_time = time.time()
        self._message_log.append((address, args))
        logger.debug("Recv: %s %s", address, args)

        # Update internal state from feedback
        self._update_state(address, args)

    def _update_state(self, address: str, args: tuple) -> None:
        """Parse Reaper feedback into internal state."""
        if not args:
            return

        val = args[0]

        # Transport state
        if address == "/play":
            self._state.transport.playing = bool(val)
        elif address == "/record":
            self._state.transport.recording = bool(val)
        elif address == "/stop":
            if val == 1.0:
                self._state.transport.playing = False
        elif address == "/time":
            self._state.transport.position_seconds = float(val)

        # Track state (addressed: /track/N/...)
        parts = address.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "track":
            try:
                track_num = int(parts[1])
                attr = parts[2]

                # Ensure track exists in state
                track = self._get_or_create_track(track_num)

                if attr == "name" and isinstance(val, str):
                    track.name = val
                elif attr == "volume":
                    track.volume = float(val)
                elif attr == "mute":
                    track.mute = bool(val)
                elif attr == "solo":
                    track.solo = bool(val)
                elif attr == "pan":
                    track.pan = float(val)
            except (ValueError, IndexError):
                pass

    def _get_or_create_track(self, track_num: int) -> TrackState:
        """Get existing track or create new one in state."""
        for t in self._state.tracks:
            if t.track_number == track_num:
                return t
        track = TrackState(track_number=track_num)
        self._state.tracks.append(track)
        self._state.tracks.sort(key=lambda t: t.track_number)
        return track

    # ── Lifecycle ───────────────────────────────────────────────

    def close(self) -> None:
        """Stop the feedback listener and clean up."""
        self._server.shutdown()
        logger.info("ReaperOSC closed")

    def __repr__(self) -> str:
        return (
            f"ReaperOSC(host={self._host!r}, send={self._send_port}, "
            f"feedback={self._feedback_port}, connected={self.is_connected})"
        )
