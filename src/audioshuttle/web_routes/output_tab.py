"""Output (DAW Connect) tab for AudioShuttle web UI."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

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

PRESETS_DIR = Path.home() / ".audioshuttle" / "presets"


def _get_osc_mappings(bridge) -> list[dict]:
    """Get OSC address patterns from the bridge."""
    if bridge is None:
        return []
    try:
        if hasattr(bridge, "_ADDRESS_PATTERNS"):
            return [
                {"pattern": p.pattern, "description": f"OSC address pattern"}
                for p in bridge._ADDRESS_PATTERNS
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


def _list_saved_presets() -> list[dict]:
    """List all saved track presets from disk."""
    presets = []
    if PRESETS_DIR.exists():
        for f in sorted(PRESETS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                presets.append({"name": f.stem, **data})
            except (json.JSONDecodeError, OSError):
                pass
    return presets


@router.get("/output/presets", response_class=JSONResponse)
async def list_presets(request: Request):
    """List saved track presets as JSON."""
    return _list_saved_presets()


@router.post("/output/preset/save", response_class=JSONResponse)
async def save_preset(request: Request):
    """Save current track state as a named preset."""
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return {"success": False, "message": "Preset name required"}

    # Sanitize filename
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    if not safe_name:
        return {"success": False, "message": "Invalid preset name"}

    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    preset_data = {
        "tracks": body.get("tracks", {}),
        "master_volume": body.get("master_volume", 1.0),
    }

    preset_path = PRESETS_DIR / f"{safe_name}.json"
    preset_path.write_text(json.dumps(preset_data, indent=2))

    from audioshuttle.error_log import error_log
    error_log.add(f"Track preset saved: {safe_name}", level="info")

    return {"success": True, "message": f"Preset '{safe_name}' saved"}


@router.post("/output/preset/load", response_class=JSONResponse)
async def load_preset(request: Request):
    """Load a track preset and apply to DAW."""
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return {"success": False, "message": "Preset name required"}

    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    preset_path = PRESETS_DIR / f"{safe_name}.json"

    if not preset_path.exists():
        return {"success": False, "message": f"Preset '{safe_name}' not found"}

    preset_data = json.loads(preset_path.read_text())

    # Apply via OSC bridge if available
    app = request.app
    bridge = app.state.bridge
    applied = 0
    if bridge:
        for track_name, track_data in preset_data.get("tracks", {}).items():
            if "volume" in track_data:
                try:
                    bridge.set_track_volume(track_name, track_data["volume"])
                    applied += 1
                except Exception:
                    pass
            if "pan" in track_data:
                try:
                    bridge.set_track_pan(track_name, track_data["pan"])
                    applied += 1
                except Exception:
                    pass
        if "master_volume" in preset_data:
            try:
                bridge.set_master_volume(preset_data["master_volume"])
                applied += 1
            except Exception:
                pass

    from audioshuttle.error_log import error_log
    error_log.add(f"Loaded preset '{safe_name}' ({applied} commands applied)", level="info")

    return {"success": True, "message": f"Preset '{safe_name}' loaded ({applied} changes applied)"}


@router.get("/output/state-snapshot", response_class=JSONResponse)
async def state_snapshot(request: Request):
    """Get current DAW state as JSON snapshot."""
    app = request.app
    bridge = app.state.bridge

    if bridge is None:
        return {"connected": False, "tracks": [], "transport": {}}

    snapshot = {
        "connected": bridge.is_connected if hasattr(bridge, "is_connected") else False,
        "tracks": [],
        "transport": {},
    }

    # Try to get transport state
    if hasattr(bridge, "_state"):
        state = bridge._state
        snapshot["transport"] = {
            "playing": getattr(state, "playing", False),
            "recording": getattr(state, "recording", False),
            "repeat": getattr(state, "repeat", False),
        }

    return snapshot
