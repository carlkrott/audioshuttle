# AudioShuttle

**Gemma enables the walk-in recording studio — speak to create.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-158%20passing-brightgreen.svg)]()

AudioShuttle uses **Gemma's lightweight efficiency** to bridge the gap between human speech and professional audio production, making music creation accessible to anyone who can speak.

## 🎯 The Problem

Professional audio production requires complex mouse and keyboard workflows. Musicians with motor disabilities, RSI, or visual impairments are effectively locked out of the creative process.

> Imagine walking into a recording studio and just... speaking. That's what AudioShuttle enables.

## 💡 The Solution — Powered by Gemma

AudioShuttle uses **Gemma E2B** as the translation layer between human speech and DAW commands. It's a two-brain architecture:

- **External AI (any LLM)** = creative producer — understands what you want
- **Gemma E2B** = precise audio engineer — translates intent to OSC commands

The flow: `Speech → [Whisper] → Text → [Gemma E2B] → OSC → Reaper DAW`

This is the first step toward a literal **walk-in recording studio** where anyone who can speak can produce music. No mouse, no keyboard, no years of DAW training.

## 🏗 Architecture

```
  User (speech/text)
       │
       ▼
  ┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌───────────┐
  │  Whisper  │────▶│  Gemma E2B   │────▶│   OSC    │────▶│  Reaper   │
  │ (STT)     │     │  (Engineer)  │     │  Bridge  │     │  (DAW)    │
  └──────────┘     └──────────────┘     └──────────┘     └───────────┘
       ▲                  ▲
       │                  │
  ┌────┴────┐      ┌─────┴─────┐
  │ Browser │      │ Any AI    │
  │  Mic    │      │ Client    │
  └─────────┘      │ (Gemini,  │
  ┌─────────┐      │  Claude)  │
  │Alt+Space│      └───────────┘
  │ Hotkey  │
  └─────────┘
```

Gemma E2B runs **locally** on GPU (3.18GB Q4_K_XL quantization) — no cloud dependency, no API costs, no latency. The model is purpose-loaded to translate natural language into precise DAW commands.

## 🚀 Quick Start

```bash
git clone https://github.com/user/audioshuttle && cd audioshuttle
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"

# Start Reaper DAW, then:
audioshuttle                    # Standalone: web UI + system tray
audioshuttle --transport stdio  # MCP server (for Gemini CLI, Claude Code, etc.)
```

Open `http://localhost:8765` in your browser for the configuration dashboard.

## 🛠 Configuration

All settings use environment variables with `AUDIOSHUTTLE_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIOSHUTTLE_REAPER_HOST` | `127.0.0.1` | Reaper OSC host |
| `AUDIOSHUTTLE_REAPER_PORT` | `8000` | Reaper OSC command port |
| `AUDIOSHUTTLE_MODEL_PATH` | *(see config)* | Path to Gemma GGUF model |
| `AUDIOSHUTTLE_WEB_PORT` | `8765` | Web UI port |

## 🎙 Voice Commands

```bash
pip install -e ".[stt]"   # adds faster-whisper
```

- **Alt+Space** — hold to record, release to send
- Speak naturally: "turn up the drums", "pan the guitar left", "mute the vocals"
- **Cleanup Audio** toggle — Gemma cleans Whisper output (removes fillers, normalizes language)

Voice pipeline: `Mic → Whisper (CPU) → [Gemma cleanup] → Gemma translate → OSC → Reaper`

## 🎹 MIDI Pattern Generator

Generate pseudo-random patterns in the web UI:
- **Drums** — kick/snare/hihat patterns with 16-bar structure
- **Rhythm** — 2-4 bar chord cycles
- **Lead** — 50% density melodic patterns
- **Melody** — 60% density with stepwise motion

Send patterns to Gemma for intelligent track assignment.

## 📋 MCP Tools (20)

AudioShuttle exposes 20 Model Context Protocol tools for precise DAW control:

| Category | Tools |
|----------|-------|
| **Transport** | `play`, `stop`, `record`, `pause`, `seek` |
| **Track Control** | `set_track_volume`, `set_track_mute`, `set_track_solo`, `set_track_pan`, `set_track_arm` |
| **Master** | `set_master_volume`, `set_master_pan` |
| **FX** | `set_fx_param`, `toggle_fx_bypass` |
| **DAW** | `get_daw_state`, `refresh_state`, `execute_action` |
| **AI** | `interpret_command`, `transcribe_audio` |
| **System** | `check_health` |

Use with any MCP-compatible client: Gemini CLI, Claude Code, or any LLM.

## 🎥 Demo

See `examples/demo_walkthrough.md` for the full shot-by-shot video script.

Key demo moments:
1. Typed commands: "mute the drums", "pan the guitar left"
2. Voice commands via Alt+Space: "turn up the drums a little"
3. Gemma translating natural speech to precise OSC in real-time

## 🧪 Development

```bash
pip install -e ".[web,tray]"
pip install pytest
pytest --tb=short -q   # 158 tests
```

### Project Structure

```
audioshuttle/
├── src/audioshuttle/
│   ├── server.py          # FastMCP server (20 tools)
│   ├── osc_bridge.py      # Reaper OSC bridge
│   ├── translator.py      # Gemma E2B intent translator
│   ├── model_server.py    # Local llama-server management
│   ├── stt.py             # Whisper speech-to-text
│   ├── voice.py           # Voice pipeline (STT → format → translate)
│   ├── hotkey.py          # Global Alt+Space hotkey
│   ├── midi_generator.py  # Pattern generator
│   ├── launcher.py        # Unified startup
│   ├── web.py             # FastAPI dashboard
│   └── config.py          # Pydantic settings
├── tests/                 # 158 tests
└── examples/
```

## 🙏 Acknowledgments

- **Kaggle Gemma 4 Good Hackathon** — making AI accessible for everyone
- **Google DeepMind** — for Gemma, the lightweight model that makes this possible
- **Reaper** — for excellent OSC support that enables external control
- **fastmcp** — clean MCP server implementation
- **faster-whisper** — efficient local speech-to-text

## License

MIT
