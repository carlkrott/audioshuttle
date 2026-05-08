"""Shortcuts reference page — lists all MCP tools."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

# Tool reference data grouped by category
TOOL_CATEGORIES = [
    {
        "name": "Transport",
        "tools": [
            {"name": "play", "desc": "Start playback", "example": "play", "params": "—"},
            {"name": "stop", "desc": "Stop playback", "example": "stop", "params": "—"},
            {"name": "record", "desc": "Start recording", "example": "record", "params": "—"},
            {"name": "pause", "desc": "Pause playback", "example": "pause", "params": "—"},
            {"name": "seek", "desc": "Seek to position", "example": "seek to bar 16", "params": "position (seconds)"},
        ],
    },
    {
        "name": "Track Control",
        "tools": [
            {"name": "set_track_volume", "desc": "Set track volume", "example": "set vocals to 80%", "params": "track, volume (0-1)"},
            {"name": "set_track_mute", "desc": "Mute/unmute track", "example": "mute the drums", "params": "track, mute (bool)"},
            {"name": "set_track_solo", "desc": "Solo/unsolo track", "example": "solo the bass", "params": "track, solo (bool)"},
            {"name": "set_track_pan", "desc": "Set track pan", "example": "pan guitar left", "params": "track, pan (-1 to 1)"},
            {"name": "set_track_arm", "desc": "Arm track for recording", "example": "arm track 3", "params": "track, arm (bool)"},
        ],
    },
    {
        "name": "Master",
        "tools": [
            {"name": "set_master_volume", "desc": "Set master volume", "example": "master volume 75%", "params": "volume (0-1)"},
            {"name": "set_master_pan", "desc": "Set master pan", "example": "pan master center", "params": "pan (-1 to 1)"},
        ],
    },
    {
        "name": "FX",
        "tools": [
            {"name": "set_fx_param", "desc": "Set FX parameter value", "example": "set reverb wet to 50%", "params": "track, fx, param, value (0-1)"},
            {"name": "toggle_fx_bypass", "desc": "Bypass/enable FX", "example": "bypass reverb on track 2", "params": "track, fx, bypass (bool)"},
        ],
    },
    {
        "name": "DAW",
        "tools": [
            {"name": "get_daw_state", "desc": "Get current DAW state", "example": "what's the current state", "params": "—"},
            {"name": "refresh_state", "desc": "Refresh DAW state from Reaper", "example": "refresh state", "params": "—"},
            {"name": "execute_action", "desc": "Execute a Reaper action by ID", "example": "execute action 40001", "params": "action_id (int)"},
        ],
    },
    {
        "name": "AI",
        "tools": [
            {"name": "interpret_command", "desc": "Translate natural language to DAW command", "example": "turn up the drums a little", "params": "command (text)"},
            {"name": "transcribe_audio", "desc": "Transcribe audio file to text", "example": "transcribe /path/to/audio.wav", "params": "audio_path"},
        ],
    },
    {
        "name": "System",
        "tools": [
            {"name": "check_health", "desc": "Check server health", "example": "health check", "params": "—"},
        ],
    },
]


@router.get("/shortcuts", response_class=HTMLResponse)
async def shortcuts_page(request: Request):
    """Render the shortcuts reference page."""
    return request.app.state.templates.TemplateResponse(
        request,
        "shortcuts.html",
        {
            "categories": TOOL_CATEGORIES,
        },
    )
