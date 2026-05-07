"""System tray icon for AudioShuttle."""

from __future__ import annotations

import logging
import threading
import webbrowser
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Check if pystray is available
try:
    import pystray
    from PIL import Image, ImageDraw

    _TRAY_AVAILABLE = True
except ImportError:
    _TRAY_AVAILABLE = False


class TrayIcon:
    """System tray icon with Open Web UI and Quit menu items."""

    def __init__(
        self,
        web_url: str = "http://127.0.0.1:8765",
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self._web_url = web_url
        self._on_quit = on_quit
        self._icon: Optional[object] = None

        if _TRAY_AVAILABLE:
            self._icon = pystray.Icon(
                "AudioShuttle",
                icon=self._create_icon_image(),
                menu=pystray.Menu(
                    pystray.MenuItem("Open Web UI", self._on_open_web, default=True),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Quit", self._on_quit_item),
                ),
            )

    def _create_icon_image(self) -> "Image.Image":
        """Generate a 64x64 icon programmatically."""
        img = Image.new("RGB", (64, 64), (26, 26, 46))  # #1a1a2e background
        dc = ImageDraw.Draw(img)
        # Green rounded rectangle (shuttle shape)
        dc.rounded_rectangle([12, 8, 52, 56], radius=8, fill=(15, 155, 88))
        # White triangle (play/forward symbol)
        dc.polygon([(28, 20), (28, 44), (44, 32)], fill=(255, 255, 255))
        return img

    def start(self) -> None:
        """Start the tray icon (blocking, must be main thread)."""
        if not _TRAY_AVAILABLE:
            logger.warning("pystray not installed, tray icon disabled")
            return
        if self._icon is None:
            return
        logger.info("Starting system tray icon")
        self._icon.run()

    def stop(self) -> None:
        """Stop the tray icon (callable from any thread)."""
        if self._icon is not None:
            self._icon.stop()

    def notify(self, message: str, title: str = "AudioShuttle") -> None:
        """Show a system tray notification."""
        if self._icon is not None and hasattr(pystray.Icon, "HAS_NOTIFICATION"):
            try:
                self._icon.notify(message, title)
            except Exception:
                pass  # Not all backends support notifications

    def _on_open_web(self, icon, item) -> None:
        """Open the web UI in the default browser."""
        webbrowser.open(self._web_url)

    def _on_quit_item(self, icon, item) -> None:
        """Handle quit from tray menu."""
        icon.stop()
        if self._on_quit is not None:
            self._on_quit()


def create_icon(
    web_url: str = "http://127.0.0.1:8765",
    on_quit: Callable[[], None] | None = None,
) -> TrayIcon:
    """Factory function to create a TrayIcon."""
    return TrayIcon(web_url=web_url, on_quit=on_quit)
