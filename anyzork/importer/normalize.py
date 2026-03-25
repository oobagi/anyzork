"""Import-spec normalization: canonical field names and structure inference."""


from __future__ import annotations

from typing import Any

from anyzork.importer._constants import (
    IMPORT_SPEC_FORMAT,
    PUBLIC_INTERACTION_TYPES,
    ImportSpecError,
)
from anyzork.importer._util import optional_str, slugify_title


def _normalize_import_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Normalize user-authored import JSON into the compiler's internal shape."""
    import_format = spec.get("format")
    if import_format is not None and import_format != IMPORT_SPEC_FORMAT:
        raise ImportSpecError(
            f"Unsupported import format {import_format!r}; expected {IMPORT_SPEC_FORMAT!r}."
        )

    spec["format"] = IMPORT_SPEC_FORMAT
    spec.setdefault("items", [])
    spec.setdefault("npcs", [])
    spec.setdefault("dialogue_nodes", [])
    spec.setdefault("dialogue_options", [])
    spec.setdefault("locks", [])
    spec.setdefault("puzzles", [])
    spec.setdefault("flags", [])
    spec.setdefault("interactions", [])
    spec.setdefault("commands", [])
    spec.setdefault("quests", [])
    spec.setdefault("interaction_responses", [])
    spec.setdefault("triggers", [])

    _normalize_npcs(spec)
    _normalize_locks(spec)
    _normalize_puzzles(spec)
    _normalize_public_interactions(spec)
    _normalize_commands(spec)
    _normalize_interaction_responses(spec)
    _normalize_triggers(spec)
    _normalize_quests(spec)
    return spec


def _normalize_npcs(spec: dict[str, Any]) -> None:
    for npc in spec.get("npcs", []):
        if "is_alive" not in npc:
            npc["is_alive"] = True


def _normalize_locks(spec: dict[str, Any]) -> None:
    for lock in spec.get("locks", []):
        if lock.get("lock_type") is None:
            if lock.get("required_flags"):
                lock["lock_type"] = "flag"
            elif lock.get("key_item_id"):
                lock["lock_type"] = "key"
            else:
                lock["lock_type"] = "flag"


def _normalize_puzzles(spec: dict[str, Any]) -> None:
    commands = spec.get("commands", [])
    interactions = spec.get("interactions", [])
    items_by_id = {item["id"]: item for item in spec.get("items", []) if item.get("id")}
    room_ids = {room["id"] for room in spec.get("rooms", []) if room.get("id")}

    # Determine a fallback room: the start room or the first room.
    fallback_room_id: str | None = None
    player = spec.get("player", {})
    if player.get("start_room_id"):
        fallback_room_id = str(player["start_room_id"])
    if not fallback_room_id:
        for room in spec.get("rooms", []):
            if room.get("is_start"):
                fallback_room_id = str(room["id"])
                break
    if not fallback_room_id and spec.get("rooms"):
        fallback_room_id = str(spec["rooms"][0]["id"])

    for puzzle in spec.get("puzzles", []):
        if puzzle.get("room_id") is None:
            inferred_room_id = _infer_puzzle_room_id(
                puzzle, commands, interactions, items_by_id, room_ids,
            )
            puzzle["room_id"] = inferred_room_id or fallback_room_id


def _infer_puzzle_room_id(
    puzzle: dict[str, Any],
    commands: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
    items_by_id: dict[str, dict[str, Any]],
    room_ids: set[str],
) -> str | None:
    puzzle_id = puzzle.get("id")

    for item_id in puzzle.get("required_items", []):
        room_id = optional_str(items_by_id.get(item_id, {}).get("room_id"))
        if room_id:
            return room_id

    # Check interactions that solve this puzzle via solve_puzzle_ids.
    if puzzle_id:
        for interaction in interactions:
            solve_ids = interaction.get("solve_puzzle_ids") or []
            if puzzle_id in solve_ids:
                ctx = interaction.get("context_room_ids") or []
                if ctx:
                    return str(ctx[0])
                room_id = optional_str(interaction.get("room_id"))
                if room_id:
                    return room_id

    set_flags = {str(flag_id) for flag_id in puzzle.get("set_flags", [])}
    required_flags = {str(flag_id) for flag_id in puzzle.get("required_flags", [])}
    for command in commands:
        context_room_ids = command.get("context_room_ids") or []
        if not context_room_ids:
            continue
        command_effects = command.get("effects") or []
        if any(
            effect.get("type") == "set_flag"
            and str(effect.get("flag_id")) in set_flags
            for effect in command_effects
        ):
            return str(context_room_ids[0])
        command_preconditions = command.get("preconditions") or []
        if any(
            pre.get("type") in {"has_flag", "flag_true"}
            and str(pre.get("flag_id") or pre.get("flag")) in required_flags
            for pre in command_preconditions
        ):
            return str(context_room_ids[0])

    for step in puzzle.get("solution_steps", []):
        if not isinstance(step, str):
            continue
        words = step.strip().split()
        if len(words) >= 3 and words[0].lower() == "go" and words[1].lower() == "to":
            candidate = slugify_title(" ".join(words[2:]))
            if candidate in room_ids:
                return candidate

    return None


def _normalize_public_interactions(spec: dict[str, Any]) -> None:
    commands = spec.setdefault("commands", [])
    interactions = spec.get("interactions", [])
    if not interactions:
        return

    item_names = {
        item["id"]: item["name"]
        for item in spec.get("items", [])
        if item.get("id") and item.get("name")
    }
    npc_names = {
        npc["id"]: npc["name"]
        for npc in spec.get("npcs", [])
        if npc.get("id") and npc.get("name")
    }
    npc_rooms = {
        npc["id"]: npc.get("room_id")
        for npc in spec.get("npcs", [])
        if npc.get("id")
    }
    item_rooms = {
        item["id"]: item.get("room_id")
        for item in spec.get("items", [])
        if item.get("id")
    }

    for interaction in interactions:
        interaction_type = str(interaction.get("type", "")).strip().lower()
        if interaction_type not in PUBLIC_INTERACTION_TYPES:
            allowed_types = ", ".join(PUBLIC_INTERACTION_TYPES)
            raise ImportSpecError(
                "Unsupported interaction type "
                f"{interaction.get('type')!r}; expected one of {allowed_types}."
            )

        context_room_ids = _interaction_context_room_ids(
            interaction,
            item_rooms=item_rooms,
            npc_rooms=npc_rooms,
        )
        command_text = _interaction_command_text(
            interaction,
            item_names=item_names,
            npc_names=npc_names,
        )
        verb = command_text.split(None, 1)[0].lower()

        preconditions: list[dict[str, Any]] = []
        preconditions.extend(
            {"type": "has_flag", "flag": flag_id}
            for flag_id in interaction.get("required_flags", [])
        )
        preconditions.extend(
            {"type": "not_flag", "flag": flag_id}
            for flag_id in interaction.get("excluded_flags", [])
        )
        preconditions.extend(
            {"type": "has_item", "item": item_id}
            for item_id in interaction.get("required_items", [])
        )

        item_id = optional_str(interaction.get("item_id"))
        npc_id = optional_str(interaction.get("npc_id"))
        container_id = optional_str(interaction.get("container_id"))

        if interaction_type == "read_item" and item_id:
            preconditions.append({"type": "item_accessible", "item": item_id})
        elif interaction_type in {"show_item_to_npc", "give_item_to_npc"}:
            if item_id:
                preconditions.append({"type": "has_item", "item": item_id})
            if npc_id:
                preconditions.append({"type": "npc_in_room", "npc": npc_id, "room": "_current"})
        elif interaction_type == "search_container" and container_id:
            preconditions.append({"type": "item_accessible", "item": container_id})
        elif interaction_type == "travel_action" and interaction.get("move_player_room_id") is None:
            raise ImportSpecError(
                f"Interaction {interaction.get('id')!r} must define move_player_room_id."
            )

        effects: list[dict[str, Any]] = []
        effects.extend(
            {"type": "set_flag", "flag": flag_id, "value": True}
            for flag_id in interaction.get("set_flags", [])
        )
        effects.extend(
            {"type": "spawn_item", "item": item_id, "location": "_inventory"}
            for item_id in interaction.get("give_items", [])
        )
        effects.extend(
            {"type": "unlock", "lock": lock_id}
            for lock_id in interaction.get("unlock_lock_ids", [])
        )
        effects.extend(
            {"type": "reveal_exit", "exit": exit_id}
            for exit_id in interaction.get("reveal_exit_ids", [])
        )
        effects.extend(
            {"type": "discover_quest", "quest": quest_id}
            for quest_id in interaction.get("discover_quest_ids", [])
        )
        effects.extend(
            {"type": "solve_puzzle", "puzzle": puzzle_id}
            for puzzle_id in interaction.get("solve_puzzle_ids", [])
        )
        if interaction.get("move_player_room_id"):
            effects.append(
                {"type": "move_player", "room": interaction["move_player_room_id"]}
            )
        score_value = interaction.get("score_value")
        if score_value:
            effects.append({"type": "add_score", "points": int(score_value)})
        consume_item = bool(interaction.get("consume_item", True))
        if item_id and interaction_type == "give_item_to_npc" and consume_item:
            effects.append({"type": "remove_item", "item": item_id})

        commands.append(
            {
                "id": interaction["id"],
                "verb": verb,
                "pattern": command_text,
                "preconditions": preconditions,
                "effects": effects,
                "success_message": str(interaction.get("success_message") or ""),
                "failure_message": _default_interaction_failure(interaction_type, interaction),
                "context_room_ids": context_room_ids,
                "priority": int(interaction.get("priority", 10)),
                "one_shot": bool(interaction.get("one_shot", False)),
            }
        )


def _interaction_context_room_ids(
    interaction: dict[str, Any],
    *,
    item_rooms: dict[str, Any],
    npc_rooms: dict[str, Any],
) -> list[str]:
    context_room_ids = interaction.get("context_room_ids") or []
    if context_room_ids:
        return [str(room_id) for room_id in context_room_ids if room_id]

    room_id = optional_str(interaction.get("room_id"))
    if room_id:
        return [room_id]

    npc_id = optional_str(interaction.get("npc_id"))
    if npc_id and npc_rooms.get(npc_id):
        return [str(npc_rooms[npc_id])]

    item_id = optional_str(interaction.get("item_id"))
    if item_id and item_rooms.get(item_id):
        return [str(item_rooms[item_id])]

    return []


def _interaction_command_text(
    interaction: dict[str, Any],
    *,
    item_names: dict[str, str],
    npc_names: dict[str, str],
) -> str:
    command = str(interaction.get("command") or "").strip().lower()
    if command:
        return command

    interaction_type = str(interaction.get("type", "")).strip().lower()
    item_id = optional_str(interaction.get("item_id"))
    npc_id = optional_str(interaction.get("npc_id"))
    container_id = optional_str(interaction.get("container_id"))

    item_text = str(item_names.get(item_id, item_id or "item")).strip().lower()
    npc_text = str(npc_names.get(npc_id, npc_id or "npc")).strip().lower()
    container_text = str(item_names.get(container_id, container_id or "container")).strip().lower()

    if interaction_type == "read_item":
        return f"read {item_text}"
    if interaction_type == "show_item_to_npc":
        return f"show {item_text} to {npc_text}"
    if interaction_type == "give_item_to_npc":
        return f"give {item_text} to {npc_text}"
    if interaction_type == "search_container":
        return f"search {container_text}"
    if interaction_type == "search_room":
        return "search room"
    if interaction_type == "travel_action":
        return "travel"
    raise ImportSpecError(f"Interaction {interaction.get('id')!r} is missing a command.")


def _default_interaction_failure(
    interaction_type: str,
    interaction: dict[str, Any],
) -> str:
    message = optional_str(interaction.get("failure_message"))
    if message:
        return message

    return {
        "read_item": "You have nothing like that to read.",
        "show_item_to_npc": "That doesn't seem useful right now.",
        "give_item_to_npc": "You can't hand that over right now.",
        "search_room": "You don't find anything new.",
        "search_container": "You don't find anything else inside.",
        "travel_action": "You can't go that way yet.",
    }.get(interaction_type, "Nothing happens.")


def _normalize_commands(spec: dict[str, Any]) -> None:
    for cmd in spec.get("commands", []):
        if "pattern" not in cmd:
            cmd["pattern"] = cmd.get("verb", "command")
        cmd.setdefault("failure_message", "Nothing happens.")


def _normalize_interaction_responses(spec: dict[str, Any]) -> None:
    # Keep only real interaction responses (with item_tag).
    real_responses: list[dict[str, Any]] = []
    for response in spec.get("interaction_responses", []):
        if response.get("item_tag"):
            real_responses.append(response)
    spec["interaction_responses"] = real_responses


def _normalize_triggers(spec: dict[str, Any]) -> None:
    for trigger in spec.get("triggers", []):
        trigger.setdefault("event_data", {})
        trigger.setdefault("disarm_flag", None)
        if not trigger["event_data"].get("room_id") and trigger.get("room_id"):
            trigger["event_data"]["room_id"] = trigger.get("room_id")
        if (
            trigger["event_type"] == "flag_set"
            and not trigger["event_data"].get("flag")
            and not trigger["event_data"].get("flag_id")
            and trigger.get("flag_id")
        ):
            trigger["event_data"]["flag"] = trigger.get("flag_id")
        if trigger["event_type"] == "room_enter" and not trigger["event_data"].get("room_id"):
            context_room_ids = trigger.get("context_room_ids") or []
            if context_room_ids:
                trigger["event_data"]["room_id"] = context_room_ids[0]
        if (
            trigger["event_type"] == "flag_set"
            and not trigger["event_data"].get("flag_id")
            and not trigger["event_data"].get("flag")
        ):
            for pre in trigger.get("preconditions", []):
                pre_type = str(pre.get("type", "")).strip().lower()
                if pre_type in {"has_flag", "flag_true"}:
                    trigger["event_data"]["flag"] = pre.get("flag_id") or pre.get("flag")
                    break

        normalized_effects: list[dict[str, Any]] = []
        for effect in trigger.get("effects", []):
            if str(effect.get("type", "")).strip().lower() == "message":
                if not trigger.get("message"):
                    trigger["message"] = effect.get("text") or effect.get("message")
                continue
            normalized_effects.append(effect)
        trigger["effects"] = normalized_effects
        if not trigger.get("message"):
            trigger["message"] = trigger.get("text") or trigger.get("response_text")


def _normalize_quests(spec: dict[str, Any]) -> None:
    """Fill in derived quest and objective flags, keeping them unique."""
    quests = spec.get("quests", [])
    flags = spec.setdefault("flags", [])
    existing_flag_ids = {
        str(flag["id"])
        for flag in flags
        if isinstance(flag, dict) and flag.get("id") is not None
    }
    generated_flags: list[dict[str, Any]] = []

    for index, quest in enumerate(quests):
        if "quest_type" not in quest:
            if "is_main_quest" in quest:
                quest["quest_type"] = "main" if quest.get("is_main_quest") else "side"
            else:
                quest["quest_type"] = "main" if index == 0 else "side"
        quest.setdefault("score_value", 0)
        quest.setdefault("sort_order", index)

    if not any(quest.get("quest_type") == "main" for quest in quests):
        quests.insert(
            0,
            {
                "id": "main_quest",
                "name": "Main Quest",
                "description": "Complete the adventure.",
                "quest_type": "main",
                "discovery_flag": None,
                "completion_flag": "main_quest_complete",
                "score_value": 0,
                "sort_order": 0,
                "objectives": [
                    {
                        "id": "complete_the_adventure",
                        "description": "Complete the adventure.",
                        "completion_flag": "main_quest_complete_adventure",
                        "order_index": 0,
                        "is_optional": 0,
                        "bonus_score": 0,
                    }
                ],
            },
        )

    for quest in quests:
        quest_id = str(quest["id"])
        completion_flag = optional_str(quest.get("completion_flag"))
        if completion_flag is None:
            completion_flag = f"{quest_id}_complete"
            quest["completion_flag"] = completion_flag
        if completion_flag not in existing_flag_ids:
            generated_flags.append(
                {
                    "id": completion_flag,
                    "value": "false",
                    "description": f"Auto-generated completion flag for quest {quest_id}.",
                }
            )
            existing_flag_ids.add(completion_flag)

        # Auto-generate failure_flag entry if provided but not in flags table.
        failure_flag = optional_str(quest.get("failure_flag"))
        if failure_flag and failure_flag not in existing_flag_ids:
            generated_flags.append(
                {
                    "id": failure_flag,
                    "value": "false",
                    "description": f"Auto-generated failure flag for quest {quest_id}.",
                }
            )
            existing_flag_ids.add(failure_flag)

        objectives = quest.setdefault("objectives", [])
        for objective in objectives:
            objective_id = str(objective["id"])
            if objective.get("completion_flag") is None:
                candidate_flag = None
                set_flags = objective.get("set_flags") or []
                required_flags = objective.get("required_flags") or []
                if set_flags:
                    candidate_flag = str(set_flags[0])
                elif len(required_flags) == 1:
                    candidate_flag = str(required_flags[0])
                if candidate_flag:
                    objective["completion_flag"] = candidate_flag
            objective.setdefault("order_index", 0)
            objective.setdefault("is_optional", 0)
            objective.setdefault("bonus_score", 0)
            objective_completion_flag = optional_str(objective.get("completion_flag"))
            if objective_completion_flag is None:
                objective_completion_flag = f"{quest_id}_{objective_id}_complete"
                objective["completion_flag"] = objective_completion_flag
            if objective_completion_flag not in existing_flag_ids:
                generated_flags.append(
                    {
                        "id": objective_completion_flag,
                        "value": "false",
                        "description": (
                            f"Auto-generated completion flag for quest objective {objective_id}."
                        ),
                    }
                )
                existing_flag_ids.add(objective_completion_flag)

    flags.extend(generated_flags)
