"""Pass 2: Room Graph — generates rooms and exits from the world concept.

This is the spatial backbone of the game. Every room, exit, region, and
the critical path emerge from this pass. The LLM is guided by level
design principles: layout flow types, hub landmarks, meaningful dead
ends, region identity, and backtracking management.
"""

from __future__ import annotations

import json
from collections import deque

from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, GenerationContext

# ---------------------------------------------------------------------------
# JSON schema the LLM must conform to
# ---------------------------------------------------------------------------

ROOMS_SCHEMA: dict = {
    "type": "object",
    "required": ["rooms", "exits"],
    "properties": {
        "rooms": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "name",
                    "description",
                    "short_description",
                    "region",
                    "is_start",
                    "is_dark",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[a-z][a-z0-9_]*$",
                        "description": (
                            "Unique snake_case identifier. "
                            "E.g. 'docking_bay', 'dark_corridor'."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Human-readable display name.",
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "Full prose description (3-5 sentences). Shown on "
                            "first visit and when the player types 'look'. Must "
                            "set atmosphere and describe permanent architectural "
                            "or environmental features. NEVER mention specific "
                            "interactable objects (items, tools, keys, weapons) — "
                            "those are added dynamically by the item system."
                        ),
                    },
                    "short_description": {
                        "type": "string",
                        "description": (
                            "Abbreviated description (1-2 sentences) shown on "
                            "return visits."
                        ),
                    },
                    "first_visit_text": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional one-time text shown only on the very "
                            "first visit. Use for dramatic moments."
                        ),
                    },
                    "region": {
                        "type": "string",
                        "description": (
                            "snake_case region tag grouping rooms thematically. "
                            "E.g. 'entry_module', 'research_wing'."
                        ),
                    },
                    "is_start": {
                        "type": "boolean",
                        "description": "True for exactly ONE room: the starting room.",
                    },
                    "is_dark": {
                        "type": "boolean",
                        "description": (
                            "True if the room requires a light source to see."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
        "exits": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "from_room_id",
                    "to_room_id",
                    "direction",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[a-z][a-z0-9_]*$",
                        "description": (
                            "Unique snake_case exit ID. Convention: "
                            "'<from_room>_to_<to_room>' or similar."
                        ),
                    },
                    "from_room_id": {
                        "type": "string",
                        "description": "Room ID the exit leads FROM.",
                    },
                    "to_room_id": {
                        "type": "string",
                        "description": "Room ID the exit leads TO.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": [
                            "north", "south", "east", "west",
                            "up", "down",
                        ],
                        "description": (
                            "Direction label. MUST be one of: north, south, "
                            "east, west, up, down. No other values allowed."
                        ),
                    },
                    "description": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional prose fragment shown when the player "
                            "looks at available exits."
                        ),
                    },
                    "is_hidden": {
                        "type": "boolean",
                        "description": (
                            "If true, this exit is not shown to the player "
                            "until revealed by a game event."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Layout type recommendations per scale and theme keywords
# ---------------------------------------------------------------------------

_LAYOUT_GUIDANCE = {
    "small": "hub-and-spoke or linear-with-branches",
    "medium": "hub-and-spoke with branches, or multi-hub",
    "large": "multi-hub with region corridors",
}

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT = """\
You are a level designer for a text adventure game engine called AnyZork.

You are executing **Pass 2: Room Graph** — the spatial backbone of the game.

## World Concept (from Pass 1)

```json
{concept_json}
```

## Your Task

Generate exactly {room_count_target} rooms organized into {region_count_target} \
region(s), connected by exits. This room graph IS the game's spatial experience.

## Layout Flow

Use a **{layout_type}** layout. Here is what that means:

- **Hub-and-spoke**: A central room connects to multiple branches. Good for \
stations, mansions, dungeons. The hub is a landmark.
- **Linear with branches**: A main corridor with optional side rooms. Strong \
pacing control.
- **Multi-hub**: Multiple hub rooms connected by corridors, each anchoring \
a region. Best for medium-to-large worlds.

## Critical Design Rules

1. **Critical path must exist.** There must be a traversable sequence of rooms \
from the start room to a logical endpoint. This is the spine of the game.

2. **Optional areas branch off the critical path.** Rewards, lore, and bonus \
content live here. The player can skip them and still finish.

3. **Regions group rooms thematically.** Each region has a distinct atmosphere \
conveyed through room descriptions. Region transitions must be noticeable — \
the description should signal "you are somewhere new."

4. **Dead ends MUST contain value.** Every dead-end room must justify its \
existence. A dead end with nothing interesting is a waste of the player's time. \
Do NOT create empty dead ends.

5. **Hub rooms are landmarks.** The player will pass through hubs repeatedly. \
Hub descriptions must be vivid, brief, and unique — "the room with the broken \
fountain," "the central atrium with the skylight."

6. **Room names must be distinctive.** "Corridor" and "Another Corridor" are a \
navigation disaster. Give every room a unique, memorable name that helps the \
player build a mental map.

7. **Backtracking should be short.** If the player must return to an earlier \
area, keep the route to 3 rooms or fewer. Place shortcut exits when possible.

## Room Description Guidelines

Room descriptions are the PERMANENT backdrop. Interactable items (keys, tools, \
weapons, collectibles) are managed by a separate item system that dynamically \
appends item-presence text — do NOT bake items into room descriptions.

Every room description follows this layered structure:
1. **Atmosphere** (first sentence): sensory tone — what does the player see, \
hear, smell, feel?
2. **Landmarks** (1-2 sentences): permanent architectural or environmental \
features that make this room distinct. Walls, floors, windows, built-in \
furniture, natural formations, structural damage. Example: "A cracked marble \
fountain dominates the courtyard." NOT: "A rusty key sits on the desk."
3. **Clue embedding** (subtle, environmental): scratches, stains, temperature \
changes, sounds from adjacent rooms — details baked into the space itself. \
NOT loose objects the player might try to pick up.

**NEVER mention specific interactable objects** in room descriptions. No items, \
tools, weapons, keys, notes, books, or anything a player might try to pick up, \
examine, or use. If a player reads it in the room description and tries to \
interact with it, the engine will say "You don't see that here." because the \
item system manages object visibility separately.

## Vocabulary

Use these words and naming conventions throughout: {vocabulary}

## Exit Conventions

- You MUST only use these directions: north, south, east, west, up, down. \
No other direction names are allowed — the engine will not recognise \
"enter", "out", "climb", "northeast", etc.
- **Every exit MUST have a reverse exit** unless it is intentionally one-way. \
For every exit A->B direction "north", create a matching exit B->A direction \
"south". One-way exits must be rare and the room description must telegraph \
the one-way nature ("a steep chute", "a door that locks behind you").
- Exit IDs: use the convention `<from_room>_<direction>` \
(e.g. "docking_bay_north", "corridor_a1_south").

## Output Requirements

- Exactly {room_count_target} rooms (+/- 2 is acceptable).
- Exactly {region_count_target} region(s).
- Exactly ONE room with `is_start: true`.
- ALL rooms must be reachable from the start room.
- Every pair of connected rooms has exits in BOTH directions (unless \
intentionally one-way, which should be rare).
- Room IDs are snake_case, unique, and descriptive.
- Exit IDs are snake_case and unique.
- Hidden exits (`is_hidden: true`) are used sparingly for secret passages \
that game events reveal later.

## Output Format

Return a single JSON object matching this schema:

```json
{schema_json}
```

Produce ONLY the JSON object. No commentary, no markdown fences.
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class RoomGraphValidationError(ValueError):
    """Raised when the room graph fails structural validation."""


_REVERSE_DIRECTIONS: dict[str, str] = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "down",
    "down": "up",
}


def _validate(data: dict, concept: dict) -> None:
    """Validate the room graph for structural integrity."""
    errors: list[str] = []

    rooms = data.get("rooms", [])
    exits_ = data.get("exits", [])

    # --- Room checks ---
    room_ids = {r["id"] for r in rooms}

    if not rooms:
        errors.append("No rooms generated.")

    # Duplicate room IDs
    seen_room_ids: set[str] = set()
    for r in rooms:
        if r["id"] in seen_room_ids:
            errors.append(f"Duplicate room ID: '{r['id']}'.")
        seen_room_ids.add(r["id"])

    # Exactly one start room
    start_rooms = [r for r in rooms if r.get("is_start")]
    if len(start_rooms) == 0:
        errors.append("No start room defined (is_start: true).")
    elif len(start_rooms) > 1:
        errors.append(
            f"Multiple start rooms: {[r['id'] for r in start_rooms]}."
        )

    # Room count within range
    scale = concept.get("scale", "medium")
    target = concept.get("room_count_target", 20)
    if abs(len(rooms) - target) > max(5, target // 3):
        errors.append(
            f"Room count ({len(rooms)}) is too far from "
            f"target ({target})."
        )

    # Region count
    regions = {r["region"] for r in rooms}
    region_target = concept.get("region_count_target", 2)
    if abs(len(regions) - region_target) > region_target:
        # Only fail if the region count is wildly off (more than double or zero)
        errors.append(
            f"Region count ({len(regions)}) differs significantly from "
            f"target ({region_target})."
        )

    # --- Exit checks ---
    exit_ids: set[str] = set()
    for ex in exits_:
        if ex["id"] in exit_ids:
            errors.append(f"Duplicate exit ID: '{ex['id']}'.")
        exit_ids.add(ex["id"])

        if ex["from_room_id"] not in room_ids:
            errors.append(
                f"Exit '{ex['id']}' references unknown from_room_id "
                f"'{ex['from_room_id']}'."
            )
        if ex["to_room_id"] not in room_ids:
            errors.append(
                f"Exit '{ex['id']}' references unknown to_room_id "
                f"'{ex['to_room_id']}'."
            )

    # --- Reachability (BFS from start) ---
    if start_rooms and not errors:
        adjacency: dict[str, set[str]] = {rid: set() for rid in room_ids}
        for ex in exits_:
            if ex["from_room_id"] in adjacency:
                adjacency[ex["from_room_id"]].add(ex["to_room_id"])

        start_id = start_rooms[0]["id"]
        visited: set[str] = set()
        queue: deque[str] = deque([start_id])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)

        unreachable = room_ids - visited
        if unreachable:
            errors.append(
                f"Rooms not reachable from start: {sorted(unreachable)}."
            )

    # --- Reverse exit check (advisory — logged but not blocking) ---
    # Build a set of (from, to, direction) tuples
    exit_set: set[tuple[str, str]] = set()
    for ex in exits_:
        exit_set.add((ex["from_room_id"], ex["to_room_id"]))

    missing_reverse: list[str] = []
    for ex in exits_:
        if ex.get("is_hidden"):
            continue  # hidden exits do not require reverse
        reverse_pair = (ex["to_room_id"], ex["from_room_id"])
        if reverse_pair not in exit_set:
            missing_reverse.append(
                f"Exit '{ex['id']}' ({ex['from_room_id']} -> "
                f"{ex['to_room_id']}) has no reverse exit."
            )

    # Missing reverse exits are warnings, not hard errors — one-way
    # exits may be intentional.  But if >25% of exits lack reverses,
    # flag it as an error.
    if missing_reverse:
        non_hidden_exits = [e for e in exits_ if not e.get("is_hidden")]
        ratio = len(missing_reverse) / max(len(non_hidden_exits), 1)
        if ratio > 0.25:
            errors.append(
                f"{len(missing_reverse)} exits lack reverse exits "
                f"({ratio:.0%} of non-hidden exits). This is too many "
                f"one-way passages. Details: {missing_reverse[:5]}"
            )

    if errors:
        raise RoomGraphValidationError(
            "Room graph validation failed:\n  - " + "\n  - ".join(errors)
        )


# ---------------------------------------------------------------------------
# Pass entry point
# ---------------------------------------------------------------------------

def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 2: Room Graph.

    Reads the world concept from ``context["concept"]``, asks the LLM to
    generate rooms and exits, validates the graph, inserts everything into
    the database, and returns the updated context.

    Args:
        db: The GameDB instance.
        provider: The LLM provider to call.
        context: Pipeline context dict.  Must contain ``"concept"``.

    Returns:
        Updated context with ``"room_ids"``, ``"rooms"``, ``"exits"``,
        ``"start_room_id"``, and ``"regions"`` keys added.

    Raises:
        RoomGraphValidationError: If the generated graph fails validation.
    """
    concept: dict = context["concept"]

    # Determine recommended layout type
    scale = concept.get("scale", "medium")
    layout_type = _LAYOUT_GUIDANCE.get(scale, "hub-and-spoke")

    # Build the prompt
    prompt = _PROMPT.format(
        concept_json=json.dumps(concept, indent=2),
        room_count_target=concept["room_count_target"],
        region_count_target=concept["region_count_target"],
        layout_type=layout_type,
        vocabulary=", ".join(concept.get("vocabulary_hints", [])),
        schema_json=json.dumps(ROOMS_SCHEMA, indent=2),
    )

    # Build generation context
    gen_ctx = GenerationContext(
        existing_data={"concept": concept},
        seed=context.get("seed"),
        temperature=0.7,
        max_tokens=32_768,
    )

    # Call the LLM
    data: dict = provider.generate_structured(
        prompt=prompt,
        schema=ROOMS_SCHEMA,
        context=gen_ctx,
    )

    # Validate
    _validate(data, concept)

    # --- Insert rooms into DB ---
    rooms = data["rooms"]
    start_room_id: str | None = None

    for room in rooms:
        db.insert_room(
            id=room["id"],
            name=room["name"],
            description=room["description"],
            short_description=room["short_description"],
            first_visit_text=room.get("first_visit_text"),
            region=room["region"],
            is_dark=int(room.get("is_dark", False)),
            is_start=int(room.get("is_start", False)),
        )
        if room.get("is_start"):
            start_room_id = room["id"]

    # --- Insert exits into DB ---
    exits_ = data["exits"]

    for ex in exits_:
        db.insert_exit(
            id=ex["id"],
            from_room_id=ex["from_room_id"],
            to_room_id=ex["to_room_id"],
            direction=ex["direction"],
            description=ex.get("description"),
            is_hidden=int(ex.get("is_hidden", False)),
        )

    # Update metadata counts
    regions = sorted({r["region"] for r in rooms})
    db.set_meta("room_count", len(rooms))
    db.set_meta("region_count", len(regions))

    # Initialize the player at the start room
    if start_room_id:
        db.init_player(start_room_id)

    # --- Return pass-specific data ---
    return {
        "rooms": rooms,
        "room_ids": [r["id"] for r in rooms],
        "exits": exits_,
        "start_room_id": start_room_id,
        "regions": regions,
    }
