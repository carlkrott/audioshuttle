"""Input (AI Connect) tab for AudioShuttle web UI."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# AI client presets
AI_CLIENTS = [
    {"name": "Gemini CLI", "description": "Google Gemini via MCP CLI client"},
    {"name": "Claude Code", "description": "Anthropic Claude via MCP CLI client"},
    {"name": "Custom", "description": "Any OpenAI-compatible client"},
]

# File path for persisted system prompt
_PROMPT_FILE = Path("~/.audioshuttle/system-prompt.txt").expanduser()

# Max voice upload size (10 MB)
_MAX_VOICE_SIZE = 10 * 1024 * 1024

# Allowed audio extensions
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac"}


def _load_saved_prompt() -> str | None:
    """Load saved system prompt from file, or None if not saved."""
    try:
        if _PROMPT_FILE.exists():
            return _PROMPT_FILE.read_text().strip() or None
    except Exception:
        pass
    return None


@router.get("/input", response_class=HTMLResponse)
async def input_page(request: Request):
    """Render the Input (AI Connect) tab."""
    app = request.app
    settings = app.state.settings
    saved = request.query_params.get("saved") == "1"
    voice_result = request.query_params.get("voice_result")

    # Get current system prompt
    from audioshuttle.translator import SYSTEM_PROMPT

    saved_prompt = _load_saved_prompt()
    current_prompt = saved_prompt if saved_prompt is not None else SYSTEM_PROMPT

    # Check STT availability
    stt_available = False
    try:
        from audioshuttle.stt import STTEngine

        stt_available = STTEngine().available
    except Exception:
        pass

    return app.state.templates.TemplateResponse(
        request,
        "input.html",
        {
            "system_prompt": current_prompt,
            "ai_clients": AI_CLIENTS,
            "chat_api_url": settings.chat_api_url,
            "chat_model_name": settings.chat_model_name,
            "saved": saved,
            "voice_cleanup": settings.voice_cleanup,
            "stt_available": stt_available,
            "voice_result": voice_result,
        },
    )


@router.post("/input/system-prompt", response_class=HTMLResponse)
async def save_system_prompt(request: Request, system_prompt: str = Form(...)):
    """Save the system prompt to file and update in-memory."""
    from audioshuttle.error_log import error_log
    from audioshuttle.translator import update_system_prompt

    try:
        # Ensure directory exists
        _PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PROMPT_FILE.write_text(system_prompt)

        # Update in-memory prompt
        update_system_prompt(system_prompt)

        logger.info("System prompt updated (%d chars)", len(system_prompt))
    except Exception as e:
        error_log.add(f"Failed to save system prompt: {e}")
        logger.error("Failed to save system prompt: %s", e)

    return RedirectResponse(url="/input?saved=1", status_code=303)


@router.post("/input/system-prompt/reset", response_class=HTMLResponse)
async def reset_system_prompt(request: Request):
    """Reset system prompt to the built-in default."""
    from audioshuttle.error_log import error_log
    from audioshuttle.translator import SYSTEM_PROMPT as DEFAULT_PROMPT, update_system_prompt

    try:
        # Remove saved file so default is used
        if _PROMPT_FILE.exists():
            _PROMPT_FILE.unlink()
        # Update in-memory
        update_system_prompt(DEFAULT_PROMPT)
        error_log.add("System prompt reset to default", level="info")
    except Exception as e:
        error_log.add(f"Failed to reset system prompt: {e}")

    return RedirectResponse(url="/input?saved=1", status_code=303)


@router.post("/input/voice", response_class=JSONResponse)
async def process_voice(
    request: Request,
    audio_file: UploadFile = File(...),
    cleanup: str = Form(""),
):
    """Process voice recording through the pipeline.

    Accepts multipart upload with audio blob and cleanup toggle.
    """
    from audioshuttle.error_log import error_log

    # Validate file size
    content = await audio_file.read()
    if len(content) > _MAX_VOICE_SIZE:
        return JSONResponse(
            {"success": False, "error": "Audio file too large (max 10 MB)"}
        )

    # Validate file type
    filename = audio_file.filename or "voice.webm"
    ext = Path(filename).suffix.lower()
    if ext not in _AUDIO_EXTENSIONS:
        return JSONResponse(
            {"success": False, "error": f"Unsupported audio format: {ext}"}
        )

    # Check for voice pipeline on app state
    voice_pipeline = getattr(request.app.state, "voice_pipeline", None)
    if voice_pipeline is None:
        return JSONResponse(
            {
                "success": False,
                "error": "Voice pipeline not initialized",
            }
        )

    do_cleanup = cleanup == "on"

    try:
        result = await voice_pipeline.process_audio(
            content, filename=filename, cleanup=do_cleanup
        )
        error_log.add(
            f"Voice: '{result.get('transcription', '')}' → "
            f"{'✓' if result['success'] else '✗ ' + (result.get('error') or '')}",
            level="info" if result["success"] else "error",
        )
        return JSONResponse(result)
    except Exception as e:
        logger.error("Voice pipeline error: %s", e)
        return JSONResponse({"success": False, "error": str(e)})


@router.post("/input/voice-settings", response_class=HTMLResponse)
async def voice_settings(request: Request, cleanup: str = Form("")):
    """Toggle the voice cleanup setting."""
    from audioshuttle.error_log import error_log

    app = request.app
    app.state.settings.voice_cleanup = cleanup == "on"
    error_log.add(
        f"Voice cleanup {'enabled' if cleanup == 'on' else 'disabled'}",
        level="info",
    )

    return RedirectResponse(url="/input", status_code=303)
