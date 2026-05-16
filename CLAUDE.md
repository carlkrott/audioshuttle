# AudioShuttle — Project Context for AI Agents

## What This Is

AudioShuttle is an AI-agnostic bridge between LLMs and Reaper DAW, using Google's Gemma 4 E4B model as a domain expert translator. Users speak natural language commands → E4B translates → OSC bridge executes → Reaper responds.

## Current State (2026-05-16)

**Fully operational Dockerized stack with AMD ROCm GPU passthrough.**

### Docker Stack
| Container | Image | Port | Status | Role |
|-----------|-------|------|--------|------|
| `audioshuttle-e4b-1` | Custom (`Dockerfile.e4b`) | 8102 | ✅ Healthy | llama.cpp + Gemma 4 E4B Q4_K_XL, 99 GPU layers |
| `audioshuttle-audioshuttle-1` | Custom (`Dockerfile`) | 8765 | ✅ Healthy | FastMCP server + Web UI |

### Key Architecture Decisions

- **`network_mode: host`** — both containers use host networking; E4B accessible at `http://localhost:8102`, audioshuttle at `http://localhost:8765`
- **`/tmp:/tmp` volume** — shared so audioshuttle can read DAW state from `/tmp/audioshuttle_daw_state.json` (written by Reaper Lua watcher)
- **`--transport=standalone`** — audioshuttle runs as standalone HTTP server, NOT stdio MCP (MCP clients connect via HTTP transport)
- **`--no-model`** — audioshuttle does NOT bundle a model; it connects to external E4B at `localhost:8102`
- **ROCm GPU** — RX 6950 XT (gfx1030), 99 layers offloaded, multi-stage Dockerfile.e4b builds llama.cpp with HIPBLAS

### E4B Container (Dockerfile.e4b)

Multi-stage build:
1. **builder stage**: Ubuntu 22.04 + ROCm SDK (rocm-hip-runtime-dev, rocblas-dev, hipblas-dev) + llama.cpp compiled with `-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1030`
2. **final stage**: Minimal Ubuntu 22.04 + ROCm runtime (rocm-hip-runtime, rocblas, hipblas) + copied llama-server binary

Key env vars:
- `N_GPU_LAYERS=99` — all layers on GPU
- `HSA_OVERRIDE_GFX_VERSION=10.3.0` — overrides for correct gfx1030 detection
- `HIP_VISIBLE_DEVICES=0`
- `CONTEXT_SIZE=81920` — E4B's full 81K context

### Audioshuttle Container (Dockerfile)

- Python 3.14-slim, `--transport=standalone --host=0.0.0.0 --port=8765 --no-browser --no-tray --no-model`
- Connects to E4B at `http://localhost:8102/v1/chat/completions`
- OSC to Reaper at `127.0.0.1:8000` (Reaper runs on host)
- Healthcheck: GET `http://localhost:8765/`

### DAW State

- **Reaper 7.71** running as korphaus user on host, OSC surface on ports 8000/9000
- **Lua watcher** (`~/.config/REAPER/Scripts/__startup.lua`) handles file triggers for track insertion, MIDI import, routing via `/tmp/audioshuttle_*` files
- **State file**: `/tmp/audioshuttle_daw_state.json` — written by Lua watcher on request (`/tmp/audioshuttle_state_request`)
- **Trigger files**: `wipe_trigger`, `track_insert_trigger`, `midi_trigger`, `state_request`, `send_trigger`, `fx_trigger`

## Working Pipeline

### Full E2E Project Creation (verified working)

```
NL command → HTTP /replay?cmd=... → translator.translate_multi() 
  → E4B model → create_genre_project() 
  → 9-step pipeline (tempo, markers, insert tracks, name tracks, color tracks)
  → 8 tracks (6 instruments + Guitars Bus + Submaster) 
  → 9 markers (intro → verse → chorus → verse → chorus → solo → chorus → outro)
```

### Key Files

| File | Purpose |
|------|---------|
| `src/audioshuttle/web_routes/home.py` | HTTP routes including `/replay` NL command endpoint |
| `src/audioshuttle/translator.py` | E4B prompt + tool dispatch (`translate_multi()`) |
| `src/audioshuttle/osc_bridge.py` | OSC bridge — 3652 lines, all DAW operations |
| `src/audioshuttle/genre_profiles.py` | 11 genres, 8 instrument families, FX chains |
| `src/audioshuttle/cli.py` | CLI + server entry point |
| `docker-compose.yml` | Two-container stack with GPU passthrough |
| `Dockerfile.e4b` | Multi-stage ROCm build |
| `Dockerfile` | Audioshuttle server container |

### Important Fixes Applied

1. **Multi-tool NL pipeline** — `replay_command` now calls `translate_multi()` (not `translate()`) so all tool calls execute sequentially
2. **Volume param name** — `_normalize_args` converts `volume` → `value` (bridge methods use `value`)
3. **`/action/<id>` embedding** — Reaper expects action ID in the OSC address path, not as a separate argument
4. **ROCm multi-stage build** — separates build tools from runtime for smaller final image
5. **GPU offload** — from 0 to 99 layers (CPU-only → full GPU acceleration)
6. **Healthcheck** — uses root path `/` instead of `/health`

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Web UI: command input + log viewer |
| `/replay?cmd=...` | GET | Execute NL command via E4B pipeline |
| `/health` | GET | Health check |
| `/log` | GET | HTML log viewer |
| `/state` | GET | JSON DAW state |

## Testing

```bash
# Test E2E project creation
curl "http://localhost:8765/replay?cmd=create+a+rock+project+called+Test+at+120+bpm"

# Check state
echo "dump" > /tmp/audioshuttle_state_request && sleep 3 && cat /tmp/audioshuttle_daw_state.json

# Wipe project
echo "1" > /tmp/audioshuttle_wipe_trigger

# Check container logs
docker logs audioshuttle-e4b-1
docker logs audioshuttle-audioshuttle-1

# Check E4B health
curl http://localhost:8102/health
```

## Known Non-Issues

- **"Reaper disconnected" warnings are benign** — health probe uses `/track/1/name` which Reaper doesn't respond to (no feedback → disconnect warning after 30s). Actual probe uses raw socket.
- **`HSA_OVERRIDE_GFX_VERSION=10.3.0`** is redundant since auto-detection correctly identifies gfx1030, but kept as safety net
- **Docker `exec` can't read server error_log** — error_log is process-local; use HTTP `/log` API instead
