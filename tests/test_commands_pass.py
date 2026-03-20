from __future__ import annotations

from anyzork.generator.passes.commands import (
    _normalize_command_aliases,
    _validate_commands,
)


def test_validate_commands_rejects_unknown_solve_puzzle_reference() -> None:
    errors = _validate_commands(
        commands=[
            {
                "id": "accuse_thorne_win",
                "verb": "accuse",
                "pattern": "accuse thorne",
                "preconditions": [],
                "effects": [{"type": "solve_puzzle", "puzzle": "win_condition_puzzle"}],
                "success_message": "You level the accusation.",
                "failure_message": "You are not ready to accuse anyone yet.",
                "priority": 10,
                "one_shot": 1,
            }
        ],
        flags=[],
        context={
            "rooms": [{"id": "drawing_room"}],
            "items": [],
            "npcs": [],
            "locks": [],
            "exits": [],
            "puzzles": [],
            "quests": [],
            "flags": [],
        },
    )

    assert errors == [
        "Command accuse_thorne_win effect solve_puzzle references "
        "non-existent puzzle 'win_condition_puzzle'."
    ]


def test_normalize_command_aliases_maps_inventory_spawn_location() -> None:
    commands = [
        {
            "id": "assemble_will_fragments",
            "effects": [
                {
                    "type": "spawn_item",
                    "item": "reconstructed_will",
                    "location": "inventory",
                }
            ],
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    assert commands[0]["effects"][0]["location"] == "_inventory"


def test_normalize_command_aliases_maps_player_inventory_alias() -> None:
    commands = [
        {
            "id": "bang_frying_pan",
            "effects": [
                {
                    "type": "move_item",
                    "item": "frying_pan",
                    "from": "_player_inventory",
                    "to": "kitchen",
                }
            ],
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    effect = commands[0]["effects"][0]
    assert effect["from"] == "_inventory"
    assert effect["to"] == "kitchen"


def test_normalize_command_aliases_maps_null_move_item_location() -> None:
    commands = [
        {
            "id": "search_guest_desk_with_trowel",
            "effects": [
                {
                    "type": "move_item",
                    "item": "guest_note",
                    "from": "null",
                    "to": "inventory",
                }
            ],
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    effect = commands[0]["effects"][0]
    assert effect["from"] == "_current"
    assert effect["to"] == "_inventory"


def test_normalize_command_aliases_prefixes_missing_verb_in_pattern() -> None:
    commands = [
        {
            "id": "bang_frying_pan",
            "verb": "bang",
            "pattern": "frying pan",
            "effects": [],
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    assert commands[0]["pattern"] == "bang frying pan"


def test_normalize_command_aliases_converts_nowhere_move_to_remove_item() -> None:
    commands = [
        {
            "id": "use_usb_drive_apartment",
            "effects": [
                {
                    "type": "move_item",
                    "item": "usb_drive",
                    "from": "_inventory",
                    "to": "_nowhere",
                }
            ],
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    assert commands[0]["effects"][0] == {
        "type": "remove_item",
        "item": "usb_drive",
    }


def test_normalize_command_aliases_fills_missing_failure_message() -> None:
    commands = [
        {
            "id": "examine_cupboard_latch",
            "verb": "examine",
            "pattern": "cupboard door",
            "preconditions": [],
            "effects": [],
            "failure_message": "",
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    assert commands[0]["failure_message"] == (
        "You don't notice anything unusual about cupboard door."
    )


def test_normalize_command_aliases_converts_toggle_precondition_alias() -> None:
    commands = [
        {
            "id": "light_gas_lamp",
            "preconditions": [
                {
                    "type": "set_toggle_state",
                    "item": "gas_lamp",
                    "state": "off",
                }
            ],
            "effects": [],
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    assert commands[0]["preconditions"][0]["type"] == "toggle_state"


def test_normalize_command_aliases_converts_portable_examine_to_item_accessible() -> None:
    commands = [
        {
            "id": "examine_wallet_clue",
            "verb": "examine",
            "preconditions": [
                {
                    "type": "item_in_room",
                    "item": "jaden_wallet",
                    "room": "chico_master_bedroom",
                }
            ],
            "effects": [],
        }
    ]

    _normalize_command_aliases(
        commands,
        {
            "locks": [],
            "items": [{"id": "jaden_wallet", "is_takeable": 1}],
        },
    )

    assert commands[0]["preconditions"][0] == {
        "type": "item_accessible",
        "item": "jaden_wallet",
    }


def test_normalize_command_aliases_converts_inventory_item_in_container_to_has_item() -> None:
    commands = [
        {
            "id": "search_backpack_for_wallet",
            "preconditions": [
                {
                    "type": "item_in_container",
                    "item": "jaden_wallet",
                    "container": "_inventory",
                }
            ],
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    assert commands[0]["preconditions"][0] == {
        "type": "has_item",
        "item": "jaden_wallet",
    }


def test_normalize_command_aliases_drops_unsupported_npc_move_item_effect() -> None:
    commands = [
        {
            "id": "bang_frying_pan",
            "verb": "bang",
            "pattern": "bang frying pan",
            "effects": [
                {
                    "type": "move_item",
                    "item": "aunt_petunia",
                    "from": "entrance_hall",
                    "to": "kitchen",
                },
                {"type": "unlock", "lock": "upstairs_access"},
            ],
        }
    ]

    _normalize_command_aliases(
        commands,
        {
            "locks": [],
            "items": [],
            "npcs": [{"id": "aunt_petunia"}],
        },
    )

    assert commands[0]["effects"] == [{"type": "unlock", "lock": "upstairs_access"}]


def test_normalize_command_aliases_converts_not_flag_effect_to_clear_flag() -> None:
    commands = [
        {
            "id": "extinguish_gas_lamp_command",
            "effects": [{"type": "not_flag", "flag": "lamp_lit"}],
        }
    ]

    _normalize_command_aliases(commands, {"locks": [], "items": []})

    effect = commands[0]["effects"][0]
    assert effect["type"] == "set_flag"
    assert effect["flag"] == "lamp_lit"
    assert effect["value"] is False


def test_normalize_command_aliases_maps_exit_unlock_to_lock_id() -> None:
    commands = [
        {
            "id": "show_handkerchief_to_davies",
            "effects": [{"type": "unlock", "lock": "grand_hall_up"}],
        }
    ]

    _normalize_command_aliases(
        commands,
        {
            "locks": [{"id": "grand_stair_lock", "target_exit_id": "grand_hall_up"}],
            "items": [],
        },
    )

    assert commands[0]["effects"][0] == {
        "type": "unlock",
        "lock": "grand_stair_lock",
    }


def test_normalize_command_aliases_maps_container_unlock_to_open_container() -> None:
    commands = [
        {
            "id": "push_portrait_button",
            "effects": [{"type": "unlock", "lock": "executive_desk"}],
        }
    ]

    _normalize_command_aliases(
        commands,
        {
            "locks": [],
            "items": [{"id": "executive_desk", "is_container": 1}],
        },
    )

    assert commands[0]["effects"][0] == {
        "type": "open_container",
        "container": "executive_desk",
    }


def test_normalize_command_aliases_maps_move_item_from_container_to_take_effect() -> None:
    commands = [
        {
            "id": "take_guest_diary_solves_puzzle",
            "effects": [
                {
                    "type": "move_item",
                    "item": "guest_diary",
                    "from": "travel_trunk",
                    "to": "_inventory",
                }
            ],
        }
    ]

    _normalize_command_aliases(
        commands,
        {
            "locks": [],
            "items": [{"id": "travel_trunk", "is_container": 1}],
        },
    )

    assert commands[0]["effects"][0] == {
        "type": "take_item_from_container",
        "item": "guest_diary",
    }


def test_normalize_command_aliases_maps_move_item_from_container_to_room() -> None:
    commands = [
        {
            "id": "pry_up_floorboard",
            "effects": [
                {
                    "type": "move_item",
                    "item": "rock_hut_key",
                    "from": "loose_floorboard",
                    "to": "old_lighthouse",
                }
            ],
        }
    ]

    _normalize_command_aliases(
        commands,
        {
            "locks": [],
            "items": [{"id": "loose_floorboard", "is_container": 1}],
        },
    )

    assert commands[0]["effects"] == [
        {"type": "take_item_from_container", "item": "rock_hut_key"},
        {
            "type": "move_item",
            "item": "rock_hut_key",
            "from": "_inventory",
            "to": "old_lighthouse",
        },
    ]


def test_validate_commands_rejects_unknown_spawn_item_reference() -> None:
    errors = _validate_commands(
        commands=[
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
                "success_message": "The fragments align.",
                "failure_message": "You are still missing pieces.",
                "priority": 5,
                "one_shot": 1,
            }
        ],
        flags=[],
        context={
            "rooms": [{"id": "study"}],
            "items": [],
            "npcs": [],
            "locks": [],
            "exits": [],
            "puzzles": [],
            "quests": [],
            "flags": [],
        },
    )

    assert errors == [
        "Command assemble_will_fragments effect spawn_item references "
        "unknown item 'reconstructed_will'."
    ]


def test_validate_commands_rejects_unknown_has_item_reference() -> None:
    errors = _validate_commands(
        commands=[
            {
                "id": "use_key_on_ashworths_diary",
                "verb": "use",
                "pattern": "use key on diary",
                "preconditions": [
                    {"type": "has_item", "item": "tiny_diary_key"},
                ],
                "effects": [{"type": "print", "message": "The diary clicks open."}],
                "success_message": "The key turns.",
                "failure_message": "You need the right key.",
                "priority": 5,
                "one_shot": 0,
            }
        ],
        flags=[],
        context={
            "rooms": [{"id": "study"}],
            "items": [],
            "npcs": [],
            "locks": [],
            "exits": [],
            "puzzles": [],
            "quests": [],
            "flags": [],
        },
    )

    assert errors == [
        "Command use_key_on_ashworths_diary precondition has_item references "
        "unknown item 'tiny_diary_key'."
    ]


def test_validate_commands_rejects_inventory_not_item_in_container_reference() -> None:
    errors = _validate_commands(
        commands=[
            {
                "id": "search_keychain_for_note",
                "verb": "search",
                "pattern": "search keychain",
                "preconditions": [
                    {
                        "type": "not_item_in_container",
                        "item": "hidden_note",
                        "container": "_inventory",
                    }
                ],
                "effects": [],
                "success_message": "You search the keychain.",
                "failure_message": "You are not sure what to search.",
                "priority": 5,
                "one_shot": 0,
            }
        ],
        flags=[],
        context={
            "rooms": [{"id": "drawing_room"}],
            "items": [{"id": "hidden_note"}],
            "npcs": [],
            "locks": [],
            "exits": [],
            "puzzles": [],
            "quests": [],
            "flags": [],
        },
    )

    assert errors == [
        "Command search_keychain_for_note precondition not_item_in_container "
        "cannot use inventory as a container; use has_item for possession or a "
        "real container ID."
    ]


def test_validate_commands_allows_effectless_examine_override() -> None:
    errors = _validate_commands(
        commands=[
            {
                "id": "examine_imposing_bookshelves_puzzle",
                "verb": "examine",
                "pattern": "examine bookshelves",
                "preconditions": [{"type": "in_room", "room": "library"}],
                "effects": [],
                "success_message": "One shelf sits slightly proud of the others.",
                "failure_message": "You do not see those shelves here.",
                "priority": 10,
                "one_shot": 0,
            }
        ],
        flags=[],
        context={
            "rooms": [{"id": "library"}],
            "items": [],
            "npcs": [],
            "locks": [],
            "exits": [],
            "puzzles": [],
            "quests": [],
            "flags": [],
        },
    )

    assert errors == []
