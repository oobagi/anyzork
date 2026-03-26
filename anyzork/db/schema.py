"""SQLite schema and database interface for AnyZork game files (.zork).

This module defines the complete database schema for a .zork game file and
provides the GameDB class — the single interface that the engine, generator,
and CLI use to read and write game state.

Every table, field, type, and constraint is derived from the authoritative
world-schema reference (docs/engine/WORLD-SCHEMA.md).
"""

from __future__ import annotations

import json as _json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from anyzork.db.items import ItemsMixin
from anyzork.db.npcs import NPCsMixin
from anyzork.db.player import PlayerMixin
from anyzork.db.quests_db import QuestsMixin
from anyzork.db.rooms import RoomsMixin
from anyzork.db.triggers_db import TriggersMixin
from anyzork.versioning import (
    APP_VERSION,
    RUNTIME_COMPAT_VERSION,
    is_runtime_compat_version,
)

# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """\
-- AnyZork World Schema v1.0
-- Authoritative source: docs/engine/WORLD-SCHEMA.md

-- -------------------------------------------------------
-- metadata: game-level information (single row, id = 1)
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS metadata (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    title           TEXT    NOT NULL,
    author_prompt   TEXT    NOT NULL,
    seed            TEXT,
    version         TEXT    NOT NULL DEFAULT 'r1',   -- runtime compatibility version
    app_version     TEXT,                            -- AnyZork app version that wrote the file
    prompt_system_version TEXT,                      -- prompt-generation system fingerprint
    created_at      TEXT    NOT NULL,
    max_score       INTEGER NOT NULL DEFAULT 0,
    win_conditions  TEXT    NOT NULL DEFAULT '[]',   -- JSON array of flag IDs
    lose_conditions TEXT,                             -- JSON array or NULL
    intro_text      TEXT    NOT NULL DEFAULT '',
    win_text        TEXT    NOT NULL DEFAULT '',
    lose_text       TEXT,
    room_count      INTEGER NOT NULL DEFAULT 0,
    realism         TEXT NOT NULL DEFAULT 'medium',  -- "low", "medium", "high"
    game_id         TEXT,
    source_game_id  TEXT,
    source_path     TEXT,
    save_slot       TEXT,
    last_played_at  TEXT,
    is_template     INTEGER NOT NULL DEFAULT 0
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
    is_dark           INTEGER NOT NULL DEFAULT 0,
    is_start          INTEGER NOT NULL DEFAULT 0,
    visited           INTEGER NOT NULL DEFAULT 0
);

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
    combination         TEXT,
    unlock_message      TEXT,
    accepts_items       TEXT,       -- JSON array of accepted item IDs, NULL = accepts anything
    reject_message      TEXT,       -- Custom rejection text when whitelist blocks an item
    home_room_id        TEXT    REFERENCES rooms(id),
    drop_description    TEXT,
    -- Item states
    is_toggleable       INTEGER NOT NULL DEFAULT 0,
    toggle_state        TEXT,           -- "off", "on", or custom state
    toggle_on_message   TEXT,           -- Message when toggled to "on"
    toggle_off_message  TEXT,           -- Message when toggled to "off"
    toggle_states       TEXT,           -- JSON array of valid states for multi-state items
    toggle_messages     TEXT,           -- JSON object mapping state -> transition message
    requires_item_id    TEXT REFERENCES items(id),  -- Item needed to function (e.g., batteries)
    requires_message    TEXT,           -- Message when required item is missing/depleted
    -- Interaction matrix
    item_tags           TEXT,           -- JSON array of tags: ["weapon", "firearm", "light_source"]
    -- Combat
    damage              INTEGER,        -- Weapon damage (NULL = not a weapon)
    -- Consumables
    quantity            INTEGER,        -- Current quantity (NULL = not stackable)
    max_quantity        INTEGER,        -- Maximum quantity
    quantity_unit       TEXT,           -- Display unit: "rounds", "charges", "uses"
    depleted_message    TEXT,           -- Message when quantity hits 0
    quantity_description TEXT,          -- Template: "The {name} has {quantity} {unit} remaining."
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
    room_id           TEXT    REFERENCES rooms(id),
                                -- NULL = template NPC (in limbo, not yet spawned)
    is_alive          INTEGER NOT NULL DEFAULT 1,
    is_blocking       INTEGER NOT NULL DEFAULT 0,
    blocked_exit_id   TEXT    REFERENCES exits(id),
    unblock_flag      TEXT,
    block_message     TEXT,           -- custom message when NPC blocks exit
    default_dialogue  TEXT    NOT NULL,
    hp                INTEGER,
    damage            INTEGER,
    defense           INTEGER,        -- damage reduction (incoming damage - defense, min 1)
    weakness          TEXT,            -- tag that makes NPC take double damage (e.g., "ice")
    drop_item         TEXT    REFERENCES items(id),  -- item dropped on death
    category          TEXT,   -- NPC category tag for interaction matrix:
                                -- "character", "merchant", "hostile"
    home_room_id      TEXT    REFERENCES rooms(id),
    room_description  TEXT,
    drop_description  TEXT,
    disposition       TEXT    NOT NULL DEFAULT 'neutral',
                                -- "hostile", "friendly", "neutral"
    faction           TEXT    -- optional faction tag for group operations
);

CREATE INDEX IF NOT EXISTS idx_npcs_room_id ON npcs(room_id);
CREATE INDEX IF NOT EXISTS idx_npcs_faction ON npcs(faction);

-- -------------------------------------------------------
-- dialogue_nodes: branching dialogue tree nodes
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS dialogue_nodes (
    id          TEXT PRIMARY KEY,
    npc_id      TEXT NOT NULL REFERENCES npcs(id),
    content     TEXT NOT NULL,
    set_flags   TEXT,          -- JSON array of flags to set when this node is visited
    effects     TEXT,          -- JSON array of effects to execute when this node is visited
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
    context_room_ids TEXT,                          -- JSON array of room IDs, NULL = global
    puzzle_id       TEXT    REFERENCES puzzles(id),
    priority        INTEGER NOT NULL DEFAULT 0,
    is_enabled      INTEGER NOT NULL DEFAULT 1,
    one_shot        INTEGER NOT NULL DEFAULT 0,
    executed        INTEGER NOT NULL DEFAULT 0,
    done_message    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_commands_verb       ON commands(verb);
CREATE INDEX IF NOT EXISTS idx_commands_context     ON commands(context_room_ids);
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
    failure_flag    TEXT,              -- when set, quest transitions to failed
    fail_message    TEXT,              -- authored flavor text shown on failure
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

-- -------------------------------------------------------
-- interaction_responses: category-level item interaction templates
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS interaction_responses (
    id              TEXT PRIMARY KEY,
    item_tag        TEXT NOT NULL,       -- Tag on the item being used (e.g., "firearm")
    target_category TEXT NOT NULL,       -- Category of the target (e.g., "character")
    response        TEXT NOT NULL,       -- Response template with {item} and {target} placeholders
    consumes        INTEGER NOT NULL DEFAULT 0,  -- Quantity consumed per use
    score_change    INTEGER NOT NULL DEFAULT 0,  -- Score adjustment
    flag_to_set     TEXT,               -- Optional flag to set on interaction
    effects         TEXT                -- JSON array of effect objects, same format as commands
);
CREATE INDEX IF NOT EXISTS idx_interactions_tag_cat
    ON interaction_responses(item_tag, target_category);

-- -------------------------------------------------------
-- triggers: reactive rules that fire on game events
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS triggers (
    id              TEXT PRIMARY KEY,
    event_type      TEXT    NOT NULL,       -- room_enter | flag_set | dialogue_node
                                            -- | item_taken | item_dropped | command_exec
                                            -- | on_item_stolen | on_attacked
    event_data      TEXT    NOT NULL DEFAULT '{}',
                                            -- JSON: partial match against
                                            -- emitted event data
    preconditions   TEXT    NOT NULL DEFAULT '[]',  -- JSON array, same format as DSL commands
    effects         TEXT    NOT NULL DEFAULT '[]',  -- JSON array, same format as DSL commands
    message         TEXT,                           -- Optional text to display when trigger fires
    priority        INTEGER NOT NULL DEFAULT 0,     -- Higher = evaluated first
    one_shot        INTEGER NOT NULL DEFAULT 0,     -- 1 = fire only once
    executed        INTEGER NOT NULL DEFAULT 0,     -- 1 = already fired (for one-shot)
    is_enabled      INTEGER NOT NULL DEFAULT 1,     -- 0 = disabled
    disarm_flag     TEXT                            -- when set, trap is skipped
);
CREATE INDEX IF NOT EXISTS idx_triggers_event_type ON triggers(event_type);
CREATE INDEX IF NOT EXISTS idx_triggers_event_data ON triggers(event_data);

-- -------------------------------------------------------
-- variables: general-purpose numerical variables
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS variables (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

-- -------------------------------------------------------
-- scheduled_triggers: deferred trigger deadlines
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheduled_triggers (
    trigger_id  TEXT PRIMARY KEY,
    fire_on_move INTEGER NOT NULL    -- move number when this trigger should fire
);

-- -------------------------------------------------------
-- hints: context-aware hints the player can request
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS hints (
    id              TEXT PRIMARY KEY,
    text            TEXT    NOT NULL,       -- hint text shown to the player
    preconditions   TEXT    NOT NULL DEFAULT '[]',  -- JSON array, same as commands
    priority        INTEGER NOT NULL DEFAULT 0,     -- higher = preferred
    used            INTEGER NOT NULL DEFAULT 0      -- 1 = already shown
);
CREATE INDEX IF NOT EXISTS idx_hints_priority ON hints(priority);

-- -------------------------------------------------------
-- npc_behaviors: autonomous NPC actions executed each turn
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS npc_behaviors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_id          TEXT    NOT NULL REFERENCES npcs(id),
    preconditions   TEXT    NOT NULL DEFAULT '[]',  -- JSON array, same as commands
    effects         TEXT    NOT NULL DEFAULT '[]',  -- JSON array, same as commands
    message         TEXT,                           -- text shown when behavior fires
    one_shot        INTEGER NOT NULL DEFAULT 0,     -- 1 = fire only once
    executed        INTEGER NOT NULL DEFAULT 0      -- 1 = already fired (for one-shot)
);
CREATE INDEX IF NOT EXISTS idx_npc_behaviors_npc ON npc_behaviors(npc_id);
"""


_METADATA_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "author_prompt",
        "seed",
        "version",
        "app_version",
        "prompt_system_version",
        "created_at",
        "max_score",
        "win_conditions",
        "lose_conditions",
        "intro_text",
        "win_text",
        "lose_text",
        "room_count",
        "realism",
        "game_id",
        "source_game_id",
        "source_path",
        "save_slot",
        "last_played_at",
        "is_template",
    }
)

_METADATA_MIGRATIONS: dict[str, str] = {
    "app_version": "TEXT",
    "game_id": "TEXT",
    "prompt_system_version": "TEXT",
    "source_game_id": "TEXT",
    "source_path": "TEXT",
    "save_slot": "TEXT",
    "last_played_at": "TEXT",
    "is_template": "INTEGER NOT NULL DEFAULT 0",
}


# ---------------------------------------------------------------------------
# GameDB — the single interface for reading / writing game state
# ---------------------------------------------------------------------------

class GameDB(
    RoomsMixin,
    ItemsMixin,
    NPCsMixin,
    PlayerMixin,
    TriggersMixin,
    QuestsMixin,
):
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
        # Keep save files self-contained and avoid WAL sidecar-file issues
        # during local CLI play and fixture rebuilds.
        self._conn.execute("PRAGMA journal_mode=DELETE")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
        self._in_transaction = False
        self._conn.executescript(SCHEMA_SQL)
        self._ensure_metadata_columns()

    # ----------------------------------------------------------- lifecycle

    def _ensure_metadata_columns(self) -> None:
        """Backfill metadata columns for older .zork files."""
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(metadata)").fetchall()
        }
        if not columns:
            return

        for name, column_sql in _METADATA_MIGRATIONS.items():
            if name not in columns:
                self._conn.execute(
                    f"ALTER TABLE metadata ADD COLUMN {name} {column_sql}"
                )

        row = self._conn.execute(
            "SELECT id, game_id, is_template, version, app_version "
            "FROM metadata WHERE id = 1"
        ).fetchone()
        if row is not None:
            if not row["game_id"]:
                self._conn.execute(
                    "UPDATE metadata SET game_id = ? WHERE id = 1",
                    (str(uuid4()),),
                )
            if row["is_template"] is None:
                self._conn.execute(
                    "UPDATE metadata SET is_template = 0 WHERE id = 1"
                )
            if row["app_version"] is None and row["version"]:
                self._conn.execute(
                    "UPDATE metadata SET app_version = ? WHERE id = 1",
                    (row["version"],),
                )
            if not is_runtime_compat_version(row["version"]):
                self._conn.execute(
                    "UPDATE metadata SET version = ? WHERE id = 1",
                    (RUNTIME_COMPAT_VERSION,),
                )

        self._conn.commit()

    def initialize(
        self,
        game_name: str,
        author: str,
        prompt: str,
        *,
        seed: str | None = None,
        app_version: str | None = None,
        intro_text: str = "",
        win_text: str = "",
        lose_text: str | None = None,
        win_conditions: str = "[]",
        lose_conditions: str | None = None,
        max_score: int = 0,
        room_count: int = 0,
        game_id: str | None = None,
        prompt_system_version: str | None = None,
        runtime_compat_version: str | None = None,
        source_game_id: str | None = None,
        source_path: str | None = None,
        save_slot: str | None = None,
        last_played_at: str | None = None,
        is_template: bool = False,
    ) -> None:
        """Create all tables and insert the initial metadata row."""
        self._conn.executescript(SCHEMA_SQL)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO metadata
                (id, title, author_prompt, seed, version, app_version, prompt_system_version,
                 created_at,
                 max_score, win_conditions, lose_conditions,
                 intro_text, win_text, lose_text,
                 room_count, game_id, source_game_id,
                 source_path, save_slot, last_played_at, is_template)
            VALUES (
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                game_name,
                prompt,
                seed,
                runtime_compat_version or RUNTIME_COMPAT_VERSION,
                app_version or APP_VERSION,
                prompt_system_version,
                datetime.now(UTC).isoformat(),
                max_score,
                win_conditions,
                lose_conditions,
                intro_text,
                win_text,
                lose_text,
                room_count,
                game_id or str(uuid4()),
                source_game_id,
                source_path,
                save_slot,
                last_played_at,
                1 if is_template else 0,
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

    def __enter__(self) -> GameDB:
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
        if not self._in_transaction:
            self._conn.commit()
        return cur

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Execute a block of mutations atomically.

        While inside this context manager, ``_mutate`` will not auto-commit.
        On clean exit the transaction is committed; on exception it is rolled
        back so the database returns to its prior state.
        """
        if self._in_transaction:
            # Already inside a transaction — just yield (re-entrant/nested).
            yield
            return
        self._in_transaction = True
        try:
            yield
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise
        finally:
            self._in_transaction = False

    # ------------------------------------------------------------- metadata

    def get_meta(self, key: str) -> Any:
        """Return a single metadata field value by column name."""
        # Validate key is a real column to prevent injection.
        if key not in _METADATA_FIELDS:
            raise KeyError(f"Unknown metadata key: {key!r}")
        row = self._conn.execute(
            f"SELECT {key} FROM metadata WHERE id = 1"
        ).fetchone()
        return row[key] if row else None

    def set_meta(self, key: str, value: Any) -> None:
        """Update a single metadata field by column name."""
        if key not in _METADATA_FIELDS:
            raise KeyError(f"Unknown metadata key: {key!r}")
        self._mutate(
            f"UPDATE metadata SET {key} = ? WHERE id = 1", (value,)
        )

    def get_all_meta(self) -> dict | None:
        """Return the full metadata row as a dict."""
        return self._fetchone("SELECT * FROM metadata WHERE id = 1")

    def touch_last_played(self) -> None:
        """Stamp the metadata row with the current UTC time."""
        self.set_meta("last_played_at", datetime.now(UTC).isoformat())

    # ------------------------------------------------------------ commands

    def get_commands_for_verb(self, verb: str, current_room_id: str | None = None) -> list[dict]:
        """Return all enabled commands matching a verb, ordered by priority.

        Higher priority commands are returned first.  If *current_room_id*
        is given, commands whose ``context_room_ids`` JSON array does not
        include that room are excluded.  Commands with ``context_room_ids``
        set to ``NULL`` are considered global and always included.
        """
        rows = self._fetchall(
            """
            SELECT * FROM commands
            WHERE LOWER(verb) = LOWER(?) AND is_enabled = 1
            ORDER BY priority DESC
            """,
            (verb,),
        )

        if current_room_id is None:
            return rows

        filtered: list[dict] = []
        for row in rows:
            ctx = row.get("context_room_ids")
            if ctx is None:
                # Global command -- always in scope
                filtered.append(row)
            else:
                try:
                    room_list = _json.loads(ctx)
                except (TypeError, _json.JSONDecodeError):
                    # Treat unparseable as global (defensive)
                    filtered.append(row)
                    continue
                if not room_list:
                    filtered.append(row)
                    continue
                if current_room_id in room_list:
                    filtered.append(row)
        return filtered

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

    # ----------------------------------------------------------- bulk insert

    def insert_command(self, **fields: Any) -> None:
        """Insert a single command row.

        Accepts either the new ``context_room_ids`` (JSON array string or
        ``None``) or the legacy ``context_room_id`` (single room ID string
        or ``None``).  When the legacy field is supplied it is automatically
        converted to a single-element JSON array.
        """
        # --- Backward compat: convert legacy context_room_id -> context_room_ids ---
        if "context_room_id" in fields:
            legacy_value = fields.pop("context_room_id")
            if "context_room_ids" not in fields:
                if legacy_value is not None:
                    fields["context_room_ids"] = _json.dumps([legacy_value])
                else:
                    fields["context_room_ids"] = None

        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        self._mutate(
            f"INSERT INTO commands ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
