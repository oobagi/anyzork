"""Room and exit persistence methods for GameDB.

Extracted from schema.py as part of the domain-focused persistence
layer refactor.  Mixed into GameDB via multiple inheritance.
"""

from __future__ import annotations

from typing import Any


class RoomsMixin:
    """Room CRUD, exits, visits, locks, and room descriptions."""

    # ---------------------------------------------------------------- rooms

    def get_room(self, room_id: str) -> dict | None:
        """Return a single room by id."""
        return self._fetchone("SELECT * FROM rooms WHERE id = ?", (room_id,))

    def get_all_rooms(self) -> list[dict]:
        """Return all rooms."""
        return self._fetchall("SELECT * FROM rooms ORDER BY id")

    def get_start_room(self) -> dict | None:
        """Return the room marked as the starting room."""
        return self._fetchone("SELECT * FROM rooms WHERE is_start = 1")

    def get_exits(self, room_id: str) -> list[dict]:
        """Return all non-hidden exits from a room, with destination room name.

        Hidden exits (``is_hidden = 1``) are excluded so the player cannot
        see or use them until revealed.
        """
        return self._fetchall(
            """
            SELECT e.*, r.name AS to_room_name
            FROM exits e
            JOIN rooms r ON r.id = e.to_room_id
            WHERE e.from_room_id = ? AND e.is_hidden = 0
            ORDER BY e.direction
            """,
            (room_id,),
        )

    def get_all_exits_from(self, room_id: str) -> list[dict]:
        """Return ALL exits from a room, including hidden ones.

        Used internally by the engine/generator — not for player-facing
        output.
        """
        return self._fetchall(
            """
            SELECT e.*, r.name AS to_room_name
            FROM exits e
            JOIN rooms r ON r.id = e.to_room_id
            WHERE e.from_room_id = ?
            ORDER BY e.direction
            """,
            (room_id,),
        )

    def get_exit_by_direction(self, room_id: str, direction: str) -> dict | None:
        """Return a specific non-hidden exit from a room by direction string."""
        return self._fetchone(
            """
            SELECT e.*, r.name AS to_room_name
            FROM exits e
            JOIN rooms r ON r.id = e.to_room_id
            WHERE e.from_room_id = ? AND LOWER(e.direction) = LOWER(?)
              AND e.is_hidden = 0
            """,
            (room_id, direction),
        )

    # --------------------------------------------------------------- visits

    def record_visit(self, room_id: str, move: int) -> bool:
        """Record a room visit.  Returns ``True`` on the first visit.

        Also sets the room's ``visited`` flag to ``1``.
        """
        existing = self._fetchone(
            "SELECT room_id FROM visited_rooms WHERE room_id = ?", (room_id,)
        )
        if existing:
            return False
        self._conn.execute(
            "INSERT INTO visited_rooms (room_id, first_visit) VALUES (?, ?)",
            (room_id, move),
        )
        self._conn.execute(
            "UPDATE rooms SET visited = 1 WHERE id = ?", (room_id,)
        )
        self._conn.commit()
        return True

    def has_visited(self, room_id: str) -> bool:
        """Return ``True`` if the room has been visited."""
        row = self._fetchone(
            "SELECT room_id FROM visited_rooms WHERE room_id = ?", (room_id,)
        )
        return row is not None

    # ---------------------------------------------------------------- locks

    def get_lock(self, lock_id: str) -> dict | None:
        """Return a single lock by id."""
        return self._fetchone("SELECT * FROM locks WHERE id = ?", (lock_id,))

    def get_lock_for_exit(self, exit_id: str) -> dict | None:
        """Return the lock (if any) gating a specific exit."""
        return self._fetchone(
            "SELECT * FROM locks WHERE target_exit_id = ? AND is_locked = 1",
            (exit_id,),
        )

    def unlock(self, lock_id: str) -> dict | None:
        """Unlock a lock and its associated exit.

        Returns the lock row (before update) so callers can access the
        ``unlock_message``.  Returns ``None`` if the lock does not exist.
        """
        lock = self.get_lock(lock_id)
        if lock is None:
            return None
        self._conn.execute(
            "UPDATE locks SET is_locked = 0 WHERE id = ?", (lock_id,)
        )
        self._conn.execute(
            "UPDATE exits SET is_locked = 0 WHERE id = ?",
            (lock["target_exit_id"],),
        )
        self._conn.commit()
        return lock

    def get_locks_in_room(self, room_id: str) -> list[dict]:
        """Return all active locks on exits from a given room, with exit info."""
        return self._fetchall(
            """
            SELECT l.*, e.direction, e.from_room_id, e.to_room_id
            FROM locks l
            JOIN exits e ON e.id = l.target_exit_id
            WHERE e.from_room_id = ? AND l.is_locked = 1
            """,
            (room_id,),
        )

    # -------------------------------------------------------- exit mutations

    def reveal_exit(self, exit_id: str) -> None:
        """Make a hidden exit visible (``is_hidden = 0``)."""
        self._mutate(
            "UPDATE exits SET is_hidden = 0 WHERE id = ?", (exit_id,)
        )

    def hide_exit(self, exit_id: str) -> None:
        """Hide a previously revealed exit (``is_hidden = 1``)."""
        self._mutate(
            "UPDATE exits SET is_hidden = 1 WHERE id = ?", (exit_id,)
        )

    def lock_exit(self, exit_id: str) -> None:
        """Lock an exit (``is_locked = 1``)."""
        self._mutate(
            "UPDATE exits SET is_locked = 1 WHERE id = ?", (exit_id,)
        )

    def unlock_exit(self, exit_id: str) -> None:
        """Unlock an exit directly (``is_locked = 0``).

        For unlocking via the lock system, use :meth:`unlock` instead.
        """
        self._mutate(
            "UPDATE exits SET is_locked = 0 WHERE id = ?", (exit_id,)
        )

    # --------------------------------------------------------- bulk insert

    def insert_room(self, **fields: Any) -> None:
        """Insert a single room row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO rooms ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def insert_exit(self, **fields: Any) -> None:
        """Insert a single exit row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO exits ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def insert_lock(self, **fields: Any) -> None:
        """Insert a single lock row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO locks ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def insert_puzzle(self, **fields: Any) -> None:
        """Insert a single puzzle row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO puzzles ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
