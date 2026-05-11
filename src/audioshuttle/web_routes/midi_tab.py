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
    translator = getattr(app.state, "translator", None)
    bridge = getattr(app.state, "bridge", None)

    if translator is None or bridge is None:
        app.state.midi_send_result = {
            "success": False,
            "message": "Translator not available.",
        }
        return RedirectResponse(url="/midi", status_code=303)

    role = pattern.get("role", "drums")

    # Build a prompt that tells the translator about the MIDI pattern context
    combined_input = (
        f"Add a new {role} track in the DAW and insert the {role} MIDI pattern onto it. "
        f"{description.strip()}"
    )

    try:
        from audioshuttle.models import DAWState

        # Get live DAW state for context
        daw_state = DAWState()
        if bridge and hasattr(bridge, 'refresh_state'):
            try:
                daw_state = bridge.refresh_state(wait=0.3)
            except Exception:
                pass
        results = translator.translate_multi(combined_input, daw_state)

        # Execute all commands in sequence
        from audioshuttle.voice import _execute_tool
        import asyncio

        executed = []
        for i, result in enumerate(results):
            if result.success and result.tool:
                try:
                    # Small delay between commands (same as voice pipeline)
                    if i > 0:
                        import time
                        time.sleep(0.3)
                    _execute_tool(bridge, result.tool, result.args)
                    executed.append(f"{result.tool}({result.args})")
                except Exception as e:
                    logger.warning("MIDI execute error for %s: %s", result.tool, e)

        if executed:
            app.state.midi_send_result = {
                "success": True,
                "message": f"✓ {' → '.join(executed)}",
                "command": executed[-1] if executed else None,
            }
        else:
            app.state.midi_send_result = {
                "success": False,
                "message": f"Could not understand: {results[0].error if results else 'no response'}",
            }
    except Exception as e:
        logger.warning("MIDI send error: %s", e)
        app.state.midi_send_result = {
            "success": False,
            "message": f"Error: {e}",
        }

    return RedirectResponse(url="/midi", status_code=303)
