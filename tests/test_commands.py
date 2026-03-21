from __future__ import annotations

import json
from pathlib import Path

import pytest

from anyzork.db.schema import GameDB
from anyzork.engine.commands import check_precondition, resolve_command


@pytest.fixture
def command_db(tmp_path: Path) -> GameDB:
    db = GameDB(tmp_path / "commands.zork")
    db.initialize(
        game_name="Command Fixture",
        author="tests",
        prompt="command coverage",
        win_conditions='["game_won"]',
        region_count=1,
        room_count=2,
    )
    db.insert_flag(id="game_won", value="false")
    db.insert_flag(id="door_open", value="false")
    db.insert_room(
        id="foyer",
        name="Foyer",
        description="A quiet foyer.",
        short_description="A quiet foyer.",
        region="house",
        is_start=1,
    )
    db.insert_room(
        id="study",
        name="Study",
        description="A cramped study.",
        short_description="A cramped study.",
        region="house",
    )
    db.insert_exit(
        id="foyer_study",
        from_room_id="foyer",
        to_room_id="study",
        direction="north",
        is_locked=1,
        is_hidden=0,
    )
    db.insert_lock(
        id="study_lock",
        lock_type="flag",
        target_exit_id="foyer_study",
        required_flags=json.dumps(["door_open"]),
        locked_message="The study door stays shut.",
        unlock_message="The study door clicks open.",
        is_locked=1,
        consume_key=0,
    )
    db.insert_item(
        id="lever",
        name="lever",
        description="A brass lever.",
        examine_description="A brass lever on the wall.",
        room_id="foyer",
        is_takeable=0,
        is_visible=1,
    )
    db.insert_item(
        id="lantern",
        name="lantern",
        description="A hand lantern.",
        examine_description="A brass lantern.",
        room_id="foyer",
        is_takeable=1,
        is_visible=1,
        is_toggleable=1,
        toggle_state="off",
    )
    db.insert_item(
        id="battery_pack",
        name="battery pack",
        description="A battery pack.",
        examine_description="A battery pack with charges.",
        room_id="foyer",
        quantity=3,
        max_quantity=3,
        quantity_unit="charges",
    )
    db.insert_command(
        id="open_door",
        verb="pull",
        pattern="pull lever",
        preconditions="[]",
        effects=json.dumps(
            [
                {"type": "set_flag", "flag": "door_open"},
                {"type": "unlock", "lock": "study_lock"},
            ]
        ),
        success_message="The study door clicks open.",
        failure_message="",
        context_room_ids=json.dumps(["foyer"]),
        is_enabled=1,
    )
    db.insert_command(
        id="move_north",
        verb="go",
        pattern="go north",
        preconditions=json.dumps([{"type": "has_flag", "flag": "door_open"}]),
        effects=json.dumps([{"type": "move_player", "room": "study"}]),
        success_message="You step into the study.",
        failure_message="The study door stays shut.",
        context_room_ids=json.dumps(["foyer"]),
        is_enabled=1,
    )
    db.insert_command(
        id="toggle_lantern",
        verb="switch",
        pattern="switch lantern on",
        preconditions=json.dumps([{"type": "toggle_state", "item": "lantern", "state": "off"}]),
        effects=json.dumps([{"type": "set_toggle_state", "item": "lantern", "state": "on"}]),
        success_message="The lantern glows.",
        failure_message="",
        is_enabled=1,
    )
    db.insert_command(
        id="use_charge",
        verb="use",
        pattern="use battery pack",
        preconditions=json.dumps([{"type": "item_accessible", "item": "battery_pack"}]),
        effects=json.dumps([{"type": "consume_quantity", "item": "battery_pack", "amount": 1}]),
        success_message="One charge drains away.",
        failure_message="",
        is_enabled=1,
    )
    db.init_player("foyer")
    try:
        yield db
    finally:
        db.close()


def test_resolve_command_respects_room_scope_and_effects(command_db: GameDB) -> None:
    result = resolve_command("pull lever", command_db, current_room_id="foyer")

    assert result.success is True
    assert "set_flag" in result.effects_applied
    assert "unlock" in result.effects_applied
    assert command_db.has_flag("door_open") is True
    assert command_db.get_exit_by_direction("foyer", "north")["is_locked"] == 0


def test_resolve_command_applies_move_player_when_preconditions_pass(command_db: GameDB) -> None:
    resolve_command("pull lever", command_db, current_room_id="foyer")

    result = resolve_command("go north", command_db, current_room_id="foyer")

    assert result.success is True
    assert command_db.get_player()["current_room_id"] == "study"


def test_check_precondition_tracks_toggle_state_and_item_accessible(command_db: GameDB) -> None:
    assert check_precondition(
        {"type": "toggle_state", "item": "lantern", "state": "off"},
        command_db,
    )
    assert check_precondition(
        {"type": "item_accessible", "item": "battery_pack"},
        command_db,
    )


def test_resolve_command_consumes_quantity_and_updates_toggle_state(command_db: GameDB) -> None:
    toggle = resolve_command("switch lantern on", command_db, current_room_id="foyer")
    consume = resolve_command("use battery pack", command_db, current_room_id="foyer")

    assert toggle.success is True
    assert consume.success is True
    assert command_db.get_item("lantern")["toggle_state"] == "on"
    assert command_db.get_item_quantity("battery_pack") == 2
