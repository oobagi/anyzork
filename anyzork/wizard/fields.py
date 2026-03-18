"""Field definitions for the prompt builder wizard.

Each field knows how to prompt the user, validate input, and render
itself in the preview panel. Fields are ordered to match how a human
naturally thinks about a world: setting first, then inhabitants, then
objects, then story, then meta-preferences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FieldType(Enum):
    """How the field collects user input."""

    TEXT = "text"                # Single-line free text
    MULTILINE = "multiline"     # Multi-line free text (enter on empty line to finish)
    SELECT = "select"           # Numbered selection from a list
    MULTI_SELECT = "multi_select"  # Comma-separated numbered selections


@dataclass
class FieldDef:
    """Definition of a single wizard field."""

    key: str
    label: str
    step: int
    required: bool
    field_type: FieldType
    ask_text: str
    guidance: str
    options: list[str] = field(default_factory=list)
    allow_custom: bool = False
    default_display: str | None = None
    prompt_label: str | None = None  # Label used in assembled prompt

    def format_for_prompt(self, value: Any) -> str | None:
        """Format a field value for the assembled prompt string.

        Returns None if the value is empty/None (field should be omitted).
        """
        if value is None:
            return None

        if isinstance(value, list):
            if not value:
                return None
            # List fields (locations, characters, items) become bullet lists.
            if self.key in ("locations", "characters", "items"):
                label = self.prompt_label or self.label
                lines = [f"Requested {label.lower()}:"]
                for entry in value:
                    lines.append(f"- {entry}")
                return "\n".join(lines)
            # Genre tags become comma-separated.
            return f"{self.prompt_label or self.label}: {', '.join(value)}"

        text = str(value).strip()
        if not text:
            return None

        if self.key == "world_description":
            return text
        if self.key == "scale":
            return f"World size: {text}"
        if self.key == "story":
            return f"Main quest: {text}"
        if self.key == "special_requests":
            return f"Additional instructions: {text}"

        return f"{self.prompt_label or self.label}: {text}"


# ---------------------------------------------------------------------------
# Scale descriptions for world size display
# ---------------------------------------------------------------------------

SCALE_OPTIONS = [
    ("Small", "8-15 rooms, 1 region. A single building or ship. ~15 min."),
    ("Medium", "16-30 rooms, 2-3 regions. Multiple wings or districts. ~45 min."),
    ("Large", "31-50 rooms, 4-6 regions. A sprawling world. ~90 min."),
]

SCALE_VALUES = ["small", "medium", "large"]

SCALE_DETAIL = {
    "small": "small (8-15 rooms, 1 region)",
    "medium": "medium (16-30 rooms, 2-3 regions)",
    "large": "large (31-50 rooms, 4-6 regions)",
}

# ---------------------------------------------------------------------------
# Tone and genre options
# ---------------------------------------------------------------------------

TONE_OPTIONS = ["dark", "whimsical", "serious", "comedic", "surreal", "grim", "hopeful"]

GENRE_OPTIONS = [
    "exploration", "puzzle", "survival", "combat",
    "mystery", "horror", "stealth", "social", "trading",
]

# ---------------------------------------------------------------------------
# Ordered field definitions
# ---------------------------------------------------------------------------

FIELDS: list[FieldDef] = [
    FieldDef(
        key="world_description",
        label="World Description",
        step=1,
        required=True,
        field_type=FieldType.MULTILINE,
        ask_text="Describe the world, setting, or scenario for your game.",
        guidance=(
            "Where is this? What kind of place? What happened here? Why is the player here?\n"
            "Be as detailed or brief as you want -- a single sentence works, a paragraph works better.\n"
            "Press Enter on an empty line when done."
        ),
        prompt_label="World Description",
    ),
    FieldDef(
        key="era",
        label="Time Period / Era",
        step=2,
        required=False,
        field_type=FieldType.TEXT,
        ask_text="When does this world exist?",
        guidance="Examples: medieval, Victorian, 1920s, far future, prehistoric, timeless/mythical",
        prompt_label="Time period",
    ),
    FieldDef(
        key="tone",
        label="Tone",
        step=3,
        required=False,
        field_type=FieldType.MULTI_SELECT,
        ask_text="What tone should the game have?",
        guidance="Enter numbers separated by commas (e.g., 1,4), or type custom tones.",
        options=TONE_OPTIONS,
        allow_custom=True,
        prompt_label="Tone",
    ),
    FieldDef(
        key="genre_tags",
        label="Genre Tags",
        step=4,
        required=False,
        field_type=FieldType.MULTI_SELECT,
        ask_text="What gameplay styles should this game emphasize?",
        guidance="Enter numbers separated by commas, or type custom tags.",
        options=GENRE_OPTIONS,
        allow_custom=True,
        prompt_label="Gameplay emphasis",
    ),
    FieldDef(
        key="locations",
        label="Key Locations",
        step=5,
        required=False,
        field_type=FieldType.MULTILINE,
        ask_text="Name any specific locations or areas you want in the game.",
        guidance=(
            "One per line. Add a brief description after a dash if you want.\n"
            "Press Enter on an empty line when done."
        ),
        prompt_label="locations",
    ),
    FieldDef(
        key="characters",
        label="Key Characters",
        step=6,
        required=False,
        field_type=FieldType.MULTILINE,
        ask_text="Describe any characters or NPCs you want in the game.",
        guidance=(
            "One per line. Include role, personality, or purpose.\n"
            "Press Enter on an empty line when done."
        ),
        prompt_label="characters",
    ),
    FieldDef(
        key="items",
        label="Key Items",
        step=7,
        required=False,
        field_type=FieldType.MULTILINE,
        ask_text="List any important items, tools, or objects you want in the game.",
        guidance=(
            "One per line. Include significance if you want.\n"
            "Press Enter on an empty line when done."
        ),
        prompt_label="items",
    ),
    FieldDef(
        key="story",
        label="Story / Main Quest",
        step=8,
        required=False,
        field_type=FieldType.MULTILINE,
        ask_text="What is the player's main goal? What is the central conflict or quest?",
        guidance=(
            "What must the player achieve to win? What stands in their way?\n"
            "Press Enter on an empty line when done."
        ),
        prompt_label="Main quest",
    ),
    FieldDef(
        key="scale",
        label="World Size",
        step=9,
        required=False,
        field_type=FieldType.SELECT,
        ask_text="How big should the game world be?",
        guidance="Choose a size. Default is medium.",
        options=[],  # Options are rendered specially (with descriptions)
        default_display="medium",
        prompt_label="World size",
    ),
    FieldDef(
        key="special_requests",
        label="Special Requests",
        step=10,
        required=False,
        field_type=FieldType.MULTILINE,
        ask_text="Anything else the generator should know?",
        guidance=(
            "Any additional instructions, constraints, or creative direction.\n"
            "Examples: 'no combat', 'include a riddle-based puzzle', 'make it kid-friendly'.\n"
            "Press Enter on an empty line when done."
        ),
        prompt_label="Additional instructions",
    ),
]

FIELD_BY_KEY = {f.key: f for f in FIELDS}
