from __future__ import annotations

from pathlib import Path

from anyzork.services.authoring import build_authoring_bundle
from anyzork.services.importing import import_zorkscript


def test_build_authoring_bundle_normalizes_multivalue_fields() -> None:
    bundle = build_authoring_bundle(
        {
            "world_description": "A flooded observatory haunted by tidal ghosts.",
            "tone": "mysterious, melancholic",
            "genre_tags": "exploration\npuzzle",
            "locations": "Observatory dome\nSea tunnel",
            "realism": "medium",
        }
    )

    assert bundle.fields["tone"] == ["mysterious", "melancholic"]
    assert bundle.fields["genre_tags"] == ["exploration", "puzzle"]
    assert bundle.fields["locations"] == ["Observatory dome", "Sea tunnel"]
    assert "You are authoring a complete, playable text adventure in ZorkScript format." in (
        bundle.authoring_prompt
    )


def test_import_zorkscript_defaults_output_into_games_dir(
    tmp_path: Path, minimal_zorkscript: str
) -> None:
    result = import_zorkscript(minimal_zorkscript, games_dir=tmp_path)

    assert result.output_path.parent == tmp_path
    assert result.output_path.exists()
