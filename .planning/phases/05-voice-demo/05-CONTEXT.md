# Phase 5 Context — Voice + Demo

> Decisions locked for researcher and planner. No re-visiting these during execution.

## A. Voice Pipeline Architecture

### Flow (two modes)

```
"Cleanup Audio" toggle OFF:
  Mic → Whisper STT → raw text → interpret_command (E2B) → OSC → DAW

"Cleanup Audio" toggle ON:
  Mic → Whisper STT → raw text → E2B formatting pass → cleaned text → interpret_command (E2B) → OSC → DAW
```

### Key Decisions

1. **"Cleanup Audio" toggle** — Simple checkbox in web UI Input tab. When ON, Whisper output passes through E2B formatting pass before hitting interpret_command. When OFF, raw Whisper text goes straight to interpret_command.

2. **Formatting pass scope — LIGHT NORMALIZATION**, not just disfluency removal:
   - Remove filler words ("um", "uh", "like", "you know")
   - Fix false starts and repetitions
   - Normalize DAW-specific language: "make the vocals louder" → "turn up the vocals"
   - Collapse run-on sentences into clean commands
   - Does NOT convert to OSC — that's interpret_command's job. The formatter just makes the text cleaner for the translator.

3. **Global hotkey (Alt+Space)** — Works system-wide, even when DAW is focused. Not browser-only. This interfaces with the MCP server directly, not through a third-party LLM client. The LocalMind project (in `~/.planning/`) had a working dictation implementation with Whisper — reuse that pattern for the hotkey + recording + transcription flow. The hotkey captures audio from the default system microphone, records while held, sends to Whisper on release.

4. **No fallback when E2B is down** — If model server isn't running, voice pipeline shows an error and is non-functional. The model is integral to the system. No degraded "raw text only" mode for voice.

5. **E2B parallelism** — Model server already supports parallel requests. The formatting pass uses the same model server endpoint. No need for a second model instance.

6. **Voice pipeline is MCP-server-native** — Voice input goes directly to the AudioShuttle MCP server, not through an external LLM client. This is the "standalone" voice interface — the user doesn't need Gemini/Claude/Codex to use voice commands.

## B. README Narrative

### Locked Direction

**Gemma-centric accessibility story.** The hero narrative is: "Gemma enables the walk-in recording studio."

- NOT "here's a technical MCP server"
- NOT "here's a DAW controller"
- YES "Gemma's lightweight efficiency bridges the gap between speaking and professional audio production"
- YES "The first step toward a literal walk-in recording studio where anyone who can speak can produce music"

### README Structure

1. **Hook:** Gemma enables walk-in recording studio for accessibility
2. **Problem:** Professional audio production requires complex mouse/keyboard workflows
3. **Solution:** Gemma as the translation layer between human speech and DAW commands
4. **Gemma qualities to emphasize:** Lightweight (runs on consumer GPU), fast enough for real-time, multilingual capability (via Whisper), accessible (no training needed)
5. **Architecture:** User → Speech → Gemma E2B → OSC → DAW
6. **Quick start:** Under 5 commands
7. **20 MCP tools table**

## C. Demo Walkthrough

### Screen Layout

Split screen:
- **One half:** Reaper DAW (full height)
- **Other half:** Terminal (top quarter) + Chromium browser (bottom quarter)

### Shot-by-Shot Flow

| Step | Action | Duration | On Screen |
|------|--------|----------|-----------|
| 1 | Reaper open, OSC settings window visible showing default parameters | 5s | Reaper with settings dialog |
| 2 | User closes OSC settings → plain Reaper with 5-track project | 3s | Reaper tracks: Drums, Bass, Vocals, Guitar, Synth |
| 3 | User opens terminal, starts Gemini CLI (`gemini`) with MCP server pre-loaded via stdio | 5s | Terminal: gemini starting |
| 4 | Chromium opens below terminal → AudioShuttle web page | 3s | Browser shows dashboard |
| 5 | User types test command in Gemini CLI | 3s | Terminal: typing |
| 6 | Reaper responds — scripted sequence: mute drums → unmute drums → pan guitar left → set vocals to 80% | 10s | Reaper faders/pans moving |
| 7 | User holds Alt+Space → dictates "turn up the drums a little" | 5s | Terminal shows mic active |
| 8 | Reaper drums fader moves up | 3s | Reaper fader change |
| 9 | User holds Alt+Space → dictates "pan the bass to the left" | 5s | Terminal shows mic active |
| 10 | Reaper bass pan moves left | 3s | Reaper pan change |
| 11 | User holds Alt+Space → dictates "unmute the synth" | 5s | Terminal shows mic active |
| 12 | Reaper synth unmutes | 3s | Reaper mute toggle |

### Intro/Outro

User will produce separately: project name, credits (including Google, energy provider, and the AI assistant), and other submission details.

### Technical Requirements for Demo

- **MCP stdio mode** — MCP server must start alongside Gemini CLI (standard MCP server behavior). Browser auto-open should be OFF by default in stdio mode.
- **Browser auto-open toggle** — Must be configurable. Default: OFF in stdio mode, ON in standalone mode.
- **Alt+Space global hotkey** — Must work while Reaper has focus
- **Reaper test project** — 5 tracks: Drums, Bass, Vocals, Guitar, Synth (with stems, user will prepare)

### Scripted Command Sequence (typed in Gemini CLI)

```
1. "mute the drums"          → drums mute in Reaper
2. "unmute the drums"        → drums unmute
3. "pan the guitar left"     → guitar pans left
4. "set vocals to 80%"       → vocal fader moves
5. (switch to voice)
6. "turn up the drums a little"  → drums fader up (voice)
7. "pan the bass to the left"    → bass pans left (voice)
8. "unmute the synth"            → synth unmutes (voice)
```

## D. Dashboard Features (10 Additions)

All 10 are planned for this phase. Priority order by impact:

### D1. MIDI Pattern Generator (New Tab: "MIDI")
- 16-bar step sequencer grid
- Dropdown for instrument role: Melody, Rhythm, Lead, Drums
- "Randomize" button fills the grid with pseudo-random pattern appropriate for the selected role
- Display as a grid (bars × steps, 16×16 or 16×4 depending on subdivision)
- Pattern rules per role:
  - **Drums:** Kick on 1 and 3, snare on 2 and 4, hi-hat every 8th note (with random variation)
  - **Rhythm:** Repetitive 2-4 bar pattern, chord tones
  - **Lead:** More melodic, wider intervals, occasional rests
  - **Melody:** Constrained to scale, stepwise motion with occasional leaps

### D2. E2B Track Assignment (MIDI Tab)
- Text below the pattern grid: "Where do you want this? Describe the instrument, key, and tempo to add it."
- Text input box + "Send" button
- Sends to E2B which formats as a DAW command to create/populate a track with the MIDI pattern
- Example input: "Add this as a drum track at 120 BPM in C minor"
- E2B translates to: create track → set tempo → insert MIDI data

### D3. Command History with Replay (Home Tab)
- Shows last 20 commands with timestamps
- Each entry shows: command text, tool called, success/error status
- Click any entry to re-execute the same command

### D4. Track Presets (Output Tab)
- Save current mixer state (all track volumes, mutes, solos, pans) as named preset
- Load preset to restore all settings at once
- Stored in `~/.audioshuttle/presets/` as JSON files

### D5. Live Connection Pulse (Home Tab)
- Animated green pulsing dot when Reaper connected
- Static red dot when disconnected
- Subtle CSS animation, no JavaScript framework

### D6. Command Log with Color Coding (New Tab: "Log")
- Chronological log of all MCP tool calls
- Green = success, yellow = warning/error recovered, red = error
- Filterable by status (all/success/warning/error)
- Shows: timestamp, tool name, parameters, result

### D7. Quick Command Buttons (Home Tab)
- Transport controls: ▶ Play, ⏹ Stop, ⏺ Record, ⏸ Pause
- One-click, no typing needed
- Directly calls MCP tools

### D8. DAW State Snapshot (Output Tab)
- "Export State" button → downloads full DAW state as JSON
- Includes: all track volumes/mutes/solos/pans, master volume, transport state, tempo
- "Import State" to restore from JSON (future: could be used for project templates)

### D9. Keyboard Shortcuts Reference (New Page/Modal)
- Lists all 20 MCP tools with example commands
- Searchable/filterable
- Shows: tool name, description, example usage, parameters

### D10. Model Status Card (Home Tab)
- Shows: E2B model loaded (yes/no), last inference time (ms), average tokens/sec
- GPU VRAM usage if available
- Model server uptime
- Updates on each inference call

## Deferred Ideas (Post-Hackathon)

These came up but are explicitly out of scope for Phase 5:
- LoRA fine-tuning for E2B on DAW-specific language
- Real-time audio waveform visualization
- Tempo/BPM tap detector
- Frequency analyzer overlay
- Plugin/AU/VST scanning and control
- Multi-DAW support (Ardour, Ableton, Logic) — architecture supports it but not tested
- User authentication for web UI
- Cloud deployment / remote DAW control
- Collaborative mixing (multiple users, same project)
