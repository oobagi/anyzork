"""Single-prompt game generation with file-header splitting."""

from __future__ import annotations

from typing import Any

from anyzork.importer.prompt import (
    _REALISM_GUIDANCE,
    ZORKSCRIPT_AUTHORING_TEMPLATE,
    _build_authoring_requirements,
    _build_quality_requirements,
)

# Expected output files in order
OUTPUT_FILES = [
    "game.zorkscript",
    "rooms.zorkscript",
    "items.zorkscript",
    "npcs.zorkscript",
    "puzzles.zorkscript",
    "quests.zorkscript",
    "commands.zorkscript",
]


def build_generation_prompt(
    concept: str,
    *,
    realism: str = "medium",
    authoring_fields: dict[str, Any] | None = None,
) -> str:
    """Build the full authoring prompt with file-header output instructions."""
    fields = authoring_fields or {}
    realism_key = (realism or "medium").strip().lower()

    quality = _build_quality_requirements(realism_key, fields)

    guidance = _REALISM_GUIDANCE.get(realism_key, [])
    realism_lines = [f"Realism: {realism_key}"]
    realism_lines.extend(f"- {line}" for line in guidance)
    realism_block = "\n".join(realism_lines)

    authoring_block = _build_authoring_requirements(fields)

    # Build the template with quality requirements
    template = ZORKSCRIPT_AUTHORING_TEMPLATE.replace(
        "{quality_requirements}", quality
    )

    # Build file output instructions
    file_instructions = [
        "",
        "Output ALL ZorkScript as a single response, organized into separate files.",
        "Clearly separate each file with a header line containing the exact filename:",
        "",
    ]
    file_descriptions = {
        "game.zorkscript": "game{} block, player{} block, and win/lose flag definitions",
        "rooms.zorkscript": "all room{} blocks with their exits",
        "items.zorkscript": "all item{} blocks (containers, toggleables, consumables, scenery)",
        "npcs.zorkscript": "all npc{} blocks with their talk/dialogue trees",
        "puzzles.zorkscript": "puzzle{} and lock{} blocks with related flag definitions",
        "quests.zorkscript": "quest{} blocks with objectives",
        "commands.zorkscript": (
            "on{} command blocks, when{} triggers,"
            " interaction{} responses, and remaining flags"
        ),
    }
    for filename in OUTPUT_FILES:
        desc = file_descriptions.get(filename, "")
        file_instructions.append(f"# {filename}")
        file_instructions.append(f"({desc})")
        file_instructions.append("")

    file_block = "\n".join(file_instructions)

    # Inject realism, authoring requirements, and file instructions before concept
    injected = f"\n{realism_block}\n\n{authoring_block}\n{file_block}\n"
    template = template.replace(
        "\nConcept:\n{concept}",
        f"{injected}\nConcept:\n{concept.strip()}",
    )

    return template.strip() + "\n"
