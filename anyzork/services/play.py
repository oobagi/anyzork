"""Programmatic play-session helpers for the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from anyzork.config import Config
from anyzork.db.schema import GameDB
from anyzork.engine.game import GameEngine

from . import library as library_service


@dataclass(frozen=True)
class PlayTurn:
    """A single turn result from the deterministic engine."""

    output: str
    should_continue: bool
    in_dialogue: bool = False
    dialogue_speaker: str | None = None
    dialogue_prompt: str | None = None


@dataclass(frozen=True)
class PlaySessionInfo:
    """Resolved play target metadata."""

    source_path: Path
    play_path: Path
    title: str
    action: str
    direct: bool


class PlaySession:
    """A long-lived deterministic play session for TUI use."""

    def __init__(self, info: PlaySessionInfo) -> None:
        self.info = info
        self.db = GameDB(info.play_path)
        self.engine = GameEngine(
            self.db,
            console=Console(),
            interactive_dialogue=False,
        )
        self._opened = False

    def open(self) -> str:
        """Render the opening output for the session once."""
        if self._opened:
            return ""
        self.db.touch_last_played()
        self._opened = True
        return self.engine.capture_opening()

    def submit(self, command: str) -> PlayTurn:
        """Submit a command and return the rendered engine output."""
        self.db.touch_last_played()
        should_continue, output = self.engine.submit_command(command)
        return PlayTurn(
            output=output,
            should_continue=should_continue,
            in_dialogue=self.engine.in_dialogue,
            dialogue_speaker=self.engine.dialogue_speaker,
            dialogue_prompt=self.engine.dialogue_prompt,
        )

    def close(self) -> None:
        """Close the backing database connection."""
        self.db.close()


def open_play_session(
    game_ref: str,
    *,
    slot: str = "default",
    restart: bool = False,
    direct: bool = False,
    cfg: Config | None = None,
) -> PlaySession:
    """Open a TUI-friendly deterministic play session."""
    config = cfg or Config()
    source_path = library_service.resolve_game_reference(game_ref, config)

    if library_service.is_within(source_path, config.saves_dir):
        if restart:
            raise ValueError("Cannot restart an existing save file directly.")
        play_path = source_path
        action = "resume-save"
        is_direct = True
    elif direct:
        play_path = source_path
        action = "direct"
        is_direct = True
    else:
        play_path, action = library_service.prepare_managed_save(
            source_path,
            slot,
            restart,
            config,
        )
        is_direct = False

    meta = library_service.read_zork_metadata(play_path) or {}
    title = str(meta.get("title") or source_path.stem)
    info = PlaySessionInfo(
        source_path=source_path.resolve(),
        play_path=play_path.resolve(),
        title=title,
        action=action,
        direct=is_direct,
    )
    return PlaySession(info)
