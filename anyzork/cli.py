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
@click.argument("prompt")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None, help="Output path for the generated .zork file.")
@click.option("--seed", type=int, default=None, help="Seed for reproducible generation.")
@click.option("--provider", type=click.Choice(["claude", "openai", "gemini"], case_sensitive=False), default=None, help="LLM provider to use (overrides ANYZORK_PROVIDER).")
def generate(prompt: str, output: Path | None, seed: int | None, provider: str | None) -> None:
    """Generate a new .zork game from a natural-language prompt."""
    import re
    import sys

    from rich.status import Status

    from anyzork.config import Config, LLMProvider

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
        slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower()).strip("_")[:40]
        slug = slug or "game"
        output = cfg.games_dir / f"{slug}.zork"

    # Ensure parent directory exists.
    output.parent.mkdir(parents=True, exist_ok=True)

    # ── Display plan ──────────────────────────────────────────────────
    console.print(f"[dim]Prompt:[/dim]    {prompt}")
    console.print(f"[dim]Provider:[/dim]  {cfg.provider.value} ({cfg.active_model})")
    console.print(f"[dim]Output:[/dim]    {output}")
    if cfg.seed is not None:
        console.print(f"[dim]Seed:[/dim]      {cfg.seed}")
    console.print()

    # ── Run generation ────────────────────────────────────────────────
    try:
        from anyzork.generator.orchestrator import generate_game

        with Status("[bold green]Generating world...", console=console, spinner="dots"):
            result_path = generate_game(prompt=prompt, config=cfg, output_path=output)

        console.print()
        console.print(f"[bold green]Done![/bold green] Game saved to [cyan]{result_path}[/cyan]")
        console.print(f"[dim]Play it with:[/dim]  anyzork play {result_path}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Generation cancelled.[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"\n[red]Generation failed:[/red] {exc}")
        sys.exit(1)


def main() -> None:
    """Entry point wired in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()
