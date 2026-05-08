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

### Phase 4: Web UI + Integration (Day 7-9) ✅
**Goal:** Web configurator with status dashboard, system tray, context memory, unified launcher — full E2E demo flow working

**Plans:** 5 plans in 3 waves — ALL COMPLETE
- [x] 04-01-PLAN.md — Web app foundation + utilities + home tab with status badges
- [x] 04-02-PLAN.md — Input tab (system prompt editor) + Output tab (DAW preset, mappings)
- [x] 04-03-PLAN.md — Context manager with compaction and Obsidian vault dump
- [x] 04-04-PLAN.md — System tray icon + unified launcher
- [x] 04-05-PLAN.md — Integration tests + human E2E verification

---

### Phase 5: Voice + Demo (Day 9-12)
**Goal:** Voice control working, MIDI pattern generator, dashboard enhancements, Kaggle submission ready

**Plans:** 7 plans in 5 waves
- [ ] 05-01-PLAN.md — STT engine (faster-whisper) + transcribe_audio MCP tool
- [ ] 05-02-PLAN.md — Home dashboard enhancements + nav/route infrastructure for new tabs
- [ ] 05-03-PLAN.md — MIDI pattern generator tab (16-bar grid + E2B track assignment)
- [ ] 05-04-PLAN.md — Command log tab + track presets + state snapshot + shortcuts reference
- [ ] 05-05-PLAN.md — Voice pipeline (Alt+Space hotkey + E2B formatting + browser recording)
- [ ] 05-06-PLAN.md — Gemma-centric README + demo walkthrough + CI workflow
- [ ] 05-07-PLAN.md — Launcher hardening + tray status + visual polish + human E2E verification

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| ROCm fails on 6950 XT | Can't run E2B on GPU | Fall back to Vulkan backend or CPU |
| E2B prompt engineering insufficient | Commands mistranslated | Add validation layer, fallback to direct tool calls |
| Reaper not available on Linux | No DAW to control | Reaper has native Linux build; alternative: use Carla |
| SSL12 not detected | No voice input | Use system mic or pre-recorded audio for demo |
| 12 days too tight | Incomplete demo | Ruthless scope: P0 only, everything else is stretch |
