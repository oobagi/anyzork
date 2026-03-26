"""NPC persistence methods for GameDB.

Extracted from schema.py as part of the domain-focused persistence
layer refactor.  Mixed into GameDB via multiple inheritance.
"""

from __future__ import annotations

from typing import Any


class NPCsMixin:
    """NPC CRUD, dialogue, disposition, factions, behaviors, and blocking."""

    # ----------------------------------------------------------------- npcs

    def get_npcs_in(self, room_id: str) -> list[dict]:
        """Return all living NPCs in a room."""
        return self._fetchall(
            "SELECT * FROM npcs WHERE room_id = ? AND is_alive = 1",
            (room_id,),
        )

    def get_npc(self, npc_id: str) -> dict | None:
        """Return a single NPC by id."""
        return self._fetchone("SELECT * FROM npcs WHERE id = ?", (npc_id,))

    def get_blocking_npc_for_exit(self, exit_id: str) -> dict | None:
        """Return a living NPC that blocks the given exit, or ``None``.

        An NPC blocks an exit when ``is_blocking = 1``, ``is_alive = 1``,
        ``blocked_exit_id`` matches, and the NPC is in the exit's origin
        room.  If the NPC has an ``unblock_flag`` and that flag is set to
        ``'true'``, the block is considered lifted and ``None`` is returned.
        """
        npc = self._fetchone(
            """
            SELECT n.* FROM npcs n
            JOIN exits e ON e.id = n.blocked_exit_id
            WHERE n.blocked_exit_id = ?
              AND n.is_blocking = 1
              AND n.is_alive = 1
              AND n.room_id = e.from_room_id
            """,
            (exit_id,),
        )
        if npc is None:
            return None
        # Check unblock_flag — if the flag is set, the NPC no longer blocks.
        unblock = npc.get("unblock_flag")
        if unblock and self.has_flag(unblock):
            return None
        return npc

    def find_npc_by_name(self, name: str, room_id: str) -> dict | None:
        """Find an NPC by display name within a specific room.

        Uses partial matching so that ``"gandalf"`` matches
        ``"Gandalf the Grey"``.  Matching rules:

        1. Exact match (case-insensitive) -- always wins.
        2. The input is a prefix of the NPC name (starts-with).
        3. The input matches the first word of the NPC name.
        4. The NPC name starts with a word that starts with the input.

        Among multiple partial matches, the NPC with the shortest name
        (most specific) is preferred.  Only living NPCs are returned.
        """
        # Try exact match first (fast path).
        exact = self._fetchone(
            """
            SELECT * FROM npcs
            WHERE LOWER(name) = LOWER(?) AND room_id = ? AND is_alive = 1
            """,
            (name, room_id),
        )
        if exact is not None:
            return exact

        # Partial match: input is a case-insensitive prefix of the NPC name,
        # OR the NPC name starts with the input as a word boundary.
        # We fetch all living NPCs in the room and filter in Python for
        # more nuanced matching than SQL LIKE can provide.
        candidates = self._fetchall(
            "SELECT * FROM npcs WHERE room_id = ? AND is_alive = 1",
            (room_id,),
        )

        name_lower = name.lower().strip()
        if not name_lower:
            return None

        matches: list[dict] = []
        for npc in candidates:
            npc_name_lower = npc["name"].lower()
            # The NPC name starts with the input (prefix match).
            if npc_name_lower.startswith(name_lower):
                matches.append(npc)
                continue
            # The input matches one or more leading words of the NPC name.
            # e.g. "gandalf the" matches "gandalf the grey"
            npc_words = npc_name_lower.split()
            input_words = name_lower.split()
            if len(input_words) <= len(npc_words):
                # Check if the input words match the leading words of the name.
                leading_match = all(
                    npc_words[i].startswith(w) for i, w in enumerate(input_words)
                )
                if leading_match:
                    matches.append(npc)

        if not matches:
            return None

        # Prefer the shortest name (most specific match).
        matches.sort(key=lambda npc: len(npc["name"]))
        return matches[0]

    def find_npc_by_name_any(self, name: str, room_id: str) -> dict | None:
        """Like :meth:`find_npc_by_name` but includes dead NPCs.

        Used by the engine to detect dead-NPC interactions (search corpse,
        block dialogue with a dead NPC, etc.).  Same matching rules apply.
        """
        exact = self._fetchone(
            """
            SELECT * FROM npcs
            WHERE LOWER(name) = LOWER(?) AND room_id = ?
            """,
            (name, room_id),
        )
        if exact is not None:
            return exact

        candidates = self._fetchall(
            "SELECT * FROM npcs WHERE room_id = ?",
            (room_id,),
        )

        name_lower = name.lower().strip()
        if not name_lower:
            return None

        matches: list[dict] = []
        for npc in candidates:
            npc_name_lower = npc["name"].lower()
            if npc_name_lower.startswith(name_lower):
                matches.append(npc)
                continue
            npc_words = npc_name_lower.split()
            input_words = name_lower.split()
            if len(input_words) <= len(npc_words):
                leading_match = all(
                    npc_words[i].startswith(w) for i, w in enumerate(input_words)
                )
                if leading_match:
                    matches.append(npc)

        if not matches:
            return None

        matches.sort(key=lambda npc: len(npc["name"]))
        return matches[0]

    # ------------------------------------------------------------ dialogue

    def get_root_dialogue_node(self, npc_id: str) -> dict | None:
        """Return the root dialogue node (is_root=1) for an NPC."""
        return self._fetchone(
            """
            SELECT * FROM dialogue_nodes
            WHERE npc_id = ? AND is_root = 1
            """,
            (npc_id,),
        )

    def get_dialogue_node(self, node_id: str) -> dict | None:
        """Return a single dialogue node by id."""
        return self._fetchone(
            "SELECT * FROM dialogue_nodes WHERE id = ?",
            (node_id,),
        )

    def get_dialogue_options(self, node_id: str) -> list[dict]:
        """Return all options for a dialogue node, ordered by sort_order."""
        return self._fetchall(
            """
            SELECT * FROM dialogue_options
            WHERE node_id = ?
            ORDER BY sort_order
            """,
            (node_id,),
        )

    # --------------------------------------------------------- NPC mutations

    def kill_npc(self, npc_id: str) -> None:
        """Set an NPC's ``is_alive`` to ``0`` and spawn a searchable body container."""
        npc = self.get_npc(npc_id)
        self._mutate("UPDATE npcs SET is_alive = 0 WHERE id = ?", (npc_id,))

        # Spawn a container item representing the body, if one doesn't already exist.
        if npc:
            body_id = f"{npc_id}_body"
            existing = self.get_item(body_id)
            if existing is None:
                self.insert_item(
                    id=body_id,
                    name=f"{npc['name']}'s Body",
                    description=f"The body of {npc['name']}.",
                    examine_description=f"{npc['name']} lies motionless.",
                    room_id=npc["room_id"],
                    is_takeable=0,
                    is_visible=1,
                    is_container=1,
                    is_open=1,
                    has_lid=0,
                    category="body",
                    room_description=f"{npc['name']}'s body lies on the ground.",
                    search_message=f"You search {npc['name']}'s body.",
                )

    def damage_npc(self, npc_id: str, amount: int) -> dict | None:
        """Reduce an NPC's HP.  Kills the NPC if HP reaches 0.

        Returns the NPC row (after update).
        """
        self._conn.execute(
            "UPDATE npcs SET hp = MAX(0, hp - ?) WHERE id = ?", (amount, npc_id)
        )
        self._conn.commit()
        npc = self.get_npc(npc_id)
        if npc and npc["hp"] is not None and npc["hp"] <= 0:
            self.kill_npc(npc_id)
            npc = self.get_npc(npc_id)
        return npc

    def spawn_npc(self, npc_id: str, room_id: str) -> None:
        """Spawn a template NPC (or re-spawn an existing one) into a room.

        Template NPCs have ``room_id = NULL`` and stay in limbo until
        spawned.  If the NPC is already in a room, this simply moves it.

        Currently delegates to ``move_npc`` since the SQL is identical.
        Kept as a separate entry point so future divergence (e.g. resetting
        HP on spawn) can be added without touching callers.
        """
        self.move_npc(npc_id, room_id)

    def move_npc(self, npc_id: str, room_id: str) -> None:
        """Move an NPC to a different room."""
        self._mutate(
            "UPDATE npcs SET room_id = ? WHERE id = ?", (room_id, npc_id)
        )

    def remove_npc(self, npc_id: str) -> None:
        """Remove an NPC from the world entirely (no body, no loot)."""
        self._mutate("DELETE FROM npcs WHERE id = ?", (npc_id,))

    # --------------------------------------------------- Faction operations

    def get_npcs_by_faction(self, faction: str) -> list[dict]:
        """Return all NPCs belonging to a faction."""
        return self._fetchall(
            "SELECT * FROM npcs WHERE faction = ?", (faction,)
        )

    def set_faction_hostile(self, faction: str) -> None:
        """Set all living NPCs in a faction to hostile disposition."""
        self._mutate(
            "UPDATE npcs SET disposition = 'hostile' WHERE faction = ? AND is_alive = 1",
            (faction,),
        )

    def kill_faction(self, faction: str) -> None:
        """Kill all living NPCs in a faction (spawns body containers)."""
        living = self._fetchall(
            "SELECT id FROM npcs WHERE faction = ? AND is_alive = 1",
            (faction,),
        )
        for npc_row in living:
            self.kill_npc(npc_row["id"])

    def remove_faction(self, faction: str) -> None:
        """Remove all NPCs in a faction from the world entirely."""
        self._mutate("DELETE FROM npcs WHERE faction = ?", (faction,))

    def move_faction(self, faction: str, room_id: str) -> None:
        """Move all living NPCs in a faction to a room."""
        self._mutate(
            "UPDATE npcs SET room_id = ? WHERE faction = ? AND is_alive = 1",
            (room_id, faction),
        )

    def set_npc_disposition(self, npc_id: str, disposition: str) -> None:
        """Set an NPC's disposition (hostile, friendly, neutral)."""
        valid_dispositions = ("hostile", "friendly", "neutral")
        if disposition not in valid_dispositions:
            raise ValueError(
                f"Invalid disposition {disposition!r}; "
                f"must be one of {valid_dispositions}"
            )
        self._mutate(
            "UPDATE npcs SET disposition = ? WHERE id = ?",
            (disposition, npc_id),
        )

    def get_npc_disposition(self, npc_id: str) -> str:
        """Return the disposition of an NPC (hostile, friendly, neutral)."""
        row = self._fetchone(
            "SELECT disposition FROM npcs WHERE id = ?", (npc_id,)
        )
        if row is None:
            return "neutral"
        return row.get("disposition", "neutral") or "neutral"

    # --------------------------------------------------------- bulk insert

    def insert_npc(self, **fields: Any) -> None:
        """Insert a single NPC row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO npcs ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def insert_dialogue_node(self, **fields: Any) -> None:
        """Insert a single dialogue node row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO dialogue_nodes ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def insert_dialogue_option(self, **fields: Any) -> None:
        """Insert a single dialogue option row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO dialogue_options ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    # --------------------------------------------------------- npc behaviors

    def insert_npc_behavior(self, **fields: Any) -> None:
        """Insert a single NPC behavior row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO npc_behaviors ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def get_npcs_with_active_behaviors(self) -> list[dict]:
        """Return id and room_id for all living NPCs that have active behaviors."""
        return self._fetchall(
            "SELECT DISTINCT n.id, n.room_id FROM npcs n "
            "INNER JOIN npc_behaviors b ON b.npc_id = n.id "
            "WHERE n.is_alive = 1 AND (b.one_shot = 0 OR b.executed = 0)"
        )

    def get_npc_behaviors(self, npc_id: str) -> list[dict]:
        """Return all active behaviors for an NPC.

        One-shot behaviors that have already fired are excluded.
        """
        return self._fetchall(
            "SELECT * FROM npc_behaviors WHERE npc_id = ? "
            "AND (one_shot = 0 OR executed = 0)",
            (npc_id,),
        )

    def get_all_npc_behaviors(self) -> list[dict]:
        """Return all NPC behavior rows (including executed one-shots)."""
        return self._fetchall("SELECT * FROM npc_behaviors")

    def mark_npc_behavior_executed(self, behavior_id: int) -> None:
        """Mark a one-shot NPC behavior as executed so it won't fire again."""
        self._mutate(
            "UPDATE npc_behaviors SET executed = 1 WHERE id = ?",
            (behavior_id,),
        )
