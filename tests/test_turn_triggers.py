"""Contract tests for turn-based triggers: turn_count(N) and schedule_trigger.

Covers:
- ZorkScript parsing of turn_count event type
- ZorkScript parsing of scheduled event type
- ZorkScript parsing of schedule_trigger effect
- DB methods: schedule_trigger, get_due_scheduled_triggers, remove_scheduled_trigger
- Engine: turn_count triggers fire at the correct move
- Engine: schedule_trigger + scheduled trigger round-trip
- Full integration: schedule_trigger arms a deferred trigger that fires N moves later
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.commands import apply_effect
from anyzork.engine.game import GameEngine
from anyzork.importer import compile_import_spec
from anyzork.zorkscript import parse_zorkscript


def _turn_trigger_zorkscript() -> str:
    return """\
game {
  title "Turn Trigger Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start armory
}

room armory {
  name "Armory"
  description "A room full of weapons."
  short "The armory."
  start true
}

npc armory_guard {
  name "Armory Guard"
  description "A stern guard."
  examine "He watches you closely."
  in armory
  dialogue "Move along."
  category "character"
}

item lighter {
  name "Lighter"
  description "A silver lighter."
  examine "It has a flint wheel."
  in armory
  tags ["tool"]
  category "tool"
}

flag game_won "Victory"
flag bomb_armed "Bomb is armed"

# Turn count trigger: fires on move 3
when turn_count(3) {
  require has_flag(bomb_armed)
  effect set_flag(game_won)
  message "The bomb detonates on turn 3."
  once
}

# Command to arm the bomb
on "arm bomb" {
  effect set_flag(bomb_armed)
  success "You arm the bomb."
  once
}

# Command to light fuse (schedule_trigger)
on "light fuse" {
  require has_item(lighter)
  effect schedule_trigger(bomb_explodes, 2)
  success "The fuse is lit."
  once
}

# Scheduled trigger
when scheduled(bomb_explodes) {
  effect change_description(armory, "Rubble and smoke.")
  effect kill_npc(armory_guard)
  message "BOOM."
  once
}
"""


# ---- Parse tests ----


def test_parse_turn_count_trigger() -> None:
    """turn_count event type is parsed correctly from ZorkScript."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    triggers = spec["triggers"]
    tc_trigger = next(t for t in triggers if t["event_type"] == "turn_count")
    assert tc_trigger["event_data"]["n"] == "3"
    assert tc_trigger["one_shot"] is True


def test_parse_scheduled_trigger() -> None:
    """scheduled event type is parsed correctly from ZorkScript."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    triggers = spec["triggers"]
    sc_trigger = next(t for t in triggers if t["event_type"] == "scheduled")
    assert sc_trigger["event_data"]["trigger_id"] == "bomb_explodes"
    assert sc_trigger["one_shot"] is True


def test_parse_schedule_trigger_effect() -> None:
    """schedule_trigger effect is compiled correctly from ZorkScript."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    commands = spec["commands"]
    fuse_cmd = next(c for c in commands if c["pattern"] == "light fuse")
    effects = fuse_cmd["effects"]
    st_effect = next(e for e in effects if e["type"] == "schedule_trigger")
    assert st_effect["trigger"] == "bomb_explodes"
    assert st_effect["turns"] == 2


# ---- DB method tests ----


def test_schedule_trigger_db(tmp_path: Path) -> None:
    """schedule_trigger creates a row, get_due returns it at the right time."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    output_path = tmp_path / "sched_db.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        # Schedule for move 5
        db.schedule_trigger("bomb_explodes", 5)

        # Not due yet at move 3
        assert db.get_due_scheduled_triggers(3) == []

        # Due at move 5
        due = db.get_due_scheduled_triggers(5)
        assert len(due) == 1
        assert due[0]["trigger_id"] == "bomb_explodes"
        assert due[0]["fire_on_move"] == 5

        # Also due at move 6 (>= check)
        due = db.get_due_scheduled_triggers(6)
        assert len(due) == 1

        # Remove it
        db.remove_scheduled_trigger("bomb_explodes")
        assert db.get_due_scheduled_triggers(10) == []


def test_schedule_trigger_reschedule(tmp_path: Path) -> None:
    """Rescheduling overwrites the previous deadline."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    output_path = tmp_path / "sched_resched.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.schedule_trigger("bomb_explodes", 5)
        db.schedule_trigger("bomb_explodes", 10)

        assert db.get_due_scheduled_triggers(5) == []
        due = db.get_due_scheduled_triggers(10)
        assert len(due) == 1
        assert due[0]["fire_on_move"] == 10


# ---- Engine effect tests ----


def test_schedule_trigger_effect(tmp_path: Path) -> None:
    """schedule_trigger effect creates the scheduled_triggers row."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    output_path = tmp_path / "sched_eff.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("armory")
        # Player is at move 0; fire_on_move = 0 + 1 + 3 = 4
        # (the +1 accounts for the tick that hasn't happened yet)
        apply_effect(
            {"type": "schedule_trigger", "trigger": "bomb_explodes", "turns": 3},
            db,
        )
        due = db.get_due_scheduled_triggers(4)
        assert len(due) == 1
        assert due[0]["trigger_id"] == "bomb_explodes"
        assert due[0]["fire_on_move"] == 4


# ---- Full integration tests ----


def _make_engine(zork_path: Path) -> tuple[GameEngine, Console]:
    """Create a non-interactive GameEngine for testing."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    db = GameDB(zork_path)
    engine = GameEngine(db, console=console, interactive_dialogue=False)
    engine.initialize_session()
    return engine, console


def _get_output(console: Console) -> str:
    """Extract text output from a Console with a StringIO file, stripping ANSI codes."""
    import re

    raw = console.file.getvalue()  # type: ignore[union-attr]
    return re.sub(r"\x1b\[[0-9;]*m", "", raw)


def test_turn_count_trigger_fires_at_correct_move(tmp_path: Path) -> None:
    """turn_count(3) trigger fires exactly on move 3 when preconditions are met."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    output_path = tmp_path / "tc_integration.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Arm the bomb first (move 1)
    engine.process_command("arm bomb")
    assert engine.db.has_flag("bomb_armed")

    # Move 2: nothing happens yet
    engine.process_command("look")
    assert not engine.db.has_flag("game_won")

    # Move 3: turn_count(3) should fire
    engine.process_command("look")
    assert engine.db.has_flag("game_won")
    output = _get_output(console)
    assert "detonates on turn 3" in output


def test_turn_count_trigger_skipped_without_precondition(tmp_path: Path) -> None:
    """turn_count trigger does not fire when preconditions fail."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    output_path = tmp_path / "tc_skip.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # Do NOT arm the bomb
    # Move through turns 1, 2, 3
    engine.process_command("look")
    engine.process_command("look")
    engine.process_command("look")

    # turn_count(3) should not have fired because bomb_armed is not set
    assert not engine.db.has_flag("game_won")


def test_scheduled_trigger_fires_after_delay(tmp_path: Path) -> None:
    """schedule_trigger + scheduled trigger fires after the correct number of moves."""
    spec = parse_zorkscript(_turn_trigger_zorkscript())
    output_path = tmp_path / "sched_integration.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Take the lighter first (need it for the fuse command)
    engine.process_command("take lighter")
    assert any(i["id"] == "lighter" for i in engine.db.get_inventory())

    # Light the fuse (schedules bomb_explodes for current_move + 2)
    engine.process_command("light fuse")
    output = _get_output(console)
    assert "fuse is lit" in output

    # Verify the guard is alive
    guard = engine.db.get_npc("armory_guard")
    assert guard is not None
    assert guard["is_alive"]

    # One more move -- not yet
    engine.process_command("look")
    guard = engine.db.get_npc("armory_guard")
    assert guard is not None
    assert guard["is_alive"]

    # This move should trigger the bomb
    engine.process_command("look")
    guard = engine.db.get_npc("armory_guard")
    assert guard is not None
    assert not guard["is_alive"]

    output = _get_output(console)
    assert "BOOM" in output


def test_turn_count_one_shot_only_fires_once(tmp_path: Path) -> None:
    """A one-shot turn_count trigger does not fire again on subsequent turns."""
    # Use a non-one-shot variant to test it fires, then it shouldn't re-fire
    src = """\
game {
  title "One-Shot Test"
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

when turn_count(2) {
  effect set_flag(done)
  message "Fired."
  once
}
"""
    spec = parse_zorkscript(src)
    output_path = tmp_path / "tc_oneshot.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # Move 1: not yet
    engine.process_command("look")
    assert not engine.db.has_flag("done")

    # Move 2: fires
    engine.process_command("look")
    assert engine.db.has_flag("done")

    # Clear the flag manually and check it doesn't re-fire
    engine.db.clear_flag("done")
    engine.process_command("look")
    assert not engine.db.has_flag("done")
