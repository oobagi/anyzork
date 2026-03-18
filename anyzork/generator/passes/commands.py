"""Pass 7: Commands — Wire the entire world together with DSL rules.

This is the most critical pass in the generation pipeline.  Every
interactable entity in the game needs commands.  If the player can see it,
they will try to interact with it.  If there is no command for that
interaction, they get a generic "You can't do that" — acceptable for truly
non-interactive scenery but frustrating for items, NPCs, and puzzle elements.

Commands use the AnyZork Command DSL: each command is a JSON rule with a
verb, a pattern, preconditions (all must be true to fire), and effects
(executed in order when the command fires).

**Built-in verbs** handled by the engine (do NOT generate DSL commands for
these unless overriding default behavior):
  - take, drop, examine, open, talk, ask

**DSL commands should focus on game-specific interactions**:
  - use X on Y, combine X with Y, read X, pull X, push X, give X to Y,
    show X to Y, enter <code>, light X, extinguish X, etc.

This pass also generates all the flag definitions referenced by commands.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, GenerationContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON schema the LLM must conform to
# ---------------------------------------------------------------------------

COMMANDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["commands", "flags"],
    "properties": {
        "commands": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "verb",
                    "pattern",
                    "preconditions",
                    "effects",
                    "success_message",
                    "failure_message",
                    "priority",
                    "one_shot",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier.",
                    },
                    "verb": {
                        "type": "string",
                        "description": "The first word of input that triggers matching.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Full input pattern with {slot} placeholders. "
                            "Must start with the verb."
                        ),
                    },
                    "preconditions": {
                        "type": "array",
                        "description": "Array of precondition objects. ALL must be true.",
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "in_room",
                                        "has_item",
                                        "has_flag",
                                        "not_flag",
                                        "item_in_room",
                                        "npc_in_room",
                                        "lock_unlocked",
                                        "puzzle_solved",
                                        "health_above",
                                        "container_open",
                                    ],
                                },
                            },
                        },
                    },
                    "effects": {
                        "type": "array",
                        "description": "Ordered array of effect objects.",
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "move_item",
                                        "remove_item",
                                        "set_flag",
                                        "unlock",
                                        "move_player",
                                        "spawn_item",
                                        "change_health",
                                        "add_score",
                                        "reveal_exit",
                                        "solve_puzzle",
                                        "discover_quest",
                                        "print",
                                        "open_container",
                                        "move_item_to_container",
                                    ],
                                },
                            },
                        },
                    },
                    "success_message": {
                        "type": "string",
                        "description": "Text shown when the command fires.",
                    },
                    "failure_message": {
                        "type": "string",
                        "description": (
                            "Text shown when preconditions fail. "
                            "Should hint at what is missing."
                        ),
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Higher priority wins on ambiguous matches.",
                    },
                    "one_shot": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = fires only once, then disabled forever.",
                    },
                    "context_room_ids": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": (
                            "JSON array of room IDs where this command is "
                            "active. null = global (works anywhere). "
                            '["room_a"] = only in that room. '
                            '["room_a", "room_b"] = works in either.'
                        ),
                    },
                    "done_message": {
                        "type": "string",
                        "description": (
                            "For one_shot commands: message shown when the player "
                            "tries the action again after it has already been "
                            "executed. Leave empty if no feedback is needed."
                        ),
                    },
                },
            },
        },
        "flags": {
            "type": "array",
            "description": "All flags referenced by commands, with initial values.",
            "items": {
                "type": "object",
                "required": ["id", "description"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case flag identifier.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Internal documentation of this flag.",
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(context: dict) -> str:
    """Construct the LLM prompt for command generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    npcs = context.get("npcs", [])
    locks = context.get("locks", [])
    puzzles = context.get("puzzles", [])

    rooms_summary = json.dumps(
        [{"id": r["id"], "name": r["name"], "region": r["region"]} for r in rooms],
        indent=2,
    )

    items_summary = json.dumps(items, indent=2)
    npcs_summary = json.dumps(npcs, indent=2)
    locks_summary = json.dumps(locks, indent=2) if locks else "[]"
    puzzles_summary = json.dumps(puzzles, indent=2) if puzzles else "[]"

    # Build the exits summary from context
    exits = context.get("exits", [])
    exits_summary = json.dumps(
        [
            {
                "id": e["id"],
                "from_room_id": e.get("from_room_id"),
                "to_room_id": e.get("to_room_id"),
                "direction": e.get("direction"),
                "is_locked": e.get("is_locked", 0),
                "is_hidden": e.get("is_hidden", 0),
            }
            for e in exits
        ],
        indent=2,
    ) if exits else "[]"

    return f"""\
You are the command systems designer for a Zork-style text adventure engine.
Your job is to generate the DSL command rules that wire every interactable
entity in the game together.

## World Concept
{json.dumps(concept, indent=2)}

## Rooms
{rooms_summary}

## Exits
{exits_summary}

## Items
{items_summary}

## NPCs
{npcs_summary}

## Locks
{locks_summary}

## Puzzles
{puzzles_summary}

## The Command DSL — CRITICAL REFERENCE

### Structure

Each command is a JSON rule:
- **verb**: The first word of the player's input (lowercased).
- **pattern**: Full input pattern with {{slot}} placeholders.
  Example: `use {{item}} on {{target}}`
- **preconditions**: ALL must be true for the command to fire.
- **effects**: Executed in order when all preconditions pass.
- **success_message**: Shown when the command fires.
- **failure_message**: Shown when preconditions fail. Must be informative.
- **one_shot**: 1 = fires only once (key unlocks, puzzle solutions, quest
  discoveries). 0 = repeatable.
- **context_room_ids**: JSON array of room IDs where the command is active.
  null = global (works anywhere). `["room_a"]` = only in that room.
  `["room_a", "room_b"]` = works in either.

### BUILT-IN VERBS — DO NOT GENERATE COMMANDS FOR THESE

The engine handles these verbs with built-in logic:
- **take** / **get** — picks up takeable items
- **drop** — drops items from inventory
- **examine** / **look at** / **inspect** — shows examine_description
- **read** — shows read_description (falls back to examine_description).
  DO NOT generate "read" commands — set `read_description` on items instead.
- **open** — basic open interaction (including auto-unlock if player has key)
- **unlock** — tries to unlock exits/containers using key_item_id from schema
- **use {{item}} on {{target}}** for key-on-lock — if a lock or container has
  `key_item_id` set, the engine handles "use key on door" automatically.
  DO NOT generate "use key on lock" commands — the locks table and items
  table `key_item_id` field handle this.
- **talk to** / **speak to** — triggers NPC dialogue system
- **ask ... about** — triggers NPC topic dialogue with flag-gated responses.
  DO NOT generate "ask NPC about topic" commands — use dialogue table entries.

DO NOT create commands for these verbs UNLESS you need to override default
behavior for a specific interaction (e.g., examining a specific item triggers
a special event beyond the normal examine_description).

### ONE-SHOT COMMANDS — USE done_message INSTEAD OF DUPLICATES

When a one-shot command has already been executed, the engine shows its
`done_message` field instead of "I don't understand." DO NOT generate
separate "already done" duplicate commands. Instead, set `done_message`
on the original one-shot command.

### GAME-SPECIFIC VERBS — YOUR FOCUS

Generate commands for these kinds of interactions:
- `use {{item}} on {{target}}` — key on lock, tool on object, item on puzzle
- `combine {{item}} with {{item2}}` — merge two inventory items
- `read {{target}}` — read inscriptions, books, notes, signs
- `pull {{target}}` — pull levers, chains, handles
- `push {{target}}` — push buttons, statues, blocks
- `give {{item}} to {{npc}}` — hand items to NPCs for quests
- `show {{item}} to {{npc}}` — present items without giving them away
- `light {{target}}` — light a lantern, torch, candle
- `enter {{code}}` — combination lock codes
- `pour {{item}}` / `pour {{item}} on {{target}}` — liquid interactions
- `climb {{target}}` — ropes, ladders, walls
- `turn {{target}}` — dials, wheels, keys in locks
- `insert {{item}} in {{target}}` — placing objects into receptacles

### Precondition Types Reference

| Type | Required Fields | Description |
|------|----------------|-------------|
| `in_room` | `room` | Player is in this room |
| `has_item` | `item` | Player has item in inventory. Supports `{{slot}}` refs |
| `has_flag` | `flag` | World flag is set (truthy) |
| `not_flag` | `flag` | World flag is NOT set |
| `item_in_room` | `item`, `room` | Item exists in room. `"_current"` for current room |
| `npc_in_room` | `npc`, `room` | NPC is in room. `"_current"` for current room |
| `lock_unlocked` | `lock` | Lock is unlocked |
| `puzzle_solved` | `puzzle` | Puzzle is solved |
| `health_above` | `threshold` | Player health > threshold |

### Effect Types Reference

| Type | Required Fields | Description |
|------|----------------|-------------|
| `move_item` | `item`, `from`, `to` | Move item between locations. `"_inventory"`, `"_current"`, or room ID |
| `remove_item` | `item` | Permanently destroy item |
| `set_flag` | `flag` | Set a world flag. Optional `value` (default true) |
| `unlock` | `lock` | Unlock a lock |
| `move_player` | `room` | Teleport player |
| `spawn_item` | `item`, `location` | Place a hidden item into the world |
| `change_health` | `amount` | Modify HP (positive heals, negative damages) |
| `add_score` | `points` | Add score points |
| `reveal_exit` | `exit` | Make hidden exit visible |
| `solve_puzzle` | `puzzle` | Mark puzzle as solved |
| `discover_quest` | `quest` | Set quest's discovery flag to trigger discovery |
| `print` | `message` | Display text. Supports `{{slot}}` refs |
| `open_container` | `container` | Set container is_locked=0 and is_open=1 |
| `move_item_to_container` | `item`, `container` | Move item into a container |

### Additional Precondition Type

| `container_open` | `container` | Container is open (or has no lid) |

### Container Unlock Commands

Locked containers with `key_item_id` set are handled automatically by the
engine — do NOT generate DSL commands for those. Only generate DSL commands
for locked containers that require non-key interactions (e.g., solving a
puzzle, using a tool in a non-standard way).

### Command Coverage Requirements

1. **Key-type locks are handled automatically** — do NOT generate "use key
   on lock" commands. The engine reads `key_item_id` from the locks table
   and items table (for containers) and handles unlocking automatically.

2. **Every puzzle** needs commands matching its solution steps.  The final
   step should include `solve_puzzle` in its effects.

3. **Interactive scenery items** (levers, buttons, switches) need
   appropriate commands.

4. **NPC quest interactions** (give item, show item) need commands with
   `npc_in_room` preconditions. But "ask NPC about topic" is handled by
   the dialogue system — do NOT generate DSL commands for those.

5. **Combination locks** need `enter {{code}}` commands.

6. **State-based interactions** — items or scenery that change behavior
   depending on flags (lit/unlit lantern, open/closed container).

7. **Readable items are handled automatically** — do NOT generate "read"
   commands. Set `read_description` on the item instead.

### CRITICAL: Use Exact IDs

You MUST use the exact `id` values from the data above. Do NOT invent
room, item, NPC, lock, exit, or puzzle IDs — copy them verbatim from
the lists. If `context_room_ids` entries or `puzzle_id` does not match an
existing entity, the reference will be dropped.

### Design Principles

- **Focus on UNIQUE interactions only**: Do not generate commands for patterns
  the engine handles automatically (key-on-lock, read, ask NPC about topic).
  Only generate DSL commands for interactions that cannot be derived from
  schema data.

- **No verb synonym duplicates**: Generate ONE canonical command per
  interaction. Do not create alternate-verb versions (e.g., do not create
  both "use X on Y" and "cut Y" for the same action).

- **Use done_message for one-shot feedback**: When a one-shot command has
  already been executed, set `done_message` to tell the player. Do NOT
  generate a second "already done" command.

- **Informative failure messages**: "The door is locked" is better than
  "You can't do that."  "The key doesn't fit this lock" is better than
  "Nothing happens."

- **One-shot for permanent changes**: Puzzle solutions, quest
  discoveries, first-time NPC meetings should be one_shot = 1.

- **Repeatable for observation**: Looking at scenery — one_shot = 0.

- **Priority ordering**: Use higher priority for specific overrides.
  A room-specific "push statue" command (priority 10) should beat a generic
  "push {{target}}" command (priority 0).

### Flags

Also generate a `flags` array listing ALL flags referenced by your commands
(in preconditions or effects), with descriptions.  All flags initialize to
`"false"`.

## Output Format

```json
{{
  "commands": [
    {{
      "id": "use_rusty_key_on_dungeon_door",
      "verb": "use",
      "pattern": "use {{item}} on {{target}}",
      "preconditions": [
        {{"type": "in_room", "room": "dungeon_entrance"}},
        {{"type": "has_item", "item": "rusty_key"}},
        {{"type": "not_flag", "flag": "dungeon_door_opened"}}
      ],
      "effects": [
        {{"type": "remove_item", "item": "rusty_key"}},
        {{"type": "unlock", "lock": "dungeon_door_lock"}},
        {{"type": "set_flag", "flag": "dungeon_door_opened"}},
        {{"type": "add_score", "points": 10}},
        {{"type": "print", "message": "The key turns with a grinding screech..."}}
      ],
      "success_message": "",
      "failure_message": "You need the right key for this door.",
      "priority": 10,
      "one_shot": 1,
      "context_room_ids": ["dungeon_entrance"]
    }}
  ],
  "flags": [
    {{
      "id": "dungeon_door_opened",
      "description": "Set when the player unlocks the dungeon door with the rusty key."
    }}
  ]
}}
```

Generate commands for EVERY interactable entity and EVERY puzzle step.
Be thorough — a missing command means the player cannot progress.
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

VALID_PRECONDITION_TYPES = {
    "in_room",
    "has_item",
    "has_flag",
    "not_flag",
    "item_in_room",
    "npc_in_room",
    "lock_unlocked",
    "puzzle_solved",
    "health_above",
    "container_open",
}

VALID_EFFECT_TYPES = {
    "move_item",
    "remove_item",
    "set_flag",
    "unlock",
    "move_player",
    "spawn_item",
    "change_health",
    "add_score",
    "reveal_exit",
    "solve_puzzle",
    "discover_quest",
    "print",
    "open_container",
    "move_item_to_container",
}


def _validate_commands(
    commands: list[dict], flags: list[dict], context: dict
) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []
    room_ids = {r["id"] for r in context.get("rooms", [])}
    item_ids = {i["id"] for i in context.get("items", [])}
    npc_ids = {n["id"] for n in context.get("npcs", [])}
    lock_ids = {lk["id"] for lk in context.get("locks", [])}
    puzzle_ids = {p["id"] for p in context.get("puzzles", [])}

    seen_ids: set[str] = set()

    for cmd in commands:
        cid = cmd.get("id", "<missing>")

        # Unique ID
        if cid in seen_ids:
            errors.append(f"Duplicate command id: {cid}")
        seen_ids.add(cid)

        # Verb present
        if not cmd.get("verb"):
            errors.append(f"Command {cid} missing verb")

        # Pattern starts with verb
        pattern = cmd.get("pattern", "")
        verb = cmd.get("verb", "")
        if pattern and verb and not pattern.lower().startswith(verb.lower()):
            errors.append(
                f"Command {cid} pattern '{pattern}' does not start with verb '{verb}'"
            )

        # Context room reference(s)
        ctx_rooms = cmd.get("context_room_ids")
        if ctx_rooms:
            if isinstance(ctx_rooms, list):
                for r in ctx_rooms:
                    if r not in room_ids:
                        errors.append(
                            f"Command {cid} references unknown room in context_room_ids: {r}"
                        )
            elif isinstance(ctx_rooms, str) and ctx_rooms not in room_ids:
                # Legacy single-string form
                errors.append(
                    f"Command {cid} references unknown context_room_ids: {ctx_rooms}"
                )

        # Validate precondition types
        for pre in cmd.get("preconditions", []):
            ptype = pre.get("type", "")
            if ptype not in VALID_PRECONDITION_TYPES:
                errors.append(
                    f"Command {cid} has invalid precondition type: {ptype}"
                )

        # Validate effect types
        effects = cmd.get("effects", [])
        if not effects:
            errors.append(f"Command {cid} has no effects")
        for eff in effects:
            etype = eff.get("type", "")
            if etype not in VALID_EFFECT_TYPES:
                errors.append(f"Command {cid} has invalid effect type: {etype}")

        # Success/failure messages
        if not cmd.get("failure_message"):
            errors.append(f"Command {cid} missing failure_message")

    # Validate flags
    seen_flag_ids: set[str] = set()
    for flag in flags:
        fid = flag.get("id", "<missing>")
        if fid in seen_flag_ids:
            errors.append(f"Duplicate flag id: {fid}")
        seen_flag_ids.add(fid)

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_commands(db: GameDB, commands: list[dict], context: dict) -> list[dict]:
    """Insert validated commands into the database.

    FK references (context_room_ids, puzzle_id) are checked against known
    IDs before insertion.  Invalid references are removed with a warning.

    Returns the list of successfully inserted commands.
    """
    room_ids = {r["id"] for r in context.get("rooms", [])}
    puzzle_ids = {p["id"] for p in context.get("puzzles", [])}
    inserted: list[dict] = []

    for cmd in commands:
        cid = cmd.get("id", "<unknown>")

        # --- Validate context_room_ids (nullable, JSON array of room IDs) ---
        ctx_rooms = cmd.get("context_room_ids")
        if ctx_rooms is not None:
            if isinstance(ctx_rooms, list):
                valid_rooms = [r for r in ctx_rooms if r in room_ids]
                invalid = [r for r in ctx_rooms if r not in room_ids]
                for r in invalid:
                    logger.warning(
                        "Command %s references non-existent room %r in "
                        "context_room_ids — removing",
                        cid,
                        r,
                    )
                cmd["context_room_ids"] = valid_rooms if valid_rooms else None
            elif isinstance(ctx_rooms, str):
                # Legacy single-string form
                if ctx_rooms not in room_ids:
                    logger.warning(
                        "Command %s references non-existent context_room_ids %r — "
                        "setting to NULL",
                        cid,
                        ctx_rooms,
                    )
                    cmd["context_room_ids"] = None
                else:
                    cmd["context_room_ids"] = [ctx_rooms]

        # --- Validate puzzle_id (nullable FK) ---
        puz_id = cmd.get("puzzle_id")
        if puz_id is not None and puz_id not in puzzle_ids:
            logger.warning(
                "Command %s references non-existent puzzle_id %r — "
                "setting to NULL",
                cid,
                puz_id,
            )
            cmd["puzzle_id"] = None

        ctx_value = cmd.get("context_room_ids")
        if isinstance(ctx_value, list):
            ctx_value = json.dumps(ctx_value) if ctx_value else None

        db.insert_command(
            id=cmd["id"],
            verb=cmd["verb"],
            pattern=cmd["pattern"],
            preconditions=json.dumps(cmd.get("preconditions", [])),
            effects=json.dumps(cmd.get("effects", [])),
            success_message=cmd.get("success_message", ""),
            failure_message=cmd.get("failure_message", ""),
            context_room_ids=ctx_value,
            puzzle_id=cmd.get("puzzle_id"),
            priority=cmd.get("priority", 0),
            is_enabled=1,
            one_shot=cmd.get("one_shot", 0),
            executed=0,
            done_message=cmd.get("done_message", ""),
        )
        inserted.append(cmd)

    return inserted


def _insert_flags(db: GameDB, flags: list[dict]) -> None:
    """Insert flag definitions into the database."""
    for flag in flags:
        db.insert_flag(
            id=flag["id"],
            value="false",
            description=flag.get("description", ""),
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 7: Commands.  Returns updated context with command data."""

    logger.info("Pass 7: Generating commands...")

    prompt = _build_prompt(context)
    gen_ctx = GenerationContext(
        existing_data={},
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=32_768,
    )

    result = provider.generate_structured(prompt, COMMANDS_SCHEMA, gen_ctx)
    commands: list[dict] = result.get("commands", [])
    flags: list[dict] = result.get("flags", [])

    # Validate
    errors = _validate_commands(commands, flags, context)
    if errors:
        for err in errors:
            logger.warning("Command validation: %s", err)

    # Insert flags first (commands may reference them)
    _insert_flags(db, flags)

    # Insert commands (with FK validation)
    inserted_commands = _insert_commands(db, commands, context)

    # Build pass-specific data for downstream passes (only inserted commands)
    commands_summary = [
        {
            "id": c["id"],
            "verb": c["verb"],
            "pattern": c["pattern"],
            "context_room_ids": c.get("context_room_ids"),
            "one_shot": c.get("one_shot", 0),
        }
        for c in inserted_commands
    ]
    flags_summary = [
        {"id": f["id"], "description": f.get("description", "")} for f in flags
    ]

    logger.info(
        "Pass 7 complete: %d commands and %d flags generated.",
        len(inserted_commands),
        len(flags),
    )
    return {"commands": commands_summary, "flags": flags_summary}
