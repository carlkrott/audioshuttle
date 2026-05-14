"""AudioShuttle Thinking Overlay — floating text window streaming model thoughts.

Always-on-top transparent window in the bottom-right corner showing:
- Model reasoning (thinking tokens) in dim text
- Response content in bright text
- Tool calls and results in color-coded text
- Vision/audio analysis status

Thread-safe via Qt signals (same pattern as VoiceOverlay).
Auto-fades after inactivity.
"""

from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont

from audioshuttle.thinking_stream import ThinkingEvent, ThinkingStream

# ── Visual constants ──────────────────────────────────────────

WINDOW_WIDTH = 420
WINDOW_HEIGHT = 220
MAX_LINES = 12
FADE_DELAY_MS = 5000  # Auto-fade after 5s of inactivity
FADE_SPEED = 0.05

# Colors by event type
TYPE_COLORS = {
    "thinking_token": "#888888",  # dim gray
    "content_token": "#00FF41",   # bright green
    "tool_call": "#FFD700",       # gold
    "tool_result": "#00BFFF",     # deep sky blue
    "error": "#FF4444",           # red
    "done": "#AAAAAA",            # light gray
    "thinking_start": "#666699",  # muted purple
}

SOURCE_ICONS = {
    "e2b": "🧠",
    "vision": "👁",
    "audio": "🎵",
    "stt": "🎙",
    "translator": "🔧",
    "executor": "⚙",
    "interrupt": "⛔",
}


class _ThinkingSignals(QObject):
    """Signal proxy for thread-safe overlay control."""
    append_text = pyqtSignal(str, str)  # text, color
    clear_text = pyqtSignal()
    fade_out = pyqtSignal()
    show_window = pyqtSignal()


class ThinkingOverlay(QWidget):
    """Floating text overlay streaming E2B's thought process.

    Shows a scrolling text window with color-coded events from
    the ThinkingStream. Auto-appears when events arrive, auto-fades
    after inactivity.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._opacity = 0.95
        self._lines: list[tuple[str, str]] = []  # (text, color)

        # Thread-safe signal proxy
        self._signals = _ThinkingSignals()
        self._signals.append_text.connect(self._do_append_text)
        self._signals.clear_text.connect(self._do_clear_text)
        self._signals.fade_out.connect(self._do_fade_out)
        self._signals.show_window.connect(self._do_show_window)

        # Window flags: frameless, always on top, click-through
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Layout
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # Title label
        self._title = QLabel("🧠 Thinking", self)
        self._title.setStyleSheet(
            "color: #CCCCCC; font-size: 9pt; font-weight: bold; "
            "padding: 0px; margin: 0px;"
        )
        layout.addWidget(self._title)

        # Content label (scrolling text)
        self._content = QLabel("", self)
        self._content.setWordWrap(True)
        self._content.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._content.setStyleSheet(
            "background-color: transparent; padding: 4px;"
        )
        font = QFont("Monospace", 9)
        self._content.setFont(font)
        layout.addWidget(self._content)

        # Position in bottom-right corner
        self._position_bottom_right()

        # Auto-hide timer
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_fade_out)

        # Fade-out animation timer
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._animate_fade)

        # ThinkingStream subscription
        self._ts = ThinkingStream.instance()
        self._ts.subscribe(self._on_thinking_event)

        # Start hidden
        self.hide()

    @property
    def signals(self) -> _ThinkingSignals:
        """Thread-safe signal proxy."""
        return self._signals

    def _position_bottom_right(self):
        """Position overlay in the bottom-right corner of the screen."""
        screen = self.screen()
        if screen:
            geo = screen.geometry()
            x = geo.right() - WINDOW_WIDTH - 20
            y = geo.bottom() - WINDOW_HEIGHT - 60
            self.move(x, y)

    # ── Thread-safe public API ─────────────────────────────────

    def append_text(self, text: str, color: str = "#CCCCCC") -> None:
        """Append a line of colored text (thread-safe)."""
        self._signals.append_text.emit(text, color)

    def clear_text(self) -> None:
        """Clear all text (thread-safe)."""
        self._signals.clear_text.emit()

    def show_thinking(self) -> None:
        """Show the overlay (thread-safe)."""
        self._signals.show_window.emit()

    def fade_out(self) -> None:
        """Start fade-out animation (thread-safe)."""
        self._signals.fade_out.emit()

    # ── ThinkingStream subscriber ──────────────────────────────

    def _on_thinking_event(self, event: ThinkingEvent) -> None:
        """Called by ThinkingStream for each event (may be any thread)."""
        color = TYPE_COLORS.get(event.type, "#CCCCCC")
        icon = SOURCE_ICONS.get(event.source, "●")

        # Truncate long text
        text = event.text
        if len(text) > 120:
            text = text[:117] + "..."

        # For content/thinking tokens, accumulate instead of making new lines
        if event.type in ("thinking_token", "content_token"):
            # Just show latest token — don't spam lines
            self._signals.append_text.emit(f"{icon} {text}", color)
        elif event.type == "done":
            # Done events fade after a delay
            self._signals.append_text.emit(f"{icon} Done", color)
            self._hide_timer.start(FADE_DELAY_MS)
        elif event.type == "tool_call":
            self._signals.append_text.emit(f"{icon} {text}", color)
            self._signals.show_window.emit()
        elif event.type == "tool_result":
            self._signals.append_text.emit(f"  ↳ {text}", color)
        elif event.type == "error":
            self._signals.append_text.emit(f"⚠ {text}", color)
            self._signals.show_window.emit()
        else:
            self._signals.append_text.emit(f"{icon} {text}", color)
            self._signals.show_window.emit()

    # ── Qt thread implementations ──────────────────────────────

    def _do_show_window(self):
        self._hide_timer.stop()
        self._opacity = 0.95
        self._apply_opacity()
        self.show()

    def _do_append_text(self, text: str, color: str):
        # Keep only last MAX_LINES
        self._lines.append((text, color))
        if len(self._lines) > MAX_LINES:
            self._lines = self._lines[-MAX_LINES:]

        # Build HTML content
        html_parts = []
        for line_text, line_color in self._lines:
            # Escape HTML special chars
            escaped = (
                line_text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            html_parts.append(
                f'<span style="color:{line_color};">{escaped}</span>'
            )
        self._content.setText("<br>".join(html_parts))

        # Reset hide timer
        self._hide_timer.start(FADE_DELAY_MS)

    def _do_clear_text(self):
        self._lines.clear()
        self._content.setText("")

    def _do_fade_out(self):
        self._fade_timer.start()

    def _animate_fade(self):
        self._opacity = max(0.0, self._opacity - FADE_SPEED)
        self._apply_opacity()
        if self._opacity <= 0.0:
            self._fade_timer.stop()
            self.hide()
            self._lines.clear()
            self._content.setText("")

    def _apply_opacity(self):
        self.setWindowOpacity(self._opacity)
        # Also set background with opacity
        self.setStyleSheet(
            f"background-color: rgba(10, 10, 15, {int(self._opacity * 220)});"
            f"border: 1px solid rgba(100, 100, 120, {int(self._opacity * 100)});"
            f"border-radius: 8px;"
        )

    def closeEvent(self, event):
        """Unsubscribe from ThinkingStream when overlay closes."""
        try:
            self._ts.unsubscribe(self._on_thinking_event)
        except Exception:
            pass
        super().closeEvent(event)
