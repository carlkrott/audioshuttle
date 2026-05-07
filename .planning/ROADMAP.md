# Roadmap — AudioShuttle

## Timeline: 12 days (deadline ~May 19)

---

### Phase 1: Foundation (Day 1-3) ✅
**Goal:** Reaper running locally, OSC communication working, project skeleton

**Plans:** 3 plans
- [x] 01-01-PLAN.md — Python package skeleton, config, data models
- [x] 01-02-PLAN.md — OSC bridge module + track command diagnostics
- [x] 01-03-PLAN.md — MCP server with 8 DAW control tools + CLI

---

### Phase 2: Core MCP Tools (Day 3-5) ✅
**Goal:** Extended MCP tools — transport seek, FX control, master control, Reaper actions, command validation

**Plans:** 2 plans in 2 waves
- [x] 02-01-PLAN.md — Address validation + transport seek + track count + master control
- [x] 02-02-PLAN.md — FX control + Reaper actions + track arm + repeat/metronome toggles

---

### Phase 3: Embedded Model Integration (Day 5-7) ✅
**Goal:** E2B running on GPU, translating natural language to OSC commands

**Plans:** 3 plans in 3 waves
- [x] 03-01-PLAN.md — Model server lifecycle (start/stop/health) + GPU config
- [x] 03-02-PLAN.md — Intent translator (prompt engineering + response parsing + fallback)
- [x] 03-03-PLAN.md — interpret_command MCP tool + server integration

---

### Phase 4: Web UI + Integration (Day 7-9)
**Goal:** Setup wizard, status dashboard, full end-to-end demo working

**Plans:** TBD
- FastAPI web UI: setup wizard, connection status, config
- System tray icon
- Obsidian memory vault setup
- End-to-end test: text command → MCP → E2B → OSC → Reaper

---

### Phase 5: Voice + Demo (Day 9-12)
**Goal:** Voice control working, Kaggle submission ready

**Plans:** TBD
- Whisper STT integration via SSL12
- Voice command pipeline: mic → Whisper → MCP → Reaper
- Demo video recording
- README, Kaggle submission package
- Polish and edge cases

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| ROCm fails on 6950 XT | Can't run E2B on GPU | Fall back to Vulkan backend or CPU |
| E2B prompt engineering insufficient | Commands mistranslated | Add validation layer, fallback to direct tool calls |
| Reaper not available on Linux | No DAW to control | Reaper has native Linux build; alternative: use Carla |
| SSL12 not detected | No voice input | Use system mic or pre-recorded audio for demo |
| 12 days too tight | Incomplete demo | Ruthless scope: P0 only, everything else is stretch |
