"""SQLite schema and database interface for AnyZork game files (.zork).

This module defines the complete database schema for a .zork game file and
provides the GameDB class — the single interface that the engine, generator,
and CLI use to read and write game state.

Every table, field, type, and constraint is derived from the authoritative
world-schema reference (docs/game-design/world-schema.md).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """\
-- AnyZork World Schema v1.0
-- Authoritative source: docs/game-design/world-schema.md

-- -------------------------------------------------------
-- metadata: game-level information (single row, id = 1)
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS metadata (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    title           TEXT    NOT NULL,
    author_prompt   TEXT    NOT NULL,
    seed            TEXT,
    version         TEXT    NOT NULL DEFAULT '1.0',
    created_at      TEXT    NOT NULL,
    max_score       INTEGER NOT NULL DEFAULT 0,
    win_conditions  TEXT    NOT NULL DEFAULT '[]',   -- JSON array of flag IDs
    lose_conditions TEXT,                             -- JSON array or NULL
    intro_text      TEXT    NOT NULL DEFAULT '',
    win_text        TEXT    NOT NULL DEFAULT '',
    lose_text       TEXT,
    region_count    INTEGER NOT NULL DEFAULT 0,
    room_count      INTEGER NOT NULL DEFAULT 0
);

-- -------------------------------------------------------
-- rooms: every discrete location in the game world
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS rooms (
    id                TEXT PRIMARY KEY,
    name              TEXT    NOT NULL,
    description       TEXT    NOT NULL,
    short_description TEXT    NOT NULL,
    first_visit_text  TEXT,
    region            TEXT    NOT NULL,
    is_dark           INTEGER NOT NULL DEFAULT 0,
    is_start          INTEGER NOT NULL DEFAULT 0,
    visited           INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rooms_region   ON rooms(region);
CREATE INDEX IF NOT EXISTS idx_rooms_is_start ON rooms(is_start);

-- -------------------------------------------------------
-- exits: one-way connections between rooms
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS exits (
    id          TEXT PRIMARY KEY,
    from_room_id TEXT NOT NULL REFERENCES rooms(id),
    to_room_id   TEXT NOT NULL REFERENCES rooms(id),
    direction   TEXT    NOT NULL,
    description TEXT,
    is_locked   INTEGER NOT NULL DEFAULT 0,
    is_hidden   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_exits_from_room ON exits(from_room_id);
CREATE INDEX IF NOT EXISTS idx_exits_to_room   ON exits(to_room_id);

-- -------------------------------------------------------
-- items: objects the player can interact with
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS items (
    id                  TEXT PRIMARY KEY,
    name                TEXT    NOT NULL,
    description         TEXT    NOT NULL,
    examine_description TEXT    NOT NULL,
    room_id             TEXT    REFERENCES rooms(id),
    container_id        TEXT    REFERENCES items(id),
    is_takeable         INTEGER NOT NULL DEFAULT 1,
    is_visible          INTEGER NOT NULL DEFAULT 1,
    is_consumed_on_use  INTEGER NOT NULL DEFAULT 0,
    is_container        INTEGER NOT NULL DEFAULT 0,
    is_open             INTEGER NOT NULL DEFAULT 0,
    has_lid             INTEGER NOT NULL DEFAULT 1,
    is_locked           INTEGER NOT NULL DEFAULT 0,
    lock_message        TEXT,
    open_message        TEXT,
    search_message      TEXT,
    take_message        TEXT,
    drop_message        TEXT,
    weight              INTEGER DEFAULT 1,
    category            TEXT,
    room_description    TEXT,
    read_description    TEXT,
    key_item_id         TEXT    REFERENCES items(id),
    consume_key         INTEGER NOT NULL DEFAULT 0,
    unlock_message      TEXT,
    CHECK (NOT (room_id IS NOT NULL AND container_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_items_room_id      ON items(room_id);
CREATE INDEX IF NOT EXISTS idx_items_container_id  ON items(container_id);

-- -------------------------------------------------------
-- npcs: non-player characters
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS npcs (
    id                TEXT PRIMARY KEY,
    name              TEXT    NOT NULL,
    description       TEXT    NOT NULL,
    examine_description TEXT  NOT NULL,
    room_id           TEXT    NOT NULL REFERENCES rooms(id),
    is_alive          INTEGER NOT NULL DEFAULT 1,
    is_blocking       INTEGER NOT NULL DEFAULT 0,
    blocked_exit_id   TEXT    REFERENCES exits(id),
    unblock_flag      TEXT,
    default_dialogue  TEXT    NOT NULL,
    hp                INTEGER,
    damage            INTEGER
);

CREATE INDEX IF NOT EXISTS idx_npcs_room_id ON npcs(room_id);

-- -------------------------------------------------------
-- dialogue_nodes: branching dialogue tree nodes
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS dialogue_nodes (
    id          TEXT PRIMARY KEY,
    npc_id      TEXT NOT NULL REFERENCES npcs(id),
    content     TEXT NOT NULL,
    set_flags   TEXT,          -- JSON array of flags to set when this node is visited
    is_root     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_dialogue_nodes_npc_id ON dialogue_nodes(npc_id);

-- -------------------------------------------------------
-- dialogue_options: player choices within a dialogue node
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS dialogue_options (
    id              TEXT PRIMARY KEY,
    node_id         TEXT NOT NULL REFERENCES dialogue_nodes(id),
    text            TEXT NOT NULL,      -- what the player sees as their choice
    next_node_id    TEXT REFERENCES dialogue_nodes(id),  -- NULL = terminal (ends conversation)
    required_flags  TEXT,   -- JSON array: flags that must be true for this option to appear
    excluded_flags  TEXT,   -- JSON array: flags that must NOT be true (hide after used)
    required_items  TEXT,   -- JSON array: item IDs player must have in inventory
    set_flags       TEXT,   -- JSON array: flags set when this option is chosen
    sort_order      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_dialogue_options_node_id ON dialogue_options(node_id);

-- -------------------------------------------------------
-- locks: gates that block exits until conditions are met
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS locks (
    id              TEXT PRIMARY KEY,
    lock_type       TEXT    NOT NULL,  -- key | puzzle | combination | state | npc
    target_exit_id  TEXT    NOT NULL REFERENCES exits(id),
    key_item_id     TEXT    REFERENCES items(id),
    puzzle_id       TEXT    REFERENCES puzzles(id),
    combination     TEXT,
    required_flags  TEXT,              -- JSON array for state-type locks
    locked_message  TEXT    NOT NULL,
    unlock_message  TEXT    NOT NULL,
    is_locked       INTEGER NOT NULL DEFAULT 1,
    consume_key     INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_locks_target_exit ON locks(target_exit_id);

-- -------------------------------------------------------
-- puzzles: multi-step challenges
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS puzzles (
    id              TEXT PRIMARY KEY,
    name            TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    room_id         TEXT    NOT NULL REFERENCES rooms(id),
    is_solved       INTEGER NOT NULL DEFAULT 0,
    solution_steps  TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    hint_text       TEXT,                           -- JSON array or NULL
    difficulty      INTEGER NOT NULL DEFAULT 1,
    score_value     INTEGER NOT NULL DEFAULT 0,
    is_optional     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_puzzles_room_id ON puzzles(room_id);

-- -------------------------------------------------------
-- commands: DSL rules defining every player action
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS commands (
    id              TEXT PRIMARY KEY,
    verb            TEXT    NOT NULL,
    pattern         TEXT    NOT NULL,
    preconditions   TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    effects         TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    success_message TEXT    NOT NULL DEFAULT '',
    failure_message TEXT    NOT NULL DEFAULT '',
    context_room_id TEXT    REFERENCES rooms(id),
    puzzle_id       TEXT    REFERENCES puzzles(id),
    priority        INTEGER NOT NULL DEFAULT 0,
    is_enabled      INTEGER NOT NULL DEFAULT 1,
    one_shot        INTEGER NOT NULL DEFAULT 0,
    executed        INTEGER NOT NULL DEFAULT 0,
    done_message    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_commands_verb       ON commands(verb);
CREATE INDEX IF NOT EXISTS idx_commands_context     ON commands(context_room_id);
CREATE INDEX IF NOT EXISTS idx_commands_puzzle      ON commands(puzzle_id);

-- -------------------------------------------------------
-- flags: boolean / string state variables
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS flags (
    id          TEXT PRIMARY KEY,
    value       TEXT    NOT NULL DEFAULT 'false',
    description TEXT
);

-- -------------------------------------------------------
-- quests: player-facing objectives with trackable progress
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS quests (
    id              TEXT PRIMARY KEY,
    name            TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    quest_type      TEXT    NOT NULL,  -- main | side
    status          TEXT    NOT NULL DEFAULT 'undiscovered',
    discovery_flag  TEXT,
    completion_flag TEXT    NOT NULL,
    score_value     INTEGER NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_quests_status ON quests(status);
CREATE INDEX IF NOT EXISTS idx_quests_type   ON quests(quest_type);

-- -------------------------------------------------------
-- quest_objectives: trackable steps within a quest
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS quest_objectives (
    id              TEXT PRIMARY KEY,
    quest_id        TEXT    NOT NULL REFERENCES quests(id),
    description     TEXT    NOT NULL,
    completion_flag TEXT    NOT NULL,
    order_index     INTEGER NOT NULL DEFAULT 0,
    is_optional     INTEGER NOT NULL DEFAULT 0,
    bonus_score     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_objectives_quest ON quest_objectives(quest_id);

-- -------------------------------------------------------
-- player: single-row runtime state (id = 1)
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS player (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    current_room_id TEXT    NOT NULL REFERENCES rooms(id),
    hp              INTEGER NOT NULL DEFAULT 100,
    max_hp          INTEGER NOT NULL DEFAULT 100,
    score           INTEGER NOT NULL DEFAULT 0,
    moves           INTEGER NOT NULL DEFAULT 0,
    game_state      TEXT    NOT NULL DEFAULT 'playing'  -- playing | won | lost
);

-- -------------------------------------------------------
-- score_entries: log of individual scoring events
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS score_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    reason      TEXT    NOT NULL,
    value       INTEGER NOT NULL,
    move_number INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_score_reason ON score_entries(reason);

-- -------------------------------------------------------
-- visited_rooms: tracks room visit history with move #
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS visited_rooms (
    room_id     TEXT    NOT NULL REFERENCES rooms(id),
    first_visit INTEGER NOT NULL,  -- move number on first visit
    PRIMARY KEY (room_id)
);
"""


# ---------------------------------------------------------------------------
# GameDB — the single interface for reading / writing game state
# ---------------------------------------------------------------------------

class GameDB:
    """Wraps a SQLite connection to a ``.zork`` game file.

    All query methods return ``dict``-like ``sqlite3.Row`` objects (or lists
    thereof).  All mutations commit immediately.  Parameterized queries are
    used everywhere — no string interpolation of user data.

    Usage::

        with GameDB("mygame.zork") as db:
            db.initialize("My Game", "Author", "A spooky dungeon")
            room = db.get_room("start_room")
    """

    # ------------------------------------------------------------------ init

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row

    # ----------------------------------------------------------- lifecycle

    def initialize(
        self,
        game_name: str,
        author: str,
        prompt: str,
        *,
        seed: str | None = None,
        intro_text: str = "",
        win_text: str = "",
        lose_text: str | None = None,
        win_conditions: str = "[]",
        lose_conditions: str | None = None,
        max_score: int = 0,
        region_count: int = 0,
        room_count: int = 0,
    ) -> None:
        """Create all tables and insert the initial metadata row."""
        self._conn.executescript(SCHEMA_SQL)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO metadata
                (id, title, author_prompt, seed, version, created_at,
                 max_score, win_conditions, lose_conditions,
                 intro_text, win_text, lose_text,
                 region_count, room_count)
            VALUES (1, ?, ?, ?, '1.0', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_name,
                prompt,
                seed,
                datetime.now(timezone.utc).isoformat(),
                max_score,
                win_conditions,
                lose_conditions,
                intro_text,
                win_text,
                lose_text,
                region_count,
                room_count,
            ),
        )
        self._conn.commit()

    def save(self) -> None:
        """Explicitly commit any pending transaction."""
        self._conn.commit()

    def close(self) -> None:
        """Commit and close the database connection."""
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> "GameDB":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ---------------------------------------------------------------- helpers

    def _fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _mutate(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    # ------------------------------------------------------------- metadata

    def get_meta(self, key: str) -> Any:
        """Return a single metadata field value by column name."""
        # Validate key is a real column to prevent injection.
        valid = {
            "title", "author_prompt", "seed", "version", "created_at",
            "max_score", "win_conditions", "lose_conditions",
            "intro_text", "win_text", "lose_text",
            "region_count", "room_count",
        }
        if key not in valid:
            raise KeyError(f"Unknown metadata key: {key!r}")
        row = self._conn.execute(
            f"SELECT {key} FROM metadata WHERE id = 1"  # noqa: S608 — key validated above
        ).fetchone()
        return row[key] if row else None

    def set_meta(self, key: str, value: Any) -> None:
        """Update a single metadata field by column name."""
        valid = {
            "title", "author_prompt", "seed", "version", "created_at",
            "max_score", "win_conditions", "lose_conditions",
            "intro_text", "win_text", "lose_text",
            "region_count", "room_count",
        }
        if key not in valid:
            raise KeyError(f"Unknown metadata key: {key!r}")
        self._mutate(
            f"UPDATE metadata SET {key} = ? WHERE id = 1", (value,)  # noqa: S608
        )

    def get_all_meta(self) -> dict | None:
        """Return the full metadata row as a dict."""
        return self._fetchone("SELECT * FROM metadata WHERE id = 1")

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
        """Return a specific exit from a room by direction string."""
        return self._fetchone(
            """
            SELECT e.*, r.name AS to_room_name
            FROM exits e
            JOIN rooms r ON r.id = e.to_room_id
            WHERE e.from_room_id = ? AND LOWER(e.direction) = LOWER(?)
            """,
            (room_id, direction),
        )

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
                "SELECT * FROM items WHERE room_id IS NULL AND container_id IS NULL AND is_visible = 1"
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
                "SELECT * FROM items WHERE room_id IS NULL AND container_id IS NULL AND is_visible = 1"
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

    def move_item(self, item_id: str, location_type: str, location_id: str) -> None:
        """Move an item to a new location.

        ``location_type`` is ``"room"`` or ``"inventory"``.  For inventory,
        ``location_id`` is ignored and ``room_id`` is set to ``NULL``.

        Always clears ``container_id`` — an item moved to a room or inventory
        is no longer inside a container.
        """
        if location_type == "inventory":
            self._mutate(
                "UPDATE items SET room_id = NULL, container_id = NULL WHERE id = ?", (item_id,)
            )
        else:
            self._mutate(
                "UPDATE items SET room_id = ?, container_id = NULL WHERE id = ?", (location_id, item_id)
            )

    def remove_item(self, item_id: str) -> None:
        """Remove an item from the game (consumed / destroyed).

        Hides the item rather than deleting to avoid FK constraint
        violations (other items may reference this via container_id).
        """
        self._mutate(
            "UPDATE items SET room_id = NULL, container_id = NULL, is_visible = 0 WHERE id = ?",
            (item_id,),
        )

    def spawn_item(self, item_id: str, location_type: str = "room", location_id: str | None = None) -> None:
        """Make a hidden item visible and optionally set its location.

        If ``location_type`` is ``"inventory"``, sets ``room_id`` to ``NULL``.
        If ``location_type`` is ``"room"`` and ``location_id`` is provided,
        moves the item to that room.
        """
        if location_type == "inventory":
            self._mutate(
                "UPDATE items SET is_visible = 1, room_id = NULL WHERE id = ?",
                (item_id,),
            )
        elif location_id is not None:
            self._mutate(
                "UPDATE items SET is_visible = 1, room_id = ? WHERE id = ?",
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

    def move_item_to_container(self, item_id: str, container_id: str) -> None:
        """Move an item into a container (``room_id = NULL``, ``container_id = ?``)."""
        self._mutate(
            "UPDATE items SET room_id = NULL, container_id = ? WHERE id = ?",
            (container_id, item_id),
        )

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
        self._mutate(f"UPDATE player SET {sets} WHERE id = 1", vals)  # noqa: S608

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

    # ------------------------------------------------------------ commands

    def get_commands_for_verb(self, verb: str) -> list[dict]:
        """Return all enabled commands matching a verb, ordered by priority.

        Higher priority commands are returned first.
        """
        return self._fetchall(
            """
            SELECT * FROM commands
            WHERE LOWER(verb) = LOWER(?) AND is_enabled = 1
            ORDER BY priority DESC
            """,
            (verb,),
        )

    def get_all_commands(self) -> list[dict]:
        """Return every command row (enabled or not)."""
        return self._fetchall("SELECT * FROM commands ORDER BY verb, priority DESC")

    def get_command(self, command_id: str) -> dict | None:
        """Return a single command by id."""
        return self._fetchone("SELECT * FROM commands WHERE id = ?", (command_id,))

    def mark_command_executed(self, command_id: str) -> None:
        """Mark a one-shot command as executed so it won't fire again."""
        self._mutate(
            "UPDATE commands SET executed = 1 WHERE id = ?", (command_id,)
        )

    def enable_command(self, command_id: str) -> None:
        """Enable a disabled command."""
        self._mutate(
            "UPDATE commands SET is_enabled = 1 WHERE id = ?", (command_id,)
        )

    def disable_command(self, command_id: str) -> None:
        """Disable a command."""
        self._mutate(
            "UPDATE commands SET is_enabled = 0 WHERE id = ?", (command_id,)
        )

    # ------------------------------------------------------------ puzzles

    def get_puzzle(self, puzzle_id: str) -> dict | None:
        """Return a single puzzle by id."""
        return self._fetchone("SELECT * FROM puzzles WHERE id = ?", (puzzle_id,))

    def solve_puzzle(self, puzzle_id: str) -> dict | None:
        """Mark a puzzle as solved and return it (with ``score_value``).

        Returns ``None`` if the puzzle does not exist.  Returns the puzzle
        row (before the update) so the caller can read ``score_value`` and
        ``name`` for messaging.
        """
        puzzle = self.get_puzzle(puzzle_id)
        if puzzle is None:
            return None
        self._mutate(
            "UPDATE puzzles SET is_solved = 1 WHERE id = ?", (puzzle_id,)
        )
        return puzzle

    # --------------------------------------------------------------- quests

    def insert_quest(self, **fields: Any) -> None:
        """Insert a single quest row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO quests ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_quest_objective(self, **fields: Any) -> None:
        """Insert a single quest_objective row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO quest_objectives ({cols}) VALUES ({placeholders})",  # noqa: S608
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

    # ----------------------------------------------------------- bulk insert
    # Convenience helpers for the generator, which inserts many rows at once.

    def insert_room(self, **fields: Any) -> None:
        """Insert a single room row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO rooms ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_exit(self, **fields: Any) -> None:
        """Insert a single exit row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO exits ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_item(self, **fields: Any) -> None:
        """Insert a single item row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO items ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_npc(self, **fields: Any) -> None:
        """Insert a single NPC row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO npcs ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_dialogue_node(self, **fields: Any) -> None:
        """Insert a single dialogue node row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO dialogue_nodes ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_dialogue_option(self, **fields: Any) -> None:
        """Insert a single dialogue option row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO dialogue_options ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_lock(self, **fields: Any) -> None:
        """Insert a single lock row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO locks ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_puzzle(self, **fields: Any) -> None:
        """Insert a single puzzle row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO puzzles ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_command(self, **fields: Any) -> None:
        """Insert a single command row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO commands ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )

    def insert_flag(self, **fields: Any) -> None:
        """Insert a single flag row."""
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO flags ({cols}) VALUES ({placeholders})",  # noqa: S608
            tuple(fields.values()),
        )


    # -------------------------------------------------------- exit mutations

    def reveal_exit(self, exit_id: str) -> None:
        """Make a hidden exit visible (``is_hidden = 0``)."""
        self._mutate(
            "UPDATE exits SET is_hidden = 0 WHERE id = ?", (exit_id,)
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

    # --------------------------------------------------------- NPC mutations

    def kill_npc(self, npc_id: str) -> None:
        """Set an NPC's ``is_alive`` to ``0``."""
        self._mutate("UPDATE npcs SET is_alive = 0 WHERE id = ?", (npc_id,))

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

    def move_npc(self, npc_id: str, room_id: str) -> None:
        """Move an NPC to a different room."""
        self._mutate(
            "UPDATE npcs SET room_id = ? WHERE id = ?", (room_id, npc_id)
        )
