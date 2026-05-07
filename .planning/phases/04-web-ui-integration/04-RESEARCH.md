# Phase 4 Research: Web UI + Integration

> Research date: 2026-05-07
> Confidence: HIGH (verified on live system, source code analysis, official docs)

## Standard Stack

| Component | Library | Version | Why |
|-----------|---------|---------|-----|
| Web framework | FastAPI | 0.128+ | Already in `[web]` deps, async, Jinja2 support built-in |
| Templates | Jinja2 | 3.1+ | Already in `[web]` deps, server-rendered multi-tab UI |
| Forms | python-multipart | 0.0.9+ | Already in `[web]` deps, needed for form POST handling |
| System tray | pystray | 0.19+ | Already in `[tray]` deps, only cross-platform Python tray lib |
| Tray icon image | Pillow | 10.0+ | Already in `[tray]` deps, for generating tray icon PNG |
| OSC (Ardour) | python-osc | 1.9+ | Already a core dep, same library for Ardour as Reaper |
| Browser launch | webbrowser | stdlib | Zero deps, works on Linux with `xdg-open` |
| GPU monitoring | sysfs `/sys/class/drm/` | kernel | No external deps, direct file reads |
| Process detection | subprocess + `pgrep` | stdlib | Reliable, used by `systemd`, no external deps |
| Markdown output | stdlib only | — | Obsidian vault files are plain markdown, no lib needed |

## Architecture Patterns

### 1. FastAPI + Jinja2 Multi-Tab Settings App

**Pattern: Server-rendered with HTMX-style progressive enhancement.**

AudioShuttle's web UI is a **configurator, not a mixer**. Server-rendered HTML is the correct choice — no SPA framework needed. The established pattern:

```
src/audioshuttle/
├── web.py              # FastAPI app factory, mounts routes
├── web_routes/         # Route modules
│   ├── __init__.py
│   ├── home.py         # GET / — error log + status badges
│   ├── input.py        # GET/POST /input — AI config tab
│   └── output.py       # GET/POST /output — DAW config tab
└── templates/           # Jinja2 HTML templates
    ├── base.html        # Shared layout: nav tabs, status bar
    ├── home.html        # Error log (scrolling <pre>), status badges
    ├── input.html       # System prompt textarea, AI config
    └── output.html      # DAW preset, OSC mappings table
```

**Key pattern — `Jinja2Templates` mounting:**

```python
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AudioShuttle")
templates = Jinja2Templates(directory="src/audioshuttle/templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("home.html", {
        "request": request,
        "errors": error_log.get_recent(50),
        "status": get_all_status(),
    })

@app.post("/output/osc-map")
async def update_osc_map(mapping: str = Form(...)):
    # Save OSC mapping, redirect back
    return RedirectResponse(url="/output", status_code=303)
```

**Tab navigation:** Pure HTML `<nav>` with links. No JavaScript needed. Each tab is a separate route that renders the full page with the active tab highlighted. Status badges in `base.html` are populated by a context processor.

**Error log on Home tab:** A `<pre id="error-log">` element. For live updates without JS, use a simple meta-refresh or an SSE endpoint. **Recommendation: start with static (page refresh), add SSE later if needed.**

**Toast notifications:** Use pystray's `icon.notify()` for system-level toasts, NOT browser notifications. The web UI error log is always visible on the Home tab.

### 2. pystray on Linux — System Tray Icon

**Pattern: Run pystray in main thread, FastAPI in background thread.**

pystray's `icon.run()` **must be called from the main thread** on macOS (OSX requirement). On Linux this isn't strictly required, but for cross-platform consistency, run pystray in the main thread and uvicorn in a daemon thread.

**Backend selection:** On Linux with CachyOS/KDE/GNOME, pystray auto-selects `appindicator` (preferred) or falls back to `gtk`. The `appindicator` backend supports menus and notifications but NOT default click action. Check `Icon.HAS_NOTIFICATION` at runtime.

```python
import pystray
from PIL import Image, ImageDraw
from threading import Thread
import uvicorn

def create_icon_image():
    """Generate a simple 64x64 icon programmatically."""
    img = Image.new('RGB', (64, 64), (30, 30, 30))
    dc = ImageDraw.Draw(img)
    dc.rectangle([16, 8, 48, 56], fill=(0, 180, 100))  # Shuttle shape
    return img

def on_open_web(icon, item):
    import webbrowser
    webbrowser.open("http://127.0.0.1:8765")

def on_quit(icon, item):
    icon.stop()
    # Signal uvicorn to shut down

icon = pystray.Icon(
    'AudioShuttle',
    icon=create_icon_image(),
    menu=pystray.Menu(
        pystray.MenuItem('Open Web UI', on_open_web, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Quit', on_quit),
    ),
)

# Start FastAPI in background thread
def run_web():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

web_thread = Thread(target=run_web, daemon=True)
web_thread.start()

# Open browser after short delay
import threading
threading.Timer(2.0, lambda: webbrowser.open("http://127.0.0.1:8765")).start()

# Block here — pystray runs main loop
icon.run()
```

**Key constraints:**
- `icon.run()` is blocking. MUST be in main thread for macOS compat.
- `icon.notify(msg, title)` for system tray notifications. Check `Icon.HAS_NOTIFICATION`.
- Menu items can have dynamic `checked`, `enabled`, `visible` via callables.
- Call `icon.update_menu()` when dynamic state changes externally.
- On Xorg (no desktop env): menus are NOT supported. Only default action works.

**Notification for errors:** The web routes can call `icon.notify(error_msg, "AudioShuttle Error")` when an error occurs. The tray icon module exposes a global icon reference.

### 3. Ardour OSC Protocol vs Reaper OSC

**Critical finding: Ardour OSC is fundamentally different from Reaper OSC.**

| Aspect | Reaper | Ardour |
|--------|--------|--------|
| **Default port** | 8000 (out), 9000 (feedback) | 3819 (bidirectional) |
| **Track numbering** | 1-based (`/track/1/volume`) | 0-based (`/strip/0/fader`) |
| **Naming convention** | `/track/N/property` | `/strip/N/property` |
| **Surface setup** | None needed | **Required**: `/set_surface` before use |
| **Strip discovery** | Manual probe (`/track/N/name`) | `/strip/list` returns all strips |
| **Transport** | `/play`, `/stop`, `/record` | `/transport_play`, `/transport_stop` |
| **Volume** | `/track/N/volume` (0.0-1.0) | `/strip/N/fader` (0.0-1.0) or `/strip/N/gain` (dB) |
| **Mute** | `/track/N/mute` | `/strip/N/mute` |
| **Solo** | `/track/N/solo` | `/strip/N/solo` |
| **Pan** | `/track/N/pan` (-1 to 1) | `/strip/N/pan_stereo_position` (-1 to 1) |
| **Record arm** | `/track/N/recarm` | `/strip/N/recenable` |
| **FX/Plugin** | `/track/N/fx/F/fxparam/P/value` | `/select/strip` then `/select/plugin` then `/select/plugin/parameter` |
| **Actions** | `/action` + command_id | `/access_action` + action path string |
| **Feedback** | Automatic, same addresses | Requires `/set_surface` with feedback flags |

**Ardour OSC requires a handshake:**

1. Send `/set_surface bank_size strip_types feedback` (e.g., `0 159 0`)
   - `strip_types` is a bitmask: 1=AudioTracks, 2=MidiTracks, 4=AudioBusses, 8=MidiBusses, 16=VCAs, 32=Master, 64=Monitor
   - 159 = all except hidden
2. Send `/strip/list` to get all strips
3. Receive `/reply` messages with strip data: `(ssid, type, name, inputs, outputs, mute, solo)`
4. Receive `/end_route_list` when done

**Architecture for multi-DAW support:**

```python
class DAWBridge(Protocol):
    """Abstract DAW OSC bridge interface."""
    def connect(self) -> bool: ...
    def transport_play(self) -> CommandResult: ...
    def set_track_volume(self, track: int, value: float) -> CommandResult: ...
    # ... etc

class ReaperBridge(DAWBridge):
    """Existing ReaperOSC class, adapted to protocol."""
    
class ArdourBridge(DAWBridge):
    """New Ardour OSC bridge with 0-based strips and surface setup."""
```

The existing `osc_bridge.py` already has the Reaper whitelist patterns. For Ardour, create `ardour_bridge.py` with Ardour-specific patterns. The `server.py` tools call the `DAWBridge` protocol, not the concrete class.

**Source:** Ron-312/ardour-mcp repo (osc_client.py, osc_listener.py), Ardour source code (libs/surfaces/osc/), multiple community OSC implementations.

### 4. Context Compaction for Local LLM

**Pattern: Rolling context with periodic summarization.**

llama-server with `--parallel 2` provides two independent slots. Slot 1 for translation, Slot 2 for skill learning. Each slot has its own context window (8192 tokens total, shared).

**Compaction pipeline:**

```
User commands → accumulated in context (messages list)
                ↓ (when approaching context limit)
Model generates summary → compacted context replaces history
                ↓ (when session ends)
Full session dumped to Obsidian vault
                ↓ (skill extraction)
Slot 2 reads current-skill.md as part of its system prompt
```

**Implementation:**

```python
class ContextManager:
    """Manages rolling context for the E2B model."""
    
    def __init__(self, max_messages: int = 40, max_chars: int = 6000):
        self.messages: list[dict] = []
        self.max_messages = max_messages
        self.max_chars = max_chars
    
    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if self._should_compact():
            self._compact()
    
    def _should_compact(self) -> bool:
        total_chars = sum(len(m["content"]) for m in self.messages)
        return total_chars > self.max_chars or len(self.messages) > self.max_messages
    
    def _compact(self):
        """Ask model to summarize older messages, keep recent ones."""
        old = self.messages[:-10]  # Keep last 10
        recent = self.messages[-10:]
        
        summary_prompt = {
            "role": "user",
            "content": f"Summarize this conversation in 200 words or less. "
                       f"Focus on user preferences, DAW settings, and workflow patterns:\n"
                       + "\n".join(m["content"][:200] for m in old)
        }
        summary = model_server.chat(
            [summary_prompt], temperature=0.3, max_tokens=300
        )
        self.messages = [
            {"role": "system", "content": f"Previous session summary: {summary}"},
            *recent,
        ]
    
    def dump_session(self, vault_path: Path):
        """Dump full session to Obsidian vault."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        session_file = vault_path / "sessions" / f"{timestamp}.md"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(self._render_markdown())
    
    def _render_markdown(self) -> str:
        lines = [f"# Session {datetime.now().isoformat()}", ""]
        for m in self.messages:
            role = m["role"].title()
            lines.append(f"**{role}:** {m['content']}", "")
        return "\n".join(lines)
```

**Do NOT hand-roll:** The summarization prompt itself. Use a well-tested template that preserves key facts (track names, user preferences, workflow patterns).

### 5. DAW Auto-Detection on Linux

**Pattern: `pgrep` + port probe.**

```python
import subprocess
import httpx

def detect_daw() -> dict[str, Any]:
    """Detect running DAWs on the local system."""
    results = {}
    
    # Method 1: Process detection via pgrep
    for name, pattern in [("reaper", "reaper"), ("ardour", "ardour")]:
        try:
            r = subprocess.run(
                ["pgrep", "-c", "-x", pattern],
                capture_output=True, text=True, timeout=2
            )
            results[name] = {"running": r.returncode == 0}
        except Exception:
            results[name] = {"running": False}
    
    # Method 2: Port probe (confirms OSC is actually listening)
    # Reaper default: 8000
    # Ardour default: 3819
    for name, port in [("reaper", 8000), ("ardour", 3819)]:
        try:
            # Send a UDP ping — if no ICMP unreachable, port is open
            from pythonosc import udp_client
            client = udp_client.SimpleUDPClient("127.0.0.1", port)
            client.send_message("/track/count", [])  # Reaper
            # Wait briefly for feedback
        except Exception:
            results[name]["osc_responsive"] = False
    
    return results
```

**Important:** `pgrep -x reaper` matches exact process name. The kernel `oom_reaper` thread would match without `-x`. Always use `-x` for exact match.

**Verified on this system:** `pgrep -a reaper` returns `/usr/lib/REAPER/reaper` (PID 3978354). `pgrep -a ardour` returns nothing (Ardour not installed).

### 6. Browser Launch on Startup

**Use `webbrowser.open()` from stdlib.** Do NOT use `subprocess(['xdg-open', ...])` — webbrowser handles edge cases, detects default browser, and is cross-platform.

```python
import webbrowser
import threading

# Launch browser AFTER server is ready, in a separate thread
# so it doesn't block the tray icon's main thread
threading.Timer(2.0, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
```

**Why threading.Timer:** The server needs a moment to bind the port. 2 seconds is generous. The timer runs in a daemon thread so it doesn't prevent shutdown.

### 7. GPU Memory Monitoring (ROCm)

**Pattern: Read AMD GPU VRAM from sysfs. No external deps needed.**

Verified on this system — the RX 6950 XT reports VRAM via `/sys/class/drm/card1/device/`:

```
mem_info_vram_total     → 16368 MB
mem_info_vram_used      → 1723 MB
mem_info_vis_vram_total → 512 MB (visible VRAM)
mem_info_vis_vram_used  → 16 MB
```

**Implementation:**

```python
import glob

def get_gpu_vram(card_index: int = 1) -> dict[str, int]:
    """Read VRAM usage from AMD GPU sysfs.
    
    Args:
        card_index: DRM card index (0=iGPU, 1=discrete GPU)
    """
    base = f"/sys/class/drm/card{card_index}/device"
    try:
        with open(f"{base}/mem_info_vram_total") as f:
            total = int(f.read().strip())
        with open(f"{base}/mem_info_vram_used") as f:
            used = int(f.read().strip())
        return {
            "vram_total_mb": total // (1024 * 1024),
            "vram_used_mb": used // (1024 * 1024),
            "vram_used_pct": round(used / total * 100, 1),
        }
    except FileNotFoundError:
        return {"vram_total_mb": 0, "vram_used_mb": 0, "vram_used_pct": 0.0}
```

**Note:** `card0` on this system is the iGPU (512MB), `card1` is the RX 6950 XT (16GB). The config already has `model_gpu_device: 0` which maps to `HIP_VISIBLE_DEVICES=0`, but the DRM card index may differ from the HIP device index. On this system, HIP device 0 = RX 6950 XT = DRM card1. **Always verify the mapping.**

**Alternative: llama-server `/health` endpoint** — when the model server is running, its `/health` endpoint returns `{"status": "ok"}` and `/props` may return slot/memory info. But this requires the server to be up. sysfs always works.

## Don't Hand-Roll

| Problem | Use Instead | Why |
|---------|-------------|-----|
| System tray icon | pystray | Only mature cross-platform Python tray lib. Handles backend selection, menus, notifications. |
| Tray icon image | Pillow `ImageDraw` | Generate programmatically, avoid bundling PNG files. |
| Browser launch | `webbrowser.open()` | stdlib, handles Linux/macOS/Windows, no subprocess hacks. |
| GPU VRAM stats | sysfs `/sys/class/drm/cardN/device/mem_info_*` | Direct kernel interface, zero deps, always available. |
| DAW detection | `pgrep -x` | Reliable, used by systemd, handles zombie processes. |
| HTML templates | Jinja2 via FastAPI `Jinja2Templates` | Built-in integration, auto-escaping, template inheritance. |
| Form handling | FastAPI `Form(...)` + `RedirectResponse(303)` | Standard post-redirect-get pattern, avoids resubmit. |
| OSC protocol | python-osc (already used) | Same lib works for Ardour, just different addresses. |
| Context compaction prompt | Tested summarization template | Don't improvise — use structured extraction of facts/preferences. |
| Ardour OSC handshake | Follow `/set_surface` → `/strip/list` → `/reply` pattern | Ardour REQUIRES surface setup before responding. |

## Common Pitfalls

### 1. Ardour OSC Requires Surface Setup
**Pitfall:** Sending OSC commands to Ardour without calling `/set_surface` first results in silence — no feedback, no strip list, no response.
**Fix:** Always send `/set_surface bank_size strip_types feedback` before any other command. Wait for `/end_route_list` after `/strip/list`.

### 2. Ardour Uses 0-Based Strip Indices
**Pitfall:** Reaper uses 1-based track numbers (`/track/1/volume`). Ardour uses 0-based strip indices (`/strip/0/fader`). Mixing these up sends commands to the wrong track.
**Fix:** The `ArdourBridge` class must convert the user-facing 1-based track numbers to 0-based strip indices internally.

### 3. pystray Must Run in Main Thread
**Pitfall:** Calling `icon.run()` from a background thread silently fails on macOS and may cause issues on some Linux desktop environments.
**Fix:** Run pystray in the main thread. Run uvicorn in a daemon thread. The main thread blocks on `icon.run()`.

### 4. pgrep Without `-x` Matches Partial Names
**Pitfall:** `pgrep reaper` matches the kernel thread `oom_reaper`, giving false positives.
**Fix:** Always use `pgrep -x reaper` for exact process name matching.

### 5. HIP Device Index ≠ DRM Card Index
**Pitfall:** `HIP_VISIBLE_DEVICES=0` maps to the first ROCm-visible GPU, but `/sys/class/drm/card0` may be an iGPU, not the dGPU.
**Fix:** Probe sysfs for the correct card, or use `HIP_VISIBLE_DEVICES` enumeration to find the match. On this system: HIP device 0 = RX 6950 XT = DRM card1.

### 6. Context Compaction Loses Track Name Mappings
**Pitfall:** Summarizing chat history may drop the mapping of track names to numbers that the model learned from DAW state.
**Fix:** Always include current DAW state (track names + numbers) in the system prompt, not in the conversation history. The compaction only summarizes conversation turns.

### 7. Jinja2 Template Auto-Escaping and Forms
**Pitfall:** FastAPI's `Jinja2Templates` enables auto-escaping by default. User input in OSC addresses or system prompts with special characters (`{{`, `}}`, `<`, `>`) will be escaped.
**Fix:** This is actually correct behavior (prevents XSS). For displaying raw content, use `{{ content | safe }}` only for trusted server-generated content, never for user input.

### 8. Post-Redirect-Get Pattern for Forms
**Pitfall:** After a POST form submission, rendering a template directly causes browser "resubmit?" warnings on refresh.
**Fix:** Always return `RedirectResponse(url="...", status_code=303)` after POST. The 303 status code tells the browser to GET the redirect target.

## Code Examples

### FastAPI App Factory with Template Tabs

```python
# web.py
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from pathlib import Path

def create_web_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="AudioShuttle", docs_url=None, redoc_url=None)
    
    templates = Jinja2Templates(
        directory=str(Path(__file__).parent / "templates")
    )
    
    # Store shared state
    app.state.settings = settings
    app.state.templates = templates
    app.state.error_log = ErrorLog(max_entries=200)
    
    # Import and mount routes
    from audioshuttle.web_routes import home, input_tab, output_tab
    app.include_router(home.router)
    app.include_router(input_tab.router)
    app.include_router(output_tab.router)
    
    return app
```

### Status Badge Context Processor

```python
# web_routes/home.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    app = request.app
    status = {
        "daw_connected": bridge.is_connected,
        "daw_name": "Reaper" if settings.daw_type == "reaper" else "Ardour",
        "mcp_running": True,
        "model_loaded": model_server.is_running if model_server else False,
        "model_state": get_model_state(),  # "running" | "compacting" | "idle" | "error"
        "gpu_vram": get_gpu_vram(card_index=1),
    }
    return app.state.templates.TemplateResponse("home.html", {
        "request": request,
        "status": status,
        "errors": app.state.error_log.get_recent(50),
    })
```

### DAWBridge Protocol for Multi-DAW

```python
# daw_protocol.py
from typing import Protocol

class DAWBridge(Protocol):
    @property
    def is_connected(self) -> bool: ...
    
    def transport_play(self) -> CommandResult: ...
    def transport_stop(self) -> CommandResult: ...
    def transport_record(self) -> CommandResult: ...
    def set_track_volume(self, track: int, value: float) -> CommandResult: ...
    def set_track_mute(self, track: int, mute: bool) -> CommandResult: ...
    def set_track_solo(self, track: int, solo: bool) -> CommandResult: ...
    def set_track_pan(self, track: int, pan: float) -> CommandResult: ...
    def set_master_volume(self, value: float) -> CommandResult: ...
    def refresh_state(self, wait: float = 0.5) -> DAWState: ...
    def close(self) -> None: ...

# ardour_bridge.py
class ArdourBridge:
    """OSC bridge for Ardour DAW."""
    
    _ADDRESS_MAP = {
        "play": "/transport_play",
        "stop": "/transport_stop",
        "record": "/rec_enable_toggle",
        "rewind": "/goto_start",
        "forward": "/goto_end",
    }
    
    def __init__(self, host: str = "127.0.0.1", port: int = 3819):
        self._client = udp_client.SimpleUDPClient(host, port)
        self._strip_count = 0
        # ... setup_surface() must be called after init
    
    def setup_surface(self, bank_size=0, strip_types=159, feedback=0):
        self._client.send_message("/set_surface", [bank_size, strip_types, feedback])
    
    def set_track_volume(self, track: int, value: float) -> CommandResult:
        # Ardour uses 0-based strip index
        strip_idx = track - 1
        return self._send(f"/strip/{strip_idx}/fader", value)
    
    def set_track_pan(self, track: int, pan: float) -> CommandResult:
        strip_idx = track - 1
        return self._send(f"/strip/{strip_idx}/pan_stereo_position", pan)
```

### System Tray Integration with Error Notifications

```python
# tray.py
import pystray
from PIL import Image, ImageDraw
from typing import Optional

_tray_icon: Optional[pystray.Icon] = None

def get_tray() -> Optional[pystray.Icon]:
    return _tray_icon

def notify_error(message: str):
    """Call from anywhere to show system tray error notification."""
    icon = get_tray()
    if icon and icon.HAS_NOTIFICATION:
        icon.notify(message, "AudioShuttle Error")

def create_tray_icon(open_callback, quit_callback) -> pystray.Icon:
    global _tray_icon
    
    img = Image.new('RGB', (64, 64), (40, 40, 40))
    dc = ImageDraw.Draw(img)
    dc.polygon([(32, 8), (56, 32), (32, 56), (8, 32)], fill=(0, 200, 120))
    
    _tray_icon = pystray.Icon(
        'AudioShuttle',
        icon=img,
        menu=pystray.Menu(
            pystray.MenuItem('Open Web UI', open_callback, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', quit_callback),
        ),
    )
    return _tray_icon
```

### GPU VRAM Monitor

```python
# gpu_monitor.py
from pathlib import Path

def get_gpu_vram(card_index: int = 1) -> dict:
    """Read AMD GPU VRAM from sysfs. Returns MB values."""
    base = Path(f"/sys/class/drm/card{card_index}/device")
    try:
        total = int((base / "mem_info_vram_total").read_text().strip())
        used = int((base / "mem_info_vram_used").read_text().strip())
        return {
            "total_mb": total // 1048576,
            "used_mb": used // 1048576,
            "percent": round(used / total * 100, 1) if total > 0 else 0,
        }
    except FileNotFoundError:
        return {"total_mb": 0, "used_mb": 0, "percent": 0.0}
```

### Obsidian Vault Session Dumper

```python
# memory.py
from datetime import datetime
from pathlib import Path

def dump_session(vault_path: Path, messages: list[dict], metadata: dict):
    """Dump a session to the Obsidian vault."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sessions_dir = vault_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    
    lines = [
        f"---",
        f"date: {datetime.now().isoformat()}",
        f"track_count: {metadata.get('track_count', 0)}",
        f"commands: {metadata.get('command_count', 0)}",
        f"---",
        f"",
        f"# Session {ts}",
        f"",
    ]
    for msg in messages:
        role = msg["role"].title()
        lines.append(f"**{role}:** {msg['content']}")
        lines.append("")
    
    (sessions_dir / f"{ts}.md").write_text("\n".join(lines))

def update_skill_file(vault_path: Path, summary: str):
    """Update the current-skill.md file for slot 2 to read."""
    skills_dir = vault_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "current-skill.md").write_text(
        f"# Current Skill Profile\n\n{summary}\n"
    )
```

## Confidence Levels

| Finding | Confidence | Basis |
|---------|-----------|-------|
| pystray main-thread requirement | HIGH | Official pystray docs, verified pattern |
| Ardour OSC address differences | HIGH | Ron-312/ardour-mcp source code, multiple community implementations |
| Ardour requires `/set_surface` handshake | HIGH | ardour-mcp osc_client.py, Ardour manual references |
| Ardour 0-based strip indexing | HIGH | ardour-mcp osc_client.py line-by-line analysis |
| sysfs VRAM monitoring path | HIGH | Verified live on this system |
| pgrep `-x` for exact match | HIGH | Verified live (oom_reaper false positive observed) |
| FastAPI + Jinja2 template pattern | HIGH | FastAPI official docs, established pattern |
| webbrowser.open() for startup | HIGH | Python stdlib, standard practice |
| Context compaction approach | MEDIUM | No llama-server-specific feature; hand-rolled summarization. Pattern is sound but prompt engineering may need iteration. |
| HIP device 0 = DRM card1 mapping | MEDIUM | Verified on this system but may differ on other hardware configs |
