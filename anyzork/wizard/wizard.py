"""Interactive prompt builder wizard.

Walks the user through structured world-building fields one at a time,
assembles the filled fields into a rich prompt string, and returns it
for the generation pipeline.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from anyzork.wizard.assembler import assemble_prompt
from anyzork.wizard.fields import (
    FIELDS,
    GENRE_OPTIONS,
    SCALE_OPTIONS,
    SCALE_VALUES,
    TONE_OPTIONS,
    FieldType,
)


def _read_multiline(console: Console, prompt_str: str = " > ") -> str | None:
    """Read multi-line input until the user submits an empty line.

    Returns None if no content was entered (user skipped).
    """
    lines: list[str] = []
    while True:
        try:
            line = console.input(prompt_str)
        except EOFError:
            break
        if not line and not lines:
            # First line empty = skip
            return None
        if not line and lines:
            # Empty line after content = done
            break
        lines.append(line)
    return "\n".join(lines) if lines else None


def _read_multiline_list(console: Console, prompt_str: str = " > ") -> list[str] | None:
    """Read multi-line input where each line is a list entry.

    Returns None if no content was entered (user skipped).
    """
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
        entries.append(line.strip())
    return entries if entries else None


def _prompt_field(console: Console, field_def, current_value: Any = None) -> Any:
    """Prompt the user for a single field value.

    Returns the value entered, or None if the user skipped.
    """
    total = len(FIELDS)
    required_str = "required" if field_def.required else "optional, press Enter to skip"

    # Step header
    console.print()
    header = Text()
    header.append(f" Step {field_def.step} of {total}", style="bold cyan")
    header.append(f" -- {field_def.label}", style="bold")
    header.append(f" ({required_str})", style="dim")
    console.print(header)
    console.print()

    # Ask text and guidance
    console.print(f" {field_def.ask_text}", style="bold")
    console.print(f" [dim]{field_def.guidance}[/dim]")

    # Show current value if editing
    if current_value is not None:
        if isinstance(current_value, list):
            console.print(f" [dim]Current: {', '.join(str(v) for v in current_value)}[/dim]")
        else:
            console.print(f" [dim]Current: {current_value}[/dim]")
    console.print()

    # Collect input based on field type
    if field_def.field_type == FieldType.MULTILINE:
        if field_def.key in ("locations", "characters", "items"):
            return _read_multiline_list(console)
        return _read_multiline(console)

    if field_def.field_type == FieldType.TEXT:
        try:
            line = console.input(" > ").strip()
        except EOFError:
            return None
        return line if line else None

    if field_def.field_type == FieldType.SELECT:
        return _prompt_select(console, field_def)

    if field_def.field_type == FieldType.MULTI_SELECT:
        return _prompt_multi_select(console, field_def)

    return None


def _prompt_select(console: Console, field_def) -> str | None:
    """Handle a single-select field (tone or world size)."""
    if field_def.key == "scale":
        # World size has special formatting with descriptions.
        for i, (label, desc) in enumerate(SCALE_OPTIONS, 1):
            console.print(f"  [cyan][{i}][/cyan] {label:10s} {desc}", style="dim")
        console.print()
        try:
            raw = console.input(" > ").strip()
        except EOFError:
            return None
        if not raw:
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(SCALE_VALUES):
                return SCALE_VALUES[idx]
        except ValueError:
            pass
        # Accept raw text like "small", "medium", "large"
        if raw.lower() in SCALE_VALUES:
            return raw.lower()
        return None

    # Generic select (tone)
    options = field_def.options
    for i, opt in enumerate(options, 1):
        console.print(f"  [cyan][{i}][/cyan] {opt}")
    console.print()
    try:
        raw = console.input(" > ").strip()
    except EOFError:
        return None
    if not raw:
        return None

    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            selected = options[idx]
            if "custom" in selected.lower() and field_def.allow_custom:
                console.print("  Type your custom tone:")
                try:
                    custom = console.input("  > ").strip()
                except EOFError:
                    return None
                return custom if custom else None
            return selected
    except ValueError:
        pass

    # Accept raw text input as custom
    return raw


def _prompt_multi_select(console: Console, field_def) -> list[str] | None:
    """Handle a multi-select field (genre tags)."""
    options = field_def.options
    for i, opt in enumerate(options, 1):
        console.print(f"  [cyan][{i}][/cyan] {opt}")
    console.print()
    try:
        raw = console.input(" > ").strip()
    except EOFError:
        return None
    if not raw:
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
    welcome.append("Fill in what inspires you, skip what doesn't. ")
    welcome.append("Only the first field is required.\n", style="dim")
    welcome.append("Tip: Press Enter on an empty line to skip optional fields.", style="dim italic")

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
) -> str | None:
    """Run the interactive prompt builder wizard.

    Args:
        console: Rich console for all I/O.
        initial_prompt: If provided, pre-fills the World Description field.
        preset: If provided, pre-fills fields from a preset dict.

    Returns:
        The assembled prompt string, or None if the user quit.
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
                    while result is None or (isinstance(result, str) and len(result.strip()) < 5):
                        result = _prompt_field(console, field_def)
                        if result is not None and isinstance(result, str) and len(result.strip()) < 5:
                            console.print(
                                " [red]Please enter at least 5 characters.[/red]"
                            )
                            result = None
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
            try:
                choice = console.input(" > ").strip().lower()
            except EOFError:
                return None

            if choice in ("g", "generate"):
                return assemble_prompt(values)

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
                    field_num = console.input(" Which field to edit? (1-10): ").strip()
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
                    console.print(" [red]Please enter a number between 1 and 10.[/red]")
                continue  # Show preview again

            console.print(" [red]Invalid choice. Use G, E, R, or Q.[/red]")

        # If we get here, user chose restart -- outer loop continues.
