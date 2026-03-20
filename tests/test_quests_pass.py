from __future__ import annotations

from pathlib import Path

import pytest

from anyzork.db.schema import GameDB
from anyzork.generator.passes.quests import run_pass
from anyzork.generator.providers.base import BaseProvider


class StubQuestProvider(BaseProvider):
    def __init__(self, result: dict) -> None:
        self.result = result

    def generate_structured(self, prompt: str, schema: dict, context=None) -> dict:
        return self.result

    def generate_text(self, prompt: str, context=None) -> str:
        raise NotImplementedError

    def validate_config(self) -> None:
        return None


class SequencedQuestProvider(BaseProvider):
    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.prompts: list[str] = []

    def generate_structured(self, prompt: str, schema: dict, context=None) -> dict:
        self.prompts.append(prompt)
        if not self.results:
            raise AssertionError("No quest result left")
        return self.results.pop(0)

    def generate_text(self, prompt: str, context=None) -> str:
        raise NotImplementedError

    def validate_config(self) -> None:
        return None


def test_quest_pass_retries_on_duplicate_objective_flags(tmp_path: Path) -> None:
    db = GameDB(tmp_path / "quests_pass_test.zork")
    db.initialize(
        game_name="Quests Pass Test",
        author="tests",
        prompt="quest validation",
    )

    provider = StubQuestProvider(
        {
            "quests": [
                {
                    "id": "solve_the_case",
                    "name": "Solve the Case",
                    "description": "Discover the truth behind the murder.",
                    "quest_type": "main",
                    "discovery_flag": None,
                    "completion_flag": "quest_solve_the_case_complete",
                    "score_value": 0,
                    "sort_order": 0,
                    "objectives": [
                        {
                            "id": "obj_find_clue",
                            "description": "Find the first clue.",
                            "completion_flag": "study_key_found",
                            "order_index": 0,
                            "is_optional": 0,
                            "bonus_score": 0,
                        },
                        {
                            "id": "obj_unlock_study",
                            "description": "Unlock the study.",
                            "completion_flag": "study_key_found",
                            "order_index": 1,
                            "is_optional": 0,
                            "bonus_score": 0,
                        },
                    ],
                }
            ],
            "flags": [
                {
                    "id": "quest_solve_the_case_complete",
                    "value": "false",
                    "description": "Set when the main quest is complete.",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="Quest validation failed"):
        run_pass(
            db,
            provider,
            {
                "concept": {},
                "rooms": [],
                "items": [],
                "npcs": [],
                "puzzles": [],
                "commands": [],
                "flags": [{"id": "study_key_found", "description": "The study key was found."}],
            },
        )

    assert db._fetchall("SELECT id FROM quests") == []
    assert db._fetchall("SELECT id FROM quest_objectives") == []
    db.close()


def test_quest_pass_retries_on_duplicate_generated_flag_ids(tmp_path: Path) -> None:
    db = GameDB(tmp_path / "quests_duplicate_flags_test.zork")
    db.initialize(
        game_name="Quests Duplicate Flags Test",
        author="tests",
        prompt="quest flag validation",
    )

    provider = StubQuestProvider(
        {
            "quests": [
                {
                    "id": "solve_the_case",
                    "name": "Solve the Case",
                    "description": "Discover the truth behind the murder.",
                    "quest_type": "main",
                    "discovery_flag": None,
                    "completion_flag": "quest_solve_the_case_complete",
                    "score_value": 0,
                    "sort_order": 0,
                    "objectives": [
                        {
                            "id": "obj_find_clue",
                            "description": "Find the first clue.",
                            "completion_flag": "study_key_found",
                            "order_index": 0,
                            "is_optional": 0,
                            "bonus_score": 0,
                        }
                    ],
                }
            ],
            "flags": [
                {
                    "id": "quest_solve_the_case_complete",
                    "value": "false",
                    "description": "Set when the main quest is complete.",
                },
                {
                    "id": "quest_solve_the_case_complete",
                    "value": "false",
                    "description": "Duplicate flag from the provider.",
                },
            ],
        }
    )

    with pytest.raises(ValueError, match="Quest validation failed"):
        run_pass(
            db,
            provider,
            {
                "concept": {},
                "rooms": [],
                "items": [],
                "npcs": [],
                "puzzles": [],
                "commands": [],
                "flags": [{"id": "study_key_found", "description": "The study key was found."}],
            },
        )

    assert db._fetchall("SELECT id FROM quests") == []
    assert db._fetchall(
        "SELECT id FROM flags WHERE id = ?",
        ("quest_solve_the_case_complete",),
    ) == []
    db.close()


def test_quest_pass_retries_after_conflicting_existing_flag_then_succeeds(
    tmp_path: Path,
) -> None:
    db = GameDB(tmp_path / "quests_retry_on_conflict_test.zork")
    db.initialize(
        game_name="Quests Retry On Conflict Test",
        author="tests",
        prompt="quest retry validation",
    )

    provider = SequencedQuestProvider(
        [
            {
                "quests": [
                    {
                        "id": "solve_the_case",
                        "name": "Solve the Case",
                        "description": "Discover the truth behind the murder.",
                        "quest_type": "main",
                        "discovery_flag": None,
                        "completion_flag": "game_won",
                        "score_value": 0,
                        "sort_order": 0,
                        "objectives": [
                            {
                                "id": "obj_find_clue",
                                "description": "Find the first clue.",
                                "completion_flag": "study_key_found",
                                "order_index": 0,
                                "is_optional": 0,
                                "bonus_score": 0,
                            }
                        ],
                    }
                ],
                "flags": [
                    {
                        "id": "game_won",
                        "value": "false",
                        "description": "Conflicts with an existing flag.",
                    }
                ],
            },
            {
                "quests": [
                    {
                        "id": "solve_the_case",
                        "name": "Solve the Case",
                        "description": "Discover the truth behind the murder.",
                        "quest_type": "main",
                        "discovery_flag": None,
                        "completion_flag": "quest_solve_the_case_complete",
                        "score_value": 0,
                        "sort_order": 0,
                        "objectives": [
                            {
                                "id": "obj_find_clue",
                                "description": "Find the first clue.",
                                "completion_flag": "study_key_found",
                                "order_index": 0,
                                "is_optional": 0,
                                "bonus_score": 0,
                            }
                        ],
                    }
                ],
                "flags": [
                    {
                        "id": "quest_solve_the_case_complete",
                        "value": "false",
                        "description": "Set when the main quest is complete.",
                    }
                ],
            },
        ]
    )

    result = run_pass(
        db,
        provider,
        {
            "concept": {},
            "rooms": [],
            "items": [],
            "npcs": [],
            "puzzles": [],
            "commands": [],
            "flags": [
                {"id": "game_won", "description": "Existing win flag."},
                {"id": "study_key_found", "description": "The study key was found."},
            ],
        },
    )

    assert len(provider.prompts) == 2
    assert "Previous Attempt Failed" in provider.prompts[1]
    assert result["quests"][0]["id"] == "solve_the_case"
    assert db._fetchall("SELECT id FROM quests") == [{"id": "solve_the_case"}]
    db.close()
