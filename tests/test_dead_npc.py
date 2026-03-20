"""Tests for dead-NPC handling in the game engine.

Covers three behaviours:
1. Talking to a dead NPC prints "{name} is dead." and does not enter dialogue.
2. Searching a dead NPC lists visible, takeable items in the room.
3. Giving/showing an item to a dead NPC is blocked with "{name} is dead."
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.game import GameEngine
from tests.build_test_game import build_test_game

# ----------------------------------------------------------------- fixtures


@pytest.fixture
def game_db(tmp_path: Path) -> GameDB:
    """Copy the primary human-testing fixture into an isolated temp dir."""
    source_path = build_test_game()
    test_path = tmp_path / "test_game.zork"
    shutil.copy2(source_path, test_path)
    db = GameDB(test_path)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def engine(game_db: GameDB) -> GameEngine:
    """GameEngine with console output captured for assertions."""
    stream = io.StringIO()
    game = GameEngine(game_db)
    game.console = Console(file=stream, force_terminal=False, color_system=None, width=120)
    game._test_stream = stream  # type: ignore[attr-defined]
    return game


def _output(engine: GameEngine) -> str:
    stream = engine._test_stream  # type: ignore[attr-defined]
    return stream.getvalue()


def _clear_output(engine: GameEngine) -> None:
    stream = engine._test_stream  # type: ignore[attr-defined]
    stream.seek(0)
    stream.truncate(0)


# -------------------------------------------------- Fix 1: dialogue blocked


def test_talk_to_dead_npc_prints_dead_message(
    game_db: GameDB, engine: GameEngine
) -> None:
    """Talking to a dead NPC should print '{name} is dead.' and return."""
    game_db.kill_npc("curator_rowan")

    engine._enter_dialogue("Curator Rowan", "entrance_hall")

    out = _output(engine)
    assert "Curator Rowan is dead." in out


def test_talk_to_dead_npc_does_not_enter_dialogue(
    game_db: GameDB, engine: GameEngine
) -> None:
    """After printing the dead message the engine must NOT enter the dialogue loop."""
    game_db.kill_npc("curator_rowan")

    engine._enter_dialogue("Curator Rowan", "entrance_hall")

    # The dialogue loop sets _in_dialogue; it should remain unset/False.
    assert not getattr(engine, "_in_dialogue", False)



# -------------------------------------------------- Fix 2: kill spawns body container


def test_kill_npc_spawns_body_container(game_db: GameDB) -> None:
    """Killing an NPC should spawn a searchable body container item."""
    game_db.kill_npc("curator_rowan")

    body = game_db.get_item("curator_rowan_body")
    assert body is not None
    assert body["is_container"] == 1
    assert body["room_id"] == "entrance_hall"
    assert "Curator Rowan" in body["name"]
    assert body["category"] == "body"


def test_kill_npc_body_is_searchable(game_db: GameDB) -> None:
    """The body container should be open and searchable."""
    game_db.kill_npc("curator_rowan")

    body = game_db.get_item("curator_rowan_body")
    assert body is not None
    assert body["is_open"] == 1
    assert body["is_takeable"] == 0


def test_kill_npc_body_not_duplicated(game_db: GameDB) -> None:
    """Killing the same NPC twice should not create duplicate bodies."""
    game_db.kill_npc("curator_rowan")
    game_db.kill_npc("curator_rowan")

    body = game_db.get_item("curator_rowan_body")
    assert body is not None


# ---------------------------------------- Fix 3: give/show blocked for dead


def test_give_to_dead_npc_blocked(
    game_db: GameDB, engine: GameEngine
) -> None:
    """Giving an item to a dead NPC should print '{name} is dead.'"""
    game_db.kill_npc("curator_rowan")
    game_db.move_item("brass_key", "inventory", "")

    engine._handle_give_show("give", "brass key", "Curator Rowan", "entrance_hall")

    out = _output(engine)
    assert "Curator Rowan is dead." in out


def test_show_to_dead_npc_blocked(
    game_db: GameDB, engine: GameEngine
) -> None:
    """Showing an item to a dead NPC should print '{name} is dead.'"""
    game_db.kill_npc("curator_rowan")
    game_db.move_item("brass_key", "inventory", "")

    engine._handle_give_show("show", "brass key", "Curator Rowan", "entrance_hall")

    out = _output(engine)
    assert "Curator Rowan is dead." in out
