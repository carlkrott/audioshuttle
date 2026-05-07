# Requirements — AudioShuttle

## Functional Requirements

### FR-01: MCP Server Interface
- **FR-01.1:** Expose MCP tools for DAW control (volume, mute, solo, pan, transport, plugin params)
- **FR-01.2:** Support stdio and SSE transports for MCP
- **FR-01.3:** Any MCP-compatible AI client can connect without custom code
- **FR-01.4:** Tools return structured responses (success/failure + current state)

### FR-02: Reaper Integration
- **FR-02.1:** Connect to Reaper via OSC over network (Tailscale)
- **FR-02.2:** Control track volume (0-1 range, dB display)
- **FR-02.3:** Control track mute/solo
- **FR-02.4:** Control track pan (-1 to 1)
- **FR-02.5:** Transport control (play, stop, record, seek)
- **FR-02.6:** Read track names and counts (DAW state discovery)
- **FR-02.7:** Control FX plugin parameters (basic: load, bypass, param value)
- **FR-02.8:** Handle connection loss gracefully with reconnection

### FR-03: Embedded Model (Domain Expert)
- **FR-03.1:** Run Gemma 4 E2B on RX 6950 XT via llama.cpp GPU
- **FR-03.2:** Accept natural language intents and return structured OSC commands
- **FR-03.3:** Provide DAW context to external AIs (what tracks exist, what's loaded)
- **FR-03.4:** Respond in <2 seconds for single command translation
- **FR-03.5:** System prompt engineered for audio domain (v1), LoRA fine-tuned (v2)

### FR-04: Web UI + System Tray
- **FR-04.1:** Setup wizard: configure Reaper IP/port, test connection
- **FR-04.2:** Status dashboard: model status, DAW connection, MCP clients connected
- **FR-04.3:** Configuration: OSC ports, model settings, memory vault path
- **FR-04.4:** System tray icon with status indicator and quick actions
- **FR-04.5:** NO mixing console, NO track faders, NO workflow UI

### FR-05: Memory / Skills System
- **FR-05.1:** Obsidian-compatible Markdown files for persistent memory
- **FR-05.2:** Store learned command mappings (user-specific overrides)
- **FR-05.3:** Store DAW project state snapshots for context restoration
- **FR-05.4:** Skills files that external AIs can read for guidance

### FR-06: Voice Input (Accessibility)
- **FR-06.1:** Local Whisper STT processing via SSL12 audio interface
- **FR-06.2:** Voice commands feed into the same MCP pipeline as text
- **FR-06.3:** Audio feedback confirmation (optional TTS for status)

## Non-Functional Requirements

### NFR-01: Performance
- **NFR-01.1:** End-to-end latency <3 seconds (voice → DAW action) for single commands
- **NFR-01.2:** MCP tool response <500ms (excluding model inference)
- **NFR-01.3:** Embedded model inference <2 seconds per command

### NFR-02: Reliability
- **NFR-02.1:** Graceful degradation when embedded model unavailable (direct MCP tool passthrough)
- **NFR-02.2:** OSC reconnection with exponential backoff
- **NFR-02.3:** State consistency — track state reflects actual DAW state

### NFR-03: Accessibility
- **NFR-03.1:** All core functions accessible via voice (no mouse/keyboard required)
- **NFR-03.2:** Clear audio confirmation of actions
- **NFR-03.3:** Web UI meets WCAG 2.1 AA (basic — contrast, keyboard nav, aria labels)

### NFR-04: Security
- **NFR-04.1:** MCP server local-only by default (localhost binding)
- **NFR-04.2:** OSC commands validated before sending (no injection)
- **NFR-04.3:** No audio data leaves the local machine

## Technical Requirements

### TR-01: Platform
- **TR-01.1:** Server runs on Linux (CachyOS, 7995x)
- **TR-01.2:** Python 3.14+ with async support
- **TR-01.3:** ROCm-compatible GPU inference for E2B model

### TR-02: Dependencies
- **TR-02.1:** `fastmcp` or `mcp` for MCP server implementation
- **TR-02.2:** `python-osc` for Reaper OSC communication
- **TR-02.3:** `fastapi` + `uvicorn` for web UI
- **TR-02.4:** `pystray` + `Pillow` for system tray
- **TR-02.5:** `openai-whisper` or `faster-whisper` for STT
- **TR-02.6:** `httpx` for llama.cpp API communication

### TR-03: Model
- **TR-03.1:** Gemma 4 E2B UD-Q4_K_XL (3GB) on RX 6950 XT
- **TR-03.2:** llama-server binary (already at /usr/bin/llama-server)
- **TR-03.3:** Context window: 8192 tokens minimum (Q4 KV cache)
- **TR-03.4:** JSON output mode for structured command generation

## Priority Classification

| Priority | Requirements | Rationale |
|----------|-------------|-----------|
| **P0 — Demo-blocking** | FR-01.1-01.4, FR-02.1-02.6, FR-03.1-03.4, NFR-01.1-01.3 | Must work for Kaggle demo |
| **P1 — Submission-quality** | FR-04.1-04.3, FR-05.1, FR-06.1-06.2, NFR-02.1-02.2 | Makes demo impressive |
| **P2 — Nice-to-have** | FR-02.7, FR-04.4, FR-05.2-05.4, FR-06.3, NFR-03 | Polish and stretch goals |
| **P3 — Post-hackathon** | Fine-tuning, multi-DAW, deep integrations | Future work |
