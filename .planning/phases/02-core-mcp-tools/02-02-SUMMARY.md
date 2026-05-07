---
phase: 02-core-mcp-tools
plan: 02
status: complete
files_modified:
  - src/audioshuttle/osc_bridge.py
  - src/audioshuttle/server.py
  - src/audioshuttle/models.py
  - tests/test_osc_bridge.py

tech_stack:
  added: []

patterns:
  - "FX parameter control via /track/N/fx/N/fxparam/N/value"
  - "FX bypass via /track/N/fx/N/bypass (1=bypassed, 0=active)"
  - "Action triggering via /action with command_id"
  - "Track arm via /track/N/recarm"
  - "Toggle pattern: /repeat and /click with no args"

key_files:
  - path: "src/audioshuttle/osc_bridge.py"
    note: "Added set_fx_param(), fx_bypass(), trigger_action(), set_track_recarm(), toggle_repeat(), toggle_metronome()"
  - path: "src/audioshuttle/server.py"
    note: "Added 6 MCP tools: set_fx_param, fx_bypass, trigger_action, set_track_arm, toggle_repeat, toggle_metronome"
  - path: "src/audioshuttle/models.py"
    note: "Added FXState model for future FX state tracking"

decisions:
  - "FX indices are 0-based (matches Reaper OSC convention)"
  - "FX bypass: 1=bypassed, 0=active (Reaper convention, inverted from expectation)"
  - "FXState model defined but NOT added to DAWState yet — Reaper doesn't proactively send FX state"
  - "Action command_id validation: must be > 0"
---

## Plan 02-02 Summary: FX Control, Actions, Arm, Toggles

### What was done
- **FX parameter control**: `set_fx_param(track, fx, param, value)` — 0-based FX/param indices, value clamped to [0.0, 1.0]
- **FX bypass**: `fx_bypass(track, fx, bypass)` — Reaper convention: 1=bypassed, 0=active
- **Action triggering**: `trigger_action(command_id)` — escape hatch for any Reaper action
- **Track arm**: `set_track_recarm(track, arm)` — arm/disarm for recording
- **Repeat toggle**: `toggle_repeat()` — sends `/repeat` with no args
- **Metronome toggle**: `toggle_metronome()` — sends `/click` with no args
- **FXState model**: Defined for future FX state tracking (not wired to DAWState yet)
- **16 new tests**: FX methods (6), actions (5), track arm (3), FXState model (2)
- **6 new MCP tools**: set_fx_param, fx_bypass, trigger_action, set_track_arm, toggle_repeat, toggle_metronome

### Verification
- 63 tests pass (47 from Plan 01 + 16 new)
- Server creates with 18 MCP tools total
- All address validation covers new patterns

### Commit
`13135eb` — feat(02): add OSC validation, transport seek, FX control, master control, actions, toggles
