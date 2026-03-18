"""Multi-pass generation orchestrator.

Coordinates the nine-pass pipeline that turns a user prompt into a
populated ``.zork`` SQLite database.  Each pass is a separate module
under ``anyzork.generator.passes``; the orchestrator sequences them,
assembles context, handles retries, and reports progress.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from anyzork.db.schema import GameDB
from anyzork.generator.providers import create_provider
from anyzork.generator.providers.base import GenerationContext, ProviderError

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
    ("puzzles", "anyzork.generator.passes.puzzles"),
    ("commands", "anyzork.generator.passes.commands"),
    ("quests", "anyzork.generator.passes.quests"),
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
        "puzzles": ["concept", "rooms", "items", "npcs", "locks"],
        "commands": ["concept", "rooms", "locks", "items", "npcs", "puzzles"],
        "quests": ["concept", "rooms", "locks", "items", "npcs", "puzzles", "commands"],
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

    Returns a list of error strings (empty means the world is valid).
    """
    errors: list[str] = []

    # --- Spatial integrity ---
    rooms = db.get_all_rooms()
    room_ids = {r["id"] for r in rooms}

    if not rooms:
        errors.append("No rooms in the database.")
        return errors

    start_rooms = [r for r in rooms if r.get("is_start")]
    if not start_rooms:
        errors.append("No room is marked as the start room (is_start = 1).")

    # Check all exits reference valid rooms.
    for room in rooms:
        for exit_row in db.get_all_exits_from(room["id"]):
            if exit_row["to_room_id"] not in room_ids:
                errors.append(
                    f"Exit from {room['id']} direction={exit_row['direction']} "
                    f"targets non-existent room {exit_row['to_room_id']!r}."
                )

    # --- Reachability (BFS from start room) ---
    if start_rooms:
        visited: set[str] = set()
        queue = [start_rooms[0]["id"]]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for exit_row in db.get_all_exits_from(current):
                if exit_row["to_room_id"] not in visited:
                    queue.append(exit_row["to_room_id"])
        unreachable = room_ids - visited
        if unreachable:
            errors.append(f"Unreachable rooms (not connected to start): {sorted(unreachable)}")

    # --- Item consistency ---
    all_item_rows = db._fetchall("SELECT * FROM items")
    container_item_ids = {
        row["id"] for row in all_item_rows if row.get("is_container")
    }
    for item in all_item_rows:
        if item["room_id"] and item["room_id"] not in room_ids:
            errors.append(
                f"Item {item['id']!r} references non-existent room {item['room_id']!r}."
            )
        # Container integrity checks
        cid = item.get("container_id")
        if cid is not None:
            if cid not in container_item_ids:
                errors.append(
                    f"Item {item['id']!r} has container_id={cid!r} "
                    f"which is not a valid container."
                )
            if item.get("is_container"):
                errors.append(
                    f"Container {item['id']!r} is nested inside another container "
                    f"(container_id={cid!r}). Nesting is not supported."
                )
            if item["room_id"] is not None:
                errors.append(
                    f"Item {item['id']!r} has both room_id and container_id set."
                )
        if item.get("is_container") and item.get("is_locked") and not item.get("lock_message"):
            errors.append(
                f"Locked container {item['id']!r} is missing lock_message."
            )

    # --- NPC validity ---
    for npc in db._fetchall("SELECT * FROM npcs"):
        if npc["room_id"] not in room_ids:
            errors.append(
                f"NPC {npc['id']!r} is in non-existent room {npc['room_id']!r}."
            )

    # --- Command reference checks ---
    all_items = {row["id"] for row in db._fetchall("SELECT id FROM items")}
    all_npcs = {row["id"] for row in db._fetchall("SELECT id FROM npcs")}
    for cmd in db.get_all_commands():
        if cmd["context_room_id"] and cmd["context_room_id"] not in room_ids:
            errors.append(
                f"Command {cmd['id']!r} references non-existent room "
                f"{cmd['context_room_id']!r}."
            )

    # --- Quest coverage ---
    quest_rows = db._fetchall("SELECT * FROM quests")
    main_quests = [q for q in quest_rows if q["quest_type"] == "main"]
    if not main_quests:
        errors.append("No main quest found. Every game must have exactly one main quest.")
    elif len(main_quests) > 1:
        errors.append(
            f"Multiple main quests found: {[q['id'] for q in main_quests]}. "
            f"Exactly one is required."
        )

    all_flags = {r["id"] for r in db._fetchall("SELECT id FROM flags")}
    for quest in quest_rows:
        if quest["discovery_flag"] and quest["discovery_flag"] not in all_flags:
            errors.append(
                f"Quest {quest['id']!r} discovery_flag {quest['discovery_flag']!r} "
                f"does not exist in flags table."
            )
        if quest["completion_flag"] not in all_flags:
            errors.append(
                f"Quest {quest['id']!r} completion_flag {quest['completion_flag']!r} "
                f"does not exist in flags table."
            )
        objectives = db._fetchall(
            "SELECT * FROM quest_objectives WHERE quest_id = ?", (quest["id"],)
        )
        if not any(not o["is_optional"] for o in objectives):
            errors.append(
                f"Quest {quest['id']!r} has no required (non-optional) objectives."
            )
        for obj in objectives:
            if obj["completion_flag"] not in all_flags:
                errors.append(
                    f"Quest objective {obj['id']!r} completion_flag "
                    f"{obj['completion_flag']!r} does not exist in flags table."
                )

    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_game(prompt: str, config: Config, output_path: Path) -> Path:
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
        seed=str(config.seed) if config.seed is not None else None,
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
