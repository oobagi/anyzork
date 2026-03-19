from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.engine.commands import apply_effect


def test_spawn_item_supports_container_location(tmp_path: Path) -> None:
    db = GameDB(tmp_path / "spawn_item_test.zork")
    db.initialize(
        game_name="Spawn Item Test",
        author="tests",
        prompt="spawn container",
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
    db.init_player("start")
    db.insert_item(
        id="wardrobe",
        name="wardrobe",
        description="A wardrobe.",
        examine_description="A wardrobe.",
        room_id="start",
        container_id=None,
        is_takeable=0,
        is_visible=1,
        is_consumed_on_use=0,
        is_container=1,
        is_open=1,
        has_lid=1,
        is_locked=0,
        lock_message=None,
        open_message=None,
        search_message=None,
        take_message=None,
        drop_message=None,
        weight=1,
        category="container",
        room_description="A wardrobe stands here.",
        read_description=None,
        key_item_id=None,
        consume_key=0,
        unlock_message=None,
        accepts_items=None,
        reject_message=None,
        home_room_id="start",
        drop_description="A wardrobe stands here.",
        is_toggleable=0,
        toggle_state=None,
        toggle_on_message=None,
        toggle_off_message=None,
        toggle_states=None,
        toggle_messages=None,
        requires_item_id=None,
        requires_message=None,
        item_tags=None,
        quantity=None,
        max_quantity=None,
        quantity_unit=None,
        depleted_message=None,
        quantity_description=None,
    )
    db.insert_item(
        id="hidden_note",
        name="hidden note",
        description="A note.",
        examine_description="A hidden note.",
        room_id=None,
        container_id=None,
        is_takeable=1,
        is_visible=0,
        is_consumed_on_use=0,
        is_container=0,
        is_open=0,
        has_lid=0,
        is_locked=0,
        lock_message=None,
        open_message=None,
        search_message=None,
        take_message=None,
        drop_message=None,
        weight=1,
        category="document",
        room_description=None,
        read_description=None,
        key_item_id=None,
        consume_key=0,
        unlock_message=None,
        accepts_items=None,
        reject_message=None,
        home_room_id="start",
        drop_description="A note lies here.",
        is_toggleable=0,
        toggle_state=None,
        toggle_on_message=None,
        toggle_off_message=None,
        toggle_states=None,
        toggle_messages=None,
        requires_item_id=None,
        requires_message=None,
        item_tags=None,
        quantity=None,
        max_quantity=None,
        quantity_unit=None,
        depleted_message=None,
        quantity_description=None,
    )

    apply_effect({"type": "spawn_item", "item": "hidden_note", "location": "wardrobe"}, db)

    note = db.get_item("hidden_note")
    assert note is not None
    assert note["is_visible"] == 1
    assert note["container_id"] == "wardrobe"
    assert note["room_id"] is None

    db.close()
