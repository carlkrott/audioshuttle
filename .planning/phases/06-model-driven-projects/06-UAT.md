# Phase 6 UAT — Model-Driven Project Generation

## Phase Goal
E2B model auto-generates complete genre-aware projects with buses, FX chains, and per-section MIDI. Pipeline with state verification between steps.

## Summary References
- 06-01-SUMMARY: Genre profile database (11 genres, 8 families, FX chains)
- 06-02-SUMMARY: create_genre_project pipeline (9-step, bus routing, FX)
- 06-03-SUMMARY: SYSTEM_PROMPT genre detection, MCP dispatch wiring

## Test Results

| # | Test | Status | Notes |
|---|------|--------|-------|
| 1 | Genre profile data completeness | ✅ PASS | 11 genres, 8 families, 7 FX chains, all populated |
| 2 | Helper functions (case, fallback, tempo, FX) | ✅ PASS | Case-insensitive, rock fallback, tempo override, FX chain resolution |
| 3 | FX chain structure consistency | ✅ PASS | Uses name/type keys, bridge code uses name key |
| 4 | SYSTEM_PROMPT genre guidance | ✅ PASS | create_genre_project in prompt, genre detection rules, backward compat |
| 5 | TOOL_SCHEMAS registration | ✅ PASS | create_genre_project with 6 params (genre, tempo, key, scale, custom_instruments, custom_sections) |
| 6 | MCP server dispatch | ✅ PASS | create_genre_project wired in _execute_tool() |
| 7 | Live: Rock project creation | ⚠️ PARTIAL | 3/6 tracks created, FX on 2 tracks, MIDI on all 6 |
| 8 | Live: Bus routing | ❌ FAIL | Guitars Bus not created (track index bug) |
| 9 | Live: Markers | ❌ FAIL | Markers created in Reaper but not in daw_state JSON |
| 10 | Live: Submaster | ❌ FAIL | Submaster not created (track index bug) |

## Issues Found

### Issue 1: Track Index Mapping Bug (BLOCKER)
**Severity:** High
**Symptom:** Bus and Submaster tracks overlap with instrument tracks
**Root cause:** `instrument_track_map` is populated in Step 5 but referenced in Step 4 where it's still empty
**Fix:** Move `instrument_track_map` population to Step 3 (after track creation)
**File:** `osc_bridge.py` lines 1402, 1410, 1424-1427

### Issue 2: Marker Verification False Negative (MEDIUM)
**Severity:** Medium
**Symptom:** Markers are created in Reaper but verification reads 0 markers
**Root cause:** Lua `dump_state()` doesn't include markers in JSON output
**Fix:** Add `EnumProjectMarkers` loop to `dump_state()` in `__startup.lua`
**File:** `__startup.lua` lines 40-118

### Issue 3: Watcher FX Crash (BLOCKER)
**Severity:** High
**Symptom:** Lua watcher dies during FX application, killing the pipeline
**Root cause:** `dump_state()` blocks the defer loop (O(tracks × FX)), starving FX trigger processing
**Fix:** Increase FX timeout to 10s, add liveness gate before each FX trigger, reduce state dump frequency
**File:** `osc_bridge.py` lines 1538-1561

## Diagnosis Summary

All 3 bugs diagnosed by parallel debug agents:

1. **Track index bug** — `instrument_track_map` populated too late (Step 5 vs Step 3). Bus/Submaster indices calculate as 7/8 instead of 13/14.
2. **Marker bug** — `dump_state()` never enumerates markers. Python reads `state_data.get("markers", [])` → always `[]`.
3. **Watcher crash** — `dump_state()` is O(tracks × FX) and blocks the defer loop. FX triggers time out at 4s. Not a crash — the loop is blocked, not dead.

## Fix Plan Created

**06-04-PLAN.md** — 3 tasks:
1. Fix track index mapping (move instrument_track_map to Step 3)
2. Add marker enumeration to Lua dump_state()
3. Fix watcher FX timeout and liveness check

## Summary

- **Tests passed:** 6/10
- **Issues:** 3 (2 blockers, 1 medium)
- **Fix plan:** 06-04-PLAN.md ready for execution
- **Status:** FIXES READY
