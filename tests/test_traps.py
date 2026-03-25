from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.game import GameEngine
from anyzork.importer import compile_import_spec
from anyzork.zorkscript import parse_zorkscript


def _minimal_trap_zorkscript() -> str:
    return """\
game {
  title "Trap Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start corridor
}

room corridor {
  name "Corridor"
  description "A dark corridor."
  short "A dark corridor."
  start true
}

flag game_won "Victory"
flag spike_pit_disarmed "Spike pit disarmed"
flag spike_pit_triggered "Spike pit triggered"

command win_game {
  verb win
  pattern "win game"
  effect set_flag(game_won)
  success "You win."
}

trap spike_pit {
  on       room_enter
  when     room_id = corridor
  disarm   spike_pit_disarmed

  require not_flag(spike_pit_disarmed)

  effect set_flag(spike_pit_triggered)

  message "The floor gives way beneath you!"
  once
}
"""


def test_parse_trap_block() -> None:
    spec = parse_zorkscript(_minimal_trap_zorkscript())
    triggers = spec["triggers"]
    assert len(triggers) == 1

    trap = triggers[0]
    assert trap["id"] == "spike_pit"
    assert trap["event_type"] == "room_enter"
    assert trap["event_data"] == {"room_id": "corridor"}
    assert trap["disarm_flag"] == "spike_pit_disarmed"
    assert trap["one_shot"] is True
    assert trap["message"] == "The floor gives way beneath you!"
    assert len(trap["preconditions"]) == 1
    assert trap["preconditions"][0]["type"] == "not_flag"
    assert len(trap["effects"]) == 1
    assert trap["effects"][0]["type"] == "set_flag"


def test_trap_compiles_to_db(tmp_path: Path) -> None:
    spec = parse_zorkscript(_minimal_trap_zorkscript())
    output_path = tmp_path / "trap_test.zork"
    compiled_path, _warnings = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        triggers = db.get_triggers_for_event("room_enter")
        assert len(triggers) >= 1
        trap = next(t for t in triggers if t["id"] == "spike_pit")
        assert trap["disarm_flag"] == "spike_pit_disarmed"
        assert trap["one_shot"] == 1
        assert trap["message"] == "The floor gives way beneath you!"


def test_trap_disarm_flag_skips_trigger(tmp_path: Path) -> None:
    spec = parse_zorkscript(_minimal_trap_zorkscript())
    output_path = tmp_path / "disarm_test.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        # Set the disarm flag
        db.set_flag("spike_pit_disarmed", "true")
        assert db.has_flag("spike_pit_disarmed")

        # Get triggers - the trap should still be in the DB
        triggers = db.get_triggers_for_event("room_enter")
        trap = next(t for t in triggers if t["id"] == "spike_pit")
        assert trap["disarm_flag"] == "spike_pit_disarmed"

        # Verify the engine would skip it (disarm_flag is set)
        assert db.has_flag(trap["disarm_flag"]) is True


def test_trap_one_shot_respected(tmp_path: Path) -> None:
    spec = parse_zorkscript(_minimal_trap_zorkscript())
    output_path = tmp_path / "oneshot_test.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        triggers = db.get_triggers_for_event("room_enter")
        trap = next(t for t in triggers if t["id"] == "spike_pit")
        assert trap["one_shot"] == 1
        assert trap["executed"] == 0

        # Mark as executed
        db.mark_trigger_executed("spike_pit")

        # Now it should not appear in the query (one_shot=1 AND executed=1)
        triggers_after = db.get_triggers_for_event("room_enter")
        trap_ids = [t["id"] for t in triggers_after]
        assert "spike_pit" not in trap_ids


def test_trap_with_command_exec_event() -> None:
    zs = """\
game {
  title "Command Trap Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start room1
}

room room1 {
  name "Room"
  description "A room."
  short "A room."
  start true
}

flag game_won "Victory"

trap cursed_lever {
  on       command_exec
  when     command_id = pull_lever

  effect set_flag(game_won)

  message "The lever sends a shock through your body!"
  once
}
"""
    spec = parse_zorkscript(zs)
    triggers = spec["triggers"]
    assert len(triggers) == 1

    trap = triggers[0]
    assert trap["id"] == "cursed_lever"
    assert trap["event_type"] == "command_exec"
    assert trap["event_data"] == {"command_id": "pull_lever"}
    assert trap["one_shot"] is True


def test_trap_without_disarm_flag() -> None:
    zs = """\
game {
  title "No Disarm Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start room1
}

room room1 {
  name "Room"
  description "A room."
  short "A room."
  start true
}

flag game_won "Victory"

trap poison_gas {
  on       room_enter
  when     room_id = room1

  effect set_flag(game_won)

  message "Poison gas fills the room!"
}
"""
    spec = parse_zorkscript(zs)
    triggers = spec["triggers"]
    assert len(triggers) == 1

    trap = triggers[0]
    assert trap["id"] == "poison_gas"
    assert "disarm_flag" not in trap or trap.get("disarm_flag") is None
    assert trap["one_shot"] is False


def test_trap_repeatable() -> None:
    zs = """\
game {
  title "Repeatable Trap Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start room1
}

room room1 {
  name "Room"
  description "A room."
  short "A room."
  start true
}

flag game_won "Victory"

trap floor_spikes {
  on       room_enter
  when     room_id = room1

  effect set_flag(game_won)

  message "Spikes shoot up from the floor!"
}
"""
    spec = parse_zorkscript(zs)
    trap = spec["triggers"][0]
    assert trap["one_shot"] is False


# ---------------------------------------------------------------------------
# Engine integration tests
# ---------------------------------------------------------------------------

def _compile_zorkscript(zs: str, tmp_path: Path) -> Path:
    spec = parse_zorkscript(zs)
    compiled_path, _ = compile_import_spec(spec, tmp_path / "game.zork")
    return compiled_path


def _make_engine(db: GameDB) -> tuple[GameEngine, StringIO]:
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    engine = GameEngine(db, console=console)
    return engine, buf


def test_engine_trap_fires_on_room_enter(tmp_path: Path) -> None:
    """Trap fires when player enters the matching room via _process_event."""
    zs = """\
game {
  title "Engine Trap Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start corridor
  hp 100
}

room corridor {
  name "Corridor"
  description "A dark corridor."
  short "A dark corridor."
  start true
}

flag game_won "Victory"
flag trap_fired "Trap fired"

command win_game {
  verb win
  pattern "win game"
  effect set_flag(game_won)
  success "You win."
}

trap pit_trap {
  on       room_enter
  when     room_id = corridor

  effect set_flag(trap_fired)

  message "A hidden pit opens beneath you!"
  once
}
"""
    path = _compile_zorkscript(zs, tmp_path)
    with GameDB(path) as db:
        engine, buf = _make_engine(db)
        assert not db.has_flag("trap_fired")

        engine._process_event("room_enter", {"room_id": "corridor"})

        assert db.has_flag("trap_fired")
        output = buf.getvalue()
        assert "A hidden pit opens beneath you!" in output


def test_engine_trap_skipped_when_disarmed(tmp_path: Path) -> None:
    """Trap is skipped when disarm_flag is set, even if preconditions pass."""
    path = _compile_zorkscript(_minimal_trap_zorkscript(), tmp_path)
    with GameDB(path) as db:
        engine, buf = _make_engine(db)

        # Disarm the trap
        db.set_flag("spike_pit_disarmed", "true")

        engine._process_event("room_enter", {"room_id": "corridor"})

        # Effect should NOT have fired
        assert not db.has_flag("spike_pit_triggered")
        assert "The floor gives way" not in buf.getvalue()


def test_engine_trap_one_shot_does_not_refire(tmp_path: Path) -> None:
    """One-shot trap fires once, then is skipped on subsequent events."""
    path = _compile_zorkscript(_minimal_trap_zorkscript(), tmp_path)
    with GameDB(path) as db:
        engine, buf = _make_engine(db)

        # First trigger — should fire
        engine._process_event("room_enter", {"room_id": "corridor"})
        assert db.has_flag("spike_pit_triggered")
        assert "The floor gives way" in buf.getvalue()

        # Clear the effect flag so we can detect a re-fire
        db.clear_flag("spike_pit_triggered")
        buf.truncate(0)
        buf.seek(0)

        # Second trigger — should NOT fire (one-shot already executed)
        engine._process_event("room_enter", {"room_id": "corridor"})
        assert not db.has_flag("spike_pit_triggered")
        assert "The floor gives way" not in buf.getvalue()


def test_engine_command_exec_event_fires_trap(tmp_path: Path) -> None:
    """command_exec event triggers a trap tied to a specific command."""
    zs = """\
game {
  title "Command Exec Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start room1
  hp 100
}

room room1 {
  name "Room"
  description "A room."
  short "A room."
  start true
}

flag game_won "Victory"
flag shocked "Got shocked"

command pull_lever {
  verb pull
  pattern "pull lever"
  effect set_flag(game_won)
  success "You pull the lever."
}

trap cursed_lever {
  on       command_exec
  when     command_id = pull_lever

  effect set_flag(shocked)

  message "The lever sends a shock through your body!"
  once
}
"""
    path = _compile_zorkscript(zs, tmp_path)
    with GameDB(path) as db:
        engine, buf = _make_engine(db)

        # Directly emit command_exec as the engine would after resolve_command
        engine._emit_event("command_exec", command_id="pull_lever")

        assert db.has_flag("shocked")
        assert "shock through your body" in buf.getvalue()


def test_trigger_block_supports_once_keyword() -> None:
    """The `once` keyword works in trigger blocks (not just trap blocks)."""
    zs = """\
game {
  title "Trigger Once Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start room1
}

room room1 {
  name "Room"
  description "A room."
  short "A room."
  start true
}

flag game_won "Victory"

trigger enter_alert {
  on       room_enter
  when     room_id = room1
  message  "Welcome!"
  once
}
"""
    spec = parse_zorkscript(zs)
    trigger = spec["triggers"][0]
    assert trigger["id"] == "enter_alert"
    assert trigger["one_shot"] is True
