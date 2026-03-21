from __future__ import annotations

import shutil
from pathlib import Path

from anyzork.config import Config
from anyzork.services.play import open_play_session


def test_open_play_session_supports_programmatic_turns(
    tmp_path: Path,
    compiled_game_path: Path,
) -> None:
    games_dir = tmp_path / "games"
    saves_dir = tmp_path / "saves"
    games_dir.mkdir()
    saves_dir.mkdir()
    target_game = games_dir / "fixture_game.zork"
    shutil.copy2(compiled_game_path, target_game)

    session = open_play_session(
        "fixture_game",
        cfg=Config(games_dir=games_dir, saves_dir=saves_dir),
    )
    try:
        opening = session.open()
        assert "Fixture Game" in opening
        assert "Foyer" in opening

        look_turn = session.submit("look")
        assert look_turn.should_continue
        assert "Foyer" in look_turn.output

        win_turn = session.submit("win game")
        assert not win_turn.should_continue
        assert "Victory" in win_turn.output or "won" in win_turn.output.lower()
    finally:
        session.close()


def test_open_play_session_keeps_dialogue_state_inside_tui_turns(
    tmp_path: Path,
    dialogue_game_path: Path,
) -> None:
    games_dir = tmp_path / "games"
    saves_dir = tmp_path / "saves"
    games_dir.mkdir()
    saves_dir.mkdir()
    target_game = games_dir / "dialogue_fixture_game.zork"
    shutil.copy2(dialogue_game_path, target_game)

    session = open_play_session(
        "dialogue_fixture_game",
        cfg=Config(games_dir=games_dir, saves_dir=saves_dir),
    )
    try:
        session.open()
        assert session.db.get_player()["moves"] == 0

        start_turn = session.submit("talk to caretaker")
        assert start_turn.should_continue
        assert start_turn.in_dialogue
        assert start_turn.dialogue_speaker == "Caretaker"
        assert start_turn.dialogue_prompt == "Choose 1-2."
        assert "Talking to Caretaker" in start_turn.output
        assert "Ask what he guards." in start_turn.output
        assert session.db.get_player()["moves"] == 0

        advance_turn = session.submit("1")
        assert advance_turn.should_continue
        assert advance_turn.in_dialogue
        assert advance_turn.dialogue_prompt == "Choose 1-1."
        assert "what do travelers seek?" in advance_turn.output
        assert "Shelter." in advance_turn.output
        assert session.db.get_player()["moves"] == 0

        finish_turn = session.submit("1")
        assert not finish_turn.should_continue
        assert not finish_turn.in_dialogue
        assert "Victory" in finish_turn.output or "won" in finish_turn.output.lower()
        assert session.db.get_player()["moves"] == 1
    finally:
        session.close()
