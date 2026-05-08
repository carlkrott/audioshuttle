# AudioShuttle — Human E2E Test Checklist

**Service running at:** http://localhost:8765
**AudioShuttle PID:** `systemctl status audioshuttle`
**Reaper:** Must be open with a multi-track project

---

## Setup

- [ ] Reaper is running with at least 3-4 named tracks (e.g. Drums, Bass, Vocals, Guitar)
- [ ] Reaper OSC is enabled (Preferences → Control/OSC/web → OSC device on port 8000/9000)
- [ ] AudioShuttle service is running: `systemctl status audioshuttle`
- [ ] Open http://localhost:8765 in a browser

---

## 1. Home Dashboard

- [ ] Page loads with dark theme, "AudioShuttle" title
- [ ] **Reaper status card** shows green "Connected" with pulsing dot
- [ ] **MCP Server** card shows green "Running"
- [ ] **STT (Whisper)** card shows green "Available"
- [ ] **Voice** card shows "Web Only" (expected — no global hotkey in this env)
- [ ] **Transport buttons** are visible: ▶ Play, ⏹ Stop, ⏺ Record, ⏸ Pause

## 2. Transport Controls

- [ ] Click **▶ Play** → Reaper transport starts playing
- [ ] Click **⏹ Stop** → Reaper transport stops
- [ ] Click **⏺ Record** → Reaper arms for recording (then stop it)
- [ ] Click **⏸ Pause** → Reaper pauses

## 3. Command History

- [ ] After using transport, command history section shows entries
- [ ] Each entry has timestamp + command name + tool
- [ ] Click a history entry → it replays the command

## 4. Input Tab — System Prompt

- [ ] Navigate to **Input** tab (nav bar)
- [ ] System prompt textarea is populated with default prompt
- [ ] Edit the prompt → click **Save** → "✓ Saved" appears
- [ ] AI Client section shows Chat API URL and Model Name

## 5. Input Tab — Voice Recording

- [ ] **"Clean up voice text with AI"** checkbox is present and checked
- [ ] Red 🎤 record button is visible
- [ ] Click the mic button → browser asks for microphone permission
- [ ] Grant permission → "Recording..." indicator appears with pulsing red dot
- [ ] Speak: "mute the drums" → click stop
- [ ] Transcription appears in result area
- [ ] If Cleanup is on: both "Heard:" and "Cleaned:" text shown
- [ ] Command is executed (Reaper responds)

## 6. Output Tab

- [ ] Navigate to **Output** tab
- [ ] Reaper shows as "Running" in DAW Detection
- [ ] DAW Preset dropdown shows Reaper/Ardour
- [ **OSC Address Mappings** table lists patterns
- [ ] **Track Presets** section: type name → click "Save Current"
- [ ] Preset appears in list → click "Load" → works

## 7. MIDI Tab

- [ ] Navigate to **MIDI** tab
- [ ] Role dropdown shows: Drums, Rhythm, Lead, Melody
- [ ] Select **Drums** → click **🎲 Randomize**
- [ ] 16-bar step sequencer grid appears with colored cells (green = active)
- [ ] Grid shows velocity levels (off/low/mid/high)
- [ ] "Send to E2B" section has description textarea + Send button
- [ ] Change role to **Melody** → Randomize again → different pattern density

## 8. Log Tab

- [ ] Navigate to **Log** tab
- [ ] Color-coded log entries visible (green info, yellow warning, red error)
- [ ] Filter buttons: All, Info, Warning, Error
- [ ] Click **Error** filter → only error entries shown
- [ ] Click **All** → all entries return
- [ ] Log auto-scrolls to bottom

## 9. Shortcuts Tab

- [ ] Navigate to **Shortcuts** tab
- [ ] "MCP Tools Reference (20)" header visible
- [ ] 7 categories listed: Transport, Track Control, Master, FX, DAW, AI, System
- [ ] Type "volume" in search box → filters to matching tools
- [ ] Clear search → all tools return

## 10. Full Voice Command Flow

- [ ] Go to Input tab, ensure Cleanup is checked
- [ ] Record: "turn up the drums a little"
- [ ] Verify: transcription shows your words
- [ ] Verify: cleaned text removes fillers if any
- [ ] Verify: command section shows the translated OSC command
- [ ] Verify: Reaper's drums track fader moves up
- [ ] Record: "pan the bass left"
- [ ] Verify: Reaper's bass track pans left
- [ ] Uncheck Cleanup → Record another command
- [ ] Verify: no "Cleaned:" section (raw text goes straight to translator)

## 11. Edge Cases

- [ ] Type garbage in replay URL: `http://localhost:8765/replay?cmd=asdfghjkl` → no crash, redirects home
- [ ] Refresh any page → loads correctly (no 500 errors)
- [ ] Open Log tab → entries from your session are present
- [ ] Open Home tab → command history has your commands

---

## After Testing

Stop the service:
```bash
systemctl stop audioshuttle
```

Restart later:
```bash
systemctl start audioshuttle
```
