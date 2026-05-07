# Project State — AudioShuttle

## Project Reference

**Goal:** Build an AI-agnostic MCP server that bridges any LLM to Reaper DAW, enabling voice/text control of professional audio production for accessibility.

**Competition:** Kaggle Gemma 4 Good Hackathon
**Deadline:** ~May 19, 2026 (12 days)
**Repository:** /home/korphaus/audioshuttle/

## Current Position

Phase: Phase 1 Foundation — ready for execution
Status: Environment validated, ready to scaffold server
Last activity: 2026-05-07 — Reaper installed, OSC confirmed

Progress: [▓░░░░░░░░░] 5%

## Verified Working

| Component | Status | Notes |
|-----------|--------|-------|
| Reaper 7.71 | ✅ Installed | pacman package, running |
| OSC bidirectional | ✅ Confirmed | Transport play/stop + real-time feedback |
| OSC track commands | ⚠️ Sent, not visible | Commands sent without error, changes not reflected in UI — debug later |
| Python 3.14 venv | ✅ Created | .venv/ with python-osc |
| Gemma E4B (chat) | ✅ Running | localhost:8090, CPU CCD0 |
| Gemma E2B model file | ✅ Available | 3GB UD-Q4_K_XL, not yet loaded |
| RX 6950 XT | ✅ Free | 16GB VRAM, ~16MB used |
| llama-server binary | ✅ Available | /usr/bin/llama-server |

## Key Resources

| Resource | Location | Notes |
|----------|----------|-------|
| Reaper config | ~/.config/REAPER/ | OSC on 8000/9000 |
| Reaper OSC patterns | ~/.config/REAPER/OSC/Default.ReaperOSC | 531 lines, full command reference |
| Test project | ~/audioshuttle/test-project.RPP | 5 tracks: Drums, Bass, Vocals, Guitar, Synth |
| E2B model | ~/models/llm/gemma-4-e2b-it/gemma-4-E2B-it-UD-Q4_K_XL.gguf | 3GB symlink |
| E4B model (running) | localhost:8090 | Already serving |
| Python venv | ~/audioshuttle/.venv/ | python-osc installed |

## Reaper OSC Command Reference (from Default.ReaperOSC)

**Transport:** `/play`, `/stop`, `/record`, `/pause`, `/rewind`, `/forward`
**Track:** `/track/{n}/volume` (0-1 float), `/track/{n}/mute` (0/1), `/track/{n}/solo` (0/1), `/track/{n}/pan` (-1 to 1)
**Track info:** `/track/{n}/name` (string), `/track/{n}/number/str`
**Master:** `/master/volume`, `/master/pan`, `/master/vu`
**FX:** `/track/{n}/fx/{n}/fxparam/{n}/value` (0-1 float)
**Actions:** `/action {command_id}` (integer)
**Markers:** `/marker/{n}/name`, `/marker/{n}/time`

## Decisions

- **Python over Rust** for 12-day timeline
- **Prompt engineering first**, LoRA fine-tuning post-hackathon
- **Reaper as DAW** (free, scriptable, OSC support)
- **Everything on this machine** — localhost OSC
- **Web UI + tray** for setup/status only (not a mixing console)
- **fastmcp** for MCP server implementation
- **Gemma E2B Q4_K_XL** as embedded domain expert model

## Known Issues

- **OSC track commands not visually reflected in Reaper**: `/track/1/mute 1` sent without error but Reaper UI didn't change. Transport commands (`/play`, `/stop`) DO work. Possible causes: (1) Reaper needs the track to be selected first via `/track/1/select`, (2) OSC pattern needs explicit track addressing, (3) Reaper OSC config needs adjustment. Will debug with proper tooling.

## Blockers/Concerns

- OSC track control visibility needs debugging (non-blocking — transport works)
- ROCm GPU inference on RX 6950 XT needs testing for E2B
- SSL12 audio interface not detected by WirePlumber (affects STT)
- No fine-tuning in v1 — relies entirely on prompt engineering

## Session Continuity

Last session: 2026-05-07
Stopped at: Environment validated, Reaper+OSC confirmed, test project created
Resume: Run `/gsd-plan-phase 1` to scaffold the MCP server
