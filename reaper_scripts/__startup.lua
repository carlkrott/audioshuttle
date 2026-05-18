-- AudioShuttle Watcher v5 — MIDI import + markers + colors
COMM_DIR = "/home/korphaus/audioshuttle/communication/"
TMP_DIR = "/tmp/"
tick = 0

function log(msg)
    local f = io.open("/tmp/watcher_debug.log", "a")
    if f then f:write(tostring(tick) .. ": " .. msg .. "\n"); f:close() end
end
function fexists(p) local f = io.open(p, "r"); if f then f:close(); return true end; return false end
function fread(p) local f = io.open(p, "r"); if not f then return nil end; local c = f:read("*all"); f:close(); return c end
function frm(p) os.remove(p) end
function fwrite(p, c) local f = io.open(p, "w"); if not f then return false end; f:write(c); f:close(); return true end

-- ============================================================
-- HANDLERS
-- ============================================================

function handle_state_request()
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
        local item_count = reaper.CountTrackMediaItems(track)
        table.insert(tracks, {
            number = i + 1, name = name or "",
            volume = math.floor(vol * 100 + 0.5) / 100,
            pan = math.floor(pan * 100 + 0.5) / 100,
            mute = mute, solo = solo, armed = armed,
            color = color_hex, items = item_count
        })
    end
    local ps = reaper.GetPlayState()
    local playing = (ps == 1) or (ps == 4)
    local recording = (ps == 5)
    local position = reaper.GetPlayPosition()
    local tempo = reaper.Master_GetTempo()
    local markers = {}
    local mc = reaper.CountProjectMarkers(0)
    for i = 0, mc - 1 do
        local _, isrgn, pos, _, name = reaper.EnumProjectMarkers(i)
        if not isrgn then markers[#markers+1] = {name = name or "", pos = math.floor(pos*10+0.5)/10} end
    end
    local L = {"{"}
    L[#L+1] = string.format('"track_count":%d,', count)
    L[#L+1] = string.format('"transport":{"playing":%s,"recording":%s,"position":%.1f,"tempo":%.0f},', tostring(playing), tostring(recording), position, tempo)
    L[#L+1] = string.format('"marker_count":%d,', #markers)
    L[#L+1] = '"tracks":['
    for i, t in ipairs(tracks) do
        local comma = (i < #tracks) and "," or ""
        L[#L+1] = string.format('{"number":%d,"name":"%s","volume":%.2f,"pan":%.2f,"mute":%s,"solo":%s,"armed":%s,"color":"%s","items":%d,"fx":%d}%s',
            t.number, t.name:gsub('"', '\\"'), t.volume, t.pan, tostring(t.mute), tostring(t.solo), tostring(t.armed), t.color, t.items, t.fx_count or 0, comma)
    end
    L[#L+1] = "]}"
    fwrite(COMM_DIR .. "audioshuttle_daw_state.json", table.concat(L, ""))
    log("STATE: " .. count .. " tracks, " .. #markers .. " markers")
end

function handle_wipe_trigger()
    -- Delete markers first (direct API, more reliable than Main_OnCommand)
    local mc = reaper.CountProjectMarkers(0)
    for i = mc - 1, 0, -1 do
        local _, isrgn = reaper.EnumProjectMarkers(i)
        reaper.DeleteProjectMarker(0, i, isrgn)
    end
    -- Delete tracks
    reaper.Main_OnCommand(40297, 0)
    local c = reaper.CountTracks(0)
    for i = c - 1, 0, -1 do reaper.DeleteTrack(reaper.GetTrack(0, i)) end
    reaper.SetCurrentBPM(0, 120, true)
    log("WIPE: done, " .. c .. " tracks, " .. mc .. " markers")
    fwrite(COMM_DIR .. "audioshuttle_wipe_done", "ok")
end

function handle_clear_trigger(content)
    local tn = tonumber(string.match(content, "track:(%d+)"))
    if not tn then return end
    local track = reaper.GetTrack(0, tn - 1)
    if not track then return end
    -- Clear by deleting items directly from the track object
    -- (avoids Main_OnCommand track selection bugs in Reaper 7.7)
    local item_count = reaper.CountTrackMediaItems(track)
    for i = item_count - 1, 0, -1 do
        reaper.DeleteTrackMediaItem(track, reaper.GetTrackMediaItem(track, i))
    end
    log("CLEAR track " .. tn .. " (" .. item_count .. " items)")
end

function handle_track_insert_trigger(content)
    local c = tonumber(content)
    if not c or c < 1 then return end
    log("INSERT " .. c .. " tracks")
    for i = 1, c do reaper.InsertTrackAtIndex(c - i, true) end
end

function handle_import_trigger(content)
    log("IMPORT: " .. content)
    local track_num, role = nil, nil
    for part in string.gmatch(content, "[^:]+") do
        if part ~= "import" and part ~= "track" then
            local n = tonumber(part)
            if n and not track_num then track_num = n
            elseif not role and not n then role = part end
        end
    end
    local midi_path = nil
    if role then
        midi_path = TMP_DIR .. "audioshuttle_" .. role .. ".mid"
        if not fexists(midi_path) then midi_path = TMP_DIR .. "audioshuttle_pattern.mid" end
    else
        local roles = {"drums","bass","keys","lead_guitar","rhythm_guitar","vocals","synth"}
        for _, r in ipairs(roles) do
            local p = TMP_DIR .. "audioshuttle_" .. r .. ".mid"
            if fexists(p) then midi_path = p; role = r; break end
        end
        if not midi_path then midi_path = TMP_DIR .. "audioshuttle_pattern.mid" end
    end
    if not fexists(midi_path) then log("IMPORT: no file " .. tostring(midi_path)); return end
    -- InsertMedia(mode=0) always puts items on track 1 regardless of selection.
    -- Strategy: insert on track 1, then move to target track.
    local t1 = reaper.GetTrack(0, 0)
    if not t1 then log("IMPORT: no track 1"); return end
    local before = reaper.CountTrackMediaItems(t1)
    reaper.SetEditCurPos(0, false, false)
    reaper.InsertMedia(midi_path, 0)
    local after = reaper.CountTrackMediaItems(t1)
    
    if after > before and track_num and track_num ~= 1 then
        local tgt = reaper.GetTrack(0, track_num - 1)
        if tgt then
            local item = reaper.GetTrackMediaItem(t1, after - 1)
            log("IMPORT DEBUG: t1_items=" .. reaper.CountTrackMediaItems(t1) .. " moving idx=" .. (after-1))
            if item then
                local move_ok, move_err = pcall(reaper.MoveMediaItemToTrack, item, tgt)
                log("IMPORT DEBUG: after move t1=" .. reaper.CountTrackMediaItems(t1) .. " t" .. track_num .. "=" .. reaper.CountTrackMediaItems(tgt))
                if move_ok then
                    log("IMPORT OK: " .. midi_path .. " moved to track " .. track_num)
                else
                    log("IMPORT: " .. midi_path .. " on track 1 (move failed)")
                end
            end
        end
    elseif after > before then
        log("IMPORT OK: " .. midi_path .. " on track 1")
    else
        log("IMPORT: " .. midi_path .. " no item created (before=" .. before .. " after=" .. after .. ")")
    end
end

function handle_markers_trigger(content)
    log("MARKERS raw: " .. content:gsub("\n","|"))
    local bpm_val, entries = nil, {}
    for part in string.gmatch(content, "[^\r\n]+") do
        local t, v = string.match(part, "^tempo:(.+)$")
        if t then bpm_val = tonumber(v) else
            local b, n = string.match(part, "^bar:(%d+):(.+)$")
            if b then entries[#entries+1] = {offset = tonumber(b), name = n} end
        end
    end
    log("MARKERS: bpm=" .. tostring(bpm_val) .. " count=" .. #entries)
    if bpm_val then reaper.SetCurrentBPM(0, bpm_val, true) end
    reaper.Main_OnCommand(40613, 0)
    local _, _, bpi = reaper.GetProjectTimeSignature(0)
    local bpb = bpi or 4
    local spb = 60.0 / (bpm_val or 120.0)
    for _, e in ipairs(entries) do
        local pos = e.offset * bpb * spb
        local ok, err = pcall(reaper.AddProjectMarker, 0, false, pos, 0, e.name, -1)
        if ok then log("MARKERS: +\"" .. e.name .. "\" at " .. string.format("%.1fs", pos))
        else log("MARKERS FAIL: " .. tostring(err)) end
    end
end

function handle_color_trigger(content)
    local tn, ch = string.match(content, "(%d+)[: ]#(%x%x%x%x%x%x)")
    if not tn then return end
    local track = reaper.GetTrack(0, tonumber(tn) - 1)
    if not track then return end
    local r = tonumber(string.sub(ch, 1, 2), 16)
    local g = tonumber(string.sub(ch, 3, 4), 16)
    local b = tonumber(string.sub(ch, 5, 6), 16)
    local ci = reaper.ColorToNative(r, g, b) | 0x1000000
    reaper.SetTrackColor(track, ci)
    log("COLOR track " .. tn .. " = #" .. ch)
end

function handle_fx_trigger(content)
    -- Format: command:track:arg1:arg2:...
    local parts = {}
    for p in string.gmatch(content, "[^:]+") do table.insert(parts, p) end
    if #parts < 2 then return end
    local cmd = parts[1]
    local tn = tonumber(parts[2])
    if not tn then return end
    local track = reaper.GetTrack(0, tn - 1)
    local result = {success = false, error = "unknown command: " .. cmd}
    
    if cmd == "add" and #parts >= 3 then
        local fx_name = parts[3]
        local idx = reaper.TrackFX_AddByName(track, fx_name, false, -1)
        result = {success = idx >= 0, fx_index = idx, fx_name = fx_name}
        log("FX add " .. fx_name .. " on t" .. tn .. " -> idx=" .. idx)
    elseif cmd == "remove" and #parts >= 3 then
        local fx_idx = tonumber(parts[3])
        if fx_idx then
            reaper.TrackFX_Delete(track, fx_idx)
            result = {success = true, fx_index = fx_idx}
        end
    elseif cmd == "wet" and #parts >= 4 then
        local fx_idx = tonumber(parts[3])
        local wet = tonumber(parts[4])
        if fx_idx and wet then
            reaper.TrackFX_SetParamNormalized(track, fx_idx, 0, wet)
            result = {success = true, wet = wet}
        end
    elseif cmd == "bypass" and #parts >= 4 then
        local fx_idx = tonumber(parts[3])
        local en = (parts[4] == "1" or parts[4] == "true")
        if fx_idx then
            reaper.TrackFX_SetEnabled(track, fx_idx, en)
            result = {success = true, bypass = en}
        end
    end
    -- Write result as JSON
    local rjson = string.format('{"success":%s,"error":"%s","fx_index":%d}',
        tostring(result.success), tostring(result.error or ""), result.fx_index or -1)
    fwrite(COMM_DIR .. "audioshuttle_fx_result.json", rjson)
end

function handle_fx_list_request(content)
    local parts = {}
    for p in string.gmatch(content, "[^:]+") do table.insert(parts, p) end
    local tn = parts[2] and tonumber(parts[2])
    if not tn then return end
    local track = reaper.GetTrack(0, tn - 1)
    if not track then return end
    local fxlist = {}
    local fc = reaper.TrackFX_GetCount(track)
    for fi = 0, fc - 1 do
        local _, fx_name = reaper.TrackFX_GetFXName(track, fi, "")
        table.insert(fxlist, {index = fi, name = fx_name or ""})
    end
    local json_parts = {"["}
    for i, fx in ipairs(fxlist) do
        json_parts[#json_parts+1] = string.format('{"index":%d,"name":"%s"}%s',
            fx.index, fx.name:gsub('"', '\\"'), (i < #fxlist) and "," or "")
    end
    json_parts[#json_parts+1] = "]"
    fwrite(COMM_DIR .. "audioshuttle_fx_list.json", table.concat(json_parts, ""))
    log("FX list t" .. tn .. ": " .. fc .. " plugins")
end

-- ============================================================
-- MAIN LOOP
-- ============================================================

function process_trigger(name, handler, content_check)
    local path = COMM_DIR .. name
    if not fexists(path) then return end
    local content = fread(path)
    if not content or content == "" then frm(path); return end
    content = string.match(content, "^%s*(.-)%s*$")
    if not content or content == "" then frm(path); return end
    if content_check and not content_check(content) then return end
    local ok, err = pcall(handler, content)
    if not ok then log("ERROR " .. name .. ": " .. tostring(err)) end
    pcall(frm, path)
end

function main_loop()
    tick = tick + 1
    fwrite(COMM_DIR .. "audioshuttle_watcher_alive", "tick=" .. tick)
    process_trigger("audioshuttle_wipe_trigger", handle_wipe_trigger, function(c) return c == "wipe" end)
    process_trigger("audioshuttle_state_request", handle_state_request, function(c) return c == "dump" end)
    process_trigger("audioshuttle_markers_trigger", handle_markers_trigger)
    process_trigger("audioshuttle_clear_trigger", handle_clear_trigger)
    process_trigger("audioshuttle_track_insert_trigger", handle_track_insert_trigger)
    process_trigger("audioshuttle_import_trigger", handle_import_trigger)
    process_trigger("audioshuttle_color_cmd.txt", handle_color_trigger)
    process_trigger("audioshuttle_fx_trigger", handle_fx_trigger)
    process_trigger("audioshuttle_fx_list_request", handle_fx_list_request)
    reaper.defer(main_loop)
end

os.execute("mkdir -p " .. COMM_DIR .. " && chmod 777 " .. COMM_DIR)
local f = io.open("/tmp/watcher_debug.log", "w")
if f then f:write("WATCHER v5 STARTED\n"); f:close() end
tick = 0
reaper.defer(main_loop)
