from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.validation import validate_game


def _make_base_db(tmp_path: Path, name: str = "test_world.zork") -> GameDB:
    """Create a minimal valid GameDB for validator tests."""
    db = GameDB(tmp_path / name)
    db.initialize(
        game_name="Test World",
        author="tests",
        prompt="validator coverage",
        win_conditions='["game_won"]',
        room_count=2,
    )
    db.insert_flag(id="game_won", value="false")
    db.insert_room(
        id="foyer",
        name="Foyer",
        description="A quiet foyer.",
        short_description="A quiet foyer.",
        is_start=1,
    )
    db.insert_room(
        id="vault",
        name="Vault",
        description="A dark vault.",
        short_description="A dark vault.",
    )
    db.insert_exit(
        id="foyer_vault",
        from_room_id="foyer",
        to_room_id="vault",
        direction="north",
        is_locked=0,
        is_hidden=0,
    )
    db.insert_exit(
        id="vault_foyer",
        from_room_id="vault",
        to_room_id="foyer",
        direction="south",
        is_locked=0,
        is_hidden=0,
    )
    db.init_player("foyer")
    return db


def test_validate_game_reports_command_reference_to_missing_item(tmp_path: Path) -> None:
    db = _make_base_db(tmp_path, "invalid_world.zork")
    try:
        db.insert_command(
            id="read_missing",
            verb="read",
            pattern="read note",
            preconditions='[{"type": "item_accessible", "item": "missing_note"}]',
            effects="[]",
            success_message="You read the note.",
            failure_message="",
            is_enabled=1,
        )

        messages = validate_game(db)
        assert any("missing_note" in str(message) for message in messages)
    finally:
        db.close()


def test_validate_combination_lock_missing_code(tmp_path: Path) -> None:
    """Combination-type lock without a combination value should produce an error."""
    db = _make_base_db(tmp_path, "combo_no_code.zork")
    try:
        db.insert_exit(
            id="foyer_vault_locked",
            from_room_id="foyer",
            to_room_id="vault",
            direction="east",
            is_locked=1,
            is_hidden=0,
        )
        db.insert_lock(
            id="vault_combo_lock",
            lock_type="combination",
            target_exit_id="foyer_vault_locked",
            locked_message="A dial blocks the way.",
            unlock_message="Click.",
            is_locked=1,
            consume_key=0,
            # No combination value — should fail validation.
        )
        messages = validate_game(db)
        assert any(
            "no combination code" in str(m) for m in messages
        ), f"Expected combination code error, got: {messages}"
    finally:
        db.close()


def test_validate_combination_lock_with_key_warns(tmp_path: Path) -> None:
    """Combination-type lock that also has a key_item_id should produce a warning."""
    db = _make_base_db(tmp_path, "combo_with_key.zork")
    try:
        db.insert_item(
            id="spare_key",
            name="Spare Key",
            description="A key.",
            examine_description="A key.",
            room_id="foyer",
            is_takeable=1,
        )
        db.insert_exit(
            id="foyer_vault_locked2",
            from_room_id="foyer",
            to_room_id="vault",
            direction="east",
            is_locked=1,
            is_hidden=0,
        )
        db.insert_lock(
            id="vault_combo_key_lock",
            lock_type="combination",
            target_exit_id="foyer_vault_locked2",
            combination="999",
            key_item_id="spare_key",
            locked_message="A dial blocks the way.",
            unlock_message="Click.",
            is_locked=1,
            consume_key=0,
        )
        messages = validate_game(db)
        assert any(
            "combination" in str(m) and "key" in str(m).lower() for m in messages
        ), f"Expected warning about combo+key conflict, got: {messages}"
    finally:
        db.close()


def test_validate_container_both_key_and_combination_warns(tmp_path: Path) -> None:
    """Locked container with both key_item_id and combination should warn."""
    db = _make_base_db(tmp_path, "container_both.zork")
    try:
        db.insert_item(
            id="chest_key",
            name="Chest Key",
            description="A key.",
            examine_description="A key.",
            room_id="foyer",
            is_takeable=1,
        )
        db.insert_item(
            id="chest",
            name="Chest",
            description="A chest.",
            examine_description="A chest.",
            room_id="foyer",
            is_container=1,
            is_locked=1,
            key_item_id="chest_key",
            combination="123",
        )
        messages = validate_game(db)
        assert any(
            "both" in str(m).lower() and "key_item_id" in str(m) for m in messages
        ), f"Expected warning about both key and combo, got: {messages}"
    finally:
        db.close()
