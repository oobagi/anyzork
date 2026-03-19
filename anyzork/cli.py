"""AnyZork CLI — click entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from anyzork import __version__
from anyzork.config import (
    _DEFAULT_MODELS,
    _PROVIDER_TO_KEY_TYPE,
    CONFIG_FILE,
    Config,
    LLMProvider,
    load_config_file,
    save_config_file,
)

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="anyzork")
def cli() -> None:
    """AnyZork -- AI-powered text adventure generator."""


@cli.command()
@click.argument("zork_file", type=click.Path(exists=True, path_type=Path))
@click.option("--narrator", is_flag=True, help="Enable narrator mode (requires API key).")
@click.option(
    "--provider",
    type=click.Choice(["claude", "openai", "gemini"], case_sensitive=False),
    default=None,
    help="LLM provider for narrator mode (overrides ANYZORK_PROVIDER).",
)
@click.option("--model", type=str, default=None, help="Model for narrator mode.")
def play(zork_file: Path, narrator: bool, provider: str | None, model: str | None) -> None:
    """Play an existing .zork game file."""
    from anyzork.db.schema import GameDB
    from anyzork.engine.game import GameEngine

    # Also check the ANYZORK_NARRATOR env var / config.
    narrator_enabled = narrator
    if not narrator_enabled:
        try:
            cfg = Config()
            narrator_enabled = cfg.narrator_enabled
        except Exception:
            pass

    db = GameDB(zork_file)
    try:
        engine = GameEngine(
            db,
            narrator_enabled=narrator_enabled,
            narrator_provider=provider,
            narrator_model=model,
        )
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
@click.option(
    "--realism",
    type=click.Choice(["low", "medium", "high"]),
    default="medium",
    help="Realism level for item dynamics.",
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
    realism: str,
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
    console.print(f"[dim]Seed:[/dim]      {cfg.seed if cfg.seed is not None else '(auto)'}")
    console.print(f"[dim]Realism:[/dim]   {realism}")
    console.print()

    # ── Run generation ────────────────────────────────────────────────
    try:
        from rich.status import Status

        from anyzork.generator.orchestrator import generate_game

        with Status("[bold green]Generating world...", console=console, spinner="dots"):
            result_path = generate_game(
                prompt=resolved_prompt,
                config=cfg,
                output_path=output,
                realism=realism,
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


@cli.command()
def init() -> None:
    """Interactive setup wizard — configure your LLM provider and API key."""

    from rich.panel import Panel

    # ── Welcome ──────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            "[bold]Let's get you set up.[/bold]",
            title="AnyZork Setup",
            border_style="bright_cyan",
            padding=(1, 2),
        )
    )
    console.print()

    # ── Provider selection ───────────────────────────────────────────
    providers = [
        (LLMProvider.CLAUDE, "Claude (Anthropic)", "recommended"),
        (LLMProvider.OPENAI, "OpenAI (GPT-4o)", ""),
        (LLMProvider.GEMINI, "Gemini (Google)", ""),
    ]

    console.print("[bold]Choose your LLM provider:[/bold]")
    for i, (_, label, note) in enumerate(providers, 1):
        suffix = f" -- {note}" if note else ""
        console.print(f"  [cyan][{i}][/cyan] {label}{suffix}")
    console.print()

    while True:
        try:
            choice_str = console.input("[bold]> [/bold]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Setup cancelled.[/dim]")
            sys.exit(0)

        if choice_str in ("1", "2", "3"):
            break
        console.print("[red]Please enter 1, 2, or 3.[/red]")

    chosen_provider, chosen_label, _ = providers[int(choice_str) - 1]
    console.print()

    # ── API key input ────────────────────────────────────────────────
    key_urls: dict[LLMProvider, str] = {
        LLMProvider.CLAUDE: "https://console.anthropic.com/settings/keys",
        LLMProvider.OPENAI: "https://platform.openai.com/api-keys",
        LLMProvider.GEMINI: "https://aistudio.google.com/apikey",
    }

    url = key_urls[chosen_provider]
    console.print(f"[bold]Enter your {chosen_label.split(' (')[0]} API key:[/bold]")
    console.print(f"  [dim](Get one at {url})[/dim]")

    while True:
        try:
            api_key = console.input("[bold]> [/bold]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Setup cancelled.[/dim]")
            sys.exit(0)

        if api_key:
            break
        console.print("[red]API key cannot be empty.[/red]")

    console.print()

    # ── Test connection ──────────────────────────────────────────────
    _test_provider_connection(chosen_provider, api_key, console)

    # ── Model selection ──────────────────────────────────────────────
    default_model = _DEFAULT_MODELS[chosen_provider]
    console.print(f"[bold]Model[/bold] (press Enter for default: [cyan]{default_model}[/cyan]):")

    try:
        model_input = console.input("[bold]> [/bold]").strip()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Setup cancelled.[/dim]")
        sys.exit(0)

    chosen_model = model_input if model_input else None
    console.print()

    # ── Save ─────────────────────────────────────────────────────────
    key_type = _PROVIDER_TO_KEY_TYPE[chosen_provider]
    save_config_file(
        provider=chosen_provider.value,
        model=chosen_model,
        api_key=api_key,
        key_type=key_type,
    )

    console.print(f"[green]Saved to {CONFIG_FILE}[/green]")
    console.print()
    console.print("[bold]You're ready![/bold] Try:")
    console.print('  [cyan]anyzork generate "A haunted mansion with a mystery"[/cyan]')
    console.print()


def _test_provider_connection(
    provider: LLMProvider,
    api_key: str,
    console: Console,
) -> None:
    """Try a minimal API call to verify the key works."""
    from rich.status import Status

    with Status("[bold]Testing connection...", console=console, spinner="dots"):
        try:
            if provider == LLMProvider.CLAUDE:
                import anthropic

                client = anthropic.Anthropic(api_key=api_key, timeout=10.0)
                client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=16,
                    messages=[{"role": "user", "content": "Hi"}],
                )

            elif provider == LLMProvider.OPENAI:
                import openai

                client = openai.OpenAI(api_key=api_key, timeout=10.0)
                client.chat.completions.create(
                    model="gpt-4o",
                    max_tokens=16,
                    messages=[{"role": "user", "content": "Hi"}],
                )

            elif provider == LLMProvider.GEMINI:
                from google import genai
                from google.genai import types as genai_types

                client = genai.Client(api_key=api_key)
                client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents="Hi",
                    config=genai_types.GenerateContentConfig(max_output_tokens=16),
                )

        except KeyboardInterrupt:
            console.print("\n[dim]Setup cancelled.[/dim]")
            sys.exit(0)
        except Exception as exc:
            console.print(f"[red]Connection failed:[/red] {exc}")
            console.print("[dim]The API key may be invalid, or the service may be down.[/dim]")
            console.print("[dim]Config will still be saved -- you can fix the key later.[/dim]")
            console.print()
            return

    console.print("[green]Testing connection... Connected![/green]")
    console.print()


@cli.command("config")
def show_config() -> None:
    """Show current AnyZork configuration and where values come from."""

    try:
        cfg = Config()
    except Exception as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        return

    api_key = cfg.get_api_key()
    if api_key and len(api_key) > 8:
        masked_key = api_key[:8] + "****"
    elif api_key:
        masked_key = "****"
    else:
        masked_key = "[red]not set[/red]"

    # Determine source of key.
    key_source = _get_key_source(cfg)

    provider_source = cfg.get_value_source("provider")
    model_source = cfg.get_value_source("model")
    display_model = cfg.active_model or "not set"
    if cfg.model is None:
        display_model += " (default)"

    console.print()
    console.print(f"[bold]Provider:[/bold]    {cfg.provider.value}  [dim]({provider_source})[/dim]")
    console.print(f"[bold]Model:[/bold]       {display_model}  [dim]({model_source})[/dim]")
    console.print(f"[bold]API Key:[/bold]     {masked_key}  [dim]({key_source})[/dim]")
    console.print(f"[bold]Config file:[/bold] {CONFIG_FILE}")
    console.print(f"[bold]Games dir:[/bold]   {cfg.games_dir}")
    console.print()


def _get_key_source(cfg: Config) -> str:
    """Determine where the active API key is coming from."""
    import os

    # Check ANYZORK_-prefixed env var.
    key_type = _PROVIDER_TO_KEY_TYPE.get(cfg.provider, "")
    anyzork_env = f"ANYZORK_{key_type.upper()}_API_KEY"
    if os.environ.get(anyzork_env):
        return "env var"

    # Check pydantic field (may have been set from .env file).
    field_map = {
        "anthropic": cfg.anthropic_api_key,
        "openai": cfg.openai_api_key,
        "google": cfg.google_api_key,
    }
    if field_map.get(key_type):
        # Could be from .env or env var -- check standard env var too.
        standard_env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        std_env = standard_env_map.get(key_type, "")
        if os.environ.get(std_env):
            return "env var"
        return "env var / .env"

    # Check config file.
    file_values = load_config_file()
    config_field = f"{key_type}_api_key"
    if file_values.get(config_field):
        return "config file"

    return "not found"


@cli.command("list")
def list_games() -> None:
    """List saved games in the default game directory."""
    from anyzork.config import Config
    from anyzork.db.schema import GameDB

    cfg = Config()
    games_dir = cfg.games_dir

    if not games_dir.exists():
        console.print(f"[dim]No games directory found at {games_dir}[/dim]")
        console.print("[dim]Generate your first game with:[/dim]  anyzork generate")
        return

    zork_files = sorted(games_dir.glob("*.zork"))
    if not zork_files:
        console.print(f"[dim]No .zork files found in {games_dir}[/dim]")
        console.print("[dim]Generate your first game with:[/dim]  anyzork generate")
        return

    from rich.table import Table

    from anyzork import __version__ as engine_version

    table = Table(title="Saved Games", show_lines=False)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Version", style="dim")
    table.add_column("Created", style="dim")
    table.add_column("Max Score", justify="right", style="green")

    for zork_file in zork_files:
        try:
            db = GameDB(zork_file)
            meta = db.get_all_meta()
            db.close()

            if meta:
                title = meta.get("title", "Untitled")
                save_ver = meta.get("version", "?")
                if save_ver != engine_version:
                    version_str = f"[yellow]v{save_ver}[/yellow]"
                else:
                    version_str = f"v{save_ver}"
                created = meta.get("created_at", "")
                if created and len(created) >= 10:
                    created = created[:10]
                max_score = str(meta.get("max_score", 0))
            else:
                title = "Untitled"
                version_str = "?"
                created = ""
                max_score = "0"
        except Exception:
            title = "(error reading file)"
            version_str = "?"
            created = ""
            max_score = "-"

        table.add_row(zork_file.name, title, version_str, created, max_score)

    console.print(table)


def main() -> None:
    """Entry point wired in pyproject.toml."""
    cli()


if __name__ == "__main__":
    main()
