---
phase: 03-embedded-model-integration
date: 2026-05-07
status: complete
---

# Phase 3 Research: Embedded Model Integration

## What we need to know

1. How to start E2B on GPU via llama-server with ROCm
2. How to build an intent-to-OSC translation pipeline
3. How to integrate the translator into the existing MCP server
4. What system prompt engineering works for audio domain

## Findings

### 1. GPU Inference Setup

**Hardware:** RX 6950 XT (gfx1030), 16368 MiB VRAM, completely free.
**Model:** Gemma 4 E2B IT, Q4_K_XL quantization, 3GB file.
**Binary:** `/usr/bin/llama-server` version 8589, ROCm support confirmed.
**E4B:** Already running on CPU CCD0 at port 8090 (separate process, separate GPU).

**Launch command (from E4B pattern):**
```bash
HIP_VISIBLE_DEVICES=0 /usr/bin/llama-server \
  -m /home/korphaus/models/llm/gemma-4-e2b-it/gemma-4-E2B-it-UD-Q4_K_XL.gguf \
  --host 127.0.0.1 --port 8092 \
  -ngl 99 -t 4 -tb 4 --parallel 2 \
  -c 8192 -ctk q4_0 -ctv q4_0 \
  --jinja --timeout 60 --mlock --no-mmap
```

Key decisions:
- `HIP_VISIBLE_DEVICES=0` — targets the 6950 XT (device 0 in ROCm)
- Port 8092 — matches existing Settings.model_api_url default
- `-c 8192` — enough for DAW state context + command + response
- `--parallel 2` — max 2 concurrent requests (small model, don't overload)
- No `--reasoning off` needed — E2B is small enough without it
- No `--mmproj` — E2B is text-only (no vision)

**VRAM estimate:** Q4_K_XL 3GB model + KV cache for 8192 context ≈ 4-5GB total. Fits easily in 16GB.

**Startup verification:** `curl http://localhost:8092/v1/models` should return model info.

### 2. Intent-to-OSC Translation Pipeline

**Architecture:**
```
User says: "mute the drums"
     │
     ▼
MCP Tool: interpret_command(user_input, daw_state)
     │
     ▼
E2B Model (system prompt + DAW context + user input)
     │
     ▼
Structured response: {"tool": "set_track_mute", "args": {"track": 1, "mute": true}}
     │
     ▼
Executor calls the MCP tool directly (bridge method)
```

**Key insight:** E2B doesn't send OSC directly. It outputs a structured tool call JSON, and the server executes it. This gives us:
- Validation: we can check the tool exists and args are valid before executing
- Safety: the model can't send arbitrary OSC
- Observability: we log every interpretation
- Composability: the same tools work for direct MCP calls AND interpreted commands

**Fallback chain:** If E2B fails (timeout, parse error, GPU issue), fall back to a simple rule-based parser (regex matching on keywords like "mute", "volume", "play").

### 3. System Prompt Design

**Context injection:** Before each translation, inject current DAW state:
```
Current DAW state:
- Tracks: [1: Drums (vol=0.75, muted=false), 2: Bass (vol=0.5, muted=true), ...]
- Transport: stopped at 45.2s
- Master: vol=0.8, pan=0.0
- Connected to Reaper

Available tools: list_tracks, get_transport, get_daw_state, transport_control,
transport_seek, set_track_volume, set_track_mute, set_track_solo, set_track_pan,
set_master_volume, set_master_pan, set_fx_param, fx_bypass, trigger_action,
set_track_arm, get_track_count, toggle_repeat, toggle_metronome
```

**System prompt structure:**
```
You are AudioShuttle, an AI assistant that translates natural language commands
into DAW control actions. You help musicians and producers control Reaper DAW
using natural language.

Given the current DAW state and a user's natural language command, output a
JSON object with the tool to call and its arguments.

Output format (JSON only, no markdown):
{"tool": "<tool_name>", "args": {<key>: <value>, ...}}

Rules:
- Track names are matched case-insensitively against the DAW state
- Volume is 0.0-1.0 (0=silent, 0.75=normal, 1.0=max)
- Pan is -1.0 (left) to 1.0 (right), 0.0 is center
- FX and parameter indices are 0-based
- Track numbers start at 1
- If the command is ambiguous, output: {"error": "ambiguous", "message": "..."}
- If you don't understand, output: {"error": "unclear", "message": "..."}
```

**Response parsing:**
1. Try JSON parse on the raw response
2. If fails, try extracting JSON from markdown code blocks
3. If still fails, return error to caller
4. Validate tool name exists in our tool registry
5. Validate args match the tool's expected parameters

### 4. Integration Points

**New module:** `src/audioshuttle/translator.py` — contains:
- `IntentTranslator` class with `translate(user_input, daw_state) -> TranslationResult`
- System prompt template
- Response parsing + validation
- Fallback rule-based parser

**New module:** `src/audioshuttle/model_server.py` — contains:
- `ModelServer` class for managing the E2B llama-server process
- `start()` / `stop()` / `is_running()` / `health_check()`
- Subprocess management with proper lifecycle

**New MCP tool:** `interpret_command(user_input: str) -> dict` — added to server.py
- Gets current DAW state
- Calls translator with user_input + state
- If translation succeeds, executes the tool and returns result
- If translation fails, returns error with suggestion

**Config updates:** Settings already has `model_api_url` and `model_name`. Add:
- `model_gpu_device: int = 0` (ROCm device index)
- `model_context_size: int = 8192`
- `model_enabled: bool = True`

**No changes to:** osc_bridge.py, models.py (except adding TranslationResult model)

### 5. Testing Strategy

**Unit tests (no GPU needed):**
- System prompt generation with various DAW states
- Response parsing: valid JSON, invalid JSON, markdown-wrapped JSON
- Fallback parser: keyword matching
- TranslationResult model validation

**Integration tests (need E2B running):**
- `interpret_command("mute the drums")` → `set_track_mute(1, True)`
- `interpret_command("turn up vocals by 3db")` → volume adjustment
- `interpret_command("seek to the beginning")` → `transport_seek(0)`
- Ambiguous commands return error
- Unrecognized commands return error

### 6. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| E2B poor at structured output | Use Jinja chat template, validate response, fallback parser |
| GPU memory conflict | E2B on device 0 (6950 XT), E4B on CPU — no conflict |
| Model too slow for real-time | E2B is 3GB Q4, should be fast. Set timeout=60s. |
| GPU inference crashes | Wrap in try/catch, fall back to rule-based, log error |
| llama-server won't start | Check ROCm, try Vulkan fallback, document both options |

### 7. Don't Hand-Roll

- Use httpx for API calls (already installed)
- Use subprocess for process management (standard lib)
- Use json for parsing (standard lib)
- Use pydantic for TranslationResult model
- Don't build a custom OpenAI client — just POST with httpx

### 8. Common Pitfalls

- **Gemma chat format:** Must use `--jinja` flag with llama-server for proper chat template handling. Without it, the model may not follow the system prompt.
- **JSON mode:** llama-server doesn't have a strict JSON mode. Must handle malformed output gracefully.
- **ROCm device ordering:** Device 0 = 6950 XT, Device 1 = Raphael iGPU. Always use `HIP_VISIBLE_DEVICES=0`.
- **Port conflicts:** E4B is on 8090, E2B should use 8092 (matching Settings default). 8091 is used by generation-api on the macbook but free locally.
- **Context window:** Don't set -c too high. 8192 is plenty for state + prompt + response. Higher = more VRAM for KV cache.
