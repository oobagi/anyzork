"""Pass 8: Lore — Layer discoverable narrative content across three tiers.

Reads everything from prior passes, then prompts the LLM to generate lore
entries that build the world's story, history, and atmosphere.

Lore exists at three tiers so that different player types all find something
rewarding:

  * **Surface** (Tier 1) — Seen by every player on the critical path.
    Embedded in room descriptions, obvious item examinations, and mandatory
    NPC dialogue.  Establishes atmosphere and basic world-building.
    Score value: 0.

  * **Engaged** (Tier 2) — Found by players who examine non-obvious items,
    explore optional rooms, and ask NPCs follow-up questions.  Rewards
    curiosity with deeper world-building.
    Score value: 2-5 points.

  * **Deep** (Tier 3) — For lore hunters.  Requires connecting information
    across multiple sources, solving optional puzzles, or finding well-hidden
    secrets.  The richest narrative payoff.
    Score value: 10-20 points.

Lore is always optional — the critical path must be comprehensible without
any Tier 2 or Tier 3 content.  But lore must be consistent: names, dates,
events, and causality never contradict across fragments.
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

LORE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["lore"],
    "properties": {
        "lore": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "tier",
                    "title",
                    "content",
                    "delivery_method",
                    "score_value",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique snake_case identifier.",
                    },
                    "tier": {
                        "type": "string",
                        "enum": ["surface", "engaged", "deep"],
                        "description": "Lore tier: surface, engaged, or deep.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Internal title for organization.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The lore text the player reads.",
                    },
                    "delivery_method": {
                        "type": "string",
                        "enum": [
                            "examine",
                            "read",
                            "talk",
                            "automatic",
                            "room_description",
                            "inscription",
                            "book",
                            "puzzle_reward",
                            "item_description",
                            "dialogue",
                        ],
                        "description": "How the player encounters this lore.",
                    },
                    "location_id": {
                        "type": ["string", "null"],
                        "description": "Room ID where this lore is found, or null.",
                    },
                    "item_id": {
                        "type": ["string", "null"],
                        "description": "Item this lore is attached to, or null.",
                    },
                    "npc_id": {
                        "type": ["string", "null"],
                        "description": "NPC who delivers this lore, or null.",
                    },
                    "required_flags": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": (
                            "Flags that must be set for this lore to be "
                            "accessible. null = always available."
                        ),
                    },
                    "score_value": {
                        "type": "integer",
                        "description": (
                            "Points for discovery. Surface = 0, "
                            "Engaged = 2-5, Deep = 10-20."
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
    """Construct the LLM prompt for lore generation."""

    concept = context.get("concept", {})
    rooms = context.get("rooms", [])
    items = context.get("items", [])
    npcs = context.get("npcs", [])
    puzzles = context.get("puzzles", [])
    flags = context.get("flags", [])

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

    items_summary = json.dumps(
        [
            {
                "id": i["id"],
                "name": i["name"],
                "room_id": i.get("room_id"),
                "category": i.get("category"),
                "is_takeable": i.get("is_takeable", 1),
            }
            for i in items
        ],
        indent=2,
    )

    npcs_summary = json.dumps(
        [
            {
                "id": n["id"],
                "name": n["name"],
                "room_id": n["room_id"],
            }
            for n in npcs
        ],
        indent=2,
    )

    puzzles_summary = json.dumps(
        [
            {
                "id": p["id"],
                "name": p["name"],
                "room_id": p["room_id"],
            }
            for p in puzzles
        ],
        indent=2,
    ) if puzzles else "[]"

    flags_summary = json.dumps(
        [{"id": f["id"], "description": f.get("description", "")} for f in flags],
        indent=2,
    ) if flags else "[]"

    # Collect regions
    regions = sorted({r["region"] for r in rooms})
    critical_path_rooms = [r for r in rooms if r.get("is_start", 0)]

    return f"""\
You are a narrative designer creating lore entries for a Zork-style text
adventure.  Your lore will be layered across three tiers so that every
type of player finds rewarding content.

## World Concept
{json.dumps(concept, indent=2)}

## Regions
{json.dumps(regions)}

## Rooms
{rooms_summary}

## Items
{items_summary}

## NPCs
{npcs_summary}

## Puzzles
{puzzles_summary}

## Existing Flags
{flags_summary}

## Your Task — Generate Lore at Three Tiers

### CRITICAL: Use Exact IDs

You MUST use the exact `id` values from the data above. Do NOT invent
room, item, or NPC IDs — copy them verbatim from the lists. If
`location_id`, `item_id`, or `npc_id` does not match an existing entity,
the lore entry will be dropped.

### Tier 1: Surface Lore (everyone sees it)

- Embedded in room descriptions and obvious item examinations.
- The player encounters this through normal play on the critical path.
- Establishes atmosphere, tone, and basic world identity.
- **score_value: 0** — surface lore is free, no score incentive needed.
- **delivery_method**: `room_description`, `automatic`, `item_description`
- **required_flags**: null (always available)
- Every region should have at least one surface lore entry.
- Content examples: a plaque naming the location, a war that scarred the
  land mentioned in a room description, item names that imply history.

### Tier 2: Engaged Lore (curious players find it)

- Found by examining non-obvious items, exploring optional rooms, or asking
  NPCs follow-up questions.
- Rewards curiosity with deeper world-building and context.
- **score_value: 2-5 points.**
- **delivery_method**: `examine`, `read`, `talk`, `inscription`, `dialogue`
- **required_flags**: may require basic exploration flags, or null.
- Content examples: a journal entry found by examining a desk, an NPC's
  backstory revealed through follow-up dialogue, an inscription on an
  old sword.

### Tier 3: Deep Lore (dedicated players piece it together)

- Fragmentary, scattered, requires synthesis across multiple sources.
- Only players who explore thoroughly and connect dots get the full picture.
- **score_value: 10-20 points.**
- **delivery_method**: `examine`, `read`, `puzzle_reward`, `book`
- **required_flags**: often requires multiple flags (exploration, puzzle
  completion, NPC dialogue).
- Content examples: five torn pages of a research log scattered across
  regions that together reveal a hidden truth; a sealed chronicle found
  after solving an optional puzzle; examining a decorative item after
  learning a specific fact reveals new text.

### Lore Design Rules

1. **Consistency is paramount.**  Names, dates, events, and causality must
   never contradict across fragments.  Every lore entry exists in the same
   shared history.

2. **Critical path comprehensible without Tier 2/3.**  Surface lore alone
   must give the player enough context to understand the world and their
   purpose in it.

3. **Each tier recontextualizes the one above it.**  Tier 2 should add
   nuance to Tier 1 facts.  Tier 3 should subvert, deepen, or reframe
   what Tier 1 and 2 established.

4. **Lore contextualizes gameplay.**  The locks, puzzles, and dangers
   should make narrative sense given the lore.  Why is this door locked?
   The lore explains.  Why is this NPC hostile?  The lore explains.

5. **Lore distribution covers all regions.**  No region should be a
   narrative dead zone.

6. **Attach lore to specific entities.**  Every lore entry should reference
   a `location_id`, `item_id`, or `npc_id` (or multiple).  Floating lore
   with no anchor is undiscoverable.

### Target Quantities

- Surface lore: 1-2 entries per region (minimum one per region)
- Engaged lore: 3-6 entries total, spread across regions
- Deep lore: 2-4 entries total, at least one requiring multi-step discovery

### Output Format

```json
{{
  "lore": [
    {{
      "id": "snake_case_id",
      "tier": "surface",
      "title": "Internal Title",
      "content": "The lore text the player reads. Can be multiple sentences or paragraphs.",
      "delivery_method": "room_description",
      "location_id": "room_id or null",
      "item_id": "item_id or null",
      "npc_id": "npc_id or null",
      "required_flags": null,
      "score_value": 0
    }}
  ]
}}
```
"""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_lore(lore_entries: list[dict], context: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []
    room_ids = {r["id"] for r in context.get("rooms", [])}
    item_ids = {i["id"] for i in context.get("items", [])}
    npc_ids = {n["id"] for n in context.get("npcs", [])}
    regions = {r["region"] for r in context.get("rooms", [])}

    seen_ids: set[str] = set()
    tiers_seen: dict[str, int] = {"surface": 0, "engaged": 0, "deep": 0}
    regions_with_lore: set[str] = set()

    for entry in lore_entries:
        lid = entry.get("id", "<missing>")

        # Unique ID
        if lid in seen_ids:
            errors.append(f"Duplicate lore id: {lid}")
        seen_ids.add(lid)

        # Tier validation
        tier = entry.get("tier", "")
        if tier not in ("surface", "engaged", "deep"):
            errors.append(f"Lore {lid} has invalid tier: {tier}")
        else:
            tiers_seen[tier] += 1

        # Required fields
        for field in ("title", "content", "delivery_method"):
            if not entry.get(field):
                errors.append(f"Lore {lid} missing required field: {field}")

        # Entity reference validation
        loc_id = entry.get("location_id")
        if loc_id and loc_id not in room_ids:
            errors.append(f"Lore {lid} references unknown room: {loc_id}")
        if loc_id:
            # Find region for this room
            for r in context.get("rooms", []):
                if r["id"] == loc_id:
                    regions_with_lore.add(r["region"])
                    break

        iid = entry.get("item_id")
        if iid and iid not in item_ids:
            errors.append(f"Lore {lid} references unknown item: {iid}")

        nid = entry.get("npc_id")
        if nid and nid not in npc_ids:
            errors.append(f"Lore {lid} references unknown NPC: {nid}")

        # Must reference at least one entity
        if not loc_id and not iid and not nid:
            errors.append(
                f"Lore {lid} has no location_id, item_id, or npc_id — "
                f"it is unanchored and undiscoverable"
            )

        # Score value validation by tier
        score = entry.get("score_value", 0)
        if tier == "surface" and score != 0:
            errors.append(
                f"Surface lore {lid} has non-zero score_value: {score}"
            )

    # Tier coverage
    if tiers_seen["surface"] == 0:
        errors.append("No surface lore entries generated")
    if tiers_seen["engaged"] == 0:
        errors.append("No engaged lore entries generated")
    if tiers_seen["deep"] == 0:
        errors.append("No deep lore entries generated")

    # Region coverage
    uncovered = regions - regions_with_lore
    if uncovered:
        errors.append(
            f"Regions with no lore: {', '.join(sorted(uncovered))}"
        )

    return errors


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------


def _insert_lore(db: GameDB, lore_entries: list[dict], context: dict) -> None:
    """Insert validated lore entries into the database.

    FK references (location_id, item_id, npc_id) are checked against
    known IDs before insertion.  Invalid references are set to NULL with
    a warning.  If all three anchors are invalid/null, the entry is
    skipped entirely (unanchored lore is undiscoverable).
    """
    room_ids = {r["id"] for r in context.get("rooms", [])}
    item_ids = {i["id"] for i in context.get("items", [])}
    npc_ids = {n["id"] for n in context.get("npcs", [])}

    for entry in lore_entries:
        lid = entry.get("id", "<unknown>")

        # --- Validate location_id (nullable FK) ---
        loc_id = entry.get("location_id")
        if loc_id is not None and loc_id not in room_ids:
            logger.warning(
                "Lore %s references non-existent location_id %r — "
                "setting to NULL",
                lid,
                loc_id,
            )
            entry["location_id"] = None

        # --- Validate item_id (nullable FK) ---
        iid = entry.get("item_id")
        if iid is not None and iid not in item_ids:
            logger.warning(
                "Lore %s references non-existent item_id %r — "
                "setting to NULL",
                lid,
                iid,
            )
            entry["item_id"] = None

        # --- Validate npc_id (nullable FK) ---
        nid = entry.get("npc_id")
        if nid is not None and nid not in npc_ids:
            logger.warning(
                "Lore %s references non-existent npc_id %r — "
                "setting to NULL",
                lid,
                nid,
            )
            entry["npc_id"] = None

        # If all anchors are gone, the lore is undiscoverable — skip it
        if (
            entry.get("location_id") is None
            and entry.get("item_id") is None
            and entry.get("npc_id") is None
        ):
            logger.warning(
                "Lore %s has no valid anchor (location_id, item_id, npc_id "
                "all null/invalid) — skipping entry",
                lid,
            )
            continue

        required_flags = entry.get("required_flags")

        db.insert_lore(
            id=entry["id"],
            tier=entry["tier"],
            title=entry["title"],
            content=entry["content"],
            delivery_method=entry["delivery_method"],
            location_id=entry.get("location_id"),
            item_id=entry.get("item_id"),
            npc_id=entry.get("npc_id"),
            required_flags=(
                json.dumps(required_flags) if required_flags else None
            ),
            is_discovered=0,
            score_value=entry.get("score_value", 0),
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict:
    """Run Pass 8: Lore.  Returns updated context with lore data."""

    logger.info("Pass 8: Generating lore...")

    prompt = _build_prompt(context)
    gen_ctx = GenerationContext(
        existing_data={},
        seed=context.get("seed"),
        temperature=0.8,
        max_tokens=32_768,
    )

    result = provider.generate_structured(prompt, LORE_SCHEMA, gen_ctx)
    lore_entries: list[dict] = result.get("lore", [])

    # Validate
    errors = _validate_lore(lore_entries, context)
    if errors:
        for err in errors:
            logger.warning("Lore validation: %s", err)

    # Insert into DB (with FK validation)
    _insert_lore(db, lore_entries, context)

    # Build pass-specific data for downstream consumers
    lore_summary = [
        {
            "id": e["id"],
            "tier": e["tier"],
            "title": e["title"],
            "delivery_method": e["delivery_method"],
            "location_id": e.get("location_id"),
            "item_id": e.get("item_id"),
            "npc_id": e.get("npc_id"),
            "score_value": e.get("score_value", 0),
        }
        for e in lore_entries
    ]

    # Compute and log tier distribution
    tier_counts = {"surface": 0, "engaged": 0, "deep": 0}
    for e in lore_entries:
        tier = e.get("tier", "")
        if tier in tier_counts:
            tier_counts[tier] += 1

    logger.info(
        "Pass 8 complete: %d lore entries generated "
        "(surface=%d, engaged=%d, deep=%d).",
        len(lore_entries),
        tier_counts["surface"],
        tier_counts["engaged"],
        tier_counts["deep"],
    )
    return {"lore": lore_summary}
