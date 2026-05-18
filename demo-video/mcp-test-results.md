# AudioShuttle MCP Tool Preflight Report
Generated: 2026-05-17 19:20:43 UTC
Host: 7995x-cachyos

## Tool: `daw_state`
**Command:** `mcp.call_tool('daw_state', {})`
**Status:** ✅ SUCCESS
**Round-trip Time:** 10ms

**Response:**
```json
{
  "connected": true,
  "daw": "reaper",
  "track_count": 8,
  "tracks": [
    {
      "number": 1,
      "name": "Keys",
      "volume": 1.0,
      "pan": 0.0,
      "muted": false,
      "soloed": false,
      "armed": false,
      "color": "#9966ff"
    },
    {
      "number": 2,
      "name": "Lead Guitar",
      "volume": 1.0,
      "pan": 0.0,
      "muted": false,
      "soloed": false,
      "armed": false,
      "color": "#ff9933"
    },
    {
      "number": 3,
      "name": "Bass",
      "volume": 1.0,
      "pan": 0.0,
      "muted": false,
      "soloed": false,
      "armed": false,
      "color": "#3366ff"
    },
    {
      "number": 4,
      "name": "Vocals",
      "volume": 1.0,
      "pan": 0.0,
      "muted": false,
      "soloed": false,
      "armed": false,
      "color": "#ff3366"
    },
    {
      "number": 5,
      "name": "Rhythm Guitar",
      "volume": 1.0,
      "pan": 0.0,
      "muted": false,
      "soloed": false,
      "armed": false,
      "color": "#ff9933"
    },
    {
      "number": 6,
      "name": "Drums",
      "volume": 1.0,
      "pan": 0.0,
      "muted": false,
      "soloed": false,
      "armed": false,
      "color": "#99cc33"
    },
    {
      "number": 7,
      "name": "Guitars Bus",
      "volume": 1.0,
      "pan": 0.0,
      "muted": false,
      "soloed": false,
      "armed": false,
      "color": "#ff9933"
    },
    {
      "number": 8,
      "name": "Submaster",
      "volume": 1.0,
      "pan": 0.0,
      "muted": false,
      "soloed": false,
      "armed": false,
      "color": "#ffffff"
    }
  ],
  "transport": {
    "playing": false,
    "recording": false,
    "position_seconds": 0.0,
    "tempo": 120.0
  }
}
```

---
## Tool: `daw_command`
**Command:** `mcp.call_tool('daw_command', {"command": "list all tracks"})`
**Status:** ✅ SUCCESS
**Round-trip Time:** 241ms

**Response:**
```json
{
  "success": true,
  "command": "list all tracks",
  "executed": 1,
  "results": [
    {
      "tool": "list_tracks",
      "action": "query",
      "note": "State query"
    }
  ],
  "errors": [],
  "summary": "No actions taken"
}
```

---
## Tool: `daw_thinking`
**Command:** `mcp.call_tool('daw_thinking', {"n": 50})`
**Status:** ✅ SUCCESS
**Round-trip Time:** 0ms

**Response:**
```json
{
  "count": 2,
  "events": [
    {
      "ts": 1779045643.618037,
      "type": "content_token",
      "source": "stt",
      "text": "Heard: list all tracks"
    },
    {
      "ts": 1779045643.802229,
      "type": "tool_call",
      "source": "translator",
      "text": "list_tracks({})"
    }
  ]
}
```

---
## Tool: `daw_interrupt`
**Command:** `mcp.call_tool('daw_interrupt', {"reason": "preflight test"})`
**Status:** ✅ SUCCESS
**Round-trip Time:** 0ms

**Response:**
```json
{
  "interrupted": true,
  "reason": "preflight test"
}
```

---
## Tool: `transcribe_audio`
**Command:** `mcp.call_tool('transcribe_audio', {"audio_path": "/tmp/dummy.wav"})`
**Status:** ✅ SUCCESS
**Round-trip Time:** 0ms

**Response:**
```json
{
  "success": false,
  "error": "faster-whisper not installed. Install with: pip install audioshuttle[stt]"
}
```

---
