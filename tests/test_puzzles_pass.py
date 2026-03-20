from __future__ import annotations

from anyzork.generator.passes.puzzles import (
    _choose_puzzle_room,
    _compile_puzzle_intents,
    _normalize_hint_progression,
    _score_for_puzzle,
)


def test_choose_puzzle_room_prefers_valid_primary_candidate() -> None:
    room_id = _choose_puzzle_room(
        {
            "primary_room_candidates": ["vault", "library"],
            "clue_room_ids": ["study"],
            "involved_item_ids": [],
        },
        {
            "rooms": [
                {"id": "library", "is_start": 0},
                {"id": "study", "is_start": 1},
            ],
            "items": [],
        },
    )

    assert room_id == "library"


def test_choose_puzzle_room_falls_back_to_involved_item_room() -> None:
    room_id = _choose_puzzle_room(
        {
            "primary_room_candidates": ["vault"],
            "clue_room_ids": [],
            "involved_item_ids": ["cipher_disk"],
        },
        {
            "rooms": [
                {"id": "library", "is_start": 0},
                {"id": "study", "is_start": 1},
            ],
            "items": [
                {"id": "cipher_disk", "room_id": "library"},
            ],
        },
    )

    assert room_id == "library"


def test_normalize_hint_progression_backfills_missing_hints() -> None:
    hints = _normalize_hint_progression(
        {
            "core_concept": "The player realizes the mural encodes a star chart.",
            "solution_beats": ["Compare the mural to the observatory controls."],
            "hint_progression": [],
        }
    )

    assert len(hints) >= 2
    assert "mural encodes a star chart" in hints[0]


def test_score_for_puzzle_rewards_optional_content() -> None:
    assert _score_for_puzzle(1, 0) == 12
    assert _score_for_puzzle(2, 1) == 22
    assert _score_for_puzzle(3, 1) == 28


def test_compile_puzzle_intents_normalizes_rows_for_db_and_downstream() -> None:
    puzzles = _compile_puzzle_intents(
        [
            {
                "id": "Mural Alignment!",
                "name": "Mural Alignment",
                "core_concept": "Align the star mural to reveal the hidden aperture.",
                "primary_room_candidates": ["observatory", "library"],
                "clue_room_ids": ["library"],
                "involved_item_ids": ["star_chart"],
                "involved_npc_ids": ["curator_rowan"],
                "solution_beats": [
                    "Study the star chart.",
                    "Adjust the mural rings to match it.",
                ],
                "hint_progression": [
                    "The mural and the chart seem connected.",
                    "Try matching the mural rings to the star chart.",
                ],
                "difficulty_hint": 2,
                "progression_role": "critical",
            }
        ],
        {
            "rooms": [
                {"id": "observatory", "is_start": 0},
                {"id": "library", "is_start": 1},
            ],
            "items": [{"id": "star_chart", "room_id": "library"}],
        },
    )

    assert puzzles[0]["id"] == "mural_alignment"
    assert puzzles[0]["room_id"] == "observatory"
    assert puzzles[0]["difficulty"] == 2
    assert puzzles[0]["score_value"] == 18
    assert puzzles[0]["is_optional"] == 0
    assert puzzles[0]["involved_item_ids"] == ["star_chart"]
    assert puzzles[0]["involved_npc_ids"] == ["curator_rowan"]
