# AudioShuttle — Speak Music Into Existence

**Voice-controlled professional music production for the 250M+ people who can't use a mouse.**

Track: Digital Equity & Inclusivity

---

## The Problem

Professional audio production is mouse-and-keyboard only. Every DAW operation — creating a track, adjusting a fader, routing audio through a bus — requires fine motor control that 250 million+ people with motor impairments cannot perform. Current "accessibility" in music software is limited to basic transport controls (play/stop/record). No system enables a motor-impaired musician to create, arrange, and mix a full professional project hands-free.

## The Solution

AudioShuttle bridges natural language voice commands to professional DAW control using **Gemma 4 E4B as a domain-expert translator**. A single spoken sentence — *"create a rock project called Midnight Drive at 130 BPM"* — produces a complete multi-track arrangement with correct instruments, MIDI patterns, bus routing, FX chains, markers, and tempo in under 45 seconds.

## How Gemma 4 E4B Is Used

Gemma 4 E4B is the core intelligence, not a bolted-on chatbot. Three capabilities make it essential:

**1. 81K Context Window** — Each genre profile contains instrument definitions, section structures, MIDI patterns, bus topologies, FX chains, and color schemes. Combined with the 40+ tool schema and live DAW state, only E4B's massive context holds everything in a single prompt without retrieval overhead.

**2. Native Tool-Use** — E4B doesn't just generate text responses. It orchestrates multi-step DAW operations: insert track → name it → set volume → apply color → route to bus → add FX. Each step is a discrete tool call that the bridge executes against Reaper, with state verification between steps.

**3. Domain Understanding** — E4B understands music concepts, not just software menus. "Make the chorus feel bigger" translates to appropriate instrumentation, dynamics, and arrangement decisions. "Add more guitar solos" doubles lead guitar variants with solo section MIDI patterns.

## Architecture

```
Voice Input → Mic Capture → Gemma 4 E4B Audio Understanding
  → E4B translates to structured tool calls
  → OSC Bridge executes 40+ DAW operations
  → Reaper Lua watcher handles insert/routing/MIDI
  → State verification confirms each step
```

The system runs **fully offline** on a single AMD GPU (RX 6950 XT) using llama.cpp with ROCm — no cloud, no API keys, no latency. This is critical for the target users: people who may be in hospitals, rehabilitation centers, or homes with unreliable internet.

## What's Working (Verified End-to-End)

- **11 genres** with doubled instrument variants (e.g., two rhythm guitars in rock, two synth leads in electronic)
- **Complete project creation** from one command: tempo, 9 markers, 8 tracks, naming, coloring, bus routing, FX chains, MIDI patterns
- **MIDI pattern generation** — instrument-specific patterns that match genre and section (verse drums ≠ chorus drums)
- **Full mix control** — volume, pan, mute, solo, rename, marker placement, tempo changes
- **Voice input pipeline** — microphone capture → E4B audio transcription → command execution with context-aware accuracy (injects track names as hints)
- **Project wipe and recreation** — switch genres instantly: *"wipe this and create a metal project at 180 BPM"*

## Technical Challenges Overcome

**MIDI Import Reliability** — Reaper's `InsertMedia()` API has a track-selection race condition where rapid sequential calls accumulate all items on the first track. After three failed approaches (mode 0/1/3), we bypassed `InsertMedia` entirely using `AddMediaItemToTrack()` + `PCM_Source_CreateFromFile()` for direct item creation with zero selection dependency.

**Container Audio Access** — The Docker container needed access to the host's SSL 12 audio interface via PipeWire. Required PulseAudio ALSA plugin (`libasound2-plugins`), host audio group membership (`group_add: 995`), and Pulse socket mount.

**Transcription Accuracy** — E4B's audio transcription confused similar track names (e.g., "bass" vs "buses"). Solved by injecting live track names as context hints into the transcription prompt, achieving the same effect as Whisper's keyword boosting.

## Impact & Vision

AudioShuttle proves that frontier AI models running locally can unlock professional creative tools for people excluded by physical interface requirements. The 81K context window isn't a benchmark number — it's what makes single-sentence music production possible. Every component runs offline on consumer hardware.

The architecture is AI-agnostic and MIT-licensed. While Gemma 4 E4B is the current domain expert, any tool-capable LLM can slot in. Our hope is that AudioShuttle becomes a template for accessible professional tools across creative disciplines.

## Built With

Gemma 4 E4B (llama.cpp + ROCm), REAPER 7.71, python-osc, FastMCP, Docker

**Code:** https://github.com/carlkrott/audioshuttle  
**Demo:** http://100.64.0.1:8765 (Tailscale mesh network)
