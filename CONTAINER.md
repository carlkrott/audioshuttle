# AudioShuttle Container Architecture

## Overview

AudioShuttle uses two Docker containers orchestrated by docker-compose:

```
┌─────────────────────┐      ┌──────────────────────┐
│  audioshuttle        │      │  e4b                 │
│  (FastMCP server)    │◄────►│  (llama.cpp + Gemma) │
│  Port 8765           │      │  Port 8102           │
│  MCP stdio transport  │      │  81K context         │
└─────────┬────────────┘      └──────────────────────┘
          │
          ▼
    Host REAPER (ports 8000/9000 OSC)
```

## Services

### audioshuttle (Python 3.14-slim)
- **Image:** Built from `Dockerfile`
- **Base:** `python:3.14-slim`
- **User:** Non-root `audioshuttle` (UID 1000)
- **Dependencies:** fastmcp, python-osc, httpx, pydantic
- **Ports:** 8765 (Web UI)
- **Transport:** stdio (MCP default)
- **Healthcheck:** HTTP GET /health on port 8765

### e4b (Ubuntu 22.04 + llama.cpp)
- **Image:** Built from `Dockerfile.e4b`
- **Base:** `ubuntu:22.04`
- **Dependencies:** cmake, build-essential, llama.cpp compiled from source
- **Ports:** 8102
- **Volume:** `./models/:/models/` (GGUF files — NOT included in image)
- **Healthcheck:** HTTP GET /health on port 8102

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| AUDIOSHUTTLE_MODEL_API_URL | http://e4b:8102/... | Model API endpoint |
| AUDIOSHUTTLE_TRANSPORT | stdio | MCP transport mode |
| E4B_CONTEXT_SIZE | 81920 | Model context window |
| E4B_N_GPU_LAYERS | 0 | GPU layers (0=CPU) |

## Networking

- Containers communicate via Docker internal network (service names: `e4b`, `audioshuttle`)
- Host REAPER communicates with audioshuttle via OSC (ports 8000/9000) — must be accessible from container
- For Linux: use `--network=host` or ensure OSC ports are exposed

## GPU Support

GPU passthrough is commented out in `docker-compose.yml`. Uncomment the relevant section for your GPU:

- **AMD ROCm:** Uncomment `/dev/kfd` and `/dev/dri` device mappings
- **NVIDIA:** Uncomment the `deploy.resources` section with nvidia driver
- **Intel:** Uncomment `/dev/dri` device mapping

Without GPU, the model runs on CPU (slow but functional for testing).