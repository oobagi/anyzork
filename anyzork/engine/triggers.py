"""Trigger system mixin for GameEngine.

Handles event emission, trigger evaluation, and event processing
including turn-count and scheduled triggers.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


class TriggerMixin:
    """Event/trigger handling methods extracted from GameEngine."""

    def _emit_event(self, event_type: str, **event_data: str) -> None:
        """Emit a game event and evaluate matching triggers.

        Events are queued and processed iteratively to prevent deep
        recursion from flag cascades.  Re-entrant calls (e.g. a trigger
        effect setting a flag that emits another ``flag_set`` event) are
        appended to the queue and processed by the outer loop.

        A hard limit of 20 queue-drain iterations prevents infinite loops
        from circular flag dependencies.
        """
        self._event_queue.append((event_type, event_data))

        if self._processing_events:
            return  # will be processed by the outer loop

        self._processing_events = True
        iterations = 0
        try:
            while self._event_queue and iterations < 20:
                ev_type, ev_data = self._event_queue.pop(0)
                self._process_event(ev_type, ev_data)
                iterations += 1
            if self._event_queue:
                logger.warning(
                    "Event cascade limit (20) reached — %d events discarded: %s",
                    len(self._event_queue),
                    self._event_queue,
                )
                self._event_queue.clear()
        finally:
            self._processing_events = False

    def _process_event(self, event_type: str, event_data: dict[str, str]) -> None:
        """Find and execute all triggers matching this event."""
        from anyzork.engine.commands import evaluate_rule

        db = self.db

        # Handle force_dialogue as a special engine-level event.
        # This initiates a dialogue tree at a specific node for an NPC.
        if event_type == "force_dialogue":
            self._handle_force_dialogue(
                event_data.get("npc_id", ""),
                event_data.get("node_id", ""),
            )
            return

        # 1. Fetch candidate triggers (enabled, non-executed one-shots).
        triggers = db.get_triggers_for_event(event_type)

        # 2. Filter by event_data partial match.
        matching: list[dict] = []
        for trigger in triggers:
            try:
                trigger_data = json.loads(trigger["event_data"]) if trigger["event_data"] else {}
            except (json.JSONDecodeError, TypeError):
                trigger_data = {}
            if all(event_data.get(k) == v for k, v in trigger_data.items()):
                matching.append(trigger)

        # 3. Already sorted by priority DESC from the query, but ensure it.
        matching.sort(key=lambda t: -t["priority"])

        # 4. Evaluate each trigger.
        for trigger in matching:
            # Double-check one-shot execution (defensive).
            if trigger["one_shot"] and trigger["executed"]:
                continue

            # Check disarm_flag — if set, this trap has been disarmed.
            disarm_flag = trigger.get("disarm_flag")
            if disarm_flag and db.has_flag(disarm_flag):
                continue

            # Evaluate preconditions and apply effects via unified pipeline.
            result = evaluate_rule(
                db=db,
                preconditions=trigger["preconditions"],
                effects=trigger["effects"],
                command_id=f"trigger:{trigger['id']}",
                emit_event=self._emit_event,
            )
            if not result.passed:
                continue

            # Fire the trigger — display message, then effect messages.
            if trigger.get("message"):
                self.console.print(trigger["message"])

            for msg in result.messages:
                self.console.print(msg)

            # Mark one-shot as executed.
            if trigger["one_shot"]:
                db.mark_trigger_executed(trigger["id"])

    def _check_turn_count_triggers(self, current_move: int) -> None:
        """Emit a synthetic turn_count event so _process_event handles matching."""
        self._emit_event("turn_count", n=str(current_move))

    def _check_scheduled_triggers(self, current_move: int) -> None:
        """Fire all scheduled triggers whose deadline has arrived."""
        db = self.db
        due = db.get_due_scheduled_triggers(current_move)
        for entry in due:
            trigger_id = entry["trigger_id"]
            db.remove_scheduled_trigger(trigger_id)
            # Emit a 'scheduled' event so _process_event picks up the matching trigger
            self._emit_event("scheduled", trigger_id=trigger_id)
