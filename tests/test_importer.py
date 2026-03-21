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


def test_compile_import_spec_writes_combination_lock(
    tmp_path: Path, minimal_import_spec: dict
) -> None:
    """Combination lock data round-trips through compile into the DB."""
    combo_spec = {
        **minimal_import_spec,
        "exits": [
            {
                "id": "foyer_study",
                "from_room_id": "foyer",
                "to_room_id": "study",
                "direction": "north",
                "is_locked": True,
            },
            {
                "id": "study_foyer",
                "from_room_id": "study",
                "to_room_id": "foyer",
                "direction": "south",
            },
        ],
        "locks": [
            {
                "id": "study_combo",
                "lock_type": "combination",
                "target_exit_id": "foyer_study",
                "combination": "813",
                "locked_message": "A dial blocks the way.",
                "unlock_message": "Click. The lock opens.",
            }
        ],
    }

    output_path = tmp_path / "combo_game.zork"
    compiled_path, warnings = compile_import_spec(combo_spec, output_path)

    with GameDB(compiled_path) as db:
        locks = db.get_locks_in_room("foyer")
        assert len(locks) == 1
        lock = locks[0]
        assert lock["lock_type"] == "combination"
        assert lock["combination"] == "813"
        assert lock["locked_message"] == "A dial blocks the way."


def test_compile_import_spec_writes_code_locked_container(
    tmp_path: Path, minimal_import_spec: dict
) -> None:
    """Container with combination field round-trips through compile into the DB."""
    container_spec = {
        **minimal_import_spec,
        "items": [
            {
                "id": "lockbox",
                "name": "Lockbox",
                "description": "A small metal box.",
                "examine_description": "It has a dial.",
                "room_id": "foyer",
                "is_takeable": False,
                "is_container": True,
                "is_locked": True,
                "combination": "417",
                "lock_message": "The lockbox is locked.",
                "open_message": "Click. Open.",
            }
        ],
    }

    output_path = tmp_path / "container_combo_game.zork"
    compiled_path, warnings = compile_import_spec(container_spec, output_path)

    with GameDB(compiled_path) as db:
        item = db.find_item_by_name("Lockbox", "room", "foyer")
        assert item is not None
        assert item["combination"] == "417"
        assert item["is_locked"] == 1
        assert item["is_container"] == 1
