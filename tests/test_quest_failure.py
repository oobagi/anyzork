"""Tests for quest failure states (issue #23).

Covers:
- fail_quest effect handler
- failure_flag check in _check_quests
- Failed quest journal formatting
- ZorkScript parser failure/fail_message fields
- Normalizer auto-generates failure flag entries
- Validator warns on missing failure flag reference
"""

from __future__ import annotations

from pathlib import Path

from anyzork.db.schema import GameDB
from anyzork.engine.commands import apply_effect
from anyzork.importer import compile_import_spec
from anyzork.importer.normalize import _normalize_import_spec
from anyzork.validation import validate_game
from anyzork.zorkscript import parse_zorkscript

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quest_db(tmp_path: Path, name: str = "quest_test.zork") -> GameDB:
    """Create a minimal GameDB with quest infrastructure for failure tests."""
    db = GameDB(tmp_path / name)
    db.initialize(
        game_name="Quest Failure Test",
        author="tests",
        prompt="quest failure coverage",
        win_conditions='["game_won"]',
        room_count=1,
    )
    db.insert_flag(id="game_won", value="false")
    db.insert_flag(id="quest_complete", value="false")
    db.insert_flag(id="quest_fail", value="false")
    db.insert_flag(id="quest_discovered", value="false")
    db.insert_flag(id="obj_done", value="false")
    db.insert_room(
        id="foyer",
        name="Foyer",
        description="A quiet foyer.",
        short_description="A quiet foyer.",
        is_start=1,
    )
    db.insert_quest(
        id="test_quest",
        name="Test Quest",
        description="A test quest.",
        quest_type="side",
        status="active",
        discovery_flag="quest_discovered",
        completion_flag="quest_complete",
        failure_flag="quest_fail",
        fail_message="You failed the quest miserably.",
        score_value=10,
        sort_order=0,
    )
    db.insert_quest_objective(
        id="test_obj",
        quest_id="test_quest",
        description="Do the thing.",
        completion_flag="obj_done",
        order_index=0,
        is_optional=0,
        bonus_score=0,
    )
    db.init_player("foyer")
    return db


# ---------------------------------------------------------------------------
# fail_quest effect
# ---------------------------------------------------------------------------


class TestFailQuestEffect:
    """Tests for the fail_quest effect handler in commands.py."""

    def test_fail_quest_transitions_active_quest_to_failed(self, tmp_path: Path) -> None:
        db = _make_quest_db(tmp_path, "fail_active.zork")
        try:
            effect = {"type": "fail_quest", "quest": "test_quest"}
            messages = apply_effect(effect, db)

            quest = db.get_quest("test_quest")
            assert quest["status"] == "failed"
            assert db.has_flag("quest_fail") is True
            assert any("failed" in m.lower() or "miserably" in m for m in messages)
        finally:
            db.close()

    def test_fail_quest_is_noop_on_completed_quest(self, tmp_path: Path) -> None:
        db = _make_quest_db(tmp_path, "fail_completed.zork")
        try:
            db.update_quest_status("test_quest", "completed")

            effect = {"type": "fail_quest", "quest": "test_quest"}
            messages = apply_effect(effect, db)

            quest = db.get_quest("test_quest")
            assert quest["status"] == "completed"
            assert db.has_flag("quest_fail") is False
            assert messages == []
        finally:
            db.close()

    def test_fail_quest_is_noop_on_already_failed_quest(self, tmp_path: Path) -> None:
        db = _make_quest_db(tmp_path, "fail_already.zork")
        try:
            db.update_quest_status("test_quest", "failed")

            effect = {"type": "fail_quest", "quest": "test_quest"}
            messages = apply_effect(effect, db)

            quest = db.get_quest("test_quest")
            assert quest["status"] == "failed"
            # Flag should NOT have been set by the effect (it was a no-op).
            assert db.has_flag("quest_fail") is False
            assert messages == []
        finally:
            db.close()

    def test_fail_quest_emits_flag_set_event(self, tmp_path: Path) -> None:
        db = _make_quest_db(tmp_path, "fail_event.zork")
        try:
            emitted: list[tuple] = []

            def capture_event(event_type: str, **kwargs: object) -> None:
                emitted.append((event_type, kwargs))

            effect = {"type": "fail_quest", "quest": "test_quest"}
            apply_effect(effect, db, emit_event=capture_event)

            assert len(emitted) == 1
            assert emitted[0] == ("flag_set", {"flag": "quest_fail"})
        finally:
            db.close()


# ---------------------------------------------------------------------------
# failure_flag in _check_quests (integration via compile + GameEngine)
# ---------------------------------------------------------------------------


class TestFailureFlagCheckQuests:
    """Tests for failure_flag triggering failure in the quest state machine."""

    def _make_quest_spec(self, *, with_discovery: bool = True) -> dict:
        """Return a minimal import spec with a quest that has a failure_flag."""
        spec: dict = {
            "format": "anyzork.import.v1",
            "game": {
                "title": "Failure Flag Test",
                "author_prompt": "Quest failure flag coverage.",
                "intro_text": "You arrive.",
                "realism": "medium",
                "win_conditions": ["game_won"],
            },
            "player": {"start_room_id": "foyer"},
            "rooms": [
                {
                    "id": "foyer",
                    "name": "Foyer",
                    "description": "A quiet foyer.",
                    "is_start": True,
                },
            ],
            "exits": [],
            "items": [],
            "npcs": [],
            "dialogue_nodes": [],
            "dialogue_options": [],
            "locks": [],
            "puzzles": [],
            "flags": [
                {"id": "game_won", "value": False, "description": "Win flag"},
                {"id": "quest_fail", "value": False, "description": "Quest failure flag"},
                {"id": "obj_flag", "value": False, "description": "Objective flag"},
            ],
            "interactions": [],
            "commands": [
                {
                    "id": "win_game",
                    "verb": "win",
                    "pattern": "win game",
                    "preconditions": [],
                    "effects": [{"type": "set_flag", "flag": "game_won", "value": True}],
                    "success_message": "You win.",
                    "failure_message": "",
                },
            ],
            "quests": [
                {
                    "id": "doomed_quest",
                    "name": "Doomed Quest",
                    "description": "A quest destined to fail.",
                    "quest_type": "side",
                    "failure_flag": "quest_fail",
                    "fail_message": "The quest has failed!",
                    "score_value": 5,
                    "objectives": [
                        {
                            "id": "doomed_obj",
                            "description": "Complete before doom.",
                            "completion_flag": "obj_flag",
                        },
                    ],
                },
            ],
            "interaction_responses": [],
            "triggers": [],
        }
        if with_discovery:
            spec["flags"].append(
                {"id": "quest_discovered", "value": False, "description": "Discovery flag"}
            )
            spec["quests"][0]["discovery_flag"] = "quest_discovered"
        return spec

    def test_failure_flag_fails_active_quest(self, tmp_path: Path) -> None:
        """Setting the failure_flag on an active quest transitions it to failed."""
        spec = self._make_quest_spec()
        output_path = tmp_path / "fail_active.zork"
        compiled_path, _warnings = compile_import_spec(spec, output_path)

        with GameDB(compiled_path) as db:
            # Discover the quest first.
            db.set_flag("quest_discovered", "true")
            db.update_quest_status("doomed_quest", "active")
            # Now set the failure flag.
            db.set_flag("quest_fail", "true")

            quest = db.get_quest("doomed_quest")
            assert quest["failure_flag"] == "quest_fail"
            assert db.has_flag("quest_fail") is True

    def test_failure_flag_on_undiscovered_quest_is_silent(self, tmp_path: Path) -> None:
        """Setting failure_flag on an undiscovered quest should still record the flag."""
        spec = self._make_quest_spec()
        output_path = tmp_path / "fail_undiscovered.zork"
        compiled_path, _warnings = compile_import_spec(spec, output_path)

        with GameDB(compiled_path) as db:
            # Quest is undiscovered. Set the failure flag directly.
            db.set_flag("quest_fail", "true")
            quest = db.get_quest("doomed_quest")
            assert quest["status"] == "undiscovered"
            assert db.has_flag("quest_fail") is True


# ---------------------------------------------------------------------------
# Journal formatting
# ---------------------------------------------------------------------------


class TestFailedQuestJournalEntry:
    """Tests for _format_quest_entry formatting of failed quests."""

    def test_failed_quest_shows_failed_label_and_fail_message(self, tmp_path: Path) -> None:
        db = _make_quest_db(tmp_path, "journal_fail.zork")
        try:
            db.update_quest_status("test_quest", "failed")

            # Import the method from game engine
            from anyzork.engine.game import GameEngine

            engine = GameEngine.__new__(GameEngine)
            engine.db = db

            lines: list[str] = []
            quest = db.get_quest("test_quest")
            engine._format_quest_entry(quest, lines)

            text = "\n".join(lines)
            assert "[FAILED]" in text
            assert "You failed the quest miserably." in text
        finally:
            db.close()

    def test_failed_quest_falls_back_to_description_when_no_fail_message(
        self, tmp_path: Path,
    ) -> None:
        db = _make_quest_db(tmp_path, "journal_fallback.zork")
        try:
            # Insert a second quest with no fail_message.
            db.insert_quest(
                id="no_msg_quest",
                name="No Message Quest",
                description="A quest with no failure message.",
                quest_type="side",
                status="failed",
                completion_flag="quest_complete",
                score_value=0,
                sort_order=1,
            )
            db.insert_quest_objective(
                id="no_msg_obj",
                quest_id="no_msg_quest",
                description="Never completed.",
                completion_flag="obj_done",
                order_index=0,
                is_optional=0,
                bonus_score=0,
            )

            from anyzork.engine.game import GameEngine

            engine = GameEngine.__new__(GameEngine)
            engine.db = db

            lines: list[str] = []
            quest = db.get_quest("no_msg_quest")
            engine._format_quest_entry(quest, lines)

            text = "\n".join(lines)
            assert "[FAILED]" in text
            assert "A quest with no failure message." in text
        finally:
            db.close()


# ---------------------------------------------------------------------------
# ZorkScript parser
# ---------------------------------------------------------------------------


class TestZorkScriptQuestFailure:
    """Tests for parsing failure and fail_message fields in quest blocks."""

    def test_parse_failure_shorthand_and_fail_message(self) -> None:
        src = """\
game {
  title "Failure Parse Test"
  author "Test"
  max_score 0
  win [game_won]
}

player { start foyer }

room foyer {
  name "Foyer"
  description "A foyer."
  short "A foyer."
  start true
}

flag game_won "Win."
flag doom_flag "Doom."

quest side:rescue {
  name "Rescue Mission"
  description "Rescue the hostage."
  completion rescue_done
  failure doom_flag
  fail_message "The hostage was lost forever."
  score 5

  objective "Find the hostage" -> hostage_found
}
"""
        spec = parse_zorkscript(src)
        quests = spec["quests"]
        assert len(quests) == 1
        quest = quests[0]
        assert quest["id"] == "rescue"
        assert quest["failure_flag"] == "doom_flag"
        assert quest["fail_message"] == "The hostage was lost forever."
        assert quest["completion_flag"] == "rescue_done"
        assert quest["score_value"] == 5


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


class TestNormalizerFailureFlag:
    """Tests for auto-generation of failure flag entries in normalize.py."""

    def test_auto_generates_failure_flag_when_not_in_flags(self) -> None:
        spec = {
            "format": "anyzork.import.v1",
            "game": {
                "title": "Normalizer Test",
                "author_prompt": "Test.",
                "intro_text": "Hello.",
                "realism": "medium",
                "win_conditions": ["game_won"],
            },
            "player": {"start_room_id": "foyer"},
            "rooms": [
                {"id": "foyer", "name": "Foyer", "description": "A foyer.", "is_start": True},
            ],
            "exits": [],
            "items": [],
            "npcs": [],
            "dialogue_nodes": [],
            "dialogue_options": [],
            "locks": [],
            "puzzles": [],
            "flags": [
                {"id": "game_won", "value": False, "description": "Win."},
            ],
            "interactions": [],
            "commands": [],
            "quests": [
                {
                    "id": "test_quest",
                    "name": "Test Quest",
                    "description": "A test.",
                    "quest_type": "side",
                    "failure_flag": "my_fail_flag",
                    "objectives": [
                        {"id": "obj1", "description": "Do it."},
                    ],
                },
            ],
            "interaction_responses": [],
            "triggers": [],
        }

        _normalize_import_spec(spec)

        flag_ids = {f["id"] for f in spec["flags"]}
        assert "my_fail_flag" in flag_ids

    def test_does_not_duplicate_existing_failure_flag(self) -> None:
        spec = {
            "format": "anyzork.import.v1",
            "game": {
                "title": "Normalizer Test",
                "author_prompt": "Test.",
                "intro_text": "Hello.",
                "realism": "medium",
                "win_conditions": ["game_won"],
            },
            "player": {"start_room_id": "foyer"},
            "rooms": [
                {"id": "foyer", "name": "Foyer", "description": "A foyer.", "is_start": True},
            ],
            "exits": [],
            "items": [],
            "npcs": [],
            "dialogue_nodes": [],
            "dialogue_options": [],
            "locks": [],
            "puzzles": [],
            "flags": [
                {"id": "game_won", "value": False, "description": "Win."},
                {"id": "existing_fail", "value": "false", "description": "Already declared."},
            ],
            "interactions": [],
            "commands": [],
            "quests": [
                {
                    "id": "test_quest",
                    "name": "Test Quest",
                    "description": "A test.",
                    "quest_type": "side",
                    "failure_flag": "existing_fail",
                    "objectives": [
                        {"id": "obj1", "description": "Do it."},
                    ],
                },
            ],
            "interaction_responses": [],
            "triggers": [],
        }

        _normalize_import_spec(spec)

        fail_flags = [f for f in spec["flags"] if f["id"] == "existing_fail"]
        assert len(fail_flags) == 1


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class TestValidatorFailureFlag:
    """Tests for validator warning on missing failure_flag reference."""

    def test_warns_on_missing_failure_flag(self, tmp_path: Path) -> None:
        db = _make_quest_db(tmp_path, "validator_test.zork")
        try:
            # Remove the quest_fail flag so the validator can't find it.
            db._mutate("DELETE FROM flags WHERE id = ?", ("quest_fail",))

            messages = validate_game(db)
            assert any(
                "failure_flag" in str(m) and "quest_fail" in str(m) for m in messages
            ), f"Expected failure_flag warning, got: {messages}"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Round-trip: ZorkScript -> compile -> validate
# ---------------------------------------------------------------------------


class TestFailureRoundTrip:
    """End-to-end: ZorkScript with quest failure compiles and validates."""

    def test_quest_failure_round_trip(self, tmp_path: Path) -> None:
        src = """\
game {
  title "Failure Round Trip"
  author "Test"
  max_score 10
  win [game_won]
}

player { start foyer }

room foyer {
  name "Foyer"
  description "A dim foyer."
  short "A dim foyer."
  start true
}

flag game_won "Win."
flag doom_flag "Doom."
flag rescue_done "Rescue completed."
flag hostage_found "Found the hostage."

quest side:rescue {
  name "Rescue Mission"
  description "Rescue the hostage before it is too late."
  completion rescue_done
  failure doom_flag
  fail_message "The hostage was lost forever."
  score 10

  objective "Find the hostage" -> hostage_found
}

on "win game" in [foyer] {
  effect set_flag(game_won)
  success "You win."
}
"""
        spec = parse_zorkscript(src)
        output_path = tmp_path / "round_trip.zork"
        compiled_path, _warnings = compile_import_spec(spec, output_path)

        with GameDB(compiled_path) as db:
            quest = db.get_quest("rescue")
            assert quest is not None
            assert quest["failure_flag"] == "doom_flag"
            assert quest["fail_message"] == "The hostage was lost forever."

            errors = validate_game(db)
            error_list = [e for e in errors if e.severity == "error"]
            assert error_list == [], (
                "Round-trip produced validation errors:\n"
                + "\n".join(f"  - {e.message}" for e in error_list)
            )
