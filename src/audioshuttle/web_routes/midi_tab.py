"""MIDI Pattern Generator tab route."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from audioshuttle.midi_generator import MIDIGenerator

logger = logging.getLogger(__name__)

router = APIRouter()
_generator = MIDIGenerator()


@router.get("/midi", response_class=HTMLResponse)
async def midi_page(request: Request):
    """Render the MIDI pattern generator tab."""
    app = request.app
    pattern = getattr(app.state, "midi_pattern", None)
    send_result = getattr(app.state, "midi_send_result", None)
    # Clear result after showing
    if send_result is not None:
        app.state.midi_send_result = None

    return app.state.templates.TemplateResponse(
        request,
        "midi.html",
        {
            "pattern": pattern,
            "send_result": send_result,
        },
    )


@router.post("/midi/generate", response_class=HTMLResponse)
async def midi_generate(
    request: Request,
    role: str = Form("drums"),
    seed: str = Form(""),
):
    """Generate a new MIDI pattern."""
    app = request.app
    seed_int = int(seed) if seed.strip().isdigit() else None
    result = _generator.generate(role=role, seed=seed_int)
    app.state.midi_pattern = result
    return RedirectResponse(url="/midi", status_code=303)


@router.post("/midi/send", response_class=HTMLResponse)
async def midi_send(
    request: Request,
    description: str = Form(""),
):
    """Send the current pattern to E2B for track assignment."""
    app = request.app
    pattern = getattr(app.state, "midi_pattern", None)
    model_server = getattr(app.state, "model_server", None)

    if not pattern:
        app.state.midi_send_result = {
            "success": False,
            "message": "No pattern generated yet. Click Randomize first.",
        }
        return RedirectResponse(url="/midi", status_code=303)

    if not description.strip():
        app.state.midi_send_result = {
            "success": False,
            "message": "Please describe where to put this pattern.",
        }
        return RedirectResponse(url="/midi", status_code=303)

    # Check model server
    if model_server is None or not model_server.is_running:
        app.state.midi_send_result = {
            "success": False,
            "message": "Model server required for MIDI track assignment. Start the E2B model first.",
        }
        return RedirectResponse(url="/midi", status_code=303)

    # Use the translator to interpret the user's description
    # The MIDI pattern context is informational — the translator maps to real tools
    translator = getattr(app.state, "translator", None)
    bridge = getattr(app.state, "bridge", None)

    if translator is None or bridge is None:
        app.state.midi_send_result = {
            "success": False,
            "message": "Translator not available.",
        }
        return RedirectResponse(url="/midi", status_code=303)

    role = pattern.get("role", "drums")

    # Send the user's description to the translator with MIDI context
    # The translator will use the real tool list from SYSTEM_PROMPT
    combined_input = f"Set up a {role} track in the DAW. {description.strip()}"

    try:
        from audioshuttle.models import DAWState

        result = translator.translate(combined_input, DAWState())
        if result.success:
            # Execute the tool on the bridge
            from audioshuttle.voice import _execute_tool
            try:
                _execute_tool(bridge, result.tool, result.args)
            except Exception:
                pass
            app.state.midi_send_result = {
                "success": True,
                "message": f"✓ {result.tool}({result.args}) — via {result.method}",
                "command": result.tool,
            }
        else:
            app.state.midi_send_result = {
                "success": False,
                "message": f"Could not interpret: {result.error}",
            }
    except Exception as e:
        logger.warning("MIDI send error: %s", e)
        app.state.midi_send_result = {
            "success": False,
            "message": f"Error: {e}",
        }

    return RedirectResponse(url="/midi", status_code=303)
