from __future__ import annotations

from pathlib import Path

import pytest

from anyzork.importer import IMPORT_SPEC_FORMAT, compile_import_spec


@pytest.fixture
def minimal_import_spec() -> dict:
    return {
        "format": IMPORT_SPEC_FORMAT,
        "game": {
            "title": "Fixture Game",
            "author_prompt": "A compact fixture world.",
            "intro_text": "You arrive.",
            "realism": "medium",
            "win_conditions": ["game_won"],
        },
        "player": {"start_room_id": "foyer"},
        "rooms": [
            {
                "id": "foyer",
                "name": "Foyer",
                "description": "A quiet foyer.",

                "is_start": True,
            },
            {
                "id": "study",
                "name": "Study",
                "description": "A cramped study.",

            },
        ],
        "exits": [
            {
                "id": "foyer_study",
                "from_room_id": "foyer",
                "to_room_id": "study",
                "direction": "north",
            },
            {
                "id": "study_foyer",
                "from_room_id": "study",
                "to_room_id": "foyer",
                "direction": "south",
            },
        ],
        "items": [],
        "npcs": [],
        "dialogue_nodes": [],
        "dialogue_options": [],
        "locks": [],
        "puzzles": [],
        "flags": [{"id": "game_won", "value": False, "description": "Win flag"}],
        "interactions": [],
        "commands": [
            {
                "id": "win_game",
                "verb": "win",
                "pattern": "win game",
                "preconditions": [],
                "effects": [{"type": "set_flag", "flag": "game_won", "value": True}],
                "success_message": "You win.",
                "failure_message": "",
            }
        ],
        "quests": [],
        "interaction_responses": [],
        "triggers": [],
    }


@pytest.fixture
def minimal_zorkscript() -> str:
    return """\
game {
  title "CLI Import Game"
  author "Imported through the CLI."
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

  exit north -> study
}

room study {
  name "Study"
  description "A cramped study."
  short "A cramped study."


  exit south -> foyer
}

flag game_won "Tracks victory."

on "win game" in [foyer, study] {
  effect set_flag(game_won)
  success "You win."
}
"""


@pytest.fixture
def compiled_game_path(tmp_path: Path, minimal_import_spec: dict) -> Path:
    output_path = tmp_path / "fixture_game.zork"
    compiled_path, _warnings = compile_import_spec(minimal_import_spec, output_path)
    return compiled_path


@pytest.fixture
def dialogue_game_path(tmp_path: Path, minimal_import_spec: dict) -> Path:
    dialogue_spec = {
        **minimal_import_spec,
        "npcs": [
            {
                "id": "caretaker",
                "name": "Caretaker",
                "description": "An old caretaker watches over the foyer.",
                "room_id": "foyer",
                "default_dialogue": "He nods politely.",
            }
        ],
        "dialogue_nodes": [
            {
                "id": "caretaker_root",
                "npc_id": "caretaker",
                "content": '"State your business," the caretaker says.',
                "is_root": True,
            },
            {
                "id": "caretaker_riddle",
                "npc_id": "caretaker",
                "content": '"Then answer me this: what do travelers seek?"',
            },
        ],
        "dialogue_options": [
            {
                "id": "caretaker_root_question",
                "node_id": "caretaker_root",
                "text": "Ask what he guards.",
                "next_node_id": "caretaker_riddle",
                "sort_order": 1,
            },
            {
                "id": "caretaker_root_leave",
                "node_id": "caretaker_root",
                "text": "Decide this can wait.",
                "next_node_id": None,
                "sort_order": 2,
            },
            {
                "id": "caretaker_answer",
                "node_id": "caretaker_riddle",
                "text": "Shelter.",
                "next_node_id": None,
                "set_flags": ["game_won"],
                "sort_order": 1,
            },
        ],
    }
    output_path = tmp_path / "dialogue_fixture_game.zork"
    compiled_path, _warnings = compile_import_spec(dialogue_spec, output_path)
    return compiled_path


@pytest.fixture
def dialogue_effects_game_path(tmp_path: Path, minimal_import_spec: dict) -> Path:
    """A game where an NPC gives an item via dialogue effects."""
    spec = {
        **minimal_import_spec,
        "items": [
            {
                "id": "magic_ring",
                "name": "Magic Ring",
                "description": "A glowing ring.",
                "examine_description": "It hums with power.",
                "is_takeable": True,
                "is_visible": False,
            },
        ],
        "npcs": [
            {
                "id": "barkeep",
                "name": "Barkeep",
                "description": "A friendly barkeep.",
                "room_id": "foyer",
                "default_dialogue": "What'll it be?",
            }
        ],
        "dialogue_nodes": [
            {
                "id": "barkeep_root",
                "npc_id": "barkeep",
                "content": "Welcome, traveler! Take this ring.",
                "effects": [
                    {"type": "spawn_item", "item": "magic_ring", "location": "_inventory"},
                    {"type": "add_score", "points": 5},
                ],
                "set_flags": ["received_ring"],
                "is_root": True,
            },
        ],
        "dialogue_options": [
            {
                "id": "barkeep_root_opt_0",
                "node_id": "barkeep_root",
                "text": "Thanks!",
                "next_node_id": None,
                "sort_order": 0,
            },
        ],
        "flags": [
            *minimal_import_spec["flags"],
            {"id": "received_ring", "value": False, "description": "Got the ring"},
        ],
    }
    output_path = tmp_path / "dialogue_effects_game.zork"
    compiled_path, _warnings = compile_import_spec(spec, output_path)
    return compiled_path


@pytest.fixture
def zork_archive_path(tmp_path: Path, minimal_zorkscript: str) -> Path:
    """Create a .zork zip archive from a minimal project."""
    from anyzork.archive import pack_project

    project_dir = tmp_path / "fixture_project"
    project_dir.mkdir()
    (project_dir / "manifest.toml").write_text(
        '[project]\n'
        'title = "Fixture Game"\n'
        'slug = "fixture-game"\n'
        'author = ""\n'
        'description = ""\n'
        'tags = []\n'
        '\n'
        '[source]\n'
        'files = ["game.zorkscript"]\n',
        encoding="utf-8",
    )
    (project_dir / "game.zorkscript").write_text(minimal_zorkscript, encoding="utf-8")
    return pack_project(project_dir, tmp_path / "fixture_game.zork")


def assert_has_error(messages: list, needle: str) -> None:
    text = "\n".join(str(message) for message in messages)
    assert needle in text
