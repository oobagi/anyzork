"""Tests for the playtest logging system."""

from __future__ import annotations

from pathlib import Path

import pytest

from anyzork.db.schema import GameDB


@pytest.fixture
def db(tmp_path: Path) -> GameDB:
    """Create a minimal game DB with schema for playtest log tests."""
    path = tmp_path / "playtest_test.zork"
    game_db = GameDB(path)
    game_db.initialize(
        game_name="Playtest Test Game",
        author="tests",
        prompt="Testing playtest log.",
        seed="playtest-test",
    )
    # Add a start room and initialise the player so get_player() works.
    game_db._mutate(
        "INSERT INTO rooms (id, name, description, short_description, region, is_start) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("cell", "Cell", "A dark cell.", "Dark cell.", "dungeon", 1),
    )
    game_db.init_player("cell")
    try:
        yield game_db
    finally:
        game_db.close()


class TestPlaytestLogTable:
    """Verify the playtest_log table is created and usable."""

    def test_table_exists(self, db: GameDB) -> None:
        """The playtest_log table should be created by SCHEMA_SQL."""
        tables = [
            row["name"]
            for row in db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "playtest_log" in tables

    def test_indexes_exist(self, db: GameDB) -> None:
        """Both indexes on playtest_log should be present."""
        indexes = [
            row["name"]
            for row in db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        ]
        assert "idx_playtest_log_move" in indexes
        assert "idx_playtest_log_outcome" in indexes


class TestLogPlaytestEvent:
    """Verify log_playtest_event inserts correctly."""

    def test_insert_single_event(self, db: GameDB) -> None:
        db.log_playtest_event(1, "cell", "look", "builtin", "look")
        rows = db.get_playtest_log()
        assert len(rows) == 1
        row = rows[0]
        assert row["move_number"] == 1
        assert row["room_id"] == "cell"
        assert row["raw_input"] == "look"
        assert row["outcome"] == "builtin"
        assert row["outcome_detail"] == "look"
        assert row["timestamp"]  # non-empty ISO timestamp

    def test_insert_multiple_events(self, db: GameDB) -> None:
        db.log_playtest_event(1, "cell", "look", "builtin", "look")
        db.log_playtest_event(2, "cell", "open chest", "fail", "locked")
        db.log_playtest_event(3, "cell", "xyzzy", "unknown", "xyzzy")
        rows = db.get_playtest_log()
        assert len(rows) == 3
        assert rows[0]["outcome"] == "builtin"
        assert rows[1]["outcome"] == "fail"
        assert rows[2]["outcome"] == "unknown"

    def test_outcome_detail_optional(self, db: GameDB) -> None:
        db.log_playtest_event(1, "cell", "help", "builtin")
        rows = db.get_playtest_log()
        assert len(rows) == 1
        assert rows[0]["outcome_detail"] is None

    def test_ordering_by_move_number(self, db: GameDB) -> None:
        # Insert out of order.
        db.log_playtest_event(3, "cell", "c", "builtin")
        db.log_playtest_event(1, "cell", "a", "builtin")
        db.log_playtest_event(2, "cell", "b", "builtin")
        rows = db.get_playtest_log()
        assert [r["move_number"] for r in rows] == [1, 2, 3]


class TestGetPlaytestLog:
    """Verify get_playtest_log returns the right data."""

    def test_empty_log(self, db: GameDB) -> None:
        rows = db.get_playtest_log()
        assert rows == []

    def test_returns_dicts(self, db: GameDB) -> None:
        db.log_playtest_event(1, "cell", "look", "builtin", "look")
        rows = db.get_playtest_log()
        assert isinstance(rows[0], dict)


class TestClearPlaytestLog:
    """Verify clear_playtest_log deletes all rows."""

    def test_clear_removes_all(self, db: GameDB) -> None:
        db.log_playtest_event(1, "cell", "look", "builtin")
        db.log_playtest_event(2, "cell", "go north", "fail")
        assert len(db.get_playtest_log()) == 2
        db.clear_playtest_log()
        assert len(db.get_playtest_log()) == 0

    def test_clear_on_empty_is_noop(self, db: GameDB) -> None:
        db.clear_playtest_log()
        assert len(db.get_playtest_log()) == 0

    def test_log_after_clear(self, db: GameDB) -> None:
        db.log_playtest_event(1, "cell", "look", "builtin")
        db.clear_playtest_log()
        db.log_playtest_event(5, "cell", "go east", "success", "cmd_1")
        rows = db.get_playtest_log()
        assert len(rows) == 1
        assert rows[0]["move_number"] == 5


class TestPlaytestTimestamps:
    """Verify timestamps are ISO 8601."""

    def test_timestamp_is_iso_format(self, db: GameDB) -> None:
        from datetime import datetime

        db.log_playtest_event(1, "cell", "look", "builtin")
        row = db.get_playtest_log()[0]
        # Should not raise.
        parsed = datetime.fromisoformat(row["timestamp"])
        assert parsed.year >= 2024
