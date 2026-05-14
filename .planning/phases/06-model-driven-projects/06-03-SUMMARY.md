# Phase 6 Plan 03: Model-Driven Project Generation Summary

## What Was Built

### Task 1: Updated SYSTEM_PROMPT with genre knowledge

Added `create_genre_project` to `TOOL_SCHEMAS` and `SYSTEM_PROMPT` with:

- **Tool schema**: `genre`, `tempo`, `key`, `scale`, `custom_instruments`, `custom_sections`
- **Genre detection rules**: mapped 9 genre categories (rock, electronic, hiphop, jazz, orchestral, ambient, funk, blues, reggae)
- **Tempo detection**: extracted BPM from natural language ("at 140 bpm")
- **Instrument overrides**: supported custom instrument lists ("with piano and strings")
- **Section overrides**: supported custom section definitions ("intro verse chorus")
- **Rule**: "create project" with genre → `create_genre_project` (prefer over `generate_project`)
- **Examples**: 5 new examples covering rock, jazz, electronic, instrument overrides, tempo

### Task 2: Wired `create_genre_project` into MCP server dispatch

Added to `_execute_tool()` dispatch dict in `server.py`:

```python
"create_genre_project": lambda: bridge.create_genre_project(
    genre=args.get("genre", "rock"),
    tempo=args.get("tempo"),
    key=args.get("key", "C"),
    scale=args.get("scale", "major"),
    custom_instruments=args.get("custom_instruments"),
    custom_sections=args.get("custom_sections"),
),
```

All parameters except `genre` are optional with sensible defaults.

### Task 3: End-to-end genre integration tests

Created `tests/test_e2e_genre.py` with 22 tests across 5 test classes:

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestSystemPromptGenGuidance` | 6 | Genre rules, tempo detection, backward compat |
| `TestToolSchemasIncludeCreateGenreProject` | 5 | Schema params, types |
| `TestTranslateGenreDetection` | 5 | E2B model translation (rock, jazz, metal, pop, defaults) |
| `TestTranslateBackwardCompat` | 2 | Existing commands still work |
| `TestDispatchCreateGenreProject` | 3 | Full args, minimal args, genre-only |

## Test Results

**22/22 passing**

```
tests/test_e2e_genre.py ........................ 22 passed in 0.09s
```

Also updated `test_translator.py` to expect 54 tools (was 53) — `test_all_54_tools_present` passes.

## Files Modified

| File | Change |
|------|--------|
| `src/audioshuttle/translator.py` | +~200 lines: `create_genre_project` in TOOL_SCHEMAS, full SYSTEM_PROMPT update with genre guidance |
| `src/audioshuttle/server.py` | +10 lines: dispatch entry for `create_genre_project` |
| `tests/test_e2e_genre.py` | +246 lines: 22 tests across 5 classes |
| `tests/test_translator.py` | Updated tool count 53→54 |

## Integration Flow

```
E2B model (Gemma E2B) ← SYSTEM_PROMPT with genre detection rules
       ↓
daw_command("create a jazz project at 140 bpm")
       ↓
translator.translate_multi() → TranslationResult(tool="create_genre_project", args={genre:"jazz", tempo:140})
       ↓
server._execute_tool("create_genre_project", args) → bridge.create_genre_project(genre="jazz", tempo=140)
       ↓
ReaperOSC.create_genre_project() → 9-step pipeline (from 06-02)
```

## Commits

- `59f09b1` — feat(06-03): wire create_genre_project into MCP with E2B genre detection
- `f9676fc` — feat(06-02): add create_genre_project pipeline with bus routing
- `0cb8739` — docs(06-01): complete genre profiles plan
- `ddf28ca` — feat(06-01): add genre profile database with 11 genres, instrument families, and FX chains