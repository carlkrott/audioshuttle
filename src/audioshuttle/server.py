"""AudioShuttle MCP server — single-tool passthrough for DAW control.

Architecture:
    OpenCode (any LLM) → daw_command("mute the drums and solo guitar")
        → E2B model translates natural language → JSON tool calls
        → DAW bridge (Reaper/Ardour/etc.) executes
        → Human-readable result back to the LLM

The LLM calling this MCP server does NOT need to know DAW internals.
It just speaks naturally and the domain expert model handles translation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp import FastMCP

from audioshuttle.config import Settings
from audioshuttle.model_server import ModelServer
from audioshuttle.osc_bridge import ReaperOSC
from audioshuttle.translator import IntentTranslator

logger = logging.getLogger(__name__)


def create_server(settings: Settings | None = None) -> FastMCP:
    """Create an MCP server with a single smart DAW control tool.

    The server exposes two tools:
    - daw_command: Natural language → model translation → DAW execution
    - daw_state: Query current project state (tracks, transport, etc.)

    This is DAW-agnostic — the model prompt adapts to the connected DAW.
    Adding a new DAW only requires a new bridge class, not new MCP tools.
    """
    if settings is None:
        settings = Settings()

    daw_name = "Reaper" if settings.daw_type == "reaper" else settings.daw_type.title()

    mcp = FastMCP(
        "AudioShuttle",
        instructions=(
            f"DAW control server connected to {daw_name}. "
            "Use daw_command for ALL DAW operations — it understands natural language "
            "and can execute multiple actions in one call. "
            "Use daw_state to query the current project. "
            "The internal domain model handles translation — you just speak naturally."
        ),
    )

    # ── DAW Bridge ──────────────────────────────────────────────
    # Select bridge based on daw_type. Add more DAWs here.
    if settings.daw_type == "reaper":
        bridge = ReaperOSC(
            host=settings.reaper_host,
            send_port=settings.reaper_port,
            feedback_port=settings.reaper_feedback_port,
        )
    else:
        raise ValueError(f"Unsupported DAW: {settings.daw_type}")

    # ── Domain Expert Model ─────────────────────────────────────
    # Uses the E2B model for command translation + arrangement assessment.
    model_server: ModelServer | None = None
    if settings.model_enabled:
        model_server = ModelServer(settings)
        # Wire model server to bridge for assess_arrangement
        bridge._model_server = model_server
        # Don't start embedded server — use external if available
        try:
            import httpx
            resp = httpx.get(
                settings.model_api_url.replace("/v1/chat/completions", "/health"),
                timeout=2.0,
            )
            if resp.status_code == 200:
                logger.info("External model server detected — using for translation")
                model_server.enable_external()
            else:
                logger.warning("Model server health check failed — rule-based only")
                model_server = None
        except Exception:
            logger.warning("No model server available — rule-based only")
            model_server = None

    translator = IntentTranslator(model_server)

    # ── Tool executor map ───────────────────────────────────────
    # Maps tool names from the translator to bridge methods.
    # This is DAW-specific but hidden from the calling LLM.
    def _execute_tool(name: str, args: dict) -> Any:
        """Execute a translated tool call on the DAW bridge."""
        tool_map = {
            "transport_control": lambda: (
                bridge.transport_play() if args.get("action") == "play"
                else bridge.transport_stop() if args.get("action") == "stop"
                else bridge.transport_record() if args.get("action") == "record"
                else bridge.transport_pause() if args.get("action") == "pause"
                else None
            ),
            "transport_seek": lambda: bridge.transport_seek(
                float(args.get("position_seconds", 0))
            ),
            "set_track_volume": lambda: bridge.set_track_volume(
                int(args["track"]), float(args["volume"])
            ),
            "set_track_mute": lambda: bridge.set_track_mute(
                int(args["track"]), bool(args["mute"])
            ),
            "set_track_solo": lambda: bridge.set_track_solo(
                int(args["track"]), bool(args["solo"])
            ),
            "set_track_pan": lambda: bridge.set_track_pan(
                int(args["track"]), float(args["pan"])
            ),
            "set_master_volume": lambda: bridge.set_master_volume(
                float(args["volume"])
            ),
            "set_master_pan": lambda: bridge.set_master_pan(
                float(args["pan"])
            ),
            "set_track_arm": lambda: bridge.set_track_recarm(
                int(args["track"]), bool(args["arm"])
            ),
            "set_track_color": lambda: bridge.set_track_color(
                int(args["track"]), str(args["color"])
            ),
            "set_track_monitor": lambda: bridge.set_track_monitor(
                int(args["track"]), int(args["mode"])
            ),
            "set_track_auto_mode": lambda: bridge.set_track_auto_mode(
                int(args["track"]), str(args["mode"])
            ),
            "set_track_send_volume": lambda: bridge.set_track_send_volume(
                int(args["track"]), int(args["send"]), float(args["volume"])
            ),
            "set_fx_param": lambda: bridge.set_fx_param(
                int(args["track"]), int(args["fx"]),
                int(args["param"]), float(args["value"])
            ),
            "fx_bypass": lambda: bridge.fx_bypass(
                int(args["track"]), int(args["fx"]), bool(args["bypass"])
            ),
            "fx_next_preset": lambda: bridge.fx_next_preset(
                int(args["track"]), int(args["fx"])
            ),
            "fx_prev_preset": lambda: bridge.fx_prev_preset(
                int(args["track"]), int(args["fx"])
            ),
            "fx_set_wetdry": lambda: bridge.fx_set_wetdry(
                int(args["track"]), int(args["fx"]), float(args["value"])
            ),
            "set_tempo": lambda: bridge.set_tempo(float(args["bpm"])),
            "insert_track": lambda: bridge.insert_track(),
            "rename_track": lambda: bridge.rename_track(
                int(args["track"]), str(args["name"])
            ),
            "insert_midi_pattern": lambda: bridge.insert_midi_pattern(
                str(args.get("role", "drums")),
                track=int(args["track"]) if "track" in args else None,
            ),
            "create_song_structure": lambda: bridge.create_song_structure(
                list(args["sections"]),
                bpm=int(args["bpm"]) if "bpm" in args else None,
            ),
            "generate_project": lambda: bridge.generate_project(
                sections=list(args["sections"]),
                instruments=list(args["instruments"]),
                key=str(args.get("key", "C")),
                scale=str(args.get("scale", "major")),
                bpm=int(args.get("bpm", 120)),
            ),
            "create_genre_project": lambda: bridge.create_genre_project(
                genre=args.get("genre", "rock"),
                tempo=args.get("tempo"),
                key=args.get("key", "C"),
                scale=args.get("scale", "major"),
                custom_instruments=args.get("custom_instruments"),
                custom_sections=args.get("custom_sections"),
            ),
            "goto_marker": lambda: bridge.goto_marker(int(args["marker"])),
            "set_marker_name": lambda: bridge.set_marker_name(
                int(args["marker"]), str(args["name"])
            ),
            "set_loop_points": lambda: bridge.set_loop_points(
                float(args["start"]), float(args["end"])
            ),
            "undo": lambda: bridge.undo(),
            "redo": lambda: bridge.redo(),
            "toggle_repeat": lambda: bridge.toggle_repeat(),
            "toggle_metronome": lambda: bridge.toggle_metronome(),
            "trigger_action": lambda: bridge.trigger_action(
                int(args["command_id"])
            ),
            # Vision & Audio Analysis (multimodal)
            "look_and_analyze": lambda: bridge.look_and_analyze(
                str(args.get("question", "Describe what you see"))
            ),
            "listen_and_analyze": lambda: bridge.listen_and_analyze(
                track=int(args["track"]) if args.get("track") is not None else None,
                start_sec=float(args.get("start_sec", 0)),
                duration_sec=float(args.get("duration_sec", 30)),
                question=str(args.get("question", "Describe the audio quality and mix")),
            ),
        }

        executor = tool_map.get(name)
        if executor is None:
            return None
        return executor()

    # ── THE Tool: daw_command ───────────────────────────────────

    @mcp.tool()
    def daw_command(command: str) -> dict[str, Any]:
        """Execute a natural language DAW command via domain expert model.

        Understands compound commands, track names, and musical terms.
        Translates via Gemma E2B model, then executes on the connected DAW.

        Examples:
            "mute the drums and solo the guitar"
            "set tempo to 140"
            "add reverb on track 3"
            "create a project in C major with drums bass melody keys, 16-bar verse 8-bar chorus"
            "rename track 5 to bass and arm it"
            "play"
            "undo"
            "go to marker 2"

        Args:
            command: Natural language DAW command. Can be multiple actions.
        """
        # Get live DAW state for context
        state = bridge.state
        if hasattr(bridge, "refresh_state"):
            try:
                state = bridge.refresh_state(wait=0.3)
            except Exception:
                pass

        # Translate natural language → structured tool calls
        results = translator.translate_multi(command, state)

        if not results:
            return {
                "success": False,
                "error": "Could not translate command",
                "command": command,
            }

        # Execute each translated tool call
        executed = []
        errors = []
        for r in results:
            if not r.success:
                errors.append(f"{r.tool}: {r.error}")
                continue

            tool_name = r.tool
            tool_args = r.args

            # Discovery tools — return state instead of executing
            if tool_name in ("list_tracks", "get_transport",
                             "get_daw_state", "get_track_count"):
                executed.append({
                    "tool": tool_name,
                    "action": "query",
                    "note": "State query — use daw_state for details",
                })
                continue

            cmd_result = _execute_tool(tool_name, tool_args)

            if cmd_result is None:
                errors.append(f"Unknown tool: {tool_name}")
                continue

            # Emit tool result to thinking stream
            try:
                from audioshuttle.thinking_stream import ThinkingStream
                ts = ThinkingStream.instance()
                ok = cmd_result.success if hasattr(cmd_result, "success") else True
                detail = ""
                if hasattr(cmd_result, "reaper_feedback") and cmd_result.reaper_feedback:
                    detail = cmd_result.reaper_feedback[:80]
                elif hasattr(cmd_result, "error") and cmd_result.error:
                    detail = cmd_result.error[:80]
                ts.emit_tool_result(tool_name, ok, detail)
            except Exception:
                pass

            executed.append({
                "tool": tool_name,
                "args": tool_args,
                "success": cmd_result.success if hasattr(cmd_result, "success") else True,
                "detail": (
                    cmd_result.reaper_feedback
                    if hasattr(cmd_result, "reaper_feedback") and cmd_result.reaper_feedback
                    else None
                ),
                "error": cmd_result.error if hasattr(cmd_result, "error") and cmd_result.error else None,
            })

        # Build summary
        success_count = sum(1 for e in executed if e.get("success", True))
        total = len(executed)

        summary_parts = []
        for e in executed:
            if e.get("action") == "query":
                continue
            if e.get("success"):
                detail = e.get("detail", "")
                if detail:
                    summary_parts.append(detail)
                else:
                    summary_parts.append(f"✓ {e['tool']}({e.get('args', {})})")
            else:
                summary_parts.append(f"✗ {e['tool']}: {e.get('error', 'failed')}")

        return {
            "success": total > 0 and len(errors) == 0,
            "command": command,
            "executed": total,
            "results": executed,
            "errors": errors,
            "summary": "\n".join(summary_parts) if summary_parts else "No actions taken",
        }

    # ── State Query Tool ────────────────────────────────────────

    @mcp.tool()
    def daw_state() -> dict[str, Any]:
        """Get current DAW project state: tracks, transport, master.

        Returns track names, volumes, mute/solo/arm states, transport
        position, tempo, and recording status.
        """
        # Try to get fresh state via watcher
        raw_state = None
        if hasattr(bridge, "refresh_state"):
            try:
                raw_state = bridge.refresh_state(wait=0.5)
            except Exception:
                pass

        if not raw_state:
            return {
                "connected": bridge.is_connected,
                "tracks": [],
                "transport": {"playing": False, "tempo": 0},
                "error": "No DAW state available" if not bridge.is_connected else None,
            }

        # Read from the watcher's JSON dump for full state
        tracks = []
        if hasattr(bridge, "state") and bridge.state:
            for t in bridge.state.tracks:
                track_info = {
                    "number": t.track_number,
                    "name": t.name or f"Track {t.track_number}",
                    "volume": round(t.volume, 2),
                    "pan": round(t.pan, 2),
                    "muted": t.mute,
                    "soloed": t.solo,
                }
                tracks.append(track_info)

        # Try to get extended state (armed, color) from raw watcher data
        try:
            import json as _json
            watcher_path = "/tmp/audioshuttle_daw_state.json"
            with open(watcher_path) as f:
                watcher_data = _json.load(f)
            for wt in watcher_data.get("tracks", []):
                for t in tracks:
                    if t["number"] == wt["number"]:
                        t["armed"] = wt.get("recarm", False)
                        t["color"] = wt.get("color", "#000000")
                        break
            transport_data = watcher_data.get("transport", {})
            transport = {
                "playing": transport_data.get("playing", False),
                "recording": transport_data.get("recording", False),
                "position_seconds": round(transport_data.get("position", 0), 1),
                "tempo": round(transport_data.get("tempo", 120), 0),
            }
        except Exception:
            transport = {
                "playing": False,
                "recording": False,
                "position_seconds": 0,
                "tempo": 120,
            }

        return {
            "connected": bridge.is_connected,
            "daw": settings.daw_type,
            "track_count": raw_state.track_count if raw_state else 0,
            "tracks": tracks,
            "transport": transport,
        }

    # ── Thinking Stream Tools ──────────────────────────────────

    @mcp.tool()
    def daw_thinking(n: int = 50) -> dict[str, Any]:
        """Get recent E2B thinking/events log.

        Shows what the model is currently thinking or has thought recently.
        Useful for understanding model reasoning during long operations.

        Args:
            n: Number of recent events to return (default 50).
        """
        from audioshuttle.thinking_stream import ThinkingStream
        ts = ThinkingStream.instance()
        events = ts.get_recent_dicts(n)
        return {
            "count": len(events),
            "events": events,
        }

    @mcp.tool()
    def daw_interrupt(reason: str = "user requested") -> dict[str, Any]:
        """Interrupt current E2B thinking/execution.

        Stops the current model operation mid-stream. Use when the model
        is taking too long or heading in the wrong direction.

        Args:
            reason: Why the interrupt was requested.
        """
        from audioshuttle.thinking_stream import ThinkingStream
        ts = ThinkingStream.instance()
        ts.interrupt(reason)
        return {
            "interrupted": True,
            "reason": reason,
        }

    return mcp
