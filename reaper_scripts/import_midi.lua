-- AudioShuttle MIDI Import Script
-- Place in Reaper's Scripts folder and bind to a custom action ID
-- This script imports /tmp/audioshuttle_pattern.mid at the edit cursor

local midi_path = "/tmp/audioshuttle_pattern.mid"

-- Check if file exists
local file = io.open(midi_path, "r")
if not file then
    reaper.ShowMessageBox("No AudioShuttle MIDI file found at " .. midi_path, "AudioShuttle", 0)
    return
end
file:close()

-- Insert the MIDI file at the edit cursor position
reaper.InsertMedia(midi_path, 0)  -- 0 = at cursor

reaper.defer(function() end)  -- No defer needed, one-shot
