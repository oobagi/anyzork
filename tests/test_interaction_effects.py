"""Tests for dynamic effects on interaction responses.

Covers:
1. kill_target effect kills an NPC when weapon used on character
2. destroy_target scatters container contents and removes the item
3. damage_target reduces NPC HP
4. open_target opens a container
5. Interaction response without effects still works (backward compatible)
6. ZorkScript parser handles effect lines in interaction blocks
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest
from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.commands import apply_effect
from anyzork.engine.game import GameEngine
from anyzork.zorkscript import parse_zorkscript
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


# ---------------------------------------- helpers


def _add_weapon_and_npc(db: GameDB) -> None:
    """Insert a weapon item (inventory) and hostile NPC for testing."""
    db.insert_item(
        id="test_sword",
        name="iron sword",
        description="A sturdy iron sword.",
        examine_description="A well-balanced blade.",
        room_id=None,
        category="weapon",
        item_tags=json.dumps(["weapon"]),
    )
    db.insert_npc(
        id="test_bandit",
        name="Bandit",
        description="A menacing bandit.",
        examine_description="Scarred and dangerous.",
        room_id="entrance_hall",
        default_dialogue="The bandit snarls at you.",
        category="hostile",
        hp=30,
    )


def _add_weapon_interaction_kill(db: GameDB) -> None:
    """Insert an interaction response: weapon tag on hostile category = kill."""
    db.insert_interaction_response(
        id="weapon_on_hostile",
        item_tag="weapon",
        target_category="hostile",
        response="You strike {target} with the {item}. They collapse.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
        effects=json.dumps([{"type": "kill_target"}]),
    )


def _add_weapon_interaction_damage(db: GameDB) -> None:
    """Insert an interaction response: weapon tag on hostile category = damage."""
    db.insert_interaction_response(
        id="weapon_on_hostile_dmg",
        item_tag="weapon",
        target_category="hostile",
        response="You slash at {target} with the {item}.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
        effects=json.dumps([{"type": "damage_target", "amount": 15}]),
    )


def _add_destructible_container(db: GameDB) -> None:
    """Insert a container with contents and a weapon interaction to destroy it."""
    db.insert_item(
        id="old_cabinet",
        name="old cabinet",
        description="A rickety wooden cabinet.",
        examine_description="The cabinet looks ready to fall apart.",
        room_id="entrance_hall",
        category="furniture",
        is_container=1,
        is_open=0,
        has_lid=1,
        is_takeable=0,
    )
    db.insert_item(
        id="hidden_gem",
        name="hidden gem",
        description="A sparkling gemstone.",
        examine_description="It catches the light beautifully.",
        room_id=None,
        container_id="old_cabinet",
        category="treasure",
    )
    db.insert_item(
        id="dusty_scroll",
        name="dusty scroll",
        description="A rolled-up parchment.",
        examine_description="The scroll is brittle with age.",
        room_id=None,
        container_id="old_cabinet",
        category="document",
    )
    db.insert_interaction_response(
        id="weapon_on_furniture",
        item_tag="weapon",
        target_category="furniture",
        response="You smash the {item} against the {target}. It splinters apart.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
        effects=json.dumps([{"type": "destroy_target"}]),
    )


# ---------------------------------------- kill_target


def test_kill_target_kills_npc_via_interaction(
    game_db: GameDB, engine: GameEngine
) -> None:
    """Using a weapon on an NPC with kill_target should kill the NPC."""
    _add_weapon_and_npc(game_db)
    _add_weapon_interaction_kill(game_db)

    npc_before = game_db.get_npc("test_bandit")
    assert npc_before["is_alive"] == 1

    handled = engine._handle_interaction("iron sword", "Bandit", "entrance_hall")

    assert handled is True
    npc_after = game_db.get_npc("test_bandit")
    assert npc_after["is_alive"] == 0

    out = _output(engine)
    assert "You strike Bandit with the iron sword" in out


def test_kill_target_spawns_body(game_db: GameDB, engine: GameEngine) -> None:
    """kill_target should spawn a searchable body container."""
    _add_weapon_and_npc(game_db)
    _add_weapon_interaction_kill(game_db)

    engine._handle_interaction("iron sword", "Bandit", "entrance_hall")

    body = game_db.get_item("test_bandit_body")
    assert body is not None
    assert body["is_container"] == 1
    assert body["room_id"] == "entrance_hall"


# ---------------------------------------- damage_target


def test_damage_target_reduces_npc_hp(
    game_db: GameDB, engine: GameEngine
) -> None:
    """damage_target should reduce NPC HP by the specified amount."""
    _add_weapon_and_npc(game_db)
    _add_weapon_interaction_damage(game_db)

    npc_before = game_db.get_npc("test_bandit")
    assert npc_before["hp"] == 30

    handled = engine._handle_interaction("iron sword", "Bandit", "entrance_hall")

    assert handled is True
    npc_after = game_db.get_npc("test_bandit")
    assert npc_after["hp"] == 15

    out = _output(engine)
    assert "You slash at Bandit" in out


def test_damage_target_kills_when_hp_reaches_zero(
    game_db: GameDB, engine: GameEngine
) -> None:
    """damage_target should kill the NPC when HP drops to 0."""
    _add_weapon_and_npc(game_db)
    # Override damage to match full HP.
    game_db.insert_interaction_response(
        id="weapon_on_hostile_lethal",
        item_tag="weapon",
        target_category="hostile",
        response="You deliver a killing blow to {target} with the {item}.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
        effects=json.dumps([{"type": "damage_target", "amount": 30}]),
    )

    engine._handle_interaction("iron sword", "Bandit", "entrance_hall")

    npc = game_db.get_npc("test_bandit")
    assert npc["is_alive"] == 0


# ---------------------------------------- destroy_target


def test_destroy_target_scatters_contents(
    game_db: GameDB, engine: GameEngine
) -> None:
    """destroy_target should scatter container contents into the room."""
    _add_weapon_and_npc(game_db)
    _add_destructible_container(game_db)

    # Verify items start inside the container.
    gem = game_db.get_item("hidden_gem")
    assert gem["container_id"] == "old_cabinet"
    scroll = game_db.get_item("dusty_scroll")
    assert scroll["container_id"] == "old_cabinet"

    handled = engine._handle_interaction("iron sword", "old cabinet", "entrance_hall")

    assert handled is True

    # Items should now be in the room, not in the container.
    gem = game_db.get_item("hidden_gem")
    assert gem["room_id"] == "entrance_hall"
    assert gem["container_id"] is None

    scroll = game_db.get_item("dusty_scroll")
    assert scroll["room_id"] == "entrance_hall"
    assert scroll["container_id"] is None


def test_destroy_target_removes_container(
    game_db: GameDB, engine: GameEngine
) -> None:
    """destroy_target should remove (hide) the container item."""
    _add_weapon_and_npc(game_db)
    _add_destructible_container(game_db)

    engine._handle_interaction("iron sword", "old cabinet", "entrance_hall")

    cabinet = game_db.get_item("old_cabinet")
    assert cabinet["is_visible"] == 0

    out = _output(engine)
    assert "splinters apart" in out


# ---------------------------------------- open_target


def test_open_target_opens_container(
    game_db: GameDB, engine: GameEngine
) -> None:
    """open_target should open a closed container."""
    _add_weapon_and_npc(game_db)

    # Insert a closed lockbox and an interaction to open it.
    game_db.insert_item(
        id="test_lockbox",
        name="rusty lockbox",
        description="A rusted lockbox.",
        examine_description="The lock is broken.",
        room_id="entrance_hall",
        category="furniture",
        is_container=1,
        is_open=0,
        has_lid=1,
        is_takeable=0,
    )
    game_db.insert_interaction_response(
        id="weapon_opens_furniture",
        item_tag="weapon",
        target_category="furniture",
        response="You pry the {target} open with the {item}.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
        effects=json.dumps([{"type": "open_target"}]),
    )

    lockbox_before = game_db.get_item("test_lockbox")
    assert lockbox_before["is_open"] == 0

    handled = engine._handle_interaction("iron sword", "rusty lockbox", "entrance_hall")

    assert handled is True
    lockbox_after = game_db.get_item("test_lockbox")
    assert lockbox_after["is_open"] == 1


# ---------------------------------------- backward compatibility


def test_interaction_without_effects_still_works(
    game_db: GameDB, engine: GameEngine
) -> None:
    """Interaction responses without effects should work exactly as before."""
    # The test game already has marking_tool_scenery without effects.
    # Move chalk to inventory and target the mural.
    game_db.move_item("chalk_stick", "inventory", "")

    handled = engine._handle_interaction(
        "chalk stick", "constellation mural", "black_stacks"
    )

    assert handled is True
    out = _output(engine)
    assert "hidden service path" in out
    # The flag should be set (old behavior).
    assert game_db.has_flag("mural_revealed")


# ---------------------------------------- apply_effect target-aware no-ops


def test_kill_target_noop_without_target_id(game_db: GameDB) -> None:
    """kill_target should silently no-op when _target_id is absent."""
    effect = {"type": "kill_target"}
    msgs = apply_effect(effect, game_db, {}, command_id="test")
    assert msgs == []


def test_destroy_target_noop_without_target_id(game_db: GameDB) -> None:
    """destroy_target should silently no-op when _target_id is absent."""
    effect = {"type": "destroy_target"}
    msgs = apply_effect(effect, game_db, {}, command_id="test")
    assert msgs == []


def test_damage_target_noop_without_target_id(game_db: GameDB) -> None:
    """damage_target should silently no-op when _target_id is absent."""
    effect = {"type": "damage_target", "amount": 10}
    msgs = apply_effect(effect, game_db, {}, command_id="test")
    assert msgs == []


def test_open_target_noop_without_target_id(game_db: GameDB) -> None:
    """open_target should silently no-op when _target_id is absent."""
    effect = {"type": "open_target"}
    msgs = apply_effect(effect, game_db, {}, command_id="test")
    assert msgs == []


# ---------------------------------------- ZorkScript parser


def test_zorkscript_parses_interaction_effects() -> None:
    """The ZorkScript parser should handle effect lines in interaction blocks."""
    source = """
    game { title "Test" }
    player { start test_room }
    room test_room { description "A room." }

    interaction weapon_on_character {
      tag      "weapon"
      target   "character"
      response "You strike {target} with the {item}."
      effect   kill_target()
      effect   add_score(10)
    }
    """
    spec = parse_zorkscript(source)
    responses = spec["interaction_responses"]
    assert len(responses) == 1
    resp = responses[0]
    assert resp["id"] == "weapon_on_character"
    assert resp["item_tag"] == "weapon"
    assert resp["target_category"] == "character"
    assert "effects" in resp
    effects = resp["effects"]
    assert len(effects) == 2
    assert effects[0] == {"type": "kill_target"}
    assert effects[1] == {"type": "add_score", "points": 10}


def test_zorkscript_interaction_without_effects_has_no_key() -> None:
    """Interaction blocks without effect lines should not have an effects key."""
    source = """
    game { title "Test" }
    player { start test_room }
    room test_room { description "A room." }

    interaction light_on_scenery {
      tag      "light_source"
      target   "scenery"
      response "You illuminate the {target}."
    }
    """
    spec = parse_zorkscript(source)
    responses = spec["interaction_responses"]
    assert len(responses) == 1
    assert "effects" not in responses[0]


def test_zorkscript_destroy_target_effect() -> None:
    """destroy_target() should parse correctly with no arguments."""
    source = """
    game { title "Test" }
    player { start test_room }
    room test_room { description "A room." }

    interaction weapon_on_furniture {
      tag      "weapon"
      target   "furniture"
      response "You smash the {item} against the {target}."
      effect   destroy_target()
    }
    """
    spec = parse_zorkscript(source)
    effects = spec["interaction_responses"][0]["effects"]
    assert len(effects) == 1
    assert effects[0] == {"type": "destroy_target"}


def test_zorkscript_damage_target_effect() -> None:
    """damage_target(N) should parse the amount argument."""
    source = """
    game { title "Test" }
    player { start test_room }
    room test_room { description "A room." }

    interaction weapon_on_hostile {
      tag      "weapon"
      target   "hostile"
      response "You slash at {target}."
      effect   damage_target(15)
    }
    """
    spec = parse_zorkscript(source)
    effects = spec["interaction_responses"][0]["effects"]
    assert len(effects) == 1
    assert effects[0] == {"type": "damage_target", "amount": 15}


# ---------------------------------------- effects column in DB


def test_effects_column_stored_and_retrieved(game_db: GameDB) -> None:
    """Effects JSON should round-trip through the interaction_responses table."""
    effects_data = [{"type": "kill_target"}, {"type": "add_score", "points": 5}]
    game_db.insert_interaction_response(
        id="test_roundtrip",
        item_tag="test_tag",
        target_category="test_cat",
        response="Test response.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
        effects=json.dumps(effects_data),
    )

    row = game_db.get_interaction_response("test_tag", "test_cat")
    assert row is not None
    assert row["effects"] is not None
    parsed = json.loads(row["effects"])
    assert parsed == effects_data


def test_effects_column_null_when_not_provided(game_db: GameDB) -> None:
    """Effects column should be NULL when no effects are given."""
    game_db.insert_interaction_response(
        id="test_no_effects",
        item_tag="no_fx_tag",
        target_category="no_fx_cat",
        response="Nothing special.",
        consumes=0,
        score_change=0,
        flag_to_set=None,
    )

    row = game_db.get_interaction_response("no_fx_tag", "no_fx_cat")
    assert row is not None
    assert row["effects"] is None
