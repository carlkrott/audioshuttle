---
phase: 04-web-ui-integration
plan: 04
status: complete
commits:
  - 4a547ea: feat(04-04): system tray icon + unified launcher + CLI update
tech_stack:
  added:
    - TrayIcon (tray.py): pystray wrapper with Open Web UI + Quit menu, icon image generation
    - launch() (launcher.py): unified startup (model → web → tray), signal handling, cleanup
    - Updated CLI (cli.py): standalone/stdio modes, --no-browser, --no-tray flags
subsystem: launcher
---

## Plan 04-04: System Tray + Unified Launcher — COMPLETE

### What was built

**Task 1 (commit `4a547ea`): System tray icon**
- `tray.py`: TrayIcon class wrapping pystray
  - 64x64 programmatically generated icon (green rounded rectangle with play symbol)
  - Menu: "Open Web UI" (default), "Quit"
  - `start()` blocking (main thread), `stop()` from any thread
  - `notify()` for system tray toasts
  - Graceful degradation when pystray/Pillow not installed

**Task 2 (commit `4a547ea`): Unified launcher + CLI update**
- `launcher.py`: `launch()` function orchestrating startup sequence:
  1. Configure logging
  2. Create bridge, model server, translator, context manager
  3. Create web app with shared components
  4. Start uvicorn in daemon thread
  5. Auto-open browser (2s delay)
  6. Start tray icon in main thread (blocking)
  7. Signal handling (SIGINT/SIGTERM) for clean shutdown
- `cli.py`: Updated entry point with:
  - `--transport {standalone,stdio}` (default: standalone)
  - `--no-browser` flag
  - `--no-tray` flag
  - `--host` and `--port` overrides

### Verified
- TrayIcon creates icon image (64x64), handles missing pystray
- CLI shows all new flags in --help
- launch() function has correct signature
- 113 existing tests still pass
