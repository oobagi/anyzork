from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.generator.passes.triggers import _insert_missing_flags_for_triggers


def test_insert_missing_flags_for_triggers_adds_referenced_flags(tmp_path: Path) -> None:
    db = GameDB(tmp_path / "triggers_pass_test.zork")
    db.initialize(
        game_name="Triggers Pass Test",
        author="tests",
        prompt="trigger flags",
    )

    inserted = _insert_missing_flags_for_triggers(
        db,
        [
            {
                "id": "trigger_a",
                "event_type": "flag_set",
                "event_data": {"flag": "power_restored"},
                "preconditions": [{"type": "not_flag", "flag": "observatory_open"}],
                "effects": [{"type": "set_flag", "flag": "observatory_open"}],
            }
        ],
        {"flags": []},
    )

    assert [flag["id"] for flag in inserted] == [
        "observatory_open",
        "power_restored",
    ]
    assert db.get_flag("power_restored") is not None
    assert db.get_flag("observatory_open") is not None

    db.close()
