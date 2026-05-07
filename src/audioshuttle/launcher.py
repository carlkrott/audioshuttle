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
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Launch AudioShuttle with all components.

    Args:
        settings: Settings instance.
        transport: "standalone" (web + tray + MCP SSE) or "stdio" (MCP stdio only).
        no_browser: Don't auto-open browser.
        no_tray: Don't show system tray icon.
        host: Override web host.
        port: Override web port.
    """
    import uvicorn

    from audioshuttle.config import Settings
    from audioshuttle.context_manager import ContextManager
    from audioshuttle.model_server import ModelServer
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

    # ── Create shared components ───────────────────────────────
    bridge = ReaperOSC(
        host=settings.reaper_host,
        send_port=settings.reaper_port,
        feedback_port=settings.reaper_feedback_port,
    )

    # Start embedded model server
    model_server: ModelServer | None = None
    if settings.model_enabled:
        model_server = ModelServer(settings)
        try:
            started = model_server.start(wait=True, timeout=60.0)
            if started:
                logger.info("E2B model server ready")
            else:
                logger.warning("E2B model server failed — fallback parser only")
                model_server = None
        except Exception as e:
            logger.warning("E2B model server error: %s — fallback only", e)
            model_server = None

    translator = IntentTranslator(model_server)
    context_manager = ContextManager(model_server, settings.memory_vault_path)

    # ── Shutdown coordination ──────────────────────────────────
    shutdown_event = threading.Event()

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

    # Also create MCP server (for future SSE mounting)
    # mcp_server = create_server(settings)

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

    # Tray icon
    if not no_tray and settings.tray_enabled:
        from audioshuttle.tray import create_icon

        def on_tray_quit():
            logger.info("Quit from tray")
            web_server.should_exit = True
            shutdown_event.set()

        tray = create_icon(
            web_url=f"http://{web_host}:{web_port}",
            on_quit=on_tray_quit,
        )

        # Run tray in main thread (blocking)
        logger.info("Starting system tray icon (Ctrl+C to quit)")
        tray.start()
    else:
        # No tray — block until shutdown
        logger.info("Running headless (Ctrl+C to quit)")
        try:
            shutdown_event.wait()
        except KeyboardInterrupt:
            pass

    # Cleanup
    logger.info("Shutting down...")
    web_server.should_exit = True
    if model_server is not None:
        model_server.stop()
    logger.info("AudioShuttle stopped")
