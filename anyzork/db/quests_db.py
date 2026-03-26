"""Quest and hint persistence methods for GameDB.

Extracted from schema.py as part of the domain-focused persistence
layer refactor.  Mixed into GameDB via multiple inheritance.
"""

from __future__ import annotations

from typing import Any


class QuestsMixin:
    """Quest CRUD, quest state, and hints."""

    # --------------------------------------------------------------- quests

    def insert_quest(self, **fields: Any) -> None:
        """Insert a single quest row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO quests ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def insert_quest_objective(self, **fields: Any) -> None:
        """Insert a single quest_objective row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO quest_objectives ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def get_all_quests(self) -> list[dict]:
        """Return all quests ordered by type (main first) then sort_order."""
        return self._fetchall(
            """
            SELECT * FROM quests
            ORDER BY CASE quest_type WHEN 'main' THEN 0 ELSE 1 END, sort_order
            """
        )

    def get_quest(self, quest_id: str) -> dict | None:
        """Return a single quest by id."""
        return self._fetchone("SELECT * FROM quests WHERE id = ?", (quest_id,))

    def get_active_quests(self) -> list[dict]:
        """Return quests with status = 'active', main quest first."""
        return self._fetchall(
            """
            SELECT * FROM quests
            WHERE status = 'active'
            ORDER BY CASE quest_type WHEN 'main' THEN 0 ELSE 1 END, sort_order
            """
        )

    def get_completed_quests(self) -> list[dict]:
        """Return quests with status = 'completed'."""
        return self._fetchall(
            "SELECT * FROM quests WHERE status = 'completed' ORDER BY sort_order"
        )

    def get_quest_objectives(self, quest_id: str) -> list[dict]:
        """Return all objectives for a quest, ordered by order_index."""
        return self._fetchall(
            "SELECT * FROM quest_objectives WHERE quest_id = ? ORDER BY order_index",
            (quest_id,),
        )

    def update_quest_status(self, quest_id: str, status: str) -> None:
        """Set quest status to 'active', 'completed', or 'failed'."""
        self._mutate(
            "UPDATE quests SET status = ? WHERE id = ?", (status, quest_id)
        )

    # -------------------------------------------------------------- hints

    def insert_hint(self, **fields: Any) -> None:
        """Insert a single hint row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO hints ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def get_all_hints(self) -> list[dict]:
        """Return all hints ordered by priority descending."""
        return self._fetchall(
            "SELECT * FROM hints ORDER BY priority DESC"
        )

    def mark_hint_used(self, hint_id: str) -> None:
        """Mark a hint as having been shown to the player."""
        self._mutate(
            "UPDATE hints SET used = 1 WHERE id = ?", (hint_id,)
        )
