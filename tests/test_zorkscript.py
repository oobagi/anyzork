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


def test_parse_combination_lock() -> None:
    """Parser maps 'code' to 'combination' in lock blocks."""
    src = """\
game {
  title "Combo Test"
  author "test"
  max_score 0
  win [game_won]
}

player { start foyer }

room foyer {
  name "Foyer"
  description "A foyer."
  short "A foyer."
  region "house"
  start true

  exit north -> vault
}

room vault {
  name "Vault"
  description "A vault."
  short "A vault."
  region "house"

  exit south -> foyer
}

flag game_won "Win."

lock vault_lock {
  exit foyer -> vault north
  type "combination"
  code "813"
  locked "A combination dial blocks the way."
  unlocked "Click. The lock opens."
}
"""
    spec = parse_zorkscript(src)
    locks = spec["locks"]
    assert len(locks) == 1
    lock = locks[0]
    assert lock["id"] == "vault_lock"
    assert lock["lock_type"] == "combination"
    assert lock["combination"] == "813"
    assert lock["locked_message"] == "A combination dial blocks the way."
    assert lock["unlock_message"] == "Click. The lock opens."


def test_parse_code_locked_container() -> None:
    """Parser maps 'code' to 'combination' in item blocks."""
    src = """\
game {
  title "Container Code Test"
  author "test"
  max_score 0
  win [game_won]
}

player { start foyer }

room foyer {
  name "Foyer"
  description "A foyer."
  short "A foyer."
  region "house"
  start true
}

flag game_won "Win."

item lockbox {
  name "Lockbox"
  description "A small metal box."
  examine "It has a dial."
  in foyer
  takeable false
  container true
  locked true
  code "417"
  lock_msg "The lockbox is locked."
  open_msg "Click. Open."
}
"""
    spec = parse_zorkscript(src)
    items = spec["items"]
    lockbox = next(i for i in items if i["id"] == "lockbox")
    assert lockbox["combination"] == "417"
    assert lockbox["is_locked"] is True
    assert lockbox["is_container"] is True


def test_item_location_and_room_aliases() -> None:
    """'location' and 'room' should map to room_id for items."""
    src = """\
game {
  title "Alias Test"
  author "test"
  max_score 0
  win [game_won]
}

player { start foyer }

room foyer {
  name "Foyer"
  description "A foyer."
  short "A foyer."
  region "house"
  start true
}

flag game_won "Win."

item lantern {
  name "Lantern"
  description "A brass lantern."
  location foyer
}

item sword {
  name "Sword"
  description "A rusty sword."
  room foyer
}
"""
    spec = parse_zorkscript(src)
    items = {i["id"]: i for i in spec["items"]}
    assert items["lantern"]["room_id"] == "foyer"
    assert items["sword"]["room_id"] == "foyer"


def test_item_portable_alias() -> None:
    """'portable' should map to is_takeable for items."""
    src = """\
game {
  title "Portable Test"
  author "test"
  max_score 0
  win [game_won]
}

player { start foyer }

room foyer {
  name "Foyer"
  description "A foyer."
  short "A foyer."
  region "house"
  start true
}

flag game_won "Win."

item anvil {
  name "Anvil"
  description "A heavy anvil."
  portable false
  in foyer
}
"""
    spec = parse_zorkscript(src)
    anvil = next(i for i in spec["items"] if i["id"] == "anvil")
    assert anvil["is_takeable"] is False


def test_npc_location_alias() -> None:
    """'location' and 'room' should map to room_id for NPCs."""
    src = """\
game {
  title "NPC Alias Test"
  author "test"
  max_score 0
  win [game_won]
}

player { start tavern }

room tavern {
  name "Tavern"
  description "A warm tavern."
  short "A warm tavern."
  region "town"
  start true
}

flag game_won "Win."

npc barkeep {
  name "Barkeep"
  description "A friendly barkeep."
  location tavern
  dialogue "What'll it be?"
  category "character"
}
"""
    spec = parse_zorkscript(src)
    npc = next(n for n in spec["npcs"] if n["id"] == "barkeep")
    assert npc["room_id"] == "tavern"


def test_puzzle_location_alias() -> None:
    """'location' and 'room' should map to room_id for puzzles."""
    src = """\
game {
  title "Puzzle Alias Test"
  author "test"
  max_score 10
  win [game_won]
}

player { start foyer }

room foyer {
  name "Foyer"
  description "A foyer."
  short "A foyer."
  region "house"
  start true
}

flag game_won "Win."

puzzle safe_puzzle {
  name "The Safe"
  description "Crack the safe."
  room foyer
  score 10
}
"""
    spec = parse_zorkscript(src)
    puzzle = next(p for p in spec["puzzles"] if p["id"] == "safe_puzzle")
    assert puzzle["room_id"] == "foyer"
