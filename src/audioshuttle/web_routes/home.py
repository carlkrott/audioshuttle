"""Home/Status route for AudioShuttle web UI."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from audioshuttle.error_log import error_log
from audioshuttle.models import CommandResult

logger = logging.getLogger(__name__)

router = APIRouter()

# Global command history for the session
_history = deque(maxlen=50)


def record_command(command: str, tool: str, success: bool) -> None:
    """Add a command to the global history."""
    from datetime import datetime
    _history.appendleft({
        "timestamp": datetime.now().isoformat(),
        "command": command,
        "tool": tool,
        "success": success,
    })


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Render the home page with status badges and error log."""
    app = request.app
    settings = app.state.settings
    bridge = app.state.bridge
    model_server = app.state.model_server
    err_log = app.state.error_log

    # Determine model state + stats
    model_state = "disabled"
    model_loaded = False
    model_inference_ms: float | None = None
    model_tokens_sec: float | None = None

    if model_server is not None:
        if hasattr(model_server, "is_running") and model_server.is_running:
            model_state = "running"
            model_loaded = True
            # Check for inference stats
            model_inference_ms = getattr(model_server, "_last_inference_ms", None)
            model_tokens_sec = getattr(model_server, "_avg_tokens_sec", None)
        else:
            model_state = "loading"

    # Determine DAW connection — probe Reaper if not yet seen
    daw_connected = False
    state = None
    if bridge is not None:
        if hasattr(bridge, "refresh_state"):
            try:
                state = bridge.refresh_state(wait=0.3)
            except Exception:
                pass
        
        if not bridge.is_connected and hasattr(bridge, "probe"):
            bridge.probe()
        daw_connected = bridge.is_connected

    # Get DAW detection info
    from audioshuttle.daw_detect import detect_daw
    detection = detect_daw()

    # Get STT availability
    stt_available = False
    try:
        from audioshuttle.stt import STTEngine
        stt_available = STTEngine().available
    except Exception:
        pass

    # Check voice mode
    voice_mode = "disabled"
    voice_pipeline = getattr(app.state, "voice_pipeline", None)
    if voice_pipeline is not None:
        voice_mode = "web"  # at minimum, browser recording works
        # Check if global hotkey is active
        voice_hotkey = getattr(app.state, "voice_hotkey", None)
        if voice_hotkey is not None and hasattr(voice_hotkey, "is_running") and voice_hotkey.is_running:
            voice_mode = "hotkey"

    status = {
        "model_state": model_state,
        "model_inference_ms": model_inference_ms,
        "model_tokens_sec": model_tokens_sec,
        "daw_connected": daw_connected,
        "detection": detection,
        "gpu_vram": {"vram_used_mb": 0, "vram_total_mb": 0},
    }

    # Add GPU info if available
    if model_server and hasattr(model_server, "get_vram_info"):
        status["gpu_vram"] = model_server.get_vram_info()

    # Get recent errors
    errors = err_log.get_recent(n=20)
    history = list(_history)

    return app.state.templates.TemplateResponse(
        request,
        "home.html",
        {
            "status": status,
            "errors": errors,
            "history": history,
            "stt_available": stt_available,
            "voice_mode": voice_mode,
            "settings": settings,
            "state": state,
        },
    )


@router.post("/transport", response_class=HTMLResponse)
async def transport_control(request: Request, action: str = Form(...)):
    """Send a transport command via OSC."""
    app = request.app
    bridge = app.state.bridge

    if bridge is None:
        error_log.add("Transport error: Reaper bridge not initialized", level="error")
        return RedirectResponse(url="/", status_code=303)

    if hasattr(bridge, "send_command"):
        # Special case: play during recording → stop record first, then play
        if action == "play":
            state = getattr(bridge, "state", None)
            is_recording = state and getattr(state.transport, "recording", False)
            if is_recording:
                # Stop recording first, then start playing
                bridge.send_command("/stop")
                import time
                time.sleep(0.05)
                result = bridge.send_command("/play", 1.0)
                record_command(action, "/stop+/play", result.success)
                error_log.add(f"Transport: stop recording + play", level="info")
            else:
                result = bridge.send_command("/play", 1.0)
                record_command(action, "/play", result.success)
                error_log.add(f"Transport: play", level="info")
        else:
            osc_map = {
                "stop": "/stop",
                "record": "/record",
                "pause": "/pause",
            }
            address = osc_map.get(action)
            if address:
                result = bridge.send_command(address)
                record_command(action, address, result.success)
                error_log.add(f"Transport: {action} ({address}) -> {'OK' if result.success else 'FAIL'}", level="info")

    return RedirectResponse(url="/", status_code=303)


@router.get("/replay", response_class=HTMLResponse)
async def replay_command(request: Request, cmd: str = ""):
    """Re-execute a command from history."""
    app = request.app
    bridge = app.state.bridge

    # Sanitize — skip replay if the command looks like garbage
    cmd = cmd.strip()
    if not cmd or len(cmd) > 200 or not all(c.isprintable() for c in cmd):
        return RedirectResponse(url="/", status_code=303)

    if bridge is None:
        return RedirectResponse(url="/", status_code=303)

    # Direct transport commands — replay via OSC directly
    direct_transport = {"play", "stop", "record", "pause"}
    if cmd in direct_transport:
        result = bridge.send_command(f"/{cmd}")
        record_command(cmd, f"/{cmd}", result.success)
        error_log.add(f"Replay: {cmd}", level="info")
    else:
        # Natural language command — translate via translator
        translator = getattr(app.state, "translator", None)
        if translator:
            from audioshuttle.models import DAWState

            # Get live DAW state for context
            daw_state = DAWState()
            if hasattr(bridge, 'refresh_state'):
                try:
                    daw_state = bridge.refresh_state(wait=0.3)
                except Exception:
                    pass
            results = translator.translate_multi(cmd, daw_state)
            if results and any(r.success for r in results):
                executed = 0
                for i, r in enumerate(results):
                    if not r.success:
                        error_log.add(f"Replay tool #{i} failed: {r.error}", level="warning")
                        continue
                    error_log.add(f"Replay NL: '{cmd}' → {r.tool} (step {i+1}/{len(results)})", level="info")
                    # Execute the translated tool via getattr on the bridge
                    if hasattr(bridge, r.tool):
                        try:
                            tool_fn = getattr(bridge, r.tool)
                            cmd_args = r.args if r.args else {}
                            cmd_result = tool_fn(**cmd_args) if isinstance(cmd_args, dict) else tool_fn()
                            error_log.add(f"Replay tool '{r.tool}' done", level="info")
                        except Exception as e:
                            error_log.add(f"Replay tool '{r.tool}' exception: {e}", level="error")
                    executed += 1
                    await asyncio.sleep(0.5)
                record_command(cmd, f"multi({executed} tools)", True)
                error_log.add(f"Replay: '{cmd}' → {executed} tool(s) executed", level="info")
            else:
                record_command(cmd, "replay", False)
                error_log.add(f"Replay failed: '{cmd}'", level="warning")
        else:
            record_command(cmd, "replay", False)

    return RedirectResponse(url="/", status_code=303)
