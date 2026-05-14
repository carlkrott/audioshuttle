# Project State — AudioShuttle

## Project Reference

**Goal:** Build an AI-agnostic MCP server that bridges any LLM to Reaper DAW, enabling voice/text control of professional audio production for accessibility.

**Competition:** Kaggle Gemma 4 Good Hackathon
**Deadline:** ~May 19, 2026 (12 days)
**Repository:** /home/korphaus/audioshuttle/

## Current Position

Phase: Phase 6 planning complete — ready for execution
Status: 173 tests passing. Voice pipeline, MIDI generator, arrangement engine, multimodal E2B all working. Model-driven project generation planned.
Last activity: 2026-05-14 — Phase 6 plans created

Progress: [▓▓▓▓▓▓▓░░░] 70%

## Verified Working

| Component | Status | Notes |
|-----------|--------|-------|
| Reaper 7.71 | ✅ Running | OSC on 8000/9000, Lua watcher alive |
| MCP server | ✅ 53 tools | 4 MCP tools: daw_command, daw_state, daw_thinking, daw_interrupt |
| Voice pipeline | ✅ Working | Alt+Space → Whisper → E2B → OSC → Reaper |
| MIDI generator | ✅ Working | Section-aware arrangement, per-instrument patterns, 15 tests |
| Multimodal E2B | ✅ Working | Port 8093, vision confirmed, streaming thinking/content |
| Thinking overlay | ✅ Working | PyQt6 floating window, JSONL log |
| generate_project | ✅ Working | Creates tracks + MIDI + plugins, flat layout |
| create_send routing | ✅ Available | Lua trigger + Python method exist |
| 173 unit tests | ✅ Passing | 2 env-dependent failures (E2B health check) |

## Key Resources

| Resource | Location | Notes |
|----------|----------|-------|
| Reaper config | ~/.config/REAPER/ | OSC on 8000/9000 |
| Lua watcher | ~/.config/REAPER/Scripts/__startup.lua | 13 trigger types, routing/sends supported |
| E2B model | localhost:8093 | Gemma E2B Q4_K_XL + mmproj BF16, ROCm dGPU |
| E4B models | localhost:8090 (CPU), 8092 (dGPU) | DO NOT TOUCH 8090 (zeroclaw) |
| MIDI triggers | /tmp/audioshuttle_*.mid | Verified correct internal eventList |

## Decisions

- **Python over Rust** for 12-day timeline
- **Prompt engineering first**, no LoRA fine-tuning
- **Reaper as DAW** (free, scriptable, OSC support)
- **Lua watcher** for operations OSC can't do (track insert, MIDI import, routing)
- **E2B as domain expert** for translation, not direct tool calling
- **Genre profiles as data** — model references pre-defined profiles, doesn't generate them
- **Pipeline with verification** — each step verifies DAW state before proceeding

## Known Issues

- **Watcher heartbeat fragility** — 5s threshold too tight for blocking Lua ops (InsertMedia). Fix planned in 06-02.
- **State dump incomplete** — doesn't include media items or sends. May need extension for verification.
- **Reaper OSC bridge disconnects** — multiple ReaperOSC instances cause feedback port conflicts
- **E2B vision unreliable for verification** — must verify programmatically, not trust visual assessment

## Blockers/Concerns

- None currently blocking. Plans ready for execution.

## Session Continuity

Last session: 2026-05-14
Stopped at: Phase 6 planning complete (3 plans, 3 waves)
Resume: Run `/gsd-execute-phase 6` to build model-driven project generation

## Phase 6 Plan Summary

| Plan | Wave | Objective | Files |
|------|------|-----------|-------|
| 06-01 | 1 | Genre profile database (11+ genres, instrument families, FX chains) | genre_profiles.py, tests |
| 06-02 | 2 | Enhanced pipeline (create_genre_project, buses, submaster, FX chains, watcher fix) | osc_bridge.py, tests |
| 06-03 | 3 | System prompt + MCP integration (genre detection, dispatch, E2E tests) | translator.py, server.py, tests |
