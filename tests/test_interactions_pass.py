from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.generator.passes.interactions import _insert_interactions


def test_insert_interactions_ignores_legacy_unsaved_fields(tmp_path: Path) -> None:
    db = GameDB(tmp_path / "interactions_pass_test.zork")
    db.initialize(
        game_name="Interactions Pass Test",
        author="tests",
        prompt="schema drift",
    )
    db.insert_room(
        id="start",
        name="Start",
        description="Start room.",
        short_description="Start room.",
        first_visit_text=None,
        region="test",
        is_dark=0,
        is_start=1,
    )

    inserted = _insert_interactions(
        db,
        [
            {
                "id": "marking_tool_scenery",
                "item_tag": "marking_tool",
                "target_category": "scenery",
                "response": "You mark the {target} with the {item}.",
                "priority": 5,
                "room_id": "start",
                "requires_state": "on",
                "consumes": 1,
                "consume_amount": 2,
                "score_change": 3,
                "flag_to_set": "mural_revealed",
            }
        ],
        {"rooms": [{"id": "start"}]},
    )

    assert inserted[0]["id"] == "marking_tool_scenery"

    row = db._fetchone(
        "SELECT * FROM interaction_responses WHERE id = ?",
        ("marking_tool_scenery",),
    )
    assert row == {
        "id": "marking_tool_scenery",
        "item_tag": "marking_tool",
        "target_category": "scenery",
        "response": "You mark the {target} with the {item}.",
        "consumes": 2,
        "score_change": 3,
        "flag_to_set": "mural_revealed",
        "effects": None,
    }

    db.close()
