from __future__ import annotations

from anyzork.zorkscript import parse_zorkscript


def test_parse_zorkscript_reads_minimal_world(minimal_zorkscript: str) -> None:
    spec = parse_zorkscript(minimal_zorkscript)

    assert spec["game"]["title"] == "CLI Import Game"
    assert spec["player"]["start_room_id"] == "foyer"
    assert len(spec["rooms"]) == 2
    assert {room["id"] for room in spec["rooms"]} == {"foyer", "study"}
    assert spec["flags"][0]["id"] == "game_won"
