"""Comprehensive tests for the ZorkScript parser."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from anyzork.zorkscript import ZorkScriptError, parse_zorkscript


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_game_source() -> str:
    """A minimal but complete ZorkScript game."""
    return textwrap.dedent("""\
        game {
          title       "Tiny Test"
          author      "A test game."
          intro       "You arrive."
          win_text    "You win."
          max_score   10
          realism     "medium"
          win         [escaped]
        }

        player {
          start  cellar
          hp     100
          max_hp 100
        }

        room cellar {
          name        "The Cellar"
          description "A damp cellar."
          short       "Damp cellar."
          region      "underground"
          start       true
        }

        flag escaped "Player escaped"
    """)


# ---------------------------------------------------------------------------
# 1. Minimal complete game
# ---------------------------------------------------------------------------

class TestMinimalGame:

    def test_parses_without_error(self):
        spec = parse_zorkscript(_minimal_game_source())
        assert spec["format"] == "anyzork.import.v1"

    def test_game_block_fields(self):
        spec = parse_zorkscript(_minimal_game_source())
        game = spec["game"]
        assert game["title"] == "Tiny Test"
        assert game["author_prompt"] == "A test game."
        assert game["intro_text"] == "You arrive."
        assert game["win_text"] == "You win."
        assert game["max_score"] == 10
        assert game["realism"] == "medium"
        assert game["win_conditions"] == ["escaped"]

    def test_player_block_fields(self):
        spec = parse_zorkscript(_minimal_game_source())
        player = spec["player"]
        assert player["start_room_id"] == "cellar"
        assert player["hp"] == 100
        assert player["max_hp"] == 100

    def test_room_present(self):
        spec = parse_zorkscript(_minimal_game_source())
        assert len(spec["rooms"]) == 1
        room = spec["rooms"][0]
        assert room["id"] == "cellar"
        assert room["name"] == "The Cellar"
        assert room["is_start"] is True

    def test_flag_present(self):
        spec = parse_zorkscript(_minimal_game_source())
        assert len(spec["flags"]) == 1
        flag = spec["flags"][0]
        assert flag["id"] == "escaped"
        assert flag["description"] == "Player escaped"
        assert flag["value"] is False

    def test_empty_collections(self):
        spec = parse_zorkscript(_minimal_game_source())
        assert spec["exits"] == []
        assert spec["items"] == []
        assert spec["npcs"] == []
        assert spec["commands"] == []
        assert spec["triggers"] == []
        assert spec["interactions"] == []
        assert spec["dialogue_nodes"] == []
        assert spec["dialogue_options"] == []
        assert spec["locks"] == []
        assert spec["puzzles"] == []
        assert spec["quests"] == []
        assert spec["interaction_responses"] == []


# ---------------------------------------------------------------------------
# 2. Rooms with inline exits
# ---------------------------------------------------------------------------

class TestRoomsAndExits:

    SOURCE = textwrap.dedent("""\
        game {
          title "Exit Test"
          author "test"
          win [done]
        }
        player { start cellar }

        room cellar {
          name        "The Cellar"
          description "Dark room."
          region      "underground"

          exit north -> courtyard
          exit east -> closet (locked)
          exit south -> tunnel (hidden)
          exit west -> garden (locked, hidden) "A vine-covered archway."
        }

        room courtyard {
          name        "Courtyard"
          description "Open air."
          region      "surface"
        }

        room closet {
          name        "Closet"
          description "Small closet."
          region      "underground"
        }

        room tunnel {
          name        "Tunnel"
          description "Dark tunnel."
          region      "underground"
        }

        room garden {
          name        "Garden"
          description "A garden."
          region      "surface"
        }

        flag done "done"
    """)

    def test_exit_count(self):
        spec = parse_zorkscript(self.SOURCE)
        assert len(spec["exits"]) == 4

    def test_basic_exit(self):
        spec = parse_zorkscript(self.SOURCE)
        north = next(e for e in spec["exits"] if e["direction"] == "north")
        assert north["id"] == "cellar_north"
        assert north["from_room_id"] == "cellar"
        assert north["to_room_id"] == "courtyard"
        assert north["is_locked"] is False
        assert north["is_hidden"] is False

    def test_locked_exit(self):
        spec = parse_zorkscript(self.SOURCE)
        east = next(e for e in spec["exits"] if e["direction"] == "east")
        assert east["id"] == "cellar_east"
        assert east["is_locked"] is True
        assert east["is_hidden"] is False

    def test_hidden_exit(self):
        spec = parse_zorkscript(self.SOURCE)
        south = next(e for e in spec["exits"] if e["direction"] == "south")
        assert south["is_hidden"] is True
        assert south["is_locked"] is False

    def test_locked_hidden_with_description(self):
        spec = parse_zorkscript(self.SOURCE)
        west = next(e for e in spec["exits"] if e["direction"] == "west")
        assert west["is_locked"] is True
        assert west["is_hidden"] is True
        assert west["description"] == "A vine-covered archway."


# ---------------------------------------------------------------------------
# 3. Items with all variants
# ---------------------------------------------------------------------------

class TestItems:

    def test_basic_item(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "R." region "w" }
            flag x "x"

            item iron_key {
              name        "Iron Key"
              description "A blackened iron key."
              examine     "Heavy and cold."
              in          r
              takeable    true
              visible     true
              room_desc   "A key on the floor."
            }
        """)
        spec = parse_zorkscript(source)
        assert len(spec["items"]) == 1
        item = spec["items"][0]
        assert item["id"] == "iron_key"
        assert item["name"] == "Iron Key"
        assert item["examine_description"] == "Heavy and cold."
        assert item["room_id"] == "r"
        assert item["is_takeable"] is True
        assert item["is_visible"] is True
        assert item["room_description"] == "A key on the floor."

    def test_container_item(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "R." region "w" }
            flag x "x"

            item chest {
              name          "Chest"
              description   "An old chest."
              examine       "Iron bands."
              in            r
              container     true
              open          false
              has_lid       true
              locked        true
              key           rusty_key
              consume_key   true
            }
        """)
        spec = parse_zorkscript(source)
        item = spec["items"][0]
        assert item["is_container"] is True
        assert item["is_open"] is False
        assert item["has_lid"] is True
        assert item["is_locked"] is True
        assert item["key_item_id"] == "rusty_key"
        assert item["consume_key"] is True

    def test_toggleable_item(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "R." region "w" }
            flag x "x"

            item lamp {
              name          "Lamp"
              description   "A lamp."
              examine       "Half full."
              in            r
              toggle        true
              toggle_state  "off"
            }
        """)
        spec = parse_zorkscript(source)
        item = spec["items"][0]
        assert item["is_toggleable"] is True
        assert item["toggle_state"] == "off"

    def test_quantity_item(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "R." region "w" }
            flag x "x"

            item revolver {
              name            "Revolver"
              description     "A six-shot."
              examine         "Four left."
              in              r
              quantity        4
              max_quantity    6
              quantity_unit   "rounds"
              tags            ["weapon", "firearm"]
            }
        """)
        spec = parse_zorkscript(source)
        item = spec["items"][0]
        assert item["quantity"] == 4
        assert item["max_quantity"] == 6
        assert item["quantity_unit"] == "rounds"
        assert item["item_tags"] == ["weapon", "firearm"]


# ---------------------------------------------------------------------------
# 4. NPCs with nested dialogue
# ---------------------------------------------------------------------------

class TestNPCsAndDialogue:

    SOURCE = textwrap.dedent("""\
        game { title "T" author "A" win [x] }
        player { start r }
        room r { name "R" description "R." region "w" }
        room courtyard { name "C" description "C." region "w" }
        flag x "x"
        flag guard_bribed "Guard bribed"

        npc guard {
          name        "The Guard"
          description "A heavyset man."
          examine     "Bloodshot eyes."
          in          r
          dialogue    "He barely looks up."
          blocking    r -> courtyard north
          unblock_flag guard_bribed

          talk root {
            "Another rat from the cells."
            option "I have something." -> bribe {
              require_item silver_key
            }
            option "I'll find another way."
          }

          talk bribe {
            "His eyes fix on the key."
            sets [guard_bribed]
          }
        }
    """)

    def test_npc_fields(self):
        spec = parse_zorkscript(self.SOURCE)
        assert len(spec["npcs"]) == 1
        npc = spec["npcs"][0]
        assert npc["id"] == "guard"
        assert npc["name"] == "The Guard"
        assert npc["examine_description"] == "Bloodshot eyes."
        assert npc["room_id"] == "r"
        assert npc["default_dialogue"] == "He barely looks up."
        assert npc["is_blocking"] is True
        assert npc["unblock_flag"] == "guard_bribed"

    def test_dialogue_nodes(self):
        spec = parse_zorkscript(self.SOURCE)
        nodes = spec["dialogue_nodes"]
        assert len(nodes) == 2
        root = nodes[0]
        assert root["id"] == "guard_root"
        assert root["npc_id"] == "guard"
        assert root["is_root"] is True
        assert root["content"] == "Another rat from the cells."

        bribe = nodes[1]
        assert bribe["id"] == "guard_bribe"
        assert bribe["is_root"] is False
        assert bribe["content"] == "His eyes fix on the key."
        assert bribe["set_flags"] == ["guard_bribed"]

    def test_dialogue_options(self):
        spec = parse_zorkscript(self.SOURCE)
        opts = spec["dialogue_options"]
        assert len(opts) == 2

        opt0 = opts[0]
        assert opt0["id"] == "guard_root_opt_0"
        assert opt0["node_id"] == "guard_root"
        assert opt0["text"] == "I have something."
        assert opt0["next_node_id"] == "guard_bribe"
        assert opt0["required_items"] == ["silver_key"]
        assert opt0["sort_order"] == 0

        opt1 = opts[1]
        assert opt1["id"] == "guard_root_opt_1"
        assert opt1["text"] == "I'll find another way."
        assert "next_node_id" not in opt1  # terminal
        assert opt1["sort_order"] == 1

    def test_npc_blocking_exit_resolved(self):
        # Need the exit to exist for resolution
        source = self.SOURCE + textwrap.dedent("""\
            room r {
              name "R" description "R." region "w"
              exit north -> courtyard
            }
        """)
        # Re-parse with rooms that have exits. Since we already have room 'r',
        # the parser just adds a second 'r' room (it does not deduplicate).
        # For this test, we verify the exit lookup works.
        spec = parse_zorkscript(source)
        npc = spec["npcs"][0]
        assert npc["blocked_exit_id"] == "r_north"


# ---------------------------------------------------------------------------
# 5. Locks referencing exits by route
# ---------------------------------------------------------------------------

class TestLocks:

    SOURCE = textwrap.dedent("""\
        game { title "T" author "A" win [x] }
        player { start cellar }
        room cellar {
          name "Cellar" description "Dark." region "underground"
          exit north -> courtyard
        }
        room courtyard {
          name "Courtyard" description "Open." region "surface"
        }
        flag x "x"

        lock cellar_door_lock {
          exit     cellar -> courtyard north
          type     "key"
          key      iron_key
          consume  true
          locked   "The iron door is locked."
          unlocked "The lock grinds open."
        }
    """)

    def test_lock_fields(self):
        spec = parse_zorkscript(self.SOURCE)
        assert len(spec["locks"]) == 1
        lock = spec["locks"][0]
        assert lock["id"] == "cellar_door_lock"
        assert lock["lock_type"] == "key"
        assert lock["key_item_id"] == "iron_key"
        assert lock["consume_key"] is True
        assert lock["locked_message"] == "The iron door is locked."
        assert lock["unlock_message"] == "The lock grinds open."

    def test_lock_exit_resolved(self):
        spec = parse_zorkscript(self.SOURCE)
        lock = spec["locks"][0]
        assert lock["target_exit_id"] == "cellar_north"


# ---------------------------------------------------------------------------
# 6. Puzzles
# ---------------------------------------------------------------------------

class TestPuzzles:

    SOURCE = textwrap.dedent("""\
        game { title "T" author "A" win [x] }
        player { start cellar }
        room cellar { name "Cellar" description "." region "w" }
        flag x "x"

        puzzle escape_cellar {
          name        "Escape the Cellar"
          description "Find the key."
          in          cellar
          score       10
          steps       ["Take the iron key", "Use it on the door"]
          hint        "Look under the jars."
        }
    """)

    def test_puzzle_fields(self):
        spec = parse_zorkscript(self.SOURCE)
        assert len(spec["puzzles"]) == 1
        p = spec["puzzles"][0]
        assert p["id"] == "escape_cellar"
        assert p["name"] == "Escape the Cellar"
        assert p["room_id"] == "cellar"
        assert p["score_value"] == 10
        assert p["solution_steps"] == ["Take the iron key", "Use it on the door"]
        assert p["hint_text"] == "Look under the jars."


# ---------------------------------------------------------------------------
# 7. Single-line flags
# ---------------------------------------------------------------------------

class TestFlags:

    def test_single_line_flags(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }

            flag x "done"
            flag door_unlocked "The cellar door unlocked"
            flag escaped "Player escaped"
        """)
        spec = parse_zorkscript(source)
        assert len(spec["flags"]) == 3
        ids = [f["id"] for f in spec["flags"]]
        assert "x" in ids
        assert "door_unlocked" in ids
        assert "escaped" in ids
        for f in spec["flags"]:
            assert f["value"] is False

    def test_block_form_flag(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }

            flag x { description "The flag" value false }
        """)
        spec = parse_zorkscript(source)
        assert len(spec["flags"]) == 1
        assert spec["flags"][0]["description"] == "The flag"


# ---------------------------------------------------------------------------
# 8. Quests with inline objectives
# ---------------------------------------------------------------------------

class TestQuests:

    SOURCE = textwrap.dedent("""\
        game { title "T" author "A" win [x] }
        player { start r }
        room r { name "R" description "." region "w" }
        flag x "x"
        flag escaped "escaped"
        flag door_unlocked "door unlocked"

        quest main:escape {
          name        "Escape"
          description "Find a way out."
          completion  escaped
          discovery   door_unlocked
          score       0

          objective "Find the key" -> door_unlocked
          objective "Escape" -> escaped (optional, bonus: 5)
        }
    """)

    def test_quest_fields(self):
        spec = parse_zorkscript(self.SOURCE)
        assert len(spec["quests"]) == 1
        q = spec["quests"][0]
        assert q["id"] == "escape"
        assert q["quest_type"] == "main"
        assert q["name"] == "Escape"
        assert q["completion_flag"] == "escaped"
        assert q["discovery_flag"] == "door_unlocked"
        assert q["score_value"] == 0

    def test_quest_objectives(self):
        spec = parse_zorkscript(self.SOURCE)
        q = spec["quests"][0]
        objs = q["objectives"]
        assert len(objs) == 2

        obj0 = objs[0]
        assert obj0["id"] == "escape_obj_0"
        assert obj0["description"] == "Find the key"
        assert obj0["completion_flag"] == "door_unlocked"
        assert obj0["is_optional"] is False
        assert obj0["bonus_score"] == 0
        assert obj0["order_index"] == 0

        obj1 = objs[1]
        assert obj1["id"] == "escape_obj_1"
        assert obj1["description"] == "Escape"
        assert obj1["completion_flag"] == "escaped"
        assert obj1["is_optional"] is True
        assert obj1["bonus_score"] == 5

    def test_side_quest(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"
            flag done "d"

            quest side:bonus {
              name "Bonus"
              description "Optional."
              completion done
            }
        """)
        spec = parse_zorkscript(source)
        q = spec["quests"][0]
        assert q["quest_type"] == "side"
        assert q["id"] == "bonus"


# ---------------------------------------------------------------------------
# 9. on blocks with preconditions and effects
# ---------------------------------------------------------------------------

class TestOnBlocks:

    SOURCE = textwrap.dedent("""\
        game { title "T" author "A" win [x] }
        player { start cellar }
        room cellar { name "C" description "." region "w" }
        flag x "x"
        flag door_unlocked "unlocked"

        on "use {item} on {target}" in [cellar] {
          require has_item(iron_key)
          require not_flag(door_unlocked)

          effect remove_item(iron_key)
          effect unlock(cellar_door_lock)
          effect set_flag(door_unlocked)
          effect add_score(10)

          success "The lock grinds open."
          fail    "You need the right key."
          once
        }
    """)

    def test_command_fields(self):
        spec = parse_zorkscript(self.SOURCE)
        assert len(spec["commands"]) == 1
        cmd = spec["commands"][0]
        assert cmd["verb"] == "use"
        assert cmd["pattern"] == "use {item} on {target}"
        assert cmd["context_room_ids"] == ["cellar"]
        assert cmd["success_message"] == "The lock grinds open."
        assert cmd["failure_message"] == "You need the right key."
        assert cmd["one_shot"] is True
        assert cmd["executed"] is False

    def test_preconditions(self):
        spec = parse_zorkscript(self.SOURCE)
        cmd = spec["commands"][0]
        preconds = cmd["preconditions"]
        assert len(preconds) == 2
        assert preconds[0] == {"type": "has_item", "item": "iron_key"}
        assert preconds[1] == {"type": "not_flag", "flag": "door_unlocked"}

    def test_effects(self):
        spec = parse_zorkscript(self.SOURCE)
        cmd = spec["commands"][0]
        effects = cmd["effects"]
        assert len(effects) == 4
        assert effects[0] == {"type": "remove_item", "item": "iron_key"}
        assert effects[1] == {"type": "unlock", "lock": "cellar_door_lock"}
        assert effects[2] == {"type": "set_flag", "flag": "door_unlocked", "value": True}
        assert effects[3] == {"type": "add_score", "points": 10}

    def test_command_auto_id(self):
        spec = parse_zorkscript(self.SOURCE)
        cmd = spec["commands"][0]
        assert cmd["id"] == "on_use_item_on_target_cellar"

    def test_global_command_no_rooms(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on "look around" {
              effect print("You look around.")
              success "Nothing special."
            }
        """)
        spec = parse_zorkscript(source)
        cmd = spec["commands"][0]
        assert cmd["context_room_ids"] == []
        assert cmd["id"] == "on_look_around"

    def test_priority_field(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on "test" {
              priority 5
              success "ok"
            }
        """)
        spec = parse_zorkscript(source)
        assert spec["commands"][0]["priority"] == 5

    def test_all_precondition_types(self):
        """Verify the parser can compile all 17 precondition types."""
        precond_lines = [
            'require in_room(cellar)',
            'require has_item(key)',
            'require has_flag(open)',
            'require not_flag(closed)',
            'require item_in_room(key, cellar)',
            'require item_accessible(key)',
            'require npc_in_room(guard, _current)',
            'require lock_unlocked(door_lock)',
            'require puzzle_solved(p1)',
            'require health_above(10)',
            'require container_open(chest)',
            'require item_in_container(gem, chest)',
            'require not_item_in_container(gem, chest)',
            'require container_has_contents(chest)',
            'require container_empty(chest)',
            'require has_quantity(ammo, 1)',
            'require toggle_state(lamp, "on")',
        ]
        body = "\n          ".join(precond_lines)
        source = textwrap.dedent(f"""\
            game {{ title "T" author "A" win [x] }}
            player {{ start r }}
            room r {{ name "R" description "." region "w" }}
            flag x "x"

            on "test" {{
              {body}
              success "ok"
            }}
        """)
        spec = parse_zorkscript(source)
        preconds = spec["commands"][0]["preconditions"]
        assert len(preconds) == 17
        types = [p["type"] for p in preconds]
        assert "in_room" in types
        assert "toggle_state" in types

    def test_all_effect_types(self):
        """Verify the parser can compile all 18 effect types."""
        effect_lines = [
            'effect move_item(key, cellar, _inventory)',
            'effect remove_item(key)',
            'effect set_flag(open)',
            'effect unlock(door_lock)',
            'effect move_player(hall)',
            'effect spawn_item(gem, _inventory)',
            'effect change_health(-10)',
            'effect add_score(5)',
            'effect reveal_exit(hidden_door)',
            'effect solve_puzzle(p1)',
            'effect discover_quest(q1)',
            'effect print("Hello.")',
            'effect open_container(chest)',
            'effect move_item_to_container(gem, chest)',
            'effect take_item_from_container(gem)',
            'effect consume_quantity(ammo, 1)',
            'effect restore_quantity(ammo, 6)',
            'effect set_toggle_state(lamp, "on")',
        ]
        body = "\n          ".join(effect_lines)
        source = textwrap.dedent(f"""\
            game {{ title "T" author "A" win [x] }}
            player {{ start r }}
            room r {{ name "R" description "." region "w" }}
            flag x "x"

            on "test" {{
              {body}
              success "ok"
            }}
        """)
        spec = parse_zorkscript(source)
        effects = spec["commands"][0]["effects"]
        assert len(effects) == 18
        types = [e["type"] for e in effects]
        assert "move_item" in types
        assert "set_toggle_state" in types

    def test_set_flag_with_false_value(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on "test" {
              effect set_flag(torch_lit, false)
              success "ok"
            }
        """)
        spec = parse_zorkscript(source)
        eff = spec["commands"][0]["effects"][0]
        assert eff["type"] == "set_flag"
        assert eff["flag"] == "torch_lit"
        assert eff["value"] is False


# ---------------------------------------------------------------------------
# 10. when blocks for all event types
# ---------------------------------------------------------------------------

class TestWhenBlocks:

    def _make_trigger_source(self, event_call: str) -> str:
        return textwrap.dedent(f"""\
            game {{ title "T" author "A" win [x] }}
            player {{ start r }}
            room r {{ name "R" description "." region "w" }}
            flag x "x"

            when {event_call} {{
              effect set_flag(x)
              message "Triggered."
              once
            }}
        """)

    def test_room_enter(self):
        spec = parse_zorkscript(self._make_trigger_source("room_enter(courtyard)"))
        t = spec["triggers"][0]
        assert t["event_type"] == "room_enter"
        assert t["event_data"] == {"room_id": "courtyard"}
        assert t["one_shot"] is True
        assert t["message"] == "Triggered."

    def test_flag_set(self):
        spec = parse_zorkscript(self._make_trigger_source("flag_set(door_opened)"))
        t = spec["triggers"][0]
        assert t["event_type"] == "flag_set"
        assert t["event_data"] == {"flag": "door_opened"}

    def test_item_taken(self):
        spec = parse_zorkscript(self._make_trigger_source("item_taken(key)"))
        t = spec["triggers"][0]
        assert t["event_type"] == "item_taken"
        assert t["event_data"] == {"item_id": "key"}

    def test_item_dropped(self):
        spec = parse_zorkscript(self._make_trigger_source("item_dropped(key)"))
        t = spec["triggers"][0]
        assert t["event_type"] == "item_dropped"
        assert t["event_data"] == {"item_id": "key"}

    def test_dialogue_node(self):
        spec = parse_zorkscript(self._make_trigger_source("dialogue_node(wizard_intro)"))
        t = spec["triggers"][0]
        assert t["event_type"] == "dialogue_node"
        assert t["event_data"] == {"node_id": "wizard_intro"}

    def test_trigger_auto_id(self):
        spec = parse_zorkscript(self._make_trigger_source("room_enter(courtyard)"))
        assert spec["triggers"][0]["id"] == "when_room_enter_courtyard"

    def test_trigger_with_preconditions(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            when room_enter(hall) {
              require not_flag(visited_hall)
              effect set_flag(visited_hall)
              message "First time here."
              once
            }
        """)
        spec = parse_zorkscript(source)
        t = spec["triggers"][0]
        assert len(t["preconditions"]) == 1
        assert t["preconditions"][0]["type"] == "not_flag"


# ---------------------------------------------------------------------------
# 11. Auto-ID generation
# ---------------------------------------------------------------------------

class TestAutoIDs:

    def test_exit_auto_ids(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start hall }
            room hall {
              name "Hall" description "." region "w"
              exit north -> tower
              exit south -> garden
              exit up -> attic
            }
            room tower { name "T" description "." region "w" }
            room garden { name "G" description "." region "w" }
            room attic { name "A" description "." region "w" }
            flag x "x"
        """)
        spec = parse_zorkscript(source)
        ids = [e["id"] for e in spec["exits"]]
        assert "hall_north" in ids
        assert "hall_south" in ids
        assert "hall_up" in ids

    def test_dialogue_auto_ids(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            npc sage {
              name "Sage" description "A sage." examine "Old." in r
              dialogue "Hello."

              talk root {
                "Welcome."
                option "Tell me more." -> lore
                option "Bye."
              }
              talk lore {
                "Ancient secrets."
              }
            }
        """)
        spec = parse_zorkscript(source)
        node_ids = [n["id"] for n in spec["dialogue_nodes"]]
        assert "sage_root" in node_ids
        assert "sage_lore" in node_ids

        opt_ids = [o["id"] for o in spec["dialogue_options"]]
        assert "sage_root_opt_0" in opt_ids
        assert "sage_root_opt_1" in opt_ids

    def test_objective_auto_ids(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"
            flag a "a"
            flag b "b"

            quest main:q {
              name "Q" description "." completion x
              objective "First" -> a
              objective "Second" -> b
            }
        """)
        spec = parse_zorkscript(source)
        objs = spec["quests"][0]["objectives"]
        assert objs[0]["id"] == "q_obj_0"
        assert objs[1]["id"] == "q_obj_1"


# ---------------------------------------------------------------------------
# 12. Multi-line strings
# ---------------------------------------------------------------------------

class TestMultiLineStrings:

    def test_multiline_string_collapsed(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r {
              name "R"
              description "Damp stone walls sweat in the lamplight. A shelf holds
                           forgotten jars. Water drips from somewhere above."
              region "w"
            }
            flag x "x"
        """)
        spec = parse_zorkscript(source)
        desc = spec["rooms"][0]["description"]
        assert "Damp stone walls" in desc
        assert "forgotten jars." in desc
        # Newlines should be collapsed to spaces
        assert "\n" not in desc


# ---------------------------------------------------------------------------
# 13. Comments
# ---------------------------------------------------------------------------

class TestComments:

    def test_comments_are_stripped(self):
        source = textwrap.dedent("""\
            # This is a comment
            game {
              title "T"
              # Another comment
              author "A"
              win [x]
            }
            player { start r }
            room r { name "R" description "." region "w" }  # inline comment
            flag x "x"
        """)
        spec = parse_zorkscript(source)
        assert spec["game"]["title"] == "T"
        assert len(spec["rooms"]) == 1


# ---------------------------------------------------------------------------
# 14. Error cases
# ---------------------------------------------------------------------------

class TestErrors:

    def test_unexpected_character(self):
        with pytest.raises(ZorkScriptError, match="unexpected character"):
            parse_zorkscript("game { title @ }")

    def test_unknown_keyword(self):
        with pytest.raises(ZorkScriptError, match="unknown top-level keyword"):
            parse_zorkscript("banana { }")

    def test_missing_closing_brace(self):
        with pytest.raises(ZorkScriptError, match="expected"):
            parse_zorkscript("game { title \"T\"")

    def test_unknown_precondition(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on "test" {
              require bogus_check(foo)
              success "ok"
            }
        """)
        with pytest.raises(ZorkScriptError, match="unknown precondition"):
            parse_zorkscript(source)

    def test_unknown_effect(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on "test" {
              effect bogus_effect(foo)
              success "ok"
            }
        """)
        with pytest.raises(ZorkScriptError, match="unknown effect"):
            parse_zorkscript(source)

    def test_error_has_line_number(self):
        source = "game {\n  title \"T\"\n  @bad\n}"
        with pytest.raises(ZorkScriptError) as exc_info:
            parse_zorkscript(source)
        assert exc_info.value.line is not None

    def test_expected_string(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on 42 {
              success "ok"
            }
        """)
        with pytest.raises(ZorkScriptError, match="expected STRING"):
            parse_zorkscript(source)


# ---------------------------------------------------------------------------
# 15. End-to-end: parse -> compile_import_spec -> load .zork
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_compile_to_zork_file(self, tmp_path: Path):
        from anyzork.importer import compile_import_spec

        source = textwrap.dedent("""\
            game {
              title       "The Iron Door"
              author      "A two-room escape puzzle."
              intro       "You wake in a stone cellar."
              win_text    "Daylight. You are free."
              max_score   20
              realism     "medium"
              win         [escaped]
            }

            player {
              start  cellar
              hp     100
              max_hp 100
            }

            room cellar {
              name        "The Cellar"
              description "Damp stone walls."
              short       "A damp cellar."
              first_visit "The smell hits you first."
              region      "underground"
              start       true

              exit north -> courtyard (locked)
            }

            room courtyard {
              name        "The Courtyard"
              description "Open sky above crumbling walls."
              short       "A crumbling courtyard."
              region      "surface"
            }

            item iron_key {
              name        "Iron Key"
              description "A blackened iron key."
              examine     "Heavy and cold."
              in          cellar
              takeable    true
              visible     true
              room_desc   "An iron key on the floor."
            }

            lock cellar_door_lock {
              exit     cellar -> courtyard north
              type     "key"
              key      iron_key
              consume  true
              locked   "The iron door is locked."
              unlocked "The lock grinds open."
            }

            puzzle escape_cellar {
              name        "Escape the Cellar"
              description "Find the key and unlock the door."
              in          cellar
              score       10
              steps       ["Take the iron key", "Use it on the door"]
              hint        "Look under the jars."
            }

            flag door_unlocked "The cellar door has been unlocked"
            flag escaped "Player has escaped"

            quest main:escape {
              name        "Escape"
              description "Find a way out."
              completion  escaped

              objective "Find the key" -> door_unlocked
              objective "Escape" -> escaped
            }

            on "use {item} on {target}" in [cellar] {
              require has_item(iron_key)
              require not_flag(door_unlocked)

              effect remove_item(iron_key)
              effect unlock(cellar_door_lock)
              effect set_flag(door_unlocked)
              effect add_score(10)

              success "The lock grinds and the door swings open."
              fail    "You need the right key."
              once
            }

            when room_enter(courtyard) {
              require not_flag(escaped)

              effect set_flag(escaped)
              effect add_score(10)

              message "Daylight washes over you."
              once
            }
        """)

        spec = parse_zorkscript(source)
        output = tmp_path / "iron_door.zork"
        compiled_path, warnings = compile_import_spec(spec, output)

        assert compiled_path.exists()
        assert compiled_path.suffix == ".zork"

        # Verify the DB can be read
        from anyzork.db.schema import GameDB
        db = GameDB(compiled_path)
        try:
            # Check metadata
            title = db.get_meta("title")
            assert title == "The Iron Door"

            # Check rooms
            cellar = db.get_room("cellar")
            assert cellar is not None
            assert cellar["name"] == "The Cellar"

            courtyard = db.get_room("courtyard")
            assert courtyard is not None

            # Check player
            player = db.get_player()
            assert player is not None
            assert player["current_room_id"] == "cellar"

            # Check item
            key = db.get_item("iron_key")
            assert key is not None
            assert key["name"] == "Iron Key"

            # Check lock
            lock = db.get_lock("cellar_door_lock")
            assert lock is not None
            assert lock["lock_type"] == "key"
            assert lock["target_exit_id"] == "cellar_north"

            # Check puzzle
            puzzle = db.get_puzzle("escape_cellar")
            assert puzzle is not None

            # Check flags
            assert db.get_flag("door_unlocked") is not None
            assert db.get_flag("escaped") is not None

            # Check quest
            quest = db.get_quest("escape")
            assert quest is not None
            assert quest["quest_type"] == "main"

        finally:
            db.close()


# ---------------------------------------------------------------------------
# Interaction responses
# ---------------------------------------------------------------------------

class TestInteractionResponses:

    def test_interaction_block(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            interaction fire_on_character {
              tag        "firearm"
              target     "character"
              response   "You fire the {item} at {target}."
              consumes   1
              score      0
              sets_flag  fired_weapon
            }
        """)
        spec = parse_zorkscript(source)
        assert len(spec["interaction_responses"]) == 1
        resp = spec["interaction_responses"][0]
        assert resp["id"] == "fire_on_character"
        assert resp["item_tag"] == "firearm"
        assert resp["target_category"] == "character"
        assert resp["response"] == "You fire the {item} at {target}."
        assert resp["consumes"] == 1
        assert resp["score_change"] == 0
        assert resp["flag_to_set"] == "fired_weapon"


# ---------------------------------------------------------------------------
# Standalone exit / command / trigger / dialogue / option blocks
# ---------------------------------------------------------------------------

class TestStandaloneBlocks:

    def test_standalone_exit_block(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start cellar }
            room cellar { name "C" description "." region "w" }
            room hall { name "H" description "." region "w" }
            flag x "x"

            exit cellar_to_hall {
              from      cellar
              to        hall
              direction north
              is_locked true
            }
        """)
        spec = parse_zorkscript(source)
        assert len(spec["exits"]) == 1
        e = spec["exits"][0]
        assert e["id"] == "cellar_to_hall"
        assert e["from_room_id"] == "cellar"
        assert e["to_room_id"] == "hall"
        assert e["direction"] == "north"
        assert e["is_locked"] is True

    def test_standalone_command_block(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            command use_key {
              verb    "use"
              pattern "use key on door"
              in_rooms [r]
              one_shot true

              require has_item(key)
              effect set_flag(x)

              on_fail "Nope."
            }
        """)
        spec = parse_zorkscript(source)
        cmd = spec["commands"][0]
        assert cmd["id"] == "use_key"
        assert cmd["verb"] == "use"
        assert cmd["pattern"] == "use key on door"
        assert cmd["context_room_ids"] == ["r"]
        assert cmd["one_shot"] is True
        assert cmd["failure_message"] == "Nope."

    def test_standalone_trigger_block(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            trigger enter_r {
              on       room_enter
              when     room_id = r
              one_shot true

              require not_flag(x)
              effect set_flag(x)

              message "Hello."
            }
        """)
        spec = parse_zorkscript(source)
        t = spec["triggers"][0]
        assert t["id"] == "enter_r"
        assert t["event_type"] == "room_enter"
        assert t["event_data"] == {"room_id": "r"}
        assert t["one_shot"] is True
        assert t["message"] == "Hello."

    def test_standalone_dialogue_block(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            dialogue wizard_intro {
              npc       old_wizard
              content   "You look lost."
              is_root   true
            }
        """)
        spec = parse_zorkscript(source)
        node = spec["dialogue_nodes"][0]
        assert node["id"] == "wizard_intro"
        assert node["npc_id"] == "old_wizard"
        assert node["content"] == "You look lost."
        assert node["is_root"] is True

    def test_standalone_option_block(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            option opt_ask_more {
              node      wizard_intro
              text      "Tell me more."
              next_node wizard_quest
              sort_order 0
            }
        """)
        spec = parse_zorkscript(source)
        opt = spec["dialogue_options"][0]
        assert opt["id"] == "opt_ask_more"
        assert opt["node_id"] == "wizard_intro"
        assert opt["text"] == "Tell me more."
        assert opt["next_node_id"] == "wizard_quest"


# ---------------------------------------------------------------------------
# Field name aliasing (lenient parsing)
# ---------------------------------------------------------------------------

class TestFieldAliasing:

    def test_game_field_aliases(self):
        source = textwrap.dedent("""\
            game {
              title           "T"
              author_prompt   "A"
              intro_text      "I"
              win_conditions  [x]
              lose_conditions [y]
            }
            player { start_room_id r }
            room r { name "R" description "." region "w" }
            flag x "x"
            flag y "y"
        """)
        spec = parse_zorkscript(source)
        game = spec["game"]
        assert game["author_prompt"] == "A"
        assert game["intro_text"] == "I"
        assert game["win_conditions"] == ["x"]
        assert game["lose_conditions"] == ["y"]

    def test_player_start_room_alias(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start_room_id r }
            room r { name "R" description "." region "w" }
            flag x "x"
        """)
        spec = parse_zorkscript(source)
        assert spec["player"]["start_room_id"] == "r"

    def test_item_examine_text_alias(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            item k {
              name "K" description "K." examine_text "Detailed." in r
            }
        """)
        spec = parse_zorkscript(source)
        assert spec["items"][0]["examine_description"] == "Detailed."


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_source(self):
        spec = parse_zorkscript("")
        assert spec["format"] == "anyzork.import.v1"
        assert spec["game"] == {}
        assert spec["rooms"] == []

    def test_only_comments(self):
        source = "# comment\n# another\n"
        spec = parse_zorkscript(source)
        assert spec["rooms"] == []

    def test_escape_in_string(self):
        source = textwrap.dedent("""\
            game { title "She said, \\"hello.\\"" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"
        """)
        spec = parse_zorkscript(source)
        assert spec["game"]["title"] == 'She said, "hello."'

    def test_negative_number(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on "test" {
              effect change_health(-10)
              success "ouch"
            }
        """)
        spec = parse_zorkscript(source)
        eff = spec["commands"][0]["effects"][0]
        assert eff["amount"] == -10

    def test_slot_reference_in_precondition(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on "use {item} on {target}" {
              require has_item({item})
              effect print("Used it.")
              success "ok"
            }
        """)
        spec = parse_zorkscript(source)
        p = spec["commands"][0]["preconditions"][0]
        assert p["item"] == "{item}"

    def test_single_room_in_on_block(self):
        """on "..." in cellar { ... } with a bare ident, not a list."""
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start cellar }
            room cellar { name "C" description "." region "w" }
            flag x "x"

            on "test" in cellar {
              success "ok"
            }
        """)
        spec = parse_zorkscript(source)
        assert spec["commands"][0]["context_room_ids"] == ["cellar"]

    def test_lose_conditions(self):
        source = textwrap.dedent("""\
            game {
              title "T" author "A"
              win  [escaped]
              lose [player_dead]
            }
            player { start r }
            room r { name "R" description "." region "w" }
            flag escaped "e"
            flag player_dead "d"
        """)
        spec = parse_zorkscript(source)
        assert spec["game"]["lose_conditions"] == ["player_dead"]

    def test_option_end_is_terminal(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            npc sage {
              name "S" description "S." examine "S." in r dialogue "Hi."

              talk root {
                "Hello."
                option "Bye." -> end
              }
            }
        """)
        spec = parse_zorkscript(source)
        opt = spec["dialogue_options"][0]
        assert opt["next_node_id"] is None

    def test_on_block_with_done_message(self):
        source = textwrap.dedent("""\
            game { title "T" author "A" win [x] }
            player { start r }
            room r { name "R" description "." region "w" }
            flag x "x"

            on "test" {
              success "first time"
              done    "already done"
              once
            }
        """)
        spec = parse_zorkscript(source)
        cmd = spec["commands"][0]
        assert cmd["done_message"] == "already done"
        assert cmd["success_message"] == "first time"
