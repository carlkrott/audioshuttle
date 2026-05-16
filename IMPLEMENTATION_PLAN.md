# AudioShuttle Multimodal + Live Thinking Implementation Plan

## Current State

| Component | Status | Port | Notes |
|-----------|--------|------|-------|
| E2B (Gemma 4 E2B IT Q4_K_XL + mmproj BF16) | ✅ Running | 8093 | ROCm dGPU, `multimodal` capability confirmed |
| E4B (CPU, zeroclaw) | ✅ Running | 8090 | **DO NOT TOUCH** — 3 persistent connections |
| E4B (dGPU, ROCm) | ✅ Running | 8092 | --mlock --metrics, no mmproj |
| AudioShuttle service | ✅ Running | 8765 | `--no-model` flag — model NOT wired |
| Reaper 7.71 | ✅ Running | — | Lua watcher, 6 tracks, arrangement engine working |
| Voice pipeline | ✅ Working | — | Alt+Space → Whisper → E2B → OSC → Reaper |

## What Exists (reuse, don't rebuild)

- `model_server.py` — lifecycle + `chat()` method (non-streaming, text-only)
- `translator.py` — `IntentTranslator._translate_with_model_multi()` sends text to E2B
- `overlay.py` — PyQt6 transparent border overlay (listening/processing/result modes)
- `server.py` — FastMCP with `daw_command` + `daw_state` tools
- `voice.py` — STT → translate_multi → execute pipeline
- Lua watcher — one-trigger-per-tick, 11 trigger types, stable
- E2B mmproj loaded — confirmed multimodal, streams `reasoning_content` + `content`

## What's Missing (this plan builds)

1. **Multimodal E2B chat** — `model_server.chat_multimodal()` with image/audio content parts
2. **Audio rendering pipeline** — Reaper → WAV → base64 → E2B for listening
3. **Screen capture pipeline** — Reaper window → PNG → base64 → E2B for vision
4. **Live thinking stream** — SSE/WebSocket broadcast of reasoning tokens + execution steps
5. **Thinking overlay** — Floating text window streaming model thoughts + MCP-readable log
6. **Model wiring** — Remove `--no-model`, connect to E2B on port 8093

---

## Plan Structure: 4 Phases, 12 Tasks

Each phase is independent enough to test standalone. Phases 1-3 can run in parallel.

---

## Phase 1: Multimodal Model Server (Foundation)

**Goal:** E2B connected, streaming, handling image + audio + text

### Task 1.1: Add `chat_streaming()` to model_server.py

**Files:** `src/audioshuttle/model_server.py`

**Action:**
- Add `chat_streaming()` generator method that sends `stream: true` to E2B
- Yields `StreamEvent` objects: `{type: "thinking"|"content"|"done", text: str}`
- Parse SSE chunks: `delta.reasoning_content` → thinking events, `delta.content` → content events
- Include `finish_reason` detection for "done" events
- Keep existing `chat()` method unchanged (backward compat)

**Verify:** Unit test sends a streaming request, receives thinking + content chunks

**Done:** `chat_streaming()` yields thinking/content/done events for any prompt

### Task 1.2: Add `chat_multimodal()` to model_server.py

**Files:** `src/audioshuttle/model_server.py`

**Action:**
- Add `chat_multimodal()` method accepting `content_parts: list[dict]`
- Supports OpenAI multipart format: `[{"type": "text", "text": "..."}, {"type": "image_url", ...}, {"type": "input_audio", ...}]`
- For audio: Gemma mmproj expects WAV/PCM — send as base64 data URI
- For images: PNG/JPEG base64 data URI (already works with ik_llama)
- Add helper methods: `image_from_file(path)`, `audio_from_file(path)`, `audio_from_bytes(wav_bytes)`
- Also add `chat_multimodal_streaming()` — combines both capabilities

**Verify:** Test with a PNG screenshot → E2B describes the image content

**Done:** E2B can process text + image + audio in a single request

### Task 1.3: Wire model server to service (remove --no-model)

**Files:** `src/audioshuttle/cli.py`, `src/audioshuttle/server.py`, `src/audioshuttle/config.py`

**Action:**
- Add config option: `model_external_url` (default `http://localhost:8093`)
- In `server.py` `create_server()`: when `model_enabled=False` but `model_external_url` is reachable, create external ModelServer pointing to E2B
- Remove need for `--no-model` flag — service auto-detects E2B on 8093
- ModelServer gets `enable_external()` pointing to `http://localhost:8093`
- Wire `bridge._model_server = model_server` regardless of embedded vs external
- Keep `--no-model` as override for when E2B is intentionally down

**Verify:** `systemctl restart audioshuttle` → logs show "External model server detected — using for translation"

**Done:** Service automatically connects to E2B on port 8093, translator works

---

## Phase 2: Audio Rendering Pipeline

**Goal:** User asks "how does the bass sound?" → Reaper renders → E2B listens → response

### Task 2.1: Reaper offline render via Lua trigger

**Files:** `~/.config/REAPER/Scripts/__startup.lua`, `src/audioshuttle/osc_bridge.py`

**Action:**

**Lua side:**
- Add new trigger: `/tmp/audioshuttle_render_trigger`
- Format: `render:START_SEC:DURATION_SEC:OUTPUT_PATH` or just `render` (full project)
- Handler uses `reaper.RenderProjectSection()` or sets render bounds + triggers action 40016
- Simpler approach: action 42230 renders with last settings, but we need programmatic control
- Best approach: Lua sets render bounds via `reaper.GetSetProjectInfo()`, then triggers render
  - `reaper.GetSetProjectInfo(0, "RENDER_STARTPOS", start, true)` 
  - `reaper.GetSetProjectInfo(0, "RENDER_ENDPOS", end, true)`
  - `reaper.GetSetProjectInfo(0, "RENDER_FILE", output_path, true)`
  - `reaper.Main_OnCommand(40016, 0)` — render project
- Write completion signal to `/tmp/audioshuttle_render_done` when render finishes

**Python side:**
- Add `render_project_section(start_sec, end_sec, output_path)` to ReaperOSC
- Uses `_lua_trigger` pattern: write trigger → wait for consumption → wait for output file
- Alternative (simpler): use Reaper's CLI render: copy project → `reaper -renderproject file.rpp`
  - This is cleaner — no Lua trigger needed, Reaper handles it
- Actually simplest: use `ffmpeg` to record PipeWire output of specific time range
  - Route Reaper output → record with `pw-cat -r` or `ffmpeg -f pulse -i Reaper`
  - But this requires real-time playback, not offline

**Recommended approach: Lua render trigger**
- Set render params in Lua
- Trigger action 42230 (render with current settings)  
- Poll for output WAV file
- Convert to 16kHz mono WAV for E2B (ffmpeg)

**Verify:** Call render trigger → WAV file appears in /tmp

**Done:** `bridge.render_section(0, 30, "/tmp/audioshuttle_render.wav")` produces a WAV file

### Task 2.2: Audio analysis tool (listen_and_analyze)

**Files:** `src/audioshuttle/osc_bridge.py`, `src/audioshuttle/translator.py`

**Action:**
- Add `listen_and_analyze(track, start, duration, question)` to ReaperOSC
- Steps:
  1. Solo the target track (OSC)
  2. Render section (Lua trigger from Task 2.1)
  3. Convert WAV to 16kHz mono 16-bit PCM (ffmpeg subprocess)
  4. Load WAV bytes → base64
  5. Build multimodal prompt: `[audio_data, text("Listen to this audio. {question}")]`
  6. Call `model_server.chat_multimodal_streaming()`
  7. Stream response to thinking stream (Phase 4)
  8. Un-solo the track
- Add to TOOL_SCHEMAS in translator.py
- Add to voice.py `_execute_tool()` map
- If track=None, render full mix (no solo)
- Include DAW state context in the prompt (key, tempo, section names)

**Verify:** `daw_command("solo track 4 and tell me how the bass sounds")` → E2B renders, listens, describes

**Done:** E2B can hear any track or the full mix and answer questions about it

---

## Phase 3: Vision Pipeline

**Goal:** User asks "does this look right?" → screenshot → E2B sees → response

### Task 3.1: Screen capture utility

**Files:** `src/audioshuttle/screen_capture.py` (new)

**Action:**
- Create `capture_reaper_window()` function
- Find Reaper window: `xdotool search --name "REAPER"` → window ID
- Capture: `import -window {wid} -resize 1280x720 /tmp/audioshuttle_screenshot.png`
  - `import` is ImageMagick (already installed)
  - Resize to 1280x720 to keep base64 size manageable for E2B context
- Alternative for Wayland: `spectacle -b -n -o /tmp/audioshuttle_screenshot.png --rectangle`
  - But `import` from ImageMagick works on X11/XWayland — Reaper runs on X11
  - Verify with `echo $DISPLAY` → `:0` (X11)
- Return PNG path
- Add `capture_full_screen()` as fallback
- JPEG alternative for smaller payloads: `import -window {wid} -quality 75 /tmp/audioshuttle_screenshot.jpg`

**Verify:** `capture_reaper_window()` produces a valid PNG showing Reaper's arrange view

**Done:** `screen_capture.py` captures Reaper window or full screen to file

### Task 3.2: Visual analysis tool (look_and_analyze)

**Files:** `src/audioshuttle/osc_bridge.py`, `src/audioshuttle/translator.py`

**Action:**
- Add `look_and_analyze(question)` to ReaperOSC
- Steps:
  1. Capture Reaper window (Task 3.1)
  2. Load PNG → base64
  3. Build multimodal prompt:
     ```
     [image_data, text("This is a screenshot of a Reaper DAW project.
     {question}
     
     Current project: {key} {scale}, {bpm} BPM
     Tracks: {track_list}
     Sections: {marker_list}")]
     ```
  4. Call `model_server.chat_multimodal_streaming()`
  5. Stream response to thinking stream (Phase 4)
- Add to TOOL_SCHEMAS: `look_and_analyze` with `question` param
- Add to voice.py `_execute_tool()` map
- Add auto-trigger: when user says "look at", "show me", "does this look", "check the arrangement"

**Verify:** `daw_command("look at my project and tell me if the structure makes sense")` → E2B describes what it sees

**Done:** E2B can see Reaper's screen and answer structural/spatial questions

---

## Phase 4: Live Thinking Stream + Overlay

**Goal:** Floating window shows model's thinking + execution in real-time, MCP-readable log

### Task 4.1: Thinking stream broadcaster

**Files:** `src/audioshuttle/thinking_stream.py` (new)

**Action:**
- Create `ThinkingStream` singleton — thread-safe event broadcaster
- Events: `ThinkingEvent(type, source, text, timestamp)`
  - Types: `thinking_start`, `thinking_token`, `content_token`, `tool_call`, `tool_result`, `error`, `done`
  - Source: "e2b" | "stt" | "translator" | "executor" | "audio" | "vision"
- Subscribers: overlay (PyQt), log file (`/tmp/audioshuttle_thinking.jsonl`), SSE endpoint
- Methods:
  - `emit(event)` — broadcast to all subscribers
  - `subscribe(callback)` — register subscriber
  - `get_recent(n)` — return last N events (for MCP queries)
- Log file: append JSON lines to `/tmp/audioshuttle_thinking.jsonl`
  - Each line: `{"ts": "...", "type": "...", "source": "...", "text": "..."}`
- Rotation: keep last 10MB, auto-trim

**Integration points:**
- `model_server.chat_multimodal_streaming()` → emit thinking/content events
- `translator._translate_with_model_multi()` → emit tool_call events
- `server._execute_tool()` → emit tool_result events
- `stt.transcribe()` → emit "heard: ..." events

**Verify:** After a voice command, `/tmp/audioshuttle_thinking.jsonl` has thinking + content + tool events

**Done:** Central broadcaster receives events from all pipeline stages

### Task 4.2: Floating thinking overlay

**Files:** `src/audioshuttle/thinking_overlay.py` (new)

**Action:**
- Create `ThinkingOverlay` — PyQt6 always-on-top transparent text window
- Position: bottom-right corner, 400px wide, 200px tall, semi-transparent dark background
- Content: scrolling text showing:
  - 🧠 Thinking: `{latest reasoning token}` (dimmed, italic)
  - 📝 Response: `{latest content token}` (bright)
  - 🔧 Tool: `{tool_name}({args})` → `{result}` (yellow → green)
  - 👁 Vision: "Analyzing screenshot..." (purple)
  - 🎵 Audio: "Listening to track 4 (0:00-0:30)..." (orange)
- Auto-scroll: always show latest, user can scroll up to see history
- Fade in/out: appears when thinking starts, fades 3s after last event
- Click-through: `WA_TransparentForMouseEvents` like voice overlay
- Font: monospace, 10pt, color-coded by event type
- Thread-safe via Qt signals (same pattern as VoiceOverlay)

**Design:**
```
┌─────────────────────────────────┐
│ 🧠 Analyzing the bass line...   │  ← thinking (dim)
│ It sounds like the bass is      │  ← thinking continuation
│ 📝 The bass has too much low    │  ← content (bright)  
│    end rumble around 80Hz.      │
│ 🔧 fx_set_wetdry(4,0,0.6) → ✓  │  ← tool execution
│ 📝 I've reduced the bass FX     │  ← content
│    wet level to 60%.            │
└─────────────────────────────────┘
```

**Verify:** Voice command triggers overlay showing thinking → content → tool execution

**Done:** Floating text window streams E2B's thought process in real-time

### Task 4.3: MCP-readable thinking log + interrupt tool

**Files:** `src/audioshuttle/server.py`, `src/audioshuttle/thinking_stream.py`

**Action:**
- Add new MCP tool: `daw_thinking`
  - Returns recent thinking events (last 50)
  - Shows what the model is currently doing
  - Can be queried by any MCP client (OpenCode, Claude, etc.)
- Add new MCP tool: `daw_interrupt`
  - Sets a flag that the streaming pipeline checks between chunks
  - When flag is set, current E2B call is cancelled (httpx stream disconnect)
  - Executor stops processing remaining tool calls
  - User can say "stop" or "wait" to trigger interrupt
  - Also usable from MCP: `daw_interrupt(reason="user wants to change direction")`
- Integration with voice: "stop"/"wait"/"hold on" → trigger interrupt
- Thinking log is also the foundation for the overlay (Task 4.2 reads from it)

**Verify:** Start a long command via MCP, then call `daw_interrupt` → execution stops, partial results returned

**Done:** MCP clients can observe and interrupt E2B's thinking/execution process

---

## Dependency Graph

```
Phase 1 (Foundation)    Phase 2 (Audio)       Phase 3 (Vision)
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ 1.1 Stream   │       │ 2.1 Render   │       │ 3.1 Capture  │
│ 1.2 Multi    │       │ 2.2 Analyze  │       │ 3.2 Analyze  │
│ 1.3 Wire     │       │              │       │              │
└──────┬───────┘       └──────┬───────┘       └──────┬───────┘
       │                      │                       │
       └──────────────────────┼───────────────────────┘
                              │
                     Phase 4 (Stream + Overlay)
                    ┌─────────────────────────┐
                    │ 4.1 ThinkingStream       │
                    │ 4.2 ThinkingOverlay      │
                    │ 4.3 MCP tools            │
                    └─────────────────────────┘
```

**Execution order:**
- Phase 1 must complete first (model server foundation)
- Phases 2 and 3 can run in parallel after Phase 1
- Phase 4 can start after 1.1 (streaming) but is best after 1+2+3

---

## Estimated Scope

| Task | Files Modified | Complexity | Estimated Time |
|------|---------------|------------|----------------|
| 1.1 chat_streaming | 1 (model_server.py) | Medium | 30 min |
| 1.2 chat_multimodal | 1 (model_server.py) | Medium | 30 min |
| 1.3 Wire model | 3 (cli, server, config) | Simple | 15 min |
| 2.1 Render pipeline | 2 (lua, osc_bridge) | Complex | 45 min |
| 2.2 Audio analyze | 2 (osc_bridge, translator) | Complex | 45 min |
| 3.1 Screen capture | 1 (new file) | Simple | 15 min |
| 3.2 Visual analyze | 2 (osc_bridge, translator) | Medium | 30 min |
| 4.1 ThinkingStream | 1 (new file) + integration | Medium | 30 min |
| 4.2 ThinkingOverlay | 1 (new file) | Medium | 30 min |
| 4.3 MCP tools | 1 (server.py) | Simple | 15 min |
| **Total** | **~12 files** | | **~5 hours** |

---

## New TOOL_SCHEMAS to Add

| Tool | Description |
|------|-------------|
| `listen_and_analyze` | Render a section, send audio to E2B for analysis |
| `look_and_analyze` | Capture Reaper screenshot, send to E2B for analysis |
| `render_section` | Render a time range to WAV (utility for listen_and_analyze) |

## New MCP Tools

| Tool | Description |
|------|-------------|
| `daw_thinking` | Return recent E2B thinking/events log |
| `daw_interrupt` | Interrupt current E2B execution |

## Key Technical Decisions

1. **E2B on port 8093** as the multimodal model (not E4B) — smaller, faster, mmproj confirmed working
2. **One Lua trigger per render** — no real-time audio streaming, just offline render + analysis
3. **ImageMagick `import`** for screen capture — works on X11/XWayland, already installed
4. **ffmpeg** for WAV conversion (Reaper render → 16kHz mono for E2B)
5. **JSONL log file** as the central thinking stream — simple, append-only, any process can read
6. **PyQt6 overlay** matching existing VoiceOverlay pattern — same window flags, same signal pattern
7. **`reasoning_content` from SSE chunks** — E2B already emits these, just need to capture and display
8. **No new dependencies** — everything uses installed tools (ffmpeg, import, xdotool, PyQt6)

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| E2B audio analysis quality | Test with simple prompts first, use specific audio terminology in prompt |
| Reaper render may not work via Lua | Fallback: use PipeWire real-time capture with `pw-cat` |
| Screen capture on Wayland | Use X11 fallback — Reaper runs under XWayland (`DISPLAY=:0`) |
| Thinking overlay too distracting | Auto-fade, click-through, small footprint |
| E2B context window too small for audio+image | Resize images to 720p, limit audio to 30s, use 32k context |
| Multiple MCP clients conflicting | ThinkingStream is read-only for subscribers, single-writer from pipeline |
