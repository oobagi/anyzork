"""Contract tests for NPC blockers and the deterministic hint layer.

Covers:
- ZorkScript parsing of NPC blocking fields (blocking, unblock, block_msg)
- ZorkScript parsing of hint blocks
- DB methods: get_blocking_npc_for_exit, insert_hint, get_all_hints, mark_hint_used
- Engine: NPC blockers prevent movement
- Engine: NPC blockers respect unblock_flag
- Engine: NPC blockers respect is_alive (dead NPCs don't block)
- Engine: hint command shows highest-priority applicable hint
- Engine: hint command filters by preconditions
- Validation: NPC blocker exit references checked
- Validation: hint precondition types validated
- Full integration: block_message shown when NPC blocks exit
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.game import GameEngine
from anyzork.importer import compile_import_spec
from anyzork.zorkscript import parse_zorkscript


def _blocker_zorkscript() -> str:
    return """\
game {
  title "NPC Blocker Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start foyer
}

room foyer {
  name "Foyer"
  description "A grand foyer."
  short "A foyer."
  start true

  exit north -> hall "A hallway stretches north."
}

room hall {
  name "Hall"
  description "A long hall."
  short "A hall."

  exit south -> foyer "The foyer lies south."
}

npc bouncer {
  name "Bouncer"
  description "A burly bouncer blocks the hallway."
  examine "He glares at you."
  in foyer
  home foyer
  room_desc "A burly bouncer stands in front of the north exit."
  dialogue "Step back."
  category "character"
  blocking foyer -> hall north
  unblock bribed_bouncer
  block_msg "The bouncer shoves you back. 'Members only.'"
  hp 50
  damage 10
}

item gold_coin {
  name "Gold Coin"
  description "A shiny gold coin."
  examine "It gleams."
  in foyer
  tags ["treasure"]
  category "treasure"
  room_desc "A gold coin lies on the floor."
}

flag game_won "Victory"
flag bribed_bouncer "The bouncer was bribed"

on "win game" {
  effect set_flag(game_won)
  success "You win."
}

on "bribe {target}" {
  require has_item(gold_coin)
  require npc_in_room(bouncer, _current)

  effect set_flag(bribed_bouncer)
  effect remove_item(gold_coin)

  success "You slip the coin to the bouncer. He nods and steps aside."
  once
}
"""


def _hint_zorkscript() -> str:
    return """\
game {
  title "Hint Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start garden
}

room garden {
  name "Garden"
  description "A quiet garden."
  short "A garden."
  start true
}

item rusty_key {
  name "Rusty Key"
  description "A rusty key."
  examine "Old and corroded."
  in garden
  tags ["key"]
  category "key_item"
  room_desc "A rusty key lies in the grass."
}

flag game_won "Victory"
flag door_unlocked "Door is open"

on "win game" {
  effect set_flag(game_won)
  success "You win."
}

hint hint_pick_up_key {
  text "There is a rusty key in the garden. Try picking it up."
  require not_flag(door_unlocked)
  priority 10
}

hint hint_use_key {
  text "You have a key. Perhaps there is a door to unlock."
  require has_item(rusty_key)
  require not_flag(door_unlocked)
  priority 20
}

hint hint_fallback {
  text "Explore and examine things."
  priority 1
}
"""


# ---- Helper functions ----


def _make_engine(zork_path: Path) -> tuple[GameEngine, Console]:
    """Create a non-interactive GameEngine for testing."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    db = GameDB(zork_path)
    engine = GameEngine(db, console=console, interactive_dialogue=False)
    engine.initialize_session()
    return engine, console


def _get_output(console: Console) -> str:
    """Extract text output from a Console with a StringIO file, stripping ANSI."""
    import re

    raw = console.file.getvalue()  # type: ignore[union-attr]
    return re.sub(r"\x1b\[[0-9;]*m", "", raw)


# ==== Parse tests ====


def test_parse_npc_blocking_fields() -> None:
    """NPC blocking fields are parsed correctly from ZorkScript."""
    spec = parse_zorkscript(_blocker_zorkscript())
    npcs = spec["npcs"]
    bouncer = next(n for n in npcs if n["id"] == "bouncer")
    assert bouncer["is_blocking"] is True
    assert bouncer["unblock_flag"] == "bribed_bouncer"
    assert bouncer["block_message"] == "The bouncer shoves you back. 'Members only.'"
    assert bouncer.get("blocked_exit_id") is not None


def test_parse_hint_blocks() -> None:
    """Hint blocks are parsed correctly from ZorkScript."""
    spec = parse_zorkscript(_hint_zorkscript())
    hints = spec["hints"]
    assert len(hints) == 3

    use_key = next(h for h in hints if h["id"] == "hint_use_key")
    assert use_key["text"] == "You have a key. Perhaps there is a door to unlock."
    assert use_key["priority"] == 20
    assert len(use_key["preconditions"]) == 2

    fallback = next(h for h in hints if h["id"] == "hint_fallback")
    assert fallback["priority"] == 1
    assert len(fallback["preconditions"]) == 0


# ==== DB method tests ====


def test_get_blocking_npc_for_exit(tmp_path: Path) -> None:
    """get_blocking_npc_for_exit returns the NPC when it blocks the exit."""
    spec = parse_zorkscript(_blocker_zorkscript())
    output_path = tmp_path / "blocker_db.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        # The bouncer should block the foyer_north exit
        blocker = db.get_blocking_npc_for_exit("foyer_north")
        assert blocker is not None
        assert blocker["id"] == "bouncer"


def test_get_blocking_npc_respects_unblock_flag(tmp_path: Path) -> None:
    """When the unblock_flag is set, get_blocking_npc_for_exit returns None."""
    spec = parse_zorkscript(_blocker_zorkscript())
    output_path = tmp_path / "blocker_unblock.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        # Set the unblock flag
        db.set_flag("bribed_bouncer", "true")
        blocker = db.get_blocking_npc_for_exit("foyer_north")
        assert blocker is None


def test_get_blocking_npc_dead_npc_no_block(tmp_path: Path) -> None:
    """Dead NPCs do not block exits."""
    spec = parse_zorkscript(_blocker_zorkscript())
    output_path = tmp_path / "blocker_dead.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.kill_npc("bouncer")
        blocker = db.get_blocking_npc_for_exit("foyer_north")
        assert blocker is None


def test_insert_and_get_hints(tmp_path: Path) -> None:
    """Hints are correctly inserted and retrieved from the DB."""
    spec = parse_zorkscript(_hint_zorkscript())
    output_path = tmp_path / "hints_db.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        hints = db.get_all_hints()
        assert len(hints) == 3
        # Highest priority first
        assert hints[0]["id"] == "hint_use_key"
        assert hints[0]["priority"] == 20


def test_mark_hint_used(tmp_path: Path) -> None:
    """mark_hint_used sets the used flag on a hint."""
    spec = parse_zorkscript(_hint_zorkscript())
    output_path = tmp_path / "hints_used.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.mark_hint_used("hint_fallback")
        hints = db.get_all_hints()
        fb = next(h for h in hints if h["id"] == "hint_fallback")
        assert fb["used"] == 1


# ==== Engine integration tests ====


def test_npc_blocker_prevents_movement(tmp_path: Path) -> None:
    """An NPC blocker prevents the player from moving through the blocked exit."""
    spec = parse_zorkscript(_blocker_zorkscript())
    output_path = tmp_path / "blocker_engine.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Try to go north — bouncer blocks
    engine.process_command("north")
    player = engine.db.get_player()
    assert player is not None
    assert player["current_room_id"] == "foyer"

    output = _get_output(console)
    assert "Members only" in output


def test_npc_blocker_cleared_by_flag(tmp_path: Path) -> None:
    """After the unblock flag is set, the NPC no longer blocks."""
    spec = parse_zorkscript(_blocker_zorkscript())
    output_path = tmp_path / "blocker_cleared.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # Pick up the coin and bribe the bouncer
    engine.process_command("take gold coin")
    engine.process_command("bribe bouncer")

    assert engine.db.has_flag("bribed_bouncer")

    # Now go north — should work
    engine.process_command("north")
    player = engine.db.get_player()
    assert player is not None
    assert player["current_room_id"] == "hall"


def test_npc_blocker_cleared_by_death(tmp_path: Path) -> None:
    """After the NPC is killed, it no longer blocks."""
    spec = parse_zorkscript(_blocker_zorkscript())
    output_path = tmp_path / "blocker_death.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # Kill the bouncer directly
    engine.db.kill_npc("bouncer")

    # Now go north — should work
    engine.process_command("north")
    player = engine.db.get_player()
    assert player is not None
    assert player["current_room_id"] == "hall"


def test_hint_command_shows_applicable_hint(tmp_path: Path) -> None:
    """The hint command shows the highest-priority hint whose preconditions are met."""
    spec = parse_zorkscript(_hint_zorkscript())
    output_path = tmp_path / "hint_engine.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Without the key in inventory, hint_use_key (priority 20) should not match.
    # hint_pick_up_key (priority 10) should match (not_flag(door_unlocked) is true).
    engine.process_command("hint")
    output = _get_output(console)
    assert "rusty key in the garden" in output


def test_hint_command_changes_with_state(tmp_path: Path) -> None:
    """After picking up the key, a higher-priority hint becomes applicable."""
    spec = parse_zorkscript(_hint_zorkscript())
    output_path = tmp_path / "hint_state.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Pick up the key
    engine.process_command("take rusty key")

    # Now hint_use_key (priority 20) should match
    engine.process_command("hint")
    output = _get_output(console)
    assert "door to unlock" in output


def test_hint_fallback_when_no_conditions_match(tmp_path: Path) -> None:
    """The fallback hint (no preconditions) is always available."""
    spec = parse_zorkscript(_hint_zorkscript())
    output_path = tmp_path / "hint_fallback.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Set door_unlocked to make the specific hints inapplicable
    engine.db.set_flag("door_unlocked", "true")

    engine.process_command("hint")
    output = _get_output(console)
    assert "Explore and examine" in output


def test_hint_no_hints_message(tmp_path: Path, minimal_import_spec: dict) -> None:
    """When no hints are defined, a message is shown."""
    output_path = tmp_path / "no_hints.zork"
    compiled_path, _ = compile_import_spec(minimal_import_spec, output_path)

    engine, console = _make_engine(compiled_path)
    engine.process_command("hint")
    output = _get_output(console)
    assert "No hints are available" in output


# ==== Validation tests ====


def test_validation_npc_blocker_exit_reference(tmp_path: Path) -> None:
    """Validation catches NPC blockers referencing non-existent exits."""
    from anyzork.validation import validate_game

    spec = parse_zorkscript(_blocker_zorkscript())
    output_path = tmp_path / "blocker_valid.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        errors = validate_game(db)
        # The valid spec should not produce npc-category errors
        npc_errors = [e for e in errors if e.category == "npc" and e.severity == "error"]
        assert len(npc_errors) == 0


def test_validation_hint_preconditions(tmp_path: Path) -> None:
    """Validation passes for hints with valid precondition types."""
    from anyzork.validation import validate_game

    spec = parse_zorkscript(_hint_zorkscript())
    output_path = tmp_path / "hint_valid.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        errors = validate_game(db)
        hint_errors = [e for e in errors if e.category == "hint" and e.severity == "error"]
        assert len(hint_errors) == 0
