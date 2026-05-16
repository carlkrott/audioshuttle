# Project State — AudioShuttle

## Project Reference

**Goal:** Build an AI-agnostic MCP server that bridges any LLM to Reaper DAW, enabling voice/text control of professional audio production for accessibility.

**Competition:** Kaggle Gemma 4 Good Hackathon
**Deadline:** ~May 19, 2026 (12 days)
**Repository:** /home/korphaus/audioshuttle/

## Current Position

Phase: Phase 7 (Pipeline Hardening) — IN PROGRESS
Status: Phase 6 complete but E2E testing revealed 5 pipeline bugs. Phase 7 addresses all of them: MIDI generation gaps, FX chain application never implemented, genre lump mapping, no bus/submaster FX, stray tracks. Also adds E4B modifier system for dynamic genre adaptation.
Last activity: 2026-05-16 — Phase 7 plans created

Progress: [▓▓▓▓▓▓▓▓▓░] 80% (planning Phase 7)

## Verified Working

| Component | Status | Notes |
|-----------|--------|-------|
| Reaper 7.71 | ✅ Running | OSC on 8000/9000, Lua watcher alive with tick counter |
| MCP server | ✅ 4 tools | daw_command, daw_state, daw_thinking, daw_interrupt |
| Voice pipeline | ✅ Working | Alt+Space → Whisper → E2B → OSC → Reaper |
| MIDI generator | ⚠️ Partial | Section-aware arrangement works but guitars/vocals get zero MIDI (_normalize_role bug + missing active_roles) |
| Multimodal E2B | ✅ Working | Port 8093, vision confirmed, streaming thinking/content |
| Thinking overlay | ✅ Working | PyQt6 floating window, JSONL log |
| generate_project | ✅ Working | Creates tracks + MIDI + plugins, flat layout |
| create_genre_project | ⚠️ Partial | 9-step pipeline works but: FX chain iteration does nothing (bug), genre lumping forces metal→rock, no bus/submaster FX |
| create_send routing | ✅ Working | Full routing infrastructure for bus→submaster routing |
| genre_profiles | ✅ Working | 11 genres, 8 instrument families, 7 FX chain types |
| 224 unit tests | ✅ Most passing | 4 mocking-related failures in pipeline tests (non-functional) |

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

### Phase 7-Blocker Bugs (in progress)

- **MIDI generation skips guitars and vocals** — `_normalize_role` now strips compound suffixes, `_SECTION_PROFILES` + `_ALL_ROLES` now include `vocals`. FIXED in 07-01.
- **FX chain Step 7 does nothing** — Fixed in 07-02 (Wave 2).
- **Genre lump mapping** — Translator.py now passes exact genre names. FIXED in 07-01.
- **No bus or submaster FX chains** — Fixed in 07-02 (Wave 2).
- **Stray Track 9** — `_remove_track` helper + Step 4b cleanup added. PARTIALLY FIXED in 07-01.

### Other Known Issues

- **4 pipeline tests fail** — mocking issue with `_verify_project_state` reading stale DAW state JSON. The actual pipeline code works correctly against live Reaper.
- **State dump incomplete** — doesn't include media items or sends. Pipeline verification uses track count and marker count only.
- **E2B vision unreliable for verification** — must verify programmatically, not trust visual assessment

## Phase 6 Completion Summary

All 4 plans completed in 4 waves:
- **06-01** (Wave 1): `genre_profiles.py` — 11 genres, 8 families, 7 FX chain types, 14 tests passing
- **06-02** (Wave 2): `create_genre_project()` — 9-step pipeline, bus routing, FX chains, watcher hardening, 13/17 tests passing
- **06-03** (Wave 3): SYSTEM_PROMPT updated with genre detection, MCP dispatch wired, 22 E2E tests passing
- **06-04** (Wave 4, gap closure): Track index bug, marker enumeration, watcher FX timeout — all 3 fixed

## Phase 7 Planning

E2E testing of `create_genre_project` with live Reaper revealed 5 pipeline bugs not caught by unit tests:
1. MIDI generation skips guitars/vocals (HIGH)
2. FX chain Step 7 never calls _fx_trigger (HIGH)
3. Genre lump mapping forces metal→rock (LOW)
4. No bus/submaster FX chains (MEDIUM)
5. Stray Track 9 (LOW)

Phase 7 also adds the E4B modifier system for dynamic genre adaptation.

## Session Continuity

Last session: 2026-05-16
Stopped at: Phase 7-01 executed and committed
Next: Execute Phase 7-02 (FX chain application) — depends on 07-01 completing first

## Phase Progress

| Phase | Plans | Status |
|-------|-------|--------|
| 1-4 | Complete | ✅ All phases done |
| 5 | 7 plans | Pending |
| 6 | 4/4 | ✅ Complete (incl. gap closure) |
| 7 | 1/3 | ⚠️ 07-01 complete, 07-02+03 pending |
| 8 | 1 plan | Pending (arrangement engine research + plan exist) |