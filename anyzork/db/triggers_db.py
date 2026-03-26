"""Trigger persistence methods for GameDB.

Extracted from schema.py as part of the domain-focused persistence
layer refactor.  Mixed into GameDB via multiple inheritance.
"""

from __future__ import annotations

from typing import Any


class TriggersMixin:
    """Trigger storage, scheduled triggers, and event queries."""

    # ------------------------------------------------------------ triggers

    def insert_trigger(self, **fields: Any) -> None:
        """Insert a single trigger row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO triggers ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def get_triggers_for_event(self, event_type: str) -> list[dict]:
        """Return all enabled, non-executed-one-shot triggers for *event_type*.

        Ordered by ``priority`` descending.  One-shot triggers that have
        already fired (``executed = 1``) are excluded.
        """
        return self._fetchall(
            "SELECT * FROM triggers WHERE event_type = ? AND is_enabled = 1 "
            "AND (one_shot = 0 OR executed = 0) ORDER BY priority DESC",
            (event_type,),
        )

    def mark_trigger_executed(self, trigger_id: str) -> None:
        """Mark a one-shot trigger as executed so it won't fire again."""
        self._mutate(
            "UPDATE triggers SET executed = 1 WHERE id = ?",
            (trigger_id,),
        )

    # --------------------------------------------------------- scheduled triggers

    def schedule_trigger(self, trigger_id: str, fire_on_move: int) -> None:
        """Schedule a trigger to fire on a specific move number.

        Uses INSERT OR REPLACE so rescheduling overwrites the old deadline.
        """
        self._mutate(
            """
            INSERT OR REPLACE INTO scheduled_triggers (trigger_id, fire_on_move)
            VALUES (?, ?)
            """,
            (trigger_id, fire_on_move),
        )

    def get_due_scheduled_triggers(self, current_move: int) -> list[dict]:
        """Return scheduled triggers whose deadline has arrived."""
        return self._fetchall(
            "SELECT * FROM scheduled_triggers WHERE fire_on_move <= ?",
            (current_move,),
        )

    def remove_scheduled_trigger(self, trigger_id: str) -> None:
        """Remove a scheduled trigger entry after it fires."""
        self._mutate(
            "DELETE FROM scheduled_triggers WHERE trigger_id = ?",
            (trigger_id,),
        )
