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
                "region": "house",
                "is_start": True,
            },
            {
                "id": "study",
                "name": "Study",
                "description": "A cramped study.",
                "region": "house",
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
  region "house"
  start true

  exit north -> study
}

room study {
  name "Study"
  description "A cramped study."
  short "A cramped study."
  region "house"

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


def assert_has_error(messages: list, needle: str) -> None:
    text = "\n".join(str(message) for message in messages)
    assert needle in text
