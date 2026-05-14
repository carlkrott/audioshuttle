import pytest
from audioshuttle.genre_profiles import (
    GENRE_PROFILES,
    INSTRUMENT_FAMILIES,
    FX_CHAINS,
    get_genre,
    get_family,
    get_fx_chain,
    get_tempo,
    validate_profile,
)


class TestGenreProfiles:
    def test_all_genres_have_required_fields(self):
        required_fields = ("tempo_range", "default_tempo", "sections", "instruments", "time_signature", "feel")
        for genre_name in GENRE_PROFILES:
            profile = GENRE_PROFILES[genre_name]
            for field in required_fields:
                assert field in profile, f"Genre '{genre_name}' missing field '{field}'"

    def test_default_tempo_in_range(self):
        for genre_name, profile in GENRE_PROFILES.items():
            tempo_range = profile["tempo_range"]
            default_tempo = profile["default_tempo"]
            assert tempo_range[0] <= default_tempo <= tempo_range[1], \
                f"Genre '{genre_name}': default_tempo {default_tempo} not in range {tempo_range}"

    def test_sections_valid(self):
        for genre_name, profile in GENRE_PROFILES.items():
            for section in profile["sections"]:
                assert isinstance(section["name"], str), f"Genre '{genre_name}': section name must be str"
                assert isinstance(section["bars"], int), f"Genre '{genre_name}': section bars must be int"
                assert section["bars"] > 0, f"Genre '{genre_name}': section bars must be > 0"

    def test_instruments_known(self):
        all_roles: set[str] = set()
        for family_roles in INSTRUMENT_FAMILIES.values():
            all_roles.update(family_roles)
        for genre_name, profile in GENRE_PROFILES.items():
            for instrument in profile["instruments"]:
                instrument_lower = instrument.lower()
                has_fx_chain = any(instrument_lower in roles for roles in INSTRUMENT_FAMILIES.values())
                assert instrument_lower in all_roles or has_fx_chain, \
                    f"Genre '{genre_name}': unknown instrument '{instrument}'"

    def test_get_genre_case_insensitive(self):
        rock_upper = get_genre("ROCK")
        rock_cap = get_genre("Rock")
        rock_lower = get_genre("rock")
        assert rock_upper == rock_cap == rock_lower

    def test_get_genre_fallback(self):
        result = get_genre("nonexistent_genre_xyz")
        assert result == GENRE_PROFILES["rock"]

    def test_get_family_known(self):
        assert get_family("lead_guitar") == "guitars"
        assert get_family("drums") == "percussion"
        assert get_family("pad") == "synths"
        assert get_family("vocals") == "vocals"

    def test_get_family_unknown(self):
        with pytest.raises(ValueError, match="Unknown instrument role"):
            get_family("bizarre_role")

    def test_get_fx_chain_genre_specific(self):
        chain = get_fx_chain("lead_guitar", "metal")
        fx_names = [fx["name"] for fx in chain]
        assert "ReaGate" in fx_names

    def test_get_fx_chain_fallback(self):
        chain = get_fx_chain("lead_guitar", "reggae")
        fx_names = [fx["name"] for fx in chain]
        assert "ReaGate" not in fx_names
        assert "ReaEQ" in fx_names

    def test_get_tempo_respects_user(self):
        assert get_tempo("rock", 140) == 140
        assert get_tempo("electronic", 100) == 100

    def test_get_tempo_defaults(self):
        assert get_tempo("rock") == 120
        assert get_tempo("electronic") == 128
        assert get_tempo(None) == 120

    def test_families_disjoint(self):
        all_roles: set[str] = set()
        for family, roles in INSTRUMENT_FAMILIES.items():
            for role in roles:
                assert role not in all_roles, f"Role '{role}' appears in multiple families"
                all_roles.add(role)

    def test_all_roles_have_family(self):
        covered_roles: set[str] = set()
        for roles in INSTRUMENT_FAMILIES.values():
            covered_roles.update(roles)
        for genre_name, profile in GENRE_PROFILES.items():
            for instrument in profile["instruments"]:
                assert instrument.lower() in covered_roles, \
                    f"Genre '{genre_name}': instrument '{instrument}' not covered by any family"