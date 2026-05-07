"""Home/Status route for AudioShuttle web UI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from audioshuttle.daw_detect import detect_daw
from audioshuttle.gpu_monitor import get_gpu_vram

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Render the home page with status badges and error log."""
    app = request.app
    settings = app.state.settings
    bridge = app.state.bridge
    model_server = app.state.model_server
    err_log = app.state.error_log

    # Determine model state
    if model_server is not None:
        if hasattr(model_server, "is_running") and model_server.is_running:
            model_state = "running"
            model_loaded = True
        else:
            model_state = "loading"
            model_loaded = False
    else:
        model_state = "disabled"
        model_loaded = False

    # Determine DAW connection
    daw_connected = False
    if bridge is not None and hasattr(bridge, "is_connected"):
        daw_connected = bridge.is_connected

    # Get DAW detection info
    detection = detect_daw()

    status = {
        "daw_connected": daw_connected,
        "daw_name": settings.daw_type.title(),
        "mcp_running": True,  # if we're serving this page, MCP is running
        "model_loaded": model_loaded,
        "model_state": model_state,
        "gpu_vram": get_gpu_vram(card_index=1),
        "detection": detection,
    }

    errors = err_log.get_recent(50)

    return app.state.templates.TemplateResponse(
        request,
        "home.html",
        {
            "status": status,
            "errors": errors,
        },
    )
