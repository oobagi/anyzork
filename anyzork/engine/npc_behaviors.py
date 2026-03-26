"""NPC behavior system mixin for GameEngine.

Handles autonomous NPC actions that fire each turn based on
preconditions and effects.
"""

from __future__ import annotations

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
        from anyzork.engine.commands import evaluate_rule

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
                # Evaluate preconditions and apply effects via unified pipeline.
                result = evaluate_rule(
                    db=db,
                    preconditions=behavior["preconditions"],
                    effects=behavior["effects"],
                    command_id=f"npc_behavior:{npc_id}:{behavior['id']}",
                    emit_event=self._emit_event,
                )
                if not result.passed:
                    continue

                # Only show messages for NPCs in the player's room
                if npc_room == player_room:
                    for msg in result.messages:
                        self.console.print(msg)

                # Show behavior message only for NPCs in the player's room
                if behavior.get("message") and npc_room == player_room:
                    self.console.print(behavior["message"])

                # Mark one-shot as executed
                if behavior["one_shot"]:
                    db.mark_npc_behavior_executed(behavior["id"])
