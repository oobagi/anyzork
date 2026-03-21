"""Contract and alignment tests for presets and authoring (issue #14).

Catches contract drift in:
- Preset loading and normalization (built-in TOML presets)
- Prompt fingerprinting (current_prompt_system_version)
- Authoring bundle output (build_authoring_bundle)
"""

from __future__ import annotations

import re

import pytest

from anyzork.importer.prompt import current_prompt_system_version
from anyzork.services.authoring import build_authoring_bundle
from anyzork.wizard.presets import discover_presets, load_preset

# ---------------------------------------------------------------------------
# Preset contract constants
# ---------------------------------------------------------------------------

EXPECTED_BUILTIN_PRESETS = {"fantasy-dungeon", "mystery-mansion", "zombie-survival"}
REQUIRED_PRESET_KEYS = {"name", "description", "fields"}


# ---------------------------------------------------------------------------
# Preset contracts
# ---------------------------------------------------------------------------


class TestPresetDiscovery:
    """Built-in presets are discoverable and well-formed."""

    def test_discover_finds_all_builtin_presets(self) -> None:
        presets = discover_presets()
        assert EXPECTED_BUILTIN_PRESETS.issubset(presets.keys())

    def test_each_preset_has_required_keys(self) -> None:
        presets = discover_presets()
        for preset_id in EXPECTED_BUILTIN_PRESETS:
            preset = presets[preset_id]
            for key in REQUIRED_PRESET_KEYS:
                assert key in preset, f"{preset_id} missing key '{key}'"

    def test_each_preset_fields_include_world_description(self) -> None:
        presets = discover_presets()
        for preset_id in EXPECTED_BUILTIN_PRESETS:
            fields = presets[preset_id]["fields"]
            assert "world_description" in fields, (
                f"{preset_id} fields missing 'world_description'"
            )


class TestPresetNormalization:
    """Preset normalization flattens array-of-tables into plain lists."""

    def test_locations_normalized_to_string_list(self) -> None:
        fields = load_preset("fantasy-dungeon")
        assert fields is not None
        locations = fields.get("locations")
        assert isinstance(locations, list)
        assert all(isinstance(entry, str) for entry in locations)
        assert len(locations) > 0

    def test_characters_normalized_to_string_list(self) -> None:
        fields = load_preset("fantasy-dungeon")
        assert fields is not None
        characters = fields.get("characters")
        assert isinstance(characters, list)
        assert all(isinstance(entry, str) for entry in characters)

    def test_items_normalized_to_string_list(self) -> None:
        fields = load_preset("fantasy-dungeon")
        assert fields is not None
        items = fields.get("items")
        assert isinstance(items, list)
        assert all(isinstance(entry, str) for entry in items)


class TestListPresets:
    """list_presets equivalent — discover_presets returns all 3 built-ins."""

    def test_list_presets_returns_all_three(self) -> None:
        presets = discover_presets()
        assert len(presets) >= 3
        assert EXPECTED_BUILTIN_PRESETS & presets.keys() == EXPECTED_BUILTIN_PRESETS


class TestUserPresetDirectoryMissing:
    """User preset directory doesn't crash when missing."""

    def test_discover_presets_survives_missing_user_dir(self, monkeypatch) -> None:
        from pathlib import Path

        from anyzork.wizard import presets as presets_module

        monkeypatch.setattr(
            presets_module,
            "_user_presets_dir",
            lambda: Path("/nonexistent/anyzork/presets"),
        )
        # Should not raise; built-in presets still returned.
        presets = discover_presets()
        assert EXPECTED_BUILTIN_PRESETS.issubset(presets.keys())


# ---------------------------------------------------------------------------
# Prompt fingerprinting contracts
# ---------------------------------------------------------------------------


class TestPromptFingerprint:
    """current_prompt_system_version returns a stable fingerprint."""

    def test_fingerprint_matches_expected_pattern(self) -> None:
        version = current_prompt_system_version()
        assert re.fullmatch(r"ps-[0-9a-f]{12}", version), (
            f"Fingerprint '{version}' does not match ps-[0-9a-f]{{12}}"
        )

    def test_fingerprint_is_deterministic(self) -> None:
        # Clear the lru_cache to ensure fresh computation on first call.
        current_prompt_system_version.cache_clear()
        v1 = current_prompt_system_version()
        current_prompt_system_version.cache_clear()
        v2 = current_prompt_system_version()
        assert v1 == v2


# ---------------------------------------------------------------------------
# Authoring output contracts
# ---------------------------------------------------------------------------


class TestAuthoringBundleMinimal:
    """build_authoring_bundle with minimal input produces a valid bundle."""

    def test_minimal_bundle_is_valid(self) -> None:
        bundle = build_authoring_bundle(
            {"world_description": "A haunted lighthouse on a cliff."}
        )
        assert bundle.fields["world_description"] == "A haunted lighthouse on a cliff."
        assert bundle.preview_prompt
        assert bundle.authoring_prompt

    def test_realism_defaults_to_medium(self) -> None:
        bundle = build_authoring_bundle(
            {"world_description": "A haunted lighthouse on a cliff."}
        )
        assert bundle.realism == "medium"


class TestAuthoringBundleNormalization:
    """Field normalization within the authoring bundle."""

    def test_comma_separated_tone_becomes_list(self) -> None:
        bundle = build_authoring_bundle(
            {
                "world_description": "A haunted lighthouse on a cliff.",
                "tone": "dark, mysterious",
            }
        )
        assert bundle.fields["tone"] == ["dark", "mysterious"]

    def test_newline_separated_locations_becomes_list(self) -> None:
        bundle = build_authoring_bundle(
            {
                "world_description": "A haunted lighthouse on a cliff.",
                "locations": "Cliff path\nLantern room\nBasement",
            }
        )
        assert bundle.fields["locations"] == ["Cliff path", "Lantern room", "Basement"]


class TestAuthoringBundlePromptContent:
    """The generated prompts contain expected content."""

    def test_preview_prompt_contains_world_description(self) -> None:
        bundle = build_authoring_bundle(
            {"world_description": "A haunted lighthouse on a cliff."}
        )
        assert "A haunted lighthouse on a cliff." in bundle.preview_prompt

    def test_authoring_prompt_contains_zorkscript(self) -> None:
        bundle = build_authoring_bundle(
            {"world_description": "A haunted lighthouse on a cliff."}
        )
        assert "ZorkScript" in bundle.authoring_prompt


class TestAuthoringValidation:
    """Validation rejects bad input."""

    def test_missing_world_description_raises(self) -> None:
        with pytest.raises(ValueError, match="required"):
            build_authoring_bundle({})

    def test_short_world_description_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 5"):
            build_authoring_bundle({"world_description": "Hi"})


class TestPresetRoundTrip:
    """Each built-in preset produces a valid authoring bundle when fed through
    build_authoring_bundle (round-trip integration test)."""

    @pytest.mark.parametrize("preset_id", sorted(EXPECTED_BUILTIN_PRESETS))
    def test_preset_produces_valid_bundle(self, preset_id: str) -> None:
        fields = load_preset(preset_id)
        assert fields is not None, f"Preset '{preset_id}' failed to load"

        bundle = build_authoring_bundle(fields)

        assert bundle.fields.get("world_description"), (
            f"{preset_id}: world_description missing after normalization"
        )
        assert bundle.preview_prompt, f"{preset_id}: empty preview_prompt"
        assert "ZorkScript" in bundle.authoring_prompt, (
            f"{preset_id}: authoring_prompt missing ZorkScript"
        )
        assert bundle.realism in ("low", "medium", "high"), (
            f"{preset_id}: unexpected realism '{bundle.realism}'"
        )
