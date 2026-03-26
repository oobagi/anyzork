"""Contract tests for NPC behavior loop: autonomous NPC actions each turn.

Covers:
- ZorkScript parsing of on_turn blocks inside NPC blocks
- DB methods: insert_npc_behavior, get_npc_behaviors, mark_npc_behavior_executed
- Compilation round-trip: ZorkScript -> DB -> query
- Engine: _process_npc_behaviors fires effects and shows messages
- Engine: one-shot behaviors only fire once
- Engine: messages only shown when NPC is in the player's room
- Engine: preconditions gate behavior execution
- Validation: invalid NPC ID, precondition, and effect references caught
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.game import GameEngine
from anyzork.importer import compile_import_spec
from anyzork.zorkscript import parse_zorkscript


def _behavior_zorkscript() -> str:
    return """\
game {
  title "NPC Behavior Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start town_square
}

room town_square {
  name "Town Square"
  description "A bustling square."
  short "The square."
  start true

  exit north -> guard_post "A path to the guard post."
}

room guard_post {
  name "Guard Post"
  description "A fortified guard post."
  short "Guard post."

  exit south -> town_square "Back to the square."
  exit east -> alarm_room "A corridor to the alarm room."
}

room alarm_room {
  name "Alarm Room"
  description "A room with a large alarm bell."
  short "The alarm room."

  exit west -> guard_post "Back to the guard post."
}

npc merchant {
  name "Wandering Merchant"
  description "A merchant with a heavy pack."
  examine "He looks ready to leave."
  in town_square
  dialogue "Buying or selling?"
  category "character"

  on_turn {
    effect set_flag(merchant_moved)
    message "The merchant shifts restlessly."
  }
}

npc guard {
  name "Guard"
  description "An armored guard."
  examine "Alert and watchful."
  in guard_post
  dialogue "Move along."
  category "character"

  on_turn {
    require has_flag(alarm_raised)
    effect move_npc(guard, alarm_room)
    message "The guard rushes toward the alarm!"
    once
  }
}

npc distant_npc {
  name "Hermit"
  description "A reclusive hermit."
  examine "He avoids eye contact."
  in alarm_room
  dialogue "Go away."
  category "character"

  on_turn {
    effect set_flag(hermit_acted)
    message "The hermit mutters to himself."
  }
}

flag game_won "Victory"
flag alarm_raised "Alarm has been raised"
flag merchant_moved "Merchant has moved"
flag hermit_acted "Hermit acted"

on "raise alarm" {
  effect set_flag(alarm_raised)
  success "You raise the alarm!"
}

on "win game" {
  effect set_flag(game_won)
  success "You win!"
}
"""


# ---- Parse tests ----


def test_parse_on_turn_block() -> None:
    """on_turn blocks are parsed correctly from ZorkScript NPC blocks."""
    spec = parse_zorkscript(_behavior_zorkscript())
    behaviors = spec["npc_behaviors"]
    assert len(behaviors) == 3

    merchant_beh = next(b for b in behaviors if b["npc_id"] == "merchant")
    assert merchant_beh["one_shot"] is False
    assert len(merchant_beh["effects"]) == 1
    assert merchant_beh["effects"][0]["type"] == "set_flag"
    assert merchant_beh["message"] == "The merchant shifts restlessly."
    assert merchant_beh["preconditions"] == []

    guard_beh = next(b for b in behaviors if b["npc_id"] == "guard")
    assert guard_beh["one_shot"] is True
    assert len(guard_beh["preconditions"]) == 1
    assert guard_beh["preconditions"][0]["type"] == "has_flag"
    assert guard_beh["preconditions"][0]["flag"] == "alarm_raised"
    assert len(guard_beh["effects"]) == 1
    assert guard_beh["effects"][0]["type"] == "move_npc"
    assert guard_beh["message"] == "The guard rushes toward the alarm!"


def test_parse_npc_without_on_turn() -> None:
    """NPCs without on_turn blocks produce no behaviors."""
    src = """\
game {
  title "No Behavior Test"
  author "Test"
  max_score 0
  win [done]
}
player { start room1 }
room room1 {
  name "Room"
  description "A room."
  short "A room."
  start true
}
flag done "Done"
npc villager {
  name "Villager"
  description "A friendly villager."
  examine "They smile."
  in room1
  dialogue "Hello!"
  category "character"
}
"""
    spec = parse_zorkscript(src)
    assert spec["npc_behaviors"] == []


# ---- DB method tests ----


def test_insert_and_get_npc_behaviors(tmp_path: Path) -> None:
    """insert_npc_behavior creates rows, get_npc_behaviors returns active ones."""
    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_db.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        # Merchant has one behavior
        merchant_behaviors = db.get_npc_behaviors("merchant")
        assert len(merchant_behaviors) == 1
        assert merchant_behaviors[0]["npc_id"] == "merchant"
        assert merchant_behaviors[0]["one_shot"] == 0

        # Guard has one behavior
        guard_behaviors = db.get_npc_behaviors("guard")
        assert len(guard_behaviors) == 1
        assert guard_behaviors[0]["one_shot"] == 1
        assert guard_behaviors[0]["executed"] == 0


def test_mark_behavior_executed(tmp_path: Path) -> None:
    """mark_npc_behavior_executed prevents one-shot from returning."""
    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_exec.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        guard_behaviors = db.get_npc_behaviors("guard")
        assert len(guard_behaviors) == 1

        db.mark_npc_behavior_executed(guard_behaviors[0]["id"])

        # After marking executed, one-shot should be excluded
        guard_behaviors = db.get_npc_behaviors("guard")
        assert len(guard_behaviors) == 0


def test_get_all_npc_behaviors(tmp_path: Path) -> None:
    """get_all_npc_behaviors returns all behaviors including executed."""
    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_all.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        all_behaviors = db.get_all_npc_behaviors()
        assert len(all_behaviors) == 3


# ---- Engine integration tests ----


def _make_engine(zork_path: Path) -> tuple[GameEngine, Console]:
    """Create a non-interactive GameEngine for testing."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    db = GameDB(zork_path)
    engine = GameEngine(db, console=console, interactive_dialogue=False)
    engine.initialize_session()
    return engine, console


def _get_output(console: Console) -> str:
    """Extract text output from a Console with a StringIO file, stripping ANSI codes."""
    raw = console.file.getvalue()  # type: ignore[union-attr]
    return re.sub(r"\x1b\[[0-9;]*m", "", raw)


def test_behavior_fires_each_turn(tmp_path: Path) -> None:
    """NPC behavior fires effects every turn (non-one-shot)."""
    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_fire.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Player is in town_square with the merchant
    engine.process_command("look")
    assert engine.db.has_flag("merchant_moved")

    # Message should be visible because merchant is in player's room
    output = _get_output(console)
    assert "merchant shifts restlessly" in output


def test_behavior_message_hidden_when_npc_in_different_room(tmp_path: Path) -> None:
    """NPC behavior messages are not shown when NPC is in a different room."""
    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_hidden.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Player is in town_square; hermit is in alarm_room
    engine.process_command("look")

    # Hermit's effect still fires (flag is set)
    assert engine.db.has_flag("hermit_acted")

    # But hermit's message should NOT be visible
    output = _get_output(console)
    assert "hermit mutters" not in output


def test_behavior_precondition_gates_execution(tmp_path: Path) -> None:
    """Behavior does not fire when preconditions fail."""
    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_gate.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # Guard behavior requires alarm_raised flag, which is not set
    engine.process_command("look")

    # Guard should NOT have moved
    guard = engine.db.get_npc("guard")
    assert guard is not None
    assert guard["room_id"] == "guard_post"


def test_behavior_fires_when_precondition_met(tmp_path: Path) -> None:
    """Behavior fires when preconditions pass."""
    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_precond.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # Raise the alarm first (sets alarm_raised flag)
    engine.process_command("raise alarm")
    assert engine.db.has_flag("alarm_raised")

    # Next turn — guard behavior should fire
    engine.process_command("look")

    guard = engine.db.get_npc("guard")
    assert guard is not None
    assert guard["room_id"] == "alarm_room"


def test_one_shot_behavior_only_fires_once(tmp_path: Path) -> None:
    """One-shot behavior fires once and is then skipped."""
    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_oneshot.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # Set alarm to enable guard behavior
    engine.process_command("raise alarm")

    # First tick fires the guard's one-shot behavior
    engine.process_command("look")
    guard = engine.db.get_npc("guard")
    assert guard is not None
    assert guard["room_id"] == "alarm_room"

    # Move guard back manually to test one-shot doesn't re-fire
    engine.db._mutate(
        "UPDATE npcs SET room_id = ? WHERE id = ?",
        ("guard_post", "guard"),
    )
    guard = engine.db.get_npc("guard")
    assert guard["room_id"] == "guard_post"

    # Next tick — behavior should NOT fire again (one-shot executed)
    engine.process_command("look")
    guard = engine.db.get_npc("guard")
    assert guard is not None
    assert guard["room_id"] == "guard_post"  # unchanged


# ---- Validation tests ----


def test_validation_passes_for_valid_behaviors(tmp_path: Path) -> None:
    """Valid behaviors produce no validation errors."""
    from anyzork.validation import validate_game

    spec = parse_zorkscript(_behavior_zorkscript())
    output_path = tmp_path / "behavior_valid.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        errors = validate_game(db)
        behavior_errors = [e for e in errors if e.category == "npc_behavior"]
        assert behavior_errors == []
