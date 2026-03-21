from __future__ import annotations

from anyzork.zorkscript import parse_zorkscript


def test_parse_zorkscript_reads_minimal_world(minimal_zorkscript: str) -> None:
    spec = parse_zorkscript(minimal_zorkscript)

    assert spec["game"]["title"] == "CLI Import Game"
    assert spec["player"]["start_room_id"] == "foyer"
    assert len(spec["rooms"]) == 2
    assert {room["id"] for room in spec["rooms"]} == {"foyer", "study"}
    assert spec["flags"][0]["id"] == "game_won"


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
