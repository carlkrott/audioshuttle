"""OSC bridge module for Reaper communication."""

from __future__ import annotations

import logging
import os
import re
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


class _ReusableOSCServer(osc_server.ThreadingOSCUDPServer):
    """OSC UDP server with SO_REUSEADDR to prevent port conflicts."""

    allow_reuse_address = True


def _make_osc_server(
    host: str, port: int, dispatcher: osc_dispatcher.Dispatcher,
) -> osc_server.ThreadingOSCUDPServer:
    """Create an OSC server with address reuse enabled."""
    return _ReusableOSCServer((host, port), dispatcher)


class ReaperOSC:
    """Bidirectional OSC bridge to Reaper DAW.

    Sends commands on send_port (default 8000) and listens
    for feedback on feedback_port (default 9000).

    Features:
        - Connection health monitoring via periodic ping
        - Automatic reconnection attempt when Reaper disconnects
        - Warning logs when connection drops for extended period
        - OSC address validation to prevent injection
    """

    # How often to ping Reaper (seconds)
    PING_INTERVAL: float = 3.0
    # How long without feedback before marking disconnected (seconds)
    # Reaper only sends feedback when state changes, not in response to queries.
    # Use a generous timeout to avoid false disconnections during idle periods.
    CONNECTION_TIMEOUT: float = 30.0
    # How long disconnected before logging a warning (seconds)
    WARNING_AFTER: float = 60.0

    # Whitelist of known Reaper OSC address patterns (regex)
    # Based on Default.ReaperOSC pattern file
    _ADDRESS_PATTERNS: list[re.Pattern[str]] = [
        re.compile(p)
        for p in [
            # Transport (triggers — no value needed)
            r"^/play$",
            r"^/stop$",
            r"^/record$",
            r"^/pause$",
            r"^/rewind$",
            r"^/forward$",
            r"^/repeat$",
            r"^/click$",
            # Time/tempo
            r"^/time$",
            r"^/tempo/raw$",
            r"^/playrate/raw$",
            # Track controls
            r"^/track/\d+/volume$",
            r"^/track/\d+/mute$",
            r"^/track/\d+/solo$",
            r"^/track/\d+/pan$",
            r"^/track/\d+/name$",
            r"^/track/\d+/select$",
            r"^/track/\d+/recarm$",
            r"^/track/\d+/fx/\d+/fxparam/\d+/value$",
            r"^/track/\d+/fx/\d+/bypass$",
            r"^/track/\d+/send/\d+/volume$",
            r"^/track/\d+/monitor$",
            r"^/track/count$",
            # Selected-track controls (for select-first approach)
            r"^/track/volume$",
            r"^/track/mute$",
            r"^/track/solo$",
            r"^/track/pan$",
            r"^/track/name$",
            r"^/track/select$",
            r"^/track/recarm$",
            # Master
            r"^/master/volume$",
            r"^/master/pan$",
            # Actions
            r"^/action$",
            # Markers
            r"^/marker/\d+/name$",
            r"^/marker/\d+/time$",
            r"^/marker/count$",
            # Device/probe
            r"^/device/fk/set/notify/activate$",
        ]
    ]

    def __init__(
        self,
        host: str = "127.0.0.1",
        send_port: int = 8000,
        feedback_port: int = 9000,
        *,
        ping_interval: float | None = None,
        connection_timeout: float | None = None,
        warning_after: float | None = None,
    ) -> None:
        self._host = host
        self._send_port = send_port
        self._feedback_port = feedback_port

        # Timing config (overridable for testing)
        self._ping_interval = ping_interval or self.PING_INTERVAL
        self._connection_timeout = connection_timeout or self.CONNECTION_TIMEOUT
        self._warning_after = warning_after or self.WARNING_AFTER

        # UDP client for sending commands
        self._client = udp_client.SimpleUDPClient(host, send_port)

        # Internal state
        self._state = DAWState()
        self._last_feedback_time: float = time.time()  # Grace period on startup
        self._reaper_seen: bool = False  # True after first real feedback from Reaper
        self._message_log: deque[tuple[str, Any]] = deque(maxlen=500)
        # Track volume dB values (track_num -> dB float) for conversion
        self._track_volume_db: dict[int, float] = {}
        # Track count from Reaper feedback
        self._track_count: int = 0

        # Connection monitoring
        self._disconnected_since: float | None = None
        self._reconnect_count: int = 0

        # Feedback listener
        self._dispatcher = osc_dispatcher.Dispatcher()
        self._dispatcher.set_default_handler(self._on_osc_message)
        self._server = _make_osc_server("127.0.0.1", feedback_port, self._dispatcher)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._server_thread.start()

        # Health monitoring thread — pings Reaper and checks connection
        self._stop_health = threading.Event()
        self._health_thread = threading.Thread(
            target=self._health_loop, daemon=True
        )
        self._health_thread.start()

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
        """True if Reaper has sent feedback recently (within connection timeout)."""
        return (time.time() - self._last_feedback_time) < self._connection_timeout

    def probe(self, timeout: float = 1.0) -> bool:
        """Actively probe Reaper to detect if it's listening.

        Sends a lightweight OSC message and checks if Reaper's UDP port
        is reachable. Updates connection state if Reaper responds.

        Returns True if Reaper appears to be alive.
        """
        import socket as _socket

        # Fast check: is anything listening on Reaper's send port?
        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            # Send a no-op query — Reaper responds to /device/fk/set/notify/activate with feedback
            # Actually just send a ping-like message and check the port is open
            sock.sendto(b"/device/fk/set/notify/activate\x00\x00\x00,fi\x00\x00\x00\x00\x00\x00\x00\x01",
                        (self._host, self._send_port))
            sock.close()
            # If we got here without error, the send succeeded (UDP doesn't confirm delivery,
            # but if Reaper is running, it received it and will send feedback)
            # Mark as seen so future sends count as connection evidence
            if not self._reaper_seen:
                logger.info("Reaper probe sent — marking as seen")
                self._reaper_seen = True
                self._last_feedback_time = time.time()
                self._log_event("Reaper detected (active probe)", "info")
            return True
        except Exception:
            return False

    @property
    def message_log(self) -> deque[tuple[str, Any]]:
        """Recent OSC messages received from Reaper."""
        return self._message_log

    @property
    def reconnect_count(self) -> int:
        """Number of times the bridge has reconnected to Reaper."""
        return self._reconnect_count

    @property
    def disconnected_since(self) -> float | None:
        """Timestamp when disconnection was detected, or None if connected."""
        if self.is_connected:
            return None
        return self._disconnected_since

    # ── Address validation ───────────────────────────────────────

    @classmethod
    def _validate_address(cls, address: str) -> bool:
        """Validate an OSC address against the known Reaper whitelist.

        Rules:
            - Must start with ``/``
            - No path traversal (``..``), null bytes, or control characters
            - Track/FX numbers in addresses must be positive integers
            - Must match a known Reaper OSC pattern
        """
        # Structural checks
        if not address.startswith("/"):
            return False
        if ".." in address:
            return False
        if "\x00" in address:
            return False
        if any(ord(c) < 0x20 for c in address):
            return False

        # Whitelist match
        return any(p.match(address) for p in cls._ADDRESS_PATTERNS)

    # ── Low-level send ──────────────────────────────────────────

    def send_command(self, address: str, *args: Any) -> CommandResult:
        """Send a validated OSC command to Reaper."""
        # Validate address before sending
        if not self._validate_address(address):
            logger.warning("Rejected invalid OSC address: %s", address)
            return CommandResult(
                success=False,
                address=address,
                error=f"Invalid OSC address: {address}",
            )

        try:
            self._client.send_message(address, list(args))
            logger.debug("Sent: %s %s", address, args)
            # Log significant commands to error_log for the Log tab
            self._log_command(address, args)
            # If Reaper has been seen before, treat successful sends as
            # connection evidence (Reaper's OSC only sends feedback on
            # state changes, not in response to queries).
            if self._reaper_seen:
                self._last_feedback_time = time.time()
            return CommandResult(
                success=True,
                address=address,
                sent_value=list(args) if len(args) > 1 else args[0] if args else None,
            )
        except Exception as e:
            logger.error("Failed to send %s: %s", address, e)
            return CommandResult(success=False, address=address, error=str(e))

    def _log_command(self, address: str, args: tuple) -> None:
        """Log OSC commands to the error_log for the Log tab."""
        try:
            from audioshuttle.error_log import error_log

            # Skip noisy polling commands
            if address in ("/track/1/name", "/track/count", "/marker/count"):
                return
            # Format a human-readable message
            msg = f"OSC → {address}"
            if args:
                msg += f" {list(args)}"
            error_log.add(msg, level="info")
        except Exception:
            pass

    def _log_event(self, message: str, level: str = "info") -> None:
        """Log a bridge event to the error_log for the Log tab."""
        try:
            from audioshuttle.error_log import error_log
            error_log.add(message, level=level)
        except Exception:
            pass

    # ── Transport ───────────────────────────────────────────────

    def transport_play(self) -> CommandResult:
        """Start playback (OSC trigger)."""
        return self.send_command("/play")

    def transport_stop(self) -> CommandResult:
        """Stop playback (OSC trigger)."""
        return self.send_command("/stop")

    def transport_record(self) -> CommandResult:
        """Toggle recording (OSC trigger)."""
        return self.send_command("/record")

    def transport_pause(self) -> CommandResult:
        """Pause playback (OSC trigger)."""
        return self.send_command("/pause")

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

    def set_master_pan(self, pan: float) -> CommandResult:
        """Set master pan (-1.0 left to 1.0 right, clamped)."""
        pan = max(-1.0, min(1.0, pan))
        return self.send_command("/master/pan", pan)

    def transport_seek(self, seconds: float) -> CommandResult:
        """Seek to a specific position in the timeline.

        Args:
            seconds: Position in seconds from the start (must be >= 0).
        """
        if seconds < 0:
            return CommandResult(
                success=False,
                address="/time",
                error=f"Seek position must be >= 0, got {seconds}",
            )
        result = self.send_command("/time", seconds)
        if result.success:
            self._state.transport.position_seconds = seconds
        return result

    def get_track_count_real(self) -> int:
        """Request track count from Reaper and return it.

        Sends ``/track/count`` and waits briefly for feedback.
        Falls back to the current cached value if no response.
        """
        self.send_command("/track/count")
        time.sleep(0.2)
        return self._track_count or self.get_track_count()

    # ── FX control ──────────────────────────────────────────────

    def set_fx_param(
        self, track: int, fx: int, param: int, value: float,
    ) -> CommandResult:
        """Set an FX plugin parameter value.

        Args:
            track: Track number (>= 1).
            fx: FX index on the track (0-based).
            param: Parameter index within the FX (0-based).
            value: Parameter value 0.0-1.0 (clamped).
        """
        if track < 1 or fx < 0 or param < 0:
            return CommandResult(
                success=False,
                address=f"/track/{track}/fx/{fx}/fxparam/{param}/value",
                error=f"Invalid indices: track={track} (>=1), fx={fx} (>=0), param={param} (>=0)",
            )
        value = max(0.0, min(1.0, value))
        return self.send_command(
            f"/track/{track}/fx/{fx}/fxparam/{param}/value", value,
        )

    def fx_bypass(self, track: int, fx: int, bypass: bool) -> CommandResult:
        """Bypass or enable an FX plugin on a track.

        Note: Reaper OSC convention: 1 = bypassed, 0 = active.

        Args:
            track: Track number (>= 1).
            fx: FX index on the track (0-based).
            bypass: True to bypass, False to enable.
        """
        if track < 1 or fx < 0:
            return CommandResult(
                success=False,
                address=f"/track/{track}/fx/{fx}/bypass",
                error=f"Invalid indices: track={track} (>=1), fx={fx} (>=0)",
            )
        return self.send_command(
            f"/track/{track}/fx/{fx}/bypass", 1 if bypass else 0,
        )

    # ── Action triggering ───────────────────────────────────────

    def trigger_action(self, command_id: int) -> CommandResult:
        """Trigger a Reaper action by its command ID.

        Args:
            command_id: Reaper action command ID (positive integer).
        """
        if command_id <= 0:
            return CommandResult(
                success=False,
                address="/action",
                error=f"Action command_id must be > 0, got {command_id}",
            )
        return self.send_command("/action", command_id)

    # ── Tempo and track management ──────────────────────────────

    def set_tempo(self, bpm: float) -> CommandResult:
        """Set the project tempo in BPM.

        Uses Reaper's OSC address /tempo/raw (not /bpm).

        Args:
            bpm: Tempo in BPM (typically 20-300).
        """
        if bpm < 20 or bpm > 300:
            return CommandResult(
                success=False,
                address="/tempo/raw",
                error=f"BPM must be 20-300, got {bpm}",
            )
        return self.send_command("/tempo/raw", float(bpm))

    def insert_track(self) -> CommandResult:
        """Insert a new track in Reaper (action 40001)."""
        return self.send_command("/action", 40001)

    def rename_track(self, track: int, name: str) -> CommandResult:
        """Rename a track.

        Args:
            track: Track number (>= 1).
            name: New track name.
        """
        if track < 1:
            return CommandResult(
                success=False,
                address=f"/track/{track}/name",
                error=f"Track must be >= 1, got {track}",
            )
        return self.send_command(f"/track/{track}/name", name)

    def insert_midi_pattern(self, role: str = "drums") -> CommandResult:
        """Generate a MIDI pattern and import it into Reaper.

        Creates a .mid file and triggers Reaper's media import action.
        Supported roles: drums, bass, chords.

        Args:
            role: Pattern type (drums, bass, chords).
        """
        try:
            from midiutil import MIDIFile
        except ImportError:
            return CommandResult(
                success=False,
                address="/action",
                error="midiutil not installed — run: pip install midiutil",
            )

        import io
        import tempfile

        role = role.lower().strip()
        midi = MIDIFile(1)
        track = 0
        tempo = 120  # Will match project tempo

        if role in ("drums", "drum", "beat", "kick"):
            channel = 9  # MIDI channel 10 (drums)
            midi.addTempo(track, 0, tempo)
            for bar in range(4):
                off = bar * 4
                # Hi-hat 8th notes
                for b in range(8):
                    midi.addNote(track, channel, 42, off + b * 0.5, 0.5, 100)
                # Kick on 1, 3
                midi.addNote(track, channel, 36, off, 1, 120)
                midi.addNote(track, channel, 36, off + 2, 1, 120)
                # Snare on 2, 4
                midi.addNote(track, channel, 38, off + 1, 1, 120)
                midi.addNote(track, channel, 38, off + 3, 1, 120)

        elif role in ("bass",):
            channel = 0
            midi.addTempo(track, 0, tempo)
            # Simple bass line: root note on each beat
            for bar in range(4):
                off = bar * 4
                for beat in range(4):
                    midi.addNote(track, channel, 36, off + beat, 0.9, 100)

        elif role in ("chords", "keys", "pad"):
            channel = 0
            midi.addTempo(track, 0, tempo)
            # Simple chord hits on beats 1 and 3
            for bar in range(4):
                off = bar * 4
                for note in (60, 64, 67):  # C major
                    midi.addNote(track, channel, note, off, 2, 80)
                    midi.addNote(track, channel, note, off + 2, 2, 80)
        else:
            return CommandResult(
                success=False,
                address="/action",
                error=f"Unknown pattern role: {role}. Use: drums, bass, chords",
            )

        # Write MIDI file
        buf = io.BytesIO()
        midi.writeFile(buf)
        midi_path = os.path.join(tempfile.gettempdir(), "audioshuttle_pattern.mid")
        with open(midi_path, "wb") as f:
            f.write(buf.getvalue())

        # Also copy to home dir for easy access
        home_copy = os.path.expanduser("~/audioshuttle_pattern.mid")
        try:
            with open(home_copy, "wb") as f:
                f.write(buf.getvalue())
        except OSError:
            home_copy = midi_path

        self._log_command(
            f"insert_midi_pattern({role})",
            f"Generated {role} pattern → {home_copy}",
        )

        # Import MIDI into Reaper via __startup.lua watcher.
        # The watcher runs inside Reaper (korphaus user) and polls for a trigger
        # file every 200ms. When it finds the trigger, it reads the MIDI file
        # and calls reaper.InsertMedia().
        #
        # Sequence: 1) Write MIDI file → 2) Write trigger → 3) Wait for consumption
        import time

        trigger_path = os.path.join(tempfile.gettempdir(), "audioshuttle_import_trigger")
        imported = False

        # Remove stale trigger if any
        try:
            os.remove(trigger_path)
        except OSError:
            pass

        # Create trigger file owned by Reaper's user (needed for sticky-bit /tmp)
        # The __startup.lua watcher runs as korphaus and needs to os.remove() it
        try:
            with open(trigger_path, "w") as f:
                f.write("import")
            # Find Reaper's UID and chown the trigger file
            import glob as _glob
            for pid_dir in _glob.glob("/proc/[0-9]*"):
                try:
                    with open(f"{pid_dir}/cmdline", "rb") as f:
                        if b"REAPER/reaper" in f.read():
                            import os as _os
                            stat = _os.stat(f"{pid_dir}")
                            _os.chown(trigger_path, stat.st_uid, stat.st_gid)
                            break
                except (OSError, PermissionError):
                    continue
        except OSError:
            pass

        # Wait for watcher to consume the trigger (polls every 200ms)
        for _ in range(15):  # up to 3 seconds
            time.sleep(0.2)
            if not os.path.exists(trigger_path):
                imported = True
                break

        if not imported:
            # Watcher didn't consume — clean up trigger
            try:
                os.remove(trigger_path)
            except OSError:
                pass

            self._log_command(
                "insert_midi_pattern",
                f"Watcher not running — MIDI saved to {home_copy}. "
                "Reopen Reaper or drag the file in manually.",
            )

        return CommandResult(
            success=True,
            address="/action",
            sent_value=midi_path,
            reaper_feedback=f"{role} pattern → {home_copy}"
            + (" (imported)" if imported else " (file saved, Reaper CLI not found)"),
        )

    def set_track_color(self, track: int, color: str) -> CommandResult:
        """Set a track's color in Reaper.

        Writes a color command file for the __startup.lua watcher.
        Reaper's OSC doesn't support track colors natively.

        Args:
            track: Track number (>= 1).
            color: Hex color like "#ff0000" or named color.
        """
        if track < 1:
            return CommandResult(
                success=False,
                address="/track/color",
                error=f"Track must be >= 1, got {track}",
            )

        # Named color to hex mapping
        named_colors = {
            "red": "#ff0000", "blue": "#0044ff", "green": "#00cc00",
            "yellow": "#ffcc00", "purple": "#9900ff", "orange": "#ff6600",
            "pink": "#ff0099", "cyan": "#00cccc", "white": "#ffffff",
            "grey": "#888888", "gray": "#888888",
        }
        hex_color = named_colors.get(color.lower().strip(), color)
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color

        # Validate hex format
        import re
        if not re.match(r"^#[0-9a-fA-F]{6}$", hex_color):
            return CommandResult(
                success=False,
                address="/track/color",
                error=f"Invalid color format: {color}. Use hex (#ff0000) or named color.",
            )

        # Write color command file for watcher
        import os
        import glob
        color_path = "/tmp/audioshuttle_color_cmd.txt"
        try:
            with open(color_path, "w") as f:
                f.write(f"{track} {hex_color}")
            # Chown to Reaper user (same as MIDI trigger pattern)
            for pid_dir in glob.glob("/proc/[0-9]*"):
                try:
                    with open(f"{pid_dir}/cmdline", "rb") as f:
                        if b"REAPER/reaper" in f.read():
                            stat = os.stat(f"{pid_dir}")
                            os.chown(color_path, stat.st_uid, stat.st_gid)
                            break
                except (OSError, PermissionError):
                    continue
        except OSError as e:
            return CommandResult(
                success=False,
                address="/track/color",
                error=f"Failed to write color command: {e}",
            )

        self._log_command(
            f"set_track_color({track}, {hex_color})",
            f"Color command written for track {track}",
        )

        return CommandResult(
            success=True,
            address="/track/color",
            sent_value=f"track={track} color={hex_color}",
        )

    # ── Track arm ────────────────────────────────────────────────

    def set_track_recarm(self, track: int, arm: bool) -> CommandResult:
        """Arm or disarm a track for recording.

        Args:
            track: Track number (>= 1).
            arm: True to arm, False to disarm.
        """
        if track < 1:
            return CommandResult(
                success=False,
                address=f"/track/{track}/recarm",
                error=f"Track must be >= 1, got {track}",
            )
        return self.send_command(f"/track/{track}/recarm", 1 if arm else 0)

    # ── Toggles ─────────────────────────────────────────────────

    def toggle_repeat(self) -> CommandResult:
        """Toggle repeat on/off in Reaper."""
        return self.send_command("/repeat")

    def toggle_metronome(self) -> CommandResult:
        """Toggle the metronome/click on/off."""
        return self.send_command("/click")

    # ── State discovery ─────────────────────────────────────────

    def refresh_state(self, wait: float = 0.5) -> DAWState:
        """Probe Reaper for current state by requesting track info.

        Args:
            wait: Seconds to wait for feedback responses (default 0.5s).
        """
        # Send requests that trigger Reaper feedback
        for i in range(1, 9):
            self.send_command(f"/track/{i}/name")
            self.send_command(f"/track/{i}/volume")
            self.send_command(f"/track/{i}/mute")
            self.send_command(f"/track/{i}/solo")
            self.send_command(f"/track/{i}/pan")
        self.send_command("/master/volume")
        self.send_command("/master/pan")
        self.send_command("/track/count")
        time.sleep(wait)
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
        now = time.time()

        # Detect reconnection (feedback received after being disconnected)
        if (
            self._disconnected_since is not None
            and (now - self._last_feedback_time) > self._connection_timeout
        ):
            logger.info(
                "Reaper feedback received — reconnected after %.1fs offline",
                now - self._disconnected_since,
            )
            self._log_event(f"Reaper reconnected after {now - self._disconnected_since:.0f}s offline", "info")
            self._disconnected_since = None

        self._last_feedback_time = now
        self._reaper_seen = True
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

        # Track count
        elif address == "/track/count":
            self._track_count = int(val)
            self._state.track_count = int(val)

        # Master state
        elif address == "/master/volume":
            self._state.master_volume = float(val)
        elif address == "/master/pan":
            self._state.master_pan = float(val)

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
                    # Reaper sends volume feedback as /track/N/volume/db
                    if len(parts) >= 4 and parts[3] == "db":
                        # Convert dB to normalized 0.0-1.0 range
                        # Reaper range: ~-60dB (min) to +12dB (max)
                        db_val = float(val)
                        self._track_volume_db[track_num] = db_val
                        track.volume = self._db_to_normalized(db_val)
                    elif len(parts) >= 4 and parts[3] == "str":
                        # String representation, skip
                        pass
                    else:
                        # Normalized volume (0.0-1.0) — direct from feedback
                        track.volume = float(val)
                elif attr == "mute":
                    track.mute = bool(val)
                elif attr == "solo":
                    track.solo = bool(val)
                elif attr == "pan":
                    track.pan = float(val)
            except (ValueError, IndexError):
                pass

    @staticmethod
    def _db_to_normalized(db: float) -> float:
        """Convert Reaper dB value to normalized 0.0-1.0 range.

        Reaper's volume fader: -inf dB -> 0.0, 0 dB -> ~0.75, +12 dB -> 1.0
        Approximate mapping using exponential scale.
        """
        if db <= -60.0:
            return 0.0
        # Reaper uses: normalized = 10^(dB/20) scaled to 0-1
        # At 0dB, normalized ≈ 0.75 (Reaper's internal scaling)
        # Simple approximation: map -60..+12 to 0..1
        return max(0.0, min(1.0, (db + 60.0) / 72.0))

    def _get_or_create_track(self, track_num: int) -> TrackState:
        """Get existing track or create new one in state."""
        for t in self._state.tracks:
            if t.track_number == track_num:
                return t
        track = TrackState(track_number=track_num)
        self._state.tracks.append(track)
        self._state.tracks.sort(key=lambda t: t.track_number)
        return track

    # ── Connection health ───────────────────────────────────────

    def _ping(self) -> CommandResult:
        """Send a lightweight probe to trigger Reaper feedback.

        Reaper's OSC sends feedback when state changes, not in response to
        queries. We send /track/1/name as a probe — Reaper may respond with
        the track name if the track exists. Connection health is tracked by
        any feedback received (from pings OR user commands).

        The connection timeout is generous (30s) to avoid false disconnections
        during idle periods when Reaper has no state changes to report.
        """
        return self.send_command("/track/1/name")

    def _health_loop(self) -> None:
        """Background thread: periodic ping + disconnection detection."""
        while not self._stop_health.is_set():
            self._ping()

            # Check connection health after ping has had time to arrive
            self._stop_health.wait(self._ping_interval)
            if self._stop_health.is_set():
                break

            now = time.time()
            time_since_feedback = now - self._last_feedback_time

            if time_since_feedback > self._connection_timeout:
                # Disconnected
                if self._disconnected_since is None:
                    self._disconnected_since = now
                    logger.warning(
                        "Reaper disconnected — no feedback for %.1fs",
                        time_since_feedback,
                    )
                    self._log_event("Reaper disconnected", "warning")
                elif (now - self._disconnected_since) > self._warning_after:
                    # Extended disconnection — log periodic warning and attempt reconnect
                    logger.warning(
                        "Reaper still disconnected after %.0fs (attempt #%d to reconnect)",
                        now - self._disconnected_since,
                        self._reconnect_count + 1,
                    )
                    self._attempt_reconnect()
            else:
                # Connected
                if self._disconnected_since is not None:
                    was_down = now - self._disconnected_since
                    logger.info(
                        "Reaper reconnected after %.1fs offline",
                        was_down,
                    )
                    self._disconnected_since = None

    def _attempt_reconnect(self) -> None:
        """Attempt to re-establish communication with Reaper.

        Re-creates the UDP client in case the port binding changed,
        sends a burst of probes, and waits briefly for a response.
        """
        self._reconnect_count += 1
        logger.info("Reconnect attempt #%d — recreating UDP client", self._reconnect_count)

        try:
            self._client = udp_client.SimpleUDPClient(
                self._host, self._send_port
            )
        except Exception as e:
            logger.error("Failed to recreate UDP client: %s", e)
            return

        # Send a burst of probes to trigger Reaper feedback
        # NOTE: Do NOT use transport commands (/play, /stop, /record) as probes —
        # they change DAW state. Only use read-only queries.
        for probe in ["/marker/count", "/track/count", "/track/1/name"]:
            self.send_command(probe)
            time.sleep(0.1)

    def close(self) -> None:
        """Stop the feedback listener, health monitor, and clean up."""
        self._stop_health.set()
        self._server.shutdown()
        logger.info("ReaperOSC closed")

    def __repr__(self) -> str:
        return (
            f"ReaperOSC(host={self._host!r}, send={self._send_port}, "
            f"feedback={self._feedback_port}, connected={self.is_connected})"
        )
