# AudioShuttle — Speak Music Into Existence

_A Kaggle Gemma 4 Good Hackathon Project_

> **TL;DR:** AudioShuttle uses Google's Gemma 4 E4B model as a domain expert to translate natural language voice commands into professional DAW operations. Say "create a metal track with a longer intro and more guitar solos" and a complete, mixed project appears in Reaper.

## Demo

_Demo video coming soon — check the GitHub repo for updates_

## The Problem

Professional audio production has a steep learning curve. DAWs require mouse-and-keyboard workflows that exclude people with motor disabilities, create barriers for musicians who think in music rather than menus, and slow down even experienced producers.

## The Gemma Solution

Gemma 4 E4B changes this. With 81K context, tool-use capabilities, and vision understanding, E4B can:
- **Translate** natural language into precise DAW commands
- **Generate** genre-appropriate MIDI patterns with section awareness
- **Adapt** arrangements dynamically (longer verses, more solos, custom instruments)
- **Route** audio through professional bus/submaster chains with FX
- **Understand** what's happening in the DAW visually via screenshots

## Architecture

```
You speak ──► Whisper STT ──► Gemma 4 E4B ──► OSC Bridge ──► REAPER
                                  │
                  ┌───────────────┴───────────────┐
                  │                               │
          Genre Profiles                   MIDI Generator
          (11 genres,                    (section-aware,
           bus routing,                 160+ patterns)
           FX chains)
```

### Key Components

1. **MCP Server** (Python/FastMCP): AI-agnostic bridge implementing the Model Context Protocol
2. **Gemma 4 E4B**: Domain expert model for natural language translation (81K context, tool-use capable)
3. **OSC Bridge**: Real-time DAW communication via Open Sound Control (sub-millisecond latency)
4. **Genre Profile Database**: 11 genres with tempo, instruments, bus routing, and FX chains
5. **MIDI Generation Engine**: Section-aware pattern generation with 5+ instrument types
6. **Lua Watcher**: Reaper-side script handling track insertion, MIDI import, and routing

## What Makes This "4 Good"

- **Accessibility:** Voice-controlled music production removes barriers for motor-impaired musicians
- **Speed:** From idea to full arrangement in under 2 minutes
- **Simplicity:** Anyone who can describe music can produce it
- **Open:** MIT-licensed, AI-agnostic design works with any LLM

## Quick Start

### Prerequisites

- [REAPER](https://reaper.fm) 7+ (free evaluation) running with OSC enabled (ports 8000/9000)
- Docker and Docker Compose (for containerized setup)
- ~12GB disk space for model files

### 1. Download Model Files

Place these in `./models/`:
- `gemma-4-E4B-it-UD-Q4_K_XL.gguf` — Main model (~12GB)
- `gemma-4-e4b-mmproj-BF16.gguf` — Vision projection

### 2. Start the Stack

```bash
docker compose up
```

### 3. Set Up REAPER

1. Open REAPER
2. Go to Preferences → Control/OSC/web
3. Add OSC control surface: Local port 8000, Remote port 9000
4. Run the Lua watcher script from `scripts/__startup.lua`

### 4. Use

```bash
# Via MCP client (Claude, Gemini, etc.)
# Or use the integrated voice pipeline (Alt+Space)
```

### Example Commands

| Command | What Happens |
|---------|-------------|
| "create a rock project" | 5 tracks + bus/Submaster with FX chains, 8-section MIDI |
| "create a metal project with more solos" | Same + added Solo section, higher lead guitar density |
| "make it 140 BPM in D minor" | Adjusts tempo and key |
| "load drums with ReaSynDr" | Adds reverb to snare |
| "mute the bass in the chorus" | Section-aware muting (requires vision) |

## Project Structure

```
audioshuttle/
├── src/audioshuttle/
│   ├── osc_bridge.py        # OSC + DAW communication
│   ├── translator.py        # E4B model prompt + dispatch
│   ├── model_server.py      # LLM server lifecycle
│   ├── genre_profiles.py    # Genre database + FX chains
│   ├── cli.py               # CLI + MCP server entry
│   └── config.py            # Configuration
├── scripts/
│   └── __startup.lua        # Reaper Lua watcher
├── Dockerfile                # Audioshuttle container
├── Dockerfile.e4b           # E4B model container
├── docker-compose.yml        # Orchestration
└── tests/                   # 200+ passing tests
```

## Built With

- **Gemma 4 E4B** — Google's most capable model for domain expertise + tool use
- **llama.cpp** — Efficient inference on consumer hardware
- **REAPER** — Professional DAW with Linux native support
- **FastMCP** — Python MCP framework
- **Whisper** — STT for voice pipeline (faster-whisper)

## Team

Created for the [Kaggle Gemma 4 Good Hackathon](https://kaggle.com/competitions/gemma-4-good).

## License

MIT — see [LICENSE](LICENSE)
