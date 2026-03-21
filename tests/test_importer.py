from __future__ import annotations

from pathlib import Path

import pytest

from anyzork.db.schema import GameDB
from anyzork.importer import ImportSpecError, compile_import_spec, current_prompt_system_version
from anyzork.versioning import APP_VERSION, RUNTIME_COMPAT_VERSION


def test_compile_import_spec_writes_versioned_metadata(
    tmp_path: Path, minimal_import_spec: dict
) -> None:
    output_path = tmp_path / "compiled_game.zork"

    compiled_path, warnings = compile_import_spec(minimal_import_spec, output_path)

    assert compiled_path == output_path.resolve()
    assert warnings == []

    with GameDB(compiled_path) as db:
        meta = db.get_all_meta() or {}
        assert meta["title"] == "Fixture Game"
        assert meta["version"] == RUNTIME_COMPAT_VERSION
        assert meta["app_version"] == APP_VERSION
        assert meta["prompt_system_version"] == current_prompt_system_version()
        assert meta["is_template"] == 1


def test_compile_import_spec_rejects_invalid_exit_direction(
    tmp_path: Path, minimal_import_spec: dict
) -> None:
    bad_spec = {
        **minimal_import_spec,
        "exits": [
            {
                "id": "foyer_study",
                "from_room_id": "foyer",
                "to_room_id": "study",
                "direction": "out",
            }
        ],
    }

    with pytest.raises(ImportSpecError, match="Unsupported exit direction"):
        compile_import_spec(bad_spec, tmp_path / "bad.zork")
