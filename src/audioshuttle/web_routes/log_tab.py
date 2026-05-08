"""Command Log tab route."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/log", response_class=HTMLResponse)
async def log_page(request: Request):
    """Render the color-coded command log."""
    app = request.app
    err_log = app.state.error_log

    entries = err_log.get_recent(200)

    return app.state.templates.TemplateResponse(
        request,
        "log.html",
        {
            "entries": entries,
        },
    )


@router.get("/log/filter/{level}", response_class=HTMLResponse)
async def log_filter(request: Request, level: str = "all"):
    """Filter log entries by level."""
    app = request.app
    err_log = app.state.error_log

    all_entries = err_log.get_recent(200)
    if level == "all":
        entries = all_entries
    else:
        entries = [e for e in all_entries if e.get("level", "").lower() == level.lower()]

    return app.state.templates.TemplateResponse(
        request,
        "log.html",
        {
            "entries": entries,
            "active_filter": level,
        },
    )
