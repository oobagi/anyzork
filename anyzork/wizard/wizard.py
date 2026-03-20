"""Interactive prompt builder wizard.

Walks the user through structured world-building fields one at a time,
assembles the filled fields into a rich prompt string, and returns it
for external ZorkScript authoring.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from anyzork.wizard.assembler import assemble_prompt
from anyzork.wizard.fields import (
    FIELDS,
    REALISM_OPTIONS,
    REALISM_VALUES,
    SCALE_OPTIONS,
    SCALE_VALUES,
    FieldType,
)

_LIST_FIELD_KEYS = {"locations", "characters", "items"}
_DESCRIBED_SELECTS = {
    "scale": (SCALE_OPTIONS, SCALE_VALUES),
    "realism": (REALISM_OPTIONS, REALISM_VALUES),
}


def _read_input(
    console: Console,
    prompt_str: str = " > ",
    *,
    allow_blank: bool = False,
    lower: bool = False,
) -> str | None:
    """Read a stripped single-line input value, optionally preserving blanks."""
    try:
        value = console.input(prompt_str).strip()
    except EOFError:
        return None
    if not value:
        if allow_blank:
            return ""
        return None
    return value.lower() if lower else value


def _read_multiline_entries(
    console: Console,
    prompt_str: str = " > ",
    *,
    normalizer: Callable[[str], str] | None = None,
) -> list[str] | None:
    """Read multi-line input until an empty line or EOF."""
    entries: list[str] = []
    while True:
        try:
            line = console.input(prompt_str)
        except EOFError:
            break
        if not line and not entries:
            return None
        if not line and entries:
            break
        entries.append(normalizer(line) if normalizer is not None else line)
    return entries if entries else None


def _read_multiline(console: Console, prompt_str: str = " > ") -> str | None:
    """Read multi-line input until the user submits an empty line.

    Returns None if no content was entered (user skipped).
    """
    lines = _read_multiline_entries(console, prompt_str)
    return "\n".join(lines) if lines else None


def _read_multiline_list(console: Console, prompt_str: str = " > ") -> list[str] | None:
    """Read multi-line input where each line is a list entry.

    Returns None if no content was entered (user skipped).
    """
    return _read_multiline_entries(console, prompt_str, normalizer=str.strip)


def _prompt_field(console: Console, field_def, current_value: Any = None) -> Any:
    """Prompt the user for a single field value.

    Returns the value entered, or None if the user skipped.
    """
    total = len(FIELDS)
    # Step header
    console.print()
    header = Text()
    header.append(f" Step {field_def.step}/{total}", style="bold cyan")
    header.append(f"  {field_def.label}", style="bold")
    if not field_def.required:
        header.append("  (optional)", style="italic")
    console.print(header)

    # Ask text and guidance
    console.print(f" {field_def.ask_text}")
    console.print(f" [italic]{field_def.guidance}[/italic]")

    # Show current value if editing
    if current_value is not None:
        if isinstance(current_value, list):
            console.print(f" [cyan]Current: {', '.join(str(v) for v in current_value)}[/cyan]")
        else:
            console.print(f" [cyan]Current: {current_value}[/cyan]")
    console.print()

    # Collect input based on field type
    if field_def.field_type == FieldType.MULTILINE:
        if field_def.key in _LIST_FIELD_KEYS:
            return _read_multiline_list(console)
        return _read_multiline(console)

    if field_def.field_type == FieldType.TEXT:
        return _read_input(console)

    if field_def.field_type == FieldType.SELECT:
        return _prompt_select(console, field_def)

    if field_def.field_type == FieldType.MULTI_SELECT:
        return _prompt_multi_select(console, field_def)

    return None


def _print_numbered_options(
    console: Console,
    options: list[str],
    *,
    descriptions: list[str] | None = None,
) -> None:
    """Render a numbered list of selectable options."""
    for i, option in enumerate(options, 1):
        if descriptions is None:
            console.print(f"  [cyan][{i}][/cyan] {option}")
        else:
            console.print(
                f"  [cyan][{i}][/cyan] [bold]{option:10s}[/bold] {descriptions[i - 1]}"
            )
    console.print()


def _prompt_described_select(
    console: Console,
    *,
    options: list[tuple[str, str]],
    values: list[str],
) -> str | None:
    """Handle numbered selects that also accept raw canonical values."""
    _print_numbered_options(
        console,
        [label for label, _ in options],
        descriptions=[description for _, description in options],
    )

    raw = _read_input(console)
    if raw is None:
        return None

    try:
        idx = int(raw) - 1
        if 0 <= idx < len(values):
            return values[idx]
    except ValueError:
        pass

    normalized = raw.lower()
    return normalized if normalized in values else None


def _prompt_select(console: Console, field_def) -> str | None:
    """Handle a single-select field."""
    if field_def.key in _DESCRIBED_SELECTS:
        options, values = _DESCRIBED_SELECTS[field_def.key]
        return _prompt_described_select(console, options=options, values=values)

    # Generic select (tone)
    options = field_def.options
    _print_numbered_options(console, options)
    raw = _read_input(console)
    if raw is None:
        return None

    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            selected = options[idx]
            if "custom" in selected.lower() and field_def.allow_custom:
                console.print("  Type your custom tone:")
                return _read_input(console, "  > ")
            return selected
    except ValueError:
        pass

    # Accept raw text input as custom
    return raw


def _prompt_multi_select(console: Console, field_def) -> list[str] | None:
    """Handle a multi-select field (genre tags)."""
    options = field_def.options
    _print_numbered_options(console, options)
    raw = _read_input(console)
    if raw is None:
        return None

    selected: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part) - 1
            if 0 <= idx < len(options):
                selected.append(options[idx])
            else:
                selected.append(part)
        except ValueError:
            # Treat non-numeric entries as custom tags
            selected.append(part)

    return selected if selected else None


def _show_preview(console: Console, values: dict[str, Any]) -> None:
    """Display a formatted preview of the assembled prompt."""
    prompt_text = assemble_prompt(values)

    panel = Panel(
        prompt_text,
        title="Prompt Preview",
        title_align="left",
        border_style="green",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def _show_welcome(console: Console) -> None:
    """Display the wizard welcome panel."""
    welcome = Text()
    welcome.append("Build your text adventure step by step.\n", style="bold")
    welcome.append("Fill in what inspires you, skip what doesn't.\n")
    welcome.append("Only the first field is required.\n")
    welcome.append("Tip: Press Enter to skip optional fields.", style="italic")

    panel = Panel(
        welcome,
        title="AnyZork -- World Builder",
        title_align="left",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def run_wizard(
    console: Console,
    initial_prompt: str | None = None,
    preset: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]] | None:
    """Run the interactive prompt builder wizard.

    Args:
        console: Rich console for all I/O.
        initial_prompt: If provided, pre-fills the World Description field.
        preset: If provided, pre-fills fields from a preset dict.

    Returns:
        A tuple of ``(prompt, realism, field_values)`` or ``None`` if the user quit.
    """
    # Initialize field values from preset or defaults.
    values: dict[str, Any] = {}
    if preset:
        values.update(preset)
    if initial_prompt:
        values["world_description"] = initial_prompt

    _show_welcome(console)

    # Walk through all fields.
    while True:
        for field_def in FIELDS:
            current = values.get(field_def.key)

            # If preset provided a value, show it and let user keep or change.
            if current is not None:
                result = _prompt_field(console, field_def, current_value=current)
                if result is not None:
                    values[field_def.key] = result
                # If result is None but current exists, keep the current value.
            else:
                result = _prompt_field(console, field_def)
                if result is not None:
                    values[field_def.key] = result
                elif field_def.required:
                    # Required field cannot be skipped.
                    console.print(" [red]This field is required. Please enter a value.[/red]")
                    while True:
                        result = _prompt_field(console, field_def)
                        too_short = (
                            result is not None
                            and isinstance(result, str)
                            and len(result.strip()) < 5
                        )
                        if too_short:
                            console.print(
                                " [red]Please enter at least 5 characters.[/red]"
                            )
                            result = None
                        if result is not None:
                            break
                    values[field_def.key] = result

        # Check that we have the required world_description.
        if not values.get("world_description"):
            console.print(
                "\n [red]World description is required. Restarting wizard.[/red]"
            )
            continue

        # Show preview and confirmation loop.
        while True:
            _show_preview(console, values)

            console.print()
            console.print(
                " [bold][G][/bold]enerate  "
                "[bold][E][/bold]dit a field  "
                "[bold][R][/bold]estart  "
                "[bold][Q][/bold]uit"
            )
            choice = _read_input(console, allow_blank=True, lower=True)
            if choice is None:
                return None

            if choice in ("g", "generate"):
                realism = values.get("realism", "medium")
                return assemble_prompt(values), realism, dict(values)

            if choice in ("q", "quit"):
                console.print("\n [yellow]Generation cancelled.[/yellow]")
                return None

            if choice in ("r", "restart"):
                values = {}
                if preset:
                    values.update(preset)
                if initial_prompt:
                    values["world_description"] = initial_prompt
                _show_welcome(console)
                break  # Break inner loop, continue outer loop (re-walk fields)

            if choice in ("e", "edit"):
                console.print()
                try:
                    field_num = console.input(
                        f" Which field to edit? (1-{len(FIELDS)}): "
                    ).strip()
                except EOFError:
                    continue
                try:
                    num = int(field_num)
                    if 1 <= num <= len(FIELDS):
                        target = FIELDS[num - 1]
                        current = values.get(target.key)
                        result = _prompt_field(console, target, current_value=current)
                        if result is not None:
                            values[target.key] = result
                        elif not target.required:
                            # User cleared an optional field
                            values.pop(target.key, None)
                    else:
                        console.print(" [red]Invalid field number.[/red]")
                except ValueError:
                    console.print(
                        f" [red]Please enter a number between 1 and {len(FIELDS)}.[/red]"
                    )
                continue  # Show preview again

            console.print(" [red]Invalid choice. Use G, E, R, or Q.[/red]")

        # If we get here, user chose restart -- outer loop continues.
