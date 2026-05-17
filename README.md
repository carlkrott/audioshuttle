# AudioShuttle — Speak Music Into Existence

> **Voice-controlled professional music production for the 250M+ people who can't use a mouse.**

_A Kaggle Gemma 4 Good Hackathon Project — Digital Equity & Inclusivity Track_

---

## The Problem

Professional audio production is **mouse-and-keyboard only**. Every DAW operation — from creating a track to setting panning to automating a fade — requires physical interaction that **250 million+ people with motor impairments cannot perform**. This isn't a minor inconvenience. It means professional music production is genuinely inaccessible to anyone with:
- Cerebral palsy, ALS, multiple sclerosis, arthritis
- Limb differences, spinal cord injuries, RSI
- Any condition affecting fine motor control

Current "accessibility" solutions are limited to simple transport controls (play/stop). **No system lets a motor-impaired musician create, arrange, and mix a full project hands-free.**

## The Solution: AudioShuttle

AudioShuttle bridges **natural language voice commands** to a professional DAW using **Gemma 4 E4B as a domain expert translator**. Say "create a rock project called Midnight Drive at 130 BPM with extra guitar solos" and a complete, mixed, full-arrangement project appears in Reaper.

**Gemma 4 E4B is essential here** — not just any LLM:
- **81K context** lets it hold the entire genre profile, arrangement structure, and tool schema in one prompt
- **Tool-use capabilities** let it reason about multi-step DAW orchestration (insert track → name it → set volume → set color → route to bus)
- **Domain expertise** means it understands "rock" isn't just a genre label — it's 6-8 instruments, specific tempo ranges, verse-chorus-solo structure, bus routing patterns

## What It Does (Verified Working)

```
You: "create a rock project called Midnight Drive at 130 bpm"

AudioShuttle → Gemma 4 E4B → 9-step DAW pipeline:
  ✓ Sets tempo to 130 BPM
  ✓ Creates 9 song structure markers (intro → verse → chorus → verse → chorus → solo → chorus → outro)
  ✓ Inserts 8 tracks (Keys, Lead Guitar, Bass, Vocals, Rhythm Guitar, Drums, Guitars Bus, Submaster)
  ✓ Renames all tracks to correct names
  ✓ Applies genre-appropriate colors to each track
  ✓ Routes instruments to bus/submaster sends

Result: Complete 168-bar rock arrangement in ~45 seconds from a single voice command
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     YOU (Voice or Text)                          │
│              "create a rock project called Midnight Drive"       │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  AudioShuttle Web UI  (http://localhost:8765)                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Gemma 4 E4B — Domain Expert Translator                  │    │
│  │  • 81K context for genre profiles + tool schema         │    │
│  │  • Tool-use for multi-step DAW orchestration            │    │
│  │  • 11 genres, 8 instrument families, 7 FX chain types   │    │
│  └──────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  OSC Bridge  (python-osc, sub-ms latency)                 │    │
│  │  • 40+ DAW operations (track, volume, pan, FX, transport) │    │
│  │  • State verification after every step                   │    │
│  └──────────────────────────────────────────────────────────┘    │
└────────────────────────────────┬────────────────────────────────┘
                                 │ OSC (localhost:8000)
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  REAPER 7.71 (Linux, OSC surface enabled)                       │
│  • Lua watcher for operations OSC can't do (insert, MIDI, sends) │
│  • ReaSynth, ReaVerb, ReaEQ on every track                       │
│  • Full arrangement with markers, routing, FX                    │
└─────────────────────────────────────────────────────────────────┘
```

### Docker Stack (GPU-Accelerated)

| Component | Container | GPU | Context |
|-----------|-----------|-----|---------|
| **Gemma 4 E4B** | `e4b` (llama.cpp + ROCm) | RX 6950 XT, 99 layers | 81K |
| **AudioShuttle** | `audioshuttle` (FastMCP) | — | — |

## What Makes This "4 Good"

### 1. Digital Equity — Real Accessibility, Not Just Play/Stop

This isn't a simple "play/stop via voice" workaround. AudioShuttle provides **full professional music production capability**:
- Create complete multi-track arrangements (not just adjust one parameter)
- Generate genre-appropriate MIDI patterns with section awareness
- Route audio through professional bus/submaster chains with effects
- Set volumes, pans, colors, markers — all via voice

**Impact:** For the first time, a motor-impaired musician can produce a full professional arrangement without touching a keyboard or mouse.

### 2. Speed — Idea to Arrangement in Under 60 Seconds

Traditional workflow: Open DAW → Create tracks → Name tracks → Set colors → Set routing → Create markers → Import MIDI → Set tempo → *45+ minutes*

AudioShuttle: `"create a rock project called Test at 130 BPM"` → Done in ~45 seconds

### 3. Simplicity — Describe Music, Not Software

"I want a metal song with a long atmospheric intro and more guitar solos" → Gemma 4 E4B interprets this as:
- Tempo: 160 BPM
- Intro: 16 bars of ambient guitar with reverb
- 2x solo sections (not the typical 1)
- Additional lead guitar density throughout chorus

The model understands **music concepts**, not DAW menus.

### 4. Open — AI-Agnostic, MIT-Licensed

AudioShuttle is an open bridge. The Gemma 4 E4B domain expert is the current implementation, but the architecture works with any tool-capable LLM. No lock-in, fully reproducible.

## Quick Start

### Prerequisites
- REAPER 7+ (free evaluation) with OSC enabled (ports 8000/9000)
- Docker + Docker Compose
- AMD RX 6000/7000 series GPU (or NVIDIA with minor config change)
- ~6GB for model files

### 1-Day Setup (if starting from scratch):
```bash
# Step 1: Get Gemma 4 E4B model files (~5.7GB total)
# Download from HuggingFace or Kaggle Models
mkdir -p models/
# gemma-4-E4B-it-UD-Q4_K_XL.gguf (~4.8GB)
# gemma-4-e4b-mmproj-BF16.gguf (~946MB)

# Step 2: Start the stack
docker compose up -d
# Wait ~2 min for model to load

# Step 3: Configure REAPER
# Open REAPER → Preferences → Control/OSC/web → Add OSC, local 8000, remote 9000
# Actions → Load Script → reaper_scripts/__startup.lua

# Step 4: Create your first project
curl "http://localhost:8765/replay?cmd=create+a+rock+project+called+My+Songs+at+120+bpm"
```

### Example Commands

| Command | Result |
|---------|--------|
| `create a rock project called Test` | 8 tracks, 9 markers, 120 BPM |
| `create a metal project at 160 bpm` | 8 tracks, faster tempo, heavier instruments |
| `create an EDM project` | Synth-heavy, 4-on-the-floor, builds and drops |
| `set track 3 volume to 0.8` | Track level adjustment |
| `pan track 2 hard left` | Stereo panning |
| `play` / `stop` | Transport control |
| `create a jazz project called Blue Notes` | 6 tracks, swing feel, jazz instrumentation |

## Technical Deep Dive

### Why Gemma 4 E4B?

| Capability | Why It Matters |
|------------|----------------|
| **81K context** | Fits entire genre profile (instruments, FX, routing) + tool schema + current state in one call |
| **Tool-use** | Native function-calling for DAW operations — multi-step orchestration with verification |
| **Domain fine-tune** | Understands music terminology — "chorus", "solo", "bus routing", "reverb send" — not just raw text |

### Full Pipeline (9 Steps)

```
Step 1: Set tempo         → /tempo/raw
Step 2: Create markers    → /marker (×9)
Step 3: Pre-insert tracks → /track/<n>/insert (×8)
Step 4: Wait + verify     → /tmp/audioshuttle_state_request
Step 5: Rename tracks      → /track/<n>/name (×8)
Step 6: Apply colors       → /action/<color_id> (×8)
Step 7: Route to buses    → /tmp/audioshuttle_send_trigger (×8)
Step 8: Bus FX             → /tmp/audioshuttle_fx_trigger (×2)
Step 9: Submaster FX      → /tmp/audioshuttle_fx_trigger (×1)
```

Each step verifies DAW state before proceeding. Stray tracks are cleaned up automatically.

## Project Structure

```
audioshuttle/
├── src/audioshuttle/
│   ├── osc_bridge.py        # OSC bridge — 40+ DAW operations
│   ├── translator.py        # E4B prompt engineering + dispatch
│   ├── genre_profiles.py    # 11 genres, 8 instruments, 7 FX types
│   ├── model_server.py      # LLM server lifecycle
│   ├── web_routes/home.py   # Web UI + /replay endpoint
│   └── cli.py               # Entry point
├── reaper_scripts/
│   └── __startup.lua       # Lua watcher (13 trigger types)
├── Dockerfile               # AudioShuttle container
├── Dockerfile.e4b           # Multi-stage ROCm build
├── docker-compose.yml       # GPU stack orchestration
├── tests/                   # 200+ unit tests
└── .planning/              # Phase planning docs
```

## Built With

- **Gemma 4 E4B** — Google's domain expert model (81K context, tool-use)
- **llama.cpp** — GPU-accelerated inference (ROCm HIPBLAS on AMD)
- **REAPER** — Professional DAW (Linux native, OSC-enabled)
- **FastMCP** — Model Context Protocol server
- **python-osc** — Open Sound Control communication
- **Docker** — Containerized deployment with GPU passthrough

## Contributing & License

MIT Licensed — see [LICENSE](LICENSE). Contributions welcome.

**Kaggle:** [Gemma 4 Good Hackathon](https://kaggle.com/competitions/gemma-4-good-hackathon)

---

*Built for the accessibility community — because music is for everyone.*