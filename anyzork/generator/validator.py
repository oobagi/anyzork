"""Pass 9: Validation — deterministic post-generation integrity checks.

This module runs after all LLM generation passes have populated the .zork
database.  It performs structural and logical checks to catch
inconsistencies that would break or degrade the player experience at
runtime.  No LLM call is made — every check is pure Python operating on
the SQLite data.

Usage::

    from anyzork.generator.validator import validate_game

    errors = validate_game(db)
    critical = [e for e in errors if e.severity == "error"]
    if critical:
        ...  # generation failed — report or retry
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anyzork.db.schema import GameDB


# ── Known DSL types (authoritative source: docs/dsl/command-spec.md) ─────

VALID_PRECONDITION_TYPES: frozenset[str] = frozenset(
    {
        "in_room",
        "has_item",
        "has_flag",
        "not_flag",
        "item_in_room",
        "npc_in_room",
        "lock_unlocked",
        "puzzle_solved",
        "health_above",
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


def _is_slot_ref(value: str) -> bool:
    """Return True if *value* is a ``{slot}`` placeholder."""
    return isinstance(value, str) and value.startswith("{") and value.endswith("}")


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
                            f"Key item '{key_id}' for lock {lock['id']} is not takeable (is_takeable=0).",
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

    # Key reachability: each key must be reachable via the unlocked
    # subgraph before its lock is encountered.
    reachable_unlocked = _reachable_rooms_unlocked(db, start_id)
    for lock in locks:
        if lock["lock_type"] == "key":
            key_id = lock.get("key_item_id")
            if key_id and key_id in items:
                key_room = items[key_id].get("room_id")
                if key_room and key_room not in reachable_unlocked:
                    errors.append(
                        ValidationError(
                            "error",
                            "lock",
                            f"Key '{key_id}' (in room '{key_room}') for lock {lock['id']} "
                            f"is not reachable without passing through a locked exit.",
                        )
                    )

    # Circular lock dependency detection.
    # Build a graph: for each lock, if its key is behind another lock,
    # that creates a dependency edge.
    exits_by_id = {e["id"]: e for e in _all_exits(db)}
    lock_by_exit: dict[str, dict] = {}
    for lock in locks:
        lock_by_exit[lock["target_exit_id"]] = lock

    # Map room -> set of locks that gate entries into that room.
    room_entry_locks: dict[str, set[str]] = {}
    for lock in locks:
        exit_row = exits_by_id.get(lock["target_exit_id"])
        if exit_row:
            dest = exit_row["to_room_id"]
            room_entry_locks.setdefault(dest, set()).add(lock["id"])

    # Build dependency edges: lock A depends on lock B if lock A's key is
    # in a room that can only be reached by passing through lock B.
    # Simplified approach: check if the key's room is behind any locked exit.
    dep_graph: dict[str, set[str]] = {lock["id"]: set() for lock in locks}
    for lock in locks:
        if lock["lock_type"] != "key":
            continue
        key_id = lock.get("key_item_id")
        if not key_id or key_id not in items:
            continue
        key_room = items[key_id].get("room_id")
        if not key_room:
            continue
        # Which locks gate the key's room?
        for other_lock_id in room_entry_locks.get(key_room, set()):
            if other_lock_id != lock["id"]:
                dep_graph[lock["id"]].add(other_lock_id)

    # Detect cycles via DFS.
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {lid: WHITE for lid in dep_graph}

    def _dfs_cycle(node: str) -> bool:
        color[node] = GRAY
        for neighbor in dep_graph.get(node, set()):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and _dfs_cycle(neighbor):
                return True
        color[node] = BLACK
        return False

    for lock_id in dep_graph:
        if color[lock_id] == WHITE:
            if _dfs_cycle(lock_id):
                errors.append(
                    ValidationError(
                        "error",
                        "lock",
                        f"Circular lock dependency detected involving lock '{lock_id}'.",
                    )
                )

    return errors


def _check_items(db: GameDB) -> list[ValidationError]:
    """Item consistency checks."""
    errors: list[ValidationError] = []
    items = _all_items(db)
    room_set = _room_ids(db)

    seen_ids: set[str] = set()
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

    # Key items referenced by locks must be takeable.
    locks = _all_locks(db)
    item_map = {i["id"]: i for i in items}
    for lock in locks:
        if lock["lock_type"] == "key":
            key_id = lock.get("key_item_id")
            if key_id and key_id in item_map:
                if not item_map[key_id].get("is_takeable"):
                    errors.append(
                        ValidationError(
                            "error",
                            "item",
                            f"Key item '{key_id}' (for lock {lock['id']}) must be takeable.",
                        )
                    )

    return errors


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

        # context_room_id must be valid if set.
        ctx_room = cmd.get("context_room_id")
        if ctx_room and ctx_room not in room_set:
            errors.append(
                ValidationError(
                    "error",
                    "command",
                    f"{cmd_label} references non-existent context_room_id '{ctx_room}'.",
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

        for pc in preconds:
            pc_type = pc.get("type")
            if pc_type not in VALID_PRECONDITION_TYPES:
                errors.append(
                    ValidationError(
                        "error",
                        "command",
                        f"{cmd_label} has unknown precondition type '{pc_type}'.",
                    )
                )
                continue

            # Validate entity references (skip slot refs like "{item}").
            if pc_type == "in_room":
                room_val = pc.get("room", "")
                if not _is_slot_ref(room_val) and room_val not in room_set:
                    errors.append(
                        ValidationError(
                            "error",
                            "command",
                            f"{cmd_label} precondition in_room references non-existent room '{room_val}'.",
                        )
                    )
            elif pc_type == "has_item":
                item_val = pc.get("item", "")
                if not _is_slot_ref(item_val) and item_val not in item_set:
                    errors.append(
                        ValidationError(
                            "warning",
                            "command",
                            f"{cmd_label} precondition has_item references unknown item '{item_val}'.",
                        )
                    )
            elif pc_type == "item_in_room":
                item_val = pc.get("item", "")
                room_val = pc.get("room", "")
                if not _is_slot_ref(item_val) and item_val not in item_set:
                    errors.append(
                        ValidationError(
                            "warning",
                            "command",
                            f"{cmd_label} precondition item_in_room references unknown item '{item_val}'.",
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
                            "command",
                            f"{cmd_label} precondition item_in_room references non-existent room '{room_val}'.",
                        )
                    )
            elif pc_type == "npc_in_room":
                npc_val = pc.get("npc", "")
                room_val = pc.get("room", "")
                if not _is_slot_ref(npc_val) and npc_val not in npc_set:
                    errors.append(
                        ValidationError(
                            "warning",
                            "command",
                            f"{cmd_label} precondition npc_in_room references unknown NPC '{npc_val}'.",
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
                            "command",
                            f"{cmd_label} precondition npc_in_room references non-existent room '{room_val}'.",
                        )
                    )
            elif pc_type == "lock_unlocked":
                lock_val = pc.get("lock", "")
                if not _is_slot_ref(lock_val) and lock_val not in lock_set:
                    errors.append(
                        ValidationError(
                            "error",
                            "command",
                            f"{cmd_label} precondition lock_unlocked references non-existent lock '{lock_val}'.",
                        )
                    )
            elif pc_type == "puzzle_solved":
                puz_val = pc.get("puzzle", "")
                if not _is_slot_ref(puz_val) and puz_val not in puzzle_set:
                    errors.append(
                        ValidationError(
                            "error",
                            "command",
                            f"{cmd_label} precondition puzzle_solved references non-existent puzzle '{puz_val}'.",
                        )
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

        for eff in effects:
            eff_type = eff.get("type")
            if eff_type not in VALID_EFFECT_TYPES:
                errors.append(
                    ValidationError(
                        "error",
                        "command",
                        f"{cmd_label} has unknown effect type '{eff_type}'.",
                    )
                )
                continue

            # Validate entity references in effects.
            if eff_type == "move_item":
                item_val = eff.get("item", "")
                if not _is_slot_ref(item_val) and item_val not in item_set:
                    errors.append(
                        ValidationError(
                            "warning",
                            "command",
                            f"{cmd_label} effect move_item references unknown item '{item_val}'.",
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
                                "command",
                                f"{cmd_label} effect move_item {loc_key}='{loc_val}' "
                                f"is not a valid room or special constant.",
                            )
                        )
            elif eff_type == "remove_item":
                item_val = eff.get("item", "")
                if not _is_slot_ref(item_val) and item_val not in item_set:
                    errors.append(
                        ValidationError(
                            "warning",
                            "command",
                            f"{cmd_label} effect remove_item references unknown item '{item_val}'.",
                        )
                    )
            elif eff_type == "unlock":
                lock_val = eff.get("lock", "")
                if not _is_slot_ref(lock_val) and lock_val not in lock_set:
                    errors.append(
                        ValidationError(
                            "error",
                            "command",
                            f"{cmd_label} effect unlock references non-existent lock '{lock_val}'.",
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
                            "command",
                            f"{cmd_label} effect move_player references non-existent room '{room_val}'.",
                        )
                    )
            elif eff_type == "spawn_item":
                item_val = eff.get("item", "")
                if not _is_slot_ref(item_val) and item_val not in item_set:
                    errors.append(
                        ValidationError(
                            "warning",
                            "command",
                            f"{cmd_label} effect spawn_item references unknown item '{item_val}'.",
                        )
                    )
                loc_val = eff.get("location", "")
                if (
                    not _is_slot_ref(loc_val)
                    and loc_val not in ("_inventory", "_current")
                    and loc_val not in room_set
                ):
                    errors.append(
                        ValidationError(
                            "warning",
                            "command",
                            f"{cmd_label} effect spawn_item location '{loc_val}' "
                            f"is not a valid room or special constant.",
                        )
                    )
            elif eff_type == "reveal_exit":
                exit_val = eff.get("exit", "")
                if not _is_slot_ref(exit_val) and exit_val not in exit_set:
                    errors.append(
                        ValidationError(
                            "error",
                            "command",
                            f"{cmd_label} effect reveal_exit references non-existent exit '{exit_val}'.",
                        )
                    )
            elif eff_type == "solve_puzzle":
                puz_val = eff.get("puzzle", "")
                if not _is_slot_ref(puz_val) and puz_val not in puzzle_set:
                    errors.append(
                        ValidationError(
                            "error",
                            "command",
                            f"{cmd_label} effect solve_puzzle references non-existent puzzle '{puz_val}'.",
                        )
                    )
            elif eff_type == "discover_quest":
                quest_val = eff.get("quest", "")
                if not _is_slot_ref(quest_val) and quest_val not in quest_set:
                    errors.append(
                        ValidationError(
                            "error",
                            "command",
                            f"{cmd_label} effect discover_quest references non-existent quest '{quest_val}'.",
                        )
                    )

    return errors


def _check_npcs(db: GameDB) -> list[ValidationError]:
    """NPC consistency checks."""
    errors: list[ValidationError] = []
    npcs = _all_npcs(db)
    room_set = _room_ids(db)
    dialogue_nodes = _all_dialogue_nodes(db)
    npc_set = _npc_ids(db)

    # Build set of NPC IDs that have at least one dialogue node.
    npcs_with_dialogue: set[str] = {d["npc_id"] for d in dialogue_nodes}

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

    # Each win-condition flag must be settable by at least one command effect.
    commands = db.get_all_commands()
    settable_flags: set[str] = set()
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
    results.extend(_check_win_condition(db))

    return results
