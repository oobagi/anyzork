"""ZorkScript LLM prompt template and builder."""

# ruff: noqa: E501

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

_PROMPT_SYSTEM_FILES: tuple[Path, ...] = (
    Path(__file__),
    Path(__file__).parent.parent / "zorkscript.py",
    Path(__file__).parent.parent / "wizard" / "assembler.py",
    Path(__file__).parent.parent / "wizard" / "fields.py",
    Path(__file__).parent.parent / "wizard" / "presets.py",
    Path(__file__).parent.parent / "wizard" / "wizard.py",
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
#
# Exit IDs are auto-generated as {from_room}_{direction}. Example:
#   exit south -> crawlspace (hidden)   --> exit ID is "the_room_south"
# Use this ID with reveal_exit: effect reveal_exit(the_room_south)
#
# Rooms that should become accessible later: add a (hidden) exit, then
# reveal it with reveal_exit(exit_id) when the path opens. Do NOT use
# move_player to reach a room with no exit connection -- the validator
# requires all rooms to be reachable via exits.

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
# NPCs can give items or trigger effects directly in dialogue:
#   talk give_reward {
#     "Here, take this -- you will need it."
#     effect spawn_item(magic_ring, _inventory)
#     effect add_score(10)
#     sets [received_ring]
#     option "Thank you." -> end
#   }
# Effects in talk blocks use the SAME syntax as on/when blocks.
# They fire when the node is visited, before the player sees options.

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
    effect remove_item(silver_key)
    effect add_score(10)
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
#   reveal_exit(exit_id)      -- unhide a hidden exit (ID = {from_room}_{direction})
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
#   fail_quest(quest_id)      -- mark a quest as failed
#   complete_quest(quest_id)  -- force-complete a quest
#   kill_npc(npc_id)          -- kill an NPC by ID (leaves body/loot)
#   remove_npc(npc_id)        -- remove NPC from world entirely (vanished)
#   lock_exit(exit_id)        -- re-lock a previously unlocked exit
#   hide_exit(exit_id)        -- re-hide a previously revealed exit
#   change_description(entity_id, "new text") -- change item/room description at runtime
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
# IMPORTANT RULES:
#   - EVERY item MUST have tags: tags ["weapon", "tool", "food", etc.]
#   - EVERY item and NPC MUST have a category: category "character", "furniture",
#     "device", "fixture", "container", "consumable", etc.
#   - Without tags and categories, "use X on Y" silently fails.
#
# Tags and categories are OPEN-ENDED. Invent whatever fits your world!
# Items can have multiple tags: tags ["weapon", "metal", "blunt"]
#
# Effects for interactions (target-aware + standard):
#   kill_target()         -- kill the target NPC, spawn lootable body
#   damage_target(N)      -- deal N damage to target NPC
#   destroy_target()      -- break target container, scatter contents
#   open_target()         -- open target container
#   set_flag(id)          -- set a flag (chain with triggers for consequences)
#   add_score(N)          -- adjust score
#   print("msg")          -- display extra text
#   kill_npc(npc_id)      -- kill a specific NPC by ID (leaves body/loot)
#   remove_npc(npc_id)    -- remove NPC from world entirely
#   fail_quest(quest_id)  -- mark a quest as failed
#   Plus all other standard effects.
#
# CHAIN CONSEQUENCES: Use set_flag() in interactions, then when blocks to
# create ripple effects. Killing a quest-giver should fail their quest.
# Destroying a locked container should scatter its contents. Think about
# what SHOULD happen when a player tries something creative.
#
# Wildcard: use target "*" as a catch-all default for a tag.
#
# Invent creative combos:
#   "weapon" on "character"      -> kill/damage NPCs
#   "weapon" on "furniture"      -> smash containers
#   "food" on "character"        -> offer food, change attitude
#   "evidence" on "character"    -> confront or accuse
#   "tool" on "device"           -> repair or sabotage
#   "poison" on "consumable"     -> taint food/drink
#   "fire" on "furniture"        -> burn it

interaction weapon_on_character {
  tag      "weapon"
  target   "character"
  response "You strike {target} with the {item}. They collapse to the ground."
  effect   kill_target()
  effect   set_flag(npc_killed)
  effect   add_score(-10)
}

# Chain consequence: use set_flag() + when blocks for ripple effects.
# Example: killing an NPC should have consequences elsewhere.
#
#   when flag_set(npc_killed) {
#     effect fail_quest(village_rescue)
#     effect add_score(-20)
#     message "With the villager dead, the quest is lost."
#     once
#   }
#
# More creative trigger examples:
#
# Environmental change -- a room floods and its description changes:
#   when flag_set(dam_broken) {
#     effect change_description(lower_cavern, "The cavern is knee-deep in rushing water. The old path east is completely submerged.")
#     effect hide_exit(lower_cavern_east)
#     effect print("A wall of water crashes through the cavern!")
#     once
#   }
#
# Cave-in blocks a path:
#   when flag_set(explosion_triggered) {
#     effect lock_exit(mine_shaft_north)
#     effect hide_exit(mine_shaft_north)
#     effect change_description(mine_shaft, "The north tunnel has collapsed. Rubble blocks the way.")
#     effect print("The ceiling gives way! Rocks seal the northern passage.")
#     once
#   }
#
# Bomb goes off, kills a guard:
#   when flag_set(bomb_detonated) {
#     effect kill_npc(tower_guard)
#     effect change_description(tower_base, "Smoke and debris fill the tower entrance. The guard lies motionless.")
#     effect print("BOOM! The blast echoes through the tower.")
#     once
#   }
#
# NPC flees the scene:
#   when flag_set(alarm_raised) {
#     effect remove_npc(shady_merchant)
#     effect print("The merchant grabs his satchel and vanishes into the crowd.")
#     once
#   }

interaction weapon_on_furniture {
  tag      "weapon"
  target   "furniture"
  response "You smash the {item} into the {target}. It splinters apart and its contents scatter across the floor."
  effect   destroy_target()
}

interaction tool_on_device {
  tag      "tool"
  target   "device"
  response "You work the {item} against the {target}. Something clicks."
  effect   open_target()
}

interaction food_on_character {
  tag      "food"
  target   "character"
  response "You offer the {item} to {target}. They accept it gratefully."
  consumes 1
  effect   set_flag(fed_npc)
}

# Wildcard default: any weapon on anything not specifically handled.
interaction weapon_on_default {
  tag      "weapon"
  target   "*"
  response "You swing the {item} at the {target}. It doesn't accomplish much."
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

    # Interaction responses — always required
    lines.append(
        "- EVERY item MUST have tags. EVERY item and NPC MUST have a category."
    )
    lines.append(
        "  Without tags and categories, 'use X on Y' silently fails."
    )
    lines.append(
        "- Write interaction responses for EVERY tag x category combo in the game."
    )
    lines.append(
        "  Include a wildcard (target '*') fallback for each tag."
    )
    lines.append(
        "- Interactions MUST have consequences: use kill_target(), destroy_target(),"
    )
    lines.append(
        "  set_flag(), add_score(), etc. Chain with when blocks for ripple effects."
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
