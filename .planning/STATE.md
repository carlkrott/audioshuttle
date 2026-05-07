# Project State — AudioShuttle

## Project Reference

**Goal:** Build an AI-agnostic MCP server that bridges any LLM to Reaper DAW, enabling voice/text control of professional audio production for accessibility.

**Competition:** Kaggle Gemma 4 Good Hackathon
**Deadline:** ~May 19, 2026 (12 days)
**Repository:** /home/korphaus/audioshuttle/

## Current Position

Phase: Pre-execution (project defined, roadmap written)
Status: Project files created, ready for Phase 1 planning
Last activity: 2026-05-07 — Project initialized

Progress: [░░░░░░░░░░] 0%

## Key Resources

| Resource | Location | Status |
|----------|----------|--------|
| Gemma E4B (chat) | localhost:8090 (CPU CCD0) | ✅ Running |
| Gemma E2B (domain expert) | /home/korphaus/models/llm/gemma-4-e2b-it/gemma-4-E2B-it-UD-Q4_K_XL.gguf | ✅ Available (3GB) |
| RX 6950 XT | GPU card1, 16GB VRAM | ✅ Free (16MB used) |
| llama-server | /usr/bin/llama-server | ✅ Available |
| Python 3.14 | /usr/bin/python3 | ✅ Available |
| SSL12 Audio | USB interface | ⚠️ WirePlumber not detecting |

## Critical Context

- **Everything runs on this machine** — Reaper + AudioShuttle + models, all localhost
- **E4B on CCD0 (port 8090)** running as CPU inference with 6.8GB RSS, `-ngl 99` with `HIP_VISIBLE_DEVICES=0` (Raphael iGPU, not actually used for GPU layers)
- **RX 6950 XT completely free** — 16368 MB VRAM, only 16 MB used. Can easily run E2B (3GB model)
- **ROCm installed** at /opt/rocm, rocm-smi works
- **No pip packages installed yet** for this project (mcp, python-osc, fastapi all need install)
- **Reaper needs installing** on this machine

## Decisions

- **Python over Rust** for 12-day timeline
- **Prompt engineering first**, LoRA fine-tuning post-hackathon
- **Reaper as DAW** (free, scriptable, OSC support)
- **Everything on this machine** — localhost OSC, no network dependency
- **Web UI + tray** for setup/status (not a mixing console)
- **fastmcp** for MCP server implementation
- **Gemma E2B Q4_K_XL** as embedded domain expert model

## Blockers/Concerns

- Reaper needs to be installed on this machine
- ROCm GPU inference on RX 6950 XT needs testing (may need Vulkan fallback)
- SSL12 audio interface not detected by WirePlumber (affects STT)
- No fine-tuning in v1 — relies entirely on prompt engineering quality

## Session Continuity

Last session: 2026-05-07
Stopped at: Project initialization complete — PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md written
Resume: Run `/gsd-plan-phase 1` to create Phase 1 execution plans
