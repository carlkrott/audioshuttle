"""Screen capture utility for Reaper DAW window.

Captures Reaper's XWayland window via ImageMagick `import` command.
Reaper runs under X11/XWayland (DISPLAY=:0), so `import` works.
Falls back to full-screen capture if Reaper window not found.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

# Default capture settings
CAPTURE_WIDTH = 1280
CAPTURE_HEIGHT = 720
CAPTURE_PATH = "/communication/audioshuttle_screenshot.png"


def find_reaper_window() -> int | None:
    """Find Reaper's window ID via xdotool.

    Returns:
        Window ID as int, or None if not found.
    """
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", "REAPER"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Take the first window found
            for line in result.stdout.strip().split("\n"):
                wid = line.strip()
                if wid.isdigit():
                    return int(wid)
    except FileNotFoundError:
        logger.debug("xdotool not found — cannot find Reaper window")
    except Exception as e:
        logger.debug("Reaper window search failed: %s", e)
    return None


def capture_reaper_window(
    output_path: str = CAPTURE_PATH,
    width: int = CAPTURE_WIDTH,
    height: int = CAPTURE_HEIGHT,
    quality: int = 0,  # 0 = PNG lossless, 1-100 = JPEG quality
) -> str | None:
    """Capture Reaper's window to an image file.

    Args:
        output_path: Where to save the screenshot.
        width: Resize width (keep aspect ratio).
        height: Resize height.
        quality: If > 0, save as JPEG with this quality instead of PNG.

    Returns:
        Path to the captured image, or None on failure.
    """
    wid = find_reaper_window()

    if wid is None:
        logger.warning("Reaper window not found — trying full-screen capture")
        return capture_full_screen(output_path, width, height, quality)

    # Build ImageMagick import command
    if quality > 0:
        # JPEG mode — smaller file size
        cmd = [
            "import", "-silent",
            "-window", str(wid),
            "-resize", f"{width}x{height}",
            "-quality", str(quality),
            output_path,
        ]
    else:
        # PNG mode — lossless
        cmd = [
            "import", "-silent",
            "-window", str(wid),
            "-resize", f"{width}x{height}",
            output_path,
        ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            size = os.path.getsize(output_path)
            logger.info("Captured Reaper window (WID %d) -> %s (%d bytes)", wid, output_path, size)
            return output_path
        else:
            logger.warning("ImageMagick import failed: %s", result.stderr)
            return None
    except FileNotFoundError:
        logger.error("ImageMagick 'import' not found — install imagemagick")
        return None
    except subprocess.TimeoutExpired:
        logger.error("Screen capture timed out")
        return None
    except Exception as e:
        logger.error("Screen capture failed: %s", e)
        return None


def capture_full_screen(
    output_path: str = CAPTURE_PATH,
    width: int = CAPTURE_WIDTH,
    height: int = CAPTURE_HEIGHT,
    quality: int = 0,
) -> str | None:
    """Capture the full screen to an image file.

    Fallback when Reaper window is not found.
    """
    # Try ImageMagick import for root window
    cmd = ["import", "-silent", "-window", "root", "-resize", f"{width}x{height}"]
    if quality > 0:
        cmd.extend(["-quality", str(quality)])
    cmd.append(output_path)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info("Captured full screen -> %s", output_path)
            return output_path
        else:
            logger.warning("Full-screen capture failed: %s", result.stderr)
    except Exception as e:
        logger.error("Full-screen capture failed: %s", e)

    # Last resort: try gnome-screenshot or scrot
    for alt_cmd in [
        (["gnome-screenshot", "-f", output_path], "gnome-screenshot"),
        (["scrot", output_path], "scrot"),
    ]:
        cmd_list, name = alt_cmd
        try:
            result = subprocess.run(
                cmd_list, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and os.path.exists(output_path):
                logger.info("Captured via %s -> %s", name, output_path)
                return output_path
        except Exception:
            continue

    return None


def capture_to_bytes(
    width: int = CAPTURE_WIDTH,
    height: int = CAPTURE_HEIGHT,
    jpeg_quality: int = 75,
) -> tuple[bytes, str] | None:
    """Capture Reaper window and return (image_bytes, mime_type).

    Returns JPEG by default for smaller payloads.
    Returns None on failure.
    """
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        path = capture_reaper_window(
            tmp_path, width, height, quality=jpeg_quality,
        )
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            return data, "image/jpeg"
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
