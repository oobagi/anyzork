"""Contract tests for turn-based combat system.

Covers:
- ZorkScript parsing of NPC combat fields (defense, weakness, drop)
- ZorkScript parsing of item damage field
- ZorkScript parsing of heal_player/damage_player effects
- DB storage of NPC combat columns and item damage
- Engine combat: damage calculation, defense, weakness doubling
- Engine combat: NPC retaliation
- Engine combat: NPC death and loot drop
- Engine combat: player death (game over)
- Engine: status command
- Engine: heal_player and damage_player effects
- Full round-trip: ZorkScript -> compile -> engine combat
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


def _combat_zorkscript() -> str:
    return """\
game {
  title "Combat Test"
  author "Test"
  max_score 0
  win [game_won]
  lose_text "You have fallen in battle."
}

player {
  start arena
  hp 100
  max_hp 100
}

room arena {
  name "Arena"
  description "A sandy arena."
  short "A sandy arena."
  start true
  exit north -> armory "A passage north to the armory."
}

room armory {
  name "Armory"
  description "Weapon racks line the walls."
  short "An armory."
  exit south -> arena "Back to the arena."
}

# Basic weapon with damage stat
item iron_sword {
  name "Iron Sword"
  description "A sturdy iron sword."
  examine "Well-balanced and sharp."
  in arena
  tags ["weapon", "blade"]
  category "weapon"
  damage 20
  take_msg "You draw the iron sword."
  room_desc "An iron sword rests on a weapon rack."
}

# Ice weapon for weakness testing
item frost_blade {
  name "Frost Blade"
  description "A sword sheathed in ice."
  examine "Frost spirals along the blade."
  in armory
  tags ["weapon", "blade", "ice"]
  category "weapon"
  damage 15
  take_msg "The cold bites your hand as you grip the hilt."
  room_desc "A frost-covered sword rests in a weapon rack."
}

# Loot item
item gold_hoard {
  name "Gold Hoard"
  description "A pile of gold coins."
  examine "Glittering coins."
  tags ["treasure"]
  category "treasure"
  take_msg "You scoop up the gold."
}

# Combat NPC with all stats
npc dragon {
  name "Ancient Dragon"
  description "A massive dragon with scales like shields."
  examine "Its eyes glow with malice."
  in arena
  home arena
  room_desc "An ancient dragon blocks the way, smoke curling from its nostrils."
  dialogue "It roars at you!"
  category "enemy"
  hp 50
  damage 25
  defense 5
  weakness "ice"
  drop gold_hoard
}

# Weak NPC for quick kill test
npc goblin {
  name "Goblin"
  description "A scrawny goblin."
  examine "It bares its teeth."
  in arena
  home arena
  room_desc "A scrawny goblin lurks in the corner."
  dialogue "It hisses."
  category "enemy"
  hp 10
  damage 3
  defense 0
}

# NPC without combat stats (fallback behavior)
npc villager {
  name "Villager"
  description "A nervous villager."
  examine "He looks scared."
  in arena
  dialogue "Please don't hurt me!"
  category "character"
}

flag game_won "Victory"

on "win" {
  effect set_flag(game_won)
  success "You win!"
}

# heal/damage player effects
on "drink potion" {
  effect heal_player(30)
  success "You drink a healing potion and feel refreshed."
}

on "touch trap" {
  effect damage_player(20)
  success "A trap springs! You take damage."
}
"""


def _compile_db(tmp_path: Path) -> Path:
    spec = parse_zorkscript(_combat_zorkscript())
    output_path = tmp_path / "combat.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)
    return compiled_path


def _make_engine(zork_path: Path) -> tuple[GameEngine, Console]:
    """Create a non-interactive GameEngine for testing."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    db = GameDB(zork_path)
    engine = GameEngine(db, console=console, interactive_dialogue=False)
    engine.initialize_session()
    return engine, console


def _get_output(console: Console) -> str:
    return console.file.getvalue()  # type: ignore[union-attr]


# ---- Parse tests ----


def test_parse_npc_defense_field() -> None:
    """Defense field is parsed correctly from ZorkScript NPC blocks."""
    spec = parse_zorkscript(_combat_zorkscript())
    npcs = spec["npcs"]
    dragon = next(n for n in npcs if n["id"] == "dragon")
    assert dragon["defense"] == 5


def test_parse_npc_weakness_field() -> None:
    """Weakness field is parsed correctly from ZorkScript NPC blocks."""
    spec = parse_zorkscript(_combat_zorkscript())
    npcs = spec["npcs"]
    dragon = next(n for n in npcs if n["id"] == "dragon")
    assert dragon["weakness"] == "ice"


def test_parse_npc_drop_field() -> None:
    """Drop field is parsed correctly from ZorkScript NPC blocks."""
    spec = parse_zorkscript(_combat_zorkscript())
    npcs = spec["npcs"]
    dragon = next(n for n in npcs if n["id"] == "dragon")
    assert dragon["drop"] == "gold_hoard"


def test_parse_item_damage_field() -> None:
    """Damage field is parsed correctly from ZorkScript item blocks."""
    spec = parse_zorkscript(_combat_zorkscript())
    items = spec["items"]
    sword = next(i for i in items if i["id"] == "iron_sword")
    assert sword["damage"] == 20


def test_parse_heal_player_effect() -> None:
    """heal_player effect is compiled correctly."""
    spec = parse_zorkscript(_combat_zorkscript())
    commands = spec["commands"]
    heal_cmd = next(c for c in commands if c["pattern"] == "drink potion")
    effects = heal_cmd["effects"]
    heal = next(e for e in effects if e["type"] == "heal_player")
    assert heal["amount"] == 30


def test_parse_damage_player_effect() -> None:
    """damage_player effect is compiled correctly."""
    spec = parse_zorkscript(_combat_zorkscript())
    commands = spec["commands"]
    trap_cmd = next(c for c in commands if c["pattern"] == "touch trap")
    effects = trap_cmd["effects"]
    dmg = next(e for e in effects if e["type"] == "damage_player")
    assert dmg["amount"] == 20


# ---- DB tests ----


def test_npc_combat_columns_stored(tmp_path: Path) -> None:
    """NPC combat columns are stored in the database after compilation."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        dragon = db.get_npc("dragon")
        assert dragon is not None
        assert dragon["hp"] == 50
        assert dragon["damage"] == 25
        assert dragon["defense"] == 5
        assert dragon["weakness"] == "ice"
        assert dragon["drop_item"] == "gold_hoard"


def test_item_damage_stored(tmp_path: Path) -> None:
    """Item damage column is stored in the database after compilation."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        sword = db.get_item("iron_sword")
        assert sword is not None
        assert sword["damage"] == 20


def test_npc_without_combat_stats(tmp_path: Path) -> None:
    """NPCs without combat stats have NULL for defense/weakness/drop."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        villager = db.get_npc("villager")
        assert villager is not None
        assert villager["defense"] is None
        assert villager["weakness"] is None
        assert villager["drop_item"] is None


# ---- Effect handler tests ----


def test_heal_player_effect(tmp_path: Path) -> None:
    """heal_player effect restores HP capped at max_hp."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("arena", hp=50, max_hp=100)
        apply_effect({"type": "heal_player", "amount": 30}, db)
        player = db.get_player()
        assert player["hp"] == 80

        # Healing past max_hp caps at max_hp
        apply_effect({"type": "heal_player", "amount": 50}, db)
        player = db.get_player()
        assert player["hp"] == 100


def test_damage_player_effect(tmp_path: Path) -> None:
    """damage_player effect reduces HP, minimum 0."""
    compiled_path = _compile_db(tmp_path)
    with GameDB(compiled_path) as db:
        db.init_player("arena", hp=100, max_hp=100)
        apply_effect({"type": "damage_player", "amount": 40}, db)
        player = db.get_player()
        assert player["hp"] == 60

        # Cannot go below 0
        apply_effect({"type": "damage_player", "amount": 200}, db)
        player = db.get_player()
        assert player["hp"] == 0


# ---- Engine combat tests ----


def test_combat_basic_damage(tmp_path: Path) -> None:
    """attack command deals weapon damage - NPC defense (min 1)."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    # Take the sword
    engine.process_command("take iron sword")

    # Attack the goblin (defense 0, sword damage 20)
    engine.process_command("attack goblin")
    output = _get_output(console)

    # Goblin has 10 HP, sword does 20, so goblin should die in one hit
    goblin = engine.db.get_npc("goblin")
    assert goblin["is_alive"] == 0
    assert "defeated" in output.lower()


def test_combat_defense_reduces_damage(tmp_path: Path) -> None:
    """NPC defense reduces incoming damage (damage - defense, min 1)."""
    compiled_path = _compile_db(tmp_path)
    engine, _console = _make_engine(compiled_path)

    # Take the sword
    engine.process_command("take iron sword")

    # Attack the dragon (defense 5, sword damage 20 -> 15 damage per hit)
    engine.process_command("attack ancient dragon")

    dragon = engine.db.get_npc("dragon")
    # Dragon started at 50 HP, took 15 damage -> 35 HP
    assert dragon["hp"] == 35
    assert dragon["is_alive"] == 1


def test_combat_weakness_doubles_damage(tmp_path: Path) -> None:
    """Weapon tags matching NPC weakness double the damage."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    # Move player to armory to get frost blade
    engine.db.update_player(current_room_id="armory")
    engine.process_command("take frost blade")

    # Move player back to arena
    engine.db.update_player(current_room_id="arena")

    # Attack dragon with frost blade (damage 15, defense 5 -> 10, x2 weakness = 20)
    engine.process_command("attack ancient dragon")
    output = _get_output(console)

    dragon = engine.db.get_npc("dragon")
    # Dragon started at 50 HP, took 20 damage -> 30 HP
    assert dragon["hp"] == 30
    assert "super effective" in output.lower()


def test_combat_npc_retaliates(tmp_path: Path) -> None:
    """NPC attacks player back after surviving an attack."""
    compiled_path = _compile_db(tmp_path)
    engine, _console = _make_engine(compiled_path)

    engine.process_command("take iron sword")
    engine.process_command("attack ancient dragon")

    player = engine.db.get_player()
    # Dragon does 25 damage to player (no player defense)
    assert player["hp"] == 75


def test_combat_npc_death_drops_loot(tmp_path: Path) -> None:
    """When NPC dies, its drop item is placed in the body container."""
    compiled_path = _compile_db(tmp_path)
    engine, _console = _make_engine(compiled_path)

    engine.process_command("take iron sword")

    # Kill dragon by repeatedly attacking
    # Dragon: 50 HP, sword does 15 per hit (20 - 5 defense)
    # Need 4 hits to kill (15, 15, 15, 15 = 60 > 50)
    for _ in range(4):
        dragon = engine.db.get_npc("dragon")
        if not dragon["is_alive"]:
            break
        engine.process_command("attack ancient dragon")

    dragon = engine.db.get_npc("dragon")
    assert dragon["is_alive"] == 0

    # Check body container exists with loot
    body = engine.db.get_item("dragon_body")
    assert body is not None
    assert body["is_container"] == 1

    # Gold hoard should be in the body container
    gold = engine.db.get_item("gold_hoard")
    assert gold is not None
    assert gold["container_id"] == "dragon_body"


def test_combat_player_death(tmp_path: Path) -> None:
    """Player HP reaching 0 triggers game over."""
    compiled_path = _compile_db(tmp_path)
    engine, _console = _make_engine(compiled_path)

    # Set player HP low enough that one dragon retaliation kills
    engine.db.update_player(hp=20)

    engine.process_command("take iron sword")
    engine.process_command("attack ancient dragon")

    # Dragon does 25 damage, player had 20 HP -> 0
    player = engine.db.get_player()
    assert player["hp"] <= 0


def test_combat_no_weapon(tmp_path: Path) -> None:
    """Attacking without a weapon shows appropriate message."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("attack goblin")
    output = _get_output(console)
    assert "no weapon" in output.lower()


def test_combat_nonexistent_target(tmp_path: Path) -> None:
    """Attacking a nonexistent NPC shows error message."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("attack ghost")
    output = _get_output(console)
    assert "nothing to attack" in output.lower()


def test_combat_npc_without_combat_stats(tmp_path: Path) -> None:
    """Attacking an NPC without combat stats falls back to trigger system."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("take iron sword")
    engine.process_command("attack villager")
    output = _get_output(console)

    # Should show the generic attack message (not combat damage)
    assert "attack" in output.lower()
    # Villager should still be alive (no stat-based combat)
    villager = engine.db.get_npc("villager")
    assert villager["is_alive"] == 1


# ---- Status command tests ----


def test_status_command(tmp_path: Path) -> None:
    """status command shows player HP."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("status")
    output = _get_output(console)
    assert "100" in output  # max_hp
    assert "hp" in output.lower()


# ---- Effect round-trip tests ----


def test_roundtrip_heal_player(tmp_path: Path) -> None:
    """Full round-trip: heal_player effect through engine command."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    # Damage player first
    engine.db.update_player(hp=50)

    engine.process_command("drink potion")
    player = engine.db.get_player()
    assert player["hp"] == 80
    assert "healing potion" in _get_output(console).lower()


def test_roundtrip_damage_player(tmp_path: Path) -> None:
    """Full round-trip: damage_player effect through engine command."""
    compiled_path = _compile_db(tmp_path)
    engine, console = _make_engine(compiled_path)

    engine.process_command("touch trap")
    player = engine.db.get_player()
    assert player["hp"] == 80
    assert "trap" in _get_output(console).lower()
