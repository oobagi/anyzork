"""Contract tests for reactive NPC triggers: theft, attacks, disposition.

Covers:
- on_item_stolen event firing and trigger parsing
- on_attacked event firing and trigger parsing
- set_disposition effect and npc_disposition precondition
- force_dialogue effect
- Disposition gating on dialogue initiation
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.game import GameEngine
from anyzork.importer import compile_import_spec
from anyzork.zorkscript import parse_zorkscript


def _reactive_npc_zorkscript() -> str:
    return """\
game {
  title "Reactive NPC Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start shop
}

room shop {
  name "Shop"
  description "A cluttered shop."
  short "A cluttered shop."
  start true

  exit south -> alley
}

room alley {
  name "Alley"
  description "A dark alley."
  short "A dark alley."

  exit north -> shop
}

item gold_ring {
  name "Gold Ring"
  description "A shiny gold ring."
  examine "It gleams."
  in shop
  takeable true
}

item iron_sword {
  name "Iron Sword"
  description "A sturdy iron sword."
  examine "Sharp and heavy."
  in shop
  takeable true
  tags ["weapon"]
}

npc shopkeeper {
  name "Shopkeeper"
  description "A portly merchant."
  examine "He watches you with keen eyes."
  in shop
  dialogue "Welcome to my shop."
  category "character"
  disposition "friendly"

  talk root {
    "Welcome, traveler! Browse my wares."
    option "Thanks." -> end
  }

  talk angry {
    "Thief! Get out of my shop!"
    option "Sorry!" -> end
  }
}

npc guard {
  name "Guard"
  description "An armed guard."
  examine "He looks tough."
  in alley
  dialogue "Move along."
  category "character"
  hp 50
  damage 10
  disposition "neutral"
}

flag game_won "Victory"
flag shopkeeper_angry "Shopkeeper is angry"
flag guard_attacked "Guard was attacked"

command win_game {
  verb win
  pattern "win game"
  effect set_flag(game_won)
  success "You win."
}

# Theft trigger: shopkeeper reacts when player takes gold_ring
when on_item_stolen(shopkeeper) {
  effect set_disposition(shopkeeper, "hostile")
  effect set_flag(shopkeeper_angry)
  message "The shopkeeper catches you stealing!"
  once
}

# Attack trigger: guard reacts when attacked
when on_attacked(guard) {
  effect set_disposition(guard, "hostile")
  effect set_flag(guard_attacked)
  message "The guard draws his weapon!"
  once
}

interaction weapon_on_character {
  tag "weapon"
  target "character"
  response "You strike {target} with the {item}."
  effect damage_target(10)
}
"""


def _force_dialogue_zorkscript() -> str:
    return """\
game {
  title "Force Dialogue Test"
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

item gem {
  name "Gem"
  description "A sparkling gem."
  examine "It glows."
  in room1
  takeable true
}

npc wizard {
  name "Wizard"
  description "A wise wizard."
  examine "He glows faintly."
  in room1
  dialogue "Greetings."
  category "character"
  disposition "neutral"

  talk root {
    "Greetings, adventurer."
    option "Hello." -> end
  }

  talk warning {
    "Do not touch that gem! It belongs to me!"
    option "Sorry." -> end
  }
}

flag game_won "Victory"
flag wizard_warned "Wizard warned player"

trigger gem_theft {
  on       on_item_stolen
  when     npc_id = wizard

  effect force_dialogue(wizard, wizard_warning)
  effect set_flag(wizard_warned)

  message "The wizard's eyes flash with anger."
  once
}
"""


# ---- Parse tests ----


def test_parse_on_item_stolen_trigger() -> None:
    """on_item_stolen event type is parsed correctly in when blocks."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    triggers = spec["triggers"]
    theft_trigger = next(
        t for t in triggers if t["event_type"] == "on_item_stolen"
    )
    assert theft_trigger["event_data"] == {"npc_id": "shopkeeper"}
    assert theft_trigger["one_shot"] is True
    assert any(
        e["type"] == "set_disposition" for e in theft_trigger["effects"]
    )


def test_parse_on_attacked_trigger() -> None:
    """on_attacked event type is parsed correctly in when blocks."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    triggers = spec["triggers"]
    attack_trigger = next(
        t for t in triggers if t["event_type"] == "on_attacked"
    )
    assert attack_trigger["event_data"] == {"npc_id": "guard"}
    assert attack_trigger["one_shot"] is True
    assert any(
        e["type"] == "set_flag" for e in attack_trigger["effects"]
    )


def test_parse_set_disposition_effect() -> None:
    """set_disposition effect is compiled correctly."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    triggers = spec["triggers"]
    theft_trigger = next(
        t for t in triggers if t["event_type"] == "on_item_stolen"
    )
    disp_effect = next(
        e for e in theft_trigger["effects"] if e["type"] == "set_disposition"
    )
    assert disp_effect["npc"] == "shopkeeper"
    assert disp_effect["disposition"] == "hostile"


def test_parse_npc_disposition_field() -> None:
    """NPC disposition field is parsed from ZorkScript."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    npcs = spec["npcs"]
    shopkeeper = next(n for n in npcs if n["id"] == "shopkeeper")
    assert shopkeeper["disposition"] == "friendly"

    guard = next(n for n in npcs if n["id"] == "guard")
    assert guard["disposition"] == "neutral"


def test_parse_force_dialogue_effect() -> None:
    """force_dialogue effect is compiled correctly."""
    spec = parse_zorkscript(_force_dialogue_zorkscript())
    triggers = spec["triggers"]
    theft_trigger = next(
        t for t in triggers if t["id"] == "gem_theft"
    )
    fd_effect = next(
        e for e in theft_trigger["effects"] if e["type"] == "force_dialogue"
    )
    assert fd_effect["npc"] == "wizard"
    assert fd_effect["node"] == "wizard_warning"


def test_parse_npc_disposition_precondition() -> None:
    """npc_disposition precondition is compiled correctly."""
    src = """\
game {
  title "Precondition Test"
  author "Test"
  max_score 0
  win [game_won]
}

player { start room1 }

room room1 {
  name "Room"
  description "A room."
  short "A room."
  start true
}

flag game_won "Victory"

on "bribe guard" {
  require npc_disposition(guard, "hostile")
  effect set_flag(game_won)
  success "You bribed the guard."
}
"""
    spec = parse_zorkscript(src)
    commands = spec["commands"]
    assert len(commands) == 1
    cmd = commands[0]
    assert len(cmd["preconditions"]) == 1
    precond = cmd["preconditions"][0]
    assert precond["type"] == "npc_disposition"
    assert precond["npc"] == "guard"
    assert precond["disposition"] == "hostile"


# ---- Compilation tests ----


def test_disposition_compiles_to_db(tmp_path: Path) -> None:
    """NPC disposition field survives compilation to .zork file."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "reactive.zork"
    compiled_path, _warnings = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        shopkeeper = db.get_npc("shopkeeper")
        assert shopkeeper is not None
        assert shopkeeper["disposition"] == "friendly"

        guard = db.get_npc("guard")
        assert guard is not None
        assert guard["disposition"] == "neutral"


def test_on_item_stolen_trigger_compiles(tmp_path: Path) -> None:
    """on_item_stolen triggers compile to the triggers table."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "theft_trigger.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        triggers = db.get_triggers_for_event("on_item_stolen")
        assert len(triggers) >= 1
        theft = next(
            t for t in triggers
            if "shopkeeper" in (t.get("event_data") or "")
        )
        assert theft["one_shot"] == 1


def test_on_attacked_trigger_compiles(tmp_path: Path) -> None:
    """on_attacked triggers compile to the triggers table."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "attack_trigger.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        triggers = db.get_triggers_for_event("on_attacked")
        assert len(triggers) >= 1


# ---- DB method tests ----


def test_set_npc_disposition(tmp_path: Path) -> None:
    """set_npc_disposition updates the NPC's disposition column."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "disp_test.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        assert db.get_npc_disposition("shopkeeper") == "friendly"
        db.set_npc_disposition("shopkeeper", "hostile")
        assert db.get_npc_disposition("shopkeeper") == "hostile"


def test_set_npc_disposition_rejects_invalid(tmp_path: Path) -> None:
    """set_npc_disposition raises ValueError for invalid disposition values."""
    import pytest

    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "disp_invalid.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        with pytest.raises(ValueError, match="Invalid disposition"):
            db.set_npc_disposition("shopkeeper", "hostle")
        # Original value should be unchanged.
        assert db.get_npc_disposition("shopkeeper") == "friendly"


def test_get_npc_disposition_default(tmp_path: Path) -> None:
    """get_npc_disposition returns 'neutral' for unknown NPC."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "disp_default.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        assert db.get_npc_disposition("nonexistent") == "neutral"


# ---- Engine integration tests ----


def _make_engine(zork_path: Path) -> tuple[GameEngine, Console]:
    """Create a non-interactive GameEngine for testing."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    db = GameDB(zork_path)
    engine = GameEngine(db, console=console, interactive_dialogue=False)
    engine.initialize_session()
    return engine, console


def _get_output(console: Console) -> str:
    """Extract text output from a Console with a StringIO file."""
    return console.file.getvalue()  # type: ignore[union-attr]


def test_theft_emits_on_item_stolen(tmp_path: Path) -> None:
    """Taking an item from a room with NPCs fires on_item_stolen triggers."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "theft_engine.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Take the gold ring while shopkeeper is present.
    engine.process_command("take gold ring")
    output = _get_output(console)

    # The theft trigger message should appear.
    assert "catches you stealing" in output

    # The shopkeeper should now be hostile.
    db = engine.db
    assert db.get_npc_disposition("shopkeeper") == "hostile"
    assert db.has_flag("shopkeeper_angry")


def test_hostile_npc_blocks_dialogue(tmp_path: Path) -> None:
    """Hostile NPCs refuse dialogue initiation."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "hostile_dialogue.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Make shopkeeper hostile.
    engine.db.set_npc_disposition("shopkeeper", "hostile")

    # Try to talk to shopkeeper.
    engine.process_command("talk to shopkeeper")
    output = _get_output(console)

    assert "refuses to speak" in output


def test_friendly_npc_allows_dialogue(tmp_path: Path) -> None:
    """Friendly NPCs allow normal dialogue."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "friendly_dialogue.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Shopkeeper is friendly by default.
    assert engine.db.get_npc_disposition("shopkeeper") == "friendly"

    # Talk to shopkeeper should work.
    engine.process_command("talk to shopkeeper")
    output = _get_output(console)

    assert "Browse my wares" in output or "Welcome" in output


def test_npc_disposition_precondition(tmp_path: Path) -> None:
    """npc_disposition precondition evaluates correctly."""
    from anyzork.engine.commands import check_precondition

    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "disp_precond.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("shop")

        # Guard is neutral.
        cond = {"type": "npc_disposition", "npc": "guard", "disposition": "neutral"}
        assert check_precondition(cond, db) is True

        cond_hostile = {"type": "npc_disposition", "npc": "guard", "disposition": "hostile"}
        assert check_precondition(cond_hostile, db) is False

        # Change disposition and recheck.
        db.set_npc_disposition("guard", "hostile")
        assert check_precondition(cond_hostile, db) is True
        assert check_precondition(cond, db) is False


def test_set_disposition_effect(tmp_path: Path) -> None:
    """set_disposition effect changes NPC disposition at runtime."""
    from anyzork.engine.commands import apply_effect

    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "disp_effect.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("shop")
        assert db.get_npc_disposition("shopkeeper") == "friendly"

        effect = {"type": "set_disposition", "npc": "shopkeeper", "disposition": "hostile"}
        apply_effect(effect, db)

        assert db.get_npc_disposition("shopkeeper") == "hostile"


def test_attack_verb_emits_on_attacked(tmp_path: Path) -> None:
    """The attack verb emits on_attacked events."""
    spec = parse_zorkscript(_reactive_npc_zorkscript())
    output_path = tmp_path / "attack_verb.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # First, take the sword so we have a weapon.
    engine.process_command("take iron sword")

    # Move to alley where the guard is.
    engine.db.update_player(current_room_id="alley")

    # Attack the guard.
    engine.process_command("attack guard")
    _get_output(console)  # consume output

    # Guard should now be hostile.
    assert engine.db.get_npc_disposition("guard") == "hostile"
    assert engine.db.has_flag("guard_attacked")


def test_named_trigger_block_with_new_events() -> None:
    """Named trigger block with on_item_stolen and on_attacked events."""
    src = """\
game {
  title "Named Trigger Test"
  author "Test"
  max_score 0
  win [game_won]
}

player { start room1 }

room room1 {
  name "Room"
  description "A room."
  short "A room."
  start true
}

flag game_won "Victory"
flag thief_caught "Thief detected"

trigger theft_alarm {
  on       on_item_stolen
  when     npc_id = merchant

  effect set_flag(thief_caught)
  effect set_disposition(merchant, "hostile")

  message "A bell rings!"
  once
}

trigger attack_alarm {
  on       on_attacked
  when     npc_id = soldier

  effect set_disposition(soldier, "hostile")

  message "To arms!"
  once
}
"""
    spec = parse_zorkscript(src)
    triggers = spec["triggers"]
    assert len(triggers) == 2

    theft = next(t for t in triggers if t["id"] == "theft_alarm")
    assert theft["event_type"] == "on_item_stolen"
    assert theft["event_data"] == {"npc_id": "merchant"}

    attack = next(t for t in triggers if t["id"] == "attack_alarm")
    assert attack["event_type"] == "on_attacked"
    assert attack["event_data"] == {"npc_id": "soldier"}
