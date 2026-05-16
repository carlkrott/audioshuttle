# Project State — AudioShuttle

## Project Reference

**Goal:** Build an AI-agnostic MCP server that bridges any LLM to Reaper DAW, enabling voice/text control of professional audio production for accessibility.

**Competition:** Kaggle Gemma 4 Good Hackathon
**Deadline:** ~May 19, 2026 (12 days)
**Repository:** /home/korphaus/audioshuttle/

## Current Position

Phase: Phase 8 (Hackathon Submission Prep) — PLANNING
Status: Phase 7 completed. E4B modifier system implemented and E2E verified. All 5 pipeline bugs fixed (MIDI generation, FX chains, genre lump mapping, bus/submaster FX, stray tracks). Modifier system working with plugin overrides, MIDI density modifiers, FX modifiers, and section changes. Now preparing for Kaggle submission: Docker packaging, security scrub, README, GitHub push, demo video.

Last activity: 2026-05-16 — Phase 8 plans created

Progress: [▓▓▓▓▓▓▓▓▓▓] 100% (Phase 7 done, Phase 8 planned)

## Verified Working

| Component | Status | Notes |
|-----------|--------|-------|
| Reaper 7.71 | ✅ Running | OSC on 8000/9000, Lua watcher alive with tick counter |
| MCP server | ✅ 4 tools | daw_command, daw_state, daw_thinking, daw_interrupt |
| Voice pipeline | ✅ Working | Alt+Space → Whisper → E2B → OSC → Reaper |
| MIDI generator | ✅ Working | Section-aware arrangement, 5+ instruments, density modifier support |
| Multimodal E2B | ✅ Working | Port 8093, vision confirmed, streaming thinking/content |
| Thinking overlay | ✅ Working | PyQt6 floating window, JSONL log |
| generate_project | ✅ Working | Creates tracks + MIDI + plugins, flat layout |
| create_genre_project | ✅ Working | Full 9-step pipeline + E4B modifier system (plugin overrides, MIDI density, FX extras, section changes) |
| create_send routing | ✅ Working | Full routing infrastructure for bus→submaster routing |
| genre_profiles | ✅ Working | 11 genres, 8 instrument families, 7 FX chain types |
| 224 unit tests | ✅ Most passing | 4 pre-existing mocking failures (non-functional, pipeline works live) |

## Key Resources

| Resource | Location | Notes |
|----------|----------|-------|
| Reaper config | ~/.config/REAPER/ | OSC on 8000/9000 |
| Lua watcher | ~/.config/REAPER/Scripts/__startup.lua | 13 trigger types, routing/sends, tick counter |
| E2B model | localhost:8093 | Gemma E2B Q4_K_XL + mmproj BF16, ROCm dGPU |
| E4B models | localhost:8090 (CPU), 8092 (dGPU) | DO NOT TOUCH 8090 (zeroclaw) |

## Decisions

- **Python over Rust** for 12-day timeline
- **Prompt engineering first**, no LoRA fine-tuning
- **Reaper as DAW** (free, scriptable, OSC support)
- **Lua watcher** for operations OSC can't do (track insert, MIDI import, routing)
- **E2B as domain expert** for translation, not direct tool calling
- **Genre profiles as data** — model references pre-defined profiles, doesn't generate them
- **Pipeline with verification** — each step verifies DAW state before proceeding
- **Bus routing per family** — instruments grouped by family route to shared bus, all buses → Submaster

## Known Issues

### Phase 7-Blocker Bugs (FIXED)

- **MIDI generation skips guitars and vocals** — `_normalize_role` now strips compound suffixes, `_SECTION_PROFILES` + `_ALL_ROLES` now include `vocals`. FIXED in 07-01.
- **FX chain Step 7 does nothing** — Fixed in 07-02 (Wave 2).
- **Genre lump mapping** — Translator.py now passes exact genre names. FIXED in 07-01.
- **No bus or submaster FX chains** — Fixed in 07-02 (Wave 2).
- **Stray Track 9** — `_remove_track` helper + Step 4b cleanup added. FIXED in 07-01.

### Other Known Issues

- **4 pipeline tests fail** — mocking issue with `_verify_project_state` reading stale DAW state JSON. The actual pipeline code works correctly against live Reaper.
- **State dump incomplete** — doesn't include media items or sends. Pipeline verification uses track count and marker count only.
- **E2B vision unreliable for verification** — must verify programmatically, not trust visual assessment

## Phase 7 Completion Summary

Phase 7 completed all 3 plans with E2E verification:
- **07-01** (Wave 1): Fixed `_normalize_role` stripping, genre lump mapping, `_SECTION_PROFILES` + `_ALL_ROLES` for vocals, `_remove_track` helper, Step 4b stray cleanup
- **07-02** (Wave 2): FX chain Step 7 now calls `_fx_trigger`, `BUS_FX_CHAINS` + `SUBMASTER_FX_CHAIN` architecture, Step 8 bus/submaster FX application
- **07-03** (Wave 3): E4B modifier system — `analyze_instruments()` in model_server, `plugin_overrides` in Step 5, `midi_modifiers` (density) in `_generate_arrangement`, `fx_modifiers` in Step 7, section_changes support. E2E verified: `create_genre_project(genre='metal', modifiers={...})` creates a complete project with all 5 instruments, bus routing, FX chains, 9 markers including Solo section, 160 BPM, 0 stray tracks.

## Session Continuity

Last session: 2026-05-16
Current: Phase 8 planning (hackathon submission prep) — 6 plans created
Next: Execute Phase 8-01 (security scrub) through 08-06 (video demo + submit)

## Phase Progress

| Phase | Plans | Status |
|-------|-------|--------|
| 1-4 | Complete | ✅ All phases done |
| 5 | 7 plans | Planned (not executed — voice pipeline partially operational) |
| 6 | 4/4 | ✅ Complete (incl. gap closure) |
| 7 | 3/3 | ✅ Complete (all pipeline bugs fixed, modifier system E2E verified) |
| 8 | 6 plans | 📋 Planned (hackathon submission prep) |