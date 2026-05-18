#!/bin/bash
# AudioShuttle Demo Video Recorder
# ================================
# Records a ~2 minute demo of the full AudioShuttle pipeline:
# voice/text commands → E4B translation → Reaper DAW control
#
# Prerequisites:
#   - Reaper running with a project open
#   - AudioShuttle container running (docker compose up)
#   - This script runs as korphaus on the host (needs XWayland access)
#
# Usage:
#   bash scripts/demo_video.sh          # Record with automated commands
#   bash scripts/demo_video.sh --dry-run # Print commands without recording

set -euo pipefail

# === CONFIG ===
CAPTURE_X=0
CAPTURE_Y=0
CAPTURE_W=3072
CAPTURE_H=1728
FPS=30
OUTPUT_DIR="/tmp/audioshuttle_demo"
VIDEO_FILE="$OUTPUT_DIR/audioshuttle_demo.mp4"
FINAL_FILE="$OUTPUT_DIR/audioshuttle_demo_final.mp4"
REPLAY_URL="http://localhost:8765/replay"
STATE_URL="http://localhost:8765/state"
DISPLAY=${DISPLAY:-:0}
SUBTITLE_FILE="$OUTPUT_DIR/subs.ass"
LOG_FILE="$OUTPUT_DIR/recording.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Timing between commands (seconds)
CMD_DELAY=3
SECTION_DELAY=5

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

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
        echo "  curl \"$REPLAY_URL?cmd=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$cmd'))")\""
    else
        curl -s "$REPLAY_URL?cmd=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$cmd'))")" > /dev/null 2>&1
    fi
    
    sleep "$delay"
}

# Check prerequisites
log "Checking prerequisites..."

if ! curl -s "$STATE_URL" > /dev/null 2>&1; then
    err "AudioShuttle not responding at $STATE_URL"
    err "Start with: docker compose up -d"
    exit 1
fi
ok "AudioShuttle server online"

if ! command -v ffmpeg &> /dev/null; then
    err "ffmpeg not installed"
    exit 1
fi
ok "ffmpeg available"

# Check Reaper window
if ! DISPLAY=$DISPLAY wmctrl -lG 2>/dev/null | grep -q "REAPER"; then
    warn "Reaper window not detected — make sure it's open"
fi

# === GENERATE SUBTITLES ===
generate_subtitles() {
    log "Generating subtitle file..."
    
    # ASS format subtitles with styling
    cat > "$SUBTITLE_FILE" << 'SUBHEADER'
[Script Info]
Title: AudioShuttle Demo
ScriptType: v4.00+
PlayResX: 3072
PlayResY: 1728
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,30,30,60,1
Style: Cmd,Arial,60,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,30,30,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
SUBHEADER

    # Subtitle events — timed to match the command sequence
    cat >> "$SUBTITLE_FILE" << 'EVENTS'
Dialogue: 0,0:00:00.00,0:00:04.00,Default,,0,0,0,,AudioShuttle — AI-powered DAW control
Dialogue: 0,0:00:01.00,0:00:04.00,Cmd,,0,0,0,,Speak naturally. E4B translates. Reaper executes.
Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,"Create a rock project at 120 BPM"
Dialogue: 0,0:00:05.00,0:00:08.00,Cmd,,0,0,0,,E4B generates full arrangement: tracks, buses, MIDI, FX
Dialogue: 0,0:00:18.00,0:00:21.00,Default,,0,0,0,,"Play"
Dialogue: 0,0:00:22.00,0:00:25.00,Default,,0,0,0,,"Increase the guitars bus by 3 dB"
Dialogue: 0,0:00:26.00,0:00:29.00,Default,,0,0,0,,"Lower rhythm guitar 1 by 6 dB"
Dialogue: 0,0:00:30.00,0:00:33.00,Default,,0,0,0,,"Mute the bass"
Dialogue: 0,0:00:34.00,0:00:37.00,Default,,0,0,0,,"Rename track 5 to Synth Pad"
Dialogue: 0,0:00:39.00,0:00:42.00,Default,,0,0,0,,"Wipe this, let's start a new metal track at 180 BPM"
Dialogue: 0,0:00:39.00,0:00:42.00,Cmd,,0,0,0,,E4B wipes project + creates new genre with doubled instruments
Dialogue: 0,0:00:55.00,0:00:58.00,Default,,0,0,0,,"Solo the drums"
Dialogue: 0,0:00:59.00,0:01:02.00,Default,,0,0,0,,"Unmute the bass"
Dialogue: 0,0:01:03.00,0:01:06.00,Default,,0,0,0,,"Add a marker called Bridge"
Dialogue: 0,0:01:08.00,0:01:11.00,Default,,0,0,0,,"Set tempo to 160"
Dialogue: 0,0:01:13.00,0:01:16.00,Default,,0,0,0,,"What tracks do I have?"
Dialogue: 0,0:01:13.00,0:01:16.00,Cmd,,0,0,0,,E4B reads back the full track list
Dialogue: 0,0:01:20.00,0:01:23.00,Default,,0,0,0,,"Stop"
Dialogue: 0,0:01:25.00,0:01:35.00,Default,,0,0,0,,Built with Gemma 4 E4B — running locally on AMD ROCm
Dialogue: 0,0:01:26.00,0:01:35.00,Cmd,,0,0,0,,Open source • Fully offline • Voice + text control
EVENTS

    ok "Subtitles written to $SUBTITLE_FILE"
}

# === LAUNCH CHROMIUM (X11 MODE) ===
launch_chromium() {
    log "Launching Chromium in X11 mode on left side of monitor..."
    
    # Kill any existing demo chromium
    pkill -f "chromium.*audioshuttle_demo" 2>/dev/null || true
    sleep 1
    
    # Launch chromium with X11 backend, sized to fill left half of U28D590
    # Left half: 0,0 to ~2510,1728
    DISPLAY=$DISPLAY chromium \
        --class=audioshuttle_demo \
        --user-data-dir=/tmp/chromium_demo_profile \
        --no-first-run \
        --disable-gpu \
        --start-maximized \
        --window-position=0,0 \
        --window-size=2500,1728 \
        "http://localhost:8765" &
    
    CHROMIUM_PID=$!
    sleep 3
    
    # Position chromium precisely with wmctrl
    DISPLAY=$DISPLAY wmctrl -r "audioshuttle_demo" -e 0,0,0,2500,1728 2>/dev/null || true
    # Or find by PID
    local WID=$(DISPLAY=$DISPLAY wmctrl -l | grep -i "audioshuttle\|localhost:8765" | awk '{print $1}' | head -1)
    if [ -n "$WID" ]; then
        DISPLAY=$DISPLAY wmctrl -i -r "$WID" -e 0,0,0,2500,1728 2>/dev/null || true
    fi
    
    ok "Chromium launched (PID $CHROMIUM_PID)"
}

# === RECORD SCREEN ===
start_recording() {
    log "Starting screen recording..."
    log "  Capture: ${CAPTURE_W}x${CAPTURE_H} at +${CAPTURE_X}+${CAPTURE_Y}"
    log "  Output:  $VIDEO_FILE"
    
    DISPLAY=$DISPLAY ffmpeg -y \
        -f x11grab \
        -video_size ${CAPTURE_W}x${CAPTURE_H} \
        -framerate $FPS \
        -i ${CAPTURE_X},${CAPTURE_Y} \
        -c:v libx264 \
        -preset fast \
        -crf 18 \
        -pix_fmt yuv420p \
        "$VIDEO_FILE" \
        > "$LOG_FILE" 2>&1 &
    
    FFMPEG_PID=$!
    sleep 2
    
    # Verify it's recording
    if kill -0 $FFMPEG_PID 2>/dev/null; then
        ok "Recording started (PID $FFMPEG_PID)"
    else
        err "ffmpeg failed to start. Check $LOG_FILE"
        cat "$LOG_FILE"
        exit 1
    fi
}

stop_recording() {
    log "Stopping recording..."
    kill -INT $FFMPEG_PID 2>/dev/null || true
    wait $FFMPEG_PID 2>/dev/null || true
    ok "Recording saved to $VIDEO_FILE"
}

# === COMMAND SEQUENCE ===
run_commands() {
    log "=== Starting command sequence ==="
    log "Total estimated time: ~90 seconds"
    echo ""
    
    # ---- SECTION 1: Project Creation (0:00 - 0:18) ----
    log "SECTION 1: Create rock project"
    send_cmd "create a rock project at 120 bpm" \
        "Create full rock arrangement: drums, bass, guitars, keys + bus routing" \
        15
    sleep 3
    
    # ---- SECTION 2: Mix Adjustments (0:18 - 0:38) ----
    log "SECTION 2: Mix adjustments"
    
    send_cmd "play" \
        "Start playback" \
        3
    
    send_cmd "increase the guitars bus by 3 dB" \
        "Adjust bus volume" \
        3
    
    send_cmd "lower rhythm guitar 1 by 6 dB" \
        "Adjust specific track with doubled instrument variant" \
        3
    
    send_cmd "mute the bass" \
        "Mute a track" \
        3
    
    send_cmd "rename track 5 to Synth Pad" \
        "Rename a track" \
        3
    
    # ---- SECTION 3: Wipe & New Genre (0:38 - 0:55) ----
    log "SECTION 3: Wipe and recreate"
    
    send_cmd "wipe this and create a metal project at 180 bpm" \
        "Full wipe + new genre with doubled instruments and bus routing" \
        15
    sleep 2
    
    # ---- SECTION 4: More Commands (0:55 - 1:20) ----
    log "SECTION 4: Advanced commands"
    
    send_cmd "solo the drums" \
        "Solo a track" \
        3
    
    send_cmd "unmute the bass" \
        "Unmute" \
        3
    
    send_cmd "add a marker called Bridge" \
        "Add named marker" \
        3
    
    send_cmd "set tempo to 160" \
        "Change tempo" \
        3
    
    send_cmd "what tracks do I have" \
        "Discovery: list all tracks with state" \
        5
    
    # ---- SECTION 5: Wrap up (1:20 - 1:30) ----
    log "SECTION 5: Wrap up"
    
    send_cmd "stop" \
        "Stop playback" \
        3
    
    log "=== Command sequence complete ==="
}

# === ADD SUBTITLES ===
add_subtitles() {
    log "Burning in subtitles..."
    
    ffmpeg -y \
        -i "$VIDEO_FILE" \
        -vf "ass=$SUBTITLE_FILE" \
        -c:v libx264 \
        -preset fast \
        -crf 18 \
        -pix_fmt yuv420p \
        "$FINAL_FILE" \
        2>> "$LOG_FILE"
    
    ok "Final video: $FINAL_FILE"
    ls -lh "$FINAL_FILE"
}

# === CLEANUP ===
cleanup() {
    log "Cleaning up..."
    
    # Stop recording if still running
    if [ -n "${FFMPEG_PID:-}" ] && kill -0 $FFMPEG_PID 2>/dev/null; then
        stop_recording
    fi
    
    # Kill demo chromium
    pkill -f "chromium.*audioshuttle_demo" 2>/dev/null || true
    rm -rf /tmp/chromium_demo_profile 2>/dev/null || true
    
    log "Done!"
}

trap cleanup EXIT

# === MAIN ===
main() {
    echo ""
    echo "========================================"
    echo "  AudioShuttle Demo Video Recorder"
    echo "========================================"
    echo ""
    
    generate_subtitles
    
    if $DRY_RUN; then
        log "DRY RUN — printing commands without executing"
        echo ""
        run_commands
        exit 0
    fi
    
    launch_chromium
    sleep 2
    
    log "Press Ctrl+C to stop recording at any time"
    log "Recording will auto-stop after the command sequence"
    echo ""
    sleep 2
    
    start_recording
    sleep 3  # Let the recording capture the initial state
    
    run_commands
    
    # Hold for 5 seconds to show final state
    sleep 5
    
    stop_recording
    add_subtitles
    
    echo ""
    ok "Demo video complete!"
    echo ""
    echo "  Raw recording:  $VIDEO_FILE"
    echo "  Final (subtitled): $FINAL_FILE"
    echo ""
    log "To preview: mpv $FINAL_FILE"
}

main "$@"
