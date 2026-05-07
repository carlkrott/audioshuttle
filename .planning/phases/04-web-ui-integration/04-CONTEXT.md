---
phase: 04-web-ui-integration
status: decisions_locked
date: 2026-05-07
areas_discussed: [layout, setup, status, demo]
deferred_to_phase_5:
  - "Whisper STT voice input (Alt+Space → mic → text → MCP)"
  - "Live voice command demo with Alt+Space hold-to-talk"
---

# Phase 4 Context — Web UI + Integration

## A. Web UI Layout & Tabs

**Architecture: Multi-tab settings application, NOT a mixer or performance tool.**

The web UI is a bridge configurator. It connects an external AI to a DAW. No faders, no meters, no live visualizations. Just settings, status, and logs.

### Tabs

1. **Home / Status** — Error log (command-line style, errors only), system status indicators
2. **Input (AI Connect)** — Configure the external AI client connection
3. **Output (DAW Connect)** — Configure the DAW target, rescan, customize mappings
4. **(Future: Memory)** — Obsidian vault status, compaction history (stretch goal)

### Input Tab (AI Connect)

- **User-editable connection details**: host, port, auth — whatever the chosen AI client needs
- **Editable system prompt / skill**: A text area exposing the SYSTEM_PROMPT that IntentTranslator sends to the model. The user can customize this to change how the model interprets commands, add domain-specific vocabulary, or adjust behavior. This IS the MCP connection's system prompt.
- **DAW info attachment**: The system prompt automatically includes current DAW details (track names, available commands, OSC mappings) pulled from the Output tab. User sees this appended content but the core prompt is editable.
- **Preset AI clients**: Dropdown with presets (Gemini CLI, Claude Code, etc.) that pre-fill connection details

### Output Tab (DAW Connect)

- **Rescan button**: Triggers E2B to scan the system for running DAWs, auto-detect which one is active, and reconfigure OSC mappings. Also propagates the updated DAW info back to the connected AI (updates the system prompt attachment).
- **DAW preset dropdown**: Select from preset DAW configurations (Reaper, Ardour). Changes OSC address patterns, default ports, available commands.
- **User-editable mappings**: Each OSC output (address pattern, port, etc.) is displayed in an editable table/list. User can customize at their own risk. Changes take effect immediately.
- **DAW auto-detection result**: Shows what DAW was detected, connection status, track count

### Key UX Decisions

- **No live state display**: This is NOT a DAW remote control surface. No faders, no meters, no transport buttons. The web UI configures the bridge; the AI sends commands through it.
- **Error visibility**: Homepage has a command-line style log showing only errors (failed connections, model crashes, OSC timeouts). Scrolling, timestamped, no other noise.
- **Toast toggle**: User can enable/disable system tray toast notifications for errors. Default: enabled.

---

## B. Setup Wizard & Auto-Detection

**On startup, the system auto-configures using the E2B model.**

### Startup Sequence

1. **E2B model loads first** — priority #1, must be running before anything else
2. **E2B scans the system** — checks what DAW is running, confirms loaded settings match presets
3. **Auto-configure**: If Reaper detected → use Reaper OSC patterns. If Ardour detected → use Ardour OSC patterns.
4. **Validate**: E2B confirms settings are correct against what it found
5. **Report status**: Web UI and taskbar icon show connected/error state

### Multi-DAW Support (Demo Presets)

For the hackathon demo, presets are configured for:
- **Reaper** (primary, already working with OSC)
- **Ardour** (secondary, needs OSC address mapping)

The E2B model checks which DAW is actually running and adjusts. The rescan button triggers the same detection flow.

### Error Handling

- **DAW not detected**: Webpage + taskbar icon popup prompt: "Issues connecting to DAW"
- **Model fails to load**: Error logged to homepage, status indicator shows errored state
- **MCP server fails**: Error logged, retry logic, user notified
- **Never silently fail**: All errors visible in the homepage log

### E2B Startup Priority

The E2B model MUST be loaded before the MCP server accepts connections. The model is the brain — without it, only fallback regex parsing works. Startup sequence blocks on model readiness.

---

## C. Status, Memory & Feedback

### Status Indicators (Homepage)

Displayed as simple status badges/pills:

| Indicator | States |
|-----------|--------|
| DAW Connection | Connected / Disconnected |
| MCP Server | Running / Stopped |
| E2B Model | Loaded / Loading / Errored |
| GPU Memory | Used MiB / Total MiB |
| Model State | Running / Compacting / Idle / Errored |

### Memory & Compaction Pipeline

**The E2B model accumulates context across translation sessions.**

1. **Every command/prompt is stored in the model's context memory**
2. **Compaction**: When context fills up, the model compacts — summarizes the session history into a condensed form
3. **Obsidian dump**: After each compaction, the compacted session is written to an Obsidian vault file for reference. This gives the user a searchable history of all DAW interactions.
4. **Skill learning**: Periodically, the model scans the accumulated interaction history and updates its "skill" — an evolving understanding of how this particular user prefers to interact with the DAW (common commands, preferred phrasing, track naming conventions, etc.)
5. **Parallel slot**: The model runs with `--parallel 2` — slot 1 for command translation, slot 2 for the skill-learning/memory context. The skill-learning slot uses max context size.

### Obsidian Vault Structure

```
audioshuttle-memory/
├── sessions/
│   ├── 2026-05-07T16-30-session.md    # Compacted session dump
│   └── ...
├── skills/
│   └── current-skill.md               # Evolving DAW interaction skill
└── README.md                           # Auto-generated index
```

### Error Display

- **Homepage**: Command-line style scrolling log, errors only, timestamped
- **Taskbar**: Toast notification (user toggle on/off, default on)
- **No other logging UI**: The homepage log is deliberately minimal — just errors for visibility

---

## D. Demo Flow & Kaggle Narrative

**The demo shows an AI controlling a DAW through natural language — the accessibility angle for "Gemma 4 Good".**

### Demo Setup (Split Screen)

Left side: **Reaper DAW** with its settings/connections window open, showing tracks
Right side: **Terminal** (Gemini CLI session)

### Demo Script

1. **Terminal opens** → user runs Gemini CLI which triggers the MCP server startup
2. **MCP server starts** → prompts Chromium to open (user toggle: `--no-browser` to disable auto-open on boot), showing the AudioShuttle web UI with system loading → ready
3. **Web UI shows**: DAW connected (Reaper), MCP server running, E2B model loaded, GPU memory stats
4. **User clicks through settings** in the web UI to demonstrate: AI connection is Gemini CLI, DAW is Reaper, system prompt is visible/editable
5. **Chromium minimized** — focus returns to terminal
6. **User types a few text commands** into Gemini CLI: "mute the drums", "turn up the vocals", "play" — each triggers visible changes in Reaper
7. **User holds Alt+Space** → speaks a command via Whisper → voice transcribed to text → sent to MCP server → Reaper responds (level change on a track, EQ on another, transport starts playing)

### Accessibility Narrative

The demo is positioned as: **"Hands-free DAW control for musicians with disabilities."** A musician who can't use a mouse/keyboard can control their entire mix through natural language — either typed or spoken. This is the Kaggle "Gemma 4 Good" angle.

### Key Visual Moments

- Seeing Reaper react in real-time to a spoken command
- The web UI showing the translation pipeline (what the AI understood, what tool it chose)
- The editable system prompt — showing that the skill is customizable
- Error resilience — showing what happens with an unclear command

---

## Deferred to Phase 5

These items are locked into Phase 5 (Voice + Demo), not Phase 4:

- **Whisper STT integration**: The Alt+Space → mic → text pipeline
- **Live voice command demo**: Hold-to-talk voice input
- **Demo video recording**: The actual Kaggle submission video
- **README / submission package**: Documentation for judges

---

## Technical Context (for researcher/planner)

### Existing Infrastructure (from Phases 1-3)

| Component | Status | Location |
|-----------|--------|----------|
| OSC Bridge | 18 tools, 24-pattern validation | `osc_bridge.py` |
| MCP Server | 19 tools (incl. interpret_command) | `server.py` |
| Model Server | E2B on RX 6950 XT, ROCm | `model_server.py` |
| Translator | Model + fallback, SYSTEM_PROMPT | `translator.py` |
| Config | pydantic-settings, all GPU params | `config.py` |
| Tests | 113 passing | `tests/` |
| Optional deps | [web], [stt], [tray] groups | `pyproject.toml` |

### E2B Model Details

- **Model**: gemma-4-E2B-it-UD-Q4_K_XL.gguf (3.18GB, May 4 2026)
- **Binary**: llama-server b9049 (ROCm)
- **GPU**: RX 6950 XT (~2GB VRAM)
- **Port**: 8092
- **Current flags**: `-ngl 99 -t 8 -tb 8 --parallel 1 -c 8192`
- **Phase 4 change**: `--parallel 2` to add skill-learning slot, possibly larger context

### External AI Client: Gemini CLI

- Gemini CLI connects to AudioShuttle's MCP server
- The MCP server exposes 19 tools including `interpret_command`
- Gemini sends natural language → `interpret_command` translates → bridge executes
- The "system prompt" the user edits in the web UI is the SYSTEM_PROMPT in `translator.py`

### DAW Presets Needed

- **Reaper**: Already working, OSC patterns in `_ADDRESS_PATTERNS` (24 patterns)
- **Ardour**: Needs OSC address mapping (similar OSC protocol, different addresses)
