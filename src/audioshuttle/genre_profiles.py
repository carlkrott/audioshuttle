from __future__ import annotations

from typing import Any

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
        "instruments": ["drums", "bass", "rhythm_guitar", "lead_guitar", "keys"],
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
        "time_signature": (4, 4),
        "feel": "half-time",
    },
    "funk": {
        "tempo_range": (90, 120),
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
        "instruments": ["drums", "bass", "rhythm_guitar", "keys", "horns", "melody"],
        "time_signature": (4, 4),
        "feel": "straight",
    },
    "blues": {
        "tempo_range": (60, 120),
        "default_tempo": 100,
        "sections": [
            {"name": "intro", "bars": 4},
            {"name": "verse", "bars": 12},
            {"name": "verse", "bars": 12},
            {"name": "solo", "bars": 12},
            {"name": "verse", "bars": 12},
            {"name": "outro", "bars": 4},
        ],
        "instruments": ["drums", "bass", "rhythm_guitar", "lead_guitar", "keys"],
        "time_signature": (4, 4),
        "feel": "shuffle",
    },
}

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
        "jazz": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
        "orchestral": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "woodwinds": {
        "orchestral": [
            {"name": "ReaEQ", "type": "eq"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
        ],
    },
    "vocals": {
        "pop": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
        "broadcast": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "de-esser", "type": "de-esser"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "synths": {
        "electronic": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaLimit", "type": "limiter"},
        ],
        "ambient": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaDelay", "type": "delay"},
            {"name": "ReaVerb", "type": "reverb"},
        ],
        "_default": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaComp", "type": "compressor"},
        ],
    },
    "percussion": {
        "rock": [
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaEQ", "type": "eq"},
        ],
        "electronic": [
            {"name": "ReaEQ", "type": "eq"},
            {"name": "ReaLimit", "type": "limiter"},
        ],
        "_default": [
            {"name": "ReaComp", "type": "compressor"},
            {"name": "ReaEQ", "type": "eq"},
        ],
    },
}


def get_genre(genre_name: str) -> dict[str, Any]:
    """Case-insensitive lookup with fallback to rock default."""
    if genre_name is None:
        return GENRE_PROFILES["rock"]
    return GENRE_PROFILES.get(genre_name.lower(), GENRE_PROFILES["rock"])


def get_family(role: str) -> str:
    """Map any instrument role to its family. Raises ValueError if role unknown."""
    role_lower = role.lower()
    for family, roles in INSTRUMENT_FAMILIES.items():
        if role_lower in roles:
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