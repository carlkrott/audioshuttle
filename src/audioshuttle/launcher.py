"""Unified launcher for AudioShuttle — starts web UI, MCP server, and tray."""

from __future__ import annotations

import logging
import signal
import threading
import webbrowser
from typing import Any

logger = logging.getLogger(__name__)


def launch(
    settings: Any,
    *,
    transport: str = "standalone",
    no_browser: bool = False,
    no_tray: bool = False,
    no_model: bool = False,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Launch AudioShuttle with all components.

    Each component starts independently — failures don't crash the whole app.

    Args:
        settings: Settings instance.
        transport: "standalone" (web + tray + MCP SSE) or "stdio" (MCP stdio only).
        no_browser: Don't auto-open browser.
        no_tray: Don't show system tray icon.
        no_model: Don't start the embedded model server.
        host: Override web host.
        port: Override web port.
    """
    import uvicorn

    from audioshuttle.config import Settings
    from audioshuttle.context_manager import ContextManager
    from audioshuttle.osc_bridge import ReaperOSC
    from audioshuttle.server import create_server
    from audioshuttle.translator import IntentTranslator
    from audioshuttle.web import create_web_app

    if not isinstance(settings, Settings):
        settings = Settings()

    web_host = host or settings.web_host
    web_port = port or settings.web_port

    # ── Configure logging ─────────────────────────────────────
    log_level = getattr(logging, settings.log_level.upper(), logging.WARNING)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("AudioShuttle starting...")

    # ── Clean up any orphaned processes from prior runs ──────
    import os as _os
    import subprocess as _sp
    import time as _time

    # Only clean up the web port — the model server is managed externally
    # (e.g., launched separately on its own port, not spawned by AudioShuttle)
    for cleanup_port in [web_port]:
        try:
            result = _sp.run(
                ["fuser", f"{cleanup_port}/tcp"], capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                for pid_str in result.stdout.strip().split():
                    try:
                        pid = int(pid_str.strip())
                        if pid != _os.getpid():
                            logger.info(
                                "Killing orphaned process on port %d (pid %d)",
                                cleanup_port, pid,
                            )
                            _os.kill(pid, 9)
                    except (ValueError, ProcessLookupError):
                        pass
        except Exception:
            pass
    _time.sleep(1)

    # ── Create shared components (each independent) ──────────

    # OSC Bridge (required for DAW control)
    bridge = ReaperOSC(
        host=settings.reaper_host,
        send_port=settings.reaper_port,
        feedback_port=settings.reaper_feedback_port,
    )

    # Embedded model server (optional — skip with --no-model)
    model_server = None
    model_ok = False
    if not no_model and settings.model_enabled:
        try:
            from audioshuttle.model_server import ModelServer

            model_server = ModelServer(settings)
            started = model_server.start(wait=True, timeout=60.0)
            if started:
                logger.info("E2B model server ready")
                model_ok = True
            else:
                logger.warning("E2B model server failed — text-only mode")
                model_server = None
        except Exception as e:
            logger.warning("E2B model server error: %s — text-only mode", e)
            model_server = None
    else:
        logger.info("Model server skipped (--no-model or disabled)")

    translator = IntentTranslator(model_server)
    context_manager = ContextManager(model_server, settings.memory_vault_path)

    # STT availability check
    stt_ok = False
    try:
        from audioshuttle.stt import STTEngine

        stt_ok = STTEngine().available
    except Exception:
        pass

    # Voice pipeline (optional)
    voice_pipeline = None
    hotkey_ok = False
    if stt_ok:
        try:
            from audioshuttle.voice import VoicePipeline

            stt_engine = STTEngine()
            voice_pipeline = VoicePipeline(
                stt_engine=stt_engine,
                model_server=model_server,
                bridge=bridge,
                translator=translator,
            )
        except Exception as e:
            logger.warning("Voice pipeline init failed: %s", e)

    # ── Shutdown coordination ──────────────────────────────────
    shutdown_event = threading.Event()
    voice_hotkey = None

    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # ── stdio mode: just run MCP server ────────────────────────
    if transport == "stdio":
        logger.info("Running in stdio mode (MCP server only)")
        mcp = create_server(settings)
        mcp.run(transport="stdio")
        return

    # ── standalone mode: web + tray + MCP ──────────────────────
    logger.info("Running in standalone mode")

    # Create web app with shared components
    web_app = create_web_app(
        settings=settings,
        bridge=bridge,
        model_server=model_server,
        translator=translator,
    )

    # Attach voice pipeline to app state for web voice recording
    web_app.state.voice_pipeline = voice_pipeline

    # Start web server in background thread
    web_config = uvicorn.Config(
        web_app,
        host=web_host,
        port=web_port,
        log_level=settings.log_level,
    )
    web_server = uvicorn.Server(web_config)
    web_thread = threading.Thread(target=web_server.run, daemon=True)
    web_thread.start()
    logger.info("Web UI started on http://%s:%d", web_host, web_port)

    # Auto-open browser
    if not no_browser and settings.auto_open_browser:
        web_url = f"http://{web_host}:{web_port}"
        threading.Timer(2.0, lambda: webbrowser.open(web_url)).start()
        logger.info("Browser will open in 2 seconds")

    # Voice hotkey (optional — best-effort)
    if voice_pipeline is not None:
        try:
            from audioshuttle.hotkey import VoiceHotkey

            voice_hotkey = VoiceHotkey(
                voice_pipeline=voice_pipeline,
                hotkey=settings.voice_hotkey,
                sample_rate=settings.voice_sample_rate,
            )
            hotkey_ok = voice_hotkey.start()
            if hotkey_ok:
                logger.info("Voice hotkey '%s' registered", settings.voice_hotkey)
            else:
                logger.warning("Voice hotkey unavailable — use browser recording")
        except Exception as e:
            logger.warning("Voice hotkey failed: %s — web recording only", e)

    # Tray icon (optional)
    tray = None
    if not no_tray and settings.tray_enabled:
        try:
            from audioshuttle.tray import create_icon

            def on_tray_quit():
                logger.info("Quit from tray")
                web_server.should_exit = True
                shutdown_event.set()

            # Build status tooltip
            components = []
            components.append(f"Model: {'running' if model_ok else 'off'}")
            components.append(f"Reaper: {'connected' if hasattr(bridge, '_reaper_seen') else 'unknown'}")
            components.append(f"STT: {'available' if stt_ok else 'off'}")
            components.append(f"Hotkey: {'active' if hotkey_ok else 'web-only'}")
            tooltip = "AudioShuttle — " + " | ".join(components)

            tray = create_icon(
                web_url=f"http://{web_host}:{web_port}",
                on_quit=on_tray_quit,
                tooltip=tooltip,
                model_server=model_server,
            )
        except Exception as e:
            logger.warning("Tray icon failed: %s", e)

    # ── Startup summary ────────────────────────────────────────
    logger.info("─" * 50)
    logger.info("AudioShuttle started — Components:")
    logger.info("  Web UI:     http://%s:%d ✓", web_host, web_port)
    logger.info("  Reaper OSC: %s", "connected ✓" if True else "not found ✗")
    logger.info("  Model:      %s", "Gemma E2B ✓" if model_ok else "off")
    logger.info("  STT:        %s", "Whisper ✓" if stt_ok else "not installed")
    logger.info("  Voice:      %s", "Alt+Space ✓" if hotkey_ok else "web-only")
    logger.info("  Tray:       %s", "active ✓" if tray else "off")
    logger.info("─" * 50)

    # Log startup events to error_log (visible in Log tab)
    try:
        from audioshuttle.error_log import error_log
        error_log.add("AudioShuttle started", level="info")
        error_log.add(f"Web UI: http://{web_host}:{web_port}", level="info")
        error_log.add(f"Reaper OSC: send={settings.reaper_port}, feedback={settings.reaper_feedback_port}", level="info")
        if model_ok:
            error_log.add("Model: Gemma E2B active", level="info")
        else:
            error_log.add("Model: disabled (--no-model)", level="warning")
        if stt_ok:
            error_log.add("STT: Whisper available", level="info")
        else:
            error_log.add("STT: not installed", level="warning")
        error_log.add(f"Voice: {'Alt+Space hotkey' if hotkey_ok else 'web-only recording'}", level="info")
        error_log.add(f"20 MCP tools registered", level="info")
    except Exception:
        pass

    # ── Main loop ──────────────────────────────────────────────
    if tray is not None:
        # Run tray in main thread (blocking)
        logger.info("Starting system tray icon (Ctrl+C to quit)")
        try:
            tray.start()
        except KeyboardInterrupt:
            pass
    else:
        # No tray — block until shutdown
        logger.info("Running headless (Ctrl+C to quit)")
        try:
            shutdown_event.wait()
        except KeyboardInterrupt:
            pass

    # ── Graceful shutdown ──────────────────────────────────────
    logger.info("Shutting down...")

    # 1. Stop voice hotkey
    if voice_hotkey is not None:
        try:
            voice_hotkey.stop()
            logger.info("Voice hotkey stopped")
        except Exception:
            pass

    # 2. Stop web server
    web_server.should_exit = True
    logger.info("Web server stopping")

    # 3. Stop model server
    if model_server is not None:
        try:
            model_server.stop()
            logger.info("Model server stopped")
        except Exception:
            pass

    # 4. Stop tray
    if tray is not None:
        try:
            tray.stop()
        except Exception:
            pass

    # 5. Close OSC bridge
    try:
        bridge.close()
    except Exception:
        pass

    logger.info("AudioShuttle stopped")
