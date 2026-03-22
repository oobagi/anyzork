"""Health checks for the local anyzork environment."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from anyzork.config import Config


@dataclass(frozen=True)
class HealthIssue:
    """A single health check finding."""

    kind: str  # "orphan_save" | "empty_save_dir"
    path: Path
    detail: str


def _library_game_ids(cfg: Config) -> set[str]:
    """Return the set of game slugs (stems) present in the library."""
    if not cfg.games_dir.exists():
        return set()
    return {p.stem for p in cfg.games_dir.glob("*.zork")}


def run_health_checks(cfg: Config) -> list[HealthIssue]:
    """Scan the saves directory and return a list of issues."""
    issues: list[HealthIssue] = []

    if not cfg.saves_dir.exists():
        return issues

    library_slugs = _library_game_ids(cfg)

    for save_dir in sorted(cfg.saves_dir.iterdir()):
        if not save_dir.is_dir():
            continue

        zork_files = list(save_dir.glob("*.zork"))

        # Check for empty save directories
        if not zork_files:
            issues.append(
                HealthIssue(
                    kind="empty_save_dir",
                    path=save_dir,
                    detail="No .zork save files in directory",
                )
            )
            continue

        # Check for orphaned saves — the save dir name is the source game slug
        source_slug = save_dir.name
        if source_slug not in library_slugs:
            issues.append(
                HealthIssue(
                    kind="orphan_save",
                    path=save_dir,
                    detail=f"No library game matches '{source_slug}'",
                )
            )

    return issues


def fix_issues(issues: list[HealthIssue], cfg: Config) -> list[str]:
    """Delete directories for the given issues. Returns descriptions of what was cleaned."""
    cleaned: list[str] = []

    for issue in issues:
        if (
            issue.kind in ("orphan_save", "empty_save_dir")
            and issue.path.exists()
            and issue.path.is_dir()
        ):
            shutil.rmtree(issue.path)
            cleaned.append(f"{issue.kind}: {issue.path.name}")

    return cleaned
