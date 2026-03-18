"""Foreign key reference sanitizer for LLM-generated game data.

LLMs generate entity IDs that reference entities from prior passes, but
those IDs sometimes don't match what's actually in the database.  This
module provides utilities to validate and sanitize FK references before
insertion, preventing ``FOREIGN KEY constraint failed`` errors without
disabling constraints.

Strategy:
  - Required FKs (e.g., npcs.room_id): if invalid, skip the entity and
    log a warning.
  - Optional FKs (e.g., npcs.blocked_exit_id, lore.item_id): if invalid,
    nullify the reference and log a warning.
"""

from __future__ import annotations

import logging
from typing import Any

from anyzork.db.schema import GameDB

logger = logging.getLogger(__name__)


def get_valid_ids(db: GameDB, table: str) -> set[str]:
    """Return the set of all primary-key IDs in the given table."""
    rows = db._fetchall(f"SELECT id FROM {table}")  # noqa: S608
    return {row["id"] for row in rows}


def sanitize_fk(
    entity: dict[str, Any],
    field: str,
    valid_ids: set[str],
    *,
    entity_type: str,
    entity_id: str,
    target_table: str,
    required: bool = False,
) -> bool:
    """Validate a single FK field on an entity dict.

    If the field value is ``None`` or empty string, it is treated as
    absent and no validation is performed.

    Args:
        entity: The mutable entity dict (modified in place for optional FKs).
        field: The field name to check (e.g., ``"room_id"``).
        valid_ids: Set of valid IDs in the target table.
        entity_type: Human-readable type for log messages (e.g., ``"NPC"``).
        entity_id: The entity's own ID for log messages.
        target_table: Target table name for log messages (e.g., ``"rooms"``).
        required: If ``True``, an invalid reference means the entity should
                  be skipped entirely (returns ``False``).  If ``False``,
                  the field is set to ``None``.

    Returns:
        ``True`` if the entity is safe to insert (FK is valid or was
        nullified).  ``False`` if the entity should be skipped (required
        FK was invalid).
    """
    value = entity.get(field)

    # Absent / null values are fine for both required and optional FKs
    # at the sanitizer level -- required-field presence is validated
    # elsewhere by the pass's own validation logic.
    if value is None or value == "":
        return True

    if value not in valid_ids:
        if required:
            logger.warning(
                "Skipping %s '%s': %s='%s' not found in %s (valid: %s)",
                entity_type,
                entity_id,
                field,
                value,
                target_table,
                sorted(valid_ids)[:10],  # Show up to 10 to avoid log spam
            )
            return False
        else:
            logger.warning(
                "Nullifying %s '%s'.%s='%s': not found in %s",
                entity_type,
                entity_id,
                field,
                value,
                target_table,
            )
            entity[field] = None
            return True

    return True
