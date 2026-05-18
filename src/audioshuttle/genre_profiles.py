from __future__ import annotations

import re
from typing import Any


def get_base_role(instrument_id: str) -> str:
    """Strip the _N suffix from a doubled instrument ID.

    'rhythm_guitar_2' -> 'rhythm_guitar', 'drums' -> 'drums'
    """
    return re.sub(r'_\d+$', '', instrument_id)

# ─── Bus / Track Color Palette ───────────────────────────────────────────────
# Consistent, non-garish colors for grouping visualization in DAW.
# Colors are hex RGB strings (no # prefix for some APIs, with # for others).

BUS_COLORS: dict[str, str] = {
    # Role-function buses (electronic/EDM groupings)
    "Lead":        "#ff3366",   # hot pink - primary melodic content
    "Rhythm":      "#3399ff",   # cool blue - rhythmic foundation
    "Textural":    "#9966ff",   # purple - atmospheric/pads
    "Auxiliary":   "#ff9933",   # warm orange - supporting melodic
    "Effects":     "#00ffcc",   # cyan - fx/riser/impact

    # Instrument-type buses (rock/metal/orchestral groupings)
    "Guitars":     "#ff9933",   # warm orange - guitar family
    "Strings":     "#ffcc66",   # golden - orchestral strings
    "Brass":       "#dd8844",   # copper/bronze - brass family
    "Woodwinds":   "#88ccaa",   # sage green - woodwinds
    "Percussion":  "#99cc33",   # olive/lime - drums/percussion
    "Bass":        "#3366ff",   # deep blue - bass family
    "Vocals":      "#ff3366",   # hot pink - vocal family
    "Synths":      "#9966ff",   # purple - synth family

    # Special tracks
    "Submaster":   "#ffffff",   # white - master bus
    "Bus":         "#888888",   # grey - generic parent bus
}

# ─── Individual Instrument Colors ─────────────────────────────────────────────
# When an instrument doesn't belong to a bus, it gets its own color
# based on its role. Singletons get the bus color of their role function.

INSTRUMENT_COLORS: dict[str, str] = {
    # Drums/percussion
    "drums":       "#99cc33",
    "drum":        "#99cc33",
    "percussion":  "#99cc33",
    "kick":        "#88bb22",
    "snare":       "#aadd22",
    "hihat":       "#bbdd44",
    "timpani":     "#778822",

    # Bass
    "bass":        "#3366ff",
    "upright_bass": "#2255dd",
    "sub":         "#2244aa",

    # Guitars
    "rhythm_guitar": "#ff9933",
    "lead_guitar":   "#ee8822",
    "guitar":       "#dd7722",

    # Keys/piano
    "keys":         "#9966ff",
    "key":          "#8855ee",
    "piano":        "#aa77ff",
    "synth":        "#8855dd",
    "pad":          "#7755cc",
    "arp":          "#6644bb",
    "strings":      "#ffcc66",
    "string":       "#eecc55",
    "violin":       "#ffdd77",
    "viola":        "#eebb55",
    "cello":        "#ddaa44",
    "harp":         "#ccaa33",

    # Brass
    "brass":        "#dd8844",
    "trumpet":      "#ee9966",
    "trombone":     "#cc7733",
    "horns":        "#bb6633",
    "saxophone":    "#dd7755",

    # Woodwinds
    "woodwinds":    "#88ccaa",
    "flute":        "#77bbaa",
    "clarinet":     "#66aa99",
    "oboe":         "#559988",

    # Vocals
    "vocals":       "#ff3366",
    "vocal":        "#ff3366",
    "voice":        "#ff2255",
    "choir":        "#ff4488",

    # Melody/lead
    "lead":         "#ff3366",
    "melody":       "#ff4477",
    "line":         "#ff5588",

    # Effects
    "fx":           "#00ffcc",
    "riser":        "#00ddcc",
    "impact":       "#00bbcc",
    "solo":         "#ee7733",
}

# Default color for any unclassified instrument
_DEFAULT_INSTRUMENT_COLOR = "#888888"


def get_track_color(instrument: str, bus_name: str | None = None) -> str:
    """Resolve the color for a track based on instrument role and bus membership.

    Args:
        instrument: Instrument name (e.g., "lead_guitar", "drums", "rhythm_guitar_2")
        bus_name: Optional bus name if instrument belongs to a bus

    Returns:
        Hex color string without # prefix (e.g., "ff9933")
    """
    inst_lower = instrument.lower().strip()

    if bus_name:
        bus_color = BUS_COLORS.get(bus_name)
        if bus_color:
            return bus_color.lstrip("#")

    if inst_lower in INSTRUMENT_COLORS:
        return INSTRUMENT_COLORS[inst_lower].lstrip("#")

    base = get_base_role(inst_lower)
    if base != inst_lower and base in INSTRUMENT_COLORS:
        return INSTRUMENT_COLORS[base].lstrip("#")

    for func, members in ROLE_FUNCTION.items():
        if inst_lower in members or base in members:
            bus_color = BUS_COLORS.get(func.capitalize())
            if bus_color:
                return bus_color.lstrip("#")
            break

    return _DEFAULT_INSTRUMENT_COLOR.lstrip("#")


def get_bus_color(bus_name: str) -> str:
    """Get the color for a bus track.

    Args:
        bus_name: Bus name (e.g., "Guitars", "Lead", "Rhythm")

    Returns:
        Hex color string without # prefix
    """
    if bus_name in BUS_COLORS:
        return BUS_COLORS[bus_name].lstrip("#")
    return _DEFAULT_INSTRUMENT_COLOR.lstrip("#")


# ─── Instrument Role Functions ────────────────────────────────────────────────
# Describes what musical function an instrument serves, independent of genre.
# Used by dynamic grouping to determine bus assignments.

ROLE_FUNCTION: dict[str, list[str]] = {
    # carries the primary melodic/harmonic content
    "lead": ["lead", "melody", "line", "vocals", "vocal", "voice"],
    # provides rhythmic foundation + harmonic support
    "rhythm": ["bass", "rhythm_guitar", "drums", "drum", "percussion", "beat"],
    # textural/ambient content - pads, strings, atmospheric
    "textural": ["pad", "strings", "string", "violin", "viola", "cello",
                 "woodwinds", "flute", "clarinet", "harp", "brass", "horn"],
    # auxiliary melodic content (counter-melodies, fills, solos)
    "auxiliary": ["lead_guitar", "solo", "arp", "keys", "key", "synth",
                  "piano", "melody"],
    # special effects, risers, impacts
    "effects": ["fx", "riser", "impact", "sub"],
}

# ─── Genre Grouping Strategies ────────────────────────────────────────────────
# Defines how instruments are grouped into buses for each genre.
# Strategy options:
#   "instrument_type"  → group by INSTRUMENT_FAMILIES (guitars, strings, etc.)
#   "role_function"     → group by musical role (lead, rhythm, textural, etc.)
#   "explicit"          → user/LLM explicitly specified grouping (no automatic rules)

GROUPING_STRATEGY: dict[str, str] = {
    # Rock/pop: by instrument type (guitars together, keys together, etc.)
    "rock": "instrument_type",
    "pop": "instrument_type",
    "metal": "instrument_type",
    "punk": "instrument_type",
    "blues": "instrument_type",
    "country": "instrument_type",
    "reggae": "instrument_type",

    # Electronic/EDM: by role function (leads grouped, pads grouped, etc.)
    "electronic": "role_function",
    "edm": "role_function",
    "house": "role_function",
    "techno": "role_function",
    "trance": "role_function",
    "dubstep": "role_function",
    "drumandbass": "role_function",
    "ambient": "role_function",
    "trap": "role_function",
    "futurebass": "role_function",

    # Hybrid: primarily role-based with instrument_type fallback
    "hiphop": "role_function",
    "rnb": "role_function",

    # Large ensemble: by instrument type (orchestral sections)
    "jazz": "role_function",
    "orchestral": "instrument_type",
    "classical": "instrument_type",
    "cinematic": "role_function",
    "funk": "instrument_type",
    "soul": "instrument_type",
    "latin": "instrument_type",
    "worship": "instrument_type",
}

# ─── Genre Hierarchy (inheritance for sub-genres) ────────────────────────────
# Sub-genres inherit from their parent genre. Leaf genres override.
GENRE_HIERARCHY: dict[str, str] = {
    "metal": "rock",
    "punk": "rock",
    "blues": "rock",
    "country": "rock",
    "synthwave": "electronic",
    "retrowave": "electronic",
    "house": "electronic",
    "techno": "electronic",
    "trance": "electronic",
    "dubstep": "electronic",
    "drumandbass": "electronic",
    "trap": "hiphop",
    "futurebass": "electronic",
    "hiphop": "electronic",
    "rnb": "hiphop",
    "soul": "rnb",
    "funk": "pop",
    "worship": "pop",
    "latin": "pop",
}

# ─── Genre Modifiers (how sub-genres modify parent) ──────────────────────────
# Each modifier is a tuple of (instruments_to_add, instruments_to_remove, section_modifications)
# These are ADDITIVE to the parent genre's profile

GENRE_MODIFIERS: dict[str, dict[str, Any]] = {
    "metal": {
        "add_instruments": ["lead_guitar"],
        "remove_instruments": ["keys"],
        "tempo_shift": 40,
        "doubles_override": {"rhythm_guitar": 2, "lead_guitar": 2, "drums": 1, "bass": 1},
    },
    "punk": {
        "tempo_shift": 40,
        "doubles_override": {"rhythm_guitar": 2, "lead_guitar": 2, "drums": 1, "bass": 1, "keys": 1, "vocals": 1},
    },
    "blues": {
        "tempo_shift": -20,
        "doubles_override": {"rhythm_guitar": 2, "lead_guitar": 2, "drums": 1, "bass": 1, "keys": 1, "vocals": 1},
    },
    "country": {
        "tempo_shift": -10,
        "doubles_override": {"rhythm_guitar": 2, "lead_guitar": 1, "strings": 2, "drums": 1, "bass": 1, "keys": 1, "vocals": 1},
    },
    "orchestral": {
        "add_instruments": ["strings", "brass", "woodwinds", "harp", "timpani"],
        "remove_instruments": ["bass", "keys", "rhythm_guitar", "lead_guitar", "drums"],
        "tempo_shift": -30,
    },
    "synthwave": {
        "add_instruments": ["pad", "arp", "fx"],
        "remove_instruments": [],
        "tempo_shift": 0,
    },
    "funk": {
        "doubles_override": {"rhythm_guitar": 2, "keys": 2, "drums": 1, "bass": 1, "melody": 1, "vocals": 1},
    },
    "soul": {
        "doubles_override": {"keys": 2, "strings": 2, "vocals": 2, "drums": 1, "bass": 1, "melody": 1},
    },
    "worship": {
        "doubles_override": {"keys": 2, "pad": 2, "strings": 2, "drums": 1, "bass": 1, "vocals": 1},
    },
    "latin": {
        "doubles_override": {"drums": 2, "keys": 2, "bass": 1, "melody": 1, "vocals": 1},
    },
}

# ─── Instrument Families (static, genre-agnostic) ────────────────────────────
# Used when grouping strategy is "instrument_type"

INSTRUMENT_FAMILIES: dict[str, set[str]] = {
    "guitars": {"rhythm_guitar", "lead_guitar", "guitar"},
    "strings": {"strings", "violin", "viola", "cello", "string", "orchestral_strings", "harp"},
    "brass": {"brass", "trumpet", "trombone", "horns", "saxophone"},
    "woodwinds": {"woodwinds", "flute", "clarinet", "oboe"},
    "vocals": {"vocals", "vocal", "voice", "choir"},
    "synths": {"synth", "pad", "arp", "fx", "riser", "keys", "key", "melody", "piano"},
    "percussion": {"drums", "drum", "beat", "kick", "snare", "percussion", "timpani"},
    "bass": {"bass", "upright_bass", "sub"},
}

# ─── Genre Profiles ──────────────────────────────────────────────────────────

GENRE_PROFILES: dict[str, dict[str, Any]] = {
    "rock": {
        "tempo_range": (100, 140),
        "default_tempo": 120,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "solo", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["drums", "bass", "rhythm_guitar", "lead_guitar", "keys", "vocals"],
        "doubles": {"rhythm_guitar": 2, "lead_guitar": 1, "keys": 1, "vocals": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "pop": {
        "tempo_range": (90, 130),
        "default_tempo": 120,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "prechorus", "bars": 4},
            {"name": "chorus", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "prechorus", "bars": 4},
            {"name": "chorus", "bars": 8},
            {"name": "bridge", "bars": 8},
            {"name": "chorus", "bars": 8},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["drums", "bass", "keys", "pad", "melody", "vocals"],
        "doubles": {"keys": 2, "pad": 1, "melody": 1, "vocals": 2, "drums": 1, "bass": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "electronic": {
        "tempo_range": (120, 140),
        "default_tempo": 128,
        "sections": [
            {"name": "intro", "bars": 8},
            {"name": "buildup", "bars": 16},
            {"name": "drop", "bars": 8},
            {"name": "breakdown", "bars": 8},
            {"name": "buildup", "bars": 16},
            {"name": "drop", "bars": 8},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["drums", "sub", "bass", "synth", "pad", "arp", "fx"],
        "doubles": {"synth": 2, "arp": 2, "pad": 2, "drums": 1, "sub": 1, "bass": 1, "fx": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "hiphop": {
        "tempo_range": (70, 100),
        "default_tempo": 90,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "hook", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "hook", "bars": 8},
            {"name": "bridge", "bars": 4},
            {"name": "hook", "bars": 8},
            {"name": "outro", "bars": 4},
        ],
        "instruments": ["drums", "bass", "sub", "keys", "pad", "melody"],
        "doubles": {"synth": 2, "pad": 2, "keys": 1, "melody": 1, "drums": 1, "bass": 1, "sub": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "jazz": {
        "tempo_range": (80, 160),
        "default_tempo": 120,
        "sections": [
            {"name": "intro", "bars": 8},
            {"name": "head", "bars": 32},
            {"name": "solo", "bars": 32},
            {"name": "head", "bars": 32},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["drums", "upright_bass", "piano", "melody", "pad"],
        "doubles": {"keys": 2, "melody": 2, "drums": 1, "upright_bass": 1, "pad": 1},
        "time_signature": (4, 4),
        "feel": "swing",
    },
    "orchestral": {
        "tempo_range": (60, 120),
        "default_tempo": 90,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "a", "bars": 16},
            {"name": "b", "bars": 16},
            {"name": "a", "bars": 16},
            {"name": "climax", "bars": 16},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["strings", "brass", "woodwinds", "percussion", "harp", "timpani"],
        "doubles": {"strings": 3, "brass": 2, "woodwinds": 1, "percussion": 1, "harp": 1, "timpani": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "ambient": {
        "tempo_range": (60, 90),
        "default_tempo": 70,
        "sections": [
            {"name": "intro", "bars": 16},
            {"name": "a", "bars": 32},
            {"name": "b", "bars": 32},
            {"name": "a", "bars": 32},
            {"name": "outro", "bars": 16},
        ],
        "instruments": ["pad", "strings", "keys", "fx", "melody"],
        "doubles": {"pad": 3, "strings": 2, "keys": 1, "fx": 1, "melody": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "metal": {
        "tempo_range": (100, 200),
        "default_tempo": 160,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "solo", "bars": 16},
            {"name": "breakdown", "bars": 8},
            {"name": "chorus", "bars": 8},
            {"name": "outro", "bars": 4},
        ],
        "instruments": ["drums", "bass", "rhythm_guitar", "lead_guitar"],
        "doubles": {"rhythm_guitar": 2, "lead_guitar": 2, "drums": 1, "bass": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "reggae": {
        "tempo_range": (60, 90),
        "default_tempo": 75,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "bridge", "bars": 8},
            {"name": "chorus", "bars": 8},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["drums", "bass", "rhythm_guitar", "keys", "melody"],
        "doubles": {"rhythm_guitar": 2, "keys": 2, "drums": 1, "bass": 1, "melody": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "cinematic": {
        "tempo_range": (60, 120),
        "default_tempo": 90,
        "sections": [
            {"name": "intro", "bars": 8},
            {"name": "rising", "bars": 16},
            {"name": "climax", "bars": 16},
            {"name": "release", "bars": 16},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["strings", "brass", "pad", "keys", "melody"],
        "doubles": {"strings": 3, "brass": 2, "pad": 2, "keys": 1, "melody": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "rnb": {
        "tempo_range": (70, 100),
        "default_tempo": 85,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "hook", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "hook", "bars": 8},
            {"name": "bridge", "bars": 8},
            {"name": "hook", "bars": 8},
            {"name": "outro", "bars": 4},
        ],
        "instruments": ["drums", "bass", "keys", "pad", "melody", "vocals"],
        "doubles": {"keys": 2, "strings": 2, "vocals": 1, "pad": 1, "drums": 1, "bass": 1, "melody": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "trap": {
        "tempo_range": (65, 100),
        "default_tempo": 80,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "hook", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "hook", "bars": 8},
            {"name": "bridge", "bars": 8},
            {"name": "hook", "bars": 8},
            {"name": "outro", "bars": 4},
        ],
        "instruments": ["drums", "bass", "sub", "keys", "pad", "melody"],
        "doubles": {"synth": 2, "pad": 2, "keys": 1, "melody": 1, "drums": 1, "bass": 1, "sub": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "funk": {
        "tempo_range": (90, 120),
        "default_tempo": 105,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "bridge", "bars": 8},
            {"name": "chorus", "bars": 8},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["drums", "bass", "rhythm_guitar", "keys", "melody", "vocals"],
        "doubles": {"rhythm_guitar": 2, "keys": 2, "drums": 1, "bass": 1, "melody": 1, "vocals": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "soul": {
        "tempo_range": (70, 100),
        "default_tempo": 85,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "bridge", "bars": 8},
            {"name": "chorus", "bars": 8},
            {"name": "outro", "bars": 4},
        ],
        "instruments": ["drums", "bass", "keys", "strings", "vocals", "melody"],
        "doubles": {"keys": 2, "strings": 2, "vocals": 2, "drums": 1, "bass": 1, "melody": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "latin": {
        "tempo_range": (90, 130),
        "default_tempo": 110,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "bridge", "bars": 8},
            {"name": "chorus", "bars": 8},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["drums", "bass", "keys", "melody", "vocals"],
        "doubles": {"drums": 2, "keys": 2, "bass": 1, "melody": 1, "vocals": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "worship": {
        "tempo_range": (60, 100),
        "default_tempo": 80,
        "sections": [
            {"name": "intro", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "verse", "bars": 16},
            {"name": "chorus", "bars": 8},
            {"name": "bridge", "bars": 8},
            {"name": "chorus", "bars": 8},
            {"name": "outro", "bars": 8},
        ],
        "instruments": ["drums", "bass", "keys", "pad", "strings", "vocals"],
        "doubles": {"keys": 2, "pad": 2, "strings": 2, "drums": 1, "bass": 1, "vocals": 1},
        "time_signature": (4, 4),
        "feel": "straight",
    },
}


# ─── Dynamic Grouping System ─────────────────────────────────────────────────

def get_grouping_strategy(genre: str) -> str:
    """Get the grouping strategy for a genre, resolving hierarchy.

    Args:
        genre: Genre name (e.g., "metal", "synthwave", "rock")

    Returns:
        Grouping strategy: "instrument_type", "role_function", or "explicit"
    """
    genre_lower = genre.lower().strip()

    # Direct match
    if genre_lower in GROUPING_STRATEGY:
        return GROUPING_STRATEGY[genre_lower]

    # Check hierarchy (walk up the tree)
    visited = set()
    current = genre_lower
    while current in GENRE_HIERARCHY:
        if current in GROUPING_STRATEGY:
            return GROUPING_STRATEGY[current]
        visited.add(current)
        current = GENRE_HIERARCHY[current]
        if current in visited:  # prevent infinite loop
            break

    # Default to role_function (most flexible)
    return "role_function"


def resolve_genre_profile(genre: str, additions: list[str] | None = None) -> dict[str, Any]:
    """Resolve a genre profile, applying hierarchy and modifiers.

    This implements the "modified rock + additions" logic:
    1. Walk up hierarchy to find root genre
    2. Apply root profile
    3. Walk back down applying modifiers
    4. Add any explicitly requested instruments

    Args:
        genre: Genre name (e.g., "metal")
        additions: Instruments to add to the base profile (e.g., ["strings"])

    Returns:
        Resolved genre profile dict with full instrumentation and sections
    """
    genre_lower = genre.lower().strip()

    # Collect hierarchy path from root to leaf
    hierarchy_path = []
    current = genre_lower
    while current:
        hierarchy_path.insert(0, current)
        current = GENRE_HIERARCHY.get(current, "")

    # Start with root profile (first in path)
    root = hierarchy_path[0]
    profile = dict(GENRE_PROFILES.get(root, GENRE_PROFILES["rock"]))

    # Apply modifiers along the path
    instruments_set = set(profile.get("instruments", []))

    for gen in hierarchy_path[1:]:
        if gen in GENRE_MODIFIERS:
            mod = GENRE_MODIFIERS[gen]
            instruments_set.difference_update(mod.get("remove_instruments", []))
            instruments_set.update(mod.get("add_instruments", []))

    # Apply user additions (e.g., explicit request for "orchestral strings")
    if additions:
        instruments_set.update(additions)

    profile["instruments"] = list(instruments_set)

    doubles = _resolve_doubles_along_path(hierarchy_path)
    profile["doubles"] = doubles

    if genre_lower in GENRE_MODIFIERS:
        shift = GENRE_MODIFIERS[genre_lower].get("tempo_shift", 0)
        if shift:
            profile["default_tempo"] = max(
                profile["tempo_range"][0],
                min(profile["tempo_range"][1], profile["default_tempo"] + shift)
            )

    profile["resolved_genre"] = genre_lower
    return profile


def _resolve_doubles_along_path(hierarchy_path: list[str]) -> dict[str, int]:
    """Merge doubles configs along a genre hierarchy path."""
    result: dict[str, int] = {}
    for gen in hierarchy_path:
        profile = GENRE_PROFILES.get(gen)
        if profile and "doubles" in profile:
            result.update(profile["doubles"])
        mod = GENRE_MODIFIERS.get(gen)
        if mod and "doubles_override" in mod:
            result.update(mod["doubles_override"])
    return result


def resolve_genre_doubles(genre: str, user_doubles: dict[str, int] | None = None) -> dict[str, int]:
    """Resolve the doubling config for a genre, with user overrides.

    Walks the genre hierarchy to merge doubles configs, then applies user overrides.

    Args:
        genre: Genre name (e.g., "metal", "punk")
        user_doubles: Optional user-specified doubling overrides

    Returns:
        Dict mapping instrument names to copy counts (1 = no double, 2+ = doubled)
    """
    genre_lower = genre.lower().strip()

    hierarchy_path = []
    current = genre_lower
    while current:
        hierarchy_path.insert(0, current)
        current = GENRE_HIERARCHY.get(current, "")

    result = _resolve_doubles_along_path(hierarchy_path)

    if user_doubles:
        result.update(user_doubles)

    return result


def get_role_function(instrument: str) -> str | None:
    """Get the musical role function for an instrument.

    Handles doubled instruments (e.g., 'rhythm_guitar_2') by stripping the _N suffix.

    Args:
        instrument: Instrument name (e.g., "lead_guitar", "pad", "rhythm_guitar_2")

    Returns:
        Role function string or None if not found
    """
    inst_lower = instrument.lower().strip()
    for function, instruments in ROLE_FUNCTION.items():
        if inst_lower in instruments:
            return function
    base = get_base_role(inst_lower)
    if base != inst_lower:
        for function, instruments in ROLE_FUNCTION.items():
            if base in instruments:
                return function
    return None


def compute_instrument_grouping(
    instruments: list[str],
    genre: str,
    explicit_buses: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Compute bus groupings for instruments based on genre and role.

    This is the core dynamic grouping function. It:
    1. Determines grouping strategy (instrument_type vs role_function)
    2. Groups instruments accordingly
    3. Respects explicit bus overrides from user/LLM

    Args:
        instruments: List of instrument names (e.g., ["drums", "bass", "lead_guitar"])
        genre: Genre name for strategy selection
        explicit_buses: Optional explicit bus assignments, e.g.,
            {"Lead Bus": ["melody", "lead_guitar"], "Rhythm Bus": ["bass", "drums"]}
            When provided, this takes highest priority.

    Returns:
        Dict mapping bus names to instrument lists, e.g.,
        {"Lead": ["melody"], "Guitars": ["rhythm_guitar", "lead_guitar"], ...}
    """
    strategy = get_grouping_strategy(genre)
    buses: dict[str, list[str]] = {}

    # Handle explicit buses first (user/LLM override)
    if explicit_buses:
        for bus_name, bus_instruments in explicit_buses.items():
            buses[bus_name] = list(bus_instruments)
        # Remove explicitly-assigned instruments from automatic grouping
        assigned = set()
        for bus_instruments in explicit_buses.values():
            assigned.update(bus_instruments)
        instruments = [i for i in instruments if i not in assigned]

    if strategy == "explicit":
        # No automatic grouping - only explicit buses
        return buses

    # ─── Role-function based grouping ─────────────────────────────────────────
    if strategy == "role_function":
        # Group by musical function
        role_groups: dict[str, list[str]] = {
            "lead": [],
            "rhythm": [],
            "textural": [],
            "auxiliary": [],
            "effects": [],
        }

        for inst in instruments:
            func = get_role_function(inst) or "auxiliary"
            if func not in role_groups:
                role_groups[func] = []
            role_groups[func].append(inst)

        # Map role groups to bus names
        for func, insts in role_groups.items():
            if len(insts) == 1:
                # Single instrument - no bus needed unless user wants it
                continue
            elif len(insts) > 1:
                # Multiple instruments - create bus
                bus_name = func.capitalize()
                buses[bus_name] = insts

    elif strategy == "instrument_type":
        family_groups: dict[str, list[str]] = {}

        for inst in instruments:
            inst_lower = inst.lower()
            base = get_base_role(inst_lower)
            assigned = False
            for family, members in INSTRUMENT_FAMILIES.items():
                if inst_lower in members or base in members:
                    if family not in family_groups:
                        family_groups[family] = []
                    family_groups[family].append(inst)
                    assigned = True
                    break
            if not assigned:
                func = get_role_function(inst)
                if func:
                    bus_name = func.capitalize()
                else:
                    bus_name = inst.capitalize()
                family_groups[bus_name] = [inst]

        for family, insts in family_groups.items():
            if len(insts) > 1:
                buses[family.capitalize()] = insts

    return buses


# ─── Genre Lookup Helpers ─────────────────────────────────────────────────────

def get_genre(genre_name: str | None) -> dict[str, Any]:
    """Get a genre profile by name, with fallback to rock."""
    if genre_name is None:
        return GENRE_PROFILES["rock"]
    return GENRE_PROFILES.get(genre_name.lower(), GENRE_PROFILES["rock"])


def get_family(role: str) -> str:
    """Map any instrument role to its family. Handles doubled instruments (_N suffix).
    Raises ValueError if role unknown."""
    role_lower = role.lower()
    for family, roles in INSTRUMENT_FAMILIES.items():
        if role_lower in roles:
            return family
    base = get_base_role(role_lower)
    if base != role_lower:
        for family, roles in INSTRUMENT_FAMILIES.items():
            if base in roles:
                return family
    raise ValueError(f"Unknown instrument role: {role}")


def get_fx_chain(role: str, genre: str) -> list[dict[str, str]]:
    """Resolve FX chain for an instrument in a genre, falling back through families and defaults."""
    try:
        family = get_family(role)
    except ValueError:
        return []
    family_chains = FX_CHAINS.get(family, {})
    genre_lower = genre.lower()
    if genre_lower in family_chains:
        return family_chains[genre_lower]
    return family_chains.get("_default", [])


def get_tempo(genre_name: str | None, user_tempo: int | None = None) -> int:
    """Use user tempo if provided, otherwise genre default, otherwise 120."""
    if user_tempo is not None:
        return user_tempo
    if genre_name is None:
        return 120
    profile = get_genre(genre_name)
    return profile.get("default_tempo", 120)


def validate_profile(genre_name: str) -> bool:
    """Check a profile has all required fields."""
    required_fields = ("tempo_range", "default_tempo", "sections", "instruments", "time_signature", "feel")
    profile = get_genre(genre_name)
    for field in required_fields:
        if field not in profile:
            return False
    return True


# ─── FX Chains (unchanged from original) ──────────────────────────────────────

FX_CHAINS: dict[str, dict[str, list[dict[str, str]]]] = {
    "guitars": {
        "rock": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
        "metal": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaGate", "type": "gate"},
        ],
        "jazz": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "light", "type": "general"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "strings": {
        "orchestral": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
        "ambient": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaDelay", "type": "delay"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "brass": {
        "orchestral": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "woodwinds": {
        "orchestral": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
        ],
    },
    "vocals": {
        "rock": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
        "pop": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
            {"name": "ReaDelay", "type": "delay"},
        ],
        "hiphop": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "Rvox", "type": "vocals"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
    },
    "synths": {
        "electronic": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
        "ambient": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaVerb", "type": "reverb"},
            {"name": "ReaDelay", "type": "delay"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "percussion": {
        "rock": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
        "electronic": [
            {"name": "ReaEQ", "type": "eq"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
        ],
    },
    "bass": {
        "rock": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
        "electronic": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
}


# ─── Bus FX Chains ────────────────────────────────────────────────────────
# Applied to bus tracks (glue compression + EQ per instrument family).
# Key = family name, value = genre -> FX chain (same structure as FX_CHAINS).

BUS_FX_CHAINS: dict[str, dict[str, list[dict[str, str]]]] = {
    "guitars": {
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "strings": {
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
    },
    "brass": {
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "woodwinds": {
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
    },
    "vocals": {
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
    },
    "synths": {
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "percussion": {
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "bass": {
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
}


def get_bus_fx_chain(bus_name: str, genre: str) -> list[dict[str, str]]:
    """Resolve FX chain for a bus by family name."""
    family = bus_name.lower()
    family_chains = BUS_FX_CHAINS.get(family, {})
    genre_lower = genre.lower()
    if genre_lower in family_chains:
        return family_chains[genre_lower]
    return family_chains.get("_default", [])


SUBMASTER_FX_CHAIN: list[dict[str, str]] = [
    {"name": "ReaEQ", "type": "eq"},
    {"name": "ReaComp", "type": "compressor"},
    {"name": "ReaLimit", "type": "limiter"},
    {"name": "ReaVerb", "type": "reverb"},
]