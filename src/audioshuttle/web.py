"""AudioShuttle FastAPI web application factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from audioshuttle.config import Settings
from audioshuttle.error_log import error_log


def create_web_app(
    settings: Settings | None = None,
    bridge: Any = None,
    model_server: Any = None,
    translator: Any = None,
) -> FastAPI:
    """Create the AudioShuttle web configuration UI.

    Args:
        settings: Application settings. Uses defaults if not provided.
        bridge: OSC bridge instance (optional, status shows disconnected if None).
        model_server: Model server instance (optional, status shows disabled if None).
        translator: Intent translator instance (optional).

    Returns:
        FastAPI application instance. Caller runs uvicorn.
    """
    if settings is None:
        settings = Settings()

    app = FastAPI(title="AudioShuttle", docs_url=None, redoc_url=None)

    templates = Jinja2Templates(
        directory=str(Path(__file__).parent / "templates")
    )

    # Shared state
    app.state.settings = settings
    app.state.templates = templates
    app.state.bridge = bridge
    app.state.model_server = model_server
    app.state.translator = translator
    app.state.error_log = error_log

    # Mount routes
    from audioshuttle.web_routes.home import router as home_router

    app.include_router(home_router)

    # Input and Output tabs added in Plan 04-02
    try:
        from audioshuttle.web_routes.input_tab import router as input_router

        app.include_router(input_router)
    except ImportError:
        pass

    try:
        from audioshuttle.web_routes.output_tab import router as output_router

        app.include_router(output_router)
    except ImportError:
        pass

    try:
        from audioshuttle.web_routes.midi_tab import router as midi_router

        app.include_router(midi_router)
    except ImportError:
        pass

    try:
        from audioshuttle.web_routes.log_tab import router as log_router

        app.include_router(log_router)
    except ImportError:
        pass

    try:
        from audioshuttle.web_routes.shortcuts import router as shortcuts_router

        app.include_router(shortcuts_router)
    except ImportError:
        pass

    return app
