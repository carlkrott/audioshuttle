# Project: AudioShuttle

> AI-agnostic bridge between any LLM and any DAW — making professional audio production accessible to everyone.

## Vision

AudioShuttle is an open-source MCP server + standalone application that lets **any AI** (Claude, local LLMs, Codex, Gemini) control **any DAW** (starting with Reaper) through natural language. It replaces physical MIDI controllers and mixing desks with voice and text commands.

**Social good angle:** People with motor disabilities (cerebral palsy, RSI, arthritis, limb differences) cannot use the complex mouse/keyboard workflows that DAWs require. AudioShuttle gives them hands-free control of professional music production software. No voice-controlled mixing solution exists today — we're building the first one.

**Kaggle submission:** Gemma 4 Good Hackathon — demonstrating Gemma's ability to serve as both the embedded domain expert (fine-tuned E2B for MIDI/audio) and the external chat interface (E4B on CPU).

## Core Architecture

```
┌─────────────────────────────────────────────────────┐
│                   External AI Layer                   │
│  (Claude, local LLM, Codex, any MCP client)          │
└────────────────────┬────────────────────────────────┘
                     │ MCP Protocol (stdio/SSE)
                     ▼
┌─────────────────────────────────────────────────────┐
│              AudioShuttle Server (Python)             │
│                                                       │
│  ┌───────────────┐  ┌──────────────────────────┐    │
│  │  MCP Tools    │  │  Embedded Gemma E2B      │    │
│  │  (exposed to  │  │  (llama.cpp GPU, 6950XT) │    │
│  │   any client) │  │  Audio domain expert     │    │
│  └───────┬───────┘  │  Intent → OSC translation│    │
│          │          │  DAW context provider     │    │
│          │          └────────────┬─────────────┘    │
│          │                       │                   │
│  ┌───────┴───────────────────────┴───────────┐      │
│  │           OSC Command Layer                │      │
│  │  Reaper OSC ↔ State tracking ↔ Validation  │      │
│  └───────────────────┬───────────────────────┘      │
│                      │                                │
│  ┌───────────────────┴───────────────────────┐      │
│  │        Obsidian Memory / Skills           │      │
│  │  Learned workflows, project state,        │      │
│  │  user preferences, custom mappings        │      │
│  └───────────────────────────────────────────┘      │
│                                                       │
│  ┌───────────────────────────────────────────┐      │
│  │     Web UI + System Tray (FastAPI)        │      │
│  │  Setup wizard, status, config, logs       │      │
│  └───────────────────────────────────────────┘      │
└────────────────────┬────────────────────────────────┘
                     │ OSC over Tailscale (UDP)
                     ▼
┌─────────────────────────────────────────────────────┐
│              Reaper DAW (PCS Machine)                 │
│  Multi-track project, plugins, routing               │
└─────────────────────────────────────────────────────┘
```

## Two-Brain Design

**External AI (any)** = "Producer Brain"
- Understands creative intent, workflow decisions, project context
- Uses MCP tools to discover what's available and issue commands
- Can be Claude, local Gemma E4B, GPT, anything with MCP support

**Embedded Gemma E2B** = "Engineer Brain"
- Audio/MIDI domain expert running on GPU (RX 6950 XT, 16GB VRAM)
- Translates high-level intent into precise OSC/MIDI commands
- Provides DAW context to external AIs (what tracks exist, what plugins are loaded)
- Prompt-engineered first, LoRA fine-tuned as stretch goal

## MVP Demo (12-day scope)

**"Wow moment":** Open Reaper with a multi-track project on PCS → speak "mute the drums" → drums mute. "Turn up the vocals by 3 dB" → fader moves. "Add some reverb to the guitar" → plugin loads.

**Demo flow:**
1. Show Reaper with 8+ tracks on PCS
2. Use Gemma E4B (already running on CCD0 port 8090) as the chat interface
3. Type/speak commands → watch Reaper respond in real-time
4. Show the MCP server handling multiple command types

**Video submission:** 2-3 minute demo highlighting the accessibility angle

## Technical Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Server | Python 3.14 + FastAPI | 12-day timeline, MCP SDK, async |
| MCP Server | `mcp` or `fastmcp` (PyPI) | Standard MCP protocol |
| DAW Control | python-osc → Reaper OSC | Network-native, full control |
| Embedded Model | llama.cpp GPU server (RX 6950 XT) | Already have llama-server binary |
| Model | Gemma 4 E2B UD-Q4_K_XL (3GB) | Fast, small, fits in 16GB VRAM |
| Chat Interface | Gemma 4 E4B (port 8090, CPU CCD0) | Already running |
| Web UI | FastAPI + Jinja2 + HTMX | Simple, no build step |
| System Tray | pystray | Cross-platform tray icon |
| Memory | Obsidian-compatible Markdown files | Agnostic, human-readable |
| STT | Whisper (local, via SSL12) | Voice input for accessibility |

## Hardware Layout

| Machine | Role | Specs |
|---------|------|-------|
| **7995x (this)** | AudioShuttle server + models | 7995x CPU, RX 6950 XT 16GB, 16GB RAM per CCD |
| **PCS** | Reaper DAW | Needs Tailscale connectivity |
| **SSL12** | Audio I/O for voice | USB, mic input for Whisper STT |

## Key Constraints

- **12-day deadline** — scope ruthlessly, demo-first
- **E2B on GPU via llama.cpp** — ROCm/Vulkan on RX 6950 XT
- **Reaper on PCS** — connected via Tailscale OSC
- **Prompt engineering first, fine-tuning later** — system prompt + MCP tool schema
- **Not a DAW replacement** — background bridge service, not a workflow UI
- **Web UI is for setup/status only** — no track faders, no mixer view

## Kaggle Submission Strategy

1. **Narrative:** "Gemma gives disabled musicians hands-free control of professional audio production"
2. **Technical demo:** Multi-track Reaper project controlled entirely by voice/text
3. **Model showcase:** E2B as embedded domain expert + E4B as chat interface
4. **Stretch:** Show Claude or another AI also driving it (proving agnostic design)
5. **Open source:** GitHub repo with clear README, install instructions, demo video

## Out of Scope (v1)

- Fine-tuning pipeline (v2)
- Multi-DAW support beyond Reaper (v2)
- Plugin-specific deep integrations (v2)
- Real-time audio analysis/feedback (v2)
- Mobile companion app (v2)
- User accounts / cloud features (ever)
