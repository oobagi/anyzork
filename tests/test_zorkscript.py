from __future__ import annotations

from anyzork.zorkscript import parse_zorkscript


def test_parse_zorkscript_reads_minimal_world(minimal_zorkscript: str) -> None:
    spec = parse_zorkscript(minimal_zorkscript)

    assert spec["game"]["title"] == "CLI Import Game"
    assert spec["player"]["start_room_id"] == "foyer"
    assert len(spec["rooms"]) == 2
    assert {room["id"] for room in spec["rooms"]} == {"foyer", "study"}
    assert spec["flags"][0]["id"] == "game_won"


def test_parse_talk_block_with_effects() -> None:
    """Effect lines in talk blocks should be parsed into dialogue nodes."""
    zs = """\
game {
  title "Effect Dialogue Test"
  author "Test"
  max_score 10
  win [game_won]
}

player {
  start tavern
}

room tavern {
  name "Tavern"
  description "A warm tavern."
  short "A warm tavern."
  region "town"
  start true
}

item magic_ring {
  name "Magic Ring"
  description "A glowing ring."
}

npc barkeep {
  name "Barkeep"
  description "A friendly barkeep."
  in tavern
  dialogue "What'll it be?"
  category "character"

  talk root {
    "Welcome, traveler! Take this ring."
    effect spawn_item(magic_ring, _inventory)
    effect add_score(5)
    sets [received_ring]
    option "Thanks!" -> end
  }
}

flag game_won "Victory"
flag received_ring "Got the ring"
"""
    spec = parse_zorkscript(zs)

    # Should have one dialogue node with effects
    assert len(spec["dialogue_nodes"]) == 1
    node = spec["dialogue_nodes"][0]
    assert node["id"] == "barkeep_root"
    assert node["is_root"] is True
    assert node["set_flags"] == ["received_ring"]

    # Effects should be parsed
    effects = node["effects"]
    assert len(effects) == 2
    assert effects[0] == {"type": "spawn_item", "item": "magic_ring", "location": "_inventory"}
    assert effects[1] == {"type": "add_score", "points": 5}

    # Options should still work
    assert len(spec["dialogue_options"]) == 1
    assert spec["dialogue_options"][0]["text"] == "Thanks!"
