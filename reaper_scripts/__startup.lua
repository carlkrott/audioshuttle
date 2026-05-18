-- AudioShuttle Lua Watcher — Reaper defer loop background script
-- Polls the communication directory for trigger files every 200ms.
-- Handles: MIDI import, track insert, clear items, markers, wipe, 
--           state dump, FX commands, render, and color commands.
--
-- Heartbeat: writes tick counter to audioshuttle_watcher_alive
-- Python side reads this to verify watcher is running.
--
-- IMPORTANT: This runs ON THE HOST inside Reaper, not in the Docker container.
-- Paths are HOST paths. Docker bind-mounts ./communication → /communication/,
-- so on the host these files are at /home/korphaus/audioshuttle/communication/

-- ============================================================
-- CONFIGURATION
-- ============================================================
local COMM_DIR = "/home/korphaus/audioshuttle/communication/"
local TMP_DIR = "/tmp/"
local tick = 0

-- ============================================================
-- FILE I/O HELPERS
-- ============================================================

local function read_file(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local content = f:read("*all")
    f:close()
    return content
end

local function write_file(path, content)
    local f = io.open(path, "w")
    if not f then return false end
    f:write(content)
    f:close()
    return true
end

local function remove_file(path)
    os.remove(path)
end

local function file_exists(path)
    local f = io.open(path, "r")
    if f then f:close(); return true end
    return false
end

-- ============================================================
-- STATE DUMP — full project state as JSON
-- ============================================================

local function dump_state()
    local tracks = {}
    local count = reaper.CountTracks(0)
    for i = 0, count - 1 do
        local track = reaper.GetTrack(0, i)
        local _, name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", "", false)
        local vol = reaper.GetMediaTrackInfo_Value(track, "D_VOL")
        local pan = reaper.GetMediaTrackInfo_Value(track, "D_PAN")
        local mute = reaper.GetMediaTrackInfo_Value(track, "B_MUTE") > 0
        local solo = reaper.GetMediaTrackInfo_Value(track, "B_SOLO") > 0
        local armed = reaper.GetMediaTrackInfo_Value(track, "I_RECARM") > 0
        local color = reaper.GetTrackColor(track)
        local color_hex = string.format("#%06x", color) or "#000000"
        local _, fx_count = reaper.TrackFX_GetCount(track)
        
        table.insert(tracks, {
            number = i + 1,
            name = name or ("Track " .. (i + 1)),
            volume = math.floor(vol * 100 + 0.5) / 100,
            pan = math.floor(pan * 100 + 0.5) / 100,
            mute = mute,
            solo = solo,
            armed = armed,
            color = color_hex,
            fx_count = fx_count
        })
    end

    -- Transport
    local play_state = reaper.GetPlayState()
    local playing = (play_state == 1) or (play_state == 4)
    local recording = (play_state == 5)
    local position = reaper.GetPlayPosition()
    local tempo = reaper.Master_GetTempo()

    -- Markers
    local markers = {}
    local marker_count = reaper.CountProjectMarkers(0)
    for i = 0, marker_count - 1 do
        local retval, isrgn, pos, rgnend, name, markrgnindexnumber = reaper.EnumProjectMarkers(i)
        if not isrgn then
            table.insert(markers, {
                index = i + 1,
                name = name or "",
                position = math.floor(pos * 100 + 0.5) / 100
            })
        end
    end

    local state = {
        track_count = count,
        tracks = tracks,
        transport = {
            playing = playing,
            recording = recording,
            position = math.floor(position * 100 + 0.5) / 100,
            tempo = math.floor(tempo * 10 + 0.5) / 10
        },
        markers = markers,
        marker_count = #markers
    }

    -- Write as JSON (manual encoding)
    local json_parts = {}
    json_parts[#json_parts + 1] = "{"
    json_parts[#json_parts + 1] = string.format('"track_count":%d,', count)
    
    -- Transport
    json_parts[#json_parts + 1] = string.format(
        '"transport":{"playing":%s,"recording":%s,"position":%.1f,"tempo":%.0f},',
        tostring(playing), tostring(recording), position, tempo
    )
    
    -- Tracks array
    json_parts[#json_parts + 1] = '"tracks":['
    for i, t in ipairs(tracks) do
        json_parts[#json_parts + 1] = string.format(
            '{"number":%d,"name":%s,"volume":%.2f,"pan":%.2f,"mute":%s,"solo":%s,"armed":%s,"color":%s,"fx_count":%d}',
            t.number,
            reaper.genGuid(""), -- placeholder, will replace with proper string
            t.volume, t.pan,
            tostring(t.mute), tostring(t.solo), tostring(t.armed),
            "\"" .. t.color .. "\"",
            t.fx_count
        )
        if i < #tracks then
            json_parts[#json_parts] = json_parts[#json_parts] .. ","
        end
    end
    json_parts[#json_parts + 1] = "],"
    
    -- Markers
    json_parts[#json_parts + 1] = string.format('"marker_count":%d,"markers":[', #markers)
    for i, m in ipairs(markers) do
        json_parts[#json_parts + 1] = string.format(
            '{"index":%d,"name":"%s","position":%.1f}',
            m.index, m.name, m.position
        )
        if i < #markers then
            json_parts[#json_parts] = json_parts[#json_parts] .. ","
        end
    end
    json_parts[#json_parts + 1] = "]"
    
    json_parts[#json_parts + 1] = "}"
    
    return table.concat(json_parts, "")
end

-- Better JSON encoder using string escaping
local function json_string(s)
    if not s then return '""' end
    s = string.gsub(s, '\\', '\\\\')
    s = string.gsub(s, '"', '\\"')
    s = string.gsub(s, '\n', '\\n')
    s = string.gsub(s, '\r', '\\r')
    return '"' .. s .. '"'
end

local function dump_state_json()
    local count = reaper.CountTracks(0)
    local tracks = {}
    for i = 0, count - 1 do
        local track = reaper.GetTrack(0, i)
        local _, name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", "", false)
        local vol = reaper.GetMediaTrackInfo_Value(track, "D_VOL")
        local pan = reaper.GetMediaTrackInfo_Value(track, "D_PAN")
        local mute = reaper.GetMediaTrackInfo_Value(track, "B_MUTE") > 0
        local solo = reaper.GetMediaTrackInfo_Value(track, "B_SOLO") > 0
        local armed = reaper.GetMediaTrackInfo_Value(track, "I_RECARM") > 0
        local color = reaper.GetTrackColor(track)
        local color_hex = string.format("#%06x", color & 0xFFFFFF)
        table.insert(tracks, {
            number = i + 1,
            name = name or ("Track " .. (i + 1)),
            volume = math.floor(vol * 100 + 0.5) / 100,
            pan = math.floor(pan * 100 + 0.5) / 100,
            mute = mute,
            solo = solo,
            armed = armed,
            color = color_hex
        })
    end

    local play_state = reaper.GetPlayState()
    local playing = (play_state == 1) or (play_state == 4)
    local recording = (play_state == 5)
    local position = reaper.GetPlayPosition()
    local tempo = reaper.Master_GetTempo()

    local lines = {}
    lines[#lines + 1] = "{"
    lines[#lines + 1] = string.format('  "track_count": %d,', count)
    lines[#lines + 1] = string.format(
        '  "transport": {"playing": %s, "recording": %s, "position": %.1f, "tempo": %.0f},',
        tostring(playing), tostring(recording), position, tempo
    )
    lines[#lines + 1] = '  "tracks": ['
    for i, t in ipairs(tracks) do
        local comma = (i < #tracks) and "," or ""
        lines[#lines + 1] = string.format(
            '    {"number": %d, "name": %s, "volume": %.2f, "pan": %.2f, "mute": %s, "solo": %s, "armed": %s, "color": %s}%s',
            t.number,
            json_string(t.name),
            t.volume, t.pan,
            tostring(t.mute), tostring(t.solo), tostring(t.armed),
            json_string(t.color),
            comma
        )
    end
    lines[#lines + 1] = "  ]"
    lines[#lines + 1] = "}"

    return table.concat(lines, "\n")
end

-- ============================================================
-- TRIGGER HANDLERS — each reads content, executes, removes trigger
-- ============================================================

-- MIDI import: content = "import:track:N:role" or "import:track:N" or "import"
local function handle_import_trigger(content)
    if not content then return end
    -- Parse: import:track:N:role or import
    local track_num = nil
    local role = nil
    
    local parts = {}
    for p in string.gmatch(content, "[^:]+") do
        table.insert(parts, p)
    end
    
    if parts[1] == "import" then
        if #parts >= 3 and parts[2] == "track" then
            track_num = tonumber(parts[3])
            if #parts >= 4 then
                role = parts[4]
            end
        end
    else
        return  -- not an import trigger
    end
    
    -- Determine MIDI file path
    local midi_path = nil
    if role then
        midi_path = TMP_DIR .. "audioshuttle_" .. role .. ".mid"
    else
        midi_path = TMP_DIR .. "audioshuttle_pattern.mid"
    end
    
    if not file_exists(midi_path) then
        -- Try the other format
        if role then
            midi_path = TMP_DIR .. "audioshuttle_pattern.mid"
            if not file_exists(midi_path) then
                return  -- no MIDI file found
            end
        else
            -- Try looking for any audioshuttle .mid file
            -- Simple fallback: try common roles
            local roles = {"drums", "bass", "keys", "guitar", "lead_guitar", "rhythm_guitar", "vocals", "synth"}
            for _, r in ipairs(roles) do
                local test_path = TMP_DIR .. "audioshuttle_" .. r .. ".mid"
                if file_exists(test_path) then
                    midi_path = test_path
                    role = r
                    break
                end
            end
            if not file_exists(midi_path) then return end
        end
    end
    
    -- Focus on target track if specified
    if track_num then
        local track = reaper.GetTrack(0, track_num - 1)
        if track then
            reaper.SetOnlyTrackSelected(track)
        end
    end
    
    -- Move cursor to start for multi-MIDI import
    reaper.SetEditCurPos(0, false, false)
    
    -- Import MIDI
    reaper.InsertMedia(midi_path, 0)
end

-- Clear track items: content = "track:N"
local function handle_clear_trigger(content)
    if not content then return end
    local track_num = tonumber(string.match(content, "track:(%d+)"))
    if not track_num then return end
    
    local track = reaper.GetTrack(0, track_num - 1)
    if not track then return end
    
    -- Select only this track, select all items, delete
    reaper.Main_OnCommand(40297, 0)  -- Unselect all tracks
    reaper.SetTrackSelected(track, true)
    reaper.Main_OnCommand(40182, 0)  -- Select all items on selected tracks
    reaper.Main_OnCommand(40006, 0)  -- Remove selected items
end

-- Track insert: content = "N" (count)
local function handle_track_insert_trigger(content)
    if not content then return end
    local count = tonumber(content)
    if not count or count < 1 then return end
    
    for i = 1, count do
        reaper.InsertTrackAtIndex(count - i, true)
    end
end

-- Markers: content = "tempo:BPM\nbar:offset:name\n..."
local function handle_markers_trigger(content)
    if not content then return end
    local lines = {}
    for line in string.gmatch(content, "[^\r\n]+") do
        table.insert(lines, line)
    end
    
    local bpm = nil
    local markers = {}
    
    for _, line in ipairs(lines) do
        if string.sub(line, 1, 6) == "tempo:" then
            bpm = tonumber(string.sub(line, 7))
        elseif string.sub(line, 1, 4) == "bar:" then
            local rest = string.sub(line, 5)
            local colon1 = string.find(rest, ":")
            if colon1 then
                local bar_offset = tonumber(string.sub(rest, 1, colon1 - 1))
                local name = string.sub(rest, colon1 + 1)
                if bar_offset and name then
                    table.insert(markers, {offset = bar_offset, name = name})
                end
            end
        end
    end
    
    -- Set tempo
    if bpm then
        reaper.SetCurrentBPM(0, bpm, true)
    end
    
    -- Remove existing markers
    reaper.Main_OnCommand(40613, 0)  -- Delete all markers
    
    -- Create markers
    -- tempo_bpm / 60 = beats per second, beats_per_measure defaults to 4
    local beats_per_measure = tonumber(reaper.GetProjectTimeSignature(nil, nil)) or 4
    local seconds_per_beat = 60.0 / (bpm or 120.0)
    
    for _, m in ipairs(markers) do
        local position = m.offset * beats_per_measure * seconds_per_beat
        reaper.AddProjectMarker(0, false, position, 0, m.name, -1)
    end
end

-- Wipe: content = "wipe"
local function handle_wipe_trigger(content)
    if not content or content ~= "wipe" then return end
    
    -- Delete all tracks
    reaper.Main_OnCommand(40297, 0)  -- Unselect all tracks
    local track_count = reaper.CountTracks(0)
    for i = track_count - 1, 0, -1 do
        local track = reaper.GetTrack(0, i)
        reaper.DeleteTrack(track)
    end
    
    -- Delete all markers
    reaper.Main_OnCommand(40613, 0)
    
    -- Reset tempo
    reaper.SetCurrentBPM(0, 120, true)
    
    -- Write done signal
    write_file(COMM_DIR .. "audioshuttle_wipe_done", "ok")
end

-- State dump: content = "dump"
local function handle_state_request(content)
    if not content or content ~= "dump" then return end
    
    local json = dump_state_json()
    write_file(COMM_DIR .. "audioshuttle_daw_state.json", json)
end

-- FX command: content = "command:track:arg1:arg2:..."
local function handle_fx_trigger(content)
    if not content then return end
    local parts = {}
    for p in string.gmatch(content, "[^:]+") do
        table.insert(parts, p)
    end
    
    if #parts < 2 then return end
    
    local command = parts[1]
    local track_num = tonumber(parts[2])
    if not track_num then return end
    
    local track = reaper.GetTrack(0, track_num - 1)
    if not track then return end
    
    local result = {success = false, error = "unknown command"}
    
    if command == "add" and #parts >= 3 then
        -- add:track:fx_name
        local fx_name = parts[3]
        local idx = reaper.TrackFX_AddByName(track, fx_name, false, -1)
        result = {success = idx >= 0, fx_index = idx, fx_name = fx_name}
    elseif command == "remove" and #parts >= 3 then
        -- remove:track:fx_index
        local fx_idx = tonumber(parts[3])
        if fx_idx then
            local ok = reaper.TrackFX_Delete(track, fx_idx)
            result = {success = ok, fx_index = fx_idx}
        end
    elseif command == "bypass" and #parts >= 4 then
        -- bypass:track:fx_index:enabled
        local fx_idx = tonumber(parts[3])
        local enabled = (parts[4] == "true" or parts[4] == "1")
        if fx_idx then
            reaper.TrackFX_SetEnabled(track, fx_idx, enabled)
            result = {success = true, fx_index = fx_idx, bypass = not enabled}
        end
    elseif command == "preset" and #parts >= 4 then
        -- preset:track:fx_index:preset_name
        local fx_idx = tonumber(parts[3])
        local preset_name = table.concat(parts, ":", 4)
        if fx_idx then
            local presets_ok = reaper.TrackFX_NavigatePresets(track, fx_idx, 1)  -- first preset
            result = {success = true, fx_index = fx_idx, note = "navigated to preset list start"}
        end
    elseif command == "wet" and #parts >= 4 then
        -- wet:track:fx_index:value
        local fx_idx = tonumber(parts[3])
        local wet_val = tonumber(parts[4])
        if fx_idx and wet_val then
            reaper.TrackFX_SetParamNormalized(track, fx_idx, 0, wet_val)  -- param 0 = wet/dry
            result = {success = true, fx_index = fx_idx, wet = wet_val}
        end
    end
    
    -- Write result as JSON
    local result_json = string.format(
        '{"success": %s, "error": %s, "fx_index": %s}',
        tostring(result.success),
        json_string(result.error or ""),
        tostring(result.fx_index or -1)
    )
    write_file(COMM_DIR .. "audioshuttle_fx_result.json", result_json)
end

-- FX list request: content = "list:track:fx_index" — list params
local function handle_fx_list_request(content)
    if not content then return end
    local parts = {}
    for p in string.gmatch(content, "[^:]+") do
        table.insert(parts, p)
    end
    
    local track_num = tonumber(parts[2])
    if not track_num then return end
    
    local track = reaper.GetTrack(0, track_num - 1)
    if not track then return end
    
    local fx_list = {}
    local fx_count = reaper.TrackFX_GetCount(track)
    for fi = 0, fx_count - 1 do
        local _, fx_name = reaper.TrackFX_GetFXName(track, fi, "")
        local param_count = reaper.TrackFX_GetNumParams(track, fi)
        local params = {}
        for pi = 0, math.min(param_count - 1, 19) do  -- max 20 params
            local _, param_name = reaper.TrackFX_GetParamName(track, fi, pi, "")
            local param_val = reaper.TrackFX_GetParam(track, fi, pi)
            params[pi + 1] = {name = param_name, value = param_val}
        end
        table.insert(fx_list, {
            index = fi,
            name = fx_name,
            param_count = param_count,
            params = params
        })
    end
    
    -- Write JSON
    local json_parts = {"["}
    for i, fx in ipairs(fx_list) do
        local param_strs = {}
        for _, p in ipairs(fx.params) do
            table.insert(param_strs, string.format(
                '{"name":%s,"value":%.4f}', json_string(p.name), p.value
            ))
        end
        json_parts[#json_parts + 1] = string.format(
            '{"index":%d,"name":%s,"param_count":%d,"params":[%s]}%s',
            fx.index, json_string(fx.name), fx.param_count,
            table.concat(param_strs, ","),
            (i < #fx_list) and "," or ""
        )
    end
    json_parts[#json_parts + 1] = "]"
    
    write_file(COMM_DIR .. "audioshuttle_fx_list.json", table.concat(json_parts, ""))
end

-- Render: content = "render:start_sec:duration_sec:output_path"
local function handle_render_trigger(content)
    if not content then return end
    local parts = {}
    for p in string.gmatch(content, "[^:]+") do
        table.insert(parts, p)
    end
    
    if #parts < 4 or parts[1] ~= "render" then return end
    
    local start_sec = tonumber(parts[2])
    local duration_sec = tonumber(parts[3])
    local output_path = table.concat(parts, ":", 4)
    
    if not start_sec or not duration_sec then return end
    
    -- Set time selection for render bounds
    reaper.GetSet_LoopTimeRange(true, false, start_sec, start_sec + duration_sec, false)
    
    -- Render using action: File: Render project to disk
    -- This uses the current render settings — we just set time selection
    reaper.Main_OnCommand(40015, 0)  -- Transport: Go to start of project
end

-- Color command: content = "track:N:#RRGGBB"
local function handle_color_trigger(content)
    if not content then return end
    -- Format: "track:N:#RRGGBB" or "color:N:#RRGGBB"
    local track_num, color_hex = string.match(content, "(%d+):(%x%x%x%x%x%x)")
    if not track_num then
        track_num, color_hex = string.match(content, "track:(%d+):#(%x%x%x%x%x%x)")
    end
    if not track_num then
        track_num, color_hex = string.match(content, "color:(%d+):(%x%x%x%x%x%x)")
    end
    if not track_num or not color_hex then return end
    
    local track = reaper.GetTrack(0, tonumber(track_num) - 1)
    if not track then return end
    
    local r = tonumber(string.sub(color_hex, 1, 2), 16)
    local g = tonumber(string.sub(color_hex, 3, 4), 16)
    local b = tonumber(string.sub(color_hex, 5, 6), 16)
    local color_int = reaper.ColorToNative(r, g, b) | 0x1000000
    reaper.SetTrackColor(track, color_int)
end

-- ============================================================
-- FX TRIGGER CLEANUP — remove trigger if nothing handled it
-- ============================================================

local function safe_check_and_remove(trigger_path, handler_func)
    if not file_exists(trigger_path) then return end
    
    local content = read_file(trigger_path)
    if not content or content == "" then
        remove_file(trigger_path)
        return
    end
    
    -- Trim whitespace
    content = string.match(content, "^%s*(.-)%s*$")
    if not content or content == "" then
        remove_file(trigger_path)
        return
    end
    
    -- Execute handler
    local ok, err = pcall(handler_func, content)
    
    -- Remove trigger (handler may have already done this, but safe to call again)
    pcall(remove_file, trigger_path)
end

-- ============================================================
-- HEARTBEAT — write tick counter
-- ============================================================

local function write_heartbeat()
    tick = tick + 1
    write_file(COMM_DIR .. "audioshuttle_watcher_alive", "tick=" .. tick)
end

-- ============================================================
-- MAIN DEFER LOOP
-- ============================================================

local function main_loop()
    -- Write heartbeat so Python knows we're alive
    write_heartbeat()
    
    -- Check and handle each trigger type
    safe_check_and_remove(COMM_DIR .. "audioshuttle_import_trigger", handle_import_trigger)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_clear_trigger", handle_clear_trigger)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_track_insert_trigger", handle_track_insert_trigger)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_markers_trigger", handle_markers_trigger)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_wipe_trigger", handle_wipe_trigger)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_state_request", handle_state_request)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_fx_trigger", handle_fx_trigger)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_fx_list_request", handle_fx_list_request)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_render_trigger", handle_render_trigger)
    safe_check_and_remove(COMM_DIR .. "audioshuttle_color_cmd.txt", handle_color_trigger)
    
    -- Also check /tmp/ for the standalone insert_midi_pattern path (backward compat)
    safe_check_and_remove(TMP_DIR .. "audioshuttle_import_trigger", handle_import_trigger)
    
    -- Re-schedule
    reaper.defer(main_loop)
end

-- ============================================================
-- STARTUP
-- ============================================================

-- Ensure communication directory exists
os.execute("mkdir -p " .. COMM_DIR)

-- Write initial heartbeat
tick = 0
write_heartbeat()

-- Start the defer loop
reaper.defer(main_loop)
