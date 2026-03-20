from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.generator.passes.triggers import (
    _compile_trigger_intents,
    _insert_missing_flags_for_triggers,
    _validate_triggers,
)


def _make_context() -> dict:
    return {
        "rooms": [
            {"id": "guard_post", "name": "Guard Post"},
            {"id": "forge", "name": "Forge"},
        ],
        "items": [
            {"id": "forged_key", "name": "Forged Key"},
        ],
        "npcs": [
            {"id": "stern_guard", "room_id": "guard_post"},
            {"id": "blacksmith", "room_id": "forge"},
        ],
        "dialogue_nodes": [
            {"id": "blacksmith_forges_key", "npc_id": "blacksmith"},
        ],
        "flags": [
            {"id": "guard_warned"},
            {"id": "range_ready"},
        ],
        "locks": [],
        "puzzles": [],
        "quests": [],
    }


def test_compile_trigger_intents_normalizes_event_data_and_preconditions() -> None:
    triggers = _compile_trigger_intents(
        [
            {
                "id": "guard challenge",
                "moment": "The guard stops the player the first time they enter.",
                "event_kind": "room_enter",
                "watched_room_id": "guard_post",
                "blocked_flags": ["guard_warned"],
                "required_npc_ids": ["stern_guard"],
                "priority_tier": "atmosphere",
                "repeat_mode": "once",
                "consequences": {
                    "set_flags": ["guard_warned"],
                    "printed_messages": ["The guard blocks your path."],
                },
            }
        ],
        _make_context(),
    )

    assert triggers[0]["id"] == "trigger_guard_challenge"
    assert triggers[0]["event_type"] == "room_enter"
    assert triggers[0]["event_data"] == {"room_id": "guard_post"}
    assert triggers[0]["priority"] == 0
    assert triggers[0]["one_shot"] is True
    assert {"type": "not_flag", "flag": "guard_warned"} in triggers[0]["preconditions"]
    assert {
        "type": "npc_in_room",
        "npc": "stern_guard",
        "room": "guard_post",
    } in triggers[0]["preconditions"]


def test_compile_trigger_intents_backfills_print_effect_for_message_only_trigger() -> None:
    triggers = _compile_trigger_intents(
        [
            {
                "id": "storm atmosphere",
                "moment": "The room rumbles whenever the storm peaks.",
                "event_kind": "room_enter",
                "watched_room_id": "guard_post",
                "response_text": "Thunder rolls through the rafters.",
                "priority_tier": "atmosphere",
                "repeat_mode": "repeat",
                "consequences": {},
            }
        ],
        _make_context(),
    )

    assert triggers[0]["message"] is None
    assert triggers[0]["effects"] == [
        {"type": "print", "message": "Thunder rolls through the rafters."}
    ]
    assert triggers[0]["one_shot"] is False


def test_compile_trigger_intents_enriches_dialogue_node_event_data() -> None:
    triggers = _compile_trigger_intents(
        [
            {
                "id": "blacksmith gives key",
                "moment": "The blacksmith hands over the reward.",
                "event_kind": "dialogue_node",
                "watched_dialogue_node_id": "blacksmith_forges_key",
                "response_text": "The blacksmith presses the key into your hand.",
                "priority_tier": "critical",
                "repeat_mode": "once",
                "consequences": {
                    "give_item_ids": ["forged_key"],
                    "score_delta": 5,
                },
            }
        ],
        _make_context(),
    )

    assert triggers[0]["event_data"] == {
        "node_id": "blacksmith_forges_key",
        "npc_id": "blacksmith",
    }
    assert triggers[0]["priority"] == 25
    assert {
        "type": "spawn_item",
        "item": "forged_key",
        "location": "_inventory",
    } in triggers[0]["effects"]
    assert {"type": "add_score", "points": 5} in triggers[0]["effects"]


def test_validate_triggers_rejects_flag_self_loop() -> None:
    errors = _validate_triggers(
        [
            {
                "id": "trigger_loop",
                "event_type": "flag_set",
                "event_data": {"flag": "range_ready"},
                "preconditions": [],
                "effects": [{"type": "set_flag", "flag": "range_ready"}],
                "message": None,
                "priority": 10,
                "one_shot": True,
            }
        ],
        _make_context(),
    )

    assert "watches flag range_ready and sets it again" in errors[0]


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
