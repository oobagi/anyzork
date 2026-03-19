"""Pass 5: NPCs — Populate the world with non-player characters.

Reads the world concept, rooms, items, and locks from prior passes, then
prompts the LLM to generate NPCs and their dialogue trees.

NPCs serve five roles:

  * **Quest givers** — provide information, tasks, or items.
  * **Gatekeepers** — block exits until a condition is met.
  * **Merchants / traders** — exchange items with the player.
  * **Lore sources** — deliver world-building through dialogue.
  * **Hostile NPCs** — must be dealt with (combat, diplomacy, stealth).

Every NPC has a consistent voice defined by vocabulary, sentence rhythm, and
personality.  Dialogue lines must pass the "would a real person say this?"
test — no exposition disguised as conversation, no "as you know" speeches.

Dialogue is structured as a tree: nodes contain NPC text, options contain
player choices that branch to other nodes.  Options can be gated by flags
and inventory items.
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

NPCS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["npcs", "dialogue_nodes", "dialogue_options"],
    "properties": {
        "npcs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "name",
                    "description",
                    "examine_description",
                    "room_id",
                    "default_dialogue",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Display name shown to the player.",
                    },
                    "description": {
                        "type": "string",
                        "description": "1-2 sentence description shown when NPC is in a room.",
                    },
                    "examine_description": {
                        "type": "string",
                        "description": "2-4 sentence detailed description on examination.",
                    },
                    "room_id": {
                        "type": "string",
                        "description": "Room ID where this NPC is located.",
                    },
                    "default_dialogue": {
                        "type": "string",
                        "description": (
                            "Fallback dialogue for NPCs without a dialogue tree "
                            "(e.g. hostile NPCs). Also shown if the tree is missing."
                        ),
                    },
                    "is_blocking": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = blocks an exit until a condition is met.",
                    },
                    "blocked_exit_id": {
                        "type": ["string", "null"],
                        "description": "Exit ID this NPC blocks (if is_blocking = 1).",
                    },
                    "unblock_flag": {
                        "type": ["string", "null"],
                        "description": "Flag that must be set to unblock the exit.",
                    },
                    "hp": {
                        "type": ["integer", "null"],
                        "description": "Hit points for combat NPCs, null for non-combatants.",
                    },
                    "damage": {
                        "type": ["integer", "null"],
                        "description": (
                            "Damage per attack for combat NPCs, null for "
                            "non-combatants."
                        ),
                    },
                    "category": {
                        "type": ["string", "null"],
                        "description": (
                            "Category for the interaction matrix. Determines "
                            "how items interact with this NPC via 'use X on Y'. "
                            "Common categories: 'character' (friendly/neutral), "
                            "'hostile' (enemy), 'animal' (non-humanoid creature), "
                            "'merchant' (trader)."
                        ),
                    },
                },
            },
        },
        "dialogue_nodes": {
            "type": "array",
            "description": "All dialogue tree nodes across all NPCs.",
            "items": {
                "type": "object",
                "required": ["id", "npc_id", "content", "is_root"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier for this node.",
                    },
                    "npc_id": {
                        "type": "string",
                        "description": "NPC this node belongs to.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The dialogue text shown to the player.",
                    },
                    "set_flags": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Flags to set when this node is visited.",
                    },
                    "is_root": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = this is the entry point for the NPC's dialogue.",
                    },
                },
            },
        },
        "dialogue_options": {
            "type": "array",
            "description": "All dialogue options across all nodes.",
            "items": {
                "type": "object",
                "required": ["id", "node_id", "text", "sort_order"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier for this option.",
                    },
                    "node_id": {
                        "type": "string",
                        "description": "The dialogue node this option belongs to.",
                    },
                    "text": {
                        "type": "string",
                        "description": "What the player sees as their choice.",
                    },
                    "next_node_id": {
                        "type": ["string", "null"],
                        "description": "Node to navigate to. null = terminal (ends conversation).",
                    },
                    "required_flags": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Flags that must be true for this option to appear.",
                    },
                    "excluded_flags": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Flags that must NOT be true (hide after used).",
                    },
                    "required_items": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Item IDs player must have in inventory.",
                    },
                    "set_flags": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Flags to set when this option is chosen.",
                    },
                    "sort_order": {
                        "type": "integer",
                        "description": "Display order (lower = shown first).",
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
    """Construct the LLM prompt for NPC generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    locks = context.get("locks", [])
    exits = context.get("exits", [])

    rooms_summary = json.dumps(
        [
            {
                "id": r["id"],
                "name": r["name"],
                "region": r["region"],
                "is_start": r.get("is_start", 0),
            }
            for r in rooms
        ],
        indent=2,
    )

    exits_summary = json.dumps(
        [
            {
                "id": e["id"],
                "from_room_id": e.get("from_room_id"),
                "to_room_id": e.get("to_room_id"),
                "direction": e.get("direction"),
            }
            for e in exits
        ],
        indent=2,
    ) if exits else "[]"

    items_summary = json.dumps(
        [
            {
                "id": i["id"],
                "name": i["name"],
                "room_id": i.get("room_id"),
                "category": i.get("category"),
            }
            for i in items
        ],
        indent=2,
    )

    locks_summary = json.dumps(locks, indent=2) if locks else "[]"

    return f"""\
You are a narrative designer creating NPCs for a Zork-style text adventure.

## World Concept
{json.dumps(concept, indent=2)}

## Existing Rooms
{rooms_summary}

## Existing Exits
{exits_summary}

## Existing Items
{items_summary}

## Existing Locks
{locks_summary}

## Your Task — Generate NPCs and Dialogue Trees

Create NPCs that serve clear narrative and mechanical purposes.  Every NPC
must contribute: gate progress, provide a useful item, deliver critical
information, or present a meaningful interaction.  No NPCs exist as empty
decoration.

### NPC Types

1. **Quest Givers** — Provide information, tasks, or items in exchange for
   player actions.  Place on or near the critical path.

2. **Gatekeepers** — Block passage until a condition is met (e.g., a guard
   who wants a bribe or proof of authority).  These correspond to NPC-type
   locks from the locks data.  Set `is_blocking: 1`, provide the
   `blocked_exit_id` and `unblock_flag`.

3. **Lore Sources** — Exist primarily to deliver world-building through
   dialogue.  Place in optional areas as exploration rewards.

4. **Merchants / Traders** — Exchange items with the player.  Optional but
   adds depth.

5. **Hostile NPCs** — Must be dealt with through combat, stealth, or
   diplomacy.  Telegraph danger in the room description.  Hostile NPCs
   should NOT have dialogue trees — use `default_dialogue` for their
   non-conversational response (a growl, a threat, etc.).

### Dialogue Tree Design

Instead of flat topic lists, design branching dialogue trees for
conversational NPCs.

**Structure:**
- Each NPC that can converse gets a **root node** (`is_root: 1`) — the
  entry point when the player types `talk to {{npc}}`.
- Nodes contain the NPC's text.  Options are the player's numbered choices.
- Options can branch to other nodes (`next_node_id`) or end the
  conversation (`next_node_id: null`).
- Sub-nodes should offer a "go back" option (`next_node_id` pointing to
  the root) so the player can explore multiple topics in one conversation.

**Gating:**
- `required_flags` on an option — all must be true for the option to appear.
- `excluded_flags` on an option — if ANY are true, the option is hidden.
  Use this to hide options the player has already explored.
- `required_items` on an option — item IDs the player must have in
  inventory.  Creates inventory-reactive dialogue.
- `set_flags` on options and nodes — flags set when chosen/visited.

**Voice consistency**: Each NPC must have a distinct voice.  A grizzled guard
speaks differently from a nervous scholar.  Define the character's vocabulary,
rhythm, and personality, then write every line through that lens.

**No exposition dumps**: Characters never explain things to each other (or the
player) that they would already know.  Information is delivered naturally
through the character's perspective and priorities.

**Default dialogue**: The `default_dialogue` field is the fallback for NPCs
without a dialogue tree (hostile NPCs) or if the tree is somehow missing.

### CRITICAL: Use Exact IDs

You MUST use the exact `id` values from the existing data above. Do NOT
invent room IDs or exit IDs — copy them verbatim from the lists above.
If `room_id` does not exactly match one of the room IDs listed in
"Existing Rooms", the NPC will fail to insert. If `blocked_exit_id` does
not exactly match an exit ID from "Existing Exits", it will be dropped.

### NPC Categories (IMPORTANT)

Every NPC MUST have a `category` field for the interaction matrix. The
category determines how items interact with this NPC when the player types
`use {{item}} on {{npc}}`.  Use these standard categories:

- `"character"` — friendly or neutral NPC (quest givers, lore sources)
- `"hostile"` — enemy NPC (combat encounters)
- `"animal"` — non-humanoid creature
- `"merchant"` — trader NPC

### Placement Rules

- Spread NPCs across regions.  Do not cluster.
- Critical-path NPCs must be in rooms the player must pass through.
- Optional NPCs go in optional areas, rewarding exploration.
- Hostile NPCs should be telegraphed — the room description hints at danger.
- Scale: aim for approximately one NPC per 3-5 rooms.

### Output Format

Return a JSON object with three top-level arrays:

```json
{{{{
  "npcs": [
    {{{{
      "id": "snake_case_id",
      "name": "Display Name",
      "description": "1-2 sentences, shown when NPC is in room",
      "examine_description": "2-4 sentences on examination",
      "room_id": "room_id_where_npc_lives",
      "default_dialogue": "Fallback line",
      "is_blocking": 0 or 1,
      "blocked_exit_id": "exit_id or null",
      "unblock_flag": "flag_name or null",
      "hp": null or integer,
      "damage": null or integer
    }}}}
  ],
  "dialogue_nodes": [
    {{{{
      "id": "npc_root",
      "npc_id": "snake_case_npc_id",
      "content": "What the NPC says",
      "set_flags": [],
      "is_root": 1
    }}}}
  ],
  "dialogue_options": [
    {{{{
      "id": "npc_opt_topic",
      "node_id": "npc_root",
      "text": "What the player says",
      "next_node_id": "npc_topic_node",
      "required_flags": [],
      "excluded_flags": ["already_asked_topic"],
      "required_items": [],
      "set_flags": ["already_asked_topic"],
      "sort_order": 0
    }}}}
  ]
}}}}
```

All IDs must be globally unique across the entire output.
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_npcs(
    npcs: list[dict],
    nodes: list[dict],
    options: list[dict],
    context: dict,
) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []
    room_ids = {r["id"] for r in context.get("rooms", [])}

    seen_npc_ids: set[str] = set()
    seen_node_ids: set[str] = set()
    seen_option_ids: set[str] = set()

    for npc in npcs:
        nid = npc.get("id", "<missing>")

        # Unique NPC ID
        if nid in seen_npc_ids:
            errors.append(f"Duplicate NPC id: {nid}")
        seen_npc_ids.add(nid)

        # Room reference
        rid = npc.get("room_id")
        if rid and rid not in room_ids:
            errors.append(f"NPC {nid} references unknown room: {rid}")

        # Required fields
        for field in ("name", "description", "examine_description", "default_dialogue"):
            if not npc.get(field):
                errors.append(f"NPC {nid} missing required field: {field}")

        # Blocking NPC consistency
        if npc.get("is_blocking") == 1:
            if not npc.get("blocked_exit_id"):
                errors.append(
                    f"Blocking NPC {nid} has is_blocking=1 but no blocked_exit_id"
                )
            if not npc.get("unblock_flag"):
                errors.append(
                    f"Blocking NPC {nid} has is_blocking=1 but no unblock_flag"
                )

    # Validate dialogue nodes
    npc_ids = {n["id"] for n in npcs}
    for node in nodes:
        nid = node.get("id", "<missing>")
        if nid in seen_node_ids:
            errors.append(f"Duplicate dialogue node id: {nid}")
        seen_node_ids.add(nid)

        if node.get("npc_id") not in npc_ids:
            errors.append(f"Dialogue node {nid} references unknown NPC: {node.get('npc_id')}")

        if not node.get("content"):
            errors.append(f"Dialogue node {nid} has empty content")

    # Validate dialogue options
    for opt in options:
        oid = opt.get("id", "<missing>")
        if oid in seen_option_ids:
            errors.append(f"Duplicate dialogue option id: {oid}")
        seen_option_ids.add(oid)

        if opt.get("node_id") not in seen_node_ids:
            errors.append(f"Dialogue option {oid} references unknown node: {opt.get('node_id')}")

        next_id = opt.get("next_node_id")
        if next_id is not None and next_id not in seen_node_ids:
            errors.append(f"Dialogue option {oid} references unknown next_node: {next_id}")

        if not opt.get("text"):
            errors.append(f"Dialogue option {oid} has empty text")

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_npcs(
    db: GameDB,
    npcs: list[dict],
    nodes: list[dict],
    options: list[dict],
    context: dict,
) -> list[dict]:
    """Insert validated NPCs, dialogue nodes, and options into the database.

    FK references (room_id, blocked_exit_id) are checked against the
    database before insertion.  Invalid references are nullified (if
    nullable) or cause the NPC to be skipped (if NOT NULL), with a
    logged warning.

    Returns the list of NPCs that were successfully inserted.
    """
    room_ids = {r["id"] for r in context.get("rooms", [])}
    exit_ids = {e["id"] for e in context.get("exits", [])}
    inserted: list[dict] = []
    inserted_npc_ids: set[str] = set()

    for npc in npcs:
        nid = npc.get("id", "<unknown>")

        # --- Validate room_id (NOT NULL FK) ---
        rid = npc.get("room_id")
        if rid not in room_ids:
            logger.warning(
                "NPC %s references non-existent room_id %r — skipping NPC",
                nid,
                rid,
            )
            continue

        # --- Validate blocked_exit_id (nullable FK) ---
        blocked_exit = npc.get("blocked_exit_id")
        if blocked_exit is not None and blocked_exit not in exit_ids:
            logger.warning(
                "NPC %s references non-existent blocked_exit_id %r — "
                "setting to NULL",
                nid,
                blocked_exit,
            )
            npc["blocked_exit_id"] = None
            # If is_blocking was set but exit is invalid, clear blocking
            if npc.get("is_blocking") == 1:
                logger.warning(
                    "NPC %s had is_blocking=1 with invalid exit — "
                    "setting is_blocking=0",
                    nid,
                )
                npc["is_blocking"] = 0

        # Insert NPC row
        db.insert_npc(
            id=npc["id"],
            name=npc["name"],
            description=npc["description"],
            examine_description=npc["examine_description"],
            room_id=npc["room_id"],
            is_alive=1,
            is_blocking=npc.get("is_blocking", 0),
            blocked_exit_id=npc.get("blocked_exit_id"),
            unblock_flag=npc.get("unblock_flag"),
            default_dialogue=npc["default_dialogue"],
            hp=npc.get("hp"),
            damage=npc.get("damage"),
            category=npc.get("category"),
        )
        inserted.append(npc)
        inserted_npc_ids.add(npc["id"])

    # Insert dialogue nodes (only for successfully inserted NPCs)
    inserted_node_ids: set[str] = set()
    for node in nodes:
        if node.get("npc_id") not in inserted_npc_ids:
            continue
        set_flags = node.get("set_flags")
        db.insert_dialogue_node(
            id=node["id"],
            npc_id=node["npc_id"],
            content=node["content"],
            set_flags=json.dumps(set_flags) if set_flags else None,
            is_root=node.get("is_root", 0),
        )
        inserted_node_ids.add(node["id"])

    # Insert dialogue options (only for successfully inserted nodes)
    for opt in options:
        if opt.get("node_id") not in inserted_node_ids:
            continue
        # Skip options pointing to non-existent nodes
        next_id = opt.get("next_node_id")
        if next_id is not None and next_id not in inserted_node_ids:
            logger.warning(
                "Dialogue option %s references non-existent next_node %r — skipping",
                opt.get("id"),
                next_id,
            )
            continue

        required_flags = opt.get("required_flags")
        excluded_flags = opt.get("excluded_flags")
        required_items = opt.get("required_items")
        set_flags = opt.get("set_flags")

        db.insert_dialogue_option(
            id=opt["id"],
            node_id=opt["node_id"],
            text=opt["text"],
            next_node_id=opt.get("next_node_id"),
            required_flags=json.dumps(required_flags) if required_flags else None,
            excluded_flags=json.dumps(excluded_flags) if excluded_flags else None,
            required_items=json.dumps(required_items) if required_items else None,
            set_flags=json.dumps(set_flags) if set_flags else None,
            sort_order=opt.get("sort_order", 0),
        )

    return inserted


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 5: NPCs.  Returns updated context with NPC data."""

    logger.info("Pass 5: Generating NPCs...")

    prompt = _build_prompt(context)
    gen_ctx = GenerationContext(
        existing_data={},
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=32_768,
    )

    result = provider.generate_structured(prompt, NPCS_SCHEMA, gen_ctx)
    npcs: list[dict] = result.get("npcs", [])
    nodes: list[dict] = result.get("dialogue_nodes", [])
    options: list[dict] = result.get("dialogue_options", [])

    # Validate
    errors = _validate_npcs(npcs, nodes, options, context)
    if errors:
        for err in errors:
            logger.warning("NPC validation: %s", err)

    # Insert into DB (with FK validation); returns only successfully inserted
    inserted_npcs = _insert_npcs(db, npcs, nodes, options, context)

    # Build pass-specific data for downstream passes (only inserted NPCs)
    npcs_summary = [
        {
            "id": n["id"],
            "name": n["name"],
            "room_id": n["room_id"],
            "is_blocking": n.get("is_blocking", 0),
            "blocked_exit_id": n.get("blocked_exit_id"),
            "unblock_flag": n.get("unblock_flag"),
            "category": n.get("category"),
        }
        for n in inserted_npcs
    ]

    if len(inserted_npcs) < len(npcs):
        logger.warning(
            "Pass 5: %d of %d NPCs skipped due to invalid FK references",
            len(npcs) - len(inserted_npcs),
            len(npcs),
        )
    logger.info("Pass 5 complete: %d NPCs inserted.", len(inserted_npcs))
    return {"npcs": npcs_summary}
