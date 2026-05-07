---
phase: 04-web-ui-integration
plan: 02
status: complete
commits:
  - 85431aa: feat(04-02): input tab (system prompt editor) + output tab (DAW config)
tech_stack:
  added:
    - Input tab (web_routes/input_tab.py): system prompt editor with save/persist
    - Output tab (web_routes/output_tab.py): DAW preset dropdown, rescan, OSC mappings
    - update_system_prompt (translator.py): runtime prompt update function
subsystem: web-ui
---

## Plan 04-02: Input Tab + Output Tab — COMPLETE

### What was built

**Task 1 (commit `85431aa`): Input tab**
- `web_routes/input_tab.py`: GET /input (system prompt textarea + AI client info), POST /input/system-prompt (save to file + update in-memory)
- `templates/input.html`: System prompt textarea, save button, AI client table, chat API config display
- `translator.py`: Added `update_system_prompt()` global function
- System prompt persisted to `~/.audioshuttle/system-prompt.txt`
- Save confirmation shown via `?saved=1` query param

**Task 2 (commit `85431aa`): Output tab**
- `web_routes/output_tab.py`: GET /output (detection, presets, mappings), POST /output/daw-preset, POST /output/rescan
- `templates/output.html`: DAW detection badges, preset dropdown, rescan button, connection info, OSC mappings table
- Uses daw_detect module for rescan
- OSC mappings from bridge._ADDRESS_PATTERNS when bridge available

### Verified
- All 3 routes work (GET /input, GET /output, POST forms)
- System prompt save persists to file and updates in-memory
- DAW preset change and rescan work
- Nav tabs link correctly between pages
