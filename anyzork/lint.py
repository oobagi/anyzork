"""Spec-level static checks on parsed ZorkScript specs. No DB required."""

from __future__ import annotations

import difflib
from typing import Any

from anyzork.diagnostics import Diagnostic
from anyzork.importer._constants import ALLOWED_EXIT_DIRECTIONS
from anyzork.validation import (
    VALID_EFFECT_TYPES,
    VALID_PRECONDITION_TYPES,
    VALID_TRIGGER_EVENT_TYPES,
)


def _did_you_mean(bad_id: str, valid_ids: set[str]) -> str | None:
    if len(valid_ids) >= 50:
        return None
    matches = difflib.get_close_matches(bad_id, sorted(valid_ids), n=3, cutoff=0.6)
    if not matches:
        return None
    return "did you mean: " + ", ".join(matches) + "?"


def _ref_check(
    bad_id: str,
    valid_ids: set[str],
    category: str,
    message: str,
) -> Diagnostic:
    return Diagnostic(
        severity="error",
        category=category,
        message=message,
        line=None,
        hint=_did_you_mean(bad_id, valid_ids),
    )


def _collect_ids(spec: dict[str, Any], key: str) -> set[str]:
    return {e["id"] for e in spec.get(key, [])}


def lint_spec(spec: dict[str, Any]) -> list[Diagnostic]:
    """Run static checks on a parsed ZorkScript spec. No DB required."""
    diags: list[Diagnostic] = []

    # -- Build entity ID sets ------------------------------------------------
    room_ids = _collect_ids(spec, "rooms")
    item_ids = _collect_ids(spec, "items")
    npc_ids = _collect_ids(spec, "npcs")
    exit_ids = _collect_ids(spec, "exits")
    flag_ids = _collect_ids(spec, "flags")
    puzzle_ids = _collect_ids(spec, "puzzles")
    dialogue_node_ids = _collect_ids(spec, "dialogue_nodes")

    # -- Structure checks ----------------------------------------------------
    game = spec.get("game")
    if not game:
        diags.append(
            Diagnostic("error", "structure", "missing or empty game block", None, None)
        )
    else:
        if not game.get("title"):
            diags.append(
                Diagnostic("error", "structure", "missing game title", None, None)
            )

    player = spec.get("player")
    if not player or not player.get("start_room_id"):
        diags.append(
            Diagnostic(
                "error",
                "structure",
                "missing player block or start_room_id",
                None,
                None,
            )
        )

    if not spec.get("rooms"):
        diags.append(
            Diagnostic("error", "structure", "no rooms defined", None, None)
        )

    # Duplicate entity IDs across all entity types
    all_entity_lists = [
        "rooms", "items", "npcs", "exits", "flags", "locks",
        "puzzles", "quests", "commands", "triggers",
        "dialogue_nodes", "dialogue_options",
    ]
    seen_ids: dict[str, str] = {}
    for entity_key in all_entity_lists:
        for entity in spec.get(entity_key, []):
            eid = entity["id"]
            if eid in seen_ids:
                diags.append(
                    Diagnostic(
                        "error",
                        "structure",
                        f"duplicate entity ID '{eid}' "
                        f"(in {entity_key}, already seen in {seen_ids[eid]})",
                        None,
                        None,
                    )
                )
            else:
                seen_ids[eid] = entity_key

    # -- Reference checks ----------------------------------------------------

    # player.start_room_id
    if player and player.get("start_room_id"):
        srid = player["start_room_id"]
        if srid not in room_ids:
            diags.append(
                _ref_check(
                    srid, room_ids, "reference",
                    f"player start_room_id '{srid}' not in rooms",
                )
            )

    # Exits
    for ex in spec.get("exits", []):
        frid = ex.get("from_room_id")
        if frid and frid not in room_ids:
            diags.append(
                _ref_check(
                    frid, room_ids, "reference",
                    f"exit '{ex['id']}' from_room_id '{frid}' not in rooms",
                )
            )
        trid = ex.get("to_room_id")
        if trid and trid not in room_ids:
            diags.append(
                _ref_check(
                    trid, room_ids, "reference",
                    f"exit '{ex['id']}' to_room_id '{trid}' not in rooms",
                )
            )

    # Items
    for item in spec.get("items", []):
        rid = item.get("room_id")
        if rid and rid not in room_ids:
            diags.append(
                _ref_check(
                    rid, room_ids, "reference",
                    f"item '{item['id']}' room_id '{rid}' not in rooms",
                )
            )
        cid = item.get("container_id")
        if cid and cid not in item_ids:
            diags.append(
                _ref_check(
                    cid, item_ids, "reference",
                    f"item '{item['id']}' container_id '{cid}' not in items",
                )
            )

    # NPCs
    for npc in spec.get("npcs", []):
        rid = npc.get("room_id")
        if rid and rid not in room_ids:
            diags.append(
                _ref_check(
                    rid, room_ids, "reference",
                    f"npc '{npc['id']}' room_id '{rid}' not in rooms",
                )
            )

    # Locks
    for lock in spec.get("locks", []):
        teid = lock.get("target_exit_id")
        if teid and teid not in exit_ids:
            diags.append(
                _ref_check(
                    teid, exit_ids, "reference",
                    f"lock '{lock['id']}' target_exit_id '{teid}' not in exits",
                )
            )
        kid = lock.get("key_item_id")
        if kid and kid not in item_ids:
            diags.append(
                _ref_check(
                    kid, item_ids, "reference",
                    f"lock '{lock['id']}' key_item_id '{kid}' not in items",
                )
            )
        pid = lock.get("puzzle_id")
        if pid and pid not in puzzle_ids:
            diags.append(
                _ref_check(
                    pid, puzzle_ids, "reference",
                    f"lock '{lock['id']}' puzzle_id '{pid}' not in puzzles",
                )
            )

    # Puzzles
    for puzzle in spec.get("puzzles", []):
        rid = puzzle.get("room_id")
        if rid and rid not in room_ids:
            diags.append(
                _ref_check(
                    rid, room_ids, "reference",
                    f"puzzle '{puzzle['id']}' room_id '{rid}' not in rooms",
                )
            )

    # Quests
    for quest in spec.get("quests", []):
        cf = quest.get("completion_flag")
        if cf and cf not in flag_ids:
            diags.append(
                _ref_check(
                    cf, flag_ids, "reference",
                    f"quest '{quest['id']}' completion_flag '{cf}' not in flags",
                )
            )
        df = quest.get("discovery_flag")
        if df and df not in flag_ids:
            diags.append(
                _ref_check(
                    df, flag_ids, "reference",
                    f"quest '{quest['id']}' discovery_flag '{df}' not in flags",
                )
            )
        for obj in quest.get("objectives", []):
            ocf = obj.get("completion_flag")
            if ocf and ocf not in flag_ids:
                diags.append(
                    _ref_check(
                        ocf, flag_ids, "reference",
                        f"quest '{quest['id']}' objective completion_flag "
                        f"'{ocf}' not in flags",
                    )
                )

    # Dialogue nodes
    for node in spec.get("dialogue_nodes", []):
        nid = node.get("npc_id")
        if nid and nid not in npc_ids:
            diags.append(
                _ref_check(
                    nid, npc_ids, "reference",
                    f"dialogue_node '{node['id']}' npc_id '{nid}' not in npcs",
                )
            )

    # Dialogue options
    for opt in spec.get("dialogue_options", []):
        nid = opt.get("node_id")
        if nid and nid not in dialogue_node_ids:
            diags.append(
                _ref_check(
                    nid, dialogue_node_ids, "reference",
                    f"dialogue_option '{opt['id']}' node_id '{nid}' "
                    f"not in dialogue_nodes",
                )
            )
        nnid = opt.get("next_node_id")
        if nnid and nnid not in dialogue_node_ids:
            diags.append(
                _ref_check(
                    nnid, dialogue_node_ids, "reference",
                    f"dialogue_option '{opt['id']}' next_node_id '{nnid}' "
                    f"not in dialogue_nodes",
                )
            )

    # Command context_room_ids
    for cmd in spec.get("commands", []):
        for crid in cmd.get("context_room_ids") or []:
            if crid not in room_ids:
                diags.append(
                    _ref_check(
                        crid, room_ids, "reference",
                        f"command '{cmd['id']}' context_room_id '{crid}' "
                        f"not in rooms",
                    )
                )

    # -- DSL type checks -----------------------------------------------------
    valid_pre_hint = "valid types: " + ", ".join(sorted(VALID_PRECONDITION_TYPES))
    valid_eff_hint = "valid types: " + ", ".join(sorted(VALID_EFFECT_TYPES))
    valid_evt_hint = "valid types: " + ", ".join(sorted(VALID_TRIGGER_EVENT_TYPES))

    # Commands: preconditions and effects
    for cmd in spec.get("commands", []):
        for pre in cmd.get("preconditions", []):
            ptype = pre.get("type")
            if ptype and ptype not in VALID_PRECONDITION_TYPES:
                diags.append(
                    Diagnostic(
                        "error", "dsl",
                        f"command '{cmd['id']}' unknown precondition type '{ptype}'",
                        None, valid_pre_hint,
                    )
                )
        for eff in cmd.get("effects", []):
            etype = eff.get("type")
            if etype and etype not in VALID_EFFECT_TYPES:
                diags.append(
                    Diagnostic(
                        "error", "dsl",
                        f"command '{cmd['id']}' unknown effect type '{etype}'",
                        None, valid_eff_hint,
                    )
                )

    # Triggers: event_type, preconditions, effects
    for trigger in spec.get("triggers", []):
        evt = trigger.get("event_type")
        if evt and evt not in VALID_TRIGGER_EVENT_TYPES:
            diags.append(
                Diagnostic(
                    "error", "dsl",
                    f"trigger '{trigger['id']}' unknown event type '{evt}'",
                    None, valid_evt_hint,
                )
            )
        for pre in trigger.get("preconditions", []):
            ptype = pre.get("type")
            if ptype and ptype not in VALID_PRECONDITION_TYPES:
                diags.append(
                    Diagnostic(
                        "error", "dsl",
                        f"trigger '{trigger['id']}' unknown precondition "
                        f"type '{ptype}'",
                        None, valid_pre_hint,
                    )
                )
        for eff in trigger.get("effects", []):
            etype = eff.get("type")
            if etype and etype not in VALID_EFFECT_TYPES:
                diags.append(
                    Diagnostic(
                        "error", "dsl",
                        f"trigger '{trigger['id']}' unknown effect type '{etype}'",
                        None, valid_eff_hint,
                    )
                )

    # -- Exit direction checks -----------------------------------------------
    allowed_dirs = set(ALLOWED_EXIT_DIRECTIONS)
    for ex in spec.get("exits", []):
        direction = ex.get("direction")
        if direction and direction not in allowed_dirs:
            diags.append(
                Diagnostic(
                    "error", "reference",
                    f"exit '{ex['id']}' direction '{direction}' not allowed",
                    None,
                    "allowed directions: " + ", ".join(ALLOWED_EXIT_DIRECTIONS),
                )
            )

    # -- Spatial checks ------------------------------------------------------
    # Build set of (from, to) pairs to detect one-way exits
    exit_pairs: set[tuple[str, str]] = set()
    for ex in spec.get("exits", []):
        frid = ex.get("from_room_id")
        trid = ex.get("to_room_id")
        if frid and trid:
            exit_pairs.add((frid, trid))

    for frid, trid in sorted(exit_pairs):
        if (trid, frid) not in exit_pairs:
            diags.append(
                Diagnostic(
                    "warning", "spatial",
                    f"one-way exit from '{frid}' to '{trid}' (no reverse exit)",
                    None, None,
                )
            )

    # -- Sort: errors first, then warnings -----------------------------------
    severity_order = {"error": 0, "warning": 1}
    diags.sort(key=lambda d: severity_order.get(d.severity, 2))

    return diags
