from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from anyzork.db.schema import GameDB
from anyzork.generator.passes import commands
from anyzork.generator.providers.base import BaseProvider


class RecordingTwoStageProvider(BaseProvider):
    def __init__(
        self,
        *,
        intents_response: dict,
        command_responses: list[dict],
    ) -> None:
        self.intents_response = intents_response
        self.command_responses = command_responses
        self.schema_calls: list[dict] = []

    def generate_structured(self, prompt: str, schema: dict, context=None) -> dict:
        self.schema_calls.append(schema)
        if schema is commands.COMMAND_INTENTS_SCHEMA:
            return self.intents_response
        if schema is commands.COMMANDS_SCHEMA:
            if not self.command_responses:
                raise AssertionError("No command response left for COMMANDS_SCHEMA")
            return self.command_responses.pop(0)
        raise AssertionError("Unexpected schema requested")

    def generate_text(self, prompt: str, context=None) -> str:
        raise NotImplementedError

    def validate_config(self) -> None:
        return None


class SlowCompileProvider(BaseProvider):
    def __init__(self, *, sleep_seconds: float) -> None:
        self.sleep_seconds = sleep_seconds

    def generate_structured(self, prompt: str, schema: dict, context=None) -> dict:
        if schema is commands.COMMAND_INTENTS_SCHEMA:
            return {
                "intents": [
                    {
                        "id": "examine_hidden_bookshelf",
                        "verb": "examine",
                        "pattern": "examine bookshelf",
                        "purpose": "Reveal the hidden shelf mechanism.",
                        "trigger_conditions": ["Player is in the library."],
                        "outcome_steps": ["Show the hidden passage clue."],
                        "success_message": "A seam in the shelf catches your eye.",
                        "failure_message": "Nothing unusual stands out.",
                        "priority": 10,
                        "one_shot": 0,
                        "context_room_ids": ["library"],
                        "done_message": "",
                    }
                ]
            }

        time.sleep(self.sleep_seconds)
        return {"commands": [], "flags": []}

    def generate_text(self, prompt: str, context=None) -> str:
        raise NotImplementedError

    def validate_config(self) -> None:
        return None


def _make_context() -> dict:
    return {
        "concept": {"prompt": "mystery manor"},
        "rooms": [
            {"id": "library", "name": "Library", "region": "house"},
        ],
        "items": [],
        "npcs": [],
        "locks": [],
        "exits": [],
        "puzzles": [],
        "flags": [],
        "seed": 1234,
    }


def _make_db(tmp_path: Path) -> GameDB:
    db = GameDB(tmp_path / "commands_pipeline_test.zork")
    db.initialize(
        game_name="Commands Pipeline Test",
        author="tests",
        prompt="two-stage commands pipeline",
    )
    db.insert_room(
        id="library",
        name="Library",
        description="A quiet library.",
        short_description="A quiet library.",
        first_visit_text=None,
        region="house",
        is_dark=0,
        is_start=1,
    )
    return db


def test_run_pass_caches_generated_intents_after_failed_compile(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    context = _make_context()
    intents_response = {
        "intents": [
            {
                "id": "examine_hidden_bookshelf",
                "verb": "examine",
                "pattern": "examine bookshelf",
                "purpose": "Reveal the hidden shelf mechanism.",
                "trigger_conditions": ["Player is in the library."],
                "outcome_steps": ["Show the hidden passage clue."],
                "success_message": "A seam in the shelf catches your eye.",
                "failure_message": "Nothing unusual stands out.",
                "priority": 10,
                "one_shot": 0,
                "context_room_ids": ["library"],
                "done_message": "",
            }
        ]
    }
    provider = RecordingTwoStageProvider(
        intents_response=intents_response,
        command_responses=[
                {
                    "commands": [
                        {
                            "id": "assemble_will_fragments",
                            "verb": "assemble",
                            "pattern": "assemble will fragments",
                            "preconditions": [],
                            "effects": [
                                {
                                    "type": "spawn_item",
                                    "item": "reconstructed_will",
                                    "location": "_inventory",
                                }
                            ],
                            "success_message": "A seam appears.",
                            "failure_message": "You are still missing pieces.",
                            "priority": 10,
                            "one_shot": 0,
                        }
                    ],
                    "flags": [],
            }
        ],
    )

    with pytest.raises(ValueError):
        commands.run_pass(db, provider, context)

    assert provider.schema_calls[:2] == [
        commands.COMMAND_INTENTS_SCHEMA,
        commands.COMMANDS_SCHEMA,
    ]
    assert context.get("_command_intents") == intents_response["intents"]


def test_second_run_reuses_cached_intents_without_regenerating_them(
    tmp_path: Path,
) -> None:
    db = _make_db(tmp_path)
    context = _make_context()
    intents_response = {
        "intents": [
            {
                "id": "examine_hidden_bookshelf",
                "verb": "examine",
                "pattern": "examine bookshelf",
                "purpose": "Reveal the hidden shelf mechanism.",
                "trigger_conditions": ["Player is in the library."],
                "outcome_steps": ["Show the hidden passage clue."],
                "success_message": "A seam in the shelf catches your eye.",
                "failure_message": "Nothing unusual stands out.",
                "priority": 10,
                "one_shot": 0,
                "context_room_ids": ["library"],
                "done_message": "",
            }
        ]
    }
    provider = RecordingTwoStageProvider(
        intents_response=intents_response,
        command_responses=[
                {
                    "commands": [
                        {
                            "id": "assemble_will_fragments",
                            "verb": "assemble",
                            "pattern": "assemble will fragments",
                            "preconditions": [],
                            "effects": [
                                {
                                    "type": "spawn_item",
                                    "item": "reconstructed_will",
                                    "location": "_inventory",
                                }
                            ],
                            "success_message": "A seam appears.",
                            "failure_message": "You are still missing pieces.",
                            "priority": 10,
                            "one_shot": 0,
                        }
                    ],
                "flags": [],
            },
            {
                "commands": [
                    {
                        "id": "examine_hidden_bookshelf",
                        "verb": "examine",
                        "pattern": "examine bookshelf",
                        "preconditions": [],
                        "effects": [
                            {"type": "print", "message": "A seam appears."}
                        ],
                        "success_message": "A seam appears.",
                        "failure_message": "Nothing happens.",
                        "priority": 10,
                        "one_shot": 0,
                    }
                ],
                "flags": [],
            },
        ],
    )

    with pytest.raises(ValueError):
        commands.run_pass(db, provider, context)

    commands.run_pass(db, provider, context)

    assert provider.schema_calls.count(commands.COMMAND_INTENTS_SCHEMA) == 1
    assert context.get("_command_intents") == intents_response["intents"]


def test_run_pass_times_out_compile_stage_and_persists_debug_artifact(
    tmp_path: Path,
) -> None:
    db = _make_db(tmp_path)
    context = _make_context()
    context["_command_debug_dir"] = tmp_path
    context["_command_stage_timeouts"] = {"compile": 0.01}
    provider = SlowCompileProvider(sleep_seconds=0.1)

    with pytest.raises(TimeoutError, match="Debug artifact written to"):
        commands.run_pass(db, provider, context)

    artifacts = list(tmp_path.glob("*-compile-*.json"))
    assert len(artifacts) == 1

    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["stage"] == "compile"
    assert payload["timeout_seconds"] == 0.01
    assert len(payload["intents"]) == 1
    assert "Compile these intents into valid AnyZork DSL rules" in payload["prompt"]
