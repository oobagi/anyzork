"""Alignment regression tests for the generate/import pipeline.

These tests verify that the ZorkScript authoring prompt, the ZorkScript parser,
the importer, and the validator all agree on vocabulary (effect names, trigger
event types, precondition types) and that the canonical example embedded in the
prompt survives the full parse -> import -> validate round-trip.
"""

from __future__ import annotations

import re
from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.importer import ZORKSCRIPT_AUTHORING_TEMPLATE, compile_import_spec
from anyzork.validation import (
    VALID_EFFECT_TYPES,
    VALID_TRIGGER_EVENT_TYPES,
    validate_game,
)
from anyzork.zorkscript import parse_zorkscript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_example_zorkscript() -> str:
    """Extract the ZorkScript example between the marker lines in the prompt."""
    start_marker = "--- EXAMPLE:"
    end_marker = "--- END EXAMPLE ---"
    start = ZORKSCRIPT_AUTHORING_TEMPLATE.index(start_marker)
    end = ZORKSCRIPT_AUTHORING_TEMPLATE.index(end_marker)
    # Skip the marker line itself
    body_start = ZORKSCRIPT_AUTHORING_TEMPLATE.index("\n", start) + 1
    return ZORKSCRIPT_AUTHORING_TEMPLATE[body_start:end].strip()


def _parse_import_validate(zorkscript: str, tmp_path: Path) -> list:
    """Parse ZorkScript, import into a temp .zork file, and return validation errors."""
    spec = parse_zorkscript(zorkscript)
    output_path = tmp_path / "test_game.zork"
    compiled_path, _warnings = compile_import_spec(spec, output_path)
    with GameDB(compiled_path) as db:
        return validate_game(db)


def _extract_prompt_effects() -> set[str]:
    """Extract standard effect names taught in the prompt's Available effects block."""
    # Match the block starting with "# Available effects" or similar
    block_match = re.search(
        r"# Available effects.*?\n((?:#.*\n)*)",
        ZORKSCRIPT_AUTHORING_TEMPLATE,
    )
    assert block_match is not None, "Could not find Available effects block in prompt"
    block = block_match.group(1)
    # Extract effect names from lines like "#   set_flag(id)  -- ..."
    return set(re.findall(r"#\s+(\w+)\(", block))


def _extract_prompt_interaction_effects() -> set[str]:
    """Extract target-aware effect names taught in the interaction section."""
    # Match the block starting with "# Effects for interactions"
    block_match = re.search(
        r"# Effects for interactions.*?\n((?:#.*\n)*)",
        ZORKSCRIPT_AUTHORING_TEMPLATE,
    )
    assert block_match is not None, "Could not find interaction effects block in prompt"
    block = block_match.group(1)
    return set(re.findall(r"#\s+(\w+)\(", block))


def _extract_prompt_trigger_types() -> set[str]:
    """Extract trigger event types taught in the prompt."""
    block_match = re.search(
        r"# ONLY these \d+ event types exist.*?\n((?:#.*\n)*)",
        ZORKSCRIPT_AUTHORING_TEMPLATE,
    )
    assert block_match is not None, "Could not find trigger event types block in prompt"
    block = block_match.group(1)
    return set(re.findall(r"#\s+(\w+)\(", block))


# ---------------------------------------------------------------------------
# D1: Prompt example imports successfully
# ---------------------------------------------------------------------------


class TestPromptExampleRoundTrip:
    """The canonical ZorkScript example in the authoring prompt must survive
    the full parse -> import -> validate pipeline without errors."""

    def test_prompt_example_parses(self) -> None:
        source = _extract_example_zorkscript()
        spec = parse_zorkscript(source)
        assert spec["game"]["title"] == "The Silver Key"
        assert len(spec["rooms"]) > 0

    def test_prompt_example_imports_and_validates(self, tmp_path: Path) -> None:
        source = _extract_example_zorkscript()
        results = _parse_import_validate(source, tmp_path)
        errors = [r for r in results if r.severity == "error"]
        assert errors == [], (
            "Prompt example produced validation errors:\n"
            + "\n".join(f"  - {e.message}" for e in errors)
        )


# ---------------------------------------------------------------------------
# D2: Vocabulary alignment tests
# ---------------------------------------------------------------------------


class TestEffectNameAlignment:
    """Effect names taught in the prompt must be recognized by the validator
    and the parser."""

    def test_prompt_standard_effects_subset_of_valid_effect_types(self) -> None:
        prompt_effects = _extract_prompt_effects()
        # Standard effects taught in the prompt should all be in VALID_EFFECT_TYPES
        unknown = prompt_effects - VALID_EFFECT_TYPES
        assert unknown == set(), (
            f"Prompt teaches effect(s) not in VALID_EFFECT_TYPES: {unknown}"
        )

    def test_prompt_standard_effects_subset_of_parser(self) -> None:
        from anyzork.zorkscript import _Parser

        prompt_effects = _extract_prompt_effects()
        parser_effects = set(_Parser._EFFECT_ARGS.keys())
        unknown = prompt_effects - parser_effects
        assert unknown == set(), (
            f"Prompt teaches effect(s) not in parser _EFFECT_ARGS: {unknown}"
        )

    def test_prompt_interaction_effects_in_parser(self) -> None:
        from anyzork.zorkscript import _Parser

        interaction_effects = _extract_prompt_interaction_effects()
        parser_effects = set(_Parser._EFFECT_ARGS.keys())
        # Target-aware effects should be in parser (they are separate from VALID_EFFECT_TYPES)
        unknown = interaction_effects - parser_effects
        assert unknown == set(), (
            f"Prompt teaches interaction effect(s) not in parser: {unknown}"
        )

    def test_valid_effect_types_subset_of_parser(self) -> None:
        from anyzork.zorkscript import _Parser

        parser_effects = set(_Parser._EFFECT_ARGS.keys())
        unknown = VALID_EFFECT_TYPES - parser_effects
        assert unknown == set(), (
            f"VALID_EFFECT_TYPES has entries not in parser _EFFECT_ARGS: {unknown}"
        )


class TestTriggerEventTypeAlignment:
    """Trigger event types taught in the prompt must match
    VALID_TRIGGER_EVENT_TYPES exactly."""

    def test_prompt_trigger_types_match_validator(self) -> None:
        prompt_types = _extract_prompt_trigger_types()
        assert prompt_types == VALID_TRIGGER_EVENT_TYPES, (
            f"Prompt trigger types {prompt_types} != "
            f"VALID_TRIGGER_EVENT_TYPES {VALID_TRIGGER_EVENT_TYPES}"
        )


# ---------------------------------------------------------------------------
# D3: Normalization tests
# ---------------------------------------------------------------------------


class TestQuestIdNormalization:
    """Quest IDs with main:/side: prefixes normalize correctly through the
    pipeline. Effect references use the bare quest ID."""

    def test_side_quest_with_discover_effect(self, tmp_path: Path) -> None:
        source = """\
game {
  title "Quest Normalization Test"
  author "Test."
  max_score 0
  win [game_won]
}

player {
  start foyer
}

room foyer {
  name "Foyer"
  description "A quiet foyer."
  short "A quiet foyer."

  start true
}

flag game_won "Win flag."
flag quest_active "Quest discovered."
flag clue_found "Found the clue."

quest side:test_quest {
  name "Test Quest"
  description "A test quest."
  completion quest_active
  discovery clue_found
  score 0

  objective "Find the clue" -> clue_found
}

on "win game" in [foyer] {
  effect set_flag(game_won)
  success "You win."
}

when flag_set(clue_found) {
  effect discover_quest(test_quest)
  message "Quest discovered."
  once
}
"""
        results = _parse_import_validate(source, tmp_path)
        errors = [r for r in results if r.severity == "error"]
        assert errors == [], (
            "Quest normalization failed:\n"
            + "\n".join(f"  - {e.message}" for e in errors)
        )


class TestDelayedSpawnItem:
    """Items declared without a location can be spawned later via
    spawn_item(item_id, room_id) in a trigger."""

    def test_spawn_item_for_locationless_item(self, tmp_path: Path) -> None:
        source = """\
game {
  title "Spawn Test"
  author "Test."
  max_score 0
  win [game_won]
}

player {
  start foyer
}

room foyer {
  name "Foyer"
  description "A quiet foyer."
  short "A quiet foyer."

  start true

  exit north -> garden
}

room garden {
  name "Garden"
  description "A sunny garden."
  short "A sunny garden."


  exit south -> foyer
}

flag game_won "Win flag."
flag entered_garden "Player entered garden."

item magic_gem {
  name "Magic Gem"
  description "A shimmering gem."
  takeable true
}

on "win game" in [foyer, garden] {
  effect set_flag(game_won)
  success "You win."
}

when room_enter(garden) {
  require not_flag(entered_garden)

  effect set_flag(entered_garden)
  effect spawn_item(magic_gem, garden)

  message "A gem materializes on the ground."
  once
}
"""
        results = _parse_import_validate(source, tmp_path)
        errors = [r for r in results if r.severity == "error"]
        assert errors == [], (
            "Delayed spawn item failed:\n"
            + "\n".join(f"  - {e.message}" for e in errors)
        )


class TestDialogueNodeTriggerReference:
    """Nested NPC talk blocks compile to dialogue node IDs of the form
    {npc_id}_{label}. Triggers using dialogue_node() must reference the
    compiled ID."""

    def test_dialogue_node_trigger(self, tmp_path: Path) -> None:
        source = """\
game {
  title "Dialogue Trigger Test"
  author "Test."
  max_score 0
  win [game_won]
}

player {
  start tavern
}

room tavern {
  name "Tavern"
  description "A smoky tavern."
  short "A smoky tavern."

  start true
}

flag game_won "Win flag."
flag secret_revealed "The barkeep told a secret."

npc barkeep {
  name "The Barkeep"
  description "A grizzled barkeep."
  in tavern
  dialogue "He polishes a glass."
  category "character"

  talk root {
    "What'll it be?"
    option "Tell me a secret." -> secret
    option "Nothing."
  }

  talk secret {
    "He leans in close. 'The cellar hides a passage.'"
    sets [secret_revealed]
  }
}

when dialogue_node(barkeep_secret) {
  effect set_flag(game_won)
  message "You now know the way out."
  once
}
"""
        results = _parse_import_validate(source, tmp_path)
        errors = [r for r in results if r.severity == "error"]
        assert errors == [], (
            "Dialogue node trigger reference failed:\n"
            + "\n".join(f"  - {e.message}" for e in errors)
        )
