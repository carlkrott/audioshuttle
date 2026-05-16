# AudioShuttle Container Architecture

## Overview

AudioShuttle runs as two Docker containers with host networking and AMD ROCm GPU passthrough:

```
┌───────────────────────────────┐     ┌────────────────────────────────┐
│  e4b (llama.cpp + Gemma 4)    │     │  audioshuttle (FastMCP server)  │
│  Port 8102                     │◄───►│  Port 8765                      │
│  99 GPU layers (ROCm)          │     │  --transport=standalone         │
│  network_mode: host            │     │  --no-model                     │
│  Models: ./models/:/models/    │     │  State: /tmp:/tmp              │
└───────────────────────────────┘     └──────────┬─────────────────────┘
                                                  │ OSC :8000/:9000
                                                  ▼
                                        ┌──────────────────────┐
                                        │  REAPER 7.71 (host)   │
                                        │  OSC control surface  │
                                        │  Lua watcher scripts  │
                                        │  State: /tmp/*.json   │
                                        └──────────────────────┘
```

## Services

### audioshuttle (Python 3.14-slim)

| Attribute | Value |
|-----------|-------|
| **Image** | Built from `Dockerfile` |
| **Base** | `python:3.14-slim` |
| **User** | Non-root `audioshuttle` (UID 1000) |
| **Command** | `--transport=standalone --host=0.0.0.0 --port=8765 --no-browser --no-tray --no-model` |
| **Network** | `network_mode: host` |
| **Volumes** | `/tmp:/tmp` (read watcher state file) |
| **Healthcheck** | `python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/')"` |
| **Model API** | `http://localhost:8102/v1/chat/completions` |
| **OSC target** | `127.0.0.1:8000` (Reaper on host) |

### e4b (Ubuntu 22.04 + llama.cpp with ROCm)

| Attribute | Value |
|-----------|-------|
| **Image** | Built from `Dockerfile.e4b` (multi-stage) |
| **Base** | `ubuntu:22.04` (final stage) |
| **Build stage** | `ubuntu:22.04` + ROCm SDK 7.2, `-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1030` |
| **User** | Non-root `audioshuttle` (UID 1000) |
| **Network** | `network_mode: host` |
| **Devices** | `/dev/kfd:/dev/kfd`, `/dev/dri/renderD128:/dev/dri/renderD128` |
| **Group add** | Host `video` (983) + `render` (987) GIDs |
| **Volumes** | `./models/:/models/` (GGUF files — NOT in image) |
| **Healthcheck** | `curl -f http://localhost:8102/health` |
| **GPU layers** | 99 (all layers offloaded to RX 6950 XT) |
| **Context** | 81920 (full E4B 81K context) |

## Environment Variables

### e4b Service

| Variable | Value | Description |
|----------|-------|-------------|
| `MODEL_PATH` | `/models/gemma-4-E4B-it-UD-Q4_K_XL.gguf` | Main model |
| `MMPROJ_PATH` | `/models/gemma-4-e4b-mmproj-BF16.gguf` | Vision projection |
| `PORT` | `8102` | llama-server port |
| `CONTEXT_SIZE` | `81920` | Context window |
| `N_GPU_LAYERS` | `99` | GPU offload layers |
| `HSA_OVERRIDE_GFX_VERSION` | `10.3.0` | AMD GPU arch (redundant, safe) |
| `HIP_VISIBLE_DEVICES` | `0` | Device visibility |

### audioshuttle Service

| Variable | Value | Description |
|----------|-------|-------------|
| `AUDIOSHUTTLE_MODEL_API_URL` | `http://localhost:8102/v1/chat/completions` | E4B endpoint |
| `AUDIOSHUTTLE_OSC_HOST` | `127.0.0.1` | Host Reaper IP |
| `AUDIOSHUTTLE_OSC_PORT` | `8000` | Host Reaper OSC port |
| `AUDIOSHUTTLE_HOST` | `0.0.0.0` | Server bind |
| `AUDIOSHUTTLE_PORT` | `8765` | Server port |

## GPU Passthrough Configuration

### AMD ROCm (default — verified on RX 6950 XT)

```yaml
services:
  e4b:
    devices:
      - /dev/kfd:/dev/kfd
      - /dev/dri/renderD128:/dev/dri/renderD128  # dGPU only
    group_add:
      - "983"   # host video group GID
      - "987"   # host render group GID
```

To find your host GIDs:
```bash
getent group video    # → video:x:983:korphaus
getent group render   # → render:x:987:korphaus
```

### NVIDIA

Replace the `devices` section with:
```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### CPU Only

Set `N_GPU_LAYERS=0` in the e4b environment.

## Build Process

```bash
# Initial build (slow — compiles llama.cpp with ROCm)
docker compose build --no-cache

# Rebuild after code changes (audioshuttle only, fast)
docker compose build --no-cache audioshuttle

# Start
docker compose up -d

# Watch logs
docker compose logs -f

# Check health
docker compose ps
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| E4B fails healthcheck | GPU device not accessible | Check `/dev/kfd` and `/dev/dri/renderD128` exist and have correct permissions |
| "ROCk module not loaded" | `amdgpu` kernel module missing | `sudo modprobe amdgpu` or reboot |
| E4B builds but model fails to load | Wrong GPU target in cmake | Change `AMDGPU_TARGETS` in Dockerfile.e4b |
| "Reaper disconnected" in logs | Benign — no feedback on probe | Ignore (socket probe works independently) |
| Audioshuttle can't reach E4B | Wrong MODEL_API_URL | Must use `localhost:8102` (not `e4b:8102` — host networking) |
| Docker exec can't see error_log | Process-local singleton | Use `curl http://localhost:8765/log` instead |
