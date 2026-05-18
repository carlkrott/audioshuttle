#!/bin/bash
# AudioShuttle Demo Video Recorder
# ================================
# Records a ~2 minute demo of the full AudioShuttle pipeline:
# text commands → Gemma 4 E4B translation → Reaper DAW control
#
# Uses gpu-screen-recorder for native Wayland/KDE capture (DP-2 = U28D590)
# and launches the web UI alongside Reaper for side-by-side recording.
#
# Prerequisites:
#   - Reaper running on the U28D590 (leftmost monitor)
#   - AudioShuttle container running (docker compose up)
#   - gpu-screen-recorder installed
#   - Run as korphaus user on the host
#
# Usage:
#   bash scripts/demo_video.sh           # Record full demo
#   bash scripts/demo_video.sh --dry-run # Print commands only
#   bash scripts/demo_video.sh --cmds    # Just run commands (no recording)

set -euo pipefail

# === CONFIG ===
MONITOR="DP-2"              # U28D590 (leftmost 4K monitor)
FPS=30
OUTPUT_DIR="/tmp/audioshuttle_demo"
VIDEO_FILE="$OUTPUT_DIR/audioshuttle_demo_raw.mp4"
FINAL_FILE="$OUTPUT_DIR/audioshuttle_demo_final.mp4"
SUBTITLE_FILE="$OUTPUT_DIR/subs.ass"
LOG_FILE="$OUTPUT_DIR/recording.log"
REPLAY_URL="http://localhost:8765/replay"
STATE_URL="http://localhost:8765/state"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Timing
CMD_DELAY=3

DRY_RUN=false
CMDS_ONLY=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true
[[ "${1:-}" == "--cmds" ]] && CMDS_ONLY=true

# GSR process
GSR_PID=""

# === SETUP ===
mkdir -p "$OUTPUT_DIR"

log() { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
ok()  { echo -e "${GREEN}[OK]${NC} $*"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERR]${NC} $*" >&2; }

send_cmd() {
    local cmd="$1"
    local desc="$2"
    local delay="${3:-$CMD_DELAY}"

    log "CMD: $desc"
    log "  → \"$cmd\""

    if $DRY_RUN; then
        local encoded
        encoded=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$cmd'))")
        echo "  curl \"$REPLAY_URL?cmd=$encoded\""
    else
        curl -s "$REPLAY_URL?cmd=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$cmd'))")" > /dev/null 2>&1
    fi

    sleep "$delay"
}

# === PREREQUISITES ===
check_prereqs() {
    log "Checking prerequisites..."

    if ! curl -s "$STATE_URL" > /dev/null 2>&1; then
        err "AudioShuttle not responding at $STATE_URL"
        err "Start with: cd ~/audioshuttle && docker compose up -d"
        exit 1
    fi
    ok "AudioShuttle server online"

    if ! command -v gpu-screen-recorder &> /dev/null; then
        err "gpu-screen-recorder not installed"
        err "Install with: sudo pacman -S gpu-screen-recorder"
        exit 1
    fi
    ok "gpu-screen-recorder available"

    if ! command -v ffmpeg &> /dev/null; then
        err "ffmpeg not installed"
        exit 1
    fi
    ok "ffmpeg available"
}

# === POSITION REAPER ===
setup_reaper() {
    log "Positioning Reaper on right half of $MONITOR..."

    # Find Reaper window
    local REAPER_WID
    REAPER_WID=$(DISPLAY=:0 wmctrl -lG 2>/dev/null | grep -i "REAPER" | awk '{print $1}' | head -1)

    if [ -z "$REAPER_WID" ]; then
        warn "Reaper window not found — make sure it's open on $MONITOR"
        return
    fi

    # Move Reaper to right 55% of the monitor (1920..3840, full height)
    # gpu-screen-recorder captures the full monitor, so we want both windows visible
    DISPLAY=:0 wmctrl -i -r "$REAPER_WID" -e 0,1728,0,2112,2160 2>/dev/null || true
    ok "Reaper repositioned to right side"
}

# === LAUNCH WEB UI ===
launch_webui() {
    log "Launching AudioShuttle web UI on left side..."

    # Kill any existing demo chromium
    pkill -f "chromium.*audioshuttle_demo" 2>/dev/null || true
    rm -rf /tmp/chromium_demo_profile 2>/dev/null || true
    sleep 1

    # Launch chromium sized to left 45% of the monitor
    # Left side: 0..1728, full height
    DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 chromium \
        --class=audioshuttle_demo \
        --user-data-dir=/tmp/chromium_demo_profile \
        --no-first-run \
        --disable-gpu \
        --window-position=0,0 \
        --window-size=1728,2160 \
        "http://localhost:8765" &

    CHROMIUM_PID=$!
    sleep 4
    ok "Web UI launched (PID $CHROMIUM_PID)"
}

# === GENERATE SUBTITLES ===
generate_subtitles() {
    log "Generating subtitle file..."

    cat > "$SUBTITLE_FILE" << 'SUBHEADER'
[Script Info]
Title: AudioShuttle Demo
ScriptType: v4.00+
PlayResX: 3840
PlayResY: 2160
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Inter,80,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,5,2,2,60,60,80,1
Style: Cmd,Inter,64,&H0000FFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,60,80,1
Style: Title,Inter Bold,100,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,6,2,8,60,60,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
SUBHEADER

    cat >> "$SUBTITLE_FILE" << 'EVENTS'
Dialogue: 0,0:00:00.00,0:00:03.50,Title,,0,0,0,,AudioShuttle
Dialogue: 0,0:00:00.50,0:00:03.50,Cmd,,0,0,0,,AI-powered DAW control with Gemma 4 E4B
Dialogue: 0,0:00:05.00,0:00:10.00,Default,,0,0,0,,"create a rock project at 120 bpm"
Dialogue: 0,0:00:05.50,0:00:10.00,Cmd,,0,0,0,,E4B generates: tracks, buses, MIDI, FX, routing
Dialogue: 0,0:00:40.00,0:00:43.00,Default,,0,0,0,,7 tracks, 9 markers, buses, MIDI — all from one sentence
Dialogue: 0,0:00:45.00,0:00:48.00,Default,,0,0,0,,play
Dialogue: 0,0:00:49.00,0:00:52.00,Default,,0,0,0,,increase the guitars bus by 3 dB
Dialogue: 0,0:00:53.00,0:00:56.00,Default,,0,0,0,,lower rhythm guitar 1 by 6 dB
Dialogue: 0,0:00:57.00,0:01:00.00,Default,,0,0,0,,mute the bass
Dialogue: 0,0:01:01.00,0:01:04.00,Default,,0,0,0,,rename track 5 to Synth Pad
Dialogue: 0,0:01:06.00,0:01:10.00,Default,,0,0,0,,wipe this and create a metal project at 180 bpm
Dialogue: 0,0:01:06.50,0:01:10.00,Cmd,,0,0,0,,Full wipe + new genre with doubled instruments
Dialogue: 0,0:01:35.00,0:01:38.00,Default,,0,0,0,,solo the drums
Dialogue: 0,0:01:39.00,0:01:42.00,Default,,0,0,0,,unmute the bass
Dialogue: 0,0:01:43.00,0:01:46.00,Default,,0,0,0,,add a marker called Bridge
Dialogue: 0,0:01:47.00,0:01:50.00,Default,,0,0,0,,set tempo to 160
Dialogue: 0,0:01:51.00,0:01:55.00,Default,,0,0,0,,what tracks do I have
Dialogue: 0,0:01:51.50,0:01:55.00,Cmd,,0,0,0,,E4B reads back the full track list
Dialogue: 0,0:01:57.00,0:02:00.00,Default,,0,0,0,,stop
Dialogue: 0,0:02:05.00,0:02:20.00,Title,,0,0,0,,Built with Gemma 4 E4B
Dialogue: 0,0:02:06.00,0:02:20.00,Cmd,,0,0,0,,Running locally on AMD ROCm • Open source • Fully offline
EVENTS

    ok "Subtitles written to $SUBTITLE_FILE"
}

# === RECORD SCREEN ===
start_recording() {
    log "Starting gpu-screen-recorder on $MONITOR..."
    log "  Output: $VIDEO_FILE"

    rm -f "$VIDEO_FILE"

    gpu-screen-recorder \
        -w "$MONITOR" \
        -f $FPS \
        -k h264 \
        -q high \
        -o "$VIDEO_FILE" \
        > "$LOG_FILE" 2>&1 &

    GSR_PID=$!
    sleep 2

    if kill -0 $GSR_PID 2>/dev/null; then
        ok "Recording started (PID $GSR_PID)"
    else
        err "gpu-screen-recorder failed. Check $LOG_FILE"
        cat "$LOG_FILE"
        exit 1
    fi
}

stop_recording() {
    log "Stopping recording..."
    if [ -n "$GSR_PID" ] && kill -0 $GSR_PID 2>/dev/null; then
        kill -INT $GSR_PID 2>/dev/null || true
        wait $GSR_PID 2>/dev/null || true
    fi
    sleep 1
    ok "Recording saved to $VIDEO_FILE"
    ls -lh "$VIDEO_FILE" 2>/dev/null
}

# === COMMAND SEQUENCE ===
run_commands() {
    local t=0
    log "=== Starting command sequence ==="
    echo ""

    # SECTION 1: Create rock project (t=0..45)
    log "SECTION 1: Create rock project [t=${t}s]"
    send_cmd "create a rock project at 120 bpm" \
        "Full arrangement: tracks, buses, MIDI, FX, routing" \
        42
    t=$((t + 44))
    sleep 2

    # SECTION 2: Mix adjustments (t=20..40)
    log "SECTION 2: Mix adjustments [t=${t}s]"

    send_cmd "play" \
        "Start playback" 3
    t=$((t + 4))

    send_cmd "increase the guitars bus by 3 dB" \
        "Bus volume" 3
    t=$((t + 4))

    send_cmd "lower rhythm guitar 1 by 6 dB" \
        "Specific doubled-instrument variant" 3
    t=$((t + 4))

    send_cmd "mute the bass" \
        "Mute track" 3
    t=$((t + 4))

    send_cmd "rename track 5 to Synth Pad" \
        "Rename track" 3
    t=$((t + 4))

    # SECTION 3: Wipe and recreate (t=41..85)
    log "SECTION 3: Wipe + metal project [t=${t}s]"

    send_cmd "wipe this and create a metal project at 180 bpm" \
        "Full wipe + new genre with doubled instruments" \
        42
    t=$((t + 44))
    sleep 2

    # SECTION 4: More commands (t=58..80)
    log "SECTION 4: Advanced commands [t=${t}s]"

    send_cmd "solo the drums" \
        "Solo" 3
    t=$((t + 4))

    send_cmd "unmute the bass" \
        "Unmute" 3
    t=$((t + 4))

    send_cmd "add a marker called Bridge" \
        "Named marker" 3
    t=$((t + 4))

    send_cmd "set tempo to 160" \
        "Tempo change" 3
    t=$((t + 4))

    send_cmd "what tracks do I have" \
        "Discovery: state readback" 5
    t=$((t + 6))

    # SECTION 5: Wrap up (t=80..85)
    log "SECTION 5: Wrap up [t=${t}s]"

    send_cmd "stop" \
        "Stop playback" 3
    t=$((t + 3))

    log "=== Command sequence complete (${t}s elapsed) ==="
}

# === ADD SUBTITLES + COMPRESS ===
add_subtitles() {
    log "Burning in subtitles and compressing..."

    ffmpeg -y \
        -i "$VIDEO_FILE" \
        -vf "ass=$SUBTITLE_FILE" \
        -c:v libx264 \
        -preset medium \
        -crf 20 \
        -pix_fmt yuv420p \
        -movflags +faststart \
        "$FINAL_FILE" \
        2>> "$LOG_FILE"

    ok "Final video: $FINAL_FILE"
    ls -lh "$FINAL_FILE"
}

# === CLEANUP ===
cleanup() {
    log "Cleaning up..."

    if [ -n "${GSR_PID:-}" ] && kill -0 $GSR_PID 2>/dev/null; then
        stop_recording
    fi

    pkill -f "chromium.*audioshuttle_demo" 2>/dev/null || true
    rm -rf /tmp/chromium_demo_profile 2>/dev/null || true

    log "Done!"
}
trap cleanup EXIT

# === MAIN ===
main() {
    echo ""
    echo "============================================"
    echo "  AudioShuttle Demo Video Recorder"
    echo "  Monitor: $MONITOR (3840x2160)"
    echo "============================================"
    echo ""

    check_prereqs
    generate_subtitles

    if $DRY_RUN; then
        log "DRY RUN — printing commands without executing"
        echo ""
        run_commands
        exit 0
    fi

    if $CMDS_ONLY; then
        log "COMMANDS ONLY — running commands without recording"
        echo ""
        run_commands
        exit 0
    fi

    # Set up layout: Reaper right, web UI left
    setup_reaper
    launch_webui
    sleep 2

    log "Starting in 3 seconds... Press Ctrl+C to cancel"
    sleep 3

    start_recording
    sleep 3  # Capture initial state

    run_commands

    # Hold final state for 8 seconds (end card time)
    log "Holding final state for 8 seconds..."
    sleep 8

    stop_recording
    add_subtitles

    echo ""
    ok "Demo video complete!"
    echo ""
    echo "  Raw recording:   $VIDEO_FILE"
    echo "  Final (subtitled): $FINAL_FILE"
    echo ""
    log "Preview: mpv $FINAL_FILE"
}

main "$@"
