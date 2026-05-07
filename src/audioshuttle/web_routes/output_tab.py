"""Output (DAW Connect) tab for AudioShuttle web UI."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from audioshuttle.daw_detect import detect_daw

router = APIRouter()

# DAW presets
DAW_PRESETS = [
    {
        "id": "reaper",
        "name": "Reaper",
        "osc_port": 8000,
        "feedback_port": 9000,
    },
    {
        "id": "ardour",
        "name": "Ardour",
        "osc_port": 3819,
        "feedback_port": 3819,
    },
]


def _get_osc_mappings(bridge) -> list[dict]:
    """Get OSC address patterns from the bridge."""
    if bridge is None:
        return []
    try:
        if hasattr(bridge, "_ADDRESS_PATTERNS"):
            return [
                {"pattern": p, "description": f"OSC address pattern"}
                for p in sorted(bridge._ADDRESS_PATTERNS.keys())
            ]
    except Exception:
        pass
    return []


@router.get("/output", response_class=HTMLResponse)
async def output_page(request: Request):
    """Render the Output (DAW Connect) tab."""
    app = request.app
    settings = app.state.settings
    bridge = app.state.bridge
    rescanned = request.query_params.get("rescanned") == "1"

    detection = detect_daw()
    osc_mappings = _get_osc_mappings(bridge)

    return app.state.templates.TemplateResponse(
        request,
        "output.html",
        {
            "daw_type": settings.daw_type,
            "daw_presets": DAW_PRESETS,
            "detection": detection,
            "osc_mappings": osc_mappings,
            "reaper_host": settings.reaper_host,
            "reaper_port": settings.reaper_port,
            "rescanned": rescanned,
        },
    )


@router.post("/output/daw-preset", response_class=HTMLResponse)
async def change_daw_preset(request: Request, daw_type: str = Form(...)):
    """Change the DAW preset."""
    from audioshuttle.error_log import error_log

    app = request.app
    settings = app.state.settings

    if daw_type in ("reaper", "ardour"):
        settings.daw_type = daw_type
        error_log.add(f"DAW preset changed to {daw_type}", level="warning")

    return RedirectResponse(url="/output?rescanned=1", status_code=303)


@router.post("/output/rescan", response_class=HTMLResponse)
async def rescan_daw(request: Request):
    """Trigger DAW rescan."""
    return RedirectResponse(url="/output?rescanned=1", status_code=303)
