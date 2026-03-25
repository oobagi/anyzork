"""DB compilation orchestrator and entity inserters."""


from __future__ import annotations

import contextlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from anyzork.db.schema import GameDB
from anyzork.importer._constants import ImportSpecError
from anyzork.importer._util import (
    bool_to_int,
    flag_value,
    json_or_none,
    json_value,
    optional_str,
    slugify_title,
)
from anyzork.importer.normalize import _normalize_import_spec
from anyzork.importer.prompt import current_prompt_system_version
from anyzork.importer.validate import _validate_exit_directions, _validate_imported_game


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
    db.initialize(
        game_name=str(game.get("title", "Imported AnyZork Game")),
        author=str(game.get("author", "Imported")),
        prompt=str(game.get("author_prompt") or game.get("prompt") or "Imported AnyZork spec"),
        prompt_system_version=current_prompt_system_version(),
        seed=str(game["seed"]) if game.get("seed") is not None else None,
        intro_text=str(game.get("intro_text", "")),
        win_text=str(game.get("win_text", "")),
        lose_text=optional_str(game.get("lose_text")),
        win_conditions=json.dumps(game.get("win_conditions", [])),
        lose_conditions=(
            json.dumps(game["lose_conditions"])
            if game.get("lose_conditions") is not None
            else None
        ),
        max_score=int(game.get("max_score", 0)),
        room_count=len(rooms),
        is_template=True,
    )
    if game.get("realism"):
        db.set_meta("realism", str(game["realism"]))


def _insert_rooms(db: GameDB, spec: dict[str, Any]) -> None:
    for room in spec.get("rooms", []):
        db.insert_room(
            id=room["id"],
            name=room["name"],
            description=room["description"],
            short_description=room.get("short_description") or room["description"],
            first_visit_text=optional_str(room.get("first_visit_text")),
            is_dark=bool_to_int(room.get("is_dark", False)),
            is_start=bool_to_int(room.get("is_start", False)),
            visited=bool_to_int(room.get("visited", False)),
        )


def _insert_exits(db: GameDB, spec: dict[str, Any]) -> None:
    for exit_row in spec.get("exits", []):
        db.insert_exit(
            id=exit_row["id"],
            from_room_id=exit_row["from_room_id"],
            to_room_id=exit_row["to_room_id"],
            direction=exit_row["direction"],
            description=optional_str(exit_row.get("description")),
            is_locked=bool_to_int(exit_row.get("is_locked", False)),
            is_hidden=bool_to_int(exit_row.get("is_hidden", False)),
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
                room_id=optional_str(item.get("room_id")),
                container_id=optional_str(item.get("container_id")),
                is_takeable=bool_to_int(item.get("is_takeable", True)),
                is_visible=bool_to_int(item.get("is_visible", True)),
                is_consumed_on_use=bool_to_int(item.get("is_consumed_on_use", False)),
                is_container=bool_to_int(item.get("is_container", False)),
                is_open=bool_to_int(item.get("is_open", False)),
                has_lid=bool_to_int(item.get("has_lid", True)),
                is_locked=bool_to_int(item.get("is_locked", False)),
                lock_message=optional_str(item.get("lock_message")),
                open_message=optional_str(item.get("open_message")),
                search_message=optional_str(item.get("search_message")),
                take_message=optional_str(item.get("take_message")),
                drop_message=optional_str(item.get("drop_message")),
                weight=item.get("weight", 1),
                category=optional_str(item.get("category")),
                room_description=optional_str(item.get("room_description")),
                read_description=optional_str(item.get("read_description")),
                key_item_id=optional_str(item.get("key_item_id")),
                consume_key=bool_to_int(item.get("consume_key", False)),
                combination=optional_str(item.get("combination")),
                unlock_message=optional_str(item.get("unlock_message")),
                accepts_items=json_or_none(item.get("accepts_items")),
                reject_message=optional_str(item.get("reject_message")),
                home_room_id=optional_str(item.get("home_room_id")),
                drop_description=optional_str(item.get("drop_description")),
                is_toggleable=bool_to_int(item.get("is_toggleable", False)),
                toggle_state=optional_str(item.get("toggle_state")),
                toggle_on_message=optional_str(item.get("toggle_on_message")),
                toggle_off_message=optional_str(item.get("toggle_off_message")),
                toggle_states=json_or_none(item.get("toggle_states")),
                toggle_messages=json_or_none(item.get("toggle_messages")),
                requires_item_id=optional_str(item.get("requires_item_id")),
                requires_message=optional_str(item.get("requires_message")),
                item_tags=json_or_none(item.get("item_tags")),
                quantity=item.get("quantity"),
                max_quantity=item.get("max_quantity"),
                quantity_unit=optional_str(item.get("quantity_unit")),
                depleted_message=optional_str(item.get("depleted_message")),
                quantity_description=optional_str(item.get("quantity_description")),
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
            is_alive=bool_to_int(npc.get("is_alive", True)),
            is_blocking=bool_to_int(npc.get("is_blocking", False)),
            blocked_exit_id=optional_str(npc.get("blocked_exit_id")),
            unblock_flag=optional_str(npc.get("unblock_flag")),
            default_dialogue=npc.get("default_dialogue", ""),
            hp=npc.get("hp"),
            damage=npc.get("damage"),
            category=optional_str(npc.get("category")),
            home_room_id=optional_str(npc.get("home_room_id")),
            room_description=optional_str(npc.get("room_description")),
            drop_description=optional_str(npc.get("drop_description")),
        )


def _insert_dialogue(db: GameDB, spec: dict[str, Any]) -> None:
    for node in spec.get("dialogue_nodes", []):
        db.insert_dialogue_node(
            id=node["id"],
            npc_id=node["npc_id"],
            content=node["content"],
            set_flags=json_or_none(node.get("set_flags")),
            effects=json_or_none(node.get("effects")),
            is_root=bool_to_int(node.get("is_root", False)),
        )

    for option in spec.get("dialogue_options", []):
        db.insert_dialogue_option(
            id=option["id"],
            node_id=option["node_id"],
            text=option["text"],
            next_node_id=optional_str(option.get("next_node_id")),
            required_flags=json_or_none(option.get("required_flags")),
            excluded_flags=json_or_none(option.get("excluded_flags")),
            required_items=json_or_none(option.get("required_items")),
            set_flags=json_or_none(option.get("set_flags")),
            sort_order=int(option.get("sort_order", 0)),
        )


def _insert_puzzles(db: GameDB, spec: dict[str, Any]) -> None:
    for puzzle in spec.get("puzzles", []):
        db.insert_puzzle(
            id=puzzle["id"],
            name=puzzle["name"],
            description=puzzle["description"],
            room_id=puzzle["room_id"],
            is_solved=bool_to_int(puzzle.get("is_solved", False)),
            solution_steps=json_value(puzzle.get("solution_steps", [])),
            hint_text=json_or_none(puzzle.get("hint_text")),
            difficulty=int(puzzle.get("difficulty", 1)),
            score_value=int(puzzle.get("score_value", 0)),
            is_optional=bool_to_int(puzzle.get("is_optional", False)),
        )


def _insert_locks(db: GameDB, spec: dict[str, Any]) -> None:
    for lock in spec.get("locks", []):
        db.insert_lock(
            id=lock["id"],
            lock_type=lock["lock_type"],
            target_exit_id=lock["target_exit_id"],
            key_item_id=optional_str(lock.get("key_item_id")),
            puzzle_id=optional_str(lock.get("puzzle_id")),
            combination=optional_str(lock.get("combination")),
            required_flags=json_or_none(lock.get("required_flags")),
            locked_message=lock.get("locked_message", "It is locked."),
            unlock_message=lock.get("unlock_message", "It unlocks."),
            is_locked=bool_to_int(lock.get("is_locked", True)),
            consume_key=bool_to_int(lock.get("consume_key", True)),
        )


def _insert_flags(db: GameDB, spec: dict[str, Any]) -> None:
    for flag in spec.get("flags", []):
        db.insert_flag(
            id=flag["id"],
            value=flag_value(flag.get("value", "false")),
            description=optional_str(flag.get("description")),
        )


def _insert_commands(db: GameDB, spec: dict[str, Any]) -> None:
    for cmd in spec.get("commands", []):
        context_room_ids = cmd.get("context_room_ids")
        context_value = None if not context_room_ids else json_value(context_room_ids)
        db.insert_command(
            id=cmd["id"],
            verb=cmd["verb"],
            pattern=cmd["pattern"],
            preconditions=json_value(cmd.get("preconditions", [])),
            effects=json_value(cmd.get("effects", [])),
            success_message=cmd.get("success_message", ""),
            failure_message=cmd.get("failure_message", ""),
            context_room_ids=context_value,
            puzzle_id=optional_str(cmd.get("puzzle_id")),
            priority=int(cmd.get("priority", 0)),
            is_enabled=bool_to_int(cmd.get("is_enabled", True)),
            one_shot=bool_to_int(cmd.get("one_shot", False)),
            executed=bool_to_int(cmd.get("executed", False)),
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
            discovery_flag=optional_str(quest.get("discovery_flag")),
            completion_flag=quest["completion_flag"],
            failure_flag=optional_str(quest.get("failure_flag")),
            fail_message=optional_str(quest.get("fail_message")),
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
                is_optional=bool_to_int(objective.get("is_optional", False)),
                bonus_score=int(objective.get("bonus_score", 0)),
            )


def _insert_interaction_responses(db: GameDB, spec: dict[str, Any]) -> None:
    for response in spec.get("interaction_responses", []):
        effects_raw = response.get("effects")
        effects_value = json_value(effects_raw) if effects_raw else None
        db.insert_interaction_response(
            id=response["id"],
            item_tag=response["item_tag"],
            target_category=response["target_category"],
            response=response["response"],
            consumes=int(response.get("consumes", 0)),
            score_change=int(response.get("score_change", 0)),
            flag_to_set=optional_str(response.get("flag_to_set")),
            effects=effects_value,
        )


def _insert_triggers(db: GameDB, spec: dict[str, Any]) -> None:
    for trigger in spec.get("triggers", []):
        db.insert_trigger(
            id=trigger["id"],
            event_type=trigger["event_type"],
            event_data=json_value(trigger.get("event_data", {})),
            preconditions=json_value(trigger.get("preconditions", [])),
            effects=json_value(trigger.get("effects", [])),
            message=optional_str(trigger.get("message")),
            priority=int(trigger.get("priority", 0)),
            one_shot=bool_to_int(trigger.get("one_shot", False)),
            executed=bool_to_int(trigger.get("executed", False)),
            is_enabled=bool_to_int(trigger.get("is_enabled", True)),
            disarm_flag=optional_str(trigger.get("disarm_flag")),
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
