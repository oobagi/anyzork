"""Shared constants and error type for the import-spec compiler."""

from __future__ import annotations


class ImportSpecError(ValueError):
    """Raised when an import spec cannot be parsed or compiled."""


IMPORT_SPEC_FORMAT = "anyzork.import.v1"
ALLOWED_EXIT_DIRECTIONS = ("north", "south", "east", "west", "up", "down")
PUBLIC_INTERACTION_TYPES = (
    "read_item",
    "show_item_to_npc",
    "give_item_to_npc",
    "search_room",
    "search_container",
    "travel_action",
)
