"""Player state persistence methods for GameDB.

Extracted from schema.py as part of the domain-focused persistence
layer refactor.  Mixed into GameDB via multiple inheritance.
"""

from __future__ import annotations

from typing import Any


class PlayerMixin:
    """Player state, flags, variables, score entries, and saves."""

    # --------------------------------------------------------------- player

    def get_player(self) -> dict | None:
        """Return the player state row."""
        return self._fetchone("SELECT * FROM player WHERE id = 1")

    def update_player(self, **kwargs: Any) -> None:
        """Update one or more player state fields.

        Only the following keys are accepted: ``current_room_id``, ``hp``,
        ``max_hp``, ``score``, ``moves``, ``game_state``.
        """
        valid = {"current_room_id", "hp", "max_hp", "score", "moves", "game_state"}
        bad = set(kwargs) - valid
        if bad:
            raise KeyError(f"Invalid player fields: {bad}")
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = tuple(kwargs.values())
        self._mutate(f"UPDATE player SET {sets} WHERE id = 1", vals)

    def init_player(self, start_room_id: str, hp: int = 100, max_hp: int = 100) -> None:
        """Insert the initial player row.  Idempotent (uses INSERT OR REPLACE)."""
        self._mutate(
            """
            INSERT OR REPLACE INTO player
                (id, current_room_id, hp, max_hp, score, moves, game_state)
            VALUES (1, ?, ?, ?, 0, 0, 'playing')
            """,
            (start_room_id, hp, max_hp),
        )

    def get_inventory(self) -> list[dict]:
        """Shorthand for items currently in the player's inventory."""
        return self.get_items_in("inventory", "")

    # ---------------------------------------------------------------- flags

    def set_flag(self, name: str, value: str = "true", move: int | None = None) -> None:
        """Set a flag value.  Creates the flag if it does not exist."""
        self._mutate(
            """
            INSERT INTO flags (id, value) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET value = excluded.value
            """,
            (name, value),
        )

    def get_flag(self, name: str) -> str | None:
        """Return a flag's value, or ``None`` if the flag does not exist."""
        row = self._fetchone("SELECT value FROM flags WHERE id = ?", (name,))
        return row["value"] if row else None

    def has_flag(self, name: str) -> bool:
        """Return ``True`` if the flag exists and its value is ``'true'``."""
        val = self.get_flag(name)
        return val == "true"

    def clear_flag(self, name: str) -> None:
        """Set a flag's value to ``'false'``."""
        self._mutate(
            "UPDATE flags SET value = 'false' WHERE id = ?", (name,)
        )

    # ----------------------------------------------------------- variables

    def get_var(self, name: str) -> int:
        """Return a variable's value, or ``0`` if the variable does not exist."""
        row = self._fetchone("SELECT value FROM variables WHERE name = ?", (name,))
        return row["value"] if row else 0

    def set_var(self, name: str, value: int) -> None:
        """Set a variable to a specific integer value.

        Creates the variable if it does not exist.
        """
        self._mutate(
            """
            INSERT INTO variables (name, value) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET value = excluded.value
            """,
            (name, value),
        )

    def change_var(self, name: str, delta: int) -> None:
        """Increment (or decrement) a variable by *delta*.

        Creates the variable if it does not exist.
        """
        self._mutate(
            """
            INSERT INTO variables (name, value) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET value = variables.value + excluded.value
            """,
            (name, delta),
        )

    # --------------------------------------------------------- score entries

    def add_score_entry(self, reason: str, value: int, move_number: int) -> bool:
        """Record a scoring event.  Returns ``False`` if already scored.

        Prevents double-scoring by checking for a duplicate ``reason``.
        Also increments the player's ``score``.
        """
        existing = self._fetchone(
            "SELECT id FROM score_entries WHERE reason = ?", (reason,)
        )
        if existing:
            return False
        self._conn.execute(
            "INSERT INTO score_entries (reason, value, move_number) VALUES (?, ?, ?)",
            (reason, value, move_number),
        )
        self._conn.execute(
            "UPDATE player SET score = score + ? WHERE id = 1", (value,)
        )
        self._conn.commit()
        return True

    def get_score_breakdown(self) -> list[dict]:
        """Return all score entries, ordered by move number."""
        return self._fetchall(
            "SELECT * FROM score_entries ORDER BY move_number"
        )

    # --------------------------------------------------------- bulk insert

    def insert_flag(self, **fields: Any) -> None:
        """Insert a single flag row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO flags ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
