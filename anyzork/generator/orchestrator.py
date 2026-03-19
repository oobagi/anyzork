"""Multi-pass generation orchestrator.

Coordinates the nine-pass pipeline that turns a user prompt into a
populated ``.zork`` SQLite database.  Each pass is a separate module
under ``anyzork.generator.passes``; the orchestrator sequences them,
assembles context, handles retries, and reports progress.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from anyzork.db.schema import GameDB
from anyzork.generator.providers import create_provider
from anyzork.generator.providers.base import GenerationContext, ProviderError
from anyzork.generator.validator import validate_game

if TYPE_CHECKING:
    from anyzork.config import Config
    from anyzork.generator.providers.base import BaseProvider

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Pass registry — ordered list of (name, module_path) tuples.
# Each module must export:
#   run_pass(db: GameDB, provider: BaseProvider, context: dict) -> dict
# ---------------------------------------------------------------------------

_PASSES: list[tuple[str, str]] = [
    ("concept", "anyzork.generator.passes.concept"),
    ("rooms", "anyzork.generator.passes.rooms"),
    ("locks", "anyzork.generator.passes.locks"),
    ("items", "anyzork.generator.passes.items"),
    ("npcs", "anyzork.generator.passes.npcs"),
    ("interactions", "anyzork.generator.passes.interactions"),
    ("puzzles", "anyzork.generator.passes.puzzles"),
    ("commands", "anyzork.generator.passes.commands"),
    ("quests", "anyzork.generator.passes.quests"),
    ("triggers", "anyzork.generator.passes.triggers"),
]


def _import_pass(module_path: str):
    """Dynamically import a pass module and return its ``run_pass`` function."""
    import importlib

    mod = importlib.import_module(module_path)
    fn = getattr(mod, "run_pass", None)
    if fn is None:
        raise ImportError(f"{module_path} does not export a 'run_pass' function")
    return fn


def _build_context(pass_name: str, results: dict[str, dict]) -> dict:
    """Assemble the context dict a pass needs based on its position.

    Each pass receives only the data from earlier passes that it depends
    on, as specified in the generation pipeline design doc.
    """
    context: dict = {}

    deps: dict[str, list[str]] = {
        "concept": [],
        "rooms": ["concept"],
        "locks": ["concept", "rooms"],
        "items": ["concept", "rooms", "locks"],
        "npcs": ["concept", "rooms", "items", "locks"],
        "interactions": ["concept", "rooms", "items", "npcs"],
        "puzzles": ["concept", "rooms", "items", "npcs", "locks"],
        "commands": ["concept", "rooms", "locks", "items", "npcs", "puzzles", "interactions"],
        "quests": ["concept", "rooms", "locks", "items", "npcs", "puzzles", "commands"],
        "triggers": ["concept", "rooms", "locks", "items", "npcs", "puzzles", "commands", "quests"],
    }

    for dep in deps.get(pass_name, []):
        if dep in results:
            context[dep] = results[dep]
            # Merge pass result keys into context so downstream passes
            # can access e.g. context["rooms"] (the list) directly,
            # rather than context["rooms"]["rooms"] (double-nested).
            if isinstance(results[dep], dict):
                context.update(results[dep])

    return context


def _run_validation(db: GameDB) -> list[str]:
    """Pass 9 — deterministic cross-referential integrity checks.

    Delegates to the real ``validate_game`` in ``anyzork.generator.validator``
    and converts the structured ``ValidationError`` results into plain
    strings for display.

    Returns a list of error/warning strings (empty means the world is valid).
    """
    results = validate_game(db)
    return [str(r) for r in results]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_game(
    prompt: str,
    config: Config,
    output_path: Path,
    *,
    realism: str = "medium",
) -> Path:
    """Run the full generation pipeline and produce a ``.zork`` file.

    Args:
        prompt: The user's natural-language world description.
        config: Resolved AnyZork configuration.
        output_path: Where to write the ``.zork`` file.

    Returns:
        The resolved ``Path`` to the generated ``.zork`` file.

    Raises:
        ProviderError: If the LLM provider cannot be created or fails
            unrecoverably during generation.
        RuntimeError: If a pass exhausts all retries.
    """
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove any leftover file from a previous failed run.
    if output_path.exists():
        output_path.unlink()

    # --- Seed resolution ---
    # If no seed was provided, generate a random one so every run is
    # reproducible after the fact (the seed is stored in metadata).
    seed = config.seed if config.seed is not None else random.randint(0, 2**31 - 1)
    console.print(f"[dim]Seed:[/] {seed}")

    # --- Provider setup ---
    provider = create_provider(config)
    console.print(
        f"[bold green]Provider:[/] {config.provider.value} "
        f"(model: {config.active_model})"
    )

    # --- Database setup ---
    db = GameDB(output_path)
    db.initialize(
        game_name="Generating...",
        author="AnyZork",
        prompt=prompt,
        seed=str(seed),
    )

    # --- Multi-pass generation ---
    results: dict[str, dict] = {}
    results["_prompt"] = {"prompt": prompt}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        total_passes = len(_PASSES) + 1  # +1 for validation
        main_task = progress.add_task("Generating world...", total=total_passes)

        for pass_name, module_path in _PASSES:
            progress.update(main_task, description=f"Pass: {pass_name}")

            run_pass = _import_pass(module_path)
            context = _build_context(pass_name, results)
            context["prompt"] = prompt
            context["seed"] = seed
            context["realism"] = realism

            last_error: Exception | None = None
            for attempt in range(1, config.max_retries + 1):
                try:
                    result = run_pass(db, provider, context)
                    results[pass_name] = result
                    logger.info("Pass '%s' succeeded on attempt %d", pass_name, attempt)
                    last_error = None
                    break
                except (ProviderError, ValueError, KeyError) as exc:
                    last_error = exc
                    logger.warning(
                        "Pass '%s' failed (attempt %d/%d): %s",
                        pass_name,
                        attempt,
                        config.max_retries,
                        exc,
                    )
                    if attempt < config.max_retries:
                        # Inject the error into context so the next attempt
                        # can include it in the prompt for self-correction.
                        context["_last_error"] = str(exc)

            if last_error is not None:
                db.close()
                raise RuntimeError(
                    f"Pass '{pass_name}' failed after {config.max_retries} attempts: {last_error}"
                ) from last_error

            progress.advance(main_task)

        # --- Pass 9: Validation (deterministic, no LLM) ---
        progress.update(main_task, description="Pass: validation")
        validation_errors = _run_validation(db)
        if validation_errors:
            for err in validation_errors:
                console.print(f"  [yellow]Warning:[/] {err}")
            logger.warning(
                "Validation found %d issue(s) — game may have inconsistencies",
                len(validation_errors),
            )
        else:
            console.print("  [green]Validation passed — world is consistent.[/]")
        progress.advance(main_task)

    # --- Finalize ---
    meta = db.get_all_meta()
    title = meta["title"] if meta else "Untitled"
    room_count = len(db.get_all_rooms())

    db.close()

    console.print(
        f"\n[bold green]Done![/] Generated [bold]{title}[/] — "
        f"{room_count} rooms. Saved to [cyan]{output_path}[/]"
    )

    return output_path
