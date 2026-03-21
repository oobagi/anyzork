from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.generator.validator import validate_game


def test_validate_game_reports_command_reference_to_missing_item(tmp_path: Path) -> None:
    db = GameDB(tmp_path / "invalid_world.zork")
    try:
        db.initialize(
            game_name="Invalid World",
            author="tests",
            prompt="validator coverage",
            win_conditions='["game_won"]',
            region_count=1,
            room_count=1,
        )
        db.insert_flag(id="game_won", value="false")
        db.insert_room(
            id="foyer",
            name="Foyer",
            description="A quiet foyer.",
            short_description="A quiet foyer.",
            region="house",
            is_start=1,
        )
        db.init_player("foyer")
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
