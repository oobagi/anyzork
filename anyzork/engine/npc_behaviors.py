"""NPC behavior system mixin for GameEngine.

Handles autonomous NPC actions that fire each turn based on
preconditions and effects.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


class NPCBehaviorMixin:
    """NPC autonomous behavior methods extracted from GameEngine."""

    def _process_npc_behaviors(self) -> None:
        """Process all NPC autonomous behaviors for this turn.

        For each living NPC with behaviors:
        1. Check preconditions — if all pass, apply effects and show message.
        2. Only show messages for NPCs in the same room as the player.
        3. One-shot behaviors are marked executed after firing.
        """
        from anyzork.engine.commands import apply_effect, check_precondition

        db = self.db
        player = db.get_player()
        if player is None:
            return
        player_room = player["current_room_id"]

        # Get all living NPCs that have behaviors
        all_npcs = db.get_npcs_with_active_behaviors()

        for npc_row in all_npcs:
            npc_id = npc_row["id"]
            # NPC room is snapshot before effects — departure messages show,
            # arrival messages don't.
            npc_room = npc_row["room_id"]
            behaviors = db.get_npc_behaviors(npc_id)

            for behavior in behaviors:
                # Check preconditions
                try:
                    preconditions = (
                        json.loads(behavior["preconditions"])
                        if behavior["preconditions"]
                        else []
                    )
                except (json.JSONDecodeError, TypeError):
                    preconditions = []

                all_pass = all(
                    check_precondition(cond, db) for cond in preconditions
                )
                if not all_pass:
                    continue

                # Apply effects
                try:
                    effects = (
                        json.loads(behavior["effects"])
                        if behavior["effects"]
                        else []
                    )
                except (json.JSONDecodeError, TypeError):
                    effects = []

                for effect in effects:
                    try:
                        msgs = apply_effect(
                            effect, db,
                            command_id=f"npc_behavior:{npc_id}:{behavior['id']}",
                            emit_event=self._emit_event,
                        )
                        # Only show effect messages for NPCs in the player's room
                        if npc_room == player_room:
                            for msg in msgs:
                                self.console.print(msg)
                    except Exception:
                        logger.exception(
                            "NPC behavior effect failed: %s for NPC %s",
                            effect, npc_id,
                        )

                # Show behavior message only for NPCs in the player's room
                if behavior.get("message") and npc_room == player_room:
                    self.console.print(behavior["message"])

                # Mark one-shot as executed
                if behavior["one_shot"]:
                    db.mark_npc_behavior_executed(behavior["id"])
