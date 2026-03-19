from __future__ import annotations

import json
from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.generator.passes.quests import _insert_quests


def test_quest_insertion_sets_main_quest_win_condition(tmp_path: Path) -> None:
    db = GameDB(tmp_path / "quest_win_test.zork")
    db.initialize(
        game_name="Quest Win Test",
        author="tests",
        prompt="quest win condition",
    )

    quests = [
        {
            "id": "restore_archive",
            "name": "Restore Archive",
            "description": "Restore the place.",
            "quest_type": "main",
            "discovery_flag": None,
            "completion_flag": "main_restore_complete",
            "score_value": 0,
            "sort_order": 0,
            "objectives": [
                {
                    "id": "obj_restore",
                    "description": "Restore power.",
                    "completion_flag": "power_restored",
                    "order_index": 0,
                    "is_optional": 0,
                    "bonus_score": 0,
                }
            ],
        }
    ]
    flags = [
        {"id": "main_restore_complete", "value": "false", "description": "main complete"},
        {"id": "power_restored", "value": "false", "description": "power restored"},
    ]

    _insert_quests(db, quests, flags)
    db.set_meta("win_conditions", json.dumps(["main_restore_complete"]))

    assert json.loads(db.get_meta("win_conditions")) == ["main_restore_complete"]

    db.close()
