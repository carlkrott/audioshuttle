# AudioShuttle Demo Walkthrough

## Screen Layout

Split screen:
- **Left half:** Reaper DAW with 5-track project
- **Right half:** Terminal (top) + Chromium browser (bottom)

## Setup

1. Reaper open with 5-track test project:
   - Track 1: Drums
   - Track 2: Bass
   - Track 3: Vocals
   - Track 4: Guitar
   - Track 5: Synth

2. Reaper OSC enabled (Preferences → Control/OSC/web → Add OSC device, mode: bidirectional, port 8000/9000)

3. Terminal: Gemini CLI configured with AudioShuttle MCP server

4. Browser: `http://localhost:8765` — AudioShuttle dashboard

## Demo Script

### Part 1: Setup (0:00 - 0:13)

| Time | Screen Left (Reaper) | Screen Right (Terminal/Browser) | Narration |
|------|---------------------|-------------------------------|-----------|
| 0:00-0:05 | Reaper open, OSC settings window showing port 8000/9000 | — | "First, Reaper's OSC configuration — bidirectional on ports 8000 and 9000." |
| 0:05-0:08 | User closes settings → 5-track project visible | — | "A standard project with five tracks: drums, bass, vocals, guitar, synth." |
| 0:08-0:13 | Reaper running | Terminal: user runs `audioshuttle` → server starts, browser opens | "Starting AudioShuttle — the dashboard shows connection status." |

### Part 2: Typed Commands (0:13 - 0:26)

| Time | Screen Left (Reaper) | Screen Right (Terminal/Browser) | Narration |
|------|---------------------|-------------------------------|-----------|
| 0:13-0:16 | Reaper running | Terminal: user types in Gemini CLI: "mute the drums" | "Natural language commands via Gemini CLI..." |
| 0:16-0:18 | Drums track mutes (M button lights up) | — | "...Gemma translates to an OSC mute command." |
| 0:18-0:20 | Reaper running | Terminal: "unmute the drums" | |
| 0:20-0:22 | Drums track unmutes | — | |
| 0:22-0:24 | Reaper running | Terminal: "pan the guitar left" | |
| 0:24-0:26 | Guitar pan knob turns left | — | |
| 0:26-0:28 | Reaper running | Terminal: "set vocals volume to 80 percent" | |
| 0:28-0:30 | Vocals fader moves to 80% | — | |

### Part 3: Voice Commands (0:30 - 0:50)

| Time | Screen Left (Reaper) | Screen Right (Terminal/Browser) | Narration |
|------|---------------------|-------------------------------|-----------|
| 0:30-0:33 | Reaper running | User holds Alt+Space → "turn up the drums a little" | "Now voice commands. Hold Alt+Space, speak, release." |
| 0:33-0:36 | Drums fader moves up slightly | Browser shows: "turn up the drums a little" → cleaned → command | "Gemma cleans the Whisper output and translates to a volume command." |
| 0:36-0:39 | Reaper running | User holds Alt+Space → "pan the bass to the left" | |
| 0:39-0:42 | Bass pan moves left | — | |
| 0:42-0:45 | Reaper running | User holds Alt+Space → "unmute the synth" | |
| 0:45-0:48 | Synth unmutes | — | |

### Part 4: Web Dashboard (0:48 - 1:00)

| Time | Screen Left (Reaper) | Screen Right (Browser) | Narration |
|------|---------------------|----------------------|-----------|
| 0:48-0:52 | Reaper running | Browser: Home tab — connection pulse, transport buttons, command history | "The web dashboard — connection status, transport controls, command history with replay." |
| 0:52-0:55 | Reaper running | Browser: MIDI tab — generate drum pattern | "The MIDI pattern generator for quick ideas." |
| 0:55-0:58 | Reaper running | Browser: Log tab — color-coded command log | "Full command log with level filtering." |
| 0:58-1:00 | Reaper running | Browser: Shortcuts tab — all 20 MCP tools | "Complete reference of all 20 MCP tools." |

## Exact Commands Used

### Typed (Gemini CLI):
1. "mute the drums" → `set_track_mute(drums, true)`
2. "unmute the drums" → `set_track_mute(drums, false)`
3. "pan the guitar left" → `set_track_pan(guitar, -0.7)`
4. "set vocals volume to 80 percent" → `set_track_volume(vocals, 0.8)`

### Voice (Alt+Space):
5. "turn up the drums a little" → `set_track_volume(drums, +0.1)`
6. "pan the bass to the left" → `set_track_pan(bass, -0.5)`
7. "unmute the synth" → `set_track_mute(synth, false)`

## Key Moments to Emphasize

1. **Gemma running locally** — no cloud, no API costs, no latency
2. **Two-brain architecture** — external AI for creativity, Gemma for precision
3. **Accessibility story** — anyone who can speak can control a DAW
4. **20 MCP tools** — works with any LLM client (Gemini, Claude, etc.)
