"""Arrangement Engine — expands genre profiles into full arrangement plans.

Takes a genre profile, user parameters, and produces a complete arrangement:
expanded instrument players, per-section layer assignments, and bus topology.
"""

from __future__ import annotations

import re
from typing import Any


# ─── Instrument Variants ──────────────────────────────────────────────────────
# Each base role maps to a list of variant descriptors. Variants determine
# playing style, density modifier, octave offset, and MIDI channel.

INSTRUMENT_VARIANTS: dict[str, list[dict[str, Any]]] = {
    "drums": [
        {"name": "Standard Kit", "complexity": "standard", "density_mod": 0.0, "octave_shift": 0, "channel": 9},
        {"name": "Cymbal Heavy", "complexity": "dense", "density_mod": 0.15, "octave_shift": 0, "channel": 9},
    ],
    "rhythm_guitar": [
        {"name": "Power Chords", "complexity": "standard", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Arpeggiated", "complexity": "arpeggio", "density_mod": -0.1, "octave_shift": 0, "channel": 0},
    ],
    "lead_guitar": [
        {"name": "Melodic Line", "complexity": "melodic", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Harmonics", "complexity": "sparse", "density_mod": -0.2, "octave_shift": 12, "channel": 0},
    ],
    "strings": [
        {"name": "Sustained", "complexity": "sustained", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Counter Melody", "complexity": "counter_melody", "density_mod": 0.1, "octave_shift": 12, "channel": 0},
    ],
    "keys": [
        {"name": "Block Chords", "complexity": "standard", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Arpeggiated Triads", "complexity": "arpeggio", "density_mod": 0.1, "octave_shift": 0, "channel": 0},
    ],
    "bass": [
        {"name": "Root-Fifth", "complexity": "standard", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Walking", "complexity": "melodic", "density_mod": 0.15, "octave_shift": 0, "channel": 0},
    ],
    "vocals": [
        {"name": "Main Melody", "complexity": "melodic", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Harmony", "complexity": "melodic", "density_mod": -0.1, "octave_shift": 4, "channel": 0},
    ],
    "pad": [
        {"name": "Sustained Chord", "complexity": "sustained", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Filtered Sweep", "complexity": "sparse", "density_mod": -0.2, "octave_shift": -12, "channel": 0},
    ],
    "cowbell": [
        {"name": "Classic", "complexity": "percussive", "density_mod": 0.0, "octave_shift": 0, "channel": 9},
        {"name": "Syncopated", "complexity": "dense", "density_mod": 0.2, "octave_shift": 0, "channel": 9},
    ],
    "synth": [
        {"name": "Lead", "complexity": "melodic", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Stab", "complexity": "percussive", "density_mod": 0.1, "octave_shift": 0, "channel": 0},
    ],
    "arp": [
        {"name": "Standard", "complexity": "arpeggio", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Fast", "complexity": "arpeggio", "density_mod": 0.2, "octave_shift": 12, "channel": 0},
    ],
    "melody": [
        {"name": "Main", "complexity": "melodic", "density_mod": 0.0, "octave_shift": 0, "channel": 0},
        {"name": "Octave Up", "complexity": "melodic", "density_mod": -0.1, "octave_shift": 12, "channel": 0},
    ],
}

DEFAULT_VARIANT: dict[str, Any] = {
    "name": "Standard",
    "complexity": "standard",
    "density_mod": 0.0,
    "octave_shift": 0,
    "channel": 0,
}


# ─── Genre Doubles ────────────────────────────────────────────────────────────
# Specifies how many instances of each instrument a genre uses.
# Only instruments with count > 1 get doubled (e.g. rhythm_guitar → _1, _2).

GENRE_DOUBLES: dict[str, dict[str, int]] = {
    "rock": {
        "rhythm_guitar": 2,
        "strings": 0,
    },
    "metal": {
        "rhythm_guitar": 2,
        "lead_guitar": 2,
    },
    "pop": {
        "keys": 2,
        "strings": 2,
        "vocals": 2,
    },
    "electronic": {
        "synth": 2,
        "arp": 2,
        "pad": 2,
    },
    "jazz": {
        "keys": 2,
        "melody": 2,
    },
    "orchestral": {
        "strings": 3,
        "brass": 2,
    },
    "ambient": {
        "pad": 3,
        "strings": 2,
    },
    "funk": {
        "rhythm_guitar": 2,
        "keys": 2,
    },
    "blues": {
        "rhythm_guitar": 2,
        "lead_guitar": 2,
    },
    "reggae": {
        "rhythm_guitar": 2,
        "keys": 2,
    },
    "country": {
        "rhythm_guitar": 2,
        "strings": 2,
    },
    "hiphop": {
        "synth": 2,
        "pad": 2,
    },
    "worship": {
        "keys": 2,
        "pad": 2,
        "strings": 2,
    },
    "cinematic": {
        "strings": 3,
        "brass": 2,
        "pad": 2,
    },
    "latin": {
        "drums": 2,
        "keys": 2,
    },
    "soul": {
        "keys": 2,
        "strings": 2,
        "vocals": 2,
    },
    "punk": {
        "rhythm_guitar": 2,
        "lead_guitar": 2,
    },
}


# ─── Section Layers ───────────────────────────────────────────────────────────
# Per-section layer assignments determine which instruments play and at what
# density/velocity.  Layer entries are tuples of:
#   (role_pattern, variant_index_or_None, density_override_or_None)
#
# role_pattern forms:
#   "drums:*"       — matches drums, drums_1, drums_2 (wildcard)
#   "rhythm_guitar:1" — matches rhythm_guitar_1 only (specific suffix)
#   "*"             — matches everyone not yet assigned
#
# variant_index:  0=first variant, 1=second variant, None=keep player default
# density_override: float to replace section density, or None to use section default

SECTION_LAYERS: dict[str, dict[str, Any]] = {
    "intro": {
        "density": 0.3,
        "vel_range": (50, 80),
        "layers": [
            [("drums:*", 0, 0.2), ("keys:*", 0, None), ("pad:*", 0, None)],
            [("bass:*", 0, 0.3)],
        ],
    },
    "verse": {
        "density": 0.6,
        "vel_range": (60, 100),
        "layers": [
            [("drums:*", None, None), ("bass:*", None, None), ("rhythm_guitar:*", 0, None)],
            [("keys:*", None, 0.4), ("rhythm_guitar:*", 1, None)],
            [("vocals:*", 0, None), ("lead_guitar:*", 0, 0.3), ("melody:*", 0, 0.3)],
        ],
    },
    "prechorus": {
        "density": 0.7,
        "vel_range": (60, 110),
        "layers": [
            [("drums:*", None, 0.5), ("bass:*", None, 0.5)],
            [("keys:*", None, None), ("pad:*", None, None), ("strings:*", None, None)],
            [("vocals:*", None, None), ("rhythm_guitar:*", None, None)],
        ],
    },
    "chorus": {
        "density": 1.0,
        "vel_range": (80, 127),
        "layers": [
            [("*", None, None)],
        ],
    },
    "solo": {
        "density": 0.8,
        "vel_range": (70, 120),
        "layers": [
            [("drums:*", None, 0.7), ("bass:*", None, 0.6), ("rhythm_guitar:*", 0, 0.5)],
            [("lead_guitar:*", None, None), ("keys:*", 1, None)],
            [("pad:*", 0, 0.3)],
        ],
    },
    "bridge": {
        "density": 0.5,
        "vel_range": (50, 90),
        "layers": [
            [("pad:*", None, None), ("strings:*", 1, None)],
            [("keys:*", 1, None), ("vocals:*", 0, 0.4)],
        ],
    },
    "breakdown": {
        "density": 0.2,
        "vel_range": (40, 70),
        "layers": [
            [("pad:*", 0, None), ("strings:*", 0, 0.3)],
        ],
    },
    "buildup": {
        "density": 0.7,
        "vel_range": (60, 120),
        "layers": [
            [("drums:*", None, 0.5), ("bass:*", None, 0.5)],
            [("pad:*", None, None), ("synth:*", None, None), ("arp:*", None, None)],
            [("strings:*", None, None), ("vocals:*", None, 0.5)],
        ],
    },
    "drop": {
        "density": 1.0,
        "vel_range": (90, 127),
        "layers": [
            [("*", None, None)],
        ],
    },
    "outro": {
        "density": 0.4,
        "vel_range": (40, 80),
        "layers": [
            [("drums:*", 0, 0.3), ("bass:*", 0, 0.2)],
            [("pad:*", None, None), ("vocals:*", 0, None)],
            [("strings:*", 0, 0.3)],
        ],
    },
    "a": {
        "density": 0.5,
        "vel_range": (55, 95),
        "layers": [[("*", None, None)]],
    },
    "b": {
        "density": 0.6,
        "vel_range": (60, 100),
        "layers": [[("*", None, None)]],
    },
    "rising": {
        "density": 0.7,
        "vel_range": (60, 110),
        "layers": [[("*", None, None)]],
    },
    "climax": {
        "density": 1.0,
        "vel_range": (85, 127),
        "layers": [[("*", None, None)]],
    },
    "release": {
        "density": 0.4,
        "vel_range": (45, 80),
        "layers": [[("*", None, None)]],
    },
}


def _normalize_section_name(name: str) -> str:
    """Normalize a section name for lookup.

    ``'Verse 1'`` → ``'verse'``, ``'CHORUS'`` → ``'chorus'``,
    ``'Pre-Chorus'`` → ``'prechorus'``.
    """
    normalized = name.lower().strip()
    normalized = re.sub(r"\s+\d+$", "", normalized)
    normalized = normalized.replace(" ", "").replace("-", "")
    return normalized


def _get_variants(role: str) -> list[dict[str, Any]]:
    """Return variant list for *role*, falling back to ``[DEFAULT_VARIANT]``."""
    return INSTRUMENT_VARIANTS.get(role, [DEFAULT_VARIANT])


def _make_display_name(role: str, index: int, total: int) -> str:
    """Human-readable name: ``'Rhythm Guitar 1'`` or just ``'Drums'``."""
    pretty = role.replace("_", " ").title()
    if total > 1:
        return f"{pretty} {index + 1}"
    return pretty


# ─── Public API ───────────────────────────────────────────────────────────────


def expand_instruments(
    base_instruments: list[str],
    genre: str,
    custom_instruments: list[str] | None = None,
    user_doubles: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Expand a base instrument list into doubled players with variants.

    Args:
        base_instruments: Genre's base instrument list.
        genre: Genre name for looking up doubling defaults.
        custom_instruments: User-requested extra instruments (e.g. ``["cowbell"]``).
        user_doubles: User-requested doubling overrides (e.g. ``{"cowbell": 2}``).

    Returns:
        List of player dicts, each with:
        - ``"id"``: unique identifier (e.g. ``"rhythm_guitar_1"``)
        - ``"base_role"``: base instrument role (e.g. ``"rhythm_guitar"``)
        - ``"variant_index"``: which variant to use (0, 1, 2…)
        - ``"variant"``: the variant descriptor dict
        - ``"display_name"``: human-readable name (e.g. ``"Rhythm Guitar 1"``)
    """
    genre_doubles = GENRE_DOUBLES.get(genre, {})
    effective_doubles: dict[str, int] = {**genre_doubles}
    if user_doubles:
        effective_doubles.update(user_doubles)

    if not base_instruments:
        return []

    all_instruments = list(base_instruments)
    if custom_instruments:
        for inst in custom_instruments:
            if inst not in all_instruments:
                all_instruments.append(inst)

    players: list[dict[str, Any]] = []

    for role in all_instruments:
        count = effective_doubles.get(role, 1)
        if count < 1:
            continue
        variants = _get_variants(role)
        for i in range(count):
            variant_index = i % len(variants)
            variant = variants[variant_index]
            suffix = f"_{i + 1}" if count > 1 else ""
            players.append({
                "id": f"{role}{suffix}",
                "base_role": role,
                "variant_index": variant_index,
                "variant": variant,
                "display_name": _make_display_name(role, i, count),
            })

    return players


def _matches_pattern(player_id: str, base_role: str, pattern: str) -> bool:
    """Check whether a player matches a role pattern.

    Pattern forms:
    - ``"drums:*"`` matches any player whose base_role is ``"drums"``
    - ``"drums:1"`` matches player ``"drums_1"`` exactly
    - ``"*"`` matches everyone
    """
    if pattern == "*":
        return True

    if ":" not in pattern:
        return base_role == pattern or player_id == pattern

    pat_role, pat_qualifier = pattern.split(":", 1)
    if base_role != pat_role:
        return False
    if pat_qualifier == "*":
        return True
    return player_id == f"{pat_role}_{pat_qualifier}"


def resolve_section_layers(
    players: list[dict[str, Any]],
    section_name: str,
    section_bars: int,
) -> list[dict[str, Any]]:
    """Determine which players are active in a section and their settings.

    Args:
        players: The expanded player list from :func:`expand_instruments`.
        section_name: Section name (e.g. ``"verse"``, ``"chorus"``).
        section_bars: Number of bars in this section.

    Returns:
        List of dicts, one per *active* player, with:
        - ``"player"``: the player dict
        - ``"density"``: effective density for this section
        - ``"vel_range"``: ``(min_vel, max_vel)`` tuple
        - ``"variant_index"``: which variant to use in this section
        - ``"active"``: always ``True``
        Players not matched by any layer are omitted (they rest).
    """
    normalized = _normalize_section_name(section_name)
    section_def = SECTION_LAYERS.get(normalized, SECTION_LAYERS["verse"])
    section_density = section_def["density"]
    vel_range = section_def["vel_range"]
    layers = section_def["layers"]

    assigned: set[str] = set()
    active: list[dict[str, Any]] = []

    for layer in layers:
        for role_pattern, variant_override, density_override in layer:
            for player in players:
                pid = player["id"]
                if pid in assigned:
                    continue
                if _matches_pattern(pid, player["base_role"], role_pattern):
                    density = (
                        density_override
                        if density_override is not None
                        else section_density + player["variant"]["density_mod"]
                    )
                    density = max(0.0, min(1.0, density))
                    vi = (
                        variant_override
                        if variant_override is not None
                        else player["variant_index"]
                    )
                    active.append({
                        "player": player,
                        "density": density,
                        "vel_range": vel_range,
                        "variant_index": vi,
                        "active": True,
                    })
                    assigned.add(pid)

    return active


def compute_bus_topology(
    players: list[dict[str, Any]],
    genre: str,
) -> dict[str, list[str]]:
    """Compute which instruments feed into which buses.

    Uses the grouping strategy from :data:`genre_profiles.GROUPING_STRATEGY` to
    decide between instrument-type grouping and role-function grouping.

    Args:
        players: The expanded player list from :func:`expand_instruments`.
        genre: Genre name for grouping strategy.

    Returns:
        Dict mapping ``bus_name`` → list of player IDs.
        e.g. ``{"Guitars": ["rhythm_guitar_1", "rhythm_guitar_2", "lead_guitar_1"], ...}``
    """
    from audioshuttle.genre_profiles import (
        GROUPING_STRATEGY,
        INSTRUMENT_FAMILIES,
        ROLE_FUNCTION,
        GENRE_HIERARCHY,
    )

    resolved_genre = genre
    while resolved_genre not in GROUPING_STRATEGY:
        parent = GENRE_HIERARCHY.get(resolved_genre)
        if parent is None:
            break
        resolved_genre = parent

    strategy = GROUPING_STRATEGY.get(resolved_genre, "instrument_type")

    family_name_map: dict[str, str] = {}
    for family_name, members in INSTRUMENT_FAMILIES.items():
        for member in members:
            family_name_map[member] = family_name

    role_name_map: dict[str, str] = {}
    for role_func, members in ROLE_FUNCTION.items():
        for member in members:
            role_name_map[member] = role_func

    bus_players: dict[str, list[str]] = {}

    for player in players:
        role = player["base_role"]

        if strategy == "instrument_type":
            bus_key = family_name_map.get(role)
        else:
            bus_key = role_name_map.get(role)

        if bus_key is None:
            continue

        bus_display = bus_key.capitalize()
        bus_players.setdefault(bus_display, []).append(player["id"])

    buses: dict[str, list[str]] = {}
    for bus_name, pids in bus_players.items():
        if len(pids) >= 2:
            buses[bus_name] = pids

    buses["Submaster"] = [p["id"] for p in players]

    return buses
