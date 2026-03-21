"""Final validation step — deterministic post-import integrity checks.

This module runs after ZorkScript has been compiled into the `.zork`
database. It performs structural and logical checks to catch
inconsistencies that would break or degrade the player experience at
runtime.  No LLM call is made — every check is pure Python operating on
the SQLite data.

Usage::

    from anyzork.validation import validate_game

    errors = validate_game(db)
    critical = [e for e in errors if e.severity == "error"]
    if critical:
        ...  # import failed — report or fix the authored script
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anyzork.db.schema import GameDB


# ── Known DSL types (authoritative source: docs/dsl/COMMANDS.md) ─────

VALID_PRECONDITION_TYPES: frozenset[str] = frozenset(
    {
        "in_room",
        "has_item",
        "has_flag",
        "not_flag",
        "item_in_room",
        "item_accessible",
        "npc_in_room",
        "lock_unlocked",
        "puzzle_solved",
        "health_above",
        "container_open",
        "item_in_container",
        "not_item_in_container",
        "container_has_contents",
        "container_empty",
        "has_quantity",
        "toggle_state",
    }
)

VALID_EFFECT_TYPES: frozenset[str] = frozenset(
    {
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
        "take_item_from_container",
        "consume_quantity",
        "restore_quantity",
        "set_toggle_state",
        "move_npc",
        "fail_quest",
        "complete_quest",
        "kill_npc",
        "remove_npc",
        "lock_exit",
        "hide_exit",
        "change_description",
    }
)

VALID_TRIGGER_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "room_enter",
        "flag_set",
        "dialogue_node",
        "item_taken",
        "item_dropped",
    }
)


# ── Data classes ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationError:
    """A single validation finding.

    Attributes:
        severity: ``"error"`` (game is broken) or ``"warning"`` (quality issue).
        category: Short slug grouping the check (e.g. ``"spatial"``,
            ``"lock"``, ``"item"``).
        message: Human-readable description of the problem.
    """

    severity: str  # "error" | "warning"
    category: str
    message: str

    def __str__(self) -> str:
        tag = "ERROR" if self.severity == "error" else "WARN"
        return f"[{tag}][{self.category}] {self.message}"


# ── Helpers ──────────────────────────────────────────────────────────────


def _room_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db.get_all_rooms()}


def _item_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db._fetchall("SELECT id FROM items")}


def _npc_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db._fetchall("SELECT id FROM npcs")}


def _lock_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db._fetchall("SELECT id FROM locks")}


def _exit_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db._fetchall("SELECT id FROM exits")}


def _puzzle_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db._fetchall("SELECT id FROM puzzles")}


def _flag_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db._fetchall("SELECT id FROM flags")}


def _quest_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db._fetchall("SELECT id FROM quests")}


def _all_exits(db: GameDB) -> list[dict]:
    return db._fetchall("SELECT * FROM exits")


def _all_locks(db: GameDB) -> list[dict]:
    return db._fetchall("SELECT * FROM locks")


def _all_items(db: GameDB) -> list[dict]:
    return db._fetchall("SELECT * FROM items")


def _all_npcs(db: GameDB) -> list[dict]:
    return db._fetchall("SELECT * FROM npcs")


def _all_quests(db: GameDB) -> list[dict]:
    return db._fetchall("SELECT * FROM quests")


def _all_dialogue_nodes(db: GameDB) -> list[dict]:
    return db._fetchall("SELECT * FROM dialogue_nodes")


def _all_dialogue_options(db: GameDB) -> list[dict]:
    return db._fetchall("SELECT * FROM dialogue_options")


def _all_triggers(db: GameDB) -> list[dict]:
    return db._fetchall("SELECT * FROM triggers")


def _dialogue_node_ids(db: GameDB) -> set[str]:
    return {r["id"] for r in db._fetchall("SELECT id FROM dialogue_nodes")}


def _is_slot_ref(value: str) -> bool:
    """Return True if *value* is a ``{slot}`` placeholder."""
    return isinstance(value, str) and value.startswith("{") and value.endswith("}")


def _is_inventory_alias(value: str) -> bool:
    """Return True if *value* refers to the player inventory alias."""
    return isinstance(value, str) and value.strip().lower() in {
        "inventory",
        "_inventory",
        "_player_inventory",
    }


# ── BFS reachability on the full exit graph (ignoring locks) ─────────────


def _reachable_rooms(db: GameDB, start_id: str) -> set[str]:
    """BFS from *start_id* following all exits (locked or not)."""
    exits = _all_exits(db)
    adj: dict[str, list[str]] = {}
    for ex in exits:
        adj.setdefault(ex["from_room_id"], []).append(ex["to_room_id"])

    visited: set[str] = set()
    queue: deque[str] = deque([start_id])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adj.get(current, []):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def _reachable_rooms_unlocked(db: GameDB, start_id: str) -> set[str]:
    """BFS from *start_id* following only **unlocked** exits."""
    exits = _all_exits(db)
    adj: dict[str, list[str]] = {}
    for ex in exits:
        if not ex["is_locked"]:
            adj.setdefault(ex["from_room_id"], []).append(ex["to_room_id"])

    visited: set[str] = set()
    queue: deque[str] = deque([start_id])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adj.get(current, []):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def _effective_item_room(
    item_id: str,
    items_by_id: dict[str, dict],
    seen: set[str] | None = None,
) -> str | None:
    """Return the effective room for an item, following container ancestry."""
    item = items_by_id.get(item_id)
    if not item:
        return None

    seen = seen or set()
    if item_id in seen:
        return None
    seen.add(item_id)

    if item.get("room_id"):
        return item["room_id"]
    if item.get("home_room_id"):
        return item["home_room_id"]

    container_id = item.get("container_id")
    if container_id:
        return _effective_item_room(container_id, items_by_id, seen)
    return None


def _reachable_rooms_with_unlocked_key_locks(
    start_id: str,
    exits: list[dict],
    locks_by_exit: dict[str, dict],
    unlocked_key_lock_ids: set[str],
) -> set[str]:
    """Return rooms reachable after unlocking the provided key-lock IDs."""
    adj: dict[str, list[str]] = {}
    for ex in exits:
        lock = locks_by_exit.get(ex["id"])
        if ex["is_locked"] and (not lock or lock["id"] not in unlocked_key_lock_ids):
            continue
        adj.setdefault(ex["from_room_id"], []).append(ex["to_room_id"])

    visited: set[str] = set()
    queue: deque[str] = deque([start_id])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adj.get(current, []):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def _simulate_key_lock_progression(
    *,
    start_id: str,
    exits: list[dict],
    locks: list[dict],
    items_by_id: dict[str, dict],
    excluded_lock_id: str | None = None,
) -> tuple[set[str], set[str]]:
    """Simulate a valid unlock order for key locks.

    Key locks unlock when their key item becomes reachable. If
    ``excluded_lock_id`` is set, that lock stays closed throughout the
    simulation so we can ask whether its key is reachable before opening it.
    """
    locks_by_exit = {lock["target_exit_id"]: lock for lock in locks}
    key_locks = [
        lock
        for lock in locks
        if lock.get("lock_type") == "key" and lock.get("id") and lock.get("key_item_id")
    ]
    unlocked_key_lock_ids: set[str] = set()

    while True:
        reachable_rooms = _reachable_rooms_with_unlocked_key_locks(
            start_id,
            exits,
            locks_by_exit,
            unlocked_key_lock_ids,
        )
        progressed = False
        for lock in key_locks:
            lock_id = lock["id"]
            if lock_id == excluded_lock_id or lock_id in unlocked_key_lock_ids:
                continue

            key_room = _effective_item_room(lock["key_item_id"], items_by_id)
            if key_room and key_room in reachable_rooms:
                unlocked_key_lock_ids.add(lock_id)
                progressed = True

        if not progressed:
            return reachable_rooms, unlocked_key_lock_ids


# ── Check implementations ────────────────────────────────────────────────


def _check_spatial(db: GameDB) -> list[ValidationError]:
    """Spatial integrity checks."""
    errors: list[ValidationError] = []
    rooms = db.get_all_rooms()
    room_set = {r["id"] for r in rooms}

    # At least one room must exist.
    if not rooms:
        errors.append(
            ValidationError("error", "spatial", "No rooms defined in the database.")
        )
        return errors

    # Exactly one start room.
    start_rooms = [r for r in rooms if r.get("is_start")]
    if len(start_rooms) == 0:
        errors.append(
            ValidationError("error", "spatial", "No start room defined (is_start=1).")
        )
        return errors  # Can't do BFS without a start room.
    if len(start_rooms) > 1:
        ids = ", ".join(r["id"] for r in start_rooms)
        errors.append(
            ValidationError(
                "error",
                "spatial",
                f"Multiple start rooms defined: {ids}. Exactly one is required.",
            )
        )

    start_id = start_rooms[0]["id"]

    # All rooms reachable from start (ignoring locks).
    reachable = _reachable_rooms(db, start_id)
    orphaned = room_set - reachable
    if orphaned:
        errors.append(
            ValidationError(
                "error",
                "spatial",
                f"Orphaned rooms unreachable from start: {', '.join(sorted(orphaned))}",
            )
        )

    # Exit foreign-key integrity.
    exits = _all_exits(db)
    for ex in exits:
        if ex["from_room_id"] not in room_set:
            errors.append(
                ValidationError(
                    "error",
                    "spatial",
                    f"Exit {ex['id']} references non-existent from_room_id '{ex['from_room_id']}'.",
                )
            )
        if ex["to_room_id"] not in room_set:
            errors.append(
                ValidationError(
                    "error",
                    "spatial",
                    f"Exit {ex['id']} references non-existent to_room_id '{ex['to_room_id']}'.",
                )
            )

    # Two-way exit symmetry: for each exit A->B via direction D, there
    # should be a matching exit B->A.  Missing reverse exits are warnings
    # (they may be intentionally one-way), but we flag them.
    exit_set: set[tuple[str, str]] = set()
    for ex in exits:
        exit_set.add((ex["from_room_id"], ex["to_room_id"]))

    for ex in exits:
        reverse = (ex["to_room_id"], ex["from_room_id"])
        if reverse not in exit_set:
            errors.append(
                ValidationError(
                    "warning",
                    "spatial",
                    f"Exit {ex['id']} ({ex['from_room_id']} -> {ex['to_room_id']}) "
                    f"has no matching reverse exit. If intentionally one-way, this is fine.",
                )
            )

    return errors


def _check_locks(db: GameDB) -> list[ValidationError]:
    """Lock solvability checks."""
    errors: list[ValidationError] = []
    rooms = db.get_all_rooms()
    if not rooms:
        return errors

    start_rooms = [r for r in rooms if r.get("is_start")]
    if not start_rooms:
        return errors
    start_id = start_rooms[0]["id"]

    locks = _all_locks(db)
    exits = _all_exits(db)
    items = {i["id"]: i for i in _all_items(db)}
    exit_set = _exit_ids(db)
    puzzle_set = _puzzle_ids(db)

    for lock in locks:
        # Target exit must exist.
        if lock["target_exit_id"] not in exit_set:
            errors.append(
                ValidationError(
                    "error",
                    "lock",
                    f"Lock {lock['id']} targets non-existent exit '{lock['target_exit_id']}'.",
                )
            )

        # Key-type locks: key_item_id must exist and be takeable.
        if lock["lock_type"] == "key":
            key_id = lock.get("key_item_id")
            if not key_id:
                errors.append(
                    ValidationError(
                        "error",
                        "lock",
                        f"Key-type lock {lock['id']} has no key_item_id.",
                    )
                )
            elif key_id not in items:
                errors.append(
                    ValidationError(
                        "error",
                        "lock",
                        f"Key-type lock {lock['id']} references non-existent item '{key_id}'.",
                    )
                )
            else:
                if not items[key_id].get("is_takeable"):
                    errors.append(
                        ValidationError(
                            "error",
                            "lock",
                            f"Key item '{key_id}' for lock {lock['id']} "
                            "is not takeable (is_takeable=0).",
                        )
                    )

        # Puzzle-type locks: puzzle must exist.
        if lock["lock_type"] == "puzzle":
            pid = lock.get("puzzle_id")
            if pid and pid not in puzzle_set:
                errors.append(
                    ValidationError(
                        "error",
                        "lock",
                        f"Puzzle-type lock {lock['id']} references non-existent puzzle '{pid}'.",
                    )
                )

    key_locks = [lock for lock in locks if lock["lock_type"] == "key"]
    for lock in key_locks:
        key_id = lock.get("key_item_id")
        if not key_id or key_id not in items:
            continue

        reachable_before, _ = _simulate_key_lock_progression(
            start_id=start_id,
            exits=exits,
            locks=locks,
            items_by_id=items,
            excluded_lock_id=lock["id"],
        )
        key_room = _effective_item_room(key_id, items)
        if key_room and key_room not in reachable_before:
            errors.append(
                ValidationError(
                    "error",
                    "lock",
                    f"Key '{key_id}' (in room '{key_room}') for lock {lock['id']} "
                    "is not reachable before its lock in any valid unlock order.",
                )
            )

    _, unlocked_key_lock_ids = _simulate_key_lock_progression(
        start_id=start_id,
        exits=exits,
        locks=locks,
        items_by_id=items,
    )
    unresolved = [
        lock["id"]
        for lock in key_locks
        if lock["id"] not in unlocked_key_lock_ids
    ]
    if unresolved:
        errors.append(
            ValidationError(
                "error",
                "lock",
                "No valid unlock order exists for key locks: "
                + ", ".join(sorted(unresolved)),
            )
        )

    return errors


def _check_items(db: GameDB) -> list[ValidationError]:
    """Item consistency checks."""
    errors: list[ValidationError] = []
    items = _all_items(db)
    rooms = db.get_all_rooms()
    room_set = {room["id"] for room in rooms}
    room_map = {room["id"]: room for room in rooms}

    seen_ids: set[str] = set()
    item_map: dict[str, dict] = {}
    for item in items:
        # Duplicate IDs (shouldn't happen due to PRIMARY KEY, but check anyway).
        if item["id"] in seen_ids:
            errors.append(
                ValidationError(
                    "error",
                    "item",
                    f"Duplicate item ID: '{item['id']}'.",
                )
            )
        seen_ids.add(item["id"])
        item_map[item["id"]] = item

        # room_id validity (NULL = in inventory, which is fine).
        rid = item.get("room_id")
        if rid is not None and rid not in room_set:
            errors.append(
                ValidationError(
                    "error",
                    "item",
                    f"Item '{item['id']}' references non-existent room '{rid}'.",
                )
            )

        if (
            rid is not None
            and item.get("is_takeable")
            and item.get("is_visible")
            and rid in room_map
            and _room_text_mentions_name(room_map[rid], item["name"])
        ):
            errors.append(
                ValidationError(
                    "warning",
                    "item",
                    f"Item '{item['id']}' is already named in room '{rid}' prose. "
                    "Takeable items should usually rely on room_description/drop_description "
                    "to avoid duplicated room text.",
                )
            )

    # Items with a home room MUST have a room_description.
    for item in items:
        if item.get("home_room_id") and not item.get("room_description"):
            errors.append(
                ValidationError(
                    "error",
                    "item",
                    f"Item '{item['id']}' has home_room_id='{item['home_room_id']}' "
                    "but no room_description. Home items require room_desc for "
                    "authored prose in their home room.",
                )
            )

    # Key items referenced by locks must be takeable.
    locks = _all_locks(db)
    for lock in locks:
        if lock["lock_type"] == "key":
            key_id = lock.get("key_item_id")
            if key_id and key_id in item_map and not item_map[key_id].get("is_takeable"):
                errors.append(
                    ValidationError(
                        "error",
                        "item",
                        f"Key item '{key_id}' (for lock {lock['id']}) must be takeable.",
                    )
                )

    # --- Container nesting validation ---
    for item in items:
        cid = item.get("container_id")
        if cid is None:
            continue

        # container_id must reference a valid container (is_container = 1).
        if cid not in item_map:
            errors.append(
                ValidationError(
                    "error",
                    "item",
                    f"Item '{item['id']}' has container_id='{cid}' which "
                    f"does not reference an existing item.",
                )
            )
            continue
        parent = item_map[cid]
        if not parent.get("is_container"):
            errors.append(
                ValidationError(
                    "error",
                    "item",
                    f"Item '{item['id']}' has container_id='{cid}' but "
                    f"'{cid}' is not a container (is_container=0).",
                )
            )

        # Whitelist check: if the parent has accepts_items, this item
        # must appear in the whitelist.
        accepts_raw = parent.get("accepts_items")
        if accepts_raw is not None:
            try:
                whitelist = (
                    json.loads(accepts_raw)
                    if isinstance(accepts_raw, str)
                    else accepts_raw
                )
            except (json.JSONDecodeError, TypeError):
                whitelist = None
            if isinstance(whitelist, list) and item["id"] not in whitelist:
                errors.append(
                    ValidationError(
                        "error",
                        "item",
                        f"Item '{item['id']}' is inside container '{cid}' "
                        f"but is not in the container's accepts_items "
                        f"whitelist {whitelist}.",
                    )
                )

    # Cycle detection: walk each container_id chain and verify no item
    # appears twice (which would indicate a cycle).
    for item in items:
        if item.get("container_id") is None:
            continue
        visited: set[str] = set()
        current_id: str | None = item["id"]
        while current_id is not None:
            if current_id in visited:
                errors.append(
                    ValidationError(
                        "error",
                        "item",
                        f"Container cycle detected involving item "
                        f"'{item['id']}': chain revisits '{current_id}'.",
                    )
                )
                break
            visited.add(current_id)
            current_item = item_map.get(current_id)
            current_id = (
                current_item.get("container_id")
                if current_item is not None
                else None
            )

    return errors


def _validate_rule_preconditions(
    *,
    label: str,
    category: str,
    preconds: list[dict],
    room_set: set[str],
    item_set: set[str],
    npc_set: set[str],
    lock_set: set[str],
    puzzle_set: set[str],
    flag_set: set[str],
    errors: list[ValidationError],
) -> None:
    """Validate precondition objects shared by commands and triggers."""
    for pc in preconds:
        pc_type = pc.get("type")
        if pc_type not in VALID_PRECONDITION_TYPES:
            errors.append(
                ValidationError(
                    "error",
                    category,
                    f"{label} has unknown precondition type '{pc_type}'.",
                )
            )
            continue

        if pc_type == "in_room":
            room_val = pc.get("room", "")
            if not _is_slot_ref(room_val) and room_val not in room_set:
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} precondition in_room references non-existent room '{room_val}'.",
                    )
                )
        elif pc_type == "has_item":
            item_val = pc.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition has_item references unknown item '{item_val}'.",
                    )
                )
        elif pc_type in {"has_flag", "not_flag"}:
            flag_val = pc.get("flag", "")
            if not _is_slot_ref(flag_val) and flag_val not in flag_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition {pc_type} references unknown flag '{flag_val}'.",
                    )
                )
        elif pc_type == "item_in_room":
            item_val = pc.get("item", "")
            room_val = pc.get("room", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition item_in_room references unknown item '{item_val}'.",
                    )
                )
            if (
                not _is_slot_ref(room_val)
                and room_val != "_current"
                and room_val not in room_set
            ):
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} precondition item_in_room references "
                        f"non-existent room '{room_val}'.",
                    )
                )
        elif pc_type == "item_accessible":
            item_val = pc.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition item_accessible references "
                        f"unknown item '{item_val}'.",
                    )
                )
        elif pc_type == "npc_in_room":
            npc_val = pc.get("npc", "")
            room_val = pc.get("room", "")
            if not _is_slot_ref(npc_val) and npc_val not in npc_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition npc_in_room references unknown NPC '{npc_val}'.",
                    )
                )
            if (
                not _is_slot_ref(room_val)
                and room_val != "_current"
                and room_val not in room_set
            ):
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} precondition npc_in_room references "
                        f"non-existent room '{room_val}'.",
                    )
                )
        elif pc_type == "lock_unlocked":
            lock_val = pc.get("lock", "")
            if not _is_slot_ref(lock_val) and lock_val not in lock_set:
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} precondition lock_unlocked references "
                        f"non-existent lock '{lock_val}'.",
                    )
                )
        elif pc_type == "puzzle_solved":
            puz_val = pc.get("puzzle", "")
            if not _is_slot_ref(puz_val) and puz_val not in puzzle_set:
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} precondition puzzle_solved references "
                        f"non-existent puzzle '{puz_val}'.",
                    )
                )
        elif pc_type in {"container_open", "container_has_contents", "container_empty"}:
            container_val = pc.get("container", "")
            if not _is_slot_ref(container_val) and container_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition {pc_type} references unknown "
                        f"container '{container_val}'.",
                    )
                )
        elif pc_type in {"item_in_container", "not_item_in_container"}:
            item_val = pc.get("item", "")
            container_val = pc.get("container", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition {pc_type} references unknown item '{item_val}'.",
                    )
                )
            if _is_inventory_alias(container_val):
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} precondition {pc_type} cannot use inventory as a "
                        "container; use has_item for possession or a real container ID.",
                    )
                )
            elif not _is_slot_ref(container_val) and container_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition {pc_type} references unknown "
                        f"container '{container_val}'.",
                    )
                )
        elif pc_type == "has_quantity":
            item_val = pc.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition has_quantity references unknown item '{item_val}'.",
                    )
                )
        elif pc_type == "toggle_state":
            item_val = pc.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} precondition toggle_state references unknown item '{item_val}'.",
                    )
                )


def _validate_rule_effects(
    *,
    label: str,
    category: str,
    effects: list[dict],
    room_set: set[str],
    item_set: set[str],
    lock_set: set[str],
    exit_set: set[str],
    puzzle_set: set[str],
    quest_set: set[str],
    npc_set: set[str],
    flag_set: set[str],
    errors: list[ValidationError],
) -> None:
    """Validate effect objects shared by commands and triggers."""
    for eff in effects:
        eff_type = eff.get("type")
        if eff_type not in VALID_EFFECT_TYPES:
            errors.append(
                ValidationError(
                    "error",
                    category,
                    f"{label} has unknown effect type '{eff_type}'.",
                )
            )
            continue

        if eff_type == "move_item":
            item_val = eff.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect move_item references unknown item '{item_val}'.",
                    )
                )
            for loc_key in ("from", "to"):
                loc_val = eff.get(loc_key, "")
                if (
                    not _is_slot_ref(loc_val)
                    and loc_val not in ("_inventory", "_current")
                    and loc_val not in room_set
                ):
                    errors.append(
                        ValidationError(
                            "warning",
                            category,
                            f"{label} effect move_item {loc_key}='{loc_val}' "
                            f"is not a valid room or special constant.",
                        )
                    )
        elif eff_type == "remove_item":
            item_val = eff.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect remove_item references unknown item '{item_val}'.",
                    )
                )
        elif eff_type == "set_flag":
            flag_val = eff.get("flag", "")
            if not _is_slot_ref(flag_val) and flag_val not in flag_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect set_flag references unknown flag '{flag_val}'.",
                    )
                )
        elif eff_type == "unlock":
            lock_val = eff.get("lock", "")
            if not _is_slot_ref(lock_val) and lock_val not in lock_set:
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} effect unlock references non-existent lock '{lock_val}'.",
                    )
                )
        elif eff_type == "move_player":
            room_val = eff.get("room", "")
            if (
                not _is_slot_ref(room_val)
                and room_val != "_current"
                and room_val not in room_set
            ):
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} effect move_player references non-existent room '{room_val}'.",
                    )
                )
        elif eff_type == "spawn_item":
            item_val = eff.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect spawn_item references unknown item '{item_val}'.",
                    )
                )
            loc_val = eff.get("location", "")
            if (
                not _is_slot_ref(loc_val)
                and loc_val not in ("_inventory", "_current")
                and loc_val not in room_set
                and loc_val not in item_set
            ):
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect spawn_item location '{loc_val}' "
                        "is not a valid room, container, or special constant.",
                    )
                )
        elif eff_type == "reveal_exit":
            exit_val = eff.get("exit", "")
            if not _is_slot_ref(exit_val) and exit_val not in exit_set:
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} effect reveal_exit references non-existent exit '{exit_val}'.",
                    )
                )
        elif eff_type == "solve_puzzle":
            puz_val = eff.get("puzzle", "")
            if not _is_slot_ref(puz_val) and puz_val not in puzzle_set:
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} effect solve_puzzle references non-existent puzzle '{puz_val}'.",
                    )
                )
        elif eff_type == "discover_quest":
            quest_val = eff.get("quest", "")
            if not _is_slot_ref(quest_val) and quest_val not in quest_set:
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} effect discover_quest references "
                        f"non-existent quest '{quest_val}'.",
                    )
                )
        elif eff_type == "open_container":
            container_val = eff.get("container", "")
            if not _is_slot_ref(container_val) and container_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect open_container references unknown "
                        f"container '{container_val}'.",
                    )
                )
        elif eff_type == "move_item_to_container":
            item_val = eff.get("item", "")
            container_val = eff.get("container", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect move_item_to_container references "
                        f"unknown item '{item_val}'.",
                    )
                )
            if not _is_slot_ref(container_val) and container_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect move_item_to_container references "
                        f"unknown container '{container_val}'.",
                    )
                )
        elif eff_type == "take_item_from_container":
            item_val = eff.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect take_item_from_container references "
                        f"unknown item '{item_val}'.",
                    )
                )
        elif eff_type == "consume_quantity":
            item_val = eff.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect consume_quantity references unknown item '{item_val}'.",
                    )
                )
        elif eff_type == "restore_quantity":
            item_val = eff.get("item", "")
            source_val = eff.get("source", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect restore_quantity references unknown item '{item_val}'.",
                    )
                )
            if source_val and not _is_slot_ref(source_val) and source_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect restore_quantity references unknown "
                        f"source item '{source_val}'.",
                    )
                )
        elif eff_type == "set_toggle_state":
            item_val = eff.get("item", "")
            if not _is_slot_ref(item_val) and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        category,
                        f"{label} effect set_toggle_state references unknown item '{item_val}'.",
                    )
                )
        elif eff_type == "move_npc":
            npc_val = eff.get("npc", "")
            if not _is_slot_ref(npc_val) and npc_val not in npc_set:
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} effect move_npc references non-existent NPC '{npc_val}'.",
                    )
                )
            room_val = eff.get("room", "")
            if (
                not _is_slot_ref(room_val)
                and room_val != "_current"
                and room_val not in room_set
            ):
                errors.append(
                    ValidationError(
                        "error",
                        category,
                        f"{label} effect move_npc references non-existent room '{room_val}'.",
                    )
                )


def _check_commands(db: GameDB) -> list[ValidationError]:
    """Command validity checks."""
    errors: list[ValidationError] = []
    commands = db.get_all_commands()
    room_set = _room_ids(db)
    item_set = _item_ids(db)
    npc_set = _npc_ids(db)
    lock_set = _lock_ids(db)
    exit_set = _exit_ids(db)
    puzzle_set = _puzzle_ids(db)
    quest_set = _quest_ids(db)

    for cmd in commands:
        cmd_label = f"Command '{cmd['id']}'"

        # context_room_ids must reference valid rooms if set.
        ctx_rooms = cmd.get("context_room_ids")
        if ctx_rooms:
            import json as _json
            try:
                ctx_list = _json.loads(ctx_rooms) if isinstance(ctx_rooms, str) else ctx_rooms
            except (_json.JSONDecodeError, TypeError):
                ctx_list = []
            for rid in ctx_list:
                if rid not in room_set:
                    errors.append(
                        ValidationError(
                            "error",
                            "command",
                            f"{cmd_label} references non-existent room '{rid}' "
                            "in context_room_ids.",
                        )
                    )

        # puzzle_id must be valid if set.
        cmd_puzzle = cmd.get("puzzle_id")
        if cmd_puzzle and cmd_puzzle not in puzzle_set:
            errors.append(
                ValidationError(
                    "error",
                    "command",
                    f"{cmd_label} references non-existent puzzle_id '{cmd_puzzle}'.",
                )
            )

        # Parse and validate preconditions.
        try:
            preconds = json.loads(cmd.get("preconditions", "[]"))
        except (json.JSONDecodeError, TypeError):
            errors.append(
                ValidationError(
                    "error",
                    "command",
                    f"{cmd_label} has invalid preconditions JSON.",
                )
            )
            preconds = []
        _validate_rule_preconditions(
            label=cmd_label,
            category="command",
            preconds=preconds,
            room_set=room_set,
            item_set=item_set,
            npc_set=npc_set,
            lock_set=lock_set,
            puzzle_set=puzzle_set,
            flag_set=_flag_ids(db),
            errors=errors,
        )

        # Parse and validate effects.
        try:
            effects = json.loads(cmd.get("effects", "[]"))
        except (json.JSONDecodeError, TypeError):
            errors.append(
                ValidationError(
                    "error",
                    "command",
                    f"{cmd_label} has invalid effects JSON.",
                )
            )
            effects = []

        success_message = (cmd.get("success_message") or "").strip()
        if not effects and not success_message:
            errors.append(
                ValidationError(
                    "error",
                    "command",
                    f"{cmd_label} can succeed without producing any effect or visible message.",
                )
            )
        _validate_rule_effects(
            label=cmd_label,
            category="command",
            effects=effects,
            room_set=room_set,
            item_set=item_set,
            lock_set=lock_set,
            exit_set=exit_set,
            puzzle_set=puzzle_set,
            quest_set=quest_set,
            npc_set=npc_set,
            flag_set=_flag_ids(db),
            errors=errors,
        )

    return errors


def _room_text_mentions_name(room: dict, name: str) -> bool:
    """Return True when a room prose field already names a visible item."""
    pattern = re.compile(re.escape(name), re.IGNORECASE)
    texts = (
        room.get("description") or "",
        room.get("short_description") or "",
        room.get("first_visit_text") or "",
    )
    return any(pattern.search(text) for text in texts)


def _check_npcs(db: GameDB) -> list[ValidationError]:
    """NPC consistency checks."""
    errors: list[ValidationError] = []
    npcs = _all_npcs(db)
    room_set = _room_ids(db)
    dialogue_nodes = _all_dialogue_nodes(db)
    npc_set = _npc_ids(db)

    for npc in npcs:
        # Room reference must be valid.
        if npc["room_id"] not in room_set:
            errors.append(
                ValidationError(
                    "error",
                    "npc",
                    f"NPC '{npc['id']}' references non-existent room '{npc['room_id']}'.",
                )
            )

        # NPCs with a home room MUST have a room_description.
        if npc.get("home_room_id") and not npc.get("room_description"):
            errors.append(
                ValidationError(
                    "error",
                    "npc",
                    f"NPC '{npc['id']}' has home_room_id='{npc['home_room_id']}' "
                    "but no room_description. Home NPCs require room_desc for "
                    "authored prose in their home room.",
                )
            )

    # Dialogue nodes must reference valid NPCs.
    for d in dialogue_nodes:
        if d["npc_id"] not in npc_set:
            errors.append(
                ValidationError(
                    "error",
                    "npc",
                    f"Dialogue node '{d['id']}' references non-existent NPC '{d['npc_id']}'.",
                )
            )

    return errors


def _check_quests(db: GameDB) -> list[ValidationError]:
    """Quest structure and reference checks."""
    errors: list[ValidationError] = []
    quest_entries = _all_quests(db)
    flag_set = _flag_ids(db)

    # Must have exactly one main quest.
    main_quests = [q for q in quest_entries if q.get("quest_type") == "main"]
    if len(main_quests) == 0:
        errors.append(
            ValidationError(
                "error",
                "quest",
                "No main quest found. Every game must have exactly one main quest.",
            )
        )
    elif len(main_quests) > 1:
        errors.append(
            ValidationError(
                "error",
                "quest",
                f"Multiple main quests found ({len(main_quests)}). Exactly one is required.",
            )
        )

    if not quest_entries:
        errors.append(
            ValidationError(
                "warning",
                "quest",
                "No quests found at all. The game will lack objectives.",
            )
        )

    for quest in quest_entries:
        qid = quest["id"]

        # Validate discovery_flag.
        disc = quest.get("discovery_flag")
        if disc is not None and disc not in flag_set:
            errors.append(
                ValidationError(
                    "warning",
                    "quest",
                    f"Quest '{qid}' discovery_flag '{disc}' not found in flags table.",
                )
            )

        # Validate completion_flag.
        comp = quest.get("completion_flag", "")
        if comp and comp not in flag_set:
            errors.append(
                ValidationError(
                    "warning",
                    "quest",
                    f"Quest '{qid}' completion_flag '{comp}' not found in flags table.",
                )
            )

        # Check objectives.
        objectives = db._fetchall(
            "SELECT * FROM quest_objectives WHERE quest_id = ?", (qid,)
        )
        if not objectives:
            errors.append(
                ValidationError(
                    "error",
                    "quest",
                    f"Quest '{qid}' has no objectives.",
                )
            )
            continue

        has_required = any(not o["is_optional"] for o in objectives)
        if not has_required:
            errors.append(
                ValidationError(
                    "error",
                    "quest",
                    f"Quest '{qid}' has no required (non-optional) objectives.",
                )
            )

        for obj in objectives:
            obj_flag = obj.get("completion_flag", "")
            if obj_flag and obj_flag not in flag_set:
                errors.append(
                    ValidationError(
                        "warning",
                        "quest",
                        f"Quest objective '{obj['id']}' completion_flag '{obj_flag}' "
                        f"not found in flags table.",
                    )
                )

    return errors


def _check_triggers(db: GameDB) -> list[ValidationError]:
    """Trigger structure, event-data, and rule reference checks."""
    errors: list[ValidationError] = []
    triggers = _all_triggers(db)
    room_set = _room_ids(db)
    item_set = _item_ids(db)
    npc_set = _npc_ids(db)
    lock_set = _lock_ids(db)
    exit_set = _exit_ids(db)
    puzzle_set = _puzzle_ids(db)
    quest_set = _quest_ids(db)
    flag_set = _flag_ids(db)
    dialogue_node_set = _dialogue_node_ids(db)

    for trigger in triggers:
        trig_label = f"Trigger '{trigger['id']}'"
        event_type = trigger.get("event_type")
        if event_type not in VALID_TRIGGER_EVENT_TYPES:
            errors.append(
                ValidationError(
                    "error",
                    "trigger",
                    f"{trig_label} has unknown event_type '{event_type}'.",
                )
            )
            continue

        try:
            event_data = json.loads(trigger.get("event_data", "{}"))
        except (json.JSONDecodeError, TypeError):
            errors.append(
                ValidationError(
                    "error",
                    "trigger",
                    f"{trig_label} has invalid event_data JSON.",
                )
            )
            event_data = {}

        if event_type == "room_enter":
            room_val = event_data.get("room_id")
            if room_val and room_val not in room_set:
                errors.append(
                    ValidationError(
                        "error",
                        "trigger",
                        f"{trig_label} event_data references non-existent room "
                        f"'{room_val}'.",
                    )
                )
        elif event_type == "flag_set":
            flag_val = event_data.get("flag")
            if flag_val and flag_val not in flag_set:
                errors.append(
                    ValidationError(
                        "warning",
                        "trigger",
                        f"{trig_label} event_data references unknown flag '{flag_val}'.",
                    )
                )
        elif event_type == "dialogue_node":
            node_val = event_data.get("node_id")
            npc_val = event_data.get("npc_id")
            if node_val and node_val not in dialogue_node_set:
                errors.append(
                    ValidationError(
                        "error",
                        "trigger",
                        f"{trig_label} event_data references non-existent "
                        f"dialogue node '{node_val}'.",
                    )
                )
            if npc_val and npc_val not in npc_set:
                errors.append(
                    ValidationError(
                        "warning",
                        "trigger",
                        f"{trig_label} event_data references unknown NPC '{npc_val}'.",
                    )
                )
        elif event_type in {"item_taken", "item_dropped"}:
            item_val = event_data.get("item_id")
            room_val = event_data.get("room_id")
            if item_val and item_val not in item_set:
                errors.append(
                    ValidationError(
                        "warning",
                        "trigger",
                        f"{trig_label} event_data references unknown item '{item_val}'.",
                    )
                )
            if room_val and room_val not in room_set:
                errors.append(
                    ValidationError(
                        "error",
                        "trigger",
                        f"{trig_label} event_data references non-existent room '{room_val}'.",
                    )
                )

        try:
            preconds = json.loads(trigger.get("preconditions", "[]"))
        except (json.JSONDecodeError, TypeError):
            errors.append(
                ValidationError(
                    "error",
                    "trigger",
                    f"{trig_label} has invalid preconditions JSON.",
                )
            )
            preconds = []

        _validate_rule_preconditions(
            label=trig_label,
            category="trigger",
            preconds=preconds,
            room_set=room_set,
            item_set=item_set,
            npc_set=npc_set,
            lock_set=lock_set,
            puzzle_set=puzzle_set,
            flag_set=flag_set,
            errors=errors,
        )

        try:
            effects = json.loads(trigger.get("effects", "[]"))
        except (json.JSONDecodeError, TypeError):
            errors.append(
                ValidationError(
                    "error",
                    "trigger",
                    f"{trig_label} has invalid effects JSON.",
                )
            )
            effects = []

        _validate_rule_effects(
            label=trig_label,
            category="trigger",
            effects=effects,
            room_set=room_set,
            item_set=item_set,
            lock_set=lock_set,
            exit_set=exit_set,
            puzzle_set=puzzle_set,
            quest_set=quest_set,
            npc_set=npc_set,
            flag_set=flag_set,
            errors=errors,
        )

    return errors


def _check_win_condition(db: GameDB) -> list[ValidationError]:
    """Win condition flag checks."""
    errors: list[ValidationError] = []
    meta = db.get_all_meta()
    if not meta:
        errors.append(
            ValidationError("error", "win", "No metadata row found.")
        )
        return errors

    # Parse win_conditions JSON.
    try:
        win_flags = json.loads(meta.get("win_conditions", "[]"))
    except (json.JSONDecodeError, TypeError):
        errors.append(
            ValidationError("error", "win", "win_conditions metadata is not valid JSON.")
        )
        return errors

    if not win_flags:
        errors.append(
            ValidationError(
                "warning",
                "win",
                "No win condition flags defined. The game has no victory state.",
            )
        )
        return errors

    # Each win-condition flag must be settable by at least one deterministic
    # state transition: command, trigger, dialogue, or quest completion.
    settable_flags: set[str] = set()
    commands = db.get_all_commands()
    for cmd in commands:
        try:
            effects = json.loads(cmd.get("effects", "[]"))
        except (json.JSONDecodeError, TypeError):
            continue
        for eff in effects:
            if eff.get("type") == "set_flag":
                flag_name = eff.get("flag")
                if flag_name:
                    settable_flags.add(flag_name)

    for trigger in _all_triggers(db):
        try:
            effects = json.loads(trigger.get("effects", "[]"))
        except (json.JSONDecodeError, TypeError):
            continue
        for eff in effects:
            if eff.get("type") == "set_flag":
                flag_name = eff.get("flag")
                if flag_name:
                    settable_flags.add(flag_name)

    for node in _all_dialogue_nodes(db):
        try:
            flags = json.loads(node.get("set_flags", "[]")) if node.get("set_flags") else []
        except (json.JSONDecodeError, TypeError):
            flags = []
        settable_flags.update(flag for flag in flags if flag)

    for option in _all_dialogue_options(db):
        try:
            flags = json.loads(option.get("set_flags", "[]")) if option.get("set_flags") else []
        except (json.JSONDecodeError, TypeError):
            flags = []
        settable_flags.update(flag for flag in flags if flag)

    for quest in _all_quests(db):
        completion_flag = quest.get("completion_flag")
        if completion_flag:
            settable_flags.add(completion_flag)

    for flag in win_flags:
        if flag not in settable_flags:
            errors.append(
                ValidationError(
                    "error",
                    "win",
                    f"Win condition flag '{flag}' is never set by any command effect. "
                    f"The game is unwinnable.",
                )
            )

    return errors


# ── Public API ───────────────────────────────────────────────────────────


def validate_game(db: GameDB) -> list[ValidationError]:
    """Run all validation checks against a populated ``.zork`` database.

    Returns a list of :class:`ValidationError` instances.  An empty list
    means the game passed all checks.  Callers should inspect
    ``severity == "error"`` entries to decide whether the game is playable.
    """
    results: list[ValidationError] = []

    results.extend(_check_spatial(db))
    results.extend(_check_locks(db))
    results.extend(_check_items(db))
    results.extend(_check_commands(db))
    results.extend(_check_npcs(db))
    results.extend(_check_quests(db))
    results.extend(_check_triggers(db))
    results.extend(_check_win_condition(db))

    return results
