"""Input (AI Connect) tab for AudioShuttle web UI."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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

    # Get current system prompt
    from audioshuttle.translator import SYSTEM_PROMPT

    saved_prompt = _load_saved_prompt()
    current_prompt = saved_prompt if saved_prompt is not None else SYSTEM_PROMPT

    return app.state.templates.TemplateResponse(
        request,
        "input.html",
        {
            "system_prompt": current_prompt,
            "ai_clients": AI_CLIENTS,
            "chat_api_url": settings.chat_api_url,
            "chat_model_name": settings.chat_model_name,
            "saved": saved,
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
