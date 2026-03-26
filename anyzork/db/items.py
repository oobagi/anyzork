"""Item and container persistence methods for GameDB.

Extracted from schema.py as part of the domain-focused persistence
layer refactor.  Mixed into GameDB via multiple inheritance.
"""

from __future__ import annotations

import json as _json
from typing import Any


class ItemsMixin:
    """Item CRUD, inventory, containers, item movement, and item dynamics."""

    # ---------------------------------------------------------------- items

    def get_items_in(self, location_type: str, location_id: str) -> list[dict]:
        """Return visible items in a location.

        ``location_type`` is one of:
        - ``"room"`` — items whose ``room_id`` matches ``location_id``
        - ``"inventory"`` — items with ``room_id IS NULL`` and ``is_visible = 1``

        Only visible items are returned.  Items inside containers
        (``container_id IS NOT NULL``) are excluded from room listings —
        they must be discovered by searching the container.
        """
        if location_type == "inventory":
            return self._fetchall(
                "SELECT * FROM items "
                "WHERE room_id IS NULL AND container_id IS NULL "
                "AND is_visible = 1"
            )
        # Default: room — exclude items that live inside a container.
        return self._fetchall(
            "SELECT * FROM items WHERE room_id = ? AND is_visible = 1 AND container_id IS NULL",
            (location_id,),
        )

    def get_item(self, item_id: str) -> dict | None:
        """Return a single item by id."""
        return self._fetchone("SELECT * FROM items WHERE id = ?", (item_id,))

    def find_item_by_name(
        self, name: str, location_type: str, location_id: str
    ) -> dict | None:
        """Find an item by display name within a specific location.

        Uses fuzzy matching so that ``"toothpaste"`` matches
        ``"empty toothpaste tube"`` and ``"towel"`` matches
        ``"small towel"``.  Matching rules (in priority order):

        1. Exact match (case-insensitive) — always wins.
        2. Input is a substring of the item name (contains match).
        3. Any input word matches any word in the item name.

        Among multiple matches, the shortest item name wins.
        """
        name_lower = name.lower().strip()
        if not name_lower:
            return None

        # Fetch candidates based on location.
        # Exclude items inside containers — they must be accessed via the
        # container search / take-from mechanics.
        if location_type == "inventory":
            candidates = self._fetchall(
                "SELECT * FROM items "
                "WHERE room_id IS NULL AND container_id IS NULL "
                "AND is_visible = 1"
            )
        else:
            candidates = self._fetchall(
                "SELECT * FROM items WHERE room_id = ? AND is_visible = 1 AND container_id IS NULL",
                (location_id,),
            )

        if not candidates:
            return None

        # Try exact match first.
        for item in candidates:
            if item["name"].lower() == name_lower:
                return item

        # Substring match: "toothpaste" is in "empty toothpaste tube".
        substring_matches: list[dict] = []
        for item in candidates:
            if name_lower in item["name"].lower():
                substring_matches.append(item)

        if substring_matches:
            substring_matches.sort(key=lambda i: len(i["name"]))
            return substring_matches[0]

        # Word match: any input word matches any item name word.
        input_words = name_lower.split()
        word_matches: list[dict] = []
        for item in candidates:
            item_words = item["name"].lower().split()
            if any(iw in item_words for iw in input_words):
                word_matches.append(item)

        if word_matches:
            word_matches.sort(key=lambda i: len(i["name"]))
            return word_matches[0]

        return None

    def find_items_by_name(
        self, name: str, location_type: str, location_id: str
    ) -> list[dict]:
        """Like ``find_item_by_name`` but returns ALL matches at the best tier."""
        name_lower = name.lower().strip()
        if not name_lower:
            return []

        if location_type == "inventory":
            candidates = self._fetchall(
                "SELECT * FROM items "
                "WHERE room_id IS NULL AND container_id IS NULL "
                "AND is_visible = 1"
            )
        else:
            candidates = self._fetchall(
                "SELECT * FROM items WHERE room_id = ? AND is_visible = 1 AND container_id IS NULL",
                (location_id,),
            )

        if not candidates:
            return []

        exact = [i for i in candidates if i["name"].lower() == name_lower]
        if exact:
            return exact

        substring_matches = [i for i in candidates if name_lower in i["name"].lower()]
        if substring_matches:
            return substring_matches

        input_words = name_lower.split()
        word_matches = [
            i for i in candidates
            if any(iw in i["name"].lower().split() for iw in input_words)
        ]
        return word_matches

    def move_item(self, item_id: str, location_type: str, location_id: str) -> None:
        """Move an item to a new location.

        ``location_type`` is ``"room"`` or ``"inventory"``.  For inventory,
        ``location_id`` is ignored and ``room_id`` is set to ``NULL``.

        Always clears ``container_id`` — an item moved to a room or inventory
        is no longer inside a container.
        """
        if location_type == "inventory":
            self._mutate(
                "UPDATE items SET room_id = NULL, container_id = NULL "
                "WHERE id = ?",
                (item_id,),
            )
        else:
            self._mutate(
                "UPDATE items SET room_id = ?, container_id = NULL "
                "WHERE id = ?",
                (location_id, item_id),
            )

    def remove_item(self, item_id: str) -> None:
        """Remove an item from the game (consumed / destroyed).

        Hides the item rather than deleting to avoid FK constraint
        violations (other items may reference this via container_id).

        When removing a container, recursively removes its contents first
        (sets ``is_visible = 0``).
        """
        contents = self.get_container_contents(item_id)
        for child in contents:
            self.remove_item(child["id"])
        self._mutate(
            "UPDATE items SET room_id = NULL, container_id = NULL, is_visible = 0 WHERE id = ?",
            (item_id,),
        )

    def spawn_item(
        self,
        item_id: str,
        location_type: str = "room",
        location_id: str | None = None,
    ) -> None:
        """Make a hidden item visible and optionally set its location.

        If ``location_type`` is ``"inventory"``, sets ``room_id`` to ``NULL``.
        If ``location_type`` is ``"room"`` and ``location_id`` is provided,
        moves the item to that room.
        If ``location_type`` is ``"container"``, places the item inside the
        container and clears ``room_id``.
        """
        if location_type == "inventory":
            self._mutate(
                "UPDATE items SET is_visible = 1, room_id = NULL, container_id = NULL "
                "WHERE id = ?",
                (item_id,),
            )
        elif location_type == "container" and location_id is not None:
            self._mutate(
                "UPDATE items SET is_visible = 1, room_id = NULL, container_id = ? "
                "WHERE id = ?",
                (location_id, item_id),
            )
        elif location_id is not None:
            self._mutate(
                "UPDATE items SET is_visible = 1, room_id = ?, container_id = NULL "
                "WHERE id = ?",
                (location_id, item_id),
            )
        else:
            self._mutate(
                "UPDATE items SET is_visible = 1 WHERE id = ?", (item_id,)
            )

    # ------------------------------------------------------------- containers

    def get_container_contents(self, container_id: str) -> list[dict]:
        """Return visible items inside a container."""
        return self._fetchall(
            "SELECT * FROM items WHERE container_id = ? AND is_visible = 1",
            (container_id,),
        )

    def open_container(self, container_id: str) -> None:
        """Open a container: set ``is_open = 1`` and ``is_locked = 0``."""
        self._mutate(
            "UPDATE items SET is_open = 1, is_locked = 0 WHERE id = ?",
            (container_id,),
        )

    def close_container(self, container_id: str) -> None:
        """Close a container: set ``is_open = 0``."""
        self._mutate(
            "UPDATE items SET is_open = 0 WHERE id = ?",
            (container_id,),
        )

    def move_item_to_container(
        self, item_id: str, container_id: str
    ) -> tuple[bool, str]:
        """Move an item into a container with full nesting validation.

        Returns a ``(success, message)`` tuple.  On success the message
        is empty.  On failure the message explains why (for player-facing
        feedback).

        Validations performed (in order):

        1. **Self-placement** -- an item cannot be placed inside itself.
        2. **Cycle detection** -- walk the target container's
           ``container_id`` chain upward and verify ``item_id`` does not
           appear (would create a cycle).
        3. **Whitelist check** -- if the container has an ``accepts_items``
           JSON array, verify ``item_id`` is listed.  Uses the container's
           ``reject_message`` for the failure text if available.
        """
        # --- Self-placement ---
        if item_id == container_id:
            return (False, "You can't put something inside itself.")

        # --- Cycle detection ---
        current_id: str | None = container_id
        while current_id is not None:
            parent = self._fetchone(
                "SELECT id, container_id FROM items WHERE id = ?", (current_id,)
            )
            if parent is None:
                break
            if parent["id"] == item_id:
                return (False, "That would create a circular containment loop.")
            current_id = parent["container_id"]

        # Look up the container and item rows.
        container = self._fetchone("SELECT * FROM items WHERE id = ?", (container_id,))
        if container is None:
            return (False, "Container not found.")

        # --- Whitelist check ---
        raw_accepts = container.get("accepts_items")
        if raw_accepts is not None:
            try:
                accepted_ids = _json.loads(raw_accepts)
            except (_json.JSONDecodeError, TypeError):
                accepted_ids = []
            if item_id not in accepted_ids:
                reject_msg = container.get("reject_message")
                if reject_msg:
                    return (False, reject_msg)
                return (
                    False,
                    f"That doesn't fit in the {container['name']}.",
                )

        # --- All checks passed — perform the move ---
        self._mutate(
            "UPDATE items SET room_id = NULL, container_id = ? WHERE id = ?",
            (container_id, item_id),
        )
        return (True, "")

    def take_item_from_container(self, item_id: str) -> None:
        """Take an item out of a container into inventory.

        Sets ``container_id = NULL`` and ``room_id = NULL`` (inventory).
        """
        self._mutate(
            "UPDATE items SET container_id = NULL, room_id = NULL WHERE id = ?",
            (item_id,),
        )

    def get_open_containers_in_room(self, room_id: str) -> list[dict]:
        """Return containers in a room that are open or have no lid (always accessible).

        Excludes locked containers.
        """
        return self._fetchall(
            """
            SELECT * FROM items
            WHERE room_id = ? AND is_container = 1 AND is_visible = 1
              AND (is_open = 1 OR has_lid = 0)
              AND is_locked = 0
            """,
            (room_id,),
        )

    def find_item_in_container(self, name: str, container_id: str) -> dict | None:
        """Find an item by display name inside a specific container.

        Uses the same fuzzy matching rules as ``find_item_by_name``.
        """
        name_lower = name.lower().strip()
        if not name_lower:
            return None

        candidates = self._fetchall(
            "SELECT * FROM items WHERE container_id = ? AND is_visible = 1",
            (container_id,),
        )
        if not candidates:
            return None

        # Exact match.
        for item in candidates:
            if item["name"].lower() == name_lower:
                return item

        # Substring match.
        substring_matches: list[dict] = []
        for item in candidates:
            if name_lower in item["name"].lower():
                substring_matches.append(item)
        if substring_matches:
            substring_matches.sort(key=lambda i: len(i["name"]))
            return substring_matches[0]

        # Word match.
        input_words = name_lower.split()
        word_matches: list[dict] = []
        for item in candidates:
            item_words = item["name"].lower().split()
            if any(iw in item_words for iw in input_words):
                word_matches.append(item)
        if word_matches:
            word_matches.sort(key=lambda i: len(i["name"]))
            return word_matches[0]

        return None

    # ------------------------------------------------------ item dynamics

    def toggle_item_state(self, item_id: str, new_state: str) -> None:
        """Update an item's ``toggle_state`` column."""
        self._mutate(
            "UPDATE items SET toggle_state = ? WHERE id = ?",
            (new_state, item_id),
        )

    def get_item_quantity(self, item_id: str) -> int | None:
        """Return the ``quantity`` for an item, or ``None`` if not a consumable."""
        row = self._fetchone(
            "SELECT quantity FROM items WHERE id = ?", (item_id,)
        )
        if row is None:
            return None
        return row["quantity"]

    def consume_item_quantity(self, item_id: str, amount: int = 1) -> bool:
        """Decrement an item's quantity by *amount*.

        Returns ``False`` if the item has insufficient quantity.  When
        quantity reaches 0, the item's ``toggle_state`` is set to the
        first entry in ``toggle_states`` (or ``"off"`` if unset).
        """
        item = self.get_item(item_id)
        if item is None or item["quantity"] is None:
            return False
        if item["quantity"] < amount:
            return False

        new_qty = item["quantity"] - amount
        self._conn.execute(
            "UPDATE items SET quantity = ? WHERE id = ?",
            (new_qty, item_id),
        )

        if new_qty <= 0:
            # Determine the "off" state from toggle_states or default.
            off_state = "off"
            raw_states = item.get("toggle_states")
            if raw_states:
                try:
                    states = _json.loads(raw_states)
                    if states:
                        off_state = states[0]
                except (_json.JSONDecodeError, TypeError):
                    pass
            self._conn.execute(
                "UPDATE items SET toggle_state = ? WHERE id = ?",
                (off_state, item_id),
            )

        self._conn.commit()
        return True

    def restore_item_quantity(
        self,
        item_id: str,
        amount: int,
        source_item_id: str | None = None,
    ) -> int:
        """Increment an item's quantity up to ``max_quantity``.

        If *source_item_id* is provided, the source item's quantity is
        decremented by the amount actually restored (limited by available
        supply).  Returns the amount actually restored.
        """
        item = self.get_item(item_id)
        if item is None or item["quantity"] is None:
            return 0

        max_qty = item["max_quantity"]
        current = item["quantity"]
        room = max_qty - current if max_qty is not None else amount
        actual = min(amount, room)

        # If a source is provided, cap by source availability.
        if source_item_id is not None:
            source = self.get_item(source_item_id)
            if source is None or source["quantity"] is None:
                return 0
            actual = min(actual, source["quantity"])
            self._conn.execute(
                "UPDATE items SET quantity = quantity - ? WHERE id = ?",
                (actual, source_item_id),
            )

        if actual <= 0:
            self._conn.commit()
            return 0

        self._conn.execute(
            "UPDATE items SET quantity = quantity + ? WHERE id = ?",
            (actual, item_id),
        )
        self._conn.commit()
        return actual

    def get_interaction_response(
        self, item_tag: str, target_category: str
    ) -> dict | None:
        """Look up the ``interaction_responses`` table for a match.

        Resolution order:

        1. Exact match on both ``item_tag`` and ``target_category``.
        2. Wildcard ``target_category = '*'`` with exact ``item_tag``.
        3. Wildcard ``item_tag = '*'`` with exact ``target_category``.

        Returns a dict or ``None``.
        """
        # 1. Exact match.
        row = self._fetchone(
            "SELECT * FROM interaction_responses WHERE item_tag = ? AND target_category = ?",
            (item_tag, target_category),
        )
        if row is not None:
            return row

        # 2. Wildcard target_category.
        row = self._fetchone(
            "SELECT * FROM interaction_responses WHERE item_tag = ? AND target_category = '*'",
            (item_tag,),
        )
        if row is not None:
            return row

        # 3. Wildcard item_tag.
        row = self._fetchone(
            "SELECT * FROM interaction_responses WHERE item_tag = '*' AND target_category = ?",
            (target_category,),
        )
        if row is not None:
            return row

        return None

    def get_active_light_sources(self) -> list[dict]:
        """Return inventory items tagged ``light_source`` with ``toggle_state = 'on'``.

        An item is in inventory when ``room_id IS NULL`` and
        ``container_id IS NULL``.  The ``item_tags`` JSON array is
        scanned in Python because SQLite has no native JSON array
        containment operator.
        """
        candidates = self._fetchall(
            """
            SELECT * FROM items
            WHERE room_id IS NULL AND container_id IS NULL
              AND is_visible = 1 AND toggle_state = 'on'
              AND item_tags IS NOT NULL
            """
        )
        results: list[dict] = []
        for item in candidates:
            try:
                tags = _json.loads(item["item_tags"])
            except (_json.JSONDecodeError, TypeError):
                continue
            if "light_source" in tags:
                results.append(item)
        return results

    def change_description(self, entity_id: str, new_text: str) -> None:
        """Change the description of an item or room at runtime.

        Tries items first, then rooms.
        """
        item = self.get_item(entity_id)
        if item is not None:
            self._mutate(
                "UPDATE items SET description = ? WHERE id = ?",
                (new_text, entity_id),
            )
            return
        room = self.get_room(entity_id)
        if room is not None:
            self._mutate(
                "UPDATE rooms SET description = ? WHERE id = ?",
                (new_text, entity_id),
            )

    # --------------------------------------------------------- bulk insert

    def insert_item(self, **fields: Any) -> None:
        """Insert a single item row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO items ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )

    def insert_interaction_response(self, **fields: Any) -> None:
        """Insert a row into the ``interaction_responses`` table."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO interaction_responses ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
