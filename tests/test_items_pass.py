from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.generator.passes.items import (
    _enforce_lock_key_placements,
    _fill_missing_item_descriptions,
    _insert_items,
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
