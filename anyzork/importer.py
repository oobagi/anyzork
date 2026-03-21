"""Public AnyZork import-spec compiler.

This module lets users author a full game spec in an external chat UI and
compile it locally into a validated ``.zork`` game file.
"""

# ruff: noqa: E501

from __future__ import annotations

import contextlib
import json
import re
import sys
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

from anyzork.db.schema import GameDB
from anyzork.validation import validate_game


class ImportSpecError(ValueError):
    """Raised when an import spec cannot be parsed or compiled."""


IMPORT_SPEC_FORMAT = "anyzork.import.v1"
ALLOWED_EXIT_DIRECTIONS = ("north", "south", "east", "west", "up", "down")
PUBLIC_INTERACTION_TYPES = (
    "read_item",
    "show_item_to_npc",
    "give_item_to_npc",
    "search_room",
    "search_container",
    "travel_action",
)

_PROMPT_SYSTEM_FILES: tuple[Path, ...] = (
    Path(__file__),
    Path(__file__).with_name("zorkscript.py"),
    Path(__file__).parent / "wizard" / "assembler.py",
    Path(__file__).parent / "wizard" / "fields.py",
    Path(__file__).parent / "wizard" / "presets.py",
    Path(__file__).parent / "wizard" / "wizard.py",
)


@lru_cache(maxsize=1)
def current_prompt_system_version() -> str:
    """Return a short fingerprint for the shipped prompt-generation system."""
    digest = sha256()
    for path in _PROMPT_SYSTEM_FILES:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"ps-{digest.hexdigest()[:12]}"


ZORKSCRIPT_AUTHORING_TEMPLATE = """\
You are authoring a complete, playable text adventure in ZorkScript format.
Output ONLY valid ZorkScript. No markdown, no commentary, no prose outside
the ZorkScript blocks. Follow the grammar shown in the example below exactly.

--- EXAMPLE: A complete mini-game in ZorkScript ---

game {
  title       "The Silver Key"
  author      "A short dungeon escape with containers, light, and puzzles."
  intro       "You wake on cold stone. Iron bars. Darkness."
  win_text    "Daylight. You stumble into the courtyard, free."
  lose_text   "The darkness claims you."
  max_score   100
  realism     "medium"
  win         [escaped_dungeon]
}

player {
  start  cell
  hp     100
}

# -- Rooms -- Use dark rooms with light sources, inline exits with (locked)/(hidden)

room cell {
  name        "Prison Cell"
  description "A narrow stone cell with damp walls. An iron door hangs open to the north. A rickety wooden table stands against the far wall, and a straw pallet lies in the corner. Scratches on the wall mark hundreds of days."
  short       "Your former cell."
  first_visit "The silence here is heavier than the stone walls."
  region      "dungeon"
  start       true

  exit north -> corridor
}

room corridor {
  name        "Dungeon Corridor"
  description "A long corridor lit by guttering torches. The air smells of damp stone and old smoke. Doors line the east wall. To the north, a heavy portcullis blocks the passage."
  short       "A torch-lit corridor running north-south."
  region      "dungeon"

  exit south -> cell
  exit north -> gate_room
  exit east  -> supply_closet
  exit down  -> cellar
}

room supply_closet {
  name        "Supply Closet"
  description "A cramped closet stuffed with crates and mouldering rope. A rusty lever protrudes from the wall, connected to chains that vanish into the ceiling. A wooden shelf holds dusty supplies."
  short       "A cluttered supply closet with a lever on the wall."
  region      "dungeon"

  exit west -> corridor
}

room cellar {
  name        "Dark Cellar"
  description "Pitch darkness swallows everything. The air is cold and still. You can hear water dripping somewhere ahead."
  short       "A pitch-dark cellar."
  first_visit "The darkness is absolute. You cannot see your hand in front of your face."
  region      "dungeon"
  dark        true

  exit up    -> corridor
  exit north -> vault (locked)
}

room vault {
  name        "Old Vault"
  description "A small stone vault, dry and cold. A heavy iron chest sits against the far wall. Cobwebs blanket the ceiling."
  short       "A sealed vault with an iron chest."
  first_visit "Stale air rushes out as the door opens for the first time in years."
  region      "dungeon"
  dark        true

  exit south -> cellar
}

room gate_room {
  name        "Portcullis Chamber"
  description "The corridor ends at a massive iron portcullis. Beyond it, a stone staircase climbs toward daylight. A guard slouches on a stool beside the gate, half-asleep."
  short       "The portcullis chamber. A guard watches the gate."
  region      "dungeon"

  exit south -> corridor
  exit north -> courtyard (locked)
}

room courtyard {
  name        "Sunlit Courtyard"
  description "Warm sunlight floods a flagstone courtyard. An overgrown garden borders the eastern wall. The main road leads west to freedom."
  short       "A bright courtyard outside the dungeon."
  first_visit "The light stings your eyes after so long underground."
  region      "exterior"

  exit south -> gate_room
}

# -- Items --
# take_msg/drop_msg: generic messages that work in ANY room.
# room_desc: shown when item is in its home room. drop_desc: shown elsewhere.
# home: the item's native room (for room_desc vs drop_desc selection).
# Containers (furniture, chests): container/open/locked/key fields.
# Toggleable (torches, switches): toggle/toggle_state/on_msg/off_msg.
# requires: item dependency (e.g. flashlight requires batteries).
#   "use batteries on flashlight" auto-works when requires is set.
# Consumables: quantity/max_quantity/quantity_unit/depleted_msg.
# Tags and categories enable the interaction matrix.
# When an NPC dies, the engine auto-spawns "{Name}'s Body" as a searchable
# container. Use triggers to move_item_to_container loot into the body.

item cell_table {
  name        "Wooden Table"
  description "A rickety table with one wobbly leg."
  examine     "The surface is scarred with knife marks. A small drawer is built into the front."
  in          cell
  takeable    false
  container   true
  category    "furniture"
  room_desc   "A rickety wooden table stands against the wall."
  open_msg    "The drawer slides open with a dry scrape."
  search_msg  "You pull open the drawer and peer inside."
}

item silver_key {
  name        "Silver Key"
  description "A small silver key, cool to the touch."
  examine     "Its head is stamped with a portcullis sigil."
  in          cell_table
  takeable    true
  home        cell
  take_msg    "You pocket the silver key."
  drop_msg    "You set the silver key down."
  room_desc   "A glint of silver catches your eye inside the drawer."
  drop_desc   "A silver key lies on the ground."
}

item oil_lantern {
  name        "Oil Lantern"
  description "A battered brass lantern with a wick."
  examine     "The oil reservoir is half full. It should burn for a while."
  in          supply_closet
  takeable    true
  toggle      true
  toggle_state "off"
  on_msg      "The flame catches and steadies, casting warm light."
  off_msg     "You snuff the flame. Darkness returns."
  tags        ["light_source"]
  take_msg    "You lift the lantern by its wire handle."
  room_desc   "A brass lantern sits on the shelf."
}

item healing_moss {
  name        "Healing Moss"
  description "Soft green moss with a sharp, clean smell."
  examine     "It clings to the damp stone. Prisoners used it to treat wounds."
  in          supply_closet
  takeable    true
  quantity    3
  max_quantity 3
  quantity_unit "clumps"
  depleted_msg "You have no moss left."
  quantity_desc "You have {quantity} {unit} of moss remaining."
  take_msg    "You scrape the moss off the stone."
  room_desc   "Green moss grows on the damp stones."
}

item rusty_lever {
  name        "Rusty Lever"
  description "A heavy iron lever mounted to the wall."
  examine     "Chains run from it up through a slot in the ceiling. It looks connected to something mechanical above."
  in          supply_closet
  takeable    false
  room_desc   "A rusty lever juts from the wall."
}

item iron_chest {
  name        "Iron Chest"
  description "A heavy chest bound in riveted iron bands."
  examine     "The lock is old but sturdy. It takes a small key."
  in          vault
  takeable    false
  container   true
  locked      true
  key         brass_key
  category    "furniture"
  room_desc   "A heavy iron chest sits against the far wall."
  lock_msg    "The chest is locked. You need a key."
  open_msg    "The lid groans open, releasing the smell of old leather."
  search_msg  "You rummage through the chest."
}

item brass_key {
  name        "Brass Key"
  description "A small brass key on a frayed cord."
  examine     "Stamped with the letters V.K. on the bow."
  in          cellar
  takeable    true
  visible     false
  take_msg    "You pick up the brass key and loop the cord around your wrist."
  room_desc   "A small brass key lies on the floor."
}

item escape_map {
  name        "Escape Map"
  description "A hand-drawn map on brittle parchment."
  examine     "It shows the dungeon layout. Someone marked a vault beneath the corridor with a star."
  read_text   "The map reads: The vault key is in the dark. Bring light."
  in          iron_chest
  takeable    true
  take_msg    "You roll up the map and tuck it into your belt."
}

item guard_stool {
  name        "Guard's Stool"
  description "A worn wooden stool."
  examine     "Initials carved into the seat: J.R."
  in          gate_room
  takeable    false
  category    "furniture"
  room_desc   "A rickety stool sits beside the gate."
}

item rusty_pipe {
  name        "Rusty Pipe"
  description "A heavy iron pipe."
  examine     "Solid and weighty. Could do some damage."
  in          supply_closet
  takeable    true
  tags        ["weapon"]
  take_msg    "You heft the pipe. It feels reassuringly solid."
  room_desc   "A rusty iron pipe leans against the wall."
}

# -- NPCs -- Use category for the interaction matrix. Nest dialogue with talk blocks.

npc guard {
  name        "The Guard"
  description "A heavyset man in dented armor."
  examine     "His eyes are bloodshot and his breath smells of cheap ale. He grips a short sword loosely."
  in          gate_room
  dialogue    "He barely looks up."
  category    "character"
  blocking    gate_room -> courtyard north
  unblock     guard_bribed

  talk root {
    "Another rat from the cells. Gate's locked. Go back to your hole."
    option "I have something for you." -> bribe {
      require_item silver_key
    }
    option "What's beyond the gate?" -> gate_info
    option "I'll find another way."
  }

  talk gate_info {
    "He snorts. 'Courtyard. Sunlight. Freedom. None of which concerns you.'"
    option "I'll be back." -> root
    option "Forget it."
  }

  talk bribe {
    "His eyes fix on the silver key. He snatches it and pockets it. Fine. Go. I never saw you."
    sets [guard_bribed]
  }
}

# -- Flags -- Single-line declarations, all start false.

flag door_raised "The portcullis has been raised"
flag guard_bribed "The guard accepted a bribe"
flag escaped_dungeon "The player escaped"
flag lever_pulled "The supply closet lever has been pulled"
flag vault_unlocked "The vault door has been unlocked"
flag found_brass_key "Found the brass key in the dark cellar"
flag lantern_lit "The lantern has been lit at least once"

# -- Locks -- Reference exits by from -> to direction.

lock portcullis_lock {
  exit     gate_room -> courtyard north
  type     "flag"
  flags    [door_raised]
  locked   "The iron portcullis is lowered. Its bars are too heavy to lift by hand."
  unlocked "With a grinding shriek, the portcullis rises into the ceiling."
}

lock vault_door_lock {
  exit     cellar -> vault north
  type     "flag"
  flags    [vault_unlocked]
  locked   "A heavy door blocks the passage. It is sealed shut."
  unlocked "The vault door grinds open on rusted hinges."
}

# -- Puzzles -- Multi-step, with hints.

puzzle lever_puzzle {
  name        "Raise the Portcullis"
  description "The portcullis blocks the exit. There must be a mechanism somewhere."
  in          gate_room
  score       15
  steps       ["Find the supply closet", "Pull the lever"]
  hint        "There must be a mechanism somewhere that controls the gate."
}

puzzle vault_puzzle {
  name        "The Hidden Vault"
  description "Find what is hidden below the dungeon."
  in          cellar
  score       20
  steps       ["Bring a light source to the dark cellar", "Find the brass key", "Open the iron chest"]
  hint        "You need light to see in the dark."
}

# -- Quests -- main: or side: prefix. Inline objectives with -> completion_flag.

quest main:escape {
  name        "Escape the Dungeon"
  description "Find a way past the locked portcullis and the guard to reach the courtyard."
  completion  escaped_dungeon
  score       0

  objective "Raise the portcullis" -> door_raised
  objective "Get past the guard" -> guard_bribed
  objective "Reach the courtyard" -> escaped_dungeon
}

quest side:vault_secret {
  name        "The Vault Below"
  description "Explore the dark cellar and discover the hidden vault."
  completion  vault_unlocked
  discovery   found_brass_key
  score       20

  objective "Find a light source" -> lantern_lit
  objective "Find the brass key" -> found_brass_key
  objective "Open the vault" -> vault_unlocked
}

# -- Commands --
# The engine handles these verbs automatically -- DO NOT author on blocks for:
#   go, take, drop, examine, look, read, open, close, unlock, search,
#   use, use X on Y, give X to NPC, show X to NPC, put X in Y,
#   turn on/off, talk to, eat, drink
# The engine also handles: dark room blocking (need light_source to act),
# dead NPCs (auto-spawn a searchable "{Name}'s Body" container on death),
# and requires (use batteries on flashlight auto-works when requires is set).
# ONLY author on blocks for CUSTOM verbs the engine doesn't know.
#
# Available effects for on/when blocks (use ONLY these, do not invent new ones):
#   set_flag(id)              -- set a flag to true
#   set_flag(id, false)       -- clear a flag
#   unlock(lock_id)           -- unlock a lock
#   remove_item(id)           -- destroy an item
#   spawn_item(id, location)  -- place an item (_inventory, room_id)
#   move_item(id, from, to)   -- move item between locations
#   move_player(room_id)      -- teleport player
#   change_health(N)          -- heal (+) or damage (-) player
#   add_score(N)              -- award points
#   reveal_exit(exit_id)      -- unhide a hidden exit
#   solve_puzzle(id)          -- mark puzzle solved
#   discover_quest(id)        -- activate a quest
#   print("msg")              -- display text
#   open_container(id)        -- open a container
#   move_item_to_container(item, container) -- put item in container
#   take_item_from_container(item)          -- remove from container
#   consume_quantity(item, N) -- use up consumable charges
#   restore_quantity(item, N) -- refill charges
#   set_toggle_state(item, state)           -- change toggle state
#   move_npc(npc_id, room_id) -- relocate an NPC
#
# Items that should appear later: declare the item WITHOUT an initial location
# and use spawn_item(item_id, room_id) or spawn_item(item_id, _inventory) when
# the reveal happens. Do not invent visibility effects.
#
# Tiered command pattern (highest priority fires first):
# 1. SPECIFIC: room-scoped on blocks with exact preconditions (one-shot story moments)
# 2. TAG-BASED: interaction responses match item tags to target categories automatically
# 3. GLOBAL FALLBACK: an on block with no room scope catches everything else
#
# Always include a global fallback for every custom verb. Fallbacks MUST use
# a success message (not fail) so the player gets feedback. Without a success
# message or effect, the command will fail validation.
#
# Common custom verbs to consider for your game:
#   pull, push, ring, hit, shoot, climb, dig, pray, combine, pour, light, break

# --- SPECIFIC room-scoped commands (tier 1) ---

on "pull {target}" in [supply_closet] {
  require not_flag(lever_pulled)

  effect set_flag(lever_pulled)
  effect set_flag(door_raised)
  effect unlock(portcullis_lock)
  effect solve_puzzle(lever_puzzle)
  effect add_score(15)

  success "You heave the lever down. Chains rattle through the ceiling. Somewhere beyond the corridor, metal grinds against stone. The portcullis is rising."
  fail    "The lever is already in the down position."
  once
}

on "hit {target}" in [gate_room] {
  require has_item(rusty_pipe)
  require npc_in_room(guard, _current)
  require not_flag(guard_bribed)

  effect set_flag(guard_bribed)
  effect add_score(10)

  success "You crack the guard across the back of the head with the pipe. He slumps to the floor."
  fail    "There's no one to hit here."
  once
}

# --- GLOBAL FALLBACK commands (tier 3) ---
# These catch every use of the verb that wasn't handled by a specific on block
# or a tag-based interaction response. Without these, the player sees
# "I don't understand that" -- always provide a fallback for custom verbs.

on "pull {target}" {
  success "There's nothing here you can pull."
}

on "hit {target}" {
  success "You don't have anything to hit with."
}

# -- Triggers -- when event_type(arg) blocks. Same require/effect syntax.
# ONLY these 5 event types exist (do not invent new ones):
#   room_enter(room_id)    -- player enters a room
#   flag_set(flag_id)      -- a flag becomes true
#   item_taken(item_id)    -- player takes an item
#   item_dropped(item_id)  -- player drops an item
#   dialogue_node(node_id) -- a dialogue node is visited
#
# Quest declarations may use main:/side: prefixes (quest side:lost_recipe { ... })
# but effect references use the NORMALIZED quest id only:
#   effect discover_quest(lost_recipe)     -- correct
#   effect discover_quest(side:lost_recipe) -- WRONG, will fail
#
# Nested NPC talk blocks compile to dialogue node ids: {npc_id}_{label}.
# When using dialogue_node triggers, reference the compiled id:
#   when dialogue_node(cook_marta_secret)  -- correct (npc_id = cook_marta, label = secret)
#   when dialogue_node(secret)             -- WRONG, bare label will fail

when room_enter(courtyard) {
  require has_flag(guard_bribed)
  require has_flag(door_raised)

  effect set_flag(escaped_dungeon)
  effect add_score(15)

  message "You climb the stairs into blinding sunlight. Free."
  once
}

when room_enter(cellar) {
  require not_flag(found_brass_key)

  message "The darkness presses in around you. If only you had a light source."
  once
}

# -- Interaction responses -- Tag-based "use X on Y" rules.
# When a player types "use X on Y", the engine checks X's tags against Y's
# category and fires the first matching interaction response.
# ONE rule covers ALL items with that tag on ALL targets with that category.
#
# Tags and categories are OPEN-ENDED. Invent whatever you want!
# Items can have multiple tags: tags ["weapon", "metal", "sharp"]
# NPCs and items must have a category set for interactions to work.
#
# Effects for interactions (target-aware + standard):
#   kill_target()       -- kill the target NPC, spawn lootable body
#   damage_target(N)    -- deal N damage to target NPC
#   destroy_target()    -- break target container, scatter contents
#   open_target()       -- open target container
#   Plus all standard effects: add_score(N), set_flag(id), print("msg"), etc.
#
# Be creative -- define fun emergent combos the player can discover:
#   "weapon" on "character"      -> kill NPCs with kill_target()
#   "weapon" on "furniture"      -> smash it with destroy_target()
#   "light_source" on "character" -> blind or distract them
#   "food" on "character"        -> offer food, they react
#   "evidence" on "character"    -> confront or accuse
#   "tool" on "furniture"        -> pry open, disassemble
#   "disguise" on "character"    -> fool NPCs
#   "pet_accessory" on "character" -> bewildered reactions
#   "holy_water" on "undead"     -> destroy undead
# Invent tags that fit YOUR game's world. The system is completely open.

interaction weapon_on_character {
  tag      "weapon"
  target   "character"
  response "You crack {target} over the head with the {item}. They crumple to the ground."
  effect   kill_target()
  effect   add_score(10)
}

interaction weapon_on_furniture {
  tag      "weapon"
  target   "furniture"
  response "You smash the {item} into the {target}. It splinters apart and its contents scatter across the floor."
  effect   destroy_target()
}

interaction light_source_on_character {
  tag      "light_source"
  target   "character"
  response "You shine the {item} in {target}'s face. They stumble back, blinded."
}

--- END EXAMPLE ---

{quality_requirements}

Constraints:
- Use ONLY keywords shown in the example. Do not invent new block types.
- Exit directions must be: north, south, east, west, up, down.
- No commentary outside ZorkScript.
- Every flag referenced in require/effect/when must have a flag declaration.
- Every ID must be snake_case and unique within its entity type.
- Preserve the concept's scope. Do not reduce it to a skeleton or expand beyond request.
- All strings in double quotes.
- Use plain ASCII punctuation. Avoid em dashes, curly quotes, and smart punctuation.
- Most fields are optional. Only include fields that add value. Keep declarations lean.
  Defaults: takeable true, visible true, dark false, start false, open false, locked false.
- Do NOT author on blocks for built-in verbs: go, take, drop, examine, read, open,
  close, unlock, search, use, give, show, put, turn, talk, eat, drink.
  The engine handles these automatically through items, containers, locks, and toggles.
  ONLY use on blocks for custom verbs: pull, push, ring, climb, dig, accuse, combine, etc.
- Every custom verb MUST have a global fallback on block with no room scope.
- Trigger event types MUST be one of: room_enter, flag_set, item_taken, item_dropped, dialogue_node.
  Do NOT invent event types like item_read, npc_talk, etc. Use flag_set triggers instead.
  Players will try verbs in rooms the author didn't anticipate.

Concept:
{concept}
"""

_REALISM_GUIDANCE: dict[str, list[str]] = {
    "low": [
        "Keep mechanics simple and accessible. Minimal nested item systems.",
        "No multi-step item dependencies (no guns requiring magazines requiring ammo,",
        "no cigarettes requiring a lighter). Items work directly when used.",
        "Prefer single-step puzzles and generous affordances.",
    ],
    "medium": [
        "Keep the world grounded and internally consistent.",
        "Some nested systems are fine when they serve the story (a locked chest",
        "needing a key, a torch needing to be lit). But avoid gratuitous simulation.",
        "Puzzles should have clear cause-and-effect, 1-3 steps.",
    ],
    "high": [
        "Favor realistic simulation. Nested item systems are encouraged: guns need",
        "ammo, devices need batteries or fuel, fire needs a source.",
        "Use containers, toggle states, and quantity tracking for immersion.",
        "Puzzles can be multi-step and require combining knowledge from different areas.",
        "Environmental consequences matter: dark rooms need light, locked things need keys.",
    ],
}

def build_zorkscript_prompt(
    concept: str,
    *,
    realism: str | None = None,
    authoring_fields: dict[str, Any] | None = None,
) -> str:
    """Build a ready-to-send external prompt for ZorkScript-format authoring."""
    concept_text = concept.strip()
    if not concept_text:
        raise ValueError("Import concept must not be empty.")

    fields = authoring_fields or {}
    realism_key = (realism or "medium").strip().lower()

    # Build quality requirements — specific to this generation's settings.
    quality = _build_quality_requirements(realism_key, fields)

    # Build realism guidance — direct, no alternatives listed.
    guidance = _REALISM_GUIDANCE.get(realism_key, [])
    realism_lines = [f"Realism: {realism_key}"]
    realism_lines.extend(f"- {line}" for line in guidance)
    realism_block = "\n".join(realism_lines)

    # Build authoring requirements (locations, characters, items, story, etc.)
    authoring_block = _build_authoring_requirements(fields)

    # Assemble: template with quality filled in, then extras before concept.
    template = ZORKSCRIPT_AUTHORING_TEMPLATE.replace(
        "{quality_requirements}", quality
    )

    injected = f"\n{realism_block}\n\n{authoring_block}\n"
    template = template.replace(
        "\nConcept:\n{concept}",
        f"{injected}\nConcept:\n{concept_text}",
    )

    return template.strip() + "\n"


_SCALE_REQUIREMENTS: dict[str, dict[str, str]] = {
    "small": {
        "rooms": "3-5 rooms in 1 region. Every room dense with interactables.",
        "items": "At least 6 items. Every room has 2+ examinable objects.",
        "npcs": "1-2 NPCs with dialogue.",
        "puzzles": "1-2 puzzles.",
        "quests": "1 main quest with 2-3 objectives.",
    },
    "medium": {
        "rooms": "6-12 rooms across 1-2 regions.",
        "items": "At least 10 items. Every major room has 2+ examinable objects.",
        "npcs": "2-4 NPCs with dialogue trees.",
        "puzzles": "2-3 puzzles with multi-step solutions.",
        "quests": "1 main quest with 3+ objectives. Side quests encouraged.",
    },
    "large": {
        "rooms": "13-25 rooms across 2-4 regions.",
        "items": "At least 20 items. Every room has 2+ examinable objects.",
        "npcs": "4+ NPCs with branching dialogue trees.",
        "puzzles": "3-5 puzzles with multi-step solutions.",
        "quests": "1 main quest with 4+ objectives. 1-2 side quests.",
    },
}


def _build_quality_requirements(realism: str, fields: dict[str, Any]) -> str:
    """Build the Quality requirements block, tailored to this generation."""
    scale = str(fields.get("scale") or "").strip().lower()
    targets = _SCALE_REQUIREMENTS.get(scale, _SCALE_REQUIREMENTS["medium"])

    lines = ["Quality requirements:"]
    lines.append(f"- {targets['rooms']}")
    lines.append(f"- {targets['items']}")

    # Furniture / containers — always, but adjust depth by realism.
    lines.append("- Use furniture (desks, tables, shelves) as searchable containers.")
    if realism == "high":
        lines.append("- Use nested containers and item dependencies where it adds depth.")

    # Toggles / dark rooms
    lines.append("- Include at least one toggle item (torch, lamp, switch) with on/off.")
    if realism != "low":
        lines.append("- Include dark rooms that require a light source.")

    # Rich item feedback
    lines.append("- Use take_msg, drop_msg, room_desc, drop_desc, examine for rich feedback. Never generic.")
    lines.append("- take_msg/drop_msg must work in ANY room (not context-specific).")
    lines.append("  Use home + room_desc for the item's native room, drop_desc for away.")

    # Consumables
    if realism != "low":
        lines.append("- Include consumable items (food, potions) with eat/drink/use commands.")

    # NPCs — use explicit character list count if provided, else scale default.
    characters = fields.get("characters") or []
    if characters:
        lines.append(f"- Exactly {len(characters)} NPCs with dialogue (one per requested character).")
    else:
        lines.append(f"- {targets['npcs']}")
    lines.append("- Every named character in the concept MUST exist as a real NPC.")
    lines.append("  If the concept says '8 people', create 8 NPCs -- not 2.")

    # Puzzles, quests
    lines.append(f"- {targets['puzzles']}")
    lines.append(f"- {targets['quests']}")

    # Custom verb fallback — always
    lines.append(
        "- Every custom verb (pull, push, ring, hit, shoot, climb, etc.) "
        "MUST have a global fallback on block."
    )

    # Interaction responses — always encouraged, richer at high realism
    lines.append(
        "- Set category on EVERY NPC ('character') and interactable item ('furniture', etc.)."
    )
    lines.append(
        "  Without a category, 'use X on Y' won't fire interaction responses."
    )
    lines.append(
        "- Use interaction responses (tag on category) so 'use X on Y' works dynamically."
    )
    lines.append(
        "  Invent creative tags: weapon, food, evidence, tool, disguise, poison, rope, etc."
    )
    if realism != "low":
        lines.append(
            "  Use kill_target(), destroy_target(), damage_target(N) for real consequences."
        )

    # Prose quality — always
    lines.append("- Room descriptions: 2-4 vivid sentences with sensory detail.")
    lines.append("- Short descriptions: 1 compact sentence.")
    lines.append("- First-visit text: a fresh reaction, not repeated from description.")
    lines.append(
        "- Do NOT mention takeable items directly in base room descriptions if room_desc/drop_desc already cover them."
    )
    lines.append(
        "  Keep movable-item prose in room_desc/drop_desc so the engine does not duplicate it."
    )
    lines.append("- Use each item's exact name in room prose so it highlights in-game.")
    lines.append(
        "- Never include a custom command unless it changes state or prints a visible result on success."
    )
    lines.append("- Starting room offers an obvious first action within 1-2 commands.")
    lines.append("- Win condition must be reachable. No dead ends or softlocks.")

    return "\n".join(lines)


def _build_authoring_requirements(authoring_fields: dict[str, Any]) -> str:
    """Return authoring requirements from wizard inputs. Only includes user-specified fields."""
    lines: list[str] = []

    locations = authoring_fields.get("locations") or []
    if locations:
        lines.append("Include these locations:")
        lines.extend(f"  - {entry}" for entry in locations)

    characters = authoring_fields.get("characters") or []
    if characters:
        lines.append("Include these characters as NPCs:")
        lines.extend(f"  - {entry}" for entry in characters)

    items = authoring_fields.get("items") or []
    if items:
        lines.append("Include these items:")
        lines.extend(f"  - {entry}" for entry in items)

    story = str(authoring_fields.get("story") or "").strip()
    if story:
        lines.append(f"Main quest goal: {story}")

    genre_tags = [str(tag).strip().lower() for tag in authoring_fields.get("genre_tags") or []]
    if genre_tags:
        lines.append(f"Gameplay emphasis: {', '.join(genre_tags)}")

    tone = authoring_fields.get("tone") or []
    if tone:
        tone_text = ", ".join(str(entry).strip() for entry in tone if str(entry).strip())
        if tone_text:
            lines.append(f"Tone: {tone_text}")

    if not lines:
        return ""
    formatted = [
        f"- {entry}" if not entry.startswith("  ") else entry
        for entry in lines
    ]
    return "Authoring requirements:\n" + "\n".join(formatted)


def load_import_source(source: str) -> dict[str, Any]:
    """Load and parse a ZorkScript spec from file, stdin, or inline text."""
    from anyzork.zorkscript import parse_zorkscript

    if source in {"", "-"}:
        raw_text = sys.stdin.read()
    else:
        candidate = Path(source).expanduser()
        raw_text = candidate.read_text(encoding="utf-8") if candidate.exists() else source

    return parse_zorkscript(raw_text)


def default_output_path(spec: dict[str, Any], games_dir: Path) -> Path:
    """Return the default output path for an imported game."""
    title = str(spec.get("game", {}).get("title", "imported_game"))
    return games_dir / f"{slugify_title(title)}.zork"


def slugify_title(title: str) -> str:
    """Return a filesystem-friendly slug for imported game titles."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug or "game"


def compile_import_spec(
    spec: dict[str, Any],
    output_path: Path,
) -> tuple[Path, list[str]]:
    """Compile a public import spec into a validated ``.zork`` file."""
    spec = _normalize_import_spec(deepcopy(spec))
    _validate_exit_directions(spec)
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    Path(f"{output_path}-wal").unlink(missing_ok=True)
    Path(f"{output_path}-shm").unlink(missing_ok=True)

    db = GameDB(output_path)
    try:
        _initialize_metadata(db, spec)
        _insert_rooms(db, spec)
        _insert_exits(db, spec)
        _insert_items(db, spec)
        _insert_npcs(db, spec)
        _insert_dialogue(db, spec)
        _insert_puzzles(db, spec)
        _insert_locks(db, spec)
        _insert_flags(db, spec)
        _insert_commands(db, spec)
        _insert_quests(db, spec)
        _insert_interaction_responses(db, spec)
        _insert_triggers(db, spec)
        _initialize_player(db, spec)
        warnings = _validate_imported_game(db)
        return output_path, warnings
    except Exception:
        with contextlib.suppress(Exception):
            db.close()
        output_path.unlink(missing_ok=True)
        Path(f"{output_path}-wal").unlink(missing_ok=True)
        Path(f"{output_path}-shm").unlink(missing_ok=True)
        raise
    finally:
        if output_path.exists():
            db.close()


def _initialize_metadata(db: GameDB, spec: dict[str, Any]) -> None:
    game = spec["game"]
    rooms = spec.get("rooms", [])
    regions = {room.get("region", "world") for room in rooms}
    db.initialize(
        game_name=str(game.get("title", "Imported AnyZork Game")),
        author=str(game.get("author", "Imported")),
        prompt=str(game.get("author_prompt") or game.get("prompt") or "Imported AnyZork spec"),
        prompt_system_version=current_prompt_system_version(),
        seed=str(game["seed"]) if game.get("seed") is not None else None,
        intro_text=str(game.get("intro_text", "")),
        win_text=str(game.get("win_text", "")),
        lose_text=_optional_str(game.get("lose_text")),
        win_conditions=json.dumps(game.get("win_conditions", [])),
        lose_conditions=(
            json.dumps(game["lose_conditions"])
            if game.get("lose_conditions") is not None
            else None
        ),
        max_score=int(game.get("max_score", 0)),
        region_count=len(regions),
        room_count=len(rooms),
        is_template=True,
    )
    if game.get("realism"):
        db.set_meta("realism", str(game["realism"]))


def _normalize_import_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Normalize user-authored import JSON into the compiler's internal shape."""
    import_format = spec.get("format")
    if import_format is not None and import_format != IMPORT_SPEC_FORMAT:
        raise ImportSpecError(
            f"Unsupported import format {import_format!r}; expected {IMPORT_SPEC_FORMAT!r}."
        )

    spec["format"] = IMPORT_SPEC_FORMAT
    spec.setdefault("items", [])
    spec.setdefault("npcs", [])
    spec.setdefault("dialogue_nodes", [])
    spec.setdefault("dialogue_options", [])
    spec.setdefault("locks", [])
    spec.setdefault("puzzles", [])
    spec.setdefault("flags", [])
    spec.setdefault("interactions", [])
    spec.setdefault("commands", [])
    spec.setdefault("quests", [])
    spec.setdefault("interaction_responses", [])
    spec.setdefault("triggers", [])

    _normalize_items(spec)
    _normalize_npcs(spec)
    _normalize_dialogue(spec)
    _normalize_locks(spec)
    _normalize_puzzles(spec)
    _normalize_flags(spec)
    _normalize_public_interactions(spec)
    _normalize_commands(spec)
    _normalize_interaction_responses(spec)
    _normalize_triggers(spec)
    _normalize_quests(spec)
    return spec


def _normalize_items(spec: dict[str, Any]) -> None:
    for item in spec.get("items", []):
        if item.get("room_id") is None:
            location_type = str(item.get("location_type", "")).strip().lower()
            location_id = _optional_str(item.get("location_id"))
            room_id = _optional_str(item.get("location_room_id"))
            if location_type == "room" and location_id and room_id is None:
                room_id = location_id
            item["room_id"] = room_id
        if "examine_description" not in item and "examine_text" in item:
            item["examine_description"] = item["examine_text"]
        if "is_takeable" not in item and "is_portable" in item:
            item["is_takeable"] = item.get("is_portable")
        if "is_visible" not in item:
            item["is_visible"] = not bool(item.get("is_hidden", False))


def _normalize_npcs(spec: dict[str, Any]) -> None:
    for npc in spec.get("npcs", []):
        if npc.get("room_id") is None:
            npc["room_id"] = _optional_str(npc.get("location_room_id"))
        if "examine_description" not in npc and "examine_text" in npc:
            npc["examine_description"] = npc["examine_text"]
        if "is_alive" not in npc:
            npc["is_alive"] = True


def _normalize_dialogue(spec: dict[str, Any]) -> None:
    for node in spec.get("dialogue_nodes", []):
        if "content" not in node and "text" in node:
            node["content"] = node.get("text")

    for option in spec.get("dialogue_options", []):
        if "node_id" not in option and "from_node_id" in option:
            option["node_id"] = option.get("from_node_id")


def _normalize_locks(spec: dict[str, Any]) -> None:
    for lock in spec.get("locks", []):
        if lock.get("target_exit_id") is None:
            lock["target_exit_id"] = _optional_str(lock.get("exit_id"))
        if lock.get("lock_type") is None:
            if lock.get("required_flags"):
                lock["lock_type"] = "flag"
            elif lock.get("key_item_id"):
                lock["lock_type"] = "key"
            else:
                lock["lock_type"] = "flag"
        if "locked_message" not in lock and "locked_text" in lock:
            lock["locked_message"] = lock.get("locked_text")


def _normalize_puzzles(spec: dict[str, Any]) -> None:
    commands = spec.get("commands", [])
    interactions = spec.get("interactions", [])
    items_by_id = {item["id"]: item for item in spec.get("items", []) if item.get("id")}
    room_ids = {room["id"] for room in spec.get("rooms", []) if room.get("id")}

    # Determine a fallback room: the start room or the first room.
    fallback_room_id: str | None = None
    player = spec.get("player", {})
    if player.get("start_room_id"):
        fallback_room_id = str(player["start_room_id"])
    if not fallback_room_id:
        for room in spec.get("rooms", []):
            if room.get("is_start"):
                fallback_room_id = str(room["id"])
                break
    if not fallback_room_id and spec.get("rooms"):
        fallback_room_id = str(spec["rooms"][0]["id"])

    for puzzle in spec.get("puzzles", []):
        if puzzle.get("room_id") is None:
            inferred_room_id = _infer_puzzle_room_id(
                puzzle, commands, interactions, items_by_id, room_ids,
            )
            puzzle["room_id"] = inferred_room_id or fallback_room_id


def _infer_puzzle_room_id(
    puzzle: dict[str, Any],
    commands: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
    items_by_id: dict[str, dict[str, Any]],
    room_ids: set[str],
) -> str | None:
    puzzle_id = puzzle.get("id")

    for item_id in puzzle.get("required_items", []):
        room_id = _optional_str(items_by_id.get(item_id, {}).get("room_id"))
        if room_id:
            return room_id

    # Check interactions that solve this puzzle via solve_puzzle_ids.
    if puzzle_id:
        for interaction in interactions:
            solve_ids = interaction.get("solve_puzzle_ids") or []
            if puzzle_id in solve_ids:
                ctx = interaction.get("context_room_ids") or []
                if ctx:
                    return str(ctx[0])
                room_id = _optional_str(interaction.get("room_id"))
                if room_id:
                    return room_id

    set_flags = {str(flag_id) for flag_id in puzzle.get("set_flags", [])}
    required_flags = {str(flag_id) for flag_id in puzzle.get("required_flags", [])}
    for command in commands:
        context_room_ids = command.get("context_room_ids") or []
        if not context_room_ids:
            continue
        command_effects = command.get("effects") or []
        if any(
            effect.get("type") == "set_flag"
            and str(effect.get("flag_id")) in set_flags
            for effect in command_effects
        ):
            return str(context_room_ids[0])
        command_preconditions = command.get("preconditions") or []
        if any(
            pre.get("type") in {"has_flag", "flag_true"}
            and str(pre.get("flag_id") or pre.get("flag")) in required_flags
            for pre in command_preconditions
        ):
            return str(context_room_ids[0])

    for step in puzzle.get("solution_steps", []):
        if not isinstance(step, str):
            continue
        words = step.strip().split()
        if len(words) >= 3 and words[0].lower() == "go" and words[1].lower() == "to":
            candidate = slugify_title(" ".join(words[2:]))
            if candidate in room_ids:
                return candidate

    return None


def _normalize_flags(spec: dict[str, Any]) -> None:
    for flag in spec.get("flags", []):
        if "value" not in flag and "default_value" in flag:
            flag["value"] = flag.get("default_value")
        if "value" not in flag and "default" in flag:
            flag["value"] = flag.get("default")
        if "description" not in flag and "name" in flag:
            flag["description"] = flag.get("name")
        if "description" not in flag and "label" in flag:
            flag["description"] = flag.get("label")


def _normalize_public_interactions(spec: dict[str, Any]) -> None:
    commands = spec.setdefault("commands", [])
    interactions = spec.get("interactions", [])
    if not interactions:
        return

    item_names = {
        item["id"]: item["name"]
        for item in spec.get("items", [])
        if item.get("id") and item.get("name")
    }
    npc_names = {
        npc["id"]: npc["name"]
        for npc in spec.get("npcs", [])
        if npc.get("id") and npc.get("name")
    }
    npc_rooms = {
        npc["id"]: npc.get("room_id")
        for npc in spec.get("npcs", [])
        if npc.get("id")
    }
    item_rooms = {
        item["id"]: item.get("room_id")
        for item in spec.get("items", [])
        if item.get("id")
    }

    for interaction in interactions:
        interaction_type = str(interaction.get("type", "")).strip().lower()
        if interaction_type not in PUBLIC_INTERACTION_TYPES:
            allowed_types = ", ".join(PUBLIC_INTERACTION_TYPES)
            raise ImportSpecError(
                "Unsupported interaction type "
                f"{interaction.get('type')!r}; expected one of {allowed_types}."
            )

        context_room_ids = _interaction_context_room_ids(
            interaction,
            item_rooms=item_rooms,
            npc_rooms=npc_rooms,
        )
        command_text = _interaction_command_text(
            interaction,
            item_names=item_names,
            npc_names=npc_names,
        )
        verb = command_text.split(None, 1)[0].lower()

        preconditions: list[dict[str, Any]] = []
        preconditions.extend(
            {"type": "has_flag", "flag": flag_id}
            for flag_id in interaction.get("required_flags", [])
        )
        preconditions.extend(
            {"type": "not_flag", "flag": flag_id}
            for flag_id in interaction.get("excluded_flags", [])
        )
        preconditions.extend(
            {"type": "has_item", "item": item_id}
            for item_id in interaction.get("required_items", [])
        )

        item_id = _optional_str(interaction.get("item_id"))
        npc_id = _optional_str(interaction.get("npc_id"))
        container_id = _optional_str(interaction.get("container_id"))

        if interaction_type == "read_item" and item_id:
            preconditions.append({"type": "item_accessible", "item": item_id})
        elif interaction_type in {"show_item_to_npc", "give_item_to_npc"}:
            if item_id:
                preconditions.append({"type": "has_item", "item": item_id})
            if npc_id:
                preconditions.append({"type": "npc_in_room", "npc": npc_id, "room": "_current"})
        elif interaction_type == "search_container" and container_id:
            preconditions.append({"type": "item_accessible", "item": container_id})
        elif interaction_type == "travel_action" and interaction.get("move_player_room_id") is None:
            raise ImportSpecError(
                f"Interaction {interaction.get('id')!r} must define move_player_room_id."
            )

        effects: list[dict[str, Any]] = []
        effects.extend(
            {"type": "set_flag", "flag": flag_id, "value": True}
            for flag_id in interaction.get("set_flags", [])
        )
        effects.extend(
            {"type": "spawn_item", "item": item_id, "location": "_inventory"}
            for item_id in interaction.get("give_items", [])
        )
        effects.extend(
            {"type": "unlock", "lock": lock_id}
            for lock_id in interaction.get("unlock_lock_ids", [])
        )
        effects.extend(
            {"type": "reveal_exit", "exit": exit_id}
            for exit_id in interaction.get("reveal_exit_ids", [])
        )
        effects.extend(
            {"type": "discover_quest", "quest": quest_id}
            for quest_id in interaction.get("discover_quest_ids", [])
        )
        effects.extend(
            {"type": "solve_puzzle", "puzzle": puzzle_id}
            for puzzle_id in interaction.get("solve_puzzle_ids", [])
        )
        if interaction.get("move_player_room_id"):
            effects.append(
                {"type": "move_player", "room": interaction["move_player_room_id"]}
            )
        score_value = interaction.get("score_value")
        if score_value:
            effects.append({"type": "add_score", "points": int(score_value)})
        consume_item = bool(interaction.get("consume_item", True))
        if item_id and interaction_type == "give_item_to_npc" and consume_item:
            effects.append({"type": "remove_item", "item": item_id})

        commands.append(
            {
                "id": interaction["id"],
                "verb": verb,
                "pattern": command_text,
                "preconditions": preconditions,
                "effects": effects,
                "success_message": str(interaction.get("success_message") or ""),
                "failure_message": _default_interaction_failure(interaction_type, interaction),
                "context_room_ids": context_room_ids,
                "priority": int(interaction.get("priority", 10)),
                "one_shot": bool(interaction.get("one_shot", False)),
            }
        )


def _interaction_context_room_ids(
    interaction: dict[str, Any],
    *,
    item_rooms: dict[str, Any],
    npc_rooms: dict[str, Any],
) -> list[str]:
    context_room_ids = interaction.get("context_room_ids") or []
    if context_room_ids:
        return [str(room_id) for room_id in context_room_ids if room_id]

    room_id = _optional_str(interaction.get("room_id"))
    if room_id:
        return [room_id]

    npc_id = _optional_str(interaction.get("npc_id"))
    if npc_id and npc_rooms.get(npc_id):
        return [str(npc_rooms[npc_id])]

    item_id = _optional_str(interaction.get("item_id"))
    if item_id and item_rooms.get(item_id):
        return [str(item_rooms[item_id])]

    return []


def _interaction_command_text(
    interaction: dict[str, Any],
    *,
    item_names: dict[str, str],
    npc_names: dict[str, str],
) -> str:
    command = str(interaction.get("command") or "").strip().lower()
    if command:
        return command

    interaction_type = str(interaction.get("type", "")).strip().lower()
    item_id = _optional_str(interaction.get("item_id"))
    npc_id = _optional_str(interaction.get("npc_id"))
    container_id = _optional_str(interaction.get("container_id"))

    item_text = str(item_names.get(item_id, item_id or "item")).strip().lower()
    npc_text = str(npc_names.get(npc_id, npc_id or "npc")).strip().lower()
    container_text = str(item_names.get(container_id, container_id or "container")).strip().lower()

    if interaction_type == "read_item":
        return f"read {item_text}"
    if interaction_type == "show_item_to_npc":
        return f"show {item_text} to {npc_text}"
    if interaction_type == "give_item_to_npc":
        return f"give {item_text} to {npc_text}"
    if interaction_type == "search_container":
        return f"search {container_text}"
    if interaction_type == "search_room":
        return "search room"
    if interaction_type == "travel_action":
        return "travel"
    raise ImportSpecError(f"Interaction {interaction.get('id')!r} is missing a command.")


def _default_interaction_failure(
    interaction_type: str,
    interaction: dict[str, Any],
) -> str:
    message = _optional_str(interaction.get("failure_message"))
    if message:
        return message

    return {
        "read_item": "You have nothing like that to read.",
        "show_item_to_npc": "That doesn't seem useful right now.",
        "give_item_to_npc": "You can't hand that over right now.",
        "search_room": "You don't find anything new.",
        "search_container": "You don't find anything else inside.",
        "travel_action": "You can't go that way yet.",
    }.get(interaction_type, "Nothing happens.")


def _normalize_commands(spec: dict[str, Any]) -> None:
    item_names = {
        item["id"]: item["name"]
        for item in spec.get("items", [])
        if item.get("id") and item.get("name")
    }
    room_names = {
        room["id"]: room["name"]
        for room in spec.get("rooms", [])
        if room.get("id") and room.get("name")
    }
    item_rooms = {
        item["id"]: item.get("room_id")
        for item in spec.get("items", [])
        if item.get("id")
    }

    for cmd in spec.get("commands", []):
        if "pattern" not in cmd:
            cmd["pattern"] = _infer_command_pattern(cmd, item_names, room_names)
        if "success_message" not in cmd:
            cmd["success_message"] = str(
                cmd.get("response_text") or cmd.get("description") or ""
            )
        cmd.setdefault("failure_message", "Nothing happens.")
        cmd["preconditions"] = [
            _normalize_condition(pre) for pre in cmd.get("preconditions", [])
        ]
        cmd["effects"] = [
            _normalize_effect(effect, item_rooms=item_rooms)
            for effect in cmd.get("effects", [])
        ]


def _infer_command_pattern(
    cmd: dict[str, Any],
    item_names: dict[str, str],
    room_names: dict[str, str],
) -> str:
    if cmd.get("name"):
        return str(cmd["name"]).strip().lower()

    verb = str(cmd.get("verb", "")).strip().lower()
    if not verb:
        return "command"

    target_id = (
        _optional_str(cmd.get("target_id"))
        or _optional_str(cmd.get("target_item_id"))
        or _optional_str(cmd.get("target_npc_id"))
        or _optional_str(cmd.get("noun"))
    )
    if not target_id:
        return verb

    target_name = item_names.get(target_id) or room_names.get(target_id) or target_id
    return f"{verb} {str(target_name).strip().lower()}"


def _normalize_condition(condition: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(condition)
    cond_type = str(normalized.get("type", "")).strip()

    if not cond_type and "flag" in normalized and "value" in normalized:
        return {
            "type": "has_flag" if bool(normalized.get("value")) else "not_flag",
            "flag": _optional_str(normalized.get("flag")),
        }

    if cond_type == "same_room":
        npc_id = _optional_str(normalized.get("npc_id") or normalized.get("npc"))
        return {"type": "npc_in_room", "npc": npc_id, "room": "_current"}

    if cond_type == "flag_set":
        flag_id = _optional_str(normalized.get("flag_id") or normalized.get("flag"))
        return {"type": "has_flag", "flag": flag_id}

    if cond_type == "flag_not_set":
        flag_id = _optional_str(normalized.get("flag_id") or normalized.get("flag"))
        return {"type": "not_flag", "flag": flag_id}

    if cond_type == "flag_true":
        flag_id = _optional_str(normalized.get("flag_id") or normalized.get("flag"))
        return {"type": "has_flag", "flag": flag_id}

    if cond_type == "flag_false":
        flag_id = _optional_str(normalized.get("flag_id") or normalized.get("flag"))
        return {"type": "not_flag", "flag": flag_id}

    if cond_type == "has_item" and "item" not in normalized and "item_id" in normalized:
        normalized["item"] = normalized.get("item_id")

    if "npc" not in normalized and "npc_id" in normalized:
        normalized["npc"] = normalized.get("npc_id")
    if "flag" not in normalized and "flag_id" in normalized:
        normalized["flag"] = normalized.get("flag_id")

    return normalized


def _normalize_effect(
    effect: dict[str, Any],
    *,
    item_rooms: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(effect)
    effect_type = str(normalized.get("type", "")).strip()
    item_rooms = item_rooms or {}

    if not effect_type:
        if "set_flag" in normalized:
            return {"type": "set_flag", "flag": normalized.get("set_flag")}
        if "show_item" in normalized:
            item_id = normalized.get("show_item")
            location = _optional_str(item_rooms.get(str(item_id))) or "_current"
            return {"type": "spawn_item", "item": item_id, "location": location}
        if "give_item" in normalized:
            return {
                "type": "spawn_item",
                "item": normalized.get("give_item"),
                "location": "_inventory",
            }

    if effect_type == "set_flag" and "flag" not in normalized and "flag_id" in normalized:
        normalized["flag"] = normalized.get("flag_id")

    if effect_type == "add_item":
        return {
            "type": "spawn_item",
            "item": normalized.get("item_id"),
            "location": "_inventory",
        }

    if effect_type == "move_player" and "room" not in normalized and "room_id" in normalized:
        normalized["room"] = normalized.get("room_id")

    return normalized


def _normalize_interaction_responses(spec: dict[str, Any]) -> None:
    commands = spec.setdefault("commands", [])
    item_names = {
        item["id"]: item["name"]
        for item in spec.get("items", [])
        if item.get("id") and item.get("name")
    }
    npc_names = {
        npc["id"]: npc["name"]
        for npc in spec.get("npcs", [])
        if npc.get("id") and npc.get("name")
    }

    # Separate real interaction responses (with item_tag) from legacy ones
    # that need conversion to commands.
    real_responses: list[dict[str, Any]] = []
    legacy_responses: list[dict[str, Any]] = []
    for response in spec.get("interaction_responses", []):
        if response.get("item_tag"):
            real_responses.append(response)
        else:
            legacy_responses.append(response)

    # Keep real interaction responses for _insert_interaction_responses.
    spec["interaction_responses"] = real_responses

    for response in legacy_responses:
        if "context_room_ids" not in response and response.get("room_id"):
            response["context_room_ids"] = [response["room_id"]]
        if "target_id" not in response and response.get("item_id"):
            response["target_id"] = response.get("item_id")

        response_type = str(
            response.get("type") or response.get("verb") or response.get("action") or ""
        ).strip().lower()
        if not response_type:
            response_type = "examine"
        target_id = _optional_str(response.get("target_id"))
        target_text = _optional_str(response.get("target"))
        if target_id and target_id in item_names:
            target_text = item_names[target_id]
        elif target_id and target_id in npc_names:
            target_text = npc_names[target_id]
        elif target_text == "room":
            target_text = None

        pattern = response_type or "interact"
        if target_text:
            pattern = f"{pattern} {str(target_text).strip().lower()}"

        preconditions = [
            {"type": "in_room", "room": room_id}
            for room_id in response.get("context_room_ids", [])
        ]
        preconditions.extend(
            {"type": "has_flag", "flag": flag_id} for flag_id in response.get("required_flags", [])
        )
        preconditions.extend(
            {"type": "not_flag", "flag": flag_id} for flag_id in response.get("excluded_flags", [])
        )

        effects = [
            {"type": "set_flag", "flag_id": flag_id}
            for flag_id in response.get("set_flags", [])
        ]
        effects.extend(
            {"type": "spawn_item", "item": item_id, "location": "_inventory"}
            for item_id in response.get("give_items", [])
        )

        commands.append(
            {
                "id": f"imported_{response['id']}",
                "verb": response_type or "interact",
                "pattern": pattern,
                "preconditions": preconditions,
                "effects": effects,
                "success_message": response.get("response_text") or response.get("text", ""),
                "failure_message": "Nothing else stands out.",
                "context_room_ids": response.get("context_room_ids", []),
                "priority": 10,
            }
        )



def _normalize_triggers(spec: dict[str, Any]) -> None:
    item_rooms = {
        item["id"]: item.get("room_id")
        for item in spec.get("items", [])
        if item.get("id")
    }
    for trigger in spec.get("triggers", []):
        if "event_type" not in trigger and "trigger_type" in trigger:
            event = str(trigger.get("trigger_type", "")).strip().lower()
            trigger["event_type"] = {
                "on_enter": "room_enter",
                "on_flag": "flag_set",
            }.get(event, event)
        if "event_type" not in trigger and "event" in trigger:
            event = str(trigger.get("event", "")).strip().lower()
            trigger["event_type"] = {
                "enter_room": "room_enter",
                "room_turn": "room_enter",
                "set_flag": "flag_set",
            }.get(event, event)

        trigger.setdefault("event_data", {})
        if not trigger["event_data"].get("room_id") and trigger.get("room_id"):
            trigger["event_data"]["room_id"] = trigger.get("room_id")
        if (
            trigger["event_type"] == "flag_set"
            and not trigger["event_data"].get("flag")
            and not trigger["event_data"].get("flag_id")
            and trigger.get("flag_id")
        ):
            trigger["event_data"]["flag"] = trigger.get("flag_id")
        if trigger["event_type"] == "room_enter" and not trigger["event_data"].get("room_id"):
            context_room_ids = trigger.get("context_room_ids") or []
            if context_room_ids:
                trigger["event_data"]["room_id"] = context_room_ids[0]
        if (
            trigger["event_type"] == "flag_set"
            and not trigger["event_data"].get("flag_id")
            and not trigger["event_data"].get("flag")
        ):
            for pre in trigger.get("preconditions", []):
                pre_type = str(pre.get("type", "")).strip().lower()
                if pre_type in {"has_flag", "flag_true"}:
                    trigger["event_data"]["flag"] = pre.get("flag_id") or pre.get("flag")
                    break

        trigger["preconditions"] = [
            _normalize_condition(pre) for pre in trigger.get("preconditions", [])
        ]

        normalized_effects: list[dict[str, Any]] = []
        for effect in trigger.get("effects", []):
            if str(effect.get("type", "")).strip().lower() == "message":
                if not trigger.get("message"):
                    trigger["message"] = effect.get("text") or effect.get("message")
                continue
            normalized_effects.append(_normalize_effect(effect, item_rooms=item_rooms))
        trigger["effects"] = normalized_effects
        if not trigger.get("message"):
            trigger["message"] = trigger.get("text") or trigger.get("response_text")


def _normalize_quests(spec: dict[str, Any]) -> None:
    """Fill in derived quest and objective flags, keeping them unique."""
    quests = spec.get("quests", [])
    flags = spec.setdefault("flags", [])
    existing_flag_ids = {
        str(flag["id"])
        for flag in flags
        if isinstance(flag, dict) and flag.get("id") is not None
    }
    generated_flags: list[dict[str, Any]] = []

    for index, quest in enumerate(quests):
        if "quest_type" not in quest:
            if "is_main_quest" in quest:
                quest["quest_type"] = "main" if quest.get("is_main_quest") else "side"
            else:
                quest["quest_type"] = "main" if index == 0 else "side"
        quest.setdefault("score_value", 0)
        quest.setdefault("sort_order", index)

    if not any(quest.get("quest_type") == "main" for quest in quests):
        quests.insert(
            0,
            {
                "id": "main_quest",
                "name": "Main Quest",
                "description": "Complete the adventure.",
                "quest_type": "main",
                "discovery_flag": None,
                "completion_flag": "main_quest_complete",
                "score_value": 0,
                "sort_order": 0,
                "objectives": [
                    {
                        "id": "complete_the_adventure",
                        "description": "Complete the adventure.",
                        "completion_flag": "main_quest_complete_adventure",
                        "order_index": 0,
                        "is_optional": 0,
                        "bonus_score": 0,
                    }
                ],
            },
        )

    for quest in quests:
        quest_id = str(quest["id"])
        completion_flag = _optional_str(quest.get("completion_flag"))
        if completion_flag is None:
            completion_flag = f"{quest_id}_complete"
            quest["completion_flag"] = completion_flag
        if completion_flag not in existing_flag_ids:
            generated_flags.append(
                {
                    "id": completion_flag,
                    "value": "false",
                    "description": f"Auto-generated completion flag for quest {quest_id}.",
                }
            )
            existing_flag_ids.add(completion_flag)

        objectives = quest.setdefault("objectives", [])
        for objective in objectives:
            objective_id = str(objective["id"])
            if objective.get("completion_flag") is None:
                candidate_flag = None
                set_flags = objective.get("set_flags") or []
                required_flags = objective.get("required_flags") or []
                if set_flags:
                    candidate_flag = str(set_flags[0])
                elif len(required_flags) == 1:
                    candidate_flag = str(required_flags[0])
                if candidate_flag:
                    objective["completion_flag"] = candidate_flag
            objective.setdefault("order_index", 0)
            objective.setdefault("is_optional", 0)
            objective.setdefault("bonus_score", 0)
            objective_completion_flag = _optional_str(objective.get("completion_flag"))
            if objective_completion_flag is None:
                objective_completion_flag = f"{quest_id}_{objective_id}_complete"
                objective["completion_flag"] = objective_completion_flag
            if objective_completion_flag not in existing_flag_ids:
                generated_flags.append(
                    {
                        "id": objective_completion_flag,
                        "value": "false",
                        "description": (
                            f"Auto-generated completion flag for quest objective {objective_id}."
                        ),
                    }
                )
                existing_flag_ids.add(objective_completion_flag)

    flags.extend(generated_flags)


def _insert_rooms(db: GameDB, spec: dict[str, Any]) -> None:
    for room in spec.get("rooms", []):
        db.insert_room(
            id=room["id"],
            name=room["name"],
            description=room["description"],
            short_description=room.get("short_description") or room["description"],
            first_visit_text=_optional_str(room.get("first_visit_text")),
            region=room.get("region", "world"),
            is_dark=_bool_to_int(room.get("is_dark", False)),
            is_start=_bool_to_int(room.get("is_start", False)),
            visited=_bool_to_int(room.get("visited", False)),
        )


def _insert_exits(db: GameDB, spec: dict[str, Any]) -> None:
    for exit_row in spec.get("exits", []):
        db.insert_exit(
            id=exit_row["id"],
            from_room_id=exit_row["from_room_id"],
            to_room_id=exit_row["to_room_id"],
            direction=exit_row["direction"],
            description=_optional_str(exit_row.get("description")),
            is_locked=_bool_to_int(exit_row.get("is_locked", False)),
            is_hidden=_bool_to_int(exit_row.get("is_hidden", False)),
        )


def _insert_items(db: GameDB, spec: dict[str, Any]) -> None:
    pending = [dict(item) for item in spec.get("items", [])]
    inserted_ids: set[str] = set()
    known_ids = {item["id"] for item in pending}

    while pending:
        progress = False
        remaining: list[dict[str, Any]] = []
        for item in pending:
            deps = {
                dep
                for dep in (
                    item.get("container_id"),
                    item.get("key_item_id"),
                    item.get("requires_item_id"),
                )
                if dep
            }
            unresolved = deps & known_ids - inserted_ids
            if unresolved:
                remaining.append(item)
                continue

            db.insert_item(
                id=item["id"],
                name=item["name"],
                description=item["description"],
                examine_description=item.get("examine_description") or item["description"],
                room_id=_optional_str(item.get("room_id")),
                container_id=_optional_str(item.get("container_id")),
                is_takeable=_bool_to_int(item.get("is_takeable", True)),
                is_visible=_bool_to_int(item.get("is_visible", True)),
                is_consumed_on_use=_bool_to_int(item.get("is_consumed_on_use", False)),
                is_container=_bool_to_int(item.get("is_container", False)),
                is_open=_bool_to_int(item.get("is_open", False)),
                has_lid=_bool_to_int(item.get("has_lid", True)),
                is_locked=_bool_to_int(item.get("is_locked", False)),
                lock_message=_optional_str(item.get("lock_message")),
                open_message=_optional_str(item.get("open_message")),
                search_message=_optional_str(item.get("search_message")),
                take_message=_optional_str(item.get("take_message")),
                drop_message=_optional_str(item.get("drop_message")),
                weight=item.get("weight", 1),
                category=_optional_str(item.get("category")),
                room_description=_optional_str(item.get("room_description")),
                read_description=_optional_str(item.get("read_description")),
                key_item_id=_optional_str(item.get("key_item_id")),
                consume_key=_bool_to_int(item.get("consume_key", False)),
                unlock_message=_optional_str(item.get("unlock_message")),
                accepts_items=_json_or_none(item.get("accepts_items")),
                reject_message=_optional_str(item.get("reject_message")),
                home_room_id=_optional_str(item.get("home_room_id")),
                drop_description=_optional_str(item.get("drop_description")),
                is_toggleable=_bool_to_int(item.get("is_toggleable", False)),
                toggle_state=_optional_str(item.get("toggle_state")),
                toggle_on_message=_optional_str(item.get("toggle_on_message")),
                toggle_off_message=_optional_str(item.get("toggle_off_message")),
                toggle_states=_json_or_none(item.get("toggle_states")),
                toggle_messages=_json_or_none(item.get("toggle_messages")),
                requires_item_id=_optional_str(item.get("requires_item_id")),
                requires_message=_optional_str(item.get("requires_message")),
                item_tags=_json_or_none(item.get("item_tags")),
                quantity=item.get("quantity"),
                max_quantity=item.get("max_quantity"),
                quantity_unit=_optional_str(item.get("quantity_unit")),
                depleted_message=_optional_str(item.get("depleted_message")),
                quantity_description=_optional_str(item.get("quantity_description")),
            )
            inserted_ids.add(item["id"])
            progress = True

        if not progress:
            unresolved_ids = ", ".join(item["id"] for item in remaining)
            raise ImportSpecError(
                f"Could not resolve item dependencies while importing: {unresolved_ids}"
            )
        pending = remaining


def _insert_npcs(db: GameDB, spec: dict[str, Any]) -> None:
    for npc in spec.get("npcs", []):
        db.insert_npc(
            id=npc["id"],
            name=npc["name"],
            description=npc["description"],
            examine_description=npc.get("examine_description") or npc["description"],
            room_id=npc["room_id"],
            is_alive=_bool_to_int(npc.get("is_alive", True)),
            is_blocking=_bool_to_int(npc.get("is_blocking", False)),
            blocked_exit_id=_optional_str(npc.get("blocked_exit_id")),
            unblock_flag=_optional_str(npc.get("unblock_flag")),
            default_dialogue=npc.get("default_dialogue", ""),
            hp=npc.get("hp"),
            damage=npc.get("damage"),
            category=_optional_str(npc.get("category")),
        )


def _insert_dialogue(db: GameDB, spec: dict[str, Any]) -> None:
    for node in spec.get("dialogue_nodes", []):
        db.insert_dialogue_node(
            id=node["id"],
            npc_id=node["npc_id"],
            content=node["content"],
            set_flags=_json_or_none(node.get("set_flags")),
            is_root=_bool_to_int(node.get("is_root", False)),
        )

    for option in spec.get("dialogue_options", []):
        db.insert_dialogue_option(
            id=option["id"],
            node_id=option["node_id"],
            text=option["text"],
            next_node_id=_optional_str(option.get("next_node_id")),
            required_flags=_json_or_none(option.get("required_flags")),
            excluded_flags=_json_or_none(option.get("excluded_flags")),
            required_items=_json_or_none(option.get("required_items")),
            set_flags=_json_or_none(option.get("set_flags")),
            sort_order=int(option.get("sort_order", 0)),
        )


def _insert_puzzles(db: GameDB, spec: dict[str, Any]) -> None:
    for puzzle in spec.get("puzzles", []):
        db.insert_puzzle(
            id=puzzle["id"],
            name=puzzle["name"],
            description=puzzle["description"],
            room_id=puzzle["room_id"],
            is_solved=_bool_to_int(puzzle.get("is_solved", False)),
            solution_steps=_json_value(puzzle.get("solution_steps", [])),
            hint_text=_json_or_none(puzzle.get("hint_text")),
            difficulty=int(puzzle.get("difficulty", 1)),
            score_value=int(puzzle.get("score_value", 0)),
            is_optional=_bool_to_int(puzzle.get("is_optional", False)),
        )


def _insert_locks(db: GameDB, spec: dict[str, Any]) -> None:
    for lock in spec.get("locks", []):
        db.insert_lock(
            id=lock["id"],
            lock_type=lock["lock_type"],
            target_exit_id=lock["target_exit_id"],
            key_item_id=_optional_str(lock.get("key_item_id")),
            puzzle_id=_optional_str(lock.get("puzzle_id")),
            combination=_optional_str(lock.get("combination")),
            required_flags=_json_or_none(lock.get("required_flags")),
            locked_message=lock.get("locked_message", "It is locked."),
            unlock_message=lock.get("unlock_message", "It unlocks."),
            is_locked=_bool_to_int(lock.get("is_locked", True)),
            consume_key=_bool_to_int(lock.get("consume_key", True)),
        )


def _insert_flags(db: GameDB, spec: dict[str, Any]) -> None:
    for flag in spec.get("flags", []):
        db.insert_flag(
            id=flag["id"],
            value=_flag_value(flag.get("value", "false")),
            description=_optional_str(flag.get("description")),
        )


def _insert_commands(db: GameDB, spec: dict[str, Any]) -> None:
    for cmd in spec.get("commands", []):
        context_room_ids = cmd.get("context_room_ids")
        context_value = None if not context_room_ids else _json_value(context_room_ids)
        db.insert_command(
            id=cmd["id"],
            verb=cmd["verb"],
            pattern=cmd["pattern"],
            preconditions=_json_value(cmd.get("preconditions", [])),
            effects=_json_value(cmd.get("effects", [])),
            success_message=cmd.get("success_message", ""),
            failure_message=cmd.get("failure_message", ""),
            context_room_ids=context_value,
            puzzle_id=_optional_str(cmd.get("puzzle_id")),
            priority=int(cmd.get("priority", 0)),
            is_enabled=_bool_to_int(cmd.get("is_enabled", True)),
            one_shot=_bool_to_int(cmd.get("one_shot", False)),
            executed=_bool_to_int(cmd.get("executed", False)),
            done_message=cmd.get("done_message", ""),
        )


def _insert_quests(db: GameDB, spec: dict[str, Any]) -> None:
    for quest in spec.get("quests", []):
        db.insert_quest(
            id=quest["id"],
            name=quest["name"],
            description=quest["description"],
            quest_type=quest["quest_type"],
            status=quest.get("status", "undiscovered"),
            discovery_flag=_optional_str(quest.get("discovery_flag")),
            completion_flag=quest["completion_flag"],
            score_value=int(quest.get("score_value", 0)),
            sort_order=int(quest.get("sort_order", 0)),
        )
        for objective in quest.get("objectives", []):
            db.insert_quest_objective(
                id=objective["id"],
                quest_id=quest["id"],
                description=objective["description"],
                completion_flag=objective["completion_flag"],
                order_index=int(objective.get("order_index", 0)),
                is_optional=_bool_to_int(objective.get("is_optional", False)),
                bonus_score=int(objective.get("bonus_score", 0)),
            )


def _insert_interaction_responses(db: GameDB, spec: dict[str, Any]) -> None:
    for response in spec.get("interaction_responses", []):
        effects_raw = response.get("effects")
        effects_value = _json_value(effects_raw) if effects_raw else None
        db.insert_interaction_response(
            id=response["id"],
            item_tag=response["item_tag"],
            target_category=response["target_category"],
            response=response["response"],
            consumes=int(response.get("consumes", 0)),
            score_change=int(response.get("score_change", 0)),
            flag_to_set=_optional_str(response.get("flag_to_set")),
            effects=effects_value,
        )


def _insert_triggers(db: GameDB, spec: dict[str, Any]) -> None:
    for trigger in spec.get("triggers", []):
        db.insert_trigger(
            id=trigger["id"],
            event_type=trigger["event_type"],
            event_data=_json_value(trigger.get("event_data", {})),
            preconditions=_json_value(trigger.get("preconditions", [])),
            effects=_json_value(trigger.get("effects", [])),
            message=_optional_str(trigger.get("message")),
            priority=int(trigger.get("priority", 0)),
            one_shot=_bool_to_int(trigger.get("one_shot", False)),
            executed=_bool_to_int(trigger.get("executed", False)),
            is_enabled=_bool_to_int(trigger.get("is_enabled", True)),
        )


def _initialize_player(db: GameDB, spec: dict[str, Any]) -> None:
    player = spec.get("player", {})
    rooms = spec.get("rooms", [])
    start_room_id = player.get("start_room_id")
    if not start_room_id:
        for room in rooms:
            if room.get("is_start"):
                start_room_id = room["id"]
                break
    if not start_room_id and rooms:
        start_room_id = rooms[0]["id"]
    if not start_room_id:
        raise ImportSpecError(
            "Import spec must define at least one room or a player.start_room_id."
        )

    db.init_player(
        start_room_id=str(start_room_id),
        hp=int(player.get("hp", 100)),
        max_hp=int(player.get("max_hp", 100)),
    )


def _validate_imported_game(db: GameDB) -> list[str]:
    results = validate_game(db)
    errors = [finding.message for finding in results if finding.severity == "error"]
    if errors:
        preview = "; ".join(errors[:8])
        raise ImportSpecError(f"Imported game failed validation: {preview}")
    return [finding.message for finding in results if finding.severity != "error"]


def _validate_exit_directions(spec: dict[str, Any]) -> None:
    """Reject imported exits that use unsupported direction labels."""
    invalid: list[str] = []
    for exit_row in spec.get("exits", []):
        direction = str(exit_row.get("direction", "")).strip().lower()
        if direction and direction not in ALLOWED_EXIT_DIRECTIONS:
            invalid.append(direction)
    if invalid:
        unique = ", ".join(sorted(set(invalid)))
        allowed = ", ".join(ALLOWED_EXIT_DIRECTIONS)
        raise ImportSpecError(
            f"Unsupported exit direction(s): {unique}. Allowed directions are: {allowed}."
        )


def _json_value(value: Any) -> str:
    return json.dumps(value if value is not None else [])


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _bool_to_int(value: Any) -> int:
    return 1 if bool(value) else 0


def _flag_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    return "true" if text in {"1", "true", "yes"} else "false"
