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

### Phase 6: Model-Driven Project Generation ✅
**Goal:** E2B model auto-generates complete genre-aware projects with buses, FX chains, and per-section MIDI. Pipeline with state verification between steps.

**Plans:** 4 plans in 4 waves — ALL COMPLETE (incl. gap closure)
- [x] 06-01-PLAN.md — Genre profile database (tempo, sections, instruments, routing, FX chains for 11+ genres)
- [x] 06-02-PLAN.md — Enhanced project pipeline (create_genre_project, bus/submaster routing, per-track FX, watcher hardening)
- [x] 06-03-PLAN.md — System prompt + model integration (genre detection, MCP wiring, E2E tests)
- [x] 06-04-PLAN.md — Gap closure: track index bug, marker enumeration, watcher FX timeout

---

### Phase 7: Pipeline Hardening ✅ (COMPLETE)
**Goal:** Fix all pipeline bugs found in Phase 6 E2E testing: MIDI generation gaps (guitars/vocals), FX chain application (never added), genre mapping (metal→rock), bus/submaster FX, stray tracks. Add E4B modifier system for dynamic genre adaptation.

**Plans:** 3 plans in 3 waves
- [x] 07-01-PLAN.md — Fix MIDI generation (_normalize_role, active_roles, genre mapping, stray track)
- [x] 07-02-PLAN.md — Fix FX application + add bus/submaster FX architecture
- [x] 07-03-PLAN.md — E4B modifier system + track-aware analysis + E2E verify

---

### Phase 8: Hackathon Submission Prep 📋 (PLANNED)
**Goal:** Package AudioShuttle for Kaggle Gemma 4 Good Hackathon submission — security scrub, Docker containerization, GitHub repository, README, demo video, and submission.

**Plans:** 6 plans in 4 waves
- [ ] 08-01-PLAN.md — Security scrub + .gitignore + codebase prep (Wave 1)
- [ ] 08-02-PLAN.md — Docker container packaging (Wave 1)
- [ ] 08-03-PLAN.md — Test Dockerized setup (Wave 2, human-verify)
- [ ] 08-04-PLAN.md — README + LICENSE + container docs (Wave 3)
- [ ] 08-05-PLAN.md — GitHub repository + push (Wave 3)
- [ ] 08-06-PLAN.md — Demo video + Kaggle submission (Wave 4, human-action)

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| ROCm fails on 6950 XT | Can't run E2B on GPU | Fall back to Vulkan backend or CPU |
| E2B prompt engineering insufficient | Commands mistranslated | Add validation layer, fallback to direct tool calls |
| Reaper not available on Linux | No DAW to control | Reaper has native Linux build; alternative: use Carla |
| SSL12 not detected | No voice input | Use system mic or pre-recorded audio for demo |
| 12 days too tight | Incomplete demo | Ruthless scope: P0 only, everything else is stretch |
