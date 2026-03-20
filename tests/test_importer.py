from __future__ import annotations

import json
from pathlib import Path

import pytest

from anyzork.db.schema import GameDB
from anyzork.importer import (
    IMPORT_SPEC_FORMAT,
    ZORKSCRIPT_AUTHORING_TEMPLATE,
    ImportSpecError,
    build_zorkscript_prompt,
    compile_import_spec,
)


def _base_import_spec() -> dict:
    return {
        "format": IMPORT_SPEC_FORMAT,
        "game": {
            "title": "Import Test",
            "author_prompt": "A compact import test.",
            "intro_text": "You arrive.",
            "realism": "medium",
        },
        "player": {"start_room_id": "start"},
        "rooms": [
            {
                "id": "start",
                "name": "Start",
                "description": "The starting room.",
                "region": "house",
                "is_start": True,
            },
            {
                "id": "hall",
                "name": "Hall",
                "description": "A short hallway.",
                "region": "house",
            },
        ],
        "exits": [
            {
                "id": "start_hall",
                "from_room_id": "start",
                "to_room_id": "hall",
                "direction": "north",
            },
            {
                "id": "hall_start",
                "from_room_id": "hall",
                "to_room_id": "start",
                "direction": "south",
            },
        ],
        "items": [],
        "npcs": [],
        "dialogue_nodes": [],
        "dialogue_options": [],
        "locks": [],
        "puzzles": [],
        "flags": [],
        "interactions": [],
        "commands": [],
        "quests": [
            {
                "id": "main",
                "name": "Main Quest",
                "description": "Solve the case.",
                "quest_type": "main",
                "score_value": 10,
                "sort_order": 0,
                "objectives": [
                    {
                        "id": "obj_find_clue",
                        "description": "Find the clue.",
                        "order_index": 0,
                        "bonus_score": 0,
                        "is_optional": 0,
                    }
                ],
            }
        ],
        "interaction_responses": [],
        "triggers": [],
    }


def test_build_zorkscript_prompt_embeds_concept_and_realism() -> None:
    prompt = build_zorkscript_prompt(
        "A haunted manor mystery set during spring break.",
        realism="high",
    )

    assert "A haunted manor mystery set during spring break." in prompt
    assert "Realism: high" in prompt
    assert "realistic simulation" in prompt


def test_build_zorkscript_prompt_includes_field_specific_requirements() -> None:
    prompt = build_zorkscript_prompt(
        "A family mystery across two houses.",
        realism="medium",
        authoring_fields={
            "scale": "medium",
            "locations": ["Chico apartment", "Cool family house"],
            "characters": ["Jazzy - observant protagonist", "Jaden - boyfriend"],
            "items": ["Phone with incriminating texts", "Silver lighter"],
            "story": "Figure out who killed Dan.",
            "genre_tags": ["mystery", "social"],
            "tone": ["dark", "comedic"],
        },
    )

    assert "6-12 rooms across 1-2 regions" in prompt
    assert "Chico apartment" in prompt
    assert "Phone with incriminating texts" in prompt
    assert "Tone: dark, comedic" in prompt


def test_build_zorkscript_prompt_defaults_to_medium_scale() -> None:
    prompt = build_zorkscript_prompt(
        "A lonely tower on a cliff.",
        authoring_fields={"world_description": "A lonely tower on a cliff."},
    )

    # No scale specified — should default to medium targets in quality block
    assert "6-12 rooms across 1-2 regions" in prompt


def test_zorkscript_template_has_required_content() -> None:
    t = ZORKSCRIPT_AUTHORING_TEMPLATE
    assert "You are authoring a complete, playable text adventure in ZorkScript" in t
    assert "game {" in t
    assert "player {" in t
    assert "room " in t
    assert "exit " in t
    assert "item " in t
    assert "npc " in t
    assert "flag " in t
    assert "lock " in t
    assert "quest " in t
    assert 'on "' in t
    assert "when " in t
    assert "require " in t
    assert "effect " in t
    assert "success " in t
    assert "fail " in t
    assert "once" in t
    assert "{quality_requirements}" in t
    assert "Concept:" in t
    assert "{concept}" in t


def test_build_zorkscript_prompt_rejects_empty_concept() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        build_zorkscript_prompt("   ")


def test_compile_import_spec_generates_missing_quest_flags(tmp_path: Path) -> None:
    output_path = tmp_path / "imported_game.zork"

    compiled_path, warnings = compile_import_spec(_base_import_spec(), output_path)

    assert compiled_path == output_path.resolve()
    assert "No win condition flags defined. The game has no victory state." in warnings
    assert compiled_path.exists()

    db = GameDB(compiled_path)
    try:
        quest = db.get_quest("main")
        assert quest is not None
        assert quest["completion_flag"] == "main_complete"
        objectives = db.get_quest_objectives("main")
        assert objectives[0]["completion_flag"] == "main_obj_find_clue_complete"
        assert db.get_flag("main_complete") == "false"
        assert db.get_flag("main_obj_find_clue_complete") == "false"
    finally:
        db.close()


def test_compile_import_spec_rejects_unsupported_format(tmp_path: Path) -> None:
    spec = _base_import_spec()
    spec["format"] = "anyzork.import.v0"

    with pytest.raises(ImportSpecError, match="Unsupported import format"):
        compile_import_spec(spec, tmp_path / "bad.zork")


def test_compile_import_spec_rejects_non_canonical_exit_direction(tmp_path: Path) -> None:
    spec = _base_import_spec()
    spec["exits"][0]["direction"] = "out"

    with pytest.raises(ImportSpecError, match="Unsupported exit direction"):
        compile_import_spec(spec, tmp_path / "bad_direction.zork")


def test_compile_import_spec_accepts_external_alias_shape(tmp_path: Path) -> None:
    spec = {
        "format": IMPORT_SPEC_FORMAT,
        "game": {
            "title": "Alias Import",
            "author_prompt": "Alias-heavy import shape.",
            "realism": "medium",
        },
        "player": {"start_room_id": "start"},
        "rooms": [
            {
                "id": "start",
                "name": "Start",
                "description": "The starting room.",
                "region": "house",
                "is_start": True,
            },
            {
                "id": "shop",
                "name": "Shop",
                "description": "A quiet shop.",
                "region": "house",
            },
        ],
        "exits": [
            {
                "id": "start_shop",
                "from_room_id": "start",
                "to_room_id": "shop",
                "direction": "north",
            }
        ],
        "items": [
            {
                "id": "wand",
                "name": "Wand",
                "description": "A wand.",
                "location_room_id": "shop",
                "is_portable": True,
                "is_hidden": False,
            }
        ],
        "npcs": [
            {
                "id": "keeper",
                "name": "Keeper",
                "description": "A watchful keeper.",
                "location_room_id": "shop",
            }
        ],
        "dialogue_nodes": [
            {"id": "keeper_intro", "npc_id": "keeper", "text": "Welcome."}
        ],
        "dialogue_options": [
            {
                "id": "keeper_opt",
                "from_node_id": "keeper_intro",
                "text": "Hello.",
            }
        ],
        "puzzles": [
            {
                "id": "get_wand",
                "name": "Get the Wand",
                "description": "Take the wand.",
                "required_items": ["wand"],
                "solution_steps": ["take wand"],
                "set_flags": ["got_wand"],
            }
        ],
        "flags": [
            {"id": "got_wand", "name": "Got the wand", "default_value": False}
        ],
        "commands": [
            {
                "id": "take_wand",
                "verb": "take",
                "target_id": "wand",
                "context_room_ids": ["shop"],
                "preconditions": [],
                "effects": [
                    {"type": "add_item", "item_id": "wand"},
                    {"type": "set_flag", "flag_id": "got_wand", "value": True},
                ],
            }
        ],
        "quests": [
            {
                "id": "main",
                "name": "Main Quest",
                "description": "Take the wand.",
                "quest_type": "main",
                "objectives": [{"id": "take_it", "description": "Take it."}],
            }
        ],
        "interaction_responses": [
            {
                "id": "look_keeper",
                "type": "look",
                "target_id": "keeper",
                "context_room_ids": ["shop"],
                "response_text": "The keeper watches you closely.",
            }
        ],
        "triggers": [
            {
                "id": "enter_shop",
                "event": "enter_room",
                "context_room_ids": ["shop"],
                "effects": [{"type": "message", "text": "The shop falls quiet."}],
            }
        ],
    }

    compiled_path, warnings = compile_import_spec(spec, tmp_path / "alias_import.zork")

    assert "No win condition flags defined. The game has no victory state." in warnings

    db = GameDB(compiled_path)
    try:
        assert db.get_item("wand")["room_id"] == "shop"
        assert db.get_npc("keeper")["room_id"] == "shop"
        assert db.get_dialogue_node("keeper_intro")["content"] == "Welcome."
        assert db.get_dialogue_options("keeper_intro")[0]["id"] == "keeper_opt"
        assert db.get_puzzle("get_wand")["room_id"] == "shop"
        imported_command = db._fetchone(
            "SELECT * FROM commands WHERE id = ?",
            ("imported_look_keeper",),
        )
        assert imported_command is not None
        assert imported_command["pattern"] == "look keeper"
        trigger = db._fetchone("SELECT * FROM triggers WHERE id = ?", ("enter_shop",))
        assert trigger is not None
        assert json.loads(trigger["event_data"]) == {"room_id": "shop"}
        assert trigger["message"] == "The shop falls quiet."
    finally:
        db.close()


def test_compile_import_spec_accepts_natural_authored_story_shape(tmp_path: Path) -> None:
    spec = {
        "format": IMPORT_SPEC_FORMAT,
        "game": {
            "title": "Story Import",
            "author_prompt": "A story-forward import.",
            "win_conditions": ["heard_truth"],
        },
        "player": {"start_room_id": "hut"},
        "rooms": [
            {
                "id": "hut",
                "name": "Hut",
                "description": "A storm-battered hut.",
                "region": "sea",
                "is_start": True,
            }
        ],
        "exits": [],
        "items": [
            {
                "id": "letter",
                "name": "Letter",
                "description": "A letter.",
                "room_id": "hut",
                "is_takeable": True,
            }
        ],
        "npcs": [
            {
                "id": "hagrid",
                "name": "Hagrid",
                "description": "A giant of a man.",
                "room_id": "hut",
            }
        ],
        "dialogue_nodes": [],
        "dialogue_options": [],
        "locks": [],
        "puzzles": [],
        "flags": [
            {"id": "met_hagrid", "name": "Met Hagrid"},
            {"id": "heard_truth", "name": "Heard the truth"},
        ],
        "commands": [
            {
                "id": "talk_hagrid",
                "verb": "talk",
                "target_npc_id": "hagrid",
                "description": "Speak with Hagrid.",
                "context_room_ids": ["hut"],
                "preconditions": [{"type": "same_room", "npc_id": "hagrid"}],
                "effects": [{"type": "set_flag", "flag_id": "met_hagrid"}],
                "response_text": "Hagrid lowers his voice.",
            },
            {
                "id": "listen_hagrid",
                "verb": "listen",
                "target_npc_id": "hagrid",
                "description": "Listen to Hagrid.",
                "context_room_ids": ["hut"],
                "preconditions": [{"type": "flag_set", "flag_id": "met_hagrid"}],
                "effects": [{"type": "set_flag", "flag_id": "heard_truth"}],
                "response_text": "Yer a wizard, Harry.",
            },
        ],
        "quests": [
            {
                "id": "truth",
                "name": "Hear the Truth",
                "description": "Survive long enough to hear Hagrid out.",
                "objectives": [
                    {
                        "id": "obj_meet_hagrid",
                        "description": "Meet Hagrid.",
                        "set_flags": ["met_hagrid"],
                    },
                    {
                        "id": "obj_hear_truth",
                        "description": "Hear the truth.",
                        "required_flags": ["heard_truth"],
                    },
                ],
            }
        ],
        "interaction_responses": [
            {
                "id": "hut_listen",
                "room_id": "hut",
                "action": "listen",
                "text": "Rain batters the walls.",
            }
        ],
        "triggers": [
            {
                "id": "hagrid_arrives",
                "event": "room_turn",
                "room_id": "hut",
                "preconditions": [{"type": "flag_not_set", "flag_id": "met_hagrid"}],
                "effects": [],
                "text": "A thunderous knock shakes the door.",
            }
        ],
    }

    compiled_path, warnings = compile_import_spec(spec, tmp_path / "story_import.zork")

    assert compiled_path.exists()
    assert warnings == []

    db = GameDB(compiled_path)
    try:
        quest = db.get_quest("truth")
        assert quest is not None
        assert quest["quest_type"] == "main"
        objectives = db.get_quest_objectives("truth")
        assert objectives[0]["completion_flag"] == "met_hagrid"
        assert objectives[1]["completion_flag"] == "heard_truth"
        talk_cmd = db._fetchone("SELECT * FROM commands WHERE id = ?", ("talk_hagrid",))
        assert talk_cmd is not None
        assert talk_cmd["pattern"] == "talk hagrid"
        assert talk_cmd["success_message"] == "Hagrid lowers his voice."
        imported_interaction = db._fetchone(
            "SELECT * FROM commands WHERE id = ?",
            ("imported_hut_listen",),
        )
        assert imported_interaction is not None
        assert imported_interaction["pattern"] == "listen"
        trigger = db._fetchone("SELECT * FROM triggers WHERE id = ?", ("hagrid_arrives",))
        assert trigger is not None
        assert trigger["event_type"] == "room_enter"
        assert json.loads(trigger["event_data"]) == {"room_id": "hut"}
        assert trigger["message"] == "A thunderous knock shakes the door."
    finally:
        db.close()


def test_compile_import_spec_compiles_public_interactions(tmp_path: Path) -> None:
    spec = _base_import_spec()
    spec["items"] = [
        {
            "id": "letter",
            "name": "Letter",
            "description": "A mysterious letter.",
            "room_id": "start",
            "is_takeable": True,
        }
    ]
    spec["flags"] = [{"id": "read_letter", "description": "Read the letter", "value": False}]
    spec["interactions"] = [
        {
            "id": "read_letter_cmd",
            "type": "read_item",
            "command": "read letter",
            "item_id": "letter",
            "set_flags": ["read_letter"],
            "success_message": "You finally unfold the letter.",
        }
    ]

    compiled_path, _warnings = compile_import_spec(spec, tmp_path / "interaction_import.zork")

    db = GameDB(compiled_path)
    try:
        command = db.get_command("read_letter_cmd")
        assert command is not None
        assert command["verb"] == "read"
        assert command["pattern"] == "read letter"
        assert json.loads(command["context_room_ids"]) == ["start"]
        assert json.loads(command["preconditions"]) == [
            {"type": "item_accessible", "item": "letter"}
        ]
        assert json.loads(command["effects"]) == [
            {"type": "set_flag", "flag": "read_letter", "value": True}
        ]
    finally:
        db.close()


def test_compile_import_spec_rejects_unknown_public_interaction_type(tmp_path: Path) -> None:
    spec = _base_import_spec()
    spec["interactions"] = [
        {
            "id": "bad",
            "type": "invent_verb",
            "command": "invent weird thing",
        }
    ]

    with pytest.raises(ImportSpecError, match="Unsupported interaction type"):
        compile_import_spec(spec, tmp_path / "bad_interaction.zork")


def test_compile_import_spec_stores_empty_legacy_command_scope_as_null(tmp_path: Path) -> None:
    spec = _base_import_spec()
    spec["commands"] = [
        {
            "id": "global_read",
            "verb": "read",
            "pattern": "read note",
            "preconditions": [],
            "effects": [],
            "success_message": "You read the note.",
            "failure_message": "",
            "context_room_ids": [],
        }
    ]

    compiled_path, _warnings = compile_import_spec(spec, tmp_path / "global_scope.zork")

    db = GameDB(compiled_path)
    try:
        command = db.get_command("global_read")
        assert command is not None
        assert command["context_room_ids"] is None
    finally:
        db.close()
