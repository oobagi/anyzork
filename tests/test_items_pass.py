from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.generator.passes.items import (
    _effective_item_room,
    _enforce_lock_key_placements,
    _fill_missing_item_descriptions,
    _insert_items,
)
from anyzork.generator.passes.locks import (
    _key_candidate_rooms,
    _repair_key_locations,
    _validate_reachability,
)


def test_insert_items_resolves_item_dependency_order(tmp_path: Path) -> None:
    db = GameDB(tmp_path / "items_pass_test.zork")
    db.initialize(
        game_name="Items Pass Test",
        author="tests",
        prompt="dependency ordering",
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

    items = [
        {
            "id": "lantern",
            "name": "lantern",
            "description": "A lantern.",
            "examine_description": "A lantern that needs a battery.",
            "room_id": "start",
            "is_takeable": 1,
            "is_visible": 1,
            "category": "tool",
            "room_description": "A lantern hangs nearby.",
            "drop_description": "A lantern lies here.",
            "requires_item_id": "battery",
        },
        {
            "id": "satchel",
            "name": "satchel",
            "description": "A satchel.",
            "examine_description": "A satchel with one clip.",
            "room_id": None,
            "container_id": "case",
            "is_takeable": 1,
            "is_visible": 1,
            "category": "container",
            "room_description": None,
            "drop_description": "A satchel lies here.",
            "is_container": 1,
            "is_open": 1,
            "has_lid": 0,
        },
        {
            "id": "repair_coil",
            "name": "repair coil",
            "description": "A repair coil.",
            "examine_description": "A heavy repair coil.",
            "room_id": None,
            "container_id": "satchel",
            "is_takeable": 1,
            "is_visible": 1,
            "category": "tool",
            "drop_description": "A repair coil lies here.",
        },
        {
            "id": "case",
            "name": "case",
            "description": "A lockbox.",
            "examine_description": "A lockbox on the floor.",
            "room_id": "start",
            "is_takeable": 0,
            "is_visible": 1,
            "category": "container",
            "room_description": "A lockbox sits here.",
            "is_container": 1,
            "is_open": 0,
            "has_lid": 1,
            "is_locked": 1,
            "key_item_id": "case_key",
            "lock_message": "Locked.",
            "open_message": "Opened.",
            "unlock_message": "Unlocked.",
        },
        {
            "id": "battery",
            "name": "battery",
            "description": "A battery.",
            "examine_description": "A fresh battery.",
            "room_id": "start",
            "is_takeable": 1,
            "is_visible": 1,
            "category": "consumable",
            "room_description": "A battery sits here.",
            "drop_description": "A battery lies here.",
        },
        {
            "id": "case_key",
            "name": "case key",
            "description": "A key.",
            "examine_description": "A small case key.",
            "room_id": "start",
            "is_takeable": 1,
            "is_visible": 1,
            "category": "key",
            "room_description": "A small key glints here.",
            "drop_description": "A small key lies here.",
        },
    ]

    inserted = _insert_items(db, items, {"rooms": [{"id": "start"}]})

    inserted_ids = [item["id"] for item in inserted]
    assert set(inserted_ids) == {
        "battery",
        "case_key",
        "case",
        "lantern",
        "satchel",
        "repair_coil",
    }
    assert inserted_ids.index("battery") < inserted_ids.index("lantern")
    assert inserted_ids.index("case_key") < inserted_ids.index("case")
    assert inserted_ids.index("case") < inserted_ids.index("satchel")
    assert inserted_ids.index("satchel") < inserted_ids.index("repair_coil")
    assert db.get_item("satchel")["container_id"] == "case"
    assert db.get_item("repair_coil")["container_id"] == "satchel"
    assert db.get_item("case")["key_item_id"] == "case_key"
    assert db.get_item("lantern")["requires_item_id"] == "battery"

    db.close()


def test_enforce_lock_key_placements_uses_lock_mapping_room() -> None:
    items = [
        {
            "id": "study_key",
            "name": "study key",
            "description": "A small iron key.",
            "examine_description": "A small iron key marked STUDY.",
            "room_id": "lord_ashworths_boudoir",
            "container_id": "jewelry_box",
            "home_room_id": "lord_ashworths_boudoir",
        },
        {
            "id": "jewelry_box",
            "name": "jewelry box",
            "description": "A small box.",
            "examine_description": "A velvet-lined jewelry box.",
            "room_id": "lord_ashworths_boudoir",
            "home_room_id": "lord_ashworths_boudoir",
        },
    ]

    _enforce_lock_key_placements(
        items,
        {
            "lock_key_mapping": {
                "study_door_lock": {
                    "key_item_id": "study_key",
                    "key_location_room_id": "entrance_hall",
                }
            }
        },
    )

    key = next(item for item in items if item["id"] == "study_key")
    assert key["room_id"] == "entrance_hall"
    assert key["home_room_id"] == "entrance_hall"
    assert key["container_id"] is None


def test_enforce_lock_key_placements_keeps_valid_container_hiding_spot() -> None:
    items = [
        {
            "id": "security_key_box",
            "name": "security key box",
            "room_id": "security_office",
            "home_room_id": "security_office",
            "is_container": 1,
        },
        {
            "id": "study_key",
            "name": "study key",
            "description": "A small iron key.",
            "examine_description": "A small iron key marked STUDY.",
            "room_id": None,
            "container_id": "security_key_box",
            "home_room_id": "security_office",
        },
    ]

    _enforce_lock_key_placements(
        items,
        {
            "lock_key_mapping": {
                "study_door_lock": {
                    "key_item_id": "study_key",
                    "candidate_room_ids": ["security_office", "lobby"],
                    "fallback_room_id": "lobby",
                }
            }
        },
    )

    key = next(item for item in items if item["id"] == "study_key")
    assert key["room_id"] is None
    assert key["container_id"] == "security_key_box"
    assert key["home_room_id"] == "security_office"


def test_fill_missing_item_descriptions_adds_room_and_drop_fallbacks() -> None:
    items = [
        {
            "id": "study_key",
            "name": "study key",
            "room_id": "entrance_hall",
            "container_id": None,
            "is_takeable": 1,
            "is_visible": 1,
            "room_description": None,
            "drop_description": None,
        }
    ]

    _fill_missing_item_descriptions(items)

    assert items[0]["room_description"] == "A study key is here."
    assert items[0]["drop_description"] == "A study key lies here."


def test_lock_reachability_allows_valid_nested_key_chain() -> None:
    errors: list[str] = []

    _validate_reachability(
        locks=[
            {
                "id": "front_door_lock",
                "lock_type": "key",
                "target_exit_id": "start_to_hall",
                "key_item_id": "front_door_key",
                "key_location_room_id": "start",
            },
            {
                "id": "vault_lock",
                "lock_type": "key",
                "target_exit_id": "hall_to_vault",
                "key_item_id": "vault_key",
                "key_location_room_id": "hall",
            },
        ],
        rooms=[
            {"id": "start", "is_start": 1},
            {"id": "hall", "is_start": 0},
            {"id": "vault", "is_start": 0},
        ],
        exits_list=[
            {"id": "start_to_hall", "from_room_id": "start", "to_room_id": "hall"},
            {"id": "hall_to_vault", "from_room_id": "hall", "to_room_id": "vault"},
        ],
        errors=errors,
    )

    assert errors == []


def test_lock_reachability_rejects_self_locked_key_chain() -> None:
    errors: list[str] = []

    _validate_reachability(
        locks=[
            {
                "id": "front_door_lock",
                "lock_type": "key",
                "target_exit_id": "start_to_hall",
                "key_item_id": "front_door_key",
                "key_location_room_id": "start",
            },
            {
                "id": "vault_lock",
                "lock_type": "key",
                "target_exit_id": "hall_to_vault",
                "key_item_id": "vault_key",
                "key_location_room_id": "vault",
            },
        ],
        rooms=[
            {"id": "start", "is_start": 1},
            {"id": "hall", "is_start": 0},
            {"id": "vault", "is_start": 0},
        ],
        exits_list=[
            {"id": "start_to_hall", "from_room_id": "start", "to_room_id": "hall"},
            {"id": "hall_to_vault", "from_room_id": "hall", "to_room_id": "vault"},
        ],
        errors=errors,
    )

    assert errors == [
        "Key-gate violation: lock 'vault_lock' requires key 'vault_key' in room "
        "'vault', but that room is not reachable before this lock in any valid "
        "unlock order.",
        "No valid unlock order exists for key locks: vault_lock",
    ]


def test_repair_key_locations_moves_self_locked_key_to_last_reachable_room() -> None:
    locks = [
        {
            "id": "front_door_lock",
            "lock_type": "key",
            "target_exit_id": "start_to_hall",
            "key_item_id": "front_door_key",
            "key_location_room_id": "start",
        },
        {
            "id": "vault_lock",
            "lock_type": "key",
            "target_exit_id": "hall_to_vault",
            "key_item_id": "vault_key",
            "key_location_room_id": "vault",
        },
    ]

    _repair_key_locations(
        locks=locks,
        rooms=[
            {"id": "start", "region": "house", "is_start": 1},
            {"id": "hall", "region": "house", "is_start": 0},
            {"id": "vault", "region": "vault", "is_start": 0},
        ],
        exits_list=[
            {"id": "start_to_hall", "from_room_id": "start", "to_room_id": "hall"},
            {"id": "hall_to_vault", "from_room_id": "hall", "to_room_id": "vault"},
        ],
    )

    assert locks[1]["key_location_room_id"] == "hall"


def test_key_candidate_rooms_include_rooms_unlocked_by_prior_key_chain() -> None:
    candidates = _key_candidate_rooms(
        lock={
            "id": "vault_lock",
            "lock_type": "key",
            "target_exit_id": "hall_to_vault",
        },
        locks=[
            {
                "id": "front_door_lock",
                "lock_type": "key",
                "target_exit_id": "start_to_hall",
                "key_item_id": "front_door_key",
                "key_location_room_id": "start",
            },
            {
                "id": "vault_lock",
                "lock_type": "key",
                "target_exit_id": "hall_to_vault",
            },
        ],
        rooms=[
            {"id": "start", "region": "house", "is_start": 1},
            {"id": "hall", "region": "house", "is_start": 0},
            {"id": "office", "region": "house", "is_start": 0},
            {"id": "vault", "region": "vault", "is_start": 0},
        ],
        exits_list=[
            {"id": "start_to_hall", "from_room_id": "start", "to_room_id": "hall"},
            {"id": "hall_to_office", "from_room_id": "hall", "to_room_id": "office"},
            {"id": "hall_to_vault", "from_room_id": "hall", "to_room_id": "vault"},
        ],
    )

    assert candidates == ["hall", "start", "office"]


def test_effective_item_room_uses_container_room() -> None:
    items_by_id = {
        "security_key_box": {
            "id": "security_key_box",
            "room_id": "security_office",
            "home_room_id": "security_office",
        },
        "study_key": {
            "id": "study_key",
            "room_id": None,
            "container_id": "security_key_box",
        },
    }

    assert _effective_item_room(items_by_id["study_key"], items_by_id) == "security_office"
