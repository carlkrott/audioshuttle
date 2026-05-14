# Phase 6 Plan 04: Gap Closure — Bug Fixes Summary

## Phase
06-model-driven-projects

## Plan
04 — gap_closure (3 bugs from UAT)

## Execution

### Tasks Completed

| # | Task | Status | Details |
|---|------|--------|---------|
| 1 | Track index mapping bug | ✅ FIXED | Moved `instrument_track_map` population from Step 5 to Step 3 (after track creation, before Step 4 uses it) |
| 2 | Marker enumeration in dump_state() | ✅ FIXED | Added `EnumProjectMarkers` loop to Lua `dump_state()` — markers now appear in JSON output |
| 3 | Watcher FX timeout + liveness gate | ✅ FIXED | Increased FX timeout 4s→10s, added liveness gate before each FX trigger with 15s recovery wait |

### Changes Made

**osc_bridge.py** (3 changes):
1. **Lines 1385-1389** — Populate `instrument_track_map` in Step 3 (after track creation, before Step 4 bus/submaster index calculations)
2. **Lines 1428-1431** — Step 5 now iterates `instrument_track_map.items()` directly (removed duplicate map population)
3. **Lines 1550-1572** — FX loop: liveness gate before each FX trigger + timeout increased from 4s to 10s

**__startup.lua** (1 change):
1. **Lines 115-127** — Added `EnumProjectMarkers` loop to `dump_state()` — markers now included in JSON state output

## Verification

- ✅ Python syntax valid (`python -m py_compile`)
- ✅ `instrument_track_map[inst]` population in Step 3, verified by grep
- ✅ `EnumProjectMarkers` present in Lua file, verified by grep
- ✅ `wait=10.0` in FX trigger, verified by grep
- ✅ Liveness gate logic present before FX trigger in Step 7

## Deviation from Plan

None — all 3 tasks executed exactly as specified in 06-04-PLAN.md.

## Artifacts Created

- `.planning/phases/06-model-driven-projects/06-04-SUMMARY.md` — this file

## Commit

```
fix(06-04): fix 3 pipeline bugs from UAT

- Track index: instrument_track_map populated in Step 3 (was Step 5)
- Markers: EnumProjectMarkers added to Lua dump_state()
- FX timeout: increased to 10s with liveness gate before each trigger
```

## Must-Haves Status

| Must-have | Status |
|-----------|--------|
| create_genre_project('rock') creates all 6 instrument tracks without watcher dying | ✅ Fixed (liveness gate + timeout) |
| Markers appear in Reaper AND are visible in daw_state JSON dump | ✅ Fixed (EnumProjectMarkers) |
| Bus tracks and Submaster are created at correct indices (after all instruments) | ✅ Fixed (instrument_track_map in Step 3) |
| FX chains are applied to all tracks without watcher timeout | ✅ Fixed (10s timeout + liveness gate) |

## Next

- Re-run UAT to verify all 10 tests pass
- Test live rock project creation with correct bus/submaster indices