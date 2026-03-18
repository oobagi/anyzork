# Prompt Builder: Guided World Generation Wizard

Interactive terminal wizard that walks users through structured world-building fields, assembles a rich prompt, and feeds it into the existing generation pipeline.

---

## 1. Design Rationale

### The problem with freeform prompts

The concept pass (Pass 1) must extract theme, setting, tone, era, scale, vocabulary, genre tags, and a win condition from a single user string. When that string is vague ("a spooky house"), the LLM fills in every blank with its own defaults. The user gets a playable game, but not necessarily the game they imagined. They had no way to say "I want it comedic, not dark" or "I want 30 rooms, not 12" without knowing the internal schema.

Experienced users who have read the pipeline docs can write prompts like: "A crumbling space station in the far future, dark tone, medium scale, 25 rooms, the AI went mad and the player is a salvage operator who must escape via the shuttle bay." But most users should not need to reverse-engineer the concept schema to get good results.

### What the wizard solves

The wizard exposes the concept pass's input surface as a guided conversation. Each field maps directly to something the LLM needs. The user provides creative intent; the wizard structures it. The result is a prompt that is 3-5x richer than what a casual user would type freeform, which directly improves generation quality across all downstream passes (rooms, items, NPCs, puzzles).

### What the wizard does NOT do

It does not replace the concept pass. The concept pass still interprets and expands the structured prompt into the full concept JSON. The wizard's output is still a text prompt -- just a much better one.

---

## 2. CLI Integration

### Invocation modes

```
# Freeform (unchanged, always works)
anyzork generate "a haunted lighthouse on a cliff"

# Guided wizard (explicit flag)
anyzork generate --guided

# Guided wizard (no prompt, no flag -- wizard launches automatically)
anyzork generate

# Preset template (fills wizard defaults, user can edit/confirm)
anyzork generate --preset fantasy-dungeon

# List available presets
anyzork generate --list-presets
```

### Behavior rules

| Invocation | Result |
|---|---|
| `anyzork generate "prompt text"` | Freeform mode. No wizard. Existing behavior unchanged. |
| `anyzork generate --guided` | Wizard launches. All fields presented. |
| `anyzork generate` (no arguments) | Wizard launches automatically. This is the new default for the no-argument case. |
| `anyzork generate --guided "prompt"` | Wizard launches with the freeform prompt pre-filled into the World Description field. Other fields start empty. |
| `anyzork generate --preset fantasy-dungeon` | Wizard launches with preset values pre-filled. User can accept or modify any field. |
| `anyzork generate --preset fantasy-dungeon --no-edit` | Preset values are used directly without wizard interaction. Generates immediately. |

### CLI signature change

```python
@cli.command()
@click.argument("prompt", required=False, default=None)
@click.option("--guided", is_flag=True, help="Launch the interactive prompt builder wizard.")
@click.option("--preset", type=str, default=None, help="Load a genre preset (e.g., fantasy-dungeon, sci-fi-station).")
@click.option("--list-presets", is_flag=True, help="List available presets and exit.")
@click.option("--no-edit", is_flag=True, help="With --preset, skip wizard and generate immediately.")
@click.option("--output", "-o", ...)
@click.option("--seed", ...)
@click.option("--provider", ...)
def generate(prompt, guided, preset, list_presets, no_edit, output, seed, provider):
```

The `prompt` argument changes from required to optional. When absent and `--guided` is not set, the wizard launches by default. When present, freeform mode is used (unless `--guided` is also set, in which case the prompt seeds the wizard).

---

## 3. Wizard Flow

### Step-by-step sequential flow

The wizard presents one field at a time, top to bottom. Each step is a Rich panel with a title, description, and input prompt. The user types their answer and presses Enter. Pressing Enter on an empty line skips the field (for optional fields) or uses the default (for fields with defaults).

### Field order and rationale

The fields are ordered to match how a human naturally thinks about a world: setting first, then inhabitants, then objects, then story, then meta-preferences. Each field informs the next -- by the time the user reaches "Story / Plot," they have already described the world, characters, and items that the story involves.

| Step | Field | Required | Default | Maps to concept pass field |
|---|---|---|---|---|
| 1 | World Description | Yes | -- | `setting` |
| 2 | Time Period / Era | No | LLM infers from world description | `era` |
| 3 | Tone | No | LLM infers | `tone` |
| 4 | Genre Tags | No | LLM infers | `genre_tags` |
| 5 | Key Locations | No | LLM generates freely | Enriches prompt for rooms pass |
| 6 | Key Characters | No | LLM generates freely | Enriches prompt for NPCs pass |
| 7 | Key Items | No | LLM generates freely | Enriches prompt for items pass |
| 8 | Story / Main Quest | No | LLM infers from setting | `win_condition_description` |
| 9 | World Size | No | "medium" | `scale`, `room_count_target`, `region_count_target` |
| 10 | Special Requests | No | None | Appended as freeform addendum |

Total: 10 fields. At minimum, the user fills in 1 (World Description). A thorough user fills all 10 in under 3 minutes.

---

## 4. Field Specifications

### Step 1: World Description (REQUIRED)

**Purpose**: The foundational creative input. Everything else builds on this.

**What we ask**: "Describe the world, setting, or scenario for your game."

**Guidance text**: "Where is this? What kind of place is it? What happened here? Why is the player here? Be as detailed or as brief as you want -- a single sentence works, a paragraph works better."

**Input type**: Multi-line free text. The user types until they submit (Enter on an empty line after content, or a single Enter for a one-liner).

**Validation**: Must be non-empty. Minimum 5 characters.

**Maps to**: The core of the assembled prompt. Becomes the `{user_prompt}` that the concept pass receives.

---

### Step 2: Time Period / Era (optional)

**Purpose**: Anchors the world temporally. Strongly influences vocabulary, technology level, and item categories.

**What we ask**: "When does this world exist?"

**Guidance text**: "Examples: medieval, Victorian, 1920s, far future, prehistoric, timeless/mythical"

**Input type**: Single-line free text.

**Default**: Omitted (LLM infers from world description).

**Maps to**: Appended to prompt as "Time period: {value}". The concept pass extracts this into the `era` field.

---

### Step 3: Tone (optional)

**Purpose**: Controls the emotional register of all generated text -- room descriptions, dialogue, item names, lore.

**What we ask**: "What tone should the game have?"

**Input type**: Selection from a list, with a "custom" option for freeform input.

**Options**: dark, whimsical, serious, comedic, surreal, grim, hopeful, custom

These match the `tone` enum in the concept schema exactly, plus "custom" for anything outside the predefined list.

**Default**: Omitted (LLM infers from world description).

**Maps to**: Appended to prompt as "Tone: {value}".

---

### Step 4: Genre Tags (optional)

**Purpose**: Controls gameplay style. "puzzle" means lock-key-gate structures. "exploration" means rewarding curiosity. "survival" means resource tension. "combat" means hostile NPCs.

**What we ask**: "What gameplay styles should this game emphasize?"

**Input type**: Multi-select from a list, with ability to add custom tags.

**Options**: exploration, puzzle, survival, combat, mystery, horror, stealth, social, trading

**Default**: Omitted (LLM infers).

**Maps to**: Appended to prompt as "Gameplay emphasis: {comma-separated tags}".

---

### Step 5: Key Locations (optional)

**Purpose**: Gives the user direct influence over the spatial layout. Instead of hoping the LLM creates a "throne room," the user can request it.

**What we ask**: "Name any specific locations or areas you want in the game."

**Guidance text**: "List locations one per line. Include a brief description if you want. Examples: 'the captain's quarters -- locked, contains the override codes' or just 'a hidden garden'. Press Enter on an empty line when done."

**Input type**: Multi-line, one entry per line. Each entry is a location name with optional description after a dash or colon.

**Default**: Omitted (LLM generates all locations from the world description).

**Maps to**: Appended to prompt as a "Requested locations" section. These become strong hints for the rooms pass -- not guarantees, but the concept pass will include them in the setting description, and the rooms pass will pick them up.

---

### Step 6: Key Characters (optional)

**Purpose**: Lets the user pre-define NPCs with specific personalities, roles, or relationships. Without this, the NPC pass generates characters from scratch based on the concept.

**What we ask**: "Describe any characters or NPCs you want in the game."

**Guidance text**: "List characters one per line. Include role, personality, or purpose. Examples: 'a nervous engineer who knows the override codes' or 'Captain Aldric -- dead, but his ghost guards the bridge'. Press Enter on an empty line when done."

**Input type**: Multi-line, one entry per line.

**Default**: Omitted.

**Maps to**: Appended to prompt as a "Requested characters" section.

---

### Step 7: Key Items (optional)

**Purpose**: Lets the user request specific items -- a magic sword, a torn map, a security badge. These become strong hints for the items pass.

**What we ask**: "List any important items, tools, or objects you want in the game."

**Guidance text**: "One per line. Include significance if you want. Examples: 'a master key that opens all doors in the east wing' or 'an ancient scroll with a riddle'. Press Enter on an empty line when done."

**Input type**: Multi-line, one entry per line.

**Default**: Omitted.

**Maps to**: Appended to prompt as a "Requested items" section.

---

### Step 8: Story / Main Quest (optional)

**Purpose**: Defines what the player is trying to accomplish. Without this, the concept pass infers a win condition from the setting. With this, the user controls the narrative goal.

**What we ask**: "What is the player's main goal? What is the central conflict or quest?"

**Guidance text**: "What must the player achieve to win? What stands in their way? Examples: 'Escape the station by restoring power to the shuttle bay' or 'Find all three crystal fragments and return them to the altar to lift the curse.'"

**Input type**: Multi-line free text.

**Default**: Omitted (LLM infers from setting).

**Maps to**: Appended to prompt as "Main quest: {value}". The concept pass extracts this into `win_condition_description`.

---

### Step 9: World Size (optional)

**Purpose**: Controls the scope of the generated game. Directly sets the concept pass's `scale`, `room_count_target`, and `region_count_target`.

**What we ask**: "How big should the game world be?"

**Input type**: Selection from three options, each with a description.

**Options**:

| Choice | Label | Description |
|---|---|---|
| 1 | Small | 8-15 rooms, 1 region. A focused experience: a single building, a ship, a small dungeon. 10-20 minutes to play. |
| 2 | Medium | 16-30 rooms, 2-3 regions. The default. A complex with multiple wings, a town with districts. 30-60 minutes to play. |
| 3 | Large | 31-50 rooms, 4-6 regions. A sprawling world with distinct zones. 1-2 hours to play. |

**Default**: Medium (2).

**Maps to**: Appended to prompt as "World size: {small/medium/large}".

---

### Step 10: Special Requests (optional)

**Purpose**: Catch-all for anything the structured fields did not cover. Accessibility preferences, specific puzzle types, narrative constraints, things to avoid.

**What we ask**: "Anything else the generator should know?"

**Guidance text**: "Any additional instructions, constraints, or creative direction. Examples: 'no combat', 'include at least one riddle-based puzzle', 'the ending should be ambiguous', 'make it kid-friendly'."

**Input type**: Multi-line free text.

**Default**: Omitted.

**Maps to**: Appended to the end of the assembled prompt as an "Additional instructions" section.

---

## 5. Terminal UX Mockups

### Wizard launch

```
$ anyzork generate

 AnyZork -- World Builder
 Build your text adventure step by step.
 Fill in what inspires you, skip what doesn't. Only the first field is required.
 Tip: Press Enter on an empty line to skip optional fields.

 Step 1 of 10 -- World Description (required)

 Describe the world, setting, or scenario for your game.
 Where is this? What kind of place? What happened here? Why is the player here?

 > A crumbling orbital research station. The central AI designated MOTHER
 > went rogue three years ago, sealing sections and venting atmosphere.
 > The crew is gone. You're a salvage operator who just docked.
 >
```

### Tone selection

```
 Step 3 of 10 -- Tone (optional, press Enter to skip)

 What tone should the game have?

  [1] dark
  [2] whimsical
  [3] serious
  [4] comedic
  [5] surreal
  [6] grim
  [7] hopeful
  [8] custom (type your own)

 > 1
```

### Genre tag multi-select

```
 Step 4 of 10 -- Genre Tags (optional, press Enter to skip)

 What gameplay styles should this game emphasize?
 Enter numbers separated by commas, or type custom tags.

  [1] exploration
  [2] puzzle
  [3] survival
  [4] combat
  [5] mystery
  [6] horror
  [7] stealth
  [8] social
  [9] trading

 > 1, 2, 5
```

### Multi-line entry (locations)

```
 Step 5 of 10 -- Key Locations (optional, press Enter to skip)

 Name any specific locations or areas you want in the game.
 One per line. Add a brief description after a dash if you want.
 Press Enter on an empty line when done.

 > The docking bay -- where the player starts, emergency lights only
 > MOTHER's core -- the central AI chamber, heavily sealed
 > The hydroponics lab -- overgrown, something is still alive in here
 > Medical bay -- ransacked, but the cryo pods are still running
 >
```

### World size selection

```
 Step 9 of 10 -- World Size (optional, default: medium)

 How big should the game world be?

  [1] Small    8-15 rooms, 1 region. A single building or ship. ~15 min.
  [2] Medium   16-30 rooms, 2-3 regions. Multiple wings or districts. ~45 min.
  [3] Large    31-50 rooms, 4-6 regions. A sprawling world. ~90 min.

 > 2
```

### Preview and confirmation

After all fields are collected, the wizard assembles the prompt and shows a preview panel. This is the most important UX moment -- the user sees exactly what the generator will receive and can approve, edit, or restart.

```
 Prompt Preview

 WORLD DESCRIPTION
 A crumbling orbital research station. The central AI designated MOTHER
 went rogue three years ago, sealing sections and venting atmosphere.
 The crew is gone. You're a salvage operator who just docked.

 TIME PERIOD: far future
 TONE: dark
 GAMEPLAY: exploration, puzzle, mystery
 WORLD SIZE: medium (16-30 rooms, 2-3 regions)

 KEY LOCATIONS
  - The docking bay -- where the player starts, emergency lights only
  - MOTHER's core -- the central AI chamber, heavily sealed
  - The hydroponics lab -- overgrown, something is still alive in here
  - Medical bay -- ransacked, but the cryo pods are still running

 KEY CHARACTERS
  - A damaged maintenance bot that speaks in fragments
  - The ghost of Dr. Vasquez, visible only in dark rooms

 KEY ITEMS
  - MOTHER's access card -- needed to enter the AI core
  - A handheld terminal with corrupted logs

 MAIN QUEST
 Reach MOTHER's core and shut her down, or find the shuttle bay
 override to escape. The player must choose.

 ADDITIONAL INSTRUCTIONS
 Include at least one area where the player must make a moral choice.

 [G]enerate  [E]dit a field  [R]estart  [Q]uit
 >
```

### Edit flow

If the user selects `[E]dit`, they are prompted for the field number (1-10) and can re-enter that field. The preview updates and the confirmation prompt reappears.

```
 Which field to edit? (1-10): 3

 Step 3 of 10 -- Tone

 Current value: dark
 New value (or Enter to keep): grim
```

---

## 6. Assembled Prompt Format

The wizard produces a single string that is passed to `generate_game(prompt=...)` exactly as a freeform prompt would be. The concept pass receives it as `context["user_prompt"]` and interprets it.

### Template

```
{world_description}

Time period: {era}
Tone: {tone}
Gameplay emphasis: {genre_tags}
World size: {scale} ({room_range} rooms, {region_range} regions)

Requested locations:
- {location_1}
- {location_2}
...

Requested characters:
- {character_1}
- {character_2}
...

Requested items:
- {item_1}
- {item_2}
...

Main quest: {story}

Additional instructions: {special_requests}
```

Sections for omitted fields are not included in the output. A minimal prompt (only world description filled) looks identical to a freeform prompt. A fully filled prompt looks like the preview above.

### Why a single string, not structured data

The generation pipeline already handles the prompt-to-concept interpretation well. The concept pass is designed to parse natural-language prompts and extract structured fields. Passing structured data directly to each pass would require:

1. Changing the orchestrator's `generate_game` signature
2. Changing every pass's context-building logic
3. Duplicating validation that the concept pass already performs
4. Creating a parallel code path that must be maintained alongside the freeform path

None of that is necessary. The wizard's structured prompt gives the concept pass clear, labeled fields to extract. The LLM does not need to guess what "dark" means when it appears after "Tone:" -- it maps directly to the `tone` enum. The wizard improves the input quality; the concept pass does the interpretation as before.

### Future optimization: structured passthrough

If a future version wants to bypass the concept pass's interpretation entirely (saving one LLM call), the wizard could emit the concept JSON directly. This is a clean optimization that does not require architectural changes -- the orchestrator could check whether the prompt is already a valid concept JSON and skip Pass 1. This is out of scope for the initial implementation but is a natural evolution.

---

## 7. Template / Preset System

### What presets do

Presets are pre-authored wizard field values for common game archetypes. They serve two purposes:

1. **Faster generation**: Users who want "a fantasy dungeon" should not have to describe one from scratch. The preset fills in world description, tone, genre tags, suggested locations, and scale. The user can accept it as-is or modify any field.

2. **Quality baseline**: Presets are hand-tuned prompts that produce consistently good results. They demonstrate what a "good" prompt looks like, teaching users how to fill in the wizard effectively for custom games.

### Preset format

Presets are stored as TOML files in `anyzork/presets/`. Each file defines values for any subset of the wizard fields.

```toml
# anyzork/presets/fantasy-dungeon.toml

name = "Fantasy Dungeon"
description = "A classic dungeon crawl with traps, treasure, and a dragon."

[fields]
world_description = """
A vast underground dungeon beneath a ruined castle. Once the vault of a
mad king who hoarded cursed artifacts, it has been sealed for centuries.
Traps still function. Creatures have moved in. The player is an adventurer
who found the entrance and descended, seeking the legendary Crown of Avarice.
"""

era = "medieval fantasy"
tone = "serious"
genre_tags = ["exploration", "puzzle", "combat"]
scale = "medium"

story = """
Find the Crown of Avarice in the deepest level of the dungeon and escape
alive. The crown is guarded by the undead king who still sits on his
throne. To reach him, you must navigate traps, solve the riddles of the
three gates, and find the silver key that unlocks the inner sanctum.
"""

[[fields.locations]]
entry = "The Collapsed Entrance -- rubble partially blocks the way back"

[[fields.locations]]
entry = "The Hall of Mirrors -- disorienting, some mirrors are doors"

[[fields.locations]]
entry = "The Throne Room -- the final chamber, cold and silent"

[[fields.characters]]
entry = "A trapped ghost who offers hints in exchange for finding her locket"

[[fields.items]]
entry = "The silver key -- ornate, hidden in the Hall of Mirrors"
entry = "The Crown of Avarice -- the ultimate goal, cursed"
```

### Included presets

The initial release ships with 6 presets covering common archetypes:

| Preset ID | Name | Scale | Genre |
|---|---|---|---|
| `fantasy-dungeon` | Fantasy Dungeon | Medium | exploration, puzzle, combat |
| `sci-fi-station` | Space Station | Medium | exploration, puzzle, survival |
| `mystery-mansion` | Mystery Mansion | Small | mystery, puzzle, exploration |
| `zombie-survival` | Zombie Outbreak | Medium | survival, combat, horror |
| `pirate-island` | Pirate Island | Large | exploration, puzzle, trading |
| `cyberpunk-heist` | Cyberpunk Heist | Small | stealth, puzzle, social |

### Preset listing

```
$ anyzork generate --list-presets

 Available Presets

 fantasy-dungeon    Fantasy Dungeon     A classic dungeon crawl with traps, treasure, and a dragon.
 sci-fi-station     Space Station       A crumbling orbital station with a rogue AI.
 mystery-mansion    Mystery Mansion     A locked-room mystery in a Victorian manor.
 zombie-survival    Zombie Outbreak     Survive the first night in an overrun research facility.
 pirate-island      Pirate Island       A sprawling island with hidden coves and buried treasure.
 cyberpunk-heist    Cyberpunk Heist     Break into a megacorp tower to steal prototype tech.

 Usage: anyzork generate --preset fantasy-dungeon
```

### Custom presets

Users can add their own preset files to `~/.anyzork/presets/`. The wizard merges both directories, with user presets taking precedence on name collision.

---

## 8. How the Wizard Improves Generation Quality

### Field-by-field impact analysis

| Wizard Field | Without wizard (freeform) | With wizard | Quality improvement |
|---|---|---|---|
| World Description | Often 1 sentence. Vague. | Guided to be specific. | Concept pass produces more coherent settings with fewer invented details. |
| Era | Usually omitted. LLM guesses. | Explicit or consciously omitted. | Vocabulary hints match the era. No anachronisms in room names. |
| Tone | Rarely specified. LLM defaults to "serious." | Chosen from the exact enum the concept pass uses. | Descriptions, dialogue, and item names share a consistent register. |
| Genre Tags | Never specified in freeform. | User chooses gameplay emphasis. | Rooms, NPCs, and items are generated to support the chosen gameplay style. |
| Key Locations | Never specified. | User names 3-5 must-have locations. | The rooms pass includes them. Player gets the game they imagined. |
| Key Characters | Never specified. | User defines NPC personalities and roles. | NPCs pass produces characters that match user expectations. |
| Key Items | Never specified. | User defines plot-critical items. | Items pass creates the requested items. Puzzle coherence improves. |
| Story / Quest | Sometimes included in freeform. Often vague. | Structured goal with conflict. | Win condition is clear. Puzzle chain has a defined endpoint. |
| World Size | Never specified. Defaults to LLM's guess. | Explicit small/medium/large. | Room count matches user expectation. No "I wanted a quick game and got 45 rooms." |
| Special Requests | Occasionally in freeform as afterthought. | Dedicated field for constraints. | Constraints like "no combat" or "kid-friendly" are not buried in prose. |

### Quantitative hypothesis

Based on the concept pass's interpretation guidelines and the downstream passes' prompt structures, a wizard-generated prompt should:

- Reduce concept pass retry rate by ~50% (fewer ambiguous inputs to misinterpret)
- Increase user satisfaction with room names and locations (user specified them)
- Reduce "wrong tone" complaints to near zero (user chose from the enum)
- Produce games that match user expectations on first generation ~80% of the time, vs. ~40% for freeform prompts [PLACEHOLDER -- measure in playtest]

---

## 9. Implementation Considerations

### Rich components used

| Component | Where used |
|---|---|
| `rich.panel.Panel` | Each wizard step is wrapped in a panel with a title and border |
| `rich.prompt.Prompt` | Single-line text inputs (era, tone selection, world size) |
| `rich.console.Console.input` | Multi-line free text inputs (world description, locations, characters) |
| `rich.text.Text` | Guidance text beneath each field title |
| `rich.markdown.Markdown` | Preview panel rendering |
| `rich.table.Table` | Preset listing, genre tag options |

### Multi-line input handling

Rich does not natively support multi-line input. The wizard uses a simple loop: read lines with `console.input()` until the user submits an empty line. Lines are joined with newlines. This matches how terminal tools like `git commit` handle multi-line input without an editor.

For users who prefer an editor, a future enhancement could support `$EDITOR` invocation (like `git commit` without `-m`). This is out of scope for the initial version.

### Non-interactive environments

If stdin is not a TTY (piped input, CI, scripted usage), the wizard must not launch. The CLI should detect `sys.stdin.isatty()` and require the freeform prompt argument in non-interactive contexts. If neither a prompt nor `--preset --no-edit` is provided in a non-TTY context, exit with an error message.

### State management

The wizard maintains a simple `dict[str, str | list[str] | None]` of field values. No persistence between runs. If the user quits mid-wizard, nothing is saved.

### Module structure

```
anyzork/
  cli.py                    # Updated generate command
  wizard/
    __init__.py             # Public API: run_wizard() -> str
    fields.py               # Field definitions, validation, rendering
    presets.py               # Preset loading and listing
    assembler.py             # Assembles field values into prompt string
  presets/
    fantasy-dungeon.toml
    sci-fi-station.toml
    mystery-mansion.toml
    zombie-survival.toml
    pirate-island.toml
    cyberpunk-heist.toml
```

### Integration point

The wizard's public API is a single function:

```python
def run_wizard(
    console: Console,
    initial_prompt: str | None = None,
    preset: dict | None = None,
) -> str | None:
    """Run the interactive prompt builder wizard.

    Returns the assembled prompt string, or None if the user quit.
    """
```

The `generate` command calls this function, receives the prompt string, and passes it to `generate_game(prompt=...)` exactly as before.

---

## 10. Edge Cases and Failure States

| Scenario | Behavior |
|---|---|
| User fills only World Description | Valid. Produces a prompt equivalent to freeform. All other fields are inferred by the concept pass. |
| User fills everything | Valid. Produces a rich, detailed prompt. Concept pass has minimal interpretation work. |
| User provides contradictory fields (e.g., era="medieval" but world description mentions "space station") | Not blocked. The concept pass resolves contradictions using its interpretation guidelines. The wizard could add a soft warning in a future version. |
| User types a very long world description (1000+ characters) | Accepted. The concept pass handles prompts of any length. |
| User selects "custom" tone and types something not in the enum | Accepted. The concept pass's LLM interpretation can map any tone description to the closest enum value. |
| Terminal window is very narrow (< 60 columns) | Rich handles wrapping. Panels may look cramped but remain functional. |
| User presses Ctrl+C during wizard | Exits cleanly with "Generation cancelled." message. No partial state is persisted. |
| User runs `--preset` with a nonexistent preset name | Error message listing available presets. |

---

## 11. Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-03-18 | Initial design. 10-field wizard, 6 presets, Rich terminal UX. |
