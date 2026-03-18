"""Pass 4: Items — Populate the world with interactive objects.

Reads the world concept, rooms, exits, and locks from prior passes, then
prompts the LLM to generate items for every room.  Items fall into four
categories:

  * **Keys** — items that unlock locks (placement must respect reachability).
  * **Tools** — reusable items the player needs for puzzles and exploration.
  * **Environmental / Scenery** — non-takeable objects that furnish rooms and
    carry lore clues in their examine descriptions.
  * **Red herrings** — takeable-but-not-required items that add texture.

Every takeable item MUST include a ``room_description`` field — the prose
sentence appended dynamically to the room description at render time.  When
the item is taken or removed, the sentence disappears automatically, keeping
room text accurate.

After inserting items, the pass cross-references the locks table and updates
any key-type locks whose ``key_item_id`` was a placeholder with the real
item ID generated here.
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

ITEMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "name",
                    "description",
                    "examine_description",
                    "room_id",
                    "is_takeable",
                    "is_visible",
                    "category",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Display name, lowercase as it appears in prose.",
                    },
                    "description": {
                        "type": "string",
                        "description": "One-sentence short description for listings.",
                    },
                    "examine_description": {
                        "type": "string",
                        "description": "2-4 sentence detailed description with embedded clues.",
                    },
                    "room_id": {
                        "type": ["string", "null"],
                        "description": "Room ID where the item starts, or null if spawned later / in inventory.",
                    },
                    "is_takeable": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = player can pick up, 0 = scenery.",
                    },
                    "is_visible": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = visible at game start, 0 = hidden until spawned.",
                    },
                    "is_consumed_on_use": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = destroyed after use, 0 = persists.",
                    },
                    "room_description": {
                        "type": ["string", "null"],
                        "description": (
                            "Prose sentence appended to the room description at render "
                            "time. REQUIRED for every takeable item. Example: "
                            "'A rusty iron key hangs from a hook beside the window.'"
                        ),
                    },
                    "take_message": {
                        "type": ["string", "null"],
                        "description": "Custom message when the player takes the item.",
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "key",
                            "tool",
                            "weapon",
                            "treasure",
                            "document",
                            "scenery",
                            "consumable",
                            "container",
                        ],
                        "description": "Item category for engine classification.",
                    },
                    "container_id": {
                        "type": ["string", "null"],
                        "description": (
                            "If this item is inside a container, the ID of the "
                            "container item. NULL if the item is in a room or "
                            "inventory. Mutually exclusive with room_id."
                        ),
                    },
                    "is_container": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "1 = this item can hold other items, 0 = normal item.",
                    },
                    "is_open": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "For containers: 1 = open, 0 = closed. Set 1 for lid-less containers.",
                    },
                    "has_lid": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "For containers: 1 = can be opened/closed, 0 = always accessible (shelf, pile).",
                    },
                    "is_locked": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "For containers: 1 = locked, needs unlocking first. 0 = not locked.",
                    },
                    "lock_message": {
                        "type": ["string", "null"],
                        "description": "For locked containers: message shown when player tries to open/search while locked.",
                    },
                    "open_message": {
                        "type": ["string", "null"],
                        "description": "For containers: message shown when the container is opened.",
                    },
                    "search_message": {
                        "type": ["string", "null"],
                        "description": "For containers: message shown before listing contents when searched.",
                    },
                    "read_description": {
                        "type": ["string", "null"],
                        "description": (
                            "For readable items (documents, notes, signs): the text "
                            "content shown when the player types 'read {item}'. Falls "
                            "back to examine_description if not set."
                        ),
                    },
                    "key_item_id": {
                        "type": ["string", "null"],
                        "description": (
                            "For locked containers: the ID of the item that unlocks "
                            "this container. The engine auto-unlocks when the player "
                            "uses this item on the container."
                        ),
                    },
                    "consume_key": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": (
                            "For locked containers with key_item_id: 1 = key is "
                            "consumed on use, 0 = key is reusable."
                        ),
                    },
                    "unlock_message": {
                        "type": ["string", "null"],
                        "description": (
                            "For locked containers with key_item_id: message shown "
                            "when the container is unlocked."
                        ),
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
    """Construct the LLM prompt for item generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    locks = context.get("locks", [])
    lock_key_mapping = context.get("lock_key_mapping", {})

    rooms_summary = json.dumps(
        [
            {
                "id": r["id"],
                "name": r["name"],
                "region": r["region"],
                "is_start": r.get("is_start", 0),
                "description": r["description"],
            }
            for r in rooms
        ],
        indent=2,
    )

    locks_summary = json.dumps(locks, indent=2) if locks else "[]"

    # Build required-keys section from the lock-key mapping
    required_keys_lines = ""
    if lock_key_mapping:
        required_keys_lines = "\n## Required Key Items (from Locks pass)\n\n"
        required_keys_lines += (
            "The following key items MUST be created with EXACTLY these IDs "
            "and placed in the specified rooms.  These are non-negotiable — "
            "the lock system depends on them.\n\n"
        )
        for lock_id, mapping in lock_key_mapping.items():
            required_keys_lines += (
                f"- Lock `{lock_id}` requires key item "
                f"`{mapping['key_item_id']}` placed in room "
                f"`{mapping.get('key_location_room_id', 'TBD')}`\n"
            )
        required_keys_lines += "\n"

    return f"""\
You are a game content designer for a Zork-style text adventure engine.

## World Concept
{json.dumps(concept, indent=2)}

## Existing Rooms
{rooms_summary}

## Existing Locks (gates that block exits)
{locks_summary}
{required_keys_lines}

## Your Task — Generate Items

Create items for this game world.  Every item serves a purpose.

### Environmental Coherence (IMPORTANT)

READ the full room descriptions above carefully before generating items.
Items must feel like they BELONG in the rooms they are placed in.

- **Match the environment.** A library gets books, scrolls, and reading lamps
  — not laser guns.  A kitchen gets utensils and food — not enchanted amulets.
  Only break environmental expectations when the world concept explicitly
  supports it (e.g., a sci-fi kitchen might have a nutrient synthesizer).
- **Match the tone.** The `room_description` field is prose that gets appended
  to the room's existing description at render time.  It must read as a
  natural continuation — same voice, same register, same level of detail.
  If the room description is atmospheric and literary, do NOT write
  "There is a key here."  Instead write something like "A tarnished brass
  key rests on the windowsill, half-hidden by the curtain."
- **Anchor items to the room's features.** Reference specific details from
  the room description when placing items.  If the room mentions a desk,
  place an item on the desk.  If the room mentions a fireplace, place an
  item on the mantle.  This makes the world feel cohesive.
- **Use scenery items to deepen rooms.** Every room should have at least one
  scenery item (`is_takeable: 0`, `category: "scenery"`) representing an
  environmental detail players can EXAMINE but not take — a mirror, a
  painting, a control panel, a fountain, a carved relief.  These give
  players something to interact with beyond the critical path and reward
  curiosity with lore or atmosphere.

### Item Categories

1. **Keys** (`category: "key"`)
   - For every lock with `lock_type: "key"`, create the key item whose `id`
     matches the lock's `key_item_id`.
   - The key MUST be placed in a room that is reachable BEFORE the locked
     exit.  Check the room graph: the player must be able to reach the key
     room without passing through the lock the key opens.
   - Keys are `is_takeable: 1` and usually `is_consumed_on_use: 1`.

2. **Tools** (`category: "tool"`)
   - Reusable items the player needs for puzzles: a lantern, a crowbar, a
     translation device, a rope, etc.
   - Place tools in rooms the player visits before the rooms where the tools
     are needed.
   - `is_consumed_on_use: 0`.

3. **Environmental / Scenery** (`category: "scenery"`)
   - Non-takeable objects that furnish rooms: a control panel, a painting,
     a bookshelf, a fountain, a statue.
   - `is_takeable: 0`, `is_consumed_on_use: 0`.
   - Their `examine_description` should embed clues, lore hints, or
     atmospheric detail.
   - Every room should have at least one scenery item.

4. **Documents** (`category: "document"`)
   - Readable items: books, scrolls, notes, inscriptions, datapads.
   - Usually `is_takeable: 1`.  Their `examine_description` contains the
     readable text — this is where lore lives.

5. **Treasure / Red Herrings** (`category: "treasure"`)
   - Items that add texture but are not required for progression.
   - Give them interesting descriptions.  They may contribute to score.

6. **Weapons** (`category: "weapon"`) — only if the game concept involves combat.

7. **Consumables** (`category: "consumable"`) — potions, food, one-time-use
   items.  `is_consumed_on_use: 1`.

### Readable Items (read_description)

Items that can be "read" (documents, notes, inscriptions, signs) should have
a `read_description` field. When the player types "read {{item}}", the engine
shows `read_description` instead of `examine_description`. If not set, the
engine falls back to `examine_description`.

Use `read_description` for the readable content (what the text says) and
`examine_description` for the physical description (what the item looks like).

### Locked Container Keys (key_item_id)

Locked containers (`is_container: 1`, `is_locked: 1`) can specify which item
unlocks them via the `key_item_id` field. When the player types
"use {{key}} on {{container}}" and the key matches, the engine automatically
unlocks and opens the container, showing `unlock_message`.

Fields for locked containers with keys:
- `key_item_id`: The ID of the item that unlocks this container.
- `consume_key`: 1 if the key is consumed on use, 0 if reusable.
- `unlock_message`: Message shown when the container is unlocked.

This eliminates the need for DSL commands for simple key-on-container
interactions.

### CRITICAL: Use Exact Room IDs

You MUST use the exact `id` values from the rooms listed above. Do NOT
invent room IDs — copy them verbatim. If `room_id` does not exactly match
one of the room IDs listed in "Existing Rooms", the item will be orphaned.

### Critical Rules

- **room_description field**: Every takeable item (`is_takeable: 1`) MUST have
  a `room_description` — a prose sentence describing how the item appears in
  its room.  This sentence is appended dynamically to the room description.
  When the item is taken, the sentence disappears.  Example:
  `"A rusty iron key hangs from a hook beside the window."`
  Scenery items may also use this field, or they may be described in the base
  room description since they never move.

- **Item density**: Aim for 1.5–2.5 items per room on average (including
  scenery).  Every room should have at least one item.

- **Start room**: The start room should have at least one takeable item so the
  player learns they can pick things up.

- **Examine descriptions embed clues**: The `examine_description` is the most
  important field.  This is where puzzle clues, lore hooks, and item
  relationships are communicated.  Be specific and evocative.  Avoid generic
  flavor text that tells the player nothing.

- **No duplicate IDs**.  Every `id` must be unique across all items.

- **IDs use snake_case**: `rusty_key`, `torn_page`, `old_lantern`.

- **Hidden items**: Items that should not appear until spawned by a command
  effect (e.g., a reward item) should have `is_visible: 0` and
  `room_id: null`.  They exist in the database but are not in the world yet.

### Container Items

Some items are containers -- objects that hold other items inside them. Chests,
drawers, bags, desks, gloveboxes, shelves, piles of debris.

When creating a container:
- Set `is_container: 1`
- Set `has_lid: 1` if it can be meaningfully opened/closed (a chest, a drawer,
  a glovebox). Set `has_lid: 0` if it's always accessible (a shelf, a pile,
  "under the seat").
- Set `is_open: 0` for lidded containers (player must open or search them).
  Set `is_open: 1` for lid-less containers.
- Set `is_locked: 1` if the container should require a key or puzzle to open.
  Provide a `lock_message`. Also create a DSL command (in Pass 7) that
  unlocks it.
- Set `is_takeable: 0` for most containers (they are furniture/fixtures).
  Set `is_takeable: 1` only for portable containers like bags or satchels.
- Write the `examine_description` to hint that the container can be searched:
  "You could look inside" or "It might be worth searching."
- Container items have `room_id` set to the room they're in, like any item.
- Containers MUST have a `room_description` field — a prose sentence
  describing how the container appears in the room.  Example:
  `"A battered wooden chest sits in the corner, its iron hinges rusted."`
  This is how the engine dynamically shows the container in room text.
- Containers use `category: "container"` or `category: "scenery"`.

When creating items inside a container:
- Set `container_id` to the container item's ID.
- Set `room_id` to null (the item is inside the container, not in the room).
- These items are hidden from the player until the container is opened and
  searched.
- Items inside containers should still have full descriptions and
  examine_descriptions.
- `room_description` is NOT needed for items inside containers (they are never
  displayed in the room text).

Container placement guidelines:
- Use containers to hide items that the player should discover through active
  exploration, not passively by entering a room.
- Key items (items needed for puzzle solutions or lock-opening) MAY be inside
  containers, but the container must be clearly visible and obviously
  searchable. Never hide a critical-path key inside a locked container that
  requires another critical-path key.
- Containers add room-level depth. A room with 2-3 visible items and 1-2
  containers (each holding 1-3 items) feels richer than a room with 5-6
  visible items.
- Locked containers are mini-puzzles. Use them sparingly -- one or two per
  game, not one per room.

**Nesting prohibition:**
A container MUST NOT be placed inside another container. `container_id` must
never reference an item where `is_container = 1`. This is a hard rule.

### Output Format

Return a JSON object with a single key `"items"` containing an array of item
objects.  Each item object must have these fields:

```json
{{
  "id": "string (snake_case, unique)",
  "name": "string (lowercase display name)",
  "description": "string (1 sentence, short)",
  "examine_description": "string (2-4 sentences, detailed, clue-bearing)",
  "room_id": "string (room ID) or null",
  "container_id": "string (container item ID) or null",
  "is_takeable": 0 or 1,
  "is_visible": 0 or 1,
  "is_consumed_on_use": 0 or 1,
  "is_container": 0 or 1,
  "is_open": 0 or 1,
  "has_lid": 0 or 1,
  "is_locked": 0 or 1,
  "lock_message": "string or null",
  "open_message": "string or null",
  "search_message": "string or null",
  "room_description": "string or null",
  "take_message": "string or null",
  "category": "key|tool|weapon|treasure|document|scenery|consumable|container",
  "read_description": "string or null",
  "key_item_id": "string or null",
  "consume_key": 0 or 1,
  "unlock_message": "string or null"
}}
```
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_items(items: list[dict], context: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []
    room_ids = {r["id"] for r in context.get("rooms", [])}
    seen_ids: set[str] = set()

    for item in items:
        iid = item.get("id", "<missing>")

        # Unique ID
        if iid in seen_ids:
            errors.append(f"Duplicate item id: {iid}")
        seen_ids.add(iid)

        # Room reference
        rid = item.get("room_id")
        if rid is not None and rid not in room_ids:
            errors.append(f"Item {iid} references unknown room: {rid}")

        # Takeable items need room_description
        if item.get("is_takeable", 0) == 1 and not item.get("room_description"):
            if item.get("is_visible", 1) == 1 and rid is not None:
                errors.append(
                    f"Takeable visible item {iid} is missing room_description"
                )

        # Required fields
        for field in ("name", "description", "examine_description", "category"):
            if not item.get(field):
                errors.append(f"Item {iid} missing required field: {field}")

    # Check lock keys exist
    locks = context.get("locks", [])
    for lock in locks:
        if lock.get("lock_type") == "key":
            key_id = lock.get("key_item_id")
            if key_id and key_id not in seen_ids:
                errors.append(
                    f"Lock {lock['id']} requires key item {key_id} "
                    f"but no item with that id was generated"
                )

    # --- Container integrity checks ---
    container_ids = {
        i["id"] for i in items if i.get("is_container")
    }
    items_by_id = {i["id"]: i for i in items}

    for item in items:
        iid = item.get("id", "<missing>")
        cid = item.get("container_id")
        rid = item.get("room_id")

        if cid is not None:
            # Item inside a container must reference a valid container
            if cid not in container_ids:
                errors.append(
                    f"Item {iid} has container_id={cid!r} which is not "
                    f"a container (is_container=1)"
                )
            # No nesting: a container must not be inside another container
            if item.get("is_container"):
                errors.append(
                    f"Container {iid} has container_id set (no nesting allowed)"
                )
            # Mutually exclusive: room_id and container_id
            if rid is not None:
                errors.append(
                    f"Item {iid} has both room_id and container_id set "
                    f"(mutually exclusive)"
                )

        # Locked containers must have a lock_message
        if item.get("is_container") and item.get("is_locked"):
            if not item.get("lock_message"):
                errors.append(
                    f"Locked container {iid} is missing lock_message"
                )

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_items(db: GameDB, items: list[dict], context: dict) -> list[dict]:
    """Insert validated items into the database.

    FK references (room_id) are checked against known room IDs before
    insertion.  Invalid room references are set to NULL with a warning.

    Returns the list of successfully inserted items.
    """
    room_ids = {r["id"] for r in context.get("rooms", [])}
    inserted: list[dict] = []

    for item in items:
        iid = item.get("id", "<unknown>")

        # --- Validate room_id (nullable FK) ---
        rid = item.get("room_id")
        if rid is not None and rid not in room_ids:
            logger.warning(
                "Item %s references non-existent room_id %r — "
                "setting to NULL (item will be in limbo)",
                iid,
                rid,
            )
            item["room_id"] = None

        db.insert_item(
            id=item["id"],
            name=item["name"],
            description=item["description"],
            examine_description=item["examine_description"],
            room_id=item.get("room_id"),
            container_id=item.get("container_id"),
            is_takeable=item.get("is_takeable", 1),
            is_visible=item.get("is_visible", 1),
            is_consumed_on_use=item.get("is_consumed_on_use", 0),
            is_container=item.get("is_container", 0),
            is_open=item.get("is_open", 0),
            has_lid=item.get("has_lid", 1),
            is_locked=item.get("is_locked", 0),
            lock_message=item.get("lock_message"),
            open_message=item.get("open_message"),
            search_message=item.get("search_message"),
            take_message=item.get("take_message"),
            drop_message=item.get("drop_message"),
            weight=item.get("weight", 1),
            category=item.get("category"),
            room_description=item.get("room_description"),
            read_description=item.get("read_description"),
            key_item_id=item.get("key_item_id"),
            consume_key=item.get("consume_key", 0),
            unlock_message=item.get("unlock_message"),
        )
        inserted.append(item)

    return inserted


def _update_lock_key_references(db: GameDB, context: dict) -> None:
    """Backfill lock rows with actual key_item_id values.

    The Locks pass (Pass 3) inserts locks with ``key_item_id = NULL`` to avoid
    FK violations (items do not exist yet).  Now that we have inserted the key
    items, we update each lock row to reference the real item.

    Uses the ``lock_key_mapping`` dict from context, which maps
    lock_id -> {"key_item_id": str, "key_location_room_id": str}.
    """
    lock_key_mapping = context.get("lock_key_mapping", {})
    for lock_id, mapping in lock_key_mapping.items():
        key_item_id = mapping.get("key_item_id")
        if not key_item_id:
            continue

        # Verify the item exists in the DB
        item = db.get_item(key_item_id)
        if item is None:
            logger.warning(
                "Lock %s requires key_item_id %s but item not found in DB",
                lock_id,
                key_item_id,
            )
            continue

        # Update the lock row to reference the key item
        db._mutate(
            "UPDATE locks SET key_item_id = ? WHERE id = ?",
            (key_item_id, lock_id),
        )
        logger.info(
            "Backfilled lock %s with key_item_id=%s",
            lock_id,
            key_item_id,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 4: Items.  Returns updated context with item data."""

    logger.info("Pass 4: Generating items...")

    prompt = _build_prompt(context)
    gen_ctx = GenerationContext(
        existing_data={},
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=32_768,
    )

    result = provider.generate_structured(prompt, ITEMS_SCHEMA, gen_ctx)
    items: list[dict] = result.get("items", [])

    # Validate
    errors = _validate_items(items, context)
    if errors:
        for err in errors:
            logger.warning("Item validation: %s", err)

    # Insert into DB (with FK validation)
    inserted_items = _insert_items(db, items, context)

    # Cross-reference locks
    _update_lock_key_references(db, context)

    # Build pass-specific data for downstream passes (only inserted items)
    items_summary = [
        {
            "id": i["id"],
            "name": i["name"],
            "room_id": i.get("room_id"),
            "container_id": i.get("container_id"),
            "is_takeable": i.get("is_takeable", 1),
            "is_visible": i.get("is_visible", 1),
            "is_container": i.get("is_container", 0),
            "is_locked": i.get("is_locked", 0),
            "category": i.get("category"),
            "description": i["description"],
        }
        for i in inserted_items
    ]

    logger.info("Pass 4 complete: %d items generated.", len(inserted_items))
    return {"items": items_summary}
