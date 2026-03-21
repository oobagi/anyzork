"""Command DSL interpreter for the AnyZork runtime engine.

Evaluates command DSL rules deterministically at play-time. No LLM involved.
Each command is a structured precondition/effect rule stored as JSON in the
database. This module parses player input, matches it against command patterns,
checks preconditions against game state, and applies effects atomically.

Implements the full specification from docs/dsl/command-spec.md.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from anyzork.db.schema import GameDB

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    """Outcome of resolving a player command.

    Attributes:
        success: Whether a command matched and all preconditions passed.
        messages: Ordered list of text messages to display to the player.
        effects_applied: List of effect type strings that were executed
            (e.g. ``["remove_item", "unlock", "print"]``).
        command_id: The id of the matched DSL command, if any.
    """

    success: bool
    messages: list[str] = field(default_factory=list)
    effects_applied: list[str] = field(default_factory=list)
    command_id: str = ""


# ---------------------------------------------------------------------------
# Slot resolution — map display names to database IDs
# ---------------------------------------------------------------------------

def _resolve_name_to_id(name: str, db: GameDB) -> str:
    """Attempt to resolve a display name to a database ID.

    Tries, in order:
    1. Direct ID match (items, npcs, rooms) — the name *is* already an ID.
    2. Case-insensitive name match against items (inventory first, then all).
    3. Case-insensitive name match against NPCs.
    4. Case-insensitive name match against rooms.
    5. Fallback: convert to snake_case (replace spaces/hyphens with
       underscores, lowercase) and return that as a best-guess ID.
    """
    # 1. Direct ID match
    if db.get_item(name):
        return name
    if db.get_npc(name):
        return name
    if db.get_room(name):
        return name

    # 2. Item by name — check inventory first, then all items
    inv_match = db.find_item_by_name(name, "inventory", "")
    if inv_match:
        return inv_match["id"]

    player = db.get_player()
    if player:
        room_match = db.find_item_by_name(name, "room", player["current_room_id"])
        if room_match:
            return room_match["id"]

    # Brute-force search all items by name (handles items in other rooms
    # referenced by preconditions with explicit room IDs).
    row = db._fetchone(
        "SELECT id FROM items WHERE LOWER(name) = LOWER(?)", (name,)
    )
    if row:
        return row["id"]

    # 3. NPC by name
    row = db._fetchone(
        "SELECT id FROM npcs WHERE LOWER(name) = LOWER(?)", (name,)
    )
    if row:
        return row["id"]

    # 4. Room by name
    row = db._fetchone(
        "SELECT id FROM rooms WHERE LOWER(name) = LOWER(?)", (name,)
    )
    if row:
        return row["id"]

    # 5. Fallback — snake_case conversion
    return re.sub(r"[\s\-]+", "_", name.strip()).lower()


def _substitute_slots(value: str, slots: dict[str, str]) -> str:
    """Replace ``{slot_name}`` placeholders with resolved slot values."""
    for slot_name, slot_value in slots.items():
        value = value.replace(f"{{{slot_name}}}", slot_value)
    return value


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------

def parse_player_input(raw_input: str, pattern: str) -> dict[str, str] | None:
    """Match player input against a command pattern, extracting named slots.

    The pattern contains literal words and ``{slot}`` placeholders. Literal
    words must match exactly (case-insensitive). Slots capture one or more
    contiguous words.

    Returns a dict mapping slot names to their captured (raw) values, or
    ``None`` if the pattern does not match.

    Examples::

        >>> parse_player_input("use rusty key on wooden door",
        ...                    "use {item} on {target}")
        {"item": "rusty key", "target": "wooden door"}

        >>> parse_player_input("look", "look")
        {}

        >>> parse_player_input("go north", "look at {target}")
        None
    """
    # Tokenise the pattern into literal segments and slot names.
    # We build a regex that captures slot values as named groups.
    #
    # Strategy: split pattern on {slot} tokens. Literals become escaped
    # regex fragments; slots become named capturing groups matching one
    # or more non-empty word sequences.
    slot_pattern = re.compile(r"\{(\w+)\}")
    parts = slot_pattern.split(pattern)
    # `parts` alternates: [literal, slot_name, literal, slot_name, ...]

    regex_parts: list[str] = []
    slot_names: list[str] = []
    # Count total slots so we can make the last one greedy
    total_slots = len(slot_pattern.findall(pattern))
    slot_index = 0
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Literal segment — escape and allow flexible whitespace
            words = part.split()
            if words:
                escaped = r"\s+".join(re.escape(w) for w in words)
                regex_parts.append(escaped)
        else:
            # Slot name — last slot is greedy, others are lazy
            slot_names.append(part)
            slot_index += 1
            quantifier = ".+" if slot_index == total_slots else ".+?"
            regex_parts.append(rf"(?P<{part}>{quantifier})")

    # Join all parts with flexible whitespace
    full_regex = r"\s+".join(p for p in regex_parts if p)
    full_regex = rf"^\s*{full_regex}\s*$"

    m = re.match(full_regex, raw_input, re.IGNORECASE)
    if m is None:
        return None

    return {name: m.group(name).strip() for name in slot_names}


def _count_slots(pattern: str) -> int:
    """Return the number of ``{slot}`` placeholders in a pattern."""
    return len(re.findall(r"\{(\w+)\}", pattern))


def _item_is_accessible(item_id: str, db: GameDB, current_room: str) -> bool:
    """Return True when an item can be interacted with from the current state.

    Accessible items are:
    - visible loose items in the current room
    - visible inventory items
    - visible items inside accessible open containers in the current room
    - visible items inside accessible open containers in inventory
    """
    item = db.get_item(item_id)
    if item is None or not item["is_visible"]:
        return False

    if item["container_id"] is None:
        return item["room_id"] in {None, current_room}

    current = item
    visited: set[str] = set()
    while current["container_id"] is not None:
        container_id = current["container_id"]
        if container_id in visited:
            return False
        visited.add(container_id)

        container = db.get_item(container_id)
        if container is None or not container["is_visible"]:
            return False
        if container["is_locked"]:
            return False
        if not container["is_open"] and container["has_lid"]:
            return False
        current = container

    return current["room_id"] in {None, current_room}


# ---------------------------------------------------------------------------
# Precondition evaluation
# ---------------------------------------------------------------------------

def check_precondition(condition: dict, db: GameDB, slots: dict[str, str] | None = None) -> bool:
    """Evaluate a single precondition against the current game state.

    Supports all precondition types from the DSL spec:
    ``in_room``, ``has_item``, ``has_flag``, ``not_flag``, ``item_in_room``,
    ``item_accessible``, ``npc_in_room``, ``lock_unlocked``,
    ``puzzle_solved``, ``health_above``, ``container_open``,
    ``item_in_container``, ``not_item_in_container``,
    ``container_has_contents``, ``container_empty``, ``has_quantity``,
    ``toggle_state``.

    Slot references (``{slot_name}``) in string fields are substituted before
    evaluation.

    Returns ``True`` if the precondition is satisfied.
    """
    slots = slots or {}
    cond_type = condition["type"]

    player = db.get_player()
    if player is None:
        logger.error("No player state found in database")
        return False

    current_room = player["current_room_id"]

    if cond_type == "in_room":
        room = _substitute_slots(condition["room"], slots)
        return current_room == room

    if cond_type == "has_item":
        item_ref = _substitute_slots(condition["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        # Check inventory for this item
        inventory = db.get_inventory()
        return any(i["id"] == item_id for i in inventory)

    if cond_type == "has_flag":
        flag = _substitute_slots(condition["flag"], slots)
        return db.has_flag(flag)

    if cond_type == "not_flag":
        flag = _substitute_slots(condition["flag"], slots)
        return not db.has_flag(flag)

    if cond_type == "item_in_room":
        item_ref = _substitute_slots(condition["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        room = _substitute_slots(condition["room"], slots)
        if room == "_current":
            room = current_room
        item = db.get_item(item_id)
        return item is not None and item["room_id"] == room

    if cond_type == "item_accessible":
        item_ref = _substitute_slots(condition["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        return _item_is_accessible(item_id, db, current_room)

    if cond_type == "npc_in_room":
        npc_ref = _substitute_slots(condition["npc"], slots)
        npc_id = _resolve_name_to_id(npc_ref, db)
        room = _substitute_slots(condition["room"], slots)
        if room == "_current":
            room = current_room
        npc = db.get_npc(npc_id)
        return npc is not None and npc["room_id"] == room and bool(npc["is_alive"])

    if cond_type == "lock_unlocked":
        lock_ref = _substitute_slots(condition["lock"], slots)
        lock = db.get_lock(lock_ref)
        return lock is not None and not lock["is_locked"]

    if cond_type == "puzzle_solved":
        puzzle_ref = _substitute_slots(condition["puzzle"], slots)
        puzzle = db.get_puzzle(puzzle_ref)
        return puzzle is not None and bool(puzzle["is_solved"])

    if cond_type == "health_above":
        threshold = condition["threshold"]
        return player["hp"] > threshold

    if cond_type == "container_open":
        container_ref = _substitute_slots(condition["container"], slots)
        container_id = _resolve_name_to_id(container_ref, db)
        item = db.get_item(container_id)
        if item is None or not item.get("is_container"):
            return False
        return bool(item.get("is_open")) or not bool(item.get("has_lid"))

    if cond_type == "item_in_container":
        item_ref = _substitute_slots(condition["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        container_ref = _substitute_slots(condition["container"], slots)
        container_id = _resolve_name_to_id(container_ref, db)
        row = db._fetchone(
            "SELECT 1 FROM items WHERE id = ? AND container_id = ? AND is_visible = 1",
            (item_id, container_id),
        )
        return row is not None

    if cond_type == "not_item_in_container":
        item_ref = _substitute_slots(condition["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        container_ref = _substitute_slots(condition["container"], slots)
        container_id = _resolve_name_to_id(container_ref, db)
        row = db._fetchone(
            "SELECT 1 FROM items WHERE id = ? AND container_id = ? AND is_visible = 1",
            (item_id, container_id),
        )
        return row is None

    if cond_type == "container_has_contents":
        container_ref = _substitute_slots(condition["container"], slots)
        container_id = _resolve_name_to_id(container_ref, db)
        row = db._fetchone(
            "SELECT 1 FROM items WHERE container_id = ? AND is_visible = 1 LIMIT 1",
            (container_id,),
        )
        return row is not None

    if cond_type == "container_empty":
        container_ref = _substitute_slots(condition["container"], slots)
        container_id = _resolve_name_to_id(container_ref, db)
        row = db._fetchone(
            "SELECT 1 FROM items WHERE container_id = ? AND is_visible = 1 LIMIT 1",
            (container_id,),
        )
        return row is None

    if cond_type == "has_quantity":
        item_ref = _substitute_slots(condition["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        item = db.get_item(item_id)
        if item is None:
            return False
        qty = item.get("quantity")
        if qty is None:
            return False
        return qty >= condition.get("min", 1)

    if cond_type == "toggle_state":
        item_ref = _substitute_slots(condition["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        item = db.get_item(item_id)
        if item is None:
            return False
        desired_state = _substitute_slots(condition["state"], slots)
        current_state = item.get("toggle_state") or "off"
        return current_state == desired_state

    logger.warning("Unknown precondition type: %s", cond_type)
    return False


# ---------------------------------------------------------------------------
# Effect execution
# ---------------------------------------------------------------------------

def apply_effect(
    effect: dict,
    db: GameDB,
    slots: dict[str, str] | None = None,
    command_id: str = "",
    emit_event: Callable[..., None] | None = None,
) -> list[str]:
    """Apply a single effect and return any messages to display.

    Supports all effect types from the DSL spec:
    ``move_item``, ``remove_item``, ``set_flag``, ``unlock``, ``move_player``,
    ``spawn_item``, ``change_health``, ``add_score``, ``reveal_exit``,
    ``solve_puzzle``, ``discover_quest``, ``open_container``,
    ``move_item_to_container``, ``take_item_from_container``, ``print``,
    ``consume_quantity``, ``restore_quantity``, ``set_toggle_state``,
    ``fail_quest``, ``complete_quest``, ``kill_npc``, ``remove_npc``,
    ``lock_exit``, ``hide_exit``, ``change_description``.

    Args:
        effect: The effect dict with a ``type`` field and type-specific params.
        db: The game database connection.
        slots: Resolved slot values from pattern matching.
        command_id: The parent command's ID, used for deterministic score
            entry deduplication.
        emit_event: Optional callback to emit game events from state changes.
            When provided, ``apply_effect`` calls it for ``set_flag``,
            ``move_player``, ``spawn_item`` (to inventory), and ``move_item``
            transitions that warrant events.

    Returns a list of messages (usually 0 or 1 strings).
    """
    slots = slots or {}
    effect_type = effect["type"]
    messages: list[str] = []

    player = db.get_player()
    if player is None:
        logger.error("No player state found in database")
        return messages

    current_room = player["current_room_id"]

    if effect_type == "move_item":
        item_ref = _substitute_slots(effect["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        from_loc = _substitute_slots(effect["from"], slots)
        to_loc = _substitute_slots(effect["to"], slots)

        if to_loc == "_inventory":
            db.move_item(item_id, "inventory", "")
            if emit_event is not None:
                emit_event("item_taken", item_id=item_id)
        elif to_loc == "_current":
            db.move_item(item_id, "room", current_room)
            if emit_event is not None and from_loc == "_inventory":
                emit_event("item_dropped", item_id=item_id, room_id=current_room)
        else:
            db.move_item(item_id, "room", to_loc)
            if emit_event is not None and from_loc == "_inventory":
                emit_event("item_dropped", item_id=item_id, room_id=to_loc)

    elif effect_type == "remove_item":
        item_ref = _substitute_slots(effect["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        db.remove_item(item_id)

    elif effect_type == "set_flag":
        flag = _substitute_slots(effect["flag"], slots)
        value = effect.get("value", True)
        if value is False or value == "false":
            db.clear_flag(flag)
        else:
            was_set = db.has_flag(flag)
            db.set_flag(flag, "true")
            if emit_event is not None and not was_set:
                emit_event("flag_set", flag=flag)

    elif effect_type == "unlock":
        lock_ref = _substitute_slots(effect["lock"], slots)
        lock = db.unlock(lock_ref)
        if lock and lock.get("unlock_message"):
            messages.append(lock["unlock_message"])

    elif effect_type == "move_player":
        room_ref = _substitute_slots(effect["room"], slots)
        db.update_player(current_room_id=room_ref)
        if emit_event is not None:
            emit_event("room_enter", room_id=room_ref)

    elif effect_type == "spawn_item":
        item_ref = _substitute_slots(effect["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        location = _substitute_slots(effect["location"], slots)

        if location == "_inventory":
            db.spawn_item(item_id, "inventory")
            if emit_event is not None:
                emit_event("item_taken", item_id=item_id)
        elif location == "_current":
            db.spawn_item(item_id, "room", current_room)
        else:
            target_item = db.get_item(location)
            if target_item is not None and target_item.get("is_container"):
                db.spawn_item(item_id, "container", location)
            else:
                db.spawn_item(item_id, "room", location)

    elif effect_type == "change_health":
        amount = effect["amount"]
        new_hp = max(0, min(player["max_hp"], player["hp"] + amount))
        db.update_player(hp=new_hp)

    elif effect_type == "add_score":
        points = effect["points"]
        move_number = player.get("moves", 0)
        reason = f"command:{command_id}" if command_id else f"score_{points}pts"
        db.add_score_entry(reason, points, move_number)

    elif effect_type == "reveal_exit":
        exit_ref = _substitute_slots(effect["exit"], slots)
        db.reveal_exit(exit_ref)

    elif effect_type == "solve_puzzle":
        puzzle_ref = _substitute_slots(effect["puzzle"], slots)
        db.solve_puzzle(puzzle_ref)

    elif effect_type == "discover_quest":
        quest_ref = _substitute_slots(effect["quest"], slots)
        quest = db.get_quest(quest_ref)
        if quest and quest.get("discovery_flag"):
            was_set = db.has_flag(quest["discovery_flag"])
            db.set_flag(quest["discovery_flag"], "true")
            if emit_event is not None and not was_set:
                emit_event("flag_set", flag=quest["discovery_flag"])

    elif effect_type == "open_container":
        container_ref = _substitute_slots(effect["container"], slots)
        container_id = _resolve_name_to_id(container_ref, db)
        db.open_container(container_id)

    elif effect_type == "move_item_to_container":
        item_ref = _substitute_slots(effect["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        container_ref = _substitute_slots(effect["container"], slots)
        container_id = _resolve_name_to_id(container_ref, db)
        success, reject_msg = db.move_item_to_container(item_id, container_id)
        if not success and reject_msg:
            messages.append(reject_msg)

    elif effect_type == "take_item_from_container":
        item_ref = _substitute_slots(effect["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        db.take_item_from_container(item_id)

    elif effect_type == "print":
        message = _substitute_slots(effect["message"], slots)
        messages.append(message)

    elif effect_type == "consume_quantity":
        item_ref = _substitute_slots(effect["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        amount = effect.get("amount", 1)
        db.consume_item_quantity(item_id, amount)

    elif effect_type == "restore_quantity":
        item_ref = _substitute_slots(effect["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        amount = effect.get("amount", 1)
        source_ref = effect.get("source")
        source_id = _resolve_name_to_id(source_ref, db) if source_ref else None
        db.restore_item_quantity(item_id, amount, source_id)

    elif effect_type == "set_toggle_state":
        item_ref = _substitute_slots(effect["item"], slots)
        item_id = _resolve_name_to_id(item_ref, db)
        new_state = _substitute_slots(effect["state"], slots)
        db.toggle_item_state(item_id, new_state)

    # -- Visibility / NPC movement effects ------------------------------------

    elif effect_type == "make_visible":
        item_ref = _substitute_slots(effect.get("item", ""), slots)
        item_id = _resolve_name_to_id(item_ref, db)
        db._mutate("UPDATE items SET is_visible = 1 WHERE id = ?", (item_id,))

    elif effect_type == "make_hidden":
        item_ref = _substitute_slots(effect.get("item", ""), slots)
        item_id = _resolve_name_to_id(item_ref, db)
        db._mutate("UPDATE items SET is_visible = 0 WHERE id = ?", (item_id,))

    elif effect_type == "make_takeable":
        item_ref = _substitute_slots(effect.get("item", ""), slots)
        item_id = _resolve_name_to_id(item_ref, db)
        db._mutate("UPDATE items SET is_takeable = 1 WHERE id = ?", (item_id,))

    elif effect_type == "move_npc":
        npc_ref = _substitute_slots(effect.get("npc", ""), slots)
        room_ref = _substitute_slots(effect.get("room", ""), slots)
        npc_id = _resolve_name_to_id(npc_ref, db)
        db.move_npc(npc_id, room_ref)

    # -- Quest effects -------------------------------------------------------

    elif effect_type == "fail_quest":
        quest_ref = _substitute_slots(effect["quest"], slots)
        db.update_quest_status(quest_ref, "failed")

    elif effect_type == "complete_quest":
        quest_ref = _substitute_slots(effect["quest"], slots)
        quest = db.get_quest(quest_ref)
        if quest:
            db.update_quest_status(quest_ref, "completed")
            if quest.get("completion_flag"):
                db.set_flag(quest["completion_flag"], "true")
                if emit_event is not None:
                    emit_event("flag_set", flag=quest["completion_flag"])
            if quest.get("score_value") and quest["score_value"] > 0:
                move_number = player.get("moves", 0)
                db.add_score_entry(
                    f"quest:{quest_ref}",
                    quest["score_value"],
                    move_number,
                )

    # -- Explicit NPC effects -----------------------------------------------

    elif effect_type == "kill_npc":
        npc_ref = _substitute_slots(effect["npc"], slots)
        npc_id = _resolve_name_to_id(npc_ref, db)
        db.kill_npc(npc_id)

    elif effect_type == "remove_npc":
        npc_ref = _substitute_slots(effect["npc"], slots)
        npc_id = _resolve_name_to_id(npc_ref, db)
        db.remove_npc(npc_id)

    # -- Exit effects -------------------------------------------------------

    elif effect_type == "lock_exit":
        exit_ref = _substitute_slots(effect["exit"], slots)
        db.lock_exit(exit_ref)

    elif effect_type == "hide_exit":
        exit_ref = _substitute_slots(effect["exit"], slots)
        db.hide_exit(exit_ref)

    # -- Entity description -------------------------------------------------

    elif effect_type == "change_description":
        entity_ref = _substitute_slots(effect["entity"], slots)
        entity_id = _resolve_name_to_id(entity_ref, db)
        new_text = _substitute_slots(effect["text"], slots)
        db.change_description(entity_id, new_text)

    # -- Target-aware effects (interaction response context only) -----------
    # These read _target_id / _target_type from resolved_slots, which are
    # injected by _handle_interaction in game.py.  When called outside that
    # context (no _target_id), they silently no-op.

    elif effect_type == "kill_target":
        target_id = slots.get("_target_id")
        if target_id:
            db.kill_npc(target_id)

    elif effect_type == "damage_target":
        target_id = slots.get("_target_id")
        amount = int(effect.get("amount", 10))
        if target_id:
            db.damage_npc(target_id, amount)

    elif effect_type == "destroy_target":
        target_id = slots.get("_target_id")
        target_type = slots.get("_target_type")
        if target_id and target_type == "item":
            # Scatter container contents into the current room first.
            contents = db.get_container_contents(target_id)
            if contents and current_room:
                for contained in contents:
                    db.move_item(contained["id"], "room", current_room)
            db.remove_item(target_id)

    elif effect_type == "open_target":
        target_id = slots.get("_target_id")
        target_type = slots.get("_target_type")
        if target_id and target_type == "item":
            db.open_container(target_id)

    else:
        logger.warning("Unknown effect type: %s", effect_type)

    return messages


# ---------------------------------------------------------------------------
# Main entry point — resolve a player command
# ---------------------------------------------------------------------------

def resolve_command(
    raw_input: str,
    db: GameDB,
    current_room_id: str | None = None,
    emit_event: Callable[..., None] | None = None,
) -> CommandResult:
    """Resolve a player's text input against the command database.

    This is the main entry point for the command DSL interpreter. It:

    1. Extracts the verb (first word) from the input.
    2. Fetches all enabled commands for that verb from the database,
       filtered to those whose ``context_room_ids`` include the player's
       current room (or are global).
    3. Tries each command's pattern for a match (ordered by priority, then
       specificity — fewest slots wins ties).
    4. For each pattern match, skips one-shot commands already executed.
    5. Checks all preconditions; if all pass, applies all effects atomically.
    6. Returns a ``CommandResult`` with success status, messages, and effects.

    If no command matches the input at all, returns a failure result with
    ``"I don't understand that."``.

    If a command matches but preconditions fail, returns a failure result with
    the command's ``failure_message`` (or a generic fallback).

    Args:
        raw_input: The player's raw text input.
        db: The game database connection.
        current_room_id: The player's current room ID.  When provided,
            commands scoped to other rooms are excluded from resolution.
        emit_event: Optional callback to emit game events from effects.
    """
    raw_input = raw_input.strip()
    if not raw_input:
        return CommandResult(success=False, messages=["I don't understand that."])

    # Extract verb — first whitespace-delimited word, lowercased
    parts = raw_input.split(None, 1)
    verb = parts[0].lower()

    # Fetch candidate commands, already ordered by priority DESC,
    # filtered to the player's current room scope.
    candidates = db.get_commands_for_verb(verb, current_room_id)
    if not candidates:
        return CommandResult(success=False, messages=["I don't understand that."])

    # Sort candidates: priority DESC (already from DB), then specificity
    # (fewer slots = more specific = tried first among same priority).
    # Stable sort preserves DB insertion order for fully equal candidates.
    candidates.sort(key=lambda c: (-c["priority"], _count_slots(c["pattern"])))

    # Track the best failure message from a matching-but-failing command
    best_fail_message: str | None = None
    best_fail_command_id: str = ""
    # Track done_message from an already-executed one-shot (fallback, not immediate return)
    best_done_message: str | None = None
    best_done_command_id: str = ""

    for cmd in candidates:
        # Parse preconditions and effects from JSON strings
        preconditions = json.loads(cmd["preconditions"]) if cmd["preconditions"] else []
        effects = json.loads(cmd["effects"]) if cmd["effects"] else []

        # Try pattern match
        match = parse_player_input(raw_input, cmd["pattern"])
        if match is None:
            continue

        # Resolve slot values from display names to database IDs
        resolved_slots: dict[str, str] = {}
        for slot_name, raw_value in match.items():
            resolved_slots[slot_name] = _resolve_name_to_id(raw_value, db)

        # Check one-shot: if already executed, save done_message as fallback
        if cmd["one_shot"] and cmd["executed"]:
            done_msg = cmd.get("done_message", "")
            if done_msg and best_done_message is None:
                # Verify preconditions still hold before saving (skip not_flag
                # since flags set BY this command will have changed).
                preconds_pass = all(
                    check_precondition(cond, db, resolved_slots)
                    for cond in preconditions
                    if cond.get("type") not in ("not_flag",)
                )
                if preconds_pass:
                    best_done_message = done_msg
                    best_done_command_id = cmd["id"]
            continue

        # Check all preconditions
        all_pass = all(
            check_precondition(cond, db, resolved_slots)
            for cond in preconditions
        )

        if not all_pass:
            # Record the failure message from the most specific matching command
            fail_msg = cmd.get("failure_message")
            if fail_msg:
                best_fail_message = fail_msg
                best_fail_command_id = cmd["id"]
            continue

        # All preconditions passed — success message FIRST, then effects.
        # This ensures the player reads the command's narrative before any
        # triggered consequences (flag_set cascades, quest updates, etc.).
        all_messages: list[str] = []
        if cmd.get("success_message"):
            all_messages.append(_substitute_slots(cmd["success_message"], resolved_slots))

        applied: list[str] = []
        for eff in effects:
            try:
                msgs = apply_effect(
                    eff, db, resolved_slots,
                    command_id=cmd["id"],
                    emit_event=emit_event,
                )
                applied.append(eff["type"])
                all_messages.extend(msgs)
            except Exception:
                logger.exception("Effect failed: %s", eff)
                applied.append(eff["type"])

        if not effects and not all_messages:
            fallback = cmd.get("failure_message") or "Nothing happens."
            return CommandResult(
                success=False,
                messages=[fallback],
                command_id=cmd["id"],
            )

        # Mark one-shot commands as executed
        if cmd["one_shot"]:
            db.mark_command_executed(cmd["id"])

        return CommandResult(
            success=True,
            messages=all_messages,
            effects_applied=applied,
            command_id=cmd["id"],
        )

    # An already-executed one-shot matched — show its done_message as fallback
    if best_done_message:
        return CommandResult(
            success=True,
            messages=[best_done_message],
            command_id=best_done_command_id,
        )

    # No command's preconditions passed (but at least one pattern matched)
    if best_fail_message:
        return CommandResult(
            success=False,
            messages=[best_fail_message],
            command_id=best_fail_command_id,
        )

    # No pattern matched at all
    return CommandResult(success=False, messages=["I don't understand that."])
