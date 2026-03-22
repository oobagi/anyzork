"""Shared CLI UI helpers — menus, error panels, confirmations."""

from __future__ import annotations

import sys

import click
from rich.console import Console

# ---------------------------------------------------------------------------
# Numbered menu picker
# ---------------------------------------------------------------------------

_QUIT_INPUTS = {"q", "quit", "exit"}


def pick_from_menu(
    console: Console,
    prompt_label: str,
    *,
    count: int,
    quit_words: set[str] | None = None,
) -> int | None:
    """Prompt the user to choose from a numbered list.

    Returns the 1-based index chosen, or ``None`` if the user quit.
    The caller is responsible for rendering the menu beforehand.

    Parameters
    ----------
    console:
        Rich console for output.
    prompt_label:
        Text shown in the prompt (e.g. ``"Choose a game number"``).
    count:
        Total number of valid options (1..count).
    quit_words:
        Inputs that cancel the selection. Defaults to ``{"q", "quit", "exit"}``.
    """
    quit_set = quit_words if quit_words is not None else _QUIT_INPUTS

    while True:
        choice = click.prompt(prompt_label, type=str).strip().lower()
        if choice in quit_set:
            console.print("[dim]Canceled.[/dim]")
            return None

        try:
            index = int(choice)
        except ValueError:
            console.print("[dim]Enter one of the numbers above, or q to cancel.[/dim]")
            continue

        if 1 <= index <= count:
            return index

        console.print("[dim]Enter one of the numbers above, or q to cancel.[/dim]")


# ---------------------------------------------------------------------------
# Error output
# ---------------------------------------------------------------------------


def print_error(console: Console, label: str, detail: object) -> None:
    """Print a ``[red]Label:[/red] detail`` error line."""
    console.print(f"[red]{label}:[/red] {detail}")


def fatal_error(console: Console, label: str, detail: object) -> None:
    """Print an error and exit with code 1."""
    print_error(console, label, detail)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Confirmation wrapper
# ---------------------------------------------------------------------------


def confirm_or_abort(
    prompt: str,
    *,
    default: bool = False,
    console: Console | None = None,
) -> bool:
    """Ask the user for confirmation.  Returns ``True`` if confirmed.

    When declined, prints ``[dim]Canceled.[/dim]`` and returns ``False``.
    """
    if click.confirm(prompt, default=default):
        return True
    if console is not None:
        console.print("[dim]Canceled.[/dim]")
    return False
