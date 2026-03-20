from __future__ import annotations

import json
from pathlib import Path

import pytest

from anyzork.db.schema import GameDB
from anyzork.generator.validator import validate_game


@pytest.fixture
def game_db(tmp_path: Path) -> GameDB:
    """Build a minimal valid world for validator-focused tests."""
    test_path = tmp_path / "validator_test_game.zork"
    db = GameDB(test_path)
    db.initialize(
        game_name="Validator Fixture",
        author="tests",
        prompt="A small deterministic fixture for validator coverage.",
        seed="validator-fixture",
        win_conditions=json.dumps(["main_quest_complete"]),
        max_score=10,
        region_count=1,
        room_count=3,
    )

    db.insert_room(
        id="briefing",
        name="Briefing Room",
        description="A compact prep room with a mission board.",
        short_description="A compact prep room.",
        first_visit_text=None,
        region="test_range",
        is_dark=0,
        is_start=1,
    )
    db.insert_room(
        id="hall",
        name="Training Hall",
        description="A quiet hall linking the prep spaces together.",
        short_description="A quiet training hall.",
        first_visit_text=None,
        region="test_range",
        is_dark=0,
        is_start=0,
    )
    db.insert_room(
        id="vault",
        name="Supply Vault",
        description="A locked-down storage room for test supplies.",
        short_description="A secure supply vault.",
        first_visit_text=None,
        region="test_range",
        is_dark=0,
        is_start=0,
    )

    db.insert_exit(
        id="briefing_to_hall",
        from_room_id="briefing",
        to_room_id="hall",
        direction="east",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="hall_to_briefing",
        from_room_id="hall",
        to_room_id="briefing",
        direction="west",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="hall_to_vault",
        from_room_id="hall",
        to_room_id="vault",
        direction="north",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="vault_to_hall",
        from_room_id="vault",
        to_room_id="hall",
        direction="south",
        is_locked=0,
        is_hidden=0,
    )

    db.init_player("briefing")

    db.insert_item(
        id="vault_key",
        name="Vault Key",
        description="A stamped brass key.",
        examine_description="A stamped brass key for training locks.",
        room_id="vault",
        container_id=None,
        is_takeable=1,
        is_visible=1,
        is_consumed_on_use=0,
        is_container=0,
        is_open=0,
        has_lid=0,
        is_locked=0,
        lock_message=None,
        open_message=None,
        search_message=None,
        take_message=None,
        drop_message=None,
        weight=1,
        category="key",
        room_description="A brass key rests on a shelf.",
        read_description=None,
        key_item_id=None,
        consume_key=0,
        unlock_message=None,
        accepts_items=None,
        reject_message=None,
        home_room_id="vault",
        drop_description="A brass key lies here.",
        is_toggleable=0,
        toggle_state=None,
        toggle_on_message=None,
        toggle_off_message=None,
        toggle_states=None,
        toggle_messages=None,
        requires_item_id=None,
        requires_message=None,
        item_tags=json.dumps(["key"]),
        quantity=None,
        max_quantity=None,
        quantity_unit=None,
        depleted_message=None,
        quantity_description=None,
    )

    db.insert_flag(
        id="quest_discovered",
        value="false",
        description="Whether the training quest is visible.",
    )
    db.insert_flag(
        id="main_quest_complete",
        value="false",
        description="Whether the training quest is complete.",
    )
    db.insert_flag(
        id="find_relic_complete",
        value="false",
        description="Whether the objective is complete.",
    )

    db.insert_quest(
        id="main_training",
        name="Complete Training",
        description="Finish the validator fixture objective.",
        quest_type="main",
        status="active",
        discovery_flag="quest_discovered",
        completion_flag="main_quest_complete",
        score_value=10,
        sort_order=0,
    )
    db.insert_quest_objective(
        id="obj_find_relic",
        quest_id="main_training",
        description="Recover the relic from the vault.",
        completion_flag="find_relic_complete",
        order_index=0,
        is_optional=0,
        bonus_score=0,
    )

    try:
        yield db
    finally:
        db.close()


def _messages(errors: list) -> list[str]:
    return [str(err) for err in errors]


def test_validate_game_accepts_minimal_valid_fixture(game_db: GameDB) -> None:
    assert validate_game(game_db) == []


def test_validate_game_reports_unreachable_lock_key(game_db: GameDB) -> None:
    game_db._mutate("UPDATE exits SET is_locked = 1 WHERE id = ?", ("hall_to_vault",))
    game_db.insert_lock(
        id="bad_key_lock",
        lock_type="key",
        target_exit_id="hall_to_vault",
        key_item_id="vault_key",
        puzzle_id=None,
        combination=None,
        required_flags=None,
        locked_message="Locked.",
        unlock_message="Unlocked.",
        is_locked=1,
        consume_key=0,
    )

    errors = validate_game(game_db)
    messages = _messages(errors)

    assert any(err.category == "lock" for err in errors)
    assert any(
        "vault_key" in msg and "before its lock in any valid unlock order" in msg
        for msg in messages
    )
    assert any("No valid unlock order exists for key locks" in msg for msg in messages)


def test_validate_game_reports_invalid_discover_quest_target(game_db: GameDB) -> None:
    game_db.insert_command(
        id="discover_missing_quest",
        verb="inspect",
        pattern="inspect {target}",
        preconditions="[]",
        effects='[{"type": "discover_quest", "quest": "missing_quest"}]',
        success_message="",
        failure_message="",
        context_room_ids=None,
        puzzle_id=None,
        priority=0,
        is_enabled=1,
        one_shot=0,
        executed=0,
        done_message="",
    )

    errors = validate_game(game_db)
    messages = _messages(errors)

    assert any(err.category == "command" for err in errors)
    assert any(
        "discover_quest" in msg and "missing_quest" in msg for msg in messages
    )


def test_validate_game_reports_inventory_not_item_in_container_use(
    game_db: GameDB,
) -> None:
    game_db.insert_command(
        id="search_keychain_for_note",
        verb="search",
        pattern="search keychain",
        preconditions=json.dumps(
            [
                {
                    "type": "not_item_in_container",
                    "item": "vault_key",
                    "container": "_inventory",
                }
            ]
        ),
        effects='[{"type": "print", "message": "You search the keychain."}]',
        success_message="",
        failure_message="You are not sure what to search.",
        context_room_ids=None,
        puzzle_id=None,
        priority=0,
        is_enabled=1,
        one_shot=0,
        executed=0,
        done_message="",
    )

    errors = validate_game(game_db)
    messages = _messages(errors)

    assert any(err.category == "command" for err in errors)
    assert any("not_item_in_container" in msg and "inventory" in msg for msg in messages)


def test_validate_game_reports_missing_quest_flags(game_db: GameDB) -> None:
    game_db._mutate(
        """
        UPDATE quests
        SET discovery_flag = ?, completion_flag = ?
        WHERE id = ?
        """,
        ("missing_discovery_flag", "missing_completion_flag", "main_training"),
    )
    game_db._mutate(
        "UPDATE quest_objectives SET completion_flag = ? WHERE id = ?",
        ("missing_objective_flag", "obj_find_relic"),
    )

    errors = validate_game(game_db)
    messages = _messages(errors)

    assert any(err.category == "quest" for err in errors)
    assert any("discovery_flag" in msg for msg in messages)
    assert any("completion_flag" in msg for msg in messages)


def test_validate_game_reports_blank_no_op_command(game_db: GameDB) -> None:
    game_db.insert_command(
        id="blank_shake",
        verb="shake",
        pattern="shake {target}",
        preconditions="[]",
        effects="[]",
        success_message="",
        failure_message="Nothing happens when you shake that.",
        context_room_ids=None,
        is_enabled=1,
    )

    errors = validate_game(game_db)
    messages = _messages(errors)

    assert any(err.category == "command" for err in errors)
    assert any(
        "can succeed without producing any effect or visible message" in msg
        for msg in messages
    )


def test_validate_game_warns_when_room_prose_already_mentions_takeable_item(
    game_db: GameDB,
) -> None:
    game_db._mutate(
        "UPDATE rooms SET description = ? WHERE id = ?",
        (
            "A compact prep room where the Vault Key rests on a shelf beneath the mission board.",
            "vault",
        ),
    )

    errors = validate_game(game_db)
    messages = _messages(errors)

    assert any(err.severity == "warning" and err.category == "item" for err in errors)
    assert any("already named in room 'vault' prose" in msg for msg in messages)
