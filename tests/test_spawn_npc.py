"""Contract tests for spawn_npc effect: dynamic NPC creation at runtime.

Covers:
- ZorkScript parsing of spawn_npc effect
- Template NPCs (no room_id = stays in limbo until spawned)
- DB method: spawn_npc (places a template NPC into a room)
- Engine effect handler for spawn_npc
- Re-spawning an already-spawned NPC moves it
- Full round-trip: ZorkScript -> compile -> engine execution
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


def _spawn_npc_zorkscript() -> str:
    return """\
game {
  title "Spawn NPC Test"
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
  exit north -> balcony
}

room balcony {
  name "Balcony"
  description "A high balcony."
  short "A high balcony."
  exit south -> courtyard
}

# Template NPC: no "in" field, stays in limbo
npc shadow_creature {
  name "Shadow Creature"
  description "A writhing mass of darkness."
  examine "Its form shifts and writhes."
  dialogue "It hisses at you."
  category "enemy"
  hp 30
}

# Normal NPC for comparison
npc guard {
  name "Guard"
  description "A stern guard."
  examine "The guard watches you carefully."
  in courtyard
  dialogue "Move along."
  category "character"
}

flag game_won "Victory"
flag defense_started "Defense has started"

on "start defense" {
  effect set_flag(defense_started)
  effect spawn_npc(shadow_creature, balcony)
  success "The defense begins! A shadow creature appears on the balcony!"
}

on "win" {
  effect set_flag(game_won)
  success "You win!"
}

on "move shadow" {
  effect spawn_npc(shadow_creature, courtyard)
  success "The shadow creature moves to the courtyard."
}

when flag_set(defense_started) {
  effect spawn_npc(shadow_creature, balcony)
  message "A shadow creature materializes on the balcony!"
  once
}
"""


# ---- Parse tests ----


def test_parse_spawn_npc_effect() -> None:
    """spawn_npc effect is compiled correctly from ZorkScript."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    commands = spec["commands"]
    start_cmd = next(c for c in commands if c["pattern"] == "start defense")
    effects = start_cmd["effects"]
    spawn_effect = next(e for e in effects if e["type"] == "spawn_npc")
    assert spawn_effect["npc"] == "shadow_creature"
    assert spawn_effect["room"] == "balcony"


def test_parse_template_npc_no_room() -> None:
    """A template NPC (no 'in' field) has no room_id in the parsed spec."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    npcs = spec["npcs"]
    shadow = next(n for n in npcs if n["id"] == "shadow_creature")
    assert "room_id" not in shadow


def test_parse_normal_npc_has_room() -> None:
    """A normal NPC (with 'in' field) has room_id in the parsed spec."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    npcs = spec["npcs"]
    guard = next(n for n in npcs if n["id"] == "guard")
    assert guard["room_id"] == "courtyard"


def test_parse_spawn_npc_in_trigger() -> None:
    """spawn_npc in a when block is compiled correctly."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    triggers = spec["triggers"]
    defense_trigger = next(
        t for t in triggers
        if any(e.get("type") == "spawn_npc" for e in t["effects"])
    )
    spawn_effect = next(e for e in defense_trigger["effects"] if e["type"] == "spawn_npc")
    assert spawn_effect["npc"] == "shadow_creature"
    assert spawn_effect["room"] == "balcony"


# ---- DB method tests ----


def test_spawn_npc_places_template_in_room(tmp_path: Path) -> None:
    """spawn_npc moves a template NPC (NULL room_id) into a room."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    output_path = tmp_path / "spawn_npc_db.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        # Template NPC should have NULL room_id.
        shadow = db.get_npc("shadow_creature")
        assert shadow is not None
        assert shadow["room_id"] is None

        # Spawn into balcony.
        db.spawn_npc("shadow_creature", "balcony")
        shadow = db.get_npc("shadow_creature")
        assert shadow["room_id"] == "balcony"


def test_spawn_npc_respawn_moves_to_new_room(tmp_path: Path) -> None:
    """spawn_npc on an already-spawned NPC moves it to the new room."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    output_path = tmp_path / "spawn_npc_respawn.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.spawn_npc("shadow_creature", "balcony")
        assert db.get_npc("shadow_creature")["room_id"] == "balcony"

        # Re-spawn to courtyard.
        db.spawn_npc("shadow_creature", "courtyard")
        assert db.get_npc("shadow_creature")["room_id"] == "courtyard"


def test_template_npc_not_in_any_room(tmp_path: Path) -> None:
    """A template NPC is not visible in any room before spawning."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    output_path = tmp_path / "spawn_npc_invisible.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        # Template NPC should not appear in any room's NPC list.
        courtyard_npcs = db.get_npcs_in("courtyard")
        balcony_npcs = db.get_npcs_in("balcony")

        shadow_ids = [n["id"] for n in courtyard_npcs + balcony_npcs]
        assert "shadow_creature" not in shadow_ids

        # Normal NPC should be present.
        guard_ids = [n["id"] for n in courtyard_npcs]
        assert "guard" in guard_ids


def test_spawned_npc_appears_in_room(tmp_path: Path) -> None:
    """After spawning, the NPC appears in the target room's NPC list."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    output_path = tmp_path / "spawn_npc_appears.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.spawn_npc("shadow_creature", "balcony")
        balcony_npcs = db.get_npcs_in("balcony")
        ids = [n["id"] for n in balcony_npcs]
        assert "shadow_creature" in ids


# ---- Engine effect tests ----


def test_spawn_npc_effect_via_engine(tmp_path: Path) -> None:
    """spawn_npc effect handler places the NPC in the target room."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    output_path = tmp_path / "spawn_npc_engine.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("courtyard")

        apply_effect(
            {"type": "spawn_npc", "npc": "shadow_creature", "room": "balcony"},
            db,
        )

        shadow = db.get_npc("shadow_creature")
        assert shadow["room_id"] == "balcony"


def test_spawn_npc_effect_current_room(tmp_path: Path) -> None:
    """spawn_npc with _current as room spawns into the player's current room."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    output_path = tmp_path / "spawn_npc_current.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("courtyard")

        apply_effect(
            {"type": "spawn_npc", "npc": "shadow_creature", "room": "_current"},
            db,
        )

        shadow = db.get_npc("shadow_creature")
        assert shadow["room_id"] == "courtyard"


# ---- Full integration test ----


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


def test_spawn_npc_full_roundtrip(tmp_path: Path) -> None:
    """Full round-trip: command spawns template NPC, NPC appears in room."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    output_path = tmp_path / "spawn_npc_roundtrip.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Before starting defense, shadow creature should not be in any room.
    shadow = engine.db.get_npc("shadow_creature")
    assert shadow["room_id"] is None

    # Start the defense -- this should spawn the shadow creature.
    engine.process_command("start defense")

    shadow = engine.db.get_npc("shadow_creature")
    assert shadow["room_id"] == "balcony"

    output = _get_output(console)
    assert "defense begins" in output.lower() or "shadow creature" in output.lower()


def test_spawn_npc_respawn_roundtrip(tmp_path: Path) -> None:
    """Full round-trip: spawning again moves the NPC to a new room."""
    spec = parse_zorkscript(_spawn_npc_zorkscript())
    output_path = tmp_path / "spawn_npc_respawn_rt.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # First spawn.
    engine.process_command("start defense")
    assert engine.db.get_npc("shadow_creature")["room_id"] == "balcony"

    # Second spawn (move to courtyard).
    engine.process_command("move shadow")
    assert engine.db.get_npc("shadow_creature")["room_id"] == "courtyard"
