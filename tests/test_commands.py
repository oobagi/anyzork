from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from anyzork.db.schema import GameDB
from anyzork.engine.commands import apply_effect, check_precondition, resolve_command


@pytest.fixture
def command_db(tmp_path: Path) -> GameDB:
    db = GameDB(tmp_path / "commands.zork")
    db.initialize(
        game_name="Command Fixture",
        author="tests",
        prompt="command coverage",
        win_conditions='["game_won"]',

        room_count=2,
    )
    db.insert_flag(id="game_won", value="false")
    db.insert_flag(id="door_open", value="false")
    db.insert_room(
        id="foyer",
        name="Foyer",
        description="A quiet foyer.",
        short_description="A quiet foyer.",

        is_start=1,
    )
    db.insert_room(
        id="study",
        name="Study",
        description="A cramped study.",
        short_description="A cramped study.",

    )
    db.insert_exit(
        id="foyer_study",
        from_room_id="foyer",
        to_room_id="study",
        direction="north",
        is_locked=1,
        is_hidden=0,
    )
    db.insert_lock(
        id="study_lock",
        lock_type="flag",
        target_exit_id="foyer_study",
        required_flags=json.dumps(["door_open"]),
        locked_message="The study door stays shut.",
        unlock_message="The study door clicks open.",
        is_locked=1,
        consume_key=0,
    )
    db.insert_item(
        id="lever",
        name="lever",
        description="A brass lever.",
        examine_description="A brass lever on the wall.",
        room_id="foyer",
        is_takeable=0,
        is_visible=1,
    )
    db.insert_item(
        id="lantern",
        name="lantern",
        description="A hand lantern.",
        examine_description="A brass lantern.",
        room_id="foyer",
        is_takeable=1,
        is_visible=1,
        is_toggleable=1,
        toggle_state="off",
    )
    db.insert_item(
        id="battery_pack",
        name="battery pack",
        description="A battery pack.",
        examine_description="A battery pack with charges.",
        room_id="foyer",
        quantity=3,
        max_quantity=3,
        quantity_unit="charges",
    )
    db.insert_command(
        id="open_door",
        verb="pull",
        pattern="pull lever",
        preconditions="[]",
        effects=json.dumps(
            [
                {"type": "set_flag", "flag": "door_open"},
                {"type": "unlock", "lock": "study_lock"},
            ]
        ),
        success_message="The study door clicks open.",
        failure_message="",
        context_room_ids=json.dumps(["foyer"]),
        is_enabled=1,
    )
    db.insert_command(
        id="move_north",
        verb="go",
        pattern="go north",
        preconditions=json.dumps([{"type": "has_flag", "flag": "door_open"}]),
        effects=json.dumps([{"type": "move_player", "room": "study"}]),
        success_message="You step into the study.",
        failure_message="The study door stays shut.",
        context_room_ids=json.dumps(["foyer"]),
        is_enabled=1,
    )
    db.insert_command(
        id="toggle_lantern",
        verb="switch",
        pattern="switch lantern on",
        preconditions=json.dumps([{"type": "toggle_state", "item": "lantern", "state": "off"}]),
        effects=json.dumps([{"type": "set_toggle_state", "item": "lantern", "state": "on"}]),
        success_message="The lantern glows.",
        failure_message="",
        is_enabled=1,
    )
    db.insert_command(
        id="use_charge",
        verb="use",
        pattern="use battery pack",
        preconditions=json.dumps([{"type": "item_accessible", "item": "battery_pack"}]),
        effects=json.dumps([{"type": "consume_quantity", "item": "battery_pack", "amount": 1}]),
        success_message="One charge drains away.",
        failure_message="",
        is_enabled=1,
    )
    db.init_player("foyer")
    try:
        yield db
    finally:
        db.close()


def test_resolve_command_respects_room_scope_and_effects(command_db: GameDB) -> None:
    result = resolve_command("pull lever", command_db, current_room_id="foyer")

    assert result.success is True
    assert "set_flag" in result.effects_applied
    assert "unlock" in result.effects_applied
    assert command_db.has_flag("door_open") is True
    assert command_db.get_exit_by_direction("foyer", "north")["is_locked"] == 0


def test_resolve_command_applies_move_player_when_preconditions_pass(command_db: GameDB) -> None:
    resolve_command("pull lever", command_db, current_room_id="foyer")

    result = resolve_command("go north", command_db, current_room_id="foyer")

    assert result.success is True
    assert command_db.get_player()["current_room_id"] == "study"


def test_check_precondition_tracks_toggle_state_and_item_accessible(command_db: GameDB) -> None:
    assert check_precondition(
        {"type": "toggle_state", "item": "lantern", "state": "off"},
        command_db,
    )
    assert check_precondition(
        {"type": "item_accessible", "item": "battery_pack"},
        command_db,
    )


def test_resolve_command_consumes_quantity_and_updates_toggle_state(command_db: GameDB) -> None:
    toggle = resolve_command("switch lantern on", command_db, current_room_id="foyer")
    consume = resolve_command("use battery pack", command_db, current_room_id="foyer")

    assert toggle.success is True
    assert consume.success is True
    assert command_db.get_item("lantern")["toggle_state"] == "on"
    assert command_db.get_item_quantity("battery_pack") == 2


# ---------------------------------------------------------------------------
# Transaction context manager unit tests
# ---------------------------------------------------------------------------


class TestGameDBTransaction:
    """Tests for GameDB.transaction() context manager."""

    def test_transaction_commits_on_success(self, tmp_path: Path) -> None:
        db = GameDB(tmp_path / "tx.zork")
        db.initialize(
            game_name="TX Test", author="tests", prompt="tx",
            win_conditions='["done"]', room_count=1,
        )
        db.insert_flag(id="alpha", value="false")

        with db.transaction():
            db.set_flag("alpha", "true")

        assert db.has_flag("alpha") is True
        db.close()

    def test_transaction_rolls_back_on_exception(self, tmp_path: Path) -> None:
        db = GameDB(tmp_path / "tx.zork")
        db.initialize(
            game_name="TX Test", author="tests", prompt="tx",
            win_conditions='["done"]', room_count=1,
        )
        db.insert_flag(id="beta", value="false")

        with pytest.raises(RuntimeError), db.transaction():
            db.set_flag("beta", "true")
            raise RuntimeError("boom")

        assert db.has_flag("beta") is False
        db.close()

    def test_nested_transaction_is_reentrant(self, tmp_path: Path) -> None:
        db = GameDB(tmp_path / "tx.zork")
        db.initialize(
            game_name="TX Test", author="tests", prompt="tx",
            win_conditions='["done"]', room_count=1,
        )
        db.insert_flag(id="gamma", value="false")

        with db.transaction():
            db.set_flag("gamma", "true")
            # Nested call should just yield without a second commit/rollback.
            with db.transaction():
                pass

        assert db.has_flag("gamma") is True
        db.close()

    def test_in_transaction_flag_resets_after_exception(self, tmp_path: Path) -> None:
        db = GameDB(tmp_path / "tx.zork")
        db.initialize(
            game_name="TX Test", author="tests", prompt="tx",
            win_conditions='["done"]', room_count=1,
        )
        db.insert_flag(id="delta", value="false")

        with pytest.raises(RuntimeError), db.transaction():
            raise RuntimeError("fail")

        # The flag should be reset so subsequent non-transactional writes
        # auto-commit normally.
        assert db._in_transaction is False
        db.set_flag("delta", "true")
        assert db.has_flag("delta") is True
        db.close()


# ---------------------------------------------------------------------------
# Atomic command execution (integration tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def atomic_db(tmp_path: Path) -> GameDB:
    """Database with commands for atomicity testing."""
    db = GameDB(tmp_path / "atomic.zork")
    db.initialize(
        game_name="Atomic Fixture",
        author="tests",
        prompt="atomic",
        win_conditions='["game_won"]',

        room_count=1,
    )
    db.insert_flag(id="game_won", value="false")
    db.insert_flag(id="step_one", value="false")
    db.insert_room(
        id="foyer",
        name="Foyer",
        description="A quiet foyer.",
        short_description="A quiet foyer.",

        is_start=1,
    )
    db.insert_item(
        id="gem",
        name="gem",
        description="A sparkling gem.",
        examine_description="A sparkling gem.",
        room_id="foyer",
        is_takeable=1,
        is_visible=1,
    )
    # Command with two effects (both are valid effect types; tests will
    # patch apply_effect to raise on the second call).
    db.insert_command(
        id="do_both",
        verb="do",
        pattern="do thing",
        preconditions="[]",
        effects=json.dumps([
            {"type": "set_flag", "flag": "step_one"},
            {"type": "set_flag", "flag": "game_won"},
        ]),
        success_message="Doing the thing.",
        failure_message="",
        context_room_ids=json.dumps(["foyer"]),
        is_enabled=1,
    )
    # A clean command with multiple effects that all succeed.
    db.insert_command(
        id="do_clean",
        verb="clean",
        pattern="clean up",
        preconditions="[]",
        effects=json.dumps([
            {"type": "set_flag", "flag": "step_one"},
            {"type": "set_flag", "flag": "game_won"},
        ]),
        success_message="All clean.",
        failure_message="",
        context_room_ids=json.dumps(["foyer"]),
        is_enabled=1,
    )
    # A one-shot command (tests will patch apply_effect to raise).
    db.insert_command(
        id="one_shot_fail",
        verb="trigger",
        pattern="trigger trap",
        preconditions="[]",
        effects=json.dumps([
            {"type": "set_flag", "flag": "step_one"},
            {"type": "set_flag", "flag": "game_won"},
        ]),
        success_message="Triggered.",
        failure_message="",
        context_room_ids=json.dumps(["foyer"]),
        is_enabled=1,
        one_shot=1,
    )
    db.init_player("foyer")
    try:
        yield db
    finally:
        db.close()


def _make_apply_effect_that_fails_on_call_n(real_fn, fail_on: int = 2):
    """Return a wrapper around apply_effect that raises on the Nth call."""
    call_count = 0

    def wrapper(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == fail_on:
            raise RuntimeError("Simulated effect failure")
        return real_fn(*args, **kwargs)

    return wrapper


def test_atomic_all_effects_applied_on_success(atomic_db: GameDB) -> None:
    """When all effects succeed, all changes are committed."""
    result = resolve_command("clean up", atomic_db, current_room_id="foyer")

    assert result.success is True
    assert atomic_db.has_flag("step_one") is True
    assert atomic_db.has_flag("game_won") is True


def test_atomic_no_effects_committed_on_failure(atomic_db: GameDB) -> None:
    """When an effect raises, no effects from the command are committed."""
    failing = _make_apply_effect_that_fails_on_call_n(apply_effect, fail_on=2)
    with patch("anyzork.engine.commands.apply_effect", side_effect=failing):
        result = resolve_command("do thing", atomic_db, current_room_id="foyer")

    # The command should not succeed because the effect loop raised.
    assert result.success is False
    # The first effect (set_flag step_one) must be rolled back.
    assert atomic_db.has_flag("step_one") is False


def test_atomic_one_shot_not_marked_on_failure(atomic_db: GameDB) -> None:
    """A one-shot command is not marked executed if effects fail."""
    failing = _make_apply_effect_that_fails_on_call_n(apply_effect, fail_on=2)
    with patch("anyzork.engine.commands.apply_effect", side_effect=failing):
        result = resolve_command("trigger trap", atomic_db, current_room_id="foyer")

    assert result.success is False
    # The one-shot marker should not be set since the transaction rolled back.
    cmd = atomic_db.get_command("one_shot_fail")
    assert cmd["executed"] == 0


def test_atomic_rollback_allows_retry(atomic_db: GameDB) -> None:
    """After a rolled-back command, subsequent commands still work."""
    failing = _make_apply_effect_that_fails_on_call_n(apply_effect, fail_on=2)
    with patch("anyzork.engine.commands.apply_effect", side_effect=failing):
        resolve_command("do thing", atomic_db, current_room_id="foyer")
    assert atomic_db.has_flag("step_one") is False

    # A different, working command should still succeed.
    result = resolve_command("clean up", atomic_db, current_room_id="foyer")
    assert result.success is True
    assert atomic_db.has_flag("step_one") is True
