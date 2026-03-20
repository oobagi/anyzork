from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.commands import check_precondition, resolve_command
from anyzork.engine.game import GameEngine
from tests.build_test_game import build_test_game


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


def test_brass_key_unlocks_workshop_exit(game_db: GameDB, engine: GameEngine) -> None:
    game_db.move_item("brass_key", "inventory", "")

    handled = engine._handle_use_on("brass key", "east", "entrance_hall")

    assert handled is True
    assert game_db.get_lock("workshop_lock")["is_locked"] == 0
    assert game_db.get_exit_by_direction("entrance_hall", "east")["is_locked"] == 0


def test_put_in_rejects_items_that_fail_container_whitelist(
    game_db: GameDB, engine: GameEngine
) -> None:
    game_db.move_item("tool_satchel", "inventory", "")
    game_db.move_item("chalk_stick", "inventory", "")

    engine._handle_put_in("chalk", "tool satchel", "entrance_hall")

    assert game_db.get_item("chalk_stick")["container_id"] is None
    assert game_db.get_item("chalk_stick")["room_id"] is None
    assert "The satchel only has clips for the repair coil." in _output(engine)


def test_dark_room_lighting_respects_required_power(game_db: GameDB, engine: GameEngine) -> None:
    game_db.move_item("field_lantern", "inventory", "")
    game_db.move_item("battery_pack", "inventory", "")
    game_db.update_player(current_room_id="black_stacks")

    engine.display_room("black_stacks")
    assert "It's pitch black. You can't see a thing." in _output(engine)

    _clear_output(engine)
    engine._handle_turn("field lantern", "on", "black_stacks")
    assert game_db.get_item("field_lantern")["toggle_state"] == "on"
    assert "repair coil" in _output(engine)

    _clear_output(engine)
    engine._handle_turn("field lantern", "off", "black_stacks")
    assert game_db.get_item("field_lantern")["toggle_state"] == "off"

    assert game_db.consume_item_quantity("battery_pack", 4) is True
    assert game_db.get_item_quantity("battery_pack") == 0

    _clear_output(engine)
    engine._handle_turn("field lantern", "on", "black_stacks")

    assert game_db.get_item("field_lantern")["toggle_state"] == "off"
    assert "The lantern stays dark. The battery pack is spent." in _output(engine)


def test_room_display_weaves_fallback_items_and_npcs_into_body(
    game_db: GameDB, engine: GameEngine
) -> None:
    game_db._mutate(
        "UPDATE items SET room_description = NULL, drop_description = NULL WHERE id = ?",
        ("brass_key",),
    )

    engine.display_room("entrance_hall", force_full=True)
    output = _output(engine)

    assert "You see:" not in output
    assert "Present:" not in output
    assert "Nearby, the brass key catches the eye." in output
    assert "Nearby, Curator Rowan lingers." in output


def test_help_summarizes_special_verbs_without_spoiling_raw_patterns(
    game_db: GameDB, engine: GameEngine
) -> None:
    game_db.insert_command(
        id="test_realize_help",
        verb="realize",
        pattern="realize Jaden left",
        preconditions="[]",
        effects="[]",
        success_message="",
        failure_message="",
        is_enabled=1,
    )
    game_db.insert_command(
        id="test_enter_help",
        verb="enter",
        pattern="enter code 7394",
        preconditions="[]",
        effects="[]",
        success_message="",
        failure_message="",
        context_room_id="entrance_hall",
        is_enabled=1,
    )
    game_db.insert_command(
        id="test_accuse_other_room",
        verb="accuse",
        pattern="accuse Curator Rowan",
        preconditions="[]",
        effects="[]",
        success_message="",
        failure_message="",
        context_room_id="observatory",
        is_enabled=1,
    )

    lines = engine._get_dsl_help_lines()

    assert "Special story actions unlock through clues" in lines
    assert "realize {conclusion}" in lines
    assert "enter code {code}" in lines
    assert "Jaden left" not in lines
    assert "7394" not in lines
    assert "accuse {suspect}" not in lines


def test_scene_prose_skips_entities_already_mentioned() -> None:
    prose = GameEngine._build_scene_prose(
        (
            "A stern ancestral portrait hangs over the mantel while "
            "Mr. Finch waits nearby."
        ),
        [{"name": "stern ancestral portrait"}],
        [{"name": "Mr. Finch"}],
    )

    assert prose == ""


def test_toggle_state_precondition_tracks_item_state(game_db: GameDB) -> None:
    game_db.move_item("field_lantern", "inventory", "")

    assert check_precondition(
        {"type": "toggle_state", "item": "field_lantern", "state": "off"},
        game_db,
    ) is True

    game_db.toggle_item_state("field_lantern", "on")

    assert check_precondition(
        {"type": "toggle_state", "item": "field_lantern", "state": "on"},
        game_db,
    ) is True


def test_item_accessible_precondition_allows_room_and_inventory_items(
    game_db: GameDB,
) -> None:
    assert check_precondition(
        {"type": "item_accessible", "item": "brass_key"},
        game_db,
    ) is True

    game_db.move_item("brass_key", "inventory", "")

    assert check_precondition(
        {"type": "item_accessible", "item": "brass_key"},
        game_db,
    ) is True


def test_dialogue_trigger_spawns_badge_and_case_key_once(
    game_db: GameDB, engine: GameEngine
) -> None:
    node = game_db.get_dialogue_node("rowan_badge_node")
    assert node is not None
    engine._apply_node_flags(node)
    engine._emit_event("dialogue_node", node_id="rowan_badge_node", npc_id="curator_rowan")

    badge = game_db.get_item("archive_badge")
    crate_key = game_db.get_item("crate_key")
    assert badge["room_id"] is None
    assert badge["is_visible"] == 1
    assert crate_key["room_id"] is None
    assert crate_key["is_visible"] == 1
    assert game_db.has_flag("badge_received") is True
    assert game_db.has_flag("badge_given") is True
    assert game_db._fetchone(
        "SELECT executed FROM triggers WHERE id = ?",
        ("trigger_issue_badge",),
    )["executed"] == 1

    game_db.remove_item("archive_badge")
    game_db.remove_item("crate_key")
    engine._emit_event("dialogue_node", node_id="rowan_badge_node", npc_id="curator_rowan")

    badge = game_db.get_item("archive_badge")
    crate_key = game_db.get_item("crate_key")
    assert badge["is_visible"] == 0
    assert badge["room_id"] is None
    assert crate_key["is_visible"] == 0
    assert crate_key["room_id"] is None


def test_interaction_matrix_discovers_side_quest_and_consumes_chalk(
    game_db: GameDB, engine: GameEngine
) -> None:
    engine._init_quest_state()
    game_db.move_item("chalk_stick", "inventory", "")

    handled = engine._handle_interaction("chalk", "mural", "black_stacks")
    engine._check_quests()

    assert handled is True
    assert game_db.get_item_quantity("chalk_stick") == 2
    assert game_db.has_flag("mural_revealed") is True

    quest = game_db.get_quest("annotate_mural")
    assert quest is not None
    assert quest["status"] == "active"


def test_item_taken_trigger_discovers_lens_side_quest(
    game_db: GameDB, engine: GameEngine
) -> None:
    engine._init_quest_state()
    game_db.move_item("focusing_lens", "inventory", "")
    engine._emit_event("item_taken", item_id="focusing_lens")
    engine._check_quests()

    assert game_db.has_flag("lens_found") is True

    quest = game_db.get_quest("calibrate_archive_lens")
    assert quest is not None
    assert quest["status"] == "active"


def test_install_command_unlocks_observatory_and_completes_main_quest(
    game_db: GameDB, engine: GameEngine
) -> None:
    engine._init_quest_state()
    game_db.move_item("repair_coil", "inventory", "")
    game_db.update_player(current_room_id="generator_room")

    node = game_db.get_dialogue_node("rowan_badge_node")
    assert node is not None
    engine._apply_node_flags(node)
    engine._emit_event("dialogue_node", node_id="rowan_badge_node", npc_id="curator_rowan")

    result = resolve_command(
        "install repair coil",
        game_db,
        current_room_id="generator_room",
        emit_event=engine._emit_event,
    )
    engine._check_quests()

    assert result.success is True
    assert "set_flag" in result.effects_applied
    assert game_db.get_item("repair_coil")["is_visible"] == 0
    assert game_db.has_flag("power_restored") is True
    assert game_db.get_lock("observatory_lock")["is_locked"] == 0
    assert game_db.has_flag("observatory_open") is True

    quest = game_db.get_quest("restore_archive")
    assert quest is not None
    assert quest["status"] == "completed"
    assert game_db.has_flag("main_restore_complete") is True

    score_entry = game_db._fetchone(
        "SELECT value FROM score_entries WHERE reason = ?",
        ("quest:restore_archive",),
    )
    assert score_entry == {"value": 15}

    game_db.update_player(moves=1)
    engine._check_quests()
    score_count = game_db._fetchone(
        "SELECT COUNT(*) AS count FROM score_entries WHERE reason = ?",
        ("quest:restore_archive",),
    )
    assert score_count == {"count": 1}
