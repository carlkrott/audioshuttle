"""OSC bridge module for Reaper communication."""

from __future__ import annotations

import logging
import os
import random
import re
import time
import io
import tempfile
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
            r"^/track/\d+/fx/\d+/openui$",
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
            r"^/action/\d+$",
            # Markers
            r"^/marker/\d+$",
            r"^/marker/\d+/name$",
            r"^/marker/\d+/time$",
            r"^/marker_id/\d+/name$",
            r"^/marker/count$",
            # Loop
            r"^/loop/start/time$",
            r"^/loop/end/time$",
            # Track automation
            r"^/track/\d+/autotrim$",
            r"^/track/\d+/autoread$",
            r"^/track/\d+/autolatch$",
            r"^/track/\d+/autotouch$",
            r"^/track/\d+/autowrite$",
            # Track sends
            r"^/track/\d+/send/\d+/volume$",
            # FX extended
            r"^/track/\d+/fx/\d+/preset\+$",
            r"^/track/\d+/fx/\d+/preset-$",
            r"^/track/\d+/fx/\d+/wetdry$",
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

    def insert_midi_pattern(
        self, role: str = "drums", track: int | None = None,
    ) -> CommandResult:
        """Generate a MIDI pattern and import it into Reaper.

        Creates a .mid file and triggers Reaper's media import action.
        Supported roles: drums, bass, chords, melody, lead.

        Args:
            role: Pattern type (drums, bass, chords, melody, lead).
            track: Optional track number to target (selects before import).
                   If None, Reaper uses the currently selected track.
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

        # Select target track BEFORE generating/importing MIDI
        # We pass the track number in the trigger file so the Lua watcher
        # can select the right track INSIDE Reaper (avoids OSC race conditions)
        target_track = track  # will be written into trigger file

        midi = MIDIFile(1)
        mtrack = 0
        tempo = 120  # Will match project tempo

        if role in ("drums", "drum", "beat", "kick"):
            channel = 9  # MIDI channel 10 (drums)
            midi.addTempo(mtrack, 0, tempo)
            for bar in range(4):
                off = bar * 4
                # Hi-hat 8th notes
                for b in range(8):
                    midi.addNote(mtrack, channel, 42, off + b * 0.5, 0.5, 100)
                # Kick on 1, 3
                midi.addNote(mtrack, channel, 36, off, 1, 120)
                midi.addNote(mtrack, channel, 36, off + 2, 1, 120)
                # Snare on 2, 4
                midi.addNote(mtrack, channel, 38, off + 1, 1, 120)
                midi.addNote(mtrack, channel, 38, off + 3, 1, 120)

        elif role in ("bass",):
            channel = 0
            midi.addTempo(mtrack, 0, tempo)
            # Simple bass line: root note on each beat
            for bar in range(4):
                off = bar * 4
                for beat in range(4):
                    midi.addNote(mtrack, channel, 36, off + beat, 0.9, 100)

        elif role in ("chords", "keys", "pad"):
            channel = 0
            midi.addTempo(mtrack, 0, tempo)
            # Simple chord hits on beats 1 and 3
            for bar in range(4):
                off = bar * 4
                for note in (60, 64, 67):  # C major
                    midi.addNote(mtrack, channel, note, off, 2, 80)
                    midi.addNote(mtrack, channel, note, off + 2, 2, 80)

        elif role in ("melody", "lead", "line"):
            channel = 0
            midi.addTempo(mtrack, 0, tempo)
            # Simple melody: ascending/descending scale pattern
            scale = [60, 62, 64, 65, 67, 69, 71, 72]  # C major scale
            for bar in range(4):
                off = bar * 4
                # Ascending on beats 1-2, descending on beats 3-4
                for i in range(4):
                    note = scale[(bar * 4 + i) % len(scale)]
                    midi.addNote(mtrack, channel, note, off + i, 0.9, 90)

        else:
            return CommandResult(
                success=False,
                address="/action",
                error=f"Unknown pattern role: {role}. Use: drums, bass, chords, melody",
            )

        # Write MIDI file — name it descriptively so if Reaper auto-names
        # the track after the file, it's at least meaningful
        buf = io.BytesIO()
        midi.writeFile(buf)
        midi_filename = f"audioshuttle_{role}.mid"
        midi_path = os.path.join(tempfile.gettempdir(), midi_filename)
        with open(midi_path, "wb") as f:
            f.write(buf.getvalue())

        # Also copy to home dir for easy access
        home_copy = os.path.expanduser(f"~/audioshuttle_{role}.mid")
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
        # Trigger format: "import" or "import:track:N:role" for targeting a specific track
        trigger_content = "import"
        if target_track is not None:
            trigger_content = f"import:track:{target_track}:{role}"
        try:
            try:
                os.remove(trigger_path)
            except OSError:
                pass
            with open(trigger_path, "w") as f:
                f.write(trigger_content)
            self._chown_to_reaper(trigger_path)
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

    # ── Key-aware pattern helpers ──────────────────────────────────────

    # Musical key → semitone offset from C
    _KEY_OFFSETS: dict[str, int] = {
        "c": 0, "c#": 1, "db": 1, "d": 2, "d#": 3, "eb": 3,
        "e": 4, "f": 5, "f#": 6, "gb": 6, "g": 7, "g#": 8,
        "ab": 8, "a": 9, "a#": 10, "bb": 10, "b": 11,
    }

    # Scale intervals (semitones from root)
    _SCALES: dict[str, list[int]] = {
        "major": [0, 2, 4, 5, 7, 9, 11],
        "minor": [0, 2, 3, 5, 7, 8, 10],
        "pentatonic": [0, 2, 4, 7, 9],
        "blues": [0, 3, 5, 6, 7, 10],
    }

    @classmethod
    def _scale_notes(cls, key: str, scale: str = "major",
                     octave: int = 4) -> list[int]:
        """Return MIDI note numbers for the given key/scale/octave."""
        root = cls._KEY_OFFSETS.get(key.lower().strip(), 0)
        intervals = cls._SCALES.get(scale.lower().strip(),
                                     cls._SCALES["major"])
        base = 12 * (octave + 1) + root  # MIDI note: octave 4 = C4 = 60
        return [base + iv for iv in intervals]

    @classmethod
    def _chord_notes(cls, key: str, scale: str = "major",
                     degree: int = 0, octave: int = 4) -> list[int]:
        """Return triad MIDI notes for a scale degree (0-based)."""
        notes = cls._scale_notes(key, scale, octave)
        # Extend scale into next octave for chord tones
        notes_extended = notes + [n + 12 for n in notes]
        return [notes_extended[degree % len(notes)],
                notes_extended[(degree + 2) % len(notes_extended)],
                notes_extended[(degree + 4) % len(notes_extended)]]

    # ── Song structure & project generation ───────────────────────────

    def _clear_track_items(self, track: int, wait: float = 1.0) -> bool:
        """Clear all items from a track via the Lua watcher.

        Args:
            track: Track number (1-based).
            wait: Max seconds to wait for completion.

        Returns:
            True if trigger was consumed (cleared), False otherwise.
        """
        trigger_path = "/tmp/audioshuttle_clear_trigger"
        try:
            os.remove(trigger_path)
        except OSError:
            pass

        with open(trigger_path, "w") as f:
            f.write(f"track:{track}")
        self._chown_to_reaper(trigger_path)

        for _ in range(int(wait / 0.1)):
            time.sleep(0.1)
            if not os.path.exists(trigger_path):
                return True
        return False

    def _insert_tracks_via_lua(self, count: int = 1, wait: float = 2.0) -> bool:
        """Insert tracks via Lua watcher (OSC /action doesn't create tracks).

        Args:
            count: Number of tracks to insert.
            wait: Max seconds to wait for trigger consumption.

        Returns:
            True if trigger was consumed, False otherwise.
        """
        trigger_path = "/tmp/audioshuttle_track_insert_trigger"
        try:
            os.remove(trigger_path)
        except OSError:
            pass

        with open(trigger_path, "w") as f:
            f.write(str(count))
        self._chown_to_reaper(trigger_path)

        for _ in range(int(wait / 0.1)):
            time.sleep(0.1)
            if not os.path.exists(trigger_path):
                return True
        return False

    def create_song_structure(
        self,
        sections: list[dict[str, str | int]],
        bpm: int | None = None,
    ) -> CommandResult:
        """Create timeline markers for song structure.

        Args:
            sections: List of {"name": "Verse 1", "bars": 16}, ...
            bpm: Optional tempo to set before creating markers.
        """
        if bpm:
            self.set_tempo(bpm)
            tempo = bpm
        else:
            # Use current tempo from state
            tempo = 120
            if hasattr(self, "state") and self.state:
                tempo = getattr(self.state, "tempo", 120) or 120

        # Build marker trigger file content
        lines = [f"tempo:{int(tempo)}"]
        bar_offset = 0
        for section in sections:
            name = str(section.get("name", "Section"))
            bars = int(section.get("bars", 8))
            lines.append(f"bar:{bar_offset}:{name}")
            bar_offset += bars

        # Write trigger file for Lua watcher
        trigger_path = "/tmp/audioshuttle_markers_trigger"
        try:
            try:
                os.remove(trigger_path)
            except OSError:
                pass
            with open(trigger_path, "w") as f:
                f.write("\n".join(lines))
            self._chown_to_reaper(trigger_path)
        except OSError as e:
            return CommandResult(
                success=False, address="/markers",
                error=f"Failed to write markers trigger: {e}",
            )

        # Wait for watcher to consume
        import time
        for _ in range(15):
            time.sleep(0.2)
            if not os.path.exists(trigger_path):
                break

        section_desc = ", ".join(
            f"{s['name']} ({s['bars']} bars)" for s in sections
        )
        self._log_command(
            "create_song_structure",
            f"Created markers: {section_desc} at {int(tempo)} BPM",
        )
        return CommandResult(
            success=True, address="/markers",
            reaper_feedback=f"Structure: {section_desc} at {int(tempo)} BPM",
        )

    def generate_project(
        self,
        sections: list[dict[str, str | int]],
        instruments: list[str],
        key: str = "C",
        scale: str = "major",
        bpm: int = 120,
    ) -> CommandResult:
        """Generate a complete project: structure markers + tracks + MIDI.

        Args:
            sections: Song sections, e.g. [{"name": "Verse", "bars": 16}, ...]
            instruments: Instruments to create, e.g. ["drums", "bass", "melody", "keys"]
            key: Musical key (C, D, E, etc.) — may include scale like "D minor"
            scale: Scale type (major, minor, pentatonic, blues)
            bpm: Tempo in BPM
        """
        try:
            from midiutil import MIDIFile
        except ImportError:
            return CommandResult(
                success=False, address="/project",
                error="midiutil not installed",
            )

        import time
        import glob as _glob

        # Parse "D minor" style key strings
        key = str(key).strip()
        for s in ("minor", "major", "pentatonic", "blues"):
            if key.lower().endswith(s):
                scale = s
                key = key[: -(len(s))].strip()
                break
        key = key.upper()
        # Keep sharps/flats: "C#" not just "C"
        if len(key) > 1 and key[1] in ("#", "B"):
            key = key[:2]
        else:
            key = key[0]

        logger.info(
            "generate_project: key=%s scale=%s bpm=%d instruments=%s sections=%s",
            key, scale, bpm, instruments,
            [(s["name"], s["bars"]) for s in sections],
        )

        # Verify Reaper is alive — best-effort check
        # (is_connected relies on OSC feedback which may not be running in MCP stdio mode)
        # We use probe() to send a UDP message and update _last_feedback_time,
        # then try refresh_state() as a second opinion.
        # If neither works, we proceed anyway — UDP commands are fire-and-forget
        # and will silently succeed once Reaper starts.
        reaper_alive = False
        try:
            self.probe(timeout=0.5)
            reaper_alive = True
        except Exception:
            pass

        if not reaper_alive and hasattr(self, "refresh_state"):
            try:
                test_state = self.refresh_state(wait=0.3)
                if test_state and test_state.track_count >= 0:
                    reaper_alive = True
            except Exception:
                pass

        if not reaper_alive:
            logger.warning(
                "generate_project: Reaper connectivity unclear — proceeding anyway. "
                "Commands will take effect once Reaper is running."
            )

        results: list[str] = []

        def _watcher_alive() -> bool:
            """Check if Lua watcher defer loop is still running."""
            try:
                alive_path = "/tmp/audioshuttle_watcher_alive"
                if not os.path.exists(alive_path):
                    return False
                mtime = os.path.getmtime(alive_path)
                if (time.time() - mtime) > 15.0:
                    # Stale — retry once after 3s
                    _time.sleep(3.0)
                    if not os.path.exists(alive_path):
                        return False
                    mtime = os.path.getmtime(alive_path)
                    if (time.time() - mtime) > 15.0:
                        return False
                # Secondary: check tick counter monotonic increase
                try:
                    with open(alive_path, "r") as f:
                        content = f.read()
                    if "tick=" in content:
                        parts = content.split("tick=")
                        if len(parts) >= 2:
                            current_tick = int(parts[1].split()[0].strip())
                            if hasattr(_watcher_alive, "_last_tick"):
                                if current_tick <= _watcher_alive._last_tick:
                                    return False
                            _watcher_alive._last_tick = current_tick
                except (OSError, ValueError):
                    pass
                return True
            except OSError:
                return False

        # Step 1: Set tempo
        self.set_tempo(bpm)
        results.append(f"Tempo: {bpm} BPM")
        time.sleep(0.3)

        # Step 2: Create song structure markers
        section_counts: dict[str, int] = {}
        expanded = []
        for sec in sections:
            base_name = str(sec["name"]).split()[0]
            section_counts.setdefault(base_name, 0)
            section_counts[base_name] += 1
            instance_name = f"{base_name} {section_counts[base_name]}"
            expanded.append({"name": instance_name, "bars": sec["bars"]})

        struct_result = self.create_song_structure(expanded, bpm=bpm)
        if struct_result.success:
            results.append(f"Structure: {', '.join(s['name'] for s in expanded)}")
            logger.info("generate_project: markers created: %s",
                        [s["name"] for s in expanded])
        else:
            logger.warning("generate_project: markers failed: %s",
                           struct_result.error)
        time.sleep(0.5)

        # Step 3: Create ALL instrument tracks FIRST (before adding any content)
        # OSC /action doesn't work for track creation — use Lua watcher instead
        num_instruments = len(instruments)
        inserted = self._insert_tracks_via_lua(count=num_instruments, wait=2.0)
        if not inserted:
            logger.warning("generate_project: track insert trigger not consumed")
        time.sleep(0.5)  # Let Reaper settle after inserts
        time.sleep(0.5)  # Let Reaper settle after all inserts

        # Get actual track count (tracks 1..N are the instruments)
        current_tracks = 0
        if hasattr(self, "state") and self.state:
            current_tracks = getattr(self.state, "track_count", 0) or 0

        scale_notes = self._scale_notes(key, scale)
        total_bars = sum(int(s["bars"]) for s in sections)
        logger.info("generate_project: scale_notes=%s total_bars=%d",
                     scale_notes, total_bars)

        for i, instrument in enumerate(instruments):
            role = instrument.lower().strip()
            logger.info("generate_project: creating %s track (%d/%d)",
                        role, i + 1, len(instruments))

            # Check watcher health before each instrument
            if not _watcher_alive():
                logger.warning(
                    "generate_project: Lua watcher died before track %d (%s) — "
                    "skipping remaining instruments",
                    i + 1, role,
                )
                results.append(f"{role.capitalize()} (SKIPPED — watcher dead)")
                continue

            # Track was already created in Step 3
            new_track = current_tracks + i + 1

            # Rename the track
            self.rename_track(new_track, role.capitalize())
            time.sleep(0.2)

            # Generate section-aware arrangement MIDI
            midi = MIDIFile(1)
            mtrack = 0
            midi.addTempo(mtrack, 0, bpm)

            self._generate_arrangement(
                midi, mtrack, role, scale_notes, expanded, bpm,
            )

            # Write MIDI file
            buf = io.BytesIO()
            midi.writeFile(buf)
            midi_path = os.path.join(
                tempfile.gettempdir(), f"audioshuttle_{role}.mid"
            )
            with open(midi_path, "wb") as f:
                f.write(buf.getvalue())
            logger.info("generate_project: wrote %s (%d bytes)",
                         midi_path, len(buf.getvalue()))

            # Clear existing items on this track before importing new MIDI
            self._clear_track_items(new_track, wait=1.0)
            time.sleep(0.5)

            # Import via watcher
            trigger_path = "/tmp/audioshuttle_import_trigger"
            try:
                os.remove(trigger_path)
            except OSError:
                pass

            trigger_content = f"import:track:{new_track}:{role}"
            with open(trigger_path, "w") as f:
                f.write(trigger_content)

            # Chown to Reaper user
            self._chown_to_reaper(trigger_path)

            # Wait for import (up to 5s — Lua processes one trigger per tick)
            imported = False
            for _ in range(40):
                time.sleep(0.2)
                if not os.path.exists(trigger_path):
                    imported = True
                    break

            if not imported:
                logger.warning("generate_project: MIDI import timeout for %s",
                               role)

            # Auto-load instrument plugin on the track
            plugin_name = self._INSTRUMENT_PLUGINS.get(role)
            if plugin_name:
                time.sleep(0.5)
                fx_result = self._fx_trigger("add", new_track, plugin_name, wait=4.0)
                if fx_result.get("success"):
                    results.append(
                        f"{role.capitalize()} (T{new_track}) + {plugin_name}"
                    )
                    logger.info(
                        "generate_project: loaded %s on track %d", plugin_name, new_track
                    )
                else:
                    results.append(f"{role.capitalize()} (T{new_track})")
                    logger.warning(
                        "generate_project: failed to load %s: %s",
                        plugin_name, fx_result.get("error"),
                    )
            else:
                results.append(f"{role.capitalize()} (T{new_track})")

            time.sleep(0.3)
            time.sleep(1.0)  # Watcher fragility buffer between instruments

        key_desc = f"{key} {scale}"
        self._log_command(
            "generate_project",
            f"Generated: {key_desc}, {bpm} BPM, "
            f"{len(instruments)} instruments, {len(expanded)} sections",
        )
        return CommandResult(
            success=True,
            address="/project",
            reaper_feedback=(
                f"Project: {key_desc}, {bpm} BPM\n"
                f"Sections: {', '.join(s['name'] for s in expanded)}\n"
                f"Tracks: {', '.join(results[2:])}"
            ),
        )

    def assess_arrangement(
        self,
        key: str,
        scale: str,
        bpm: int,
        sections: list[dict[str, str | int]],
        instruments: list[str],
    ) -> CommandResult:
        """Ask the E2B model to evaluate the musical arrangement.

        Uses the model server (Gemma E2B) to assess arrangement quality,
        suggest improvements, and describe the energy flow.

        Args:
            key: Musical key (C, D, E, etc.).
            scale: Scale type (major, minor, etc.).
            bpm: Tempo.
            sections: Song sections.
            instruments: Instrument list.
        """
        import json as _json

        assessment = None

        # Try to call model server for assessment
        if hasattr(self, "_model_server") and self._model_server:
            try:
                section_desc = ", ".join(
                    f"{s['name']} ({s['bars']} bars)" for s in sections
                )
                prompt = (
                    f"Rate this song arrangement from 1-10 for musical quality.\n"
                    f"Key: {key} {scale}, BPM: {bpm}\n"
                    f"Sections: {section_desc}\n"
                    f"Instruments: {', '.join(instruments)}\n\n"
                    f"Respond with ONLY a JSON object: "
                    f'{{"rating": N, "suggestions": ["suggestion1"], '
                    f'"energy_flow": "description of energy across sections"}}'
                )
                result = self._model_server.chat(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                )
                if result:
                    # Parse response — extract JSON from model output
                    content = ""
                    if isinstance(result, dict):
                        # Handle reasoning_content from thinking models
                        content = result.get("content", "")
                        if not content:
                            content = result.get("reasoning_content", "")
                    elif isinstance(result, str):
                        content = result
                    if content:
                        # Try to extract JSON from the response
                        try:
                            # Find JSON object in the text
                            start = content.find("{")
                            end = content.rfind("}") + 1
                            if start >= 0 and end > start:
                                assessment = _json.loads(content[start:end])
                        except (_json.JSONDecodeError, ValueError):
                            assessment = {"raw_response": content[:200]}
            except Exception as e:
                logger.warning("assess_arrangement: model call failed: %s", e)

        feedback = f"Arrangement: {key} {scale}, {bpm} BPM, {len(sections)} sections, {len(instruments)} instruments"
        if assessment:
            rating = assessment.get("rating", "?")
            suggestions = assessment.get("suggestions", [])
            energy = assessment.get("energy_flow", "")
            feedback += f"\nE2B Rating: {rating}/10"
            if energy:
                feedback += f"\nEnergy: {energy}"
            if suggestions:
                feedback += f"\nSuggestions: {'; '.join(suggestions[:3])}"
        else:
            feedback += "\n(E2B model unavailable for assessment)"

        self._log_command("assess_arrangement", feedback)
        return CommandResult(
            success=True,
            address="/assess",
            reaper_feedback=feedback,
        )

    def create_genre_project(
        self,
        genre: str = "rock",
        tempo: int | None = None,
        key: str = "C",
        scale: str = "major",
        custom_instruments: list[str] | None = None,
        custom_sections: list[dict] | None = None,
    ) -> CommandResult:
        """Create a complete genre-aware Reaper project with bus routing and FX chains.

        Pipeline: tempo → markers → tracks → buses → plugins → MIDI → FX → routing → verify

        Args:
            genre: Genre name (case-insensitive). Looks up from genre_profiles.
            tempo: Override genre default tempo. None = use genre default.
            key: Musical key (C, D, E, etc.).
            scale: Scale type (major, minor, pentatonic, blues).
            custom_instruments: Override instruments list. None = use genre default.
            custom_sections: Override section list. None = use genre default.
        """
        import time as _time
        import json as _json

        # ── Step 0: Genre resolution ─────────────────────────────────
        try:
            from audioshuttle.genre_profiles import (
                get_genre, get_family, get_fx_chain, get_tempo,
                INSTRUMENT_FAMILIES,
            )
        except ImportError:
            return CommandResult(
                success=False, address="/project/genre",
                error="genre_profiles module not available",
            )

        profile = get_genre(genre)
        resolved_tempo = get_tempo(genre, tempo)
        instruments = custom_instruments or profile["instruments"]
        sections = custom_sections or profile["sections"]

        logger.info(
            "create_genre_project: genre=%s tempo=%d instruments=%s sections=%s",
            genre, resolved_tempo, instruments,
            [(s["name"], s["bars"]) for s in sections],
        )

        results: list[str] = []
        instrument_track_map: dict[str, int] = {}
        bus_track_map: dict[str, int] = {}
        submaster_idx: int | None = None

        def _watcher_alive() -> bool:
            """Check if Lua watcher defer loop is still running."""
            try:
                alive_path = "/tmp/audioshuttle_watcher_alive"
                if not os.path.exists(alive_path):
                    return False
                mtime = os.path.getmtime(alive_path)
                if (time.time() - mtime) > 15.0:
                    # Stale — retry once after 3s
                    _time.sleep(3.0)
                    if not os.path.exists(alive_path):
                        return False
                    mtime = os.path.getmtime(alive_path)
                    if (time.time() - mtime) > 15.0:
                        return False
                # Secondary: check tick counter monotonic increase
                try:
                    with open(alive_path, "r") as f:
                        content = f.read()
                    if "tick=" in content:
                        parts = content.split("tick=")
                        if len(parts) >= 2:
                            current_tick = int(parts[1].split()[0].strip())
                            if hasattr(_watcher_alive, "_last_tick"):
                                if current_tick <= _watcher_alive._last_tick:
                                    return False
                            _watcher_alive._last_tick = current_tick
                except (OSError, ValueError):
                    pass
                return True
            except OSError:
                return False

        def _read_daw_state_json() -> dict:
            """Read and parse the DAW state JSON dump."""
            state_path = "/tmp/audioshuttle_daw_state.json"
            try:
                with open(state_path, "r") as f:
                    return _json.load(f)
            except (OSError, _json.JSONDecodeError):
                return {}

        def _verify_project_state(
            expected_tracks: int,
            expected_markers: int,
            description: str,
        ) -> bool:
            """Verify DAW state matches expectations. Returns True if OK."""
            try:
                self.refresh_state(wait=0.5)
                state_data = _read_daw_state_json()
                actual_tracks = state_data.get("track_count", 0)
                actual_markers = len(state_data.get("markers", []))
                if actual_tracks < expected_tracks:
                    logger.warning(
                        "%s: track count %d < expected %d",
                        description, actual_tracks, expected_tracks,
                    )
                    return False
                if actual_markers < expected_markers:
                    logger.warning(
                        "%s: marker count %d < expected %d",
                        description, actual_markers, expected_markers,
                    )
                    return False
                logger.info(
                    "%s: verified %d tracks, %d markers",
                    description, actual_tracks, actual_markers,
                )
                return True
            except Exception as e:
                logger.warning("%s: verification failed: %s", description, e)
                return False

        try:
            # ── Step 1: Set tempo ──────────────────────────────────────
            self.set_tempo(resolved_tempo)
            results.append(f"Tempo: {resolved_tempo} BPM")
            _time.sleep(0.5)
            self.refresh_state(wait=0.5)
            if hasattr(self, "state") and self.state:
                actual_tempo = getattr(self.state.transport, "tempo", 0)
                if abs(actual_tempo - resolved_tempo) > 1:
                    logger.warning(
                        "create_genre_project: tempo verification failed "
                        "(expected %d, got %.0f)",
                        resolved_tempo, actual_tempo,
                    )
            else:
                logger.warning("create_genre_project: could not verify tempo")

            # ── Step 2: Create markers ──────────────────────────────────
            struct_result = self.create_song_structure(sections, bpm=resolved_tempo)
            if struct_result.success:
                results.append(f"Markers: {', '.join(s['name'] for s in sections)}")
            else:
                logger.warning("create_genre_project: markers failed: %s",
                               struct_result.error)
            _time.sleep(0.5)
            _verify_project_state(0, len(sections), "Step 2: markers")

            # ── Step 3: Create instrument tracks ───────────────────────
            num_instruments = len(instruments)
            # Get current track count BEFORE insertion
            self.refresh_state(wait=0.3)
            pre_insertion_count = getattr(self.state, "track_count", 0) if hasattr(self, "state") and self.state else 0
            
            inserted = self._insert_tracks_via_lua(count=num_instruments, wait=2.0)
            if not inserted:
                logger.warning("create_genre_project: track insert trigger not consumed")
            
            # Wait for all tracks to be created (Lua watcher processes one per tick)
            expected_total = pre_insertion_count + num_instruments
            for attempt in range(30):  # up to 6s
                _time.sleep(0.2)
                self.refresh_state(wait=0.2)
                current_tracks = getattr(self.state, "track_count", 0) if hasattr(self, "state") and self.state else 0
                if current_tracks >= expected_total:
                    break
                if attempt % 5 == 4:
                    logger.info("create_genre_project: waiting for tracks... %d/%d", current_tracks, expected_total)
            
            # Update base_track_count to actual count after insertion
            base_track_count = getattr(self.state, "track_count", 0) if hasattr(self, "state") and self.state else 0
            results.append(f"Tracks: {num_instruments} instruments")

            # Populate instrument_track_map using PRE-insertion count
            # (instruments start at pre_insertion_count + 1)
            track_offset = pre_insertion_count + 1
            for i, inst in enumerate(instruments):
                instrument_track_map[inst] = track_offset + i

            # ── Step 4: Create bus tracks + Submaster ─────────────────
            # Determine which families need buses (>1 instrument in family)
            family_instrument_count: dict[str, list[str]] = {}
            for inst in instruments:
                try:
                    fam = get_family(inst)
                    family_instrument_count.setdefault(fam, []).append(inst)
                except ValueError:
                    pass

            buses_to_create = [
                fam for fam, insts in family_instrument_count.items()
                if len(insts) > 1
            ]

            # Create bus tracks
            for bus_name in buses_to_create:
                bus_track_num = base_track_count + len(bus_track_map) + 1
                inserted_bus = self._insert_tracks_via_lua(count=1, wait=1.0)
                if inserted_bus:
                    # Wait for track to actually appear
                    for _ in range(10):
                        _time.sleep(0.2)
                        self.refresh_state(wait=0.2)
                        current = getattr(self.state, "track_count", 0) if hasattr(self, "state") and self.state else 0
                        if current >= bus_track_num:
                            break
                    self.rename_track(bus_track_num, f"{bus_name.capitalize()} Bus")
                    bus_track_map[bus_name] = bus_track_num
                    logger.info("create_genre_project: created bus track %s at T%d", bus_name.capitalize(), bus_track_num)

            # Create Submaster
            sub_track_num = base_track_count + len(bus_track_map) + 1
            inserted_sub = self._insert_tracks_via_lua(count=1, wait=1.0)
            if inserted_sub:
                # Wait for track to actually appear
                for _ in range(10):
                    _time.sleep(0.2)
                    self.refresh_state(wait=0.2)
                    current = getattr(self.state, "track_count", 0) if hasattr(self, "state") and self.state else 0
                    if current >= sub_track_num:
                        break
                self.rename_track(sub_track_num, "Submaster")
                submaster_idx = sub_track_num
                logger.info("create_genre_project: created Submaster at track %d", sub_track_num)

            _time.sleep(0.5)
            expected_total = base_track_count + num_instruments + len(bus_track_map) + 1
            _verify_project_state(expected_total, len(sections), "Step 4: buses")
            results.append(f"Buses: {list(bus_track_map.keys())}")

            # ── Step 5: Rename tracks + load instrument plugins ───────
            for inst, track_idx in instrument_track_map.items():
                role = inst.lower().strip()
                self.rename_track(track_idx, role.capitalize())
                _time.sleep(0.2)

                plugin_name = self._INSTRUMENT_PLUGINS.get(role)
                if plugin_name:
                    _time.sleep(0.3)
                    fx_result = self._fx_trigger("add", track_idx, plugin_name, wait=4.0)
                    if fx_result.get("success"):
                        logger.info(
                            "create_genre_project: loaded %s on track %d",
                            plugin_name, track_idx,
                        )
                    else:
                        logger.warning(
                            "create_genre_project: failed to load %s on track %d",
                            plugin_name, track_idx,
                        )
                _time.sleep(0.2)

            # ── Step 6: Generate MIDI per section per instrument ───────
            # Reuse the inner logic from generate_project — but just the
            # _generate_arrangement call and MIDI write/import, not track creation
            from midiutil import MIDIFile

            key_parsed = str(key).strip()
            scale_parsed = scale
            for s in ("minor", "major", "pentatonic", "blues"):
                if key_parsed.lower().endswith(s):
                    scale_parsed = s
                    key_parsed = key_parsed[: -(len(s))].strip()
                    break
            key_parsed = key_parsed.upper()
            if len(key_parsed) > 1 and key_parsed[1] in ("#", "B"):
                key_parsed = key_parsed[:2]
            else:
                key_parsed = key_parsed[0] if key_parsed else "C"

            section_counts: dict[str, int] = {}
            expanded = []
            for sec in sections:
                base_name = str(sec["name"]).split()[0]
                section_counts.setdefault(base_name, 0)
                section_counts[base_name] += 1
                instance_name = f"{base_name} {section_counts[base_name]}"
                expanded.append({"name": instance_name, "bars": sec["bars"]})

            scale_notes = self._scale_notes(key_parsed, scale_parsed)

            for i, inst in enumerate(instruments):
                track_idx = instrument_track_map[inst]
                role = inst.lower().strip()

                if not _watcher_alive():
                    logger.warning(
                        "create_genre_project: watcher died before MIDI for %s",
                        role,
                    )
                    results.append(f"{role.capitalize()} (SKIPPED — watcher dead)")
                    _time.sleep(1.0)
                    continue

                # Generate MIDI
                midi = MIDIFile(1)
                mtrack = 0
                midi.addTempo(mtrack, 0, resolved_tempo)
                self._generate_arrangement(
                    midi, mtrack, role, scale_notes, expanded, resolved_tempo,
                )

                buf = io.BytesIO()
                midi.writeFile(buf)
                midi_path = os.path.join(tempfile.gettempdir(), f"audioshuttle_{role}.mid")
                with open(midi_path, "wb") as f:
                    f.write(buf.getvalue())

                # Clear existing items before import
                self._clear_track_items(track_idx, wait=1.0)
                _time.sleep(0.5)

                # Import via watcher trigger
                trigger_path = "/tmp/audioshuttle_import_trigger"
                try:
                    os.remove(trigger_path)
                except OSError:
                    pass

                trigger_content = f"import:track:{track_idx}:{role}"
                with open(trigger_path, "w") as f:
                    f.write(trigger_content)
                self._chown_to_reaper(trigger_path)

                # Wait for import (up to 8s)
                imported = False
                for _ in range(40):
                    _time.sleep(0.2)
                    if not os.path.exists(trigger_path):
                        imported = True
                        break

                results.append(
                    f"{role.capitalize()} (T{track_idx})" +
                    (" + imported" if imported else " (import timeout)")
                )
                logger.info(
                    "create_genre_project: MIDI %s for %s (track %d)",
                    "imported" if imported else "TIMEOUT", role, track_idx,
                )

                _time.sleep(1.0)  # Watcher fragility buffer

            # ── Step 7: Apply FX chains ────────────────────────────────
            for inst, track_idx in instrument_track_map.items():
                role = inst.lower().strip()
                try:
                    fx_chain = get_fx_chain(role, genre)
                except Exception:
                    fx_chain = []

                for fx_def in fx_chain:
                    plugin_name = fx_def.get("name", "")
                    if not plugin_name:
                        continue

                    # Wait for watcher if it's unresponsive (liveness gate)
                    if not _watcher_alive():
                        logger.info("create_genre_project: waiting for watcher before FX...")
                        recovered = False
                        for _ in range(5):
                            _time.sleep(3.0)
                            if _watcher_alive():
                                recovered = True
                                break
                        if not recovered:
                            logger.warning(
                                "create_genre_project: watcher still dead, skipping remaining FX on %s",
                                role,
                            )
                            break

                    result = self._fx_trigger("add", track_idx, plugin_name, wait=10.0)
                    if result.get("success"):
                        logger.info(
                            "create_genre_project: applied %s to track %d",
                            plugin_name, track_idx,
                        )
                    else:
                        logger.warning(
                            "create_genre_project: failed to apply %s to track %d",
                            plugin_name, track_idx,
                        )
                    _time.sleep(2.0)  # Per-FX settle time

                if fx_chain:
                    results.append(f"{role.capitalize()} FX: {len(fx_chain)} plugins")

            # ── Step 8: Route instruments to buses ─────────────────────
            # First pass: instrument → bus (where applicable)
            for inst, track_idx in instrument_track_map.items():
                role = inst.lower().strip()
                try:
                    fam = get_family(role)
                except ValueError:
                    fam = None

                if fam and fam in bus_track_map:
                    # Route instrument → its bus
                    bus_idx = bus_track_map[fam]
                    send_result = self.create_send(track_idx, bus_idx)
                    if send_result.success:
                        logger.info(
                            "create_genre_project: routed %s (T%d) → %s Bus (T%d)",
                            role, track_idx, fam.capitalize(), bus_idx,
                        )
                    else:
                        logger.warning(
                            "create_genre_project: send %s → %s failed",
                            role, fam,
                        )

            # Second pass: bus → Submaster
            for bus_name, bus_idx in bus_track_map.items():
                if submaster_idx is not None:
                    send_result = self.create_send(bus_idx, submaster_idx)
                    if send_result.success:
                        logger.info(
                            "create_genre_project: routed %s Bus (T%d) → Submaster (T%d)",
                            bus_name.capitalize(), bus_idx, submaster_idx,
                        )
                    else:
                        logger.warning(
                            "create_genre_project: send %s Bus → Submaster failed",
                            bus_name,
                        )

            # Third pass: instruments without a bus family → direct to Submaster
            for inst, track_idx in instrument_track_map.items():
                role = inst.lower().strip()
                try:
                    fam = get_family(role)
                except ValueError:
                    fam = None

                if not fam or fam not in bus_track_map:
                    if submaster_idx is not None:
                        send_result = self.create_send(track_idx, submaster_idx)
                        if send_result.success:
                            logger.info(
                                "create_genre_project: routed %s (T%d) → Submaster (T%d) [direct]",
                                role, track_idx, submaster_idx,
                            )

            results.append(f"Routing: {len(bus_track_map)} buses + Submaster")

            # ── Step 9: Final verification ─────────────────────────────
            expected_tracks_final = pre_insertion_count + num_instruments + len(bus_track_map) + 1
            verified = _verify_project_state(
                expected_tracks_final, len(sections), "Step 9: final verification",
            )

            section_names = ", ".join(s["name"] for s in expanded)
            track_summaries = ", ".join(r for r in results if r and not r.startswith("Tempo") and not r.startswith("Markers"))
            bus_names = ", ".join(f"{k} Bus" for k in bus_track_map.keys())
            routing_summary = (
                f"{len(instrument_track_map)} instruments, "
                f"{len(bus_track_map)} buses → Submaster"
            )

            return CommandResult(
                success=True,
                address="/project/genre",
                reaper_feedback=(
                    f"Genre: {genre}, Tempo: {resolved_tempo}, Key: {key} {scale_parsed}\n"
                    f"Sections: {section_names}\n"
                    f"Tracks: {track_summaries}\n"
                    f"Buses: {bus_names or '(none)'}\n"
                    f"Routing: {routing_summary}"
                ),
            )

        except Exception as e:
            logger.error("create_genre_project: unexpected error: %s", e)
            return CommandResult(
                success=False,
                address="/project/genre",
                error=f"Pipeline error: {e}",
                reaper_feedback="\n".join(results) if results else "",
            )

    def look_and_analyze(self, question: str = "Describe what you see") -> CommandResult:
        """Capture Reaper screenshot and analyze with E2B vision.

        Takes a screenshot of the Reaper window, sends it to E2B for
        visual analysis along with the current DAW state context.

        Args:
            question: What to ask about the screenshot.

        Returns:
            CommandResult with E2B's analysis in reaper_feedback.
        """
        from audioshuttle.thinking_stream import ThinkingStream

        ts = ThinkingStream.instance()
        ts.clear_interrupt()

        if not hasattr(self, "_model_server") or not self._model_server:
            return CommandResult(
                success=False,
                address="/look",
                error="Model server not available for vision analysis",
            )

        # Capture screenshot
        ts.emit_vision("Capturing Reaper window...")
        from audioshuttle.screen_capture import capture_reaper_window
        screenshot_path = capture_reaper_window()
        if not screenshot_path:
            ts.emit_error("Screen capture failed")
            return CommandResult(
                success=False,
                address="/look",
                error="Could not capture Reaper window",
            )

        ts.emit_vision(f"Screenshot captured ({os.path.getsize(screenshot_path)} bytes)")

        # Build DAW state context
        state_context = self._format_state_for_vision()

        # Build multimodal prompt
        from audioshuttle.model_server import ModelServer
        content_parts = [
            ModelServer.image_from_file(screenshot_path),
            ModelServer.text_part(
                f"This is a screenshot of a Reaper DAW project.\n"
                f"{state_context}\n\n"
                f"Question: {question}\n\n"
                f"Provide a clear, concise answer. Describe what you see in the "
                f"arrangement, track layout, and any issues you notice."
            ),
        ]

        messages = [{"role": "user", "content": content_parts}]

        # Stream the response
        ts.emit_vision("Analyzing screenshot with E2B vision...")
        analysis_parts = []
        for event in self._model_server.chat_multimodal_streaming(
            messages, temperature=0.3, max_tokens=4096
        ):
            if ts.is_interrupted():
                ts.emit_done("interrupt")
                break
            if event.type == "thinking_token":
                ts.emit_thinking(event.text, "vision")
            elif event.type == "content_token":
                analysis_parts.append(event.text)
                ts.emit_content(event.text, "vision")
            elif event.type == "done":
                break

        analysis = "".join(analysis_parts).strip()
        ts.emit_done("vision")

        if not analysis:
            return CommandResult(
                success=False,
                address="/look",
                error="E2B vision returned no response",
            )

        self._log_command("look_and_analyze", f"Q: {question} | A: {analysis[:200]}")
        return CommandResult(
            success=True,
            address="/look",
            reaper_feedback=analysis,
        )

    def listen_and_analyze(
        self,
        track: int | None = None,
        start_sec: float = 0,
        duration_sec: float = 30,
        question: str = "Describe the audio quality and mix",
    ) -> CommandResult:
        """Render audio and analyze with E2B via spectrogram image.

        Since llama-server doesn't support input_audio directly, this
        renders audio to WAV, converts to a spectrogram image, and
        sends it as a vision query.

        Args:
            track: Track number to solo (None = full mix).
            start_sec: Start time in seconds.
            duration_sec: Duration to render.
            question: What to ask about the audio.

        Returns:
            CommandResult with E2B's analysis.
        """
        from audioshuttle.thinking_stream import ThinkingStream

        ts = ThinkingStream.instance()
        ts.clear_interrupt()

        if not hasattr(self, "_model_server") or not self._model_server:
            return CommandResult(
                success=False,
                address="/listen",
                error="Model server not available for audio analysis",
            )

        was_soloed = None
        try:
            # Solo the target track if specified
            if track is not None:
                ts.emit_audio(f"Soloing track {track} for rendering...")
                # Save current solo state
                if hasattr(self, 'state') and self.state:
                    for t in self.state.tracks:
                        if t.track_number == track:
                            was_soloed = t.solo
                            break
                self.set_track_solo(track, True)

            # Render audio section via Lua trigger
            ts.emit_audio(f"Rendering {duration_sec}s from {start_sec}s...")
            wav_path = f"/tmp/audioshuttle_render_{track or 'mix'}.wav"
            render_ok = self._render_audio_section(start_sec, duration_sec, wav_path)

            if not render_ok or not os.path.exists(wav_path):
                ts.emit_error("Audio render failed")
                return CommandResult(
                    success=False,
                    address="/listen",
                    error="Could not render audio section",
                )

            ts.emit_audio(f"Rendered {os.path.getsize(wav_path)} bytes WAV")

            # Convert to spectrogram image
            ts.emit_audio("Generating spectrogram...")
            spectrogram_path = self._wav_to_spectrogram(wav_path)

            if not spectrogram_path:
                ts.emit_error("Spectrogram generation failed")
                return CommandResult(
                    success=False,
                    address="/listen",
                    error="Could not generate spectrogram",
                )

            # Build multimodal prompt
            state_context = self._format_state_for_vision()
            track_desc = f"track {track}" if track else "full mix"

            from audioshuttle.model_server import ModelServer
            content_parts = [
                ModelServer.image_from_file(spectrogram_path),
                ModelServer.text_part(
                    f"This is a spectrogram of the {track_desc} from a Reaper DAW project.\n"
                    f"Time range: {start_sec}s to {start_sec + duration_sec}s\n"
                    f"{state_context}\n\n"
                    f"Question: {question}\n\n"
                    f"Analyze the spectrogram: describe the frequency content, "
                    f"dynamics, any issues (clipping, mud, harsh frequencies), "
                    f"and the overall character of the sound."
                ),
            ]

            messages = [{"role": "user", "content": content_parts}]

            # Stream the response
            ts.emit_audio("Analyzing spectrogram with E2B vision...")
            analysis_parts = []
            for event in self._model_server.chat_multimodal_streaming(
                messages, temperature=0.3, max_tokens=4096
            ):
                if ts.is_interrupted():
                    ts.emit_done("interrupt")
                    break
                if event.type == "thinking_token":
                    ts.emit_thinking(event.text, "audio")
                elif event.type == "content_token":
                    analysis_parts.append(event.text)
                    ts.emit_content(event.text, "audio")
                elif event.type == "done":
                    break

            analysis = "".join(analysis_parts).strip()
            ts.emit_done("audio")

            if not analysis:
                return CommandResult(
                    success=False,
                    address="/listen",
                    error="E2B returned no audio analysis",
                )

            self._log_command("listen_and_analyze", f"Track={track} | Q: {question} | A: {analysis[:200]}")
            return CommandResult(
                success=True,
                address="/listen",
                reaper_feedback=analysis,
            )

        finally:
            # Restore solo state
            if track is not None and was_soloed is not None:
                try:
                    self.set_track_solo(track, was_soloed)
                except Exception:
                    pass

    def _render_audio_section(
        self, start_sec: float, duration_sec: float, output_path: str,
    ) -> bool:
        """Render a section of audio to WAV via Lua trigger.

        Uses Reaper's render functionality triggered through the Lua watcher.
        """
        # Write render trigger for the Lua watcher
        trigger_content = f"render:{start_sec:.2f}:{duration_sec:.2f}:{output_path}"
        return self._lua_trigger("render_trigger", trigger_content, timeout=30.0)

    @staticmethod
    def _wav_to_spectrogram(wav_path: str) -> str | None:
        """Convert a WAV file to a spectrogram PNG using ffmpeg + sox."""
        import subprocess

        output_path = wav_path.rsplit(".", 1)[0] + "_spectrogram.png"

        # Try sox first (best spectrograms)
        try:
            result = subprocess.run(
                ["sox", wav_path, "-n", "spectrogram",
                 "-o", output_path, "-x", "1280", "-y", "720"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(output_path):
                return output_path
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # Fallback: use ffmpeg to generate a spectrogram
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path,
                 "-lavfi", "showspectrumpic=s=1280x720:legend=1",
                 "-frames:v", "1", output_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(output_path):
                return output_path
        except FileNotFoundError:
            logger.error("Neither sox nor ffmpeg available for spectrogram")
        except Exception as e:
            logger.error("Spectrogram generation failed: %s", e)

        return None

    def _format_state_for_vision(self) -> str:
        """Format current DAW state for inclusion in vision prompts."""
        parts = []
        if hasattr(self, 'state') and self.state:
            s = self.state
            if s.tracks:
                track_desc = ", ".join(
                    f"T{t.track_number}={t.name or 'unnamed'}"
                    for t in s.tracks[:10]
                )
                parts.append(f"Tracks ({len(s.tracks)}): {track_desc}")
            if s.transport.tempo > 0:
                parts.append(f"Tempo: {s.transport.tempo:.0f} BPM")
            if s.transport.playing:
                parts.append(f"Playing at {s.transport.position_seconds:.1f}s")
        return "\n".join(parts) if parts else "No DAW state available"

    def _generate_arrangement(
        self,
        midi: "MIDIFile",
        mtrack: int,
        role: str,
        scale_notes: list[int],
        sections: list[dict[str, str | int]],
        bpm: int,
    ) -> None:
        """Generate section-aware MIDI arrangement for one instrument.

        Iterates over song sections, looks up density/velocity profiles,
        and generates section-appropriate patterns placed at correct beat offsets.

        Args:
            midi: MIDIFile object to write into.
            mtrack: Track index within the MIDI file.
            role: Instrument role (drums, bass, melody, etc.).
            scale_notes: MIDI note numbers for the current key/scale.
            sections: Song sections with {"name": str, "bars": int, "start_bar": int}.
            bpm: Tempo.
        """
        bar_offset = 0
        for section in sections:
            name = str(section.get("name", "Verse"))
            bars = int(section.get("bars", 8))
            section_type = self._normalize_section_name(name)
            profile = self._SECTION_PROFILES.get(section_type, self._SECTION_PROFILES["verse"])

            # Seed for reproducible but section-unique variation
            random.seed(hash(f"{role}:{name}:{bars}"))

            # Check if this role is active in this section
            norm_role = self._normalize_role(role)
            if norm_role not in profile["active_roles"] and role.lower() not in profile["active_roles"]:
                bar_offset += bars
                continue  # Instrument rests in this section

            density = profile["density"]
            vel_lo, vel_hi = profile["vel_range"]

            self._generate_section_pattern(
                midi, mtrack, role, scale_notes,
                start_bar=bar_offset, bars=bars,
                density=density, vel_range=(vel_lo, vel_hi),
                section_type=section_type, bpm=bpm,
            )
            bar_offset += bars

    def _generate_section_pattern(
        self,
        midi: "MIDIFile",
        mtrack: int,
        role: str,
        scale_notes: list[int],
        start_bar: int,
        bars: int,
        density: float,
        vel_range: tuple[int, int],
        section_type: str,
        bpm: int,
    ) -> None:
        """Generate MIDI for one instrument in one section.

        Args:
            midi: MIDIFile to write into.
            mtrack: MIDI track index.
            role: Instrument role.
            scale_notes: Scale degrees as MIDI note numbers.
            start_bar: Bar offset where this section begins.
            bars: Number of bars in this section.
            density: 0.0-1.0 note density/activity.
            vel_range: (min_vel, max_vel) for dynamics.
            section_type: Normalized section name (verse, chorus, etc.).
            bpm: Tempo.
        """
        norm_role = self._normalize_role(role)
        vel_mid = (vel_range[0] + vel_range[1]) // 2

        # ── Drums ──────────────────────────────────────────────────
        if norm_role in ("drums", "drum", "beat", "kick", "snare", "rhythm"):
            ch = 9  # Channel 10 (drums)
            for bar in range(bars):
                off = (start_bar + bar) * 4

                # Kick on 1, (3 in chorus/high density)
                midi.addNote(mtrack, ch, 36, off, 1, vel_mid)
                if density >= 0.8:
                    midi.addNote(mtrack, ch, 36, off + 2, 1, int(vel_mid * 0.95))

                # Snare on 2 and 4
                if density >= 0.3:
                    midi.addNote(mtrack, ch, 38, off + 1, 1, vel_mid)
                if density >= 0.4:
                    midi.addNote(mtrack, ch, 38, off + 3, 1, int(vel_mid * 0.9))

                # Hi-hat subdivision scales with density
                if density >= 0.8:  # 16th notes
                    for b in range(16):
                        vel = int(vel_mid * (0.5 if b % 2 == 0 else 0.35))
                        midi.addNote(mtrack, ch, 42, off + b * 0.25, 0.25, vel)
                elif density >= 0.5:  # 8th notes
                    for b in range(8):
                        vel = int(vel_mid * 0.5)
                        midi.addNote(mtrack, ch, 42, off + b * 0.5, 0.5, vel)
                else:  # Quarter notes
                    for b in range(4):
                        vel = int(vel_mid * 0.4)
                        midi.addNote(mtrack, ch, 42, off + b, 1, vel)

                # Ghost snare in chorus
                if section_type == "chorus" and density >= 0.9:
                    midi.addNote(mtrack, ch, 38, off + 2.75, 0.25, int(vel_mid * 0.35))

        # ── Bass ───────────────────────────────────────────────────
        elif norm_role == "bass":
            ch = 0
            root = scale_notes[0] - 12  # One octave down
            fifth = scale_notes[4] - 12 if len(scale_notes) > 4 else root + 7
            octave_up = root + 12
            for bar in range(bars):
                off = (start_bar + bar) * 4
                if density >= 0.7:
                    # Walking bass: root, approach, fifth, approach
                    midi.addNote(mtrack, ch, root, off, 0.9, vel_mid)
                    approach = root + (scale_notes[1] - scale_notes[0]) if len(scale_notes) > 1 else root + 2
                    midi.addNote(mtrack, ch, approach - 12, off + 1, 0.9, int(vel_mid * 0.85))
                    midi.addNote(mtrack, ch, fifth, off + 2, 0.9, vel_mid)
                    back = root + (scale_notes[-2] - scale_notes[-1]) if len(scale_notes) > 2 else root - 1
                    midi.addNote(mtrack, ch, back - 12, off + 3, 0.9, int(vel_mid * 0.8))
                elif density >= 0.4:
                    # Root-fifth: beats 1-2 root, 3-4 fifth
                    midi.addNote(mtrack, ch, root, off, 1.8, vel_mid)
                    midi.addNote(mtrack, ch, root, off + 1, 1.8, int(vel_mid * 0.9))
                    midi.addNote(mtrack, ch, fifth, off + 2, 1.8, vel_mid)
                    midi.addNote(mtrack, ch, fifth, off + 3, 1.8, int(vel_mid * 0.9))
                else:
                    # Sparse: whole note root only
                    midi.addNote(mtrack, ch, root, off, 3.8, int(vel_mid * 0.8))

        # ── Melody / Lead ──────────────────────────────────────────
        elif norm_role in ("melody", "lead", "line"):
            ch = 0
            for bar in range(bars):
                off = (start_bar + bar) * 4
                for beat in range(4):
                    # Rest probability inversely proportional to density
                    if random.random() > density * 0.8 + 0.2:
                        continue
                    # Stepwise motion with occasional leaps at high density
                    if density >= 0.7 and random.random() < 0.3:
                        idx = (bar * 4 + beat + random.randint(1, 3)) % len(scale_notes)
                    else:
                        idx = (bar * 4 + beat) % len(scale_notes)
                    note = scale_notes[idx]
                    # Wider octave range in chorus
                    if section_type == "chorus" and random.random() < 0.2:
                        note += 12
                    dur = 0.9 if density >= 0.5 else 1.8
                    midi.addNote(mtrack, ch, note, off + beat, dur, vel_mid)

        # ── Keys / Chords ──────────────────────────────────────────
        elif norm_role in ("chords", "keys", "key"):
            ch = 0
            # Scale-appropriate chord degrees
            if len(scale_notes) >= 5:
                chord_degrees = [0, 3, 4]  # I, IV, V
                if density >= 0.7:
                    chord_degrees = [0, 1, 3, 4, 5]  # I, ii, IV, V, vi
            else:
                chord_degrees = [0, 2, 3]
            for bar in range(bars):
                off = (start_bar + bar) * 4
                deg = chord_degrees[bar % len(chord_degrees)]
                triad = self._chord_notes(
                    ["C", "C#", "D", "D#", "E", "F",
                     "F#", "G", "G#", "A", "A#", "B"][
                        (scale_notes[0] - 60) % 12
                    ],
                    "major", degree=deg,
                )
                if density >= 0.8:
                    # Arpeggiated: play chord tones individually
                    for i, note in enumerate(triad):
                        midi.addNote(mtrack, ch, note, off + i * 0.5, 0.45, int(vel_mid * 0.7))
                        midi.addNote(mtrack, ch, note, off + 2 + i * 0.5, 0.45, int(vel_mid * 0.65))
                else:
                    # Block chords: hold for whole bar
                    for note in triad:
                        midi.addNote(mtrack, ch, note, off, 3.8, int(vel_mid * 0.75))

        # ── Pad ────────────────────────────────────────────────────
        elif norm_role == "pad":
            ch = 0
            root = scale_notes[0]
            third = scale_notes[2] if len(scale_notes) > 2 else root + 4
            fifth = scale_notes[4] if len(scale_notes) > 4 else root + 7
            chord = [root, third, fifth]
            # Add seventh at high density
            if density >= 0.7 and len(scale_notes) > 6:
                seventh = scale_notes[6]
                chord.append(seventh)
            for bar in range(bars):
                off = (start_bar + bar) * 4
                for note in chord:
                    midi.addNote(mtrack, ch, note, off, 3.9, int(vel_mid * 0.6))

        # ── Strings ────────────────────────────────────────────────
        elif norm_role in ("strings", "string"):
            ch = 0
            root = scale_notes[0]
            third = scale_notes[2] if len(scale_notes) > 2 else root + 4
            fifth = scale_notes[4] if len(scale_notes) > 4 else root + 7
            for bar in range(bars):
                off = (start_bar + bar) * 4
                for note in [root, third, fifth]:
                    midi.addNote(mtrack, ch, note, off, 3.8, int(vel_mid * 0.65))
                # Counter-melody at high density
                if density >= 0.7:
                    for beat in range(0, 4, 2):
                        idx = (bar * 2 + beat // 2) % len(scale_notes)
                        midi.addNote(mtrack, ch, scale_notes[idx] + 12,
                                     off + beat, 1.8, int(vel_mid * 0.5))

        # ── Arp ────────────────────────────────────────────────────
        elif norm_role == "arp":
            ch = 0
            # Speed scales with density: 8ths at 0.5, 16ths at 0.8+
            subdivision = 0.5 if density < 0.7 else 0.25
            notes_per_bar = int(4.0 / subdivision)
            for bar in range(bars):
                off = (start_bar + bar) * 4
                for i in range(notes_per_bar):
                    idx = (bar * notes_per_bar + i) % len(scale_notes)
                    note = scale_notes[idx]
                    # Octave alternation for interest
                    if i % 2 == 1:
                        note += 12
                    midi.addNote(mtrack, ch, note,
                                 off + i * subdivision,
                                 subdivision * 0.9,
                                 int(vel_mid * 0.7))

        # ── FX Riser ───────────────────────────────────────────────
        elif norm_role in ("fx", "riser"):
            ch = 0
            # Ascending pitch sweep over the section
            start_note = scale_notes[0] - 12
            end_note = scale_notes[0] + 24
            total_beats = bars * 4
            step = max(1, total_beats // 16)
            for i in range(0, total_beats, step):
                progress = i / total_beats
                note = int(start_note + (end_note - start_note) * progress)
                vel = int(vel_range[0] + (vel_range[1] - vel_range[0]) * progress)
                midi.addNote(mtrack, ch, note,
                             (start_bar * 4) + i, step * 0.9, vel)

        # ── Sub Kick ───────────────────────────────────────────────
        elif norm_role == "sub":
            ch = 0
            root = scale_notes[0] - 24  # Two octaves down
            for bar in range(bars):
                off = (start_bar + bar) * 4
                if density >= 0.6:
                    # Four on the floor
                    for beat in range(4):
                        midi.addNote(mtrack, ch, root, off + beat, 0.9, vel_mid)
                else:
                    # Just beat 1
                    midi.addNote(mtrack, ch, root, off, 0.9, int(vel_mid * 0.8))

        # ── Generic fallback ───────────────────────────────────────
        else:
            ch = 0
            for bar in range(bars):
                off = (start_bar + bar) * 4
                for beat in range(4):
                    if random.random() > density:
                        continue
                    idx = (bar * 4 + beat) % len(scale_notes)
                    midi.addNote(mtrack, ch, scale_notes[idx],
                                 off + beat, 0.9, vel_mid)

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
            self._chown_to_reaper(color_path)
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

    # ── Navigation ────────────────────────────────────────────────

    def goto_marker(self, marker: int) -> CommandResult:
        """Jump to a marker by number."""
        if marker < 1:
            return CommandResult(
                success=False, address="/marker", error=f"Marker must be >= 1, got {marker}"
            )
        return self.send_command(f"/marker/{marker}")

    def set_marker_name(self, marker: int, name: str) -> CommandResult:
        """Name a marker by its ID number."""
        if marker < 1:
            return CommandResult(
                success=False, address="/marker_id/name", error=f"Marker must be >= 1, got {marker}"
            )
        return self.send_command(f"/marker_id/{marker}/name", name)

    def set_loop_points(self, start: float, end: float) -> CommandResult:
        """Set loop start and end points in seconds."""
        if start < 0 or end <= start:
            return CommandResult(
                success=False, address="/loop",
                error=f"Invalid loop range: {start} to {end}",
            )
        self.send_command("/loop/start/time", start)
        return self.send_command("/loop/end/time", end)

    def rewind(self) -> CommandResult:
        """Hold rewind (sends toggle)."""
        return self.send_command("/rewind", 1.0)

    def forward(self) -> CommandResult:
        """Hold fast forward (sends toggle)."""
        return self.send_command("/forward", 1.0)

    # ── Track monitoring ──────────────────────────────────────────

    def set_track_monitor(self, track: int, mode: int) -> CommandResult:
        """Set track monitoring mode.

        Uses Reaper actions to explicitly set the mode (more reliable than OSC).
        Selects the track first, then triggers the monitor mode action.

        Args:
            track: Track number (>= 1).
            mode: 0=off, 1=normal, 2=not when playing (tape style).
        """
        if track < 1:
            return CommandResult(
                success=False, address="/action",
                error=f"Track must be >= 1, got {track}",
            )
        action_map = {0: 40492, 1: 40493, 2: 40494}
        action_id = action_map.get(mode)
        if action_id is None:
            return CommandResult(
                success=False, address="/action",
                error=f"Mode must be 0, 1, or 2, got {mode}",
            )
        # Select the track first, then trigger the action
        self.select_track(track)
        return self.send_command(f"/action/{action_id}")

    # ── Track sends ───────────────────────────────────────────────

    def set_track_send_volume(self, track: int, send: int, volume: float) -> CommandResult:
        """Set a track send volume.

        Args:
            track: Track number (>= 1).
            send: Send index (>= 0).
            volume: Volume 0.0-1.0.
        """
        if track < 1:
            return CommandResult(
                success=False, address="/track/send/volume",
                error=f"Track must be >= 1, got {track}",
            )
        volume = max(0.0, min(1.0, volume))
        return self.send_command(f"/track/{track}/send/{send}/volume", volume)

    # ── Track automation ──────────────────────────────────────────

    def set_track_auto_mode(self, track: int, mode: str) -> CommandResult:
        """Set track automation mode.

        Uses Reaper actions (not OSC toggles) to explicitly set the mode.
        Selects the track first, then triggers the automation mode action.

        Args:
            track: Track number (>= 1).
            mode: One of 'trim', 'read', 'latch', 'touch', 'write'.
        """
        if track < 1:
            return CommandResult(
                success=False, address="/action",
                error=f"Track must be >= 1, got {track}",
            )
        action_map = {
            "trim": 40452,
            "read": 40453,
            "latch": 40454,
            "touch": 40455,
            "write": 40456,
        }
        action_id = action_map.get(mode.lower())
        if not action_id:
            return CommandResult(
                success=False, address="/action",
                error=f"Unknown auto mode: {mode}. Use: trim, read, latch, touch, write",
            )
        # Select the track first, then trigger the action
        self.select_track(track)
        return self.send_command(f"/action/{action_id}")

    # ── FX extended ───────────────────────────────────────────────

    def fx_next_preset(self, track: int, fx: int) -> CommandResult:
        """Cycle to next FX preset."""
        if track < 1 or fx < 0:
            return CommandResult(
                success=False, address="/fx/preset+",
                error=f"Invalid track={track} or fx={fx}",
            )
        return self.send_command(f"/track/{track}/fx/{fx}/preset+")

    def fx_prev_preset(self, track: int, fx: int) -> CommandResult:
        """Cycle to previous FX preset."""
        if track < 1 or fx < 0:
            return CommandResult(
                success=False, address="/fx/preset-",
                error=f"Invalid track={track} or fx={fx}",
            )
        return self.send_command(f"/track/{track}/fx/{fx}/preset-")

    def fx_set_wetdry(self, track: int, fx: int, value: float) -> CommandResult:
        """Set FX wet/dry mix.

        Args:
            track: Track number (>= 1).
            fx: FX index (>= 0).
            value: Wet/dry 0.0 (dry) to 1.0 (wet).
        """
        if track < 1 or fx < 0:
            return CommandResult(
                success=False, address="/fx/wetdry",
                error=f"Invalid track={track} or fx={fx}",
            )
        value = max(0.0, min(1.0, value))
        return self.send_command(f"/track/{track}/fx/{fx}/wetdry", value)

    # ── Plugin/FX management via Lua watcher ────────────────────────

    # Instrument role → default plugin mapping
    _INSTRUMENT_PLUGINS: dict[str, str] = {
        "drums": "ReaSynDr",
        "drum": "ReaSynDr",
        "beat": "ReaSynDr",
        "kick": "ReaSynDr",
        "snare": "ReaSynDr",
        "rhythm": "ReaSynDr",
        "bass": "ReaSynth",
        "melody": "ReaSynth",
        "lead": "ReaSynth",
        "line": "ReaSynth",
        "chords": "ReaSynth",
        "keys": "ReaSynth",
        "key": "ReaSynth",
        "pad": "ReaSynth",
        "synth": "ReaSynth",
        "strings": "ReaSynth",
        "string": "ReaSynth",
        "arp": "ReaSynth",
        "fx": "ReaSynth",
        "riser": "ReaSynth",
        "sub": "ReaSynth",
    }

    # All roles that can appear in arrangements
    _ALL_ROLES = frozenset({
        "drums", "drum", "beat", "kick", "snare", "rhythm",
        "bass", "melody", "lead", "line",
        "chords", "keys", "key", "pad", "synth",
        "strings", "string", "arp", "fx", "riser", "sub",
    })

    # Section density profiles — density controls note density & subdivision
    # vel_range = (min_velocity, max_velocity) for MIDI notes
    # active_roles = which instrument roles play in this section
    _SECTION_PROFILES: dict[str, dict] = {
        "intro": {
            "density": 0.3,
            "vel_range": (50, 80),
            "active_roles": {"drums", "drum", "beat", "kick", "keys", "key", "pad"},
        },
        "verse": {
            "density": 0.6,
            "vel_range": (60, 100),
            "active_roles": {
                "drums", "drum", "beat", "kick", "snare", "rhythm",
                "bass", "keys", "key", "melody", "lead",
            },
        },
        "chorus": {
            "density": 1.0,
            "vel_range": (80, 127),
            "active_roles": _ALL_ROLES,
        },
        "bridge": {
            "density": 0.5,
            "vel_range": (50, 90),
            "active_roles": {"keys", "key", "pad", "strings", "string", "arp"},
        },
        "breakdown": {
            "density": 0.2,
            "vel_range": (40, 70),
            "active_roles": {"keys", "key", "pad"},
        },
        "buildup": {
            "density": 0.7,
            "vel_range": (60, 120),
            "active_roles": _ALL_ROLES,
        },
        "drop": {
            "density": 1.0,
            "vel_range": (90, 127),
            "active_roles": _ALL_ROLES,
        },
        "outro": {
            "density": 0.4,
            "vel_range": (40, 80),
            "active_roles": {"drums", "drum", "beat", "kick", "bass", "keys", "key", "pad"},
        },
    }

    @staticmethod
    def _normalize_section_name(name: str) -> str:
        """Normalize section name for profile lookup.
        'Verse 1' → 'verse', 'CHORUS' → 'chorus', 'Pre-Chorus' → 'prechorus'
        """
        normalized = name.lower().strip()
        # Remove trailing numbers: 'verse 1' → 'verse'
        normalized = re.sub(r'\s+\d+$', '', normalized)
        # Remove spaces and hyphens: 'pre chorus' → 'prechorus'
        normalized = normalized.replace(" ", "").replace("-", "")
        return normalized

    @staticmethod
    def _normalize_role(role: str) -> str:
        """Normalize instrument role for matching.
        'Lead Synth' → 'lead', 'FX Riser' → 'fx', 'Snare+Hat' → 'snare'
        """
        return role.lower().strip().split()[0].split("+")[0].split("-")[0]

    def _fx_trigger(
        self, command: str, track: int, *args: str, wait: float = 1.0,
    ) -> dict:
        """Send an FX command to the Lua watcher and return the JSON result.

        Args:
            command: FX command (add, remove, set_preset, bypass, set_param, list).
            track: Track number (1-based).
            *args: Additional command arguments.
            wait: Max seconds to wait for result.
        """
        parts = [command, str(track)] + list(args)
        content = ":".join(parts)
        result = self._lua_trigger(
            "/tmp/audioshuttle_fx_trigger",
            "/tmp/audioshuttle_fx_result.json",
            content,
            wait=wait,
        )
        return result or {"success": False, "error": "timeout waiting for FX result"}

    def load_plugin(
        self, track: int, plugin_name: str,
    ) -> CommandResult:
        """Load a plugin/FX onto a track.

        Supports VST, VSTi, and JSFX plugins by name.
        Examples: "ReaSynth", "ReaSynDr", "ReaEQ", "JS: Delay", "ReaSamplOmatic5000"

        Args:
            track: Track number (>= 1).
            plugin_name: Plugin name as Reaper knows it.
        """
        if track < 1:
            return CommandResult(
                success=False, address="/fx/add",
                error=f"Invalid track={track} (must be >= 1)",
            )

        result = self._fx_trigger("add", track, plugin_name)

        if result.get("success"):
            self._log_command(
                "load_plugin",
                f"Loaded '{result.get('name', plugin_name)}' on track {track} (FX#{result.get('fx_index', '?')})",
            )
            return CommandResult(
                success=True,
                address="/fx/add",
                reaper_feedback=(
                    f"Loaded {result.get('name', plugin_name)} "
                    f"on track {track} as FX#{result.get('fx_index', '?')}"
                ),
            )
        else:
            return CommandResult(
                success=False, address="/fx/add",
                error=result.get("error", f"Failed to load {plugin_name}"),
            )

    def remove_plugin(self, track: int, fx: int) -> CommandResult:
        """Remove a plugin/FX from a track.

        Args:
            track: Track number (>= 1).
            fx: FX index on the track (0-based).
        """
        if track < 1 or fx < 0:
            return CommandResult(
                success=False, address="/fx/remove",
                error=f"Invalid track={track} or fx={fx}",
            )

        result = self._fx_trigger("remove", track, str(fx))

        if result.get("success"):
            return CommandResult(
                success=True, address="/fx/remove",
                reaper_feedback=f"Removed FX#{fx} from track {track}",
            )
        else:
            return CommandResult(
                success=False, address="/fx/remove",
                error=result.get("error", "Failed to remove FX"),
            )

    def set_plugin_preset(
        self, track: int, fx: int, preset_name: str,
    ) -> CommandResult:
        """Set a plugin's preset by name.

        Args:
            track: Track number (>= 1).
            fx: FX index (0-based).
            preset_name: Preset name to apply.
        """
        if track < 1 or fx < 0:
            return CommandResult(
                success=False, address="/fx/preset",
                error=f"Invalid track={track} or fx={fx}",
            )

        result = self._fx_trigger("set_preset", track, str(fx), preset_name)

        if result.get("success"):
            return CommandResult(
                success=True, address="/fx/preset",
                reaper_feedback=f"Set preset '{preset_name}' on track {track} FX#{fx}",
            )
        else:
            return CommandResult(
                success=False, address="/fx/preset",
                error=result.get("error", f"Failed to set preset '{preset_name}'"),
            )

    def list_track_fx(self, track: int) -> CommandResult:
        """List all FX/plugins on a track.

        Args:
            track: Track number (>= 1).
        """
        if track < 1:
            return CommandResult(
                success=False, address="/fx/list",
                error=f"Invalid track={track}",
            )

        result = self._fx_trigger("list", track)

        if result.get("success"):
            fx_list = result.get("fx", [])
            if not fx_list:
                return CommandResult(
                    success=True, address="/fx/list",
                    reaper_feedback=f"Track {track}: no FX loaded",
                )
            lines = [f"Track {track} FX:"]
            for fx in fx_list:
                instr_tag = " [INSTRUMENT]" if fx.get("is_instrument") else ""
                status = "ON" if fx.get("enabled") else "BYPASSED"
                preset = fx.get("preset", "")
                preset_str = f" (preset: {preset})" if preset else ""
                lines.append(
                    f"  FX#{fx['index']}: {fx['name']}{instr_tag} [{status}]{preset_str}"
                )
            return CommandResult(
                success=True, address="/fx/list",
                reaper_feedback="\n".join(lines),
            )
        else:
            return CommandResult(
                success=False, address="/fx/list",
                error=result.get("error", "Failed to list FX"),
            )

    def list_available_plugins(self) -> CommandResult:
        """List all available plugins that can be loaded.

        Queries the Lua watcher's curated plugin database.
        """
        import json as _json

        trigger_path = "/tmp/audioshuttle_fx_list_request"
        result_path = "/tmp/audioshuttle_fx_list.json"

        try:
            os.remove(result_path)
        except OSError:
            pass

        # Write trigger
        try:
            os.remove(trigger_path)
        except OSError:
            pass
        with open(trigger_path, "w") as f:
            f.write("list")

        self._chown_to_reaper(trigger_path)

        # Wait for result
        import time
        for _ in range(20):
            time.sleep(0.1)
            if os.path.exists(result_path):
                try:
                    with open(result_path) as rf:
                        result = _json.load(rf)
                    os.remove(result_path)
                    break
                except (OSError, ValueError):
                    result = None
        else:
            result = None

        if not result:
            return CommandResult(
                success=False, address="/fx/list_all",
                error="Timeout listing available plugins",
            )

        plugins = result.get("plugins", [])

        # Group by category
        categories: dict[str, list[str]] = {}
        for p in plugins:
            cat = p.get("category", "other")
            categories.setdefault(cat, []).append(
                f"{p['name']} ({p['type']})"
            )

        lines = ["Available plugins:"]
        for cat in sorted(categories):
            lines.append(f"  {cat.upper()}:")
            for name in sorted(categories[cat]):
                lines.append(f"    • {name}")

        return CommandResult(
            success=True, address="/fx/list_all",
            reaper_feedback="\n".join(lines),
        )

    def _chown_to_reaper(self, path: str) -> None:
        """Chown a file to the Reaper user (found via /proc).

        Skips sudo wrappers (UID 0) to find the actual Reaper process
        running as the target user (e.g. korphaus).
        """
        import glob as _glob
        for pid_dir in _glob.glob("/proc/[0-9]*"):
            try:
                with open(f"{pid_dir}/cmdline", "rb") as pf:
                    cmdline = pf.read()
                    if b"REAPER/reaper" in cmdline and b"sudo" not in cmdline:
                        stat = os.stat(f"{pid_dir}")
                        # Skip root (sudo wrapper) — we want the actual user
                        if stat.st_uid == 0:
                            continue
                        os.chown(path, stat.st_uid, stat.st_gid)
                        break
            except (OSError, PermissionError):
                continue

    def _lua_trigger(
        self, trigger_path: str, result_path: str,
        content: str, wait: float = 1.0,
    ) -> dict | None:
        """Generic Lua watcher trigger: write content, wait for JSON result.

        Uses remove-then-create to avoid PermissionError on tmpfs when
        the trigger file is owned by a different user (Reaper/korphaus)
        and Python runs as root.
        """
        import json as _json
        import time

        try:
            os.remove(result_path)
        except OSError:
            pass

        # Remove-then-create avoids tmpfs PermissionError when
        # file was previously chowned to Reaper's user
        try:
            os.remove(trigger_path)
        except OSError:
            pass

        with open(trigger_path, "w") as f:
            f.write(content)

        self._chown_to_reaper(trigger_path)

        for _ in range(int(wait * 10)):
            time.sleep(0.1)
            if os.path.exists(result_path):
                try:
                    with open(result_path) as rf:
                        result = _json.load(rf)
                    os.remove(result_path)
                    return result
                except (OSError, ValueError):
                    pass

        return None

    # ── Plugin parameter discovery ──────────────────────────────────

    def get_plugin_params(
        self, track: int, fx: int,
    ) -> CommandResult:
        """Dump all parameters for a plugin, with names, values, and ranges.

        This is the key tool that makes set_fx_param useful — the model can
        discover what parameters exist and what to set.

        Args:
            track: Track number (>= 1).
            fx: FX index on the track (0-based).
        """
        if track < 1 or fx < 0:
            return CommandResult(
                success=False, address="/fx/params",
                error=f"Invalid track={track} or fx={fx}",
            )

        result = self._lua_trigger(
            "/tmp/audioshuttle_fx_params_request",
            "/tmp/audioshuttle_fx_params.json",
            f"{track}:{fx}",
        )

        if not result:
            return CommandResult(
                success=False, address="/fx/params",
                error="Timeout querying plugin parameters",
            )

        if result.get("success"):
            params = result.get("params", [])
            fx_name = result.get("fx_name", "Unknown")
            lines = [f"{fx_name} (Track {track} FX#{fx}) — {len(params)} params:"]
            for p in params:
                display = p.get("display", "")
                display_str = f" [{display}]" if display else ""
                lines.append(
                    f"  #{p['i']}: {p['name']} = {p['value']:.3f}{display_str}"
                )
            return CommandResult(
                success=True, address="/fx/params",
                reaper_feedback="\n".join(lines),
            )
        else:
            return CommandResult(
                success=False, address="/fx/params",
                error=result.get("error", "Failed to get params"),
            )

    # ── Track routing (sends) ───────────────────────────────────────

    def create_send(
        self, source_track: int, dest_track: int,
    ) -> CommandResult:
        """Create an audio send from one track to another.

        Args:
            source_track: Source track number (>= 1).
            dest_track: Destination track number (>= 1).
        """
        if source_track < 1 or dest_track < 1:
            return CommandResult(
                success=False, address="/routing/send",
                error=f"Invalid source={source_track} or dest={dest_track}",
            )

        result = self._lua_trigger(
            "/tmp/audioshuttle_routing_trigger",
            "/tmp/audioshuttle_routing_result.json",
            f"create_send:{source_track}:{dest_track}",
        )

        if result and result.get("success"):
            return CommandResult(
                success=True, address="/routing/send",
                reaper_feedback=f"Send created: Track {source_track} → Track {dest_track}",
            )
        return CommandResult(
            success=False, address="/routing/send",
            error=(result or {}).get("error", "Failed to create send"),
        )

    def delete_send(
        self, track: int, send: int,
    ) -> CommandResult:
        """Remove an audio send from a track.

        Args:
            track: Track number (>= 1).
            send: Send index (0-based).
        """
        if track < 1 or send < 0:
            return CommandResult(
                success=False, address="/routing/send",
                error=f"Invalid track={track} or send={send}",
            )

        result = self._lua_trigger(
            "/tmp/audioshuttle_routing_trigger",
            "/tmp/audioshuttle_routing_result.json",
            f"delete_send:{track}:{send}",
        )

        if result and result.get("success"):
            return CommandResult(
                success=True, address="/routing/send",
                reaper_feedback=f"Removed send #{send} from track {track}",
            )
        return CommandResult(
            success=False, address="/routing/send",
            error=(result or {}).get("error", "Failed to delete send"),
        )

    # ── Track input source ──────────────────────────────────────────

    def set_track_input(
        self, track: int, input_code: int,
    ) -> CommandResult:
        """Set the recording input source for a track.

        Args:
            track: Track number (>= 1).
            input_code: Input source code. -1=None, 0=MIDI,
                        0x100+ch=Mono audio, 0x600+ch=Stereo audio.
                        Common: 256=input 1 mono, 6400=input 1 stereo.
        """
        if track < 1:
            return CommandResult(
                success=False, address="/track/input",
                error=f"Invalid track={track}",
            )

        result = self._lua_trigger(
            "/tmp/audioshuttle_input_trigger",
            "/tmp/audioshuttle_input_result.json",
            f"{track}:{input_code}",
        )

        if result and result.get("success"):
            return CommandResult(
                success=True, address="/track/input",
                reaper_feedback=f"Track {track} input set to {input_code}",
            )
        return CommandResult(
            success=False, address="/track/input",
            error=(result or {}).get("error", "Failed to set input"),
        )

    # ── Quick OSC wins ──────────────────────────────────────────────

    def select_track(self, track: int) -> CommandResult:
        """Select a track in Reaper (deselects others).

        Args:
            track: Track number (>= 1).
        """
        if track < 1:
            return CommandResult(
                success=False, address="/track/select",
                error=f"Invalid track={track}",
            )
        return self.send_command(f"/track/{track}/select", 1)

    def open_fx_ui(self, track: int, fx: int) -> CommandResult:
        """Open a plugin's UI window.

        Args:
            track: Track number (>= 1).
            fx: FX index (0-based).
        """
        if track < 1 or fx < 0:
            return CommandResult(
                success=False, address="/fx/openui",
                error=f"Invalid track={track} or fx={fx}",
            )
        return self.send_command(f"/track/{track}/fx/{fx}/openui", 1)

    def set_playrate(self, rate: float) -> CommandResult:
        """Set the playback rate (0.25 to 4.0).

        Different from tempo — changes pitch too.

        Args:
            rate: Playback rate (1.0 = normal).
        """
        rate = max(0.25, min(4.0, rate))
        return self.send_command("/playrate/raw", rate)

    def solo_reset(self) -> CommandResult:
        """Unsolo all tracks."""
        return self.send_command("/action/40740")  # Unsolo all tracks

    def move_track(self, track: int, new_position: int) -> CommandResult:
        """Move a track to a new position in the track list.

        Args:
            track: Track number to move (>= 1).
            new_position: Target position (>= 1).
        """
        if track < 1 or new_position < 1:
            return CommandResult(
                success=False, address="/track/move",
                error=f"Invalid track={track} or position={new_position}",
            )

        result = self._lua_trigger(
            "/tmp/audioshuttle_move_trigger",
            "/tmp/audioshuttle_move_result.json",
            f"{track}:{new_position}",
        )

        if result and result.get("success"):
            return CommandResult(
                success=True, address="/track/move",
                reaper_feedback=f"Moved track {track} to position {new_position}",
            )
        return CommandResult(
            success=False, address="/track/move",
            error=(result or {}).get("error", "Failed to move track"),
        )

    # ── Undo/Redo via actions ─────────────────────────────────────

    def undo(self) -> CommandResult:
        """Undo last action (Reaper action 40029)."""
        return self.send_command("/action/40029")

    def redo(self) -> CommandResult:
        """Redo last action (Reaper action 40100)."""
        return self.send_command("/action/40100")

    # ── State discovery ─────────────────────────────────────────

    def refresh_state(self, wait: float = 0.5) -> DAWState:
        """Get current DAW state via the Lua watcher's state dump.

        Writes a trigger file that the __startup.lua watcher detects.
        The watcher dumps full track state (names, volumes, colors, etc.)
        to /tmp/audioshuttle_daw_state.json, which we read back.

        Args:
            wait: Seconds to wait for the state dump (default 0.5s).
        """
        import json
        import glob

        state_path = "/tmp/audioshuttle_daw_state.json"
        trigger_path = "/tmp/audioshuttle_state_request"

        # Remove stale state file
        try:
            os.remove(state_path)
        except OSError:
            pass

        # Write trigger file for the watcher
        try:
            try:
                os.remove(trigger_path)
            except OSError:
                pass
            with open(trigger_path, "w") as f:
                f.write("dump")
            self._chown_to_reaper(trigger_path)
        except OSError as e:
            logger.warning("Failed to write state trigger: %s", e)
            return self._state

        # Poll for the state dump (watcher checks every ~200ms)
        import subprocess
        for _ in range(int(wait / 0.05)):
            if os.path.exists(state_path):
                break
            time.sleep(0.05)

        # Read and parse the state dump
        try:
            with open(state_path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read watcher state dump: %s", e)
            return self._state

        # Update internal state from dump
        self._state.track_count = data.get("track_count", 0)

        # Update tracks
        existing = {t.track_number: t for t in self._state.tracks}
        self._state.tracks.clear()
        for td in data.get("tracks", []):
            num = td["number"]
            track = existing.get(num) or TrackState(track_number=num)
            track.name = td.get("name", "")
            track.volume = td.get("volume", 0.75)
            track.pan = td.get("pan", 0.0)
            track.mute = td.get("mute", False)
            track.solo = td.get("solo", False)
            self._state.tracks.append(track)
        self._state.tracks.sort(key=lambda t: t.track_number)

        # Update transport
        transport = data.get("transport", {})
        self._state.transport.playing = transport.get("playing", False)
        self._state.transport.recording = transport.get("recording", False)
        self._state.transport.position_seconds = transport.get("position", 0.0)
        self._state.transport.tempo = transport.get("tempo", 120.0)

        logger.info(
            "State refreshed from watcher: %d tracks, tempo=%.0f",
            len(self._state.tracks), self._state.transport.tempo,
        )
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
