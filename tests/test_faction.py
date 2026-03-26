"""Contract tests for NPC faction system: group hostility and mass operations.

Covers:
- ZorkScript parsing of faction field on NPCs
- ZorkScript parsing of faction effects (set_faction_hostile, kill_faction,
  remove_faction, move_faction)
- ZorkScript parsing of faction preconditions (faction_alive, faction_dead)
- DB query: get_npcs_by_faction
- DB mutations: set_faction_hostile, kill_faction, remove_faction, move_faction
- Engine effect handlers for all 4 faction effects
- Engine precondition handlers for faction_alive/faction_dead
- Full round-trip: ZorkScript -> compile -> engine execution
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.commands import apply_effect, check_precondition
from anyzork.engine.game import GameEngine
from anyzork.importer import compile_import_spec
from anyzork.zorkscript import parse_zorkscript


def _faction_zorkscript() -> str:
    return """\
game {
  title "Faction Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start courtyard
}

room courtyard {
  name "Courtyard"
  description "A stone courtyard."
  short "A stone courtyard."
  start true
  exit north -> barracks
}

room barracks {
  name "Barracks"
  description "A military barracks."
  short "A military barracks."
  exit south -> courtyard
}

npc goblin_sentry {
  name "Goblin Sentry"
  description "A goblin in crude armor."
  examine "It watches you with beady eyes."
  in courtyard
  dialogue "It snarls at you."
  category "character"
  faction "goblin"
  hp 20
  damage 5
}

npc goblin_archer {
  name "Goblin Archer"
  description "A goblin with a short bow."
  examine "It has an arrow nocked and ready."
  in courtyard
  dialogue "It growls menacingly."
  category "character"
  faction "goblin"
  hp 15
  damage 8
}

npc friendly_merchant {
  name "Friendly Merchant"
  description "A human merchant."
  examine "She smiles warmly."
  in courtyard
  dialogue "Welcome to my shop!"
  category "character"
  faction "merchants"
}

flag game_won "Victory"
flag goblins_hostile "Goblins are hostile"
flag goblins_dead "All goblins dead"

on "anger goblins" {
  effect set_faction_hostile("goblin")
  effect set_flag(goblins_hostile)
  success "The goblins turn hostile!"
}

on "kill goblins" {
  effect kill_faction("goblin")
  success "All goblins have been slain."
}

on "banish goblins" {
  effect remove_faction("goblin")
  success "The goblins vanish."
}

on "rally goblins" {
  effect move_faction("goblin", barracks)
  success "The goblins march to the barracks."
}

on "check goblins dead" {
  require faction_dead("goblin")
  effect set_flag(goblins_dead)
  success "All goblins confirmed dead."
  fail "Some goblins are still alive."
}

on "check goblins alive" {
  require faction_alive("goblin")
  success "Some goblins are still alive."
  fail "No goblins remain."
}

on "win" {
  effect set_flag(game_won)
  success "You win!"
}
"""


# ---- Parse tests ----


def test_parse_faction_field() -> None:
    """Faction field is parsed correctly from ZorkScript NPC blocks."""
    spec = parse_zorkscript(_faction_zorkscript())
    npcs = spec["npcs"]
    sentry = next(n for n in npcs if n["id"] == "goblin_sentry")
    assert sentry["faction"] == "goblin"

    archer = next(n for n in npcs if n["id"] == "goblin_archer")
    assert archer["faction"] == "goblin"

    merchant = next(n for n in npcs if n["id"] == "friendly_merchant")
    assert merchant["faction"] == "merchants"


def test_parse_npc_without_faction() -> None:
    """NPCs without a faction field have no faction key."""
    src = """\
game { title "T" author "A" max_score 0 win [w] }
player { start r }
room r { name "R" description "D" short "S" start true }
npc bob { name "Bob" description "D" examine "E" in r dialogue "Hi" category "character" }
flag w "W"
"""
    spec = parse_zorkscript(src)
    bob = spec["npcs"][0]
    assert "faction" not in bob


def test_parse_set_faction_hostile_effect() -> None:
    """set_faction_hostile effect is compiled correctly."""
    spec = parse_zorkscript(_faction_zorkscript())
    commands = spec["commands"]
    anger_cmd = next(c for c in commands if c["pattern"] == "anger goblins")
    effects = anger_cmd["effects"]
    faction_effect = next(e for e in effects if e["type"] == "set_faction_hostile")
    assert faction_effect["faction"] == "goblin"


def test_parse_kill_faction_effect() -> None:
    """kill_faction effect is compiled correctly."""
    spec = parse_zorkscript(_faction_zorkscript())
    commands = spec["commands"]
    kill_cmd = next(c for c in commands if c["pattern"] == "kill goblins")
    effects = kill_cmd["effects"]
    faction_effect = next(e for e in effects if e["type"] == "kill_faction")
    assert faction_effect["faction"] == "goblin"


def test_parse_remove_faction_effect() -> None:
    """remove_faction effect is compiled correctly."""
    spec = parse_zorkscript(_faction_zorkscript())
    commands = spec["commands"]
    banish_cmd = next(c for c in commands if c["pattern"] == "banish goblins")
    effects = banish_cmd["effects"]
    faction_effect = next(e for e in effects if e["type"] == "remove_faction")
    assert faction_effect["faction"] == "goblin"


def test_parse_move_faction_effect() -> None:
    """move_faction effect is compiled correctly."""
    spec = parse_zorkscript(_faction_zorkscript())
    commands = spec["commands"]
    rally_cmd = next(c for c in commands if c["pattern"] == "rally goblins")
    effects = rally_cmd["effects"]
    faction_effect = next(e for e in effects if e["type"] == "move_faction")
    assert faction_effect["faction"] == "goblin"
    assert faction_effect["room"] == "barracks"


def test_parse_faction_alive_precondition() -> None:
    """faction_alive precondition is compiled correctly."""
    spec = parse_zorkscript(_faction_zorkscript())
    commands = spec["commands"]
    alive_cmd = next(c for c in commands if c["pattern"] == "check goblins alive")
    preconds = alive_cmd["preconditions"]
    faction_prec = next(p for p in preconds if p["type"] == "faction_alive")
    assert faction_prec["faction"] == "goblin"


def test_parse_faction_dead_precondition() -> None:
    """faction_dead precondition is compiled correctly."""
    spec = parse_zorkscript(_faction_zorkscript())
    commands = spec["commands"]
    dead_cmd = next(c for c in commands if c["pattern"] == "check goblins dead")
    preconds = dead_cmd["preconditions"]
    faction_prec = next(p for p in preconds if p["type"] == "faction_dead")
    assert faction_prec["faction"] == "goblin"


# ---- DB method tests ----


def _compile_db(tmp_path: Path) -> Path:
    spec = parse_zorkscript(_faction_zorkscript())
    output_path = tmp_path / "faction.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)
    return compiled_path


def test_faction_column_stored(tmp_path: Path) -> None:
    """Faction column is stored in the npcs table after compilation."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        sentry = db.get_npc("goblin_sentry")
        assert sentry is not None
        assert sentry["faction"] == "goblin"

        merchant = db.get_npc("friendly_merchant")
        assert merchant["faction"] == "merchants"


def test_get_npcs_by_faction(tmp_path: Path) -> None:
    """get_npcs_by_faction returns all NPCs in a faction."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        goblins = db.get_npcs_by_faction("goblin")
        ids = {n["id"] for n in goblins}
        assert ids == {"goblin_sentry", "goblin_archer"}

        merchants = db.get_npcs_by_faction("merchants")
        assert len(merchants) == 1
        assert merchants[0]["id"] == "friendly_merchant"

        # Nonexistent faction returns empty list
        assert db.get_npcs_by_faction("pirates") == []


def test_set_faction_hostile_db(tmp_path: Path) -> None:
    """set_faction_hostile sets all living members to hostile disposition."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        # Both should be neutral initially
        assert db.get_npc("goblin_sentry")["disposition"] == "neutral"
        assert db.get_npc("goblin_archer")["disposition"] == "neutral"

        db.set_faction_hostile("goblin")

        assert db.get_npc("goblin_sentry")["disposition"] == "hostile"
        assert db.get_npc("goblin_archer")["disposition"] == "hostile"

        # Merchant (different faction) should not be affected
        assert db.get_npc("friendly_merchant")["disposition"] == "neutral"


def test_kill_faction_db(tmp_path: Path) -> None:
    """kill_faction kills all living members and spawns body containers."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.kill_faction("goblin")

        sentry = db.get_npc("goblin_sentry")
        assert sentry["is_alive"] == 0

        archer = db.get_npc("goblin_archer")
        assert archer["is_alive"] == 0

        # Bodies should be spawned
        sentry_body = db.get_item("goblin_sentry_body")
        assert sentry_body is not None
        assert sentry_body["is_container"] == 1

        archer_body = db.get_item("goblin_archer_body")
        assert archer_body is not None

        # Merchant should be unaffected
        assert db.get_npc("friendly_merchant")["is_alive"] == 1


def test_remove_faction_db(tmp_path: Path) -> None:
    """remove_faction deletes all members from the database."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.remove_faction("goblin")

        assert db.get_npc("goblin_sentry") is None
        assert db.get_npc("goblin_archer") is None

        # Merchant should still exist
        assert db.get_npc("friendly_merchant") is not None


def test_move_faction_db(tmp_path: Path) -> None:
    """move_faction moves all living members to a new room."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        # Initially in courtyard
        assert db.get_npc("goblin_sentry")["room_id"] == "courtyard"
        assert db.get_npc("goblin_archer")["room_id"] == "courtyard"

        db.move_faction("goblin", "barracks")

        assert db.get_npc("goblin_sentry")["room_id"] == "barracks"
        assert db.get_npc("goblin_archer")["room_id"] == "barracks"

        # Merchant should not have moved
        assert db.get_npc("friendly_merchant")["room_id"] == "courtyard"


def test_move_faction_skips_dead(tmp_path: Path) -> None:
    """move_faction only moves living NPCs, not dead ones."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        # Kill the sentry
        db.kill_npc("goblin_sentry")
        assert db.get_npc("goblin_sentry")["is_alive"] == 0

        db.move_faction("goblin", "barracks")

        # Dead sentry stays where it was
        assert db.get_npc("goblin_sentry")["room_id"] == "courtyard"
        # Living archer moves
        assert db.get_npc("goblin_archer")["room_id"] == "barracks"


# ---- Engine effect handler tests ----


def test_effect_set_faction_hostile(tmp_path: Path) -> None:
    """set_faction_hostile effect handler works through apply_effect."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        apply_effect({"type": "set_faction_hostile", "faction": "goblin"}, db)
        assert db.get_npc("goblin_sentry")["disposition"] == "hostile"
        assert db.get_npc("goblin_archer")["disposition"] == "hostile"


def test_effect_kill_faction(tmp_path: Path) -> None:
    """kill_faction effect handler works through apply_effect."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        apply_effect({"type": "kill_faction", "faction": "goblin"}, db)
        assert db.get_npc("goblin_sentry")["is_alive"] == 0
        assert db.get_npc("goblin_archer")["is_alive"] == 0


def test_effect_remove_faction(tmp_path: Path) -> None:
    """remove_faction effect handler works through apply_effect."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        apply_effect({"type": "remove_faction", "faction": "goblin"}, db)
        assert db.get_npc("goblin_sentry") is None
        assert db.get_npc("goblin_archer") is None


def test_effect_move_faction(tmp_path: Path) -> None:
    """move_faction effect handler works through apply_effect."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        apply_effect(
            {"type": "move_faction", "faction": "goblin", "room": "barracks"}, db
        )
        assert db.get_npc("goblin_sentry")["room_id"] == "barracks"
        assert db.get_npc("goblin_archer")["room_id"] == "barracks"


def test_effect_move_faction_current_room(tmp_path: Path) -> None:
    """move_faction with _current uses the player's current room."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("barracks")
        # Move goblins from courtyard to player's current room (barracks)
        apply_effect(
            {"type": "move_faction", "faction": "goblin", "room": "_current"}, db
        )
        assert db.get_npc("goblin_sentry")["room_id"] == "barracks"
        assert db.get_npc("goblin_archer")["room_id"] == "barracks"


# ---- Precondition handler tests ----


def test_precondition_faction_alive_true(tmp_path: Path) -> None:
    """faction_alive is true when at least one member is alive."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        result = check_precondition(
            {"type": "faction_alive", "faction": "goblin"}, db
        )
        assert result is True


def test_precondition_faction_alive_partial(tmp_path: Path) -> None:
    """faction_alive is true even if some members are dead."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        db.kill_npc("goblin_sentry")
        result = check_precondition(
            {"type": "faction_alive", "faction": "goblin"}, db
        )
        assert result is True


def test_precondition_faction_alive_all_dead(tmp_path: Path) -> None:
    """faction_alive is false when all members are dead."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        db.kill_npc("goblin_sentry")
        db.kill_npc("goblin_archer")
        result = check_precondition(
            {"type": "faction_alive", "faction": "goblin"}, db
        )
        assert result is False


def test_precondition_faction_alive_nonexistent(tmp_path: Path) -> None:
    """faction_alive is false for a faction that does not exist."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        result = check_precondition(
            {"type": "faction_alive", "faction": "pirates"}, db
        )
        assert result is False


def test_precondition_faction_dead_true(tmp_path: Path) -> None:
    """faction_dead is true when all members are dead."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        db.kill_npc("goblin_sentry")
        db.kill_npc("goblin_archer")
        result = check_precondition(
            {"type": "faction_dead", "faction": "goblin"}, db
        )
        assert result is True


def test_precondition_faction_dead_partial(tmp_path: Path) -> None:
    """faction_dead is false when some members are still alive."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        db.kill_npc("goblin_sentry")
        result = check_precondition(
            {"type": "faction_dead", "faction": "goblin"}, db
        )
        assert result is False


def test_precondition_faction_dead_nonexistent(tmp_path: Path) -> None:
    """faction_dead is false for a faction that does not exist (no members)."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("courtyard")
        result = check_precondition(
            {"type": "faction_dead", "faction": "pirates"}, db
        )
        assert result is False


# ---- Full integration tests ----


def _make_engine(zork_path: Path) -> tuple[GameEngine, Console]:
    """Create a non-interactive GameEngine for testing."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    db = GameDB(zork_path)
    engine = GameEngine(db, console=console, interactive_dialogue=False)
    engine.initialize_session()
    return engine, console


def _get_output(console: Console) -> str:
    return console.file.getvalue()  # type: ignore[union-attr]


def test_roundtrip_set_faction_hostile(tmp_path: Path) -> None:
    """Full round-trip: anger goblins command sets all goblins hostile."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("anger goblins")

    assert engine.db.get_npc("goblin_sentry")["disposition"] == "hostile"
    assert engine.db.get_npc("goblin_archer")["disposition"] == "hostile"
    assert engine.db.get_npc("friendly_merchant")["disposition"] == "neutral"
    assert "hostile" in _get_output(console).lower()


def test_roundtrip_kill_faction(tmp_path: Path) -> None:
    """Full round-trip: kill goblins command kills all goblins."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("kill goblins")

    assert engine.db.get_npc("goblin_sentry")["is_alive"] == 0
    assert engine.db.get_npc("goblin_archer")["is_alive"] == 0
    assert engine.db.get_npc("friendly_merchant")["is_alive"] == 1
    assert "slain" in _get_output(console).lower()


def test_roundtrip_faction_dead_precondition(tmp_path: Path) -> None:
    """Full round-trip: faction_dead precondition gates a command."""
    compiled_path = _compile_db(tmp_path)
    engine, _console = _make_engine(compiled_path)

    # Before killing: faction_dead should fail
    engine.process_command("check goblins dead")
    assert not engine.db.has_flag("goblins_dead")

    # Kill all goblins
    engine.process_command("kill goblins")

    # Now faction_dead should pass
    engine.process_command("check goblins dead")
    assert engine.db.has_flag("goblins_dead")


def test_roundtrip_move_faction(tmp_path: Path) -> None:
    """Full round-trip: rally goblins moves all goblins to barracks."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("rally goblins")

    assert engine.db.get_npc("goblin_sentry")["room_id"] == "barracks"
    assert engine.db.get_npc("goblin_archer")["room_id"] == "barracks"
    assert "barracks" in _get_output(console).lower()


def test_roundtrip_remove_faction(tmp_path: Path) -> None:
    """Full round-trip: banish goblins removes all goblins from the world."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("banish goblins")

    assert engine.db.get_npc("goblin_sentry") is None
    assert engine.db.get_npc("goblin_archer") is None
    assert engine.db.get_npc("friendly_merchant") is not None
    assert "vanish" in _get_output(console).lower()
