"""AudioShuttle Voice Overlay — visual feedback for push-to-talk.

Full-screen transparent overlay with animated green border and mode label.
Adapted from LocalMind's overlay for Linux/KDE Wayland.

Thread-safe: all visual updates go through Qt signals.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject


BORDER_WIDTH = 3
CORNER_RADIUS = 10
GREEN_RGB = (0, 255, 65)
RED_RGB = (255, 50, 50)
BLUE_RGB = (80, 160, 255)


class _OverlaySignals(QObject):
    """Signal proxy for thread-safe overlay control."""
    show_listening = pyqtSignal()
    show_processing = pyqtSignal()
    show_result = pyqtSignal(str, int)
    show_error = pyqtSignal(str, int)
    hide_overlay = pyqtSignal()


class VoiceOverlay(QWidget):
    """Always-on-top transparent overlay for voice recording feedback.

    Shows a pulsing colored border around the screen with a mode label
    at the bottom center (like LocalMind).

    Modes:
        idle      — hidden
        listening — green pulse, "Listening..."
        processing — blue pulse, "Processing..."
        error     — red pulse, error message

    Thread-safe: use the signals (show_listening, etc.) from any thread.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._border_opacity = 0.0
        self._label_opacity = 0.0
        self._error_color = False
        self._blue_color = False
        self._label_text = ""

        # Thread-safe signal proxy
        self._signals = _OverlaySignals()
        self._signals.show_listening.connect(self._do_show_listening)
        self._signals.show_processing.connect(self._do_show_processing)
        self._signals.show_result.connect(self._do_show_result)
        self._signals.show_error.connect(self._do_show_error)
        self._signals.hide_overlay.connect(self._do_hide_overlay)

        # Window flags: frameless, always on top, no focus
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

        # Cover full screen
        screen = self.screen()
        if screen:
            self.setGeometry(screen.geometry())

        # Mode label (bottom center)
        self._mode_label = QLabel("", self)
        self._mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_label.setStyleSheet(self._label_style(255))
        self._mode_label.adjustSize()
        self._mode_label.hide()
        self._position_label()

        # Pulse animation timer (~60fps)
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(16)
        self._pulse_timer.timeout.connect(self._animate_pulse)
        self._pulse_direction = 1

        # Auto-hide timer
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide_overlay)

        # Fade-out timer
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._animate_fade)

    @property
    def signals(self) -> _OverlaySignals:
        """Thread-safe signal proxy for controlling the overlay from other threads."""
        return self._signals

    def _label_style(self, alpha: int) -> str:
        return (
            f"background-color: rgba(20, 20, 20, 180);"
            f"color: rgba(255, 255, 255, {alpha});"
            "border-radius: 8px;"
            "padding: 8px 24px;"
            "font-size: 14pt;"
            "font-weight: bold;"
        )

    def _position_label(self):
        size = self._mode_label.sizeHint()
        x = (self.width() - size.width()) // 2
        y = self.height() - size.height() - 60
        self._mode_label.move(max(0, x), max(0, y))
        self._mode_label.resize(size.width() + 20, size.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_label()

    # ── Thread-safe public API (call from any thread) ──────────

    def show_listening(self):
        self._signals.show_listening.emit()

    def show_processing(self):
        self._signals.show_processing.emit()

    def show_result(self, text: str, duration_ms: int = 3000):
        self._signals.show_result.emit(text, duration_ms)

    def show_error(self, message: str, duration_ms: int = 4000):
        self._signals.show_error.emit(message, duration_ms)

    def hide_overlay(self):
        self._signals.hide_overlay.emit()

    # ── Actual implementations (Qt thread only) ────────────────

    def _do_show_listening(self):
        self._stop_all_timers()
        self._error_color = False
        self._blue_color = False
        self._border_opacity = 0.3
        self._pulse_direction = 1
        self._label_text = "🎙 Listening..."
        self._update_label_text()
        self._label_opacity = 1.0
        self._mode_label.setStyleSheet(self._label_style(255))
        self._mode_label.show()
        self.show()
        self._pulse_timer.start()

    def _do_show_processing(self):
        self._stop_all_timers()
        self._error_color = False
        self._blue_color = True
        self._border_opacity = 0.3
        self._pulse_direction = 1
        self._label_text = "⚙ Processing..."
        self._update_label_text()
        self._label_opacity = 1.0
        self._mode_label.setStyleSheet(self._label_style(255))
        self._mode_label.show()
        self.show()
        self._pulse_timer.start()

    def _do_show_result(self, text: str, duration_ms: int):
        self._stop_all_timers()
        self._error_color = False
        self._blue_color = False
        self._border_opacity = 0.0
        self._label_text = f"✓ {text}"
        self._update_label_text()
        self._label_opacity = 1.0
        self._mode_label.setStyleSheet(self._label_style(255))
        self._mode_label.show()
        self.show()
        self._hide_timer.start(duration_ms)

    def _do_show_error(self, message: str, duration_ms: int):
        self._stop_all_timers()
        self._error_color = True
        self._blue_color = False
        self._border_opacity = 0.3
        self._pulse_direction = 1
        self._label_text = f"⚠ {message}"
        self._update_label_text()
        self._label_opacity = 1.0
        self._mode_label.setStyleSheet(self._label_style(255))
        self._mode_label.show()
        self.show()
        self._pulse_timer.start()
        self._hide_timer.start(duration_ms)

    def _do_hide_overlay(self):
        self._pulse_timer.stop()
        self._fade_timer.start()

    # ── Internals ───────────────────────────────────────────────

    def _update_label_text(self):
        self._mode_label.setText(self._label_text)
        self._mode_label.adjustSize()
        self._position_label()

    def _stop_all_timers(self):
        self._pulse_timer.stop()
        self._fade_timer.stop()
        self._hide_timer.stop()

    def _animate_pulse(self):
        """Pulse border opacity 0.2 ↔ 1.0."""
        speed = 0.02
        self._border_opacity += speed * self._pulse_direction
        if self._border_opacity >= 1.0:
            self._border_opacity = 1.0
            self._pulse_direction = -1
        elif self._border_opacity <= 0.2:
            self._border_opacity = 0.2
            self._pulse_direction = 1
        self.repaint()

    def _animate_fade(self):
        """Gradually fade out border and label."""
        step = 0.05
        self._border_opacity = max(0.0, self._border_opacity - step)
        self._label_opacity = max(0.0, self._label_opacity - step)
        if self._label_opacity < 0.02:
            self._mode_label.hide()
        else:
            alpha = int(self._label_opacity * 255)
            self._mode_label.setStyleSheet(self._label_style(alpha))
            self._mode_label.show()
        if self._border_opacity <= 0.0 and self._label_opacity <= 0.0:
            self._fade_timer.stop()
            self.hide()
        else:
            self.repaint()

    def paintEvent(self, event):
        if self._border_opacity <= 0.005:
            return

        from PyQt6.QtGui import QPainter, QColor, QPen
        from PyQt6.QtCore import QRectF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._error_color:
            r, g, b = RED_RGB
        elif self._blue_color:
            r, g, b = BLUE_RGB
        else:
            r, g, b = GREEN_RGB

        alpha = int(self._border_opacity * 255)
        color = QColor(r, g, b, alpha)
        pen = QPen(color)
        pen.setWidth(BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.drawRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
        painter.end()
