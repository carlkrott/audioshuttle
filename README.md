# AudioShuttle — Speak Music Into Existence

_A Kaggle Gemma 4 Good Hackathon Project_

> **TL;DR:** AudioShuttle uses Google's Gemma 4 E4B model as a domain expert to translate natural language voice commands into professional DAW operations. Say "create a metal track with a longer intro and more guitar solos" and a complete, mixed project appears in Reaper.

## Demo

```bash
# Full project from natural language (verified working):
curl "http://localhost:8765/replay?cmd=create+a+rock+project+called+Midnight+Drive+at+130+bpm"
# → 8 tracks (Keys, Lead Guitar, Bass, Vocals, Rhythm Guitar, Drums,
#             Guitars Bus, Submaster) + 9 markers + colors + tempo
```

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

### Docker Stack

```
┌──────────────────────────────────────────────────────────┐
│  HOST (Linux with AMD ROCm / NVIDIA GPU)                  │
│                                                           │
│  ┌──────────────────────┐    ┌──────────────────────┐    │
│  │  e4b (Docker)        │    │  audioshuttle (Docker)│    │
│  │  llama.cpp + Gemma 4 │◄──►│  FastMCP + Web UI    │    │
│  │  E4B Q4_K_XL         │    │  Port 8765           │    │
│  │  Port 8102           │    │  NL → tool dispatch  │    │
│  │  99 GPU layers       │    └──────────┬───────────┘    │
│  └──────────────────────┘               │                 │
│                                  OSC: localhost:8000      │
│                                         ▼                 │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  REAPER 7.71 (host)                                  │ │
│  │  Lua watcher scripts, MIDI import, routing, FX       │ │
│  │  State file: /tmp/audioshuttle_daw_state.json        │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Key Components

1. **E4B Model Container** — llama.cpp with HIPBLAS/ROCm, Gemma 4 E4B Q4_K_XL, 81K context
2. **AudioShuttle Server** — FastMCP-based HTTP server, translates NL → OSC commands
3. **OSC Bridge** — Real-time DAW communication via Open Sound Control
4. **Genre Profile Database** — 11 genres with tempo, instruments, bus routing, and FX chains
5. **MIDI Generation Engine** — Section-aware pattern generation with 5+ instrument types
6. **Lua Watcher** — Reaper-side script handling track insertion, MIDI import, and routing

## What Makes This "4 Good"

- **Accessibility:** Voice-controlled music production removes barriers for motor-impaired musicians
- **Speed:** From idea to full arrangement in under 1 minute
- **Simplicity:** Anyone who can describe music can produce it
- **Open:** MIT-licensed, AI-agnostic design works with any LLM

## Quick Start

### Prerequisites

- **REAPER 7+** running with OSC enabled (Preferences → Control/OSC/web → port 8000/9000)
- **Docker + Docker Compose** with GPU passthrough support
- **AMD ROCm** drivers (Linux) OR **NVIDIA Container Toolkit**
- **~6GB disk space** for model files (Q4_K_XL quantization)

### 1. Download Model Files

Place these in `./models/`:
- `gemma-4-E4B-it-UD-Q4_K_XL.gguf` — Main model (~4.8GB)
- `gemma-4-e4b-mmproj-BF16.gguf` — Vision projection (~946MB)

### 2. Build and Start

```bash
docker compose build --no-cache   # ~30 min (ROCm compilation)
docker compose up -d              # Start both containers
docker compose logs -f            # Watch startup progress
```

Wait for both containers to become healthy (~2 min for E4B model load).

### 3. Set Up REAPER

1. Open REAPER
2. Go to Preferences → Control/OSC/web
3. Add OSC control surface: Local port 8000, Remote port 9000
4. Run the Lua watcher script: **Actions → Load Script → `reaper_scripts/__startup.lua`**
   - Or install permanently to `~/.config/REAPER/Scripts/__startup.lua`

### 4. Create Your First Project

```bash
# Open the Web UI
open http://localhost:8765

# Or use curl:
curl "http://localhost:8765/replay?cmd=create+a+rock+project+called+My+Songs+at+120+bpm"

# Check the result:
echo "dump" > /tmp/audioshuttle_state_request && sleep 3 && \
  python3 -c "import json; d=json.load(open('/tmp/audioshuttle_daw_state.json')); print(json.dumps(d, indent=2))"
```

### Example Commands

| Command | What Happens |
|---------|-------------|
| `create a rock project` | 6 tracks + Guitars Bus + Submaster, 9-section markers, colors |
| `create a metal project at 160 bpm` | Same + heavier instruments, faster tempo |
| `play` / `stop` | Transport control |
| `set track 3 volume to 0.8` | Track level adjustment |
| `pan track 2 hard left` | Stereo panning |

## Project Structure

```
audioshuttle/
├── src/audioshuttle/
│   ├── osc_bridge.py        # OSC + DAW communication (3650+ lines)
│   ├── translator.py        # E4B model prompt + dispatch
│   ├── model_server.py      # LLM server lifecycle
│   ├── genre_profiles.py    # 11 genres, FX chains
│   ├── web_routes/
│   │   └── home.py          # Web UI + /replay endpoint
│   ├── cli.py               # CLI + server entry
│   └── config.py            # Configuration
├── reaper_scripts/
│   └── __startup.lua        # Reaper Lua watcher (13 trigger types)
├── Dockerfile                # Audioshuttle container (Python 3.14-slim)
├── Dockerfile.e4b           # E4B container (multi-stage, ROCm HIPBLAS)
├── docker-compose.yml        # Two-container GPU stack
├── tests/                   # 200+ tests
└── .planning/               # GSD phase planning docs
```

## GPU Support

### AMD ROCm (verified — RX 6950 XT / gfx1030)

The default `Dockerfile.e4b` targets `gfx1030`. For other AMD GPUs, change the cmake flag:

```dockerfile
-DAMDGPU_TARGETS=gfx1100   # RX 7900 XTX
-DAMDGPU_TARGETS=gfx942    # MI300X
```

### NVIDIA

Uncomment the `deploy.resources` section in `docker-compose.yml` and install `nvidia-container-toolkit`.

### CPU Only

Set `N_GPU_LAYERS=0` in `docker-compose.yml` — slower but functional for testing.

## Built With

- **Gemma 4 E4B** — Google's most capable model for domain expertise + tool use
- **llama.cpp** — Efficient inference with ROCm HIPBLAS backend
- **REAPER** — Professional DAW with Linux native support
- **FastMCP** — Python MCP framework
- **Docker** — Containerized deployment with GPU passthrough

## Team

Created for the [Kaggle Gemma 4 Good Hackathon](https://kaggle.com/competitions/gemma-4-good).

## License

MIT — see [LICENSE](LICENSE)
