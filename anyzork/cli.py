"""AnyZork CLI — click entry point."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from anyzork import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="anyzork")
def cli() -> None:
    """AnyZork -- AI-powered text adventure generator."""


@cli.command()
@click.argument("zork_file", type=click.Path(exists=True, path_type=Path))
def play(zork_file: Path) -> None:
    """Play an existing .zork game file."""
    from anyzork.db.schema import GameDB
    from anyzork.engine.game import GameEngine

    db = GameDB(zork_file)
    try:
        engine = GameEngine(db)
        engine.start()
    except KeyboardInterrupt:
        console.print("\nFarewell, adventurer.", style="dim italic")
    finally:
        db.close()


@cli.command()
@click.argument("prompt", required=False, default=None)
@click.option("--guided", is_flag=True, help="Launch the interactive prompt builder wizard.")
@click.option(
    "--preset",
    type=str,
    default=None,
    help="Load a genre preset (e.g., fantasy-dungeon, zombie-survival).",
)
@click.option("--list-presets", is_flag=True, help="List available presets and exit.")
@click.option(
    "--no-edit",
    is_flag=True,
    help="With --preset, skip the wizard and generate immediately.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path for the generated .zork file.",
)
@click.option(
    "--seed",
    type=int,
    default=None,
    help="Seed for reproducible generation.",
)
@click.option(
    "--provider",
    type=click.Choice(["claude", "openai", "gemini"], case_sensitive=False),
    default=None,
    help="LLM provider to use (overrides ANYZORK_PROVIDER).",
)
def generate(
    prompt: str | None,
    guided: bool,
    preset: str | None,
    list_presets: bool,
    no_edit: bool,
    output: Path | None,
    seed: int | None,
    provider: str | None,
) -> None:
    """Generate a new .zork game from a natural-language prompt.

    \b
    Usage modes:
      anyzork generate "prompt"          Freeform generation (existing behavior)
      anyzork generate                   Launch the interactive wizard
      anyzork generate --guided          Launch the wizard explicitly
      anyzork generate --preset zombie-survival   Load a preset, preview, confirm
      anyzork generate --list-presets    List available presets
    """
    import re
    import sys

    from anyzork.config import Config, LLMProvider

    # ── List presets and exit ──────────────────────────────────────────
    if list_presets:
        from anyzork.wizard.presets import list_presets as _list_presets

        _list_presets(console)
        return

    # ── Resolve prompt: freeform, wizard, or preset ────────────────────
    resolved_prompt = _resolve_prompt(prompt, guided, preset, no_edit, console)
    if resolved_prompt is None:
        # User quit the wizard or Ctrl+C.
        sys.exit(0)

    # ── Build configuration from environment ──────────────────────────
    overrides: dict[str, object] = {}
    if provider:
        overrides["provider"] = LLMProvider(provider.lower())
    if seed is not None:
        overrides["seed"] = seed

    try:
        cfg = Config(**overrides)  # type: ignore[arg-type]
    except Exception as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        sys.exit(1)

    # ── Validate API key ──────────────────────────────────────────────
    api_key = cfg.get_api_key()
    if not api_key:
        console.print(
            f"[red]No API key found for provider '{cfg.provider.value}'.[/red]\n"
            f"Set one of: ANYZORK_{cfg.provider.value.upper()}_API_KEY "
            f"or the provider's standard env var."
        )
        sys.exit(1)

    # ── Determine output path ─────────────────────────────────────────
    if output is None:
        # Derive a filename from the prompt (slugified, truncated).
        slug = re.sub(r"[^a-z0-9]+", "_", resolved_prompt.lower()).strip("_")[:40]
        slug = slug or "game"
        output = cfg.games_dir / f"{slug}.zork"

    # Ensure parent directory exists.
    output.parent.mkdir(parents=True, exist_ok=True)

    # ── Display plan ──────────────────────────────────────────────────
    # Show a truncated preview for long prompts (wizard-generated).
    preview = resolved_prompt
    if len(preview) > 200:
        preview = preview[:200] + "..."
    console.print(f"[dim]Prompt:[/dim]    {preview}")
    console.print(f"[dim]Provider:[/dim]  {cfg.provider.value} ({cfg.active_model})")
    console.print(f"[dim]Output:[/dim]    {output}")
    if cfg.seed is not None:
        console.print(f"[dim]Seed:[/dim]      {cfg.seed}")
    console.print()

    # ── Run generation ────────────────────────────────────────────────
    try:
        from rich.status import Status

        from anyzork.generator.orchestrator import generate_game

        with Status("[bold green]Generating world...", console=console, spinner="dots"):
            result_path = generate_game(
                prompt=resolved_prompt, config=cfg, output_path=output
            )

        console.print()
        console.print(f"[bold green]Done![/bold green] Game saved to [cyan]{result_path}[/cyan]")
        console.print(f"[dim]Play it with:[/dim]  anyzork play {result_path}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Generation cancelled.[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"\n[red]Generation failed:[/red] {exc}")
        sys.exit(1)


def _resolve_prompt(
    prompt: str | None,
    guided: bool,
    preset_name: str | None,
    no_edit: bool,
    console: Console,
) -> str | None:
    """Determine the final prompt string based on CLI arguments.

    Returns the prompt string, or None if the user quit.
    """
    import sys

    from anyzork.wizard import run_wizard
    from anyzork.wizard.assembler import assemble_prompt
    from anyzork.wizard.presets import load_preset

    # Case 1: Preset mode.
    if preset_name is not None:
        preset_fields = load_preset(preset_name)
        if preset_fields is None:
            console.print(f"[red]Unknown preset: '{preset_name}'[/red]")
            console.print("[dim]Use --list-presets to see available presets.[/dim]")
            sys.exit(1)

        if no_edit:
            # Skip wizard, generate immediately from preset values.
            return assemble_prompt(preset_fields)

        # Launch wizard with preset values pre-filled.
        return run_wizard(console, preset=preset_fields)

    # Case 2: Freeform prompt provided without --guided.
    if prompt is not None and not guided:
        return prompt

    # Case 3: Freeform prompt provided WITH --guided — seed the wizard.
    if prompt is not None and guided:
        return run_wizard(console, initial_prompt=prompt)

    # Case 4: No prompt, --guided flag or no arguments at all — launch wizard.
    # In non-interactive environments, require a prompt argument.
    if not sys.stdin.isatty():
        console.print(
            "[red]No prompt provided and stdin is not a terminal.[/red]\n"
            "[dim]Provide a prompt argument or use --preset with --no-edit.[/dim]"
        )
        sys.exit(1)

    return run_wizard(console)


def main() -> None:
    """Entry point wired in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()
