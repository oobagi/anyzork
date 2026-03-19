# Generation Pipeline Design

How AnyZork turns a prompt into a playable `.zork` file.

## 1. Why Multi-Pass

Generating a whole adventure in one shot produces brittle, tangled output. AnyZork uses a staged pipeline so each pass can focus on a narrow concern, validate its own output, and be retried independently.

Benefits:

- Focused prompts: each pass sees only the slice of the world it needs.
- Cheaper retries: a broken quest pass does not force rooms and items to regenerate.
- Better validation: structural mistakes can be caught before later passes build on them.
- Cleaner mental models: spatial layout, commands, quest tracking, and reactive events are generated separately.

## 2. Current Pass Order

The current implementation runs ten LLM-backed passes followed by deterministic validation.

### Pass 1: Concept

Produces game-level creative direction in `metadata`: title, setting, tone, scale targets, intro/win text, and win-condition scaffolding.

### Pass 2: Rooms

Produces `rooms` and `exits`. This establishes the spatial graph, start room, region layout, and hidden or special routes.

### Pass 3: Locks

Produces `locks` and related initial flags. This shapes progression and ensures gates have reachable solutions.

### Pass 4: Items

Produces `items`, including containers, key items, readable/scenic objects, item-state metadata, and placement.

### Pass 5: NPCs

Produces `npcs`, `dialogue_nodes`, and `dialogue_options`. NPCs are authored as deterministic dialogue trees, not runtime freeform agents.

### Pass 6: Interactions

Produces `interaction_responses`: category-level rules for using tagged items on tagged targets. This is where realism-sensitive generic interactions such as firearms on characters or light sources in dark spaces are standardized.

### Pass 7: Puzzles

Produces `puzzles` and any puzzle-specific flags or metadata. Puzzles should reference existing rooms, items, locks, and NPCs rather than inventing isolated mechanics.

### Pass 8: Commands

Produces `commands`, the player-initiated DSL rules. Commands wire specific puzzle steps, key uses, container actions, readable objects, and custom interactions into deterministic gameplay.

### Pass 9: Quests

Produces `quests`, `quest_objectives`, and supporting flags.

Quest design rules:

- exactly one main quest
- two to four side quests
- objectives track existing or newly declared flags
- quests organize progress; they do not replace gating
- the main quest completion flag should align with metadata win conditions

### Pass 10: Triggers

Produces `triggers`, reactive rules fired by emitted events such as:

- `room_enter`
- `flag_set`
- `dialogue_node`
- `item_taken`
- `item_dropped`

Triggers handle world reactions that should not require a typed command, such as dialogue rewards, automatic unlocks, or room-entry events.

### Final Step: Validation

Validation is deterministic code, not an LLM call. It reads the fully populated database and reports cross-table inconsistencies.

## 3. Pass Dependency Rules

The orchestrator builds pass context from prior outputs only.

| Pass | Reads |
|---|---|
| `concept` | prompt only |
| `rooms` | concept |
| `locks` | concept, rooms |
| `items` | concept, rooms, locks |
| `npcs` | concept, rooms, items, locks |
| `interactions` | concept, rooms, items, npcs |
| `puzzles` | concept, rooms, items, npcs, locks |
| `commands` | concept, rooms, locks, items, npcs, puzzles, interactions |
| `quests` | concept, rooms, locks, items, npcs, puzzles, commands |
| `triggers` | concept, rooms, locks, items, npcs, puzzles, commands, quests |

## 4. Design Guidance Per Stage

### Spatial Design

- The start room must orient the player and teach at least one core verb.
- Critical-path rooms must remain traversable once the right solutions are found.
- Optional branches should contain meaningful rewards: shortcuts, puzzle clues, items, side quests, or atmospheric discoveries.

### Progression Design

- Every mandatory gate needs a reachable solution.
- Avoid circular lock dependencies.
- Use flags as shared glue between commands, quests, locks, and triggers.

### Content Design

- Clues should live in room text, examine text, dialogue, and puzzle hints.
- NPCs should have a clear gameplay purpose: quest giver, blocker, guide, trader, or witness.
- Optional content should deepen understanding or reward curiosity, not just pad room count.

### Reactivity Design

- Commands answer "what can the player do?"
- Triggers answer "what happens because that state changed?"
- Keep those concerns separate so generation stays legible.

## 5. Validation Checklist

The validator should confirm:

### Structural integrity

- every room is reachable from the start on the base graph
- exits reference valid rooms
- locks reference valid exits, items, or puzzles
- dialogue nodes and options reference valid NPCs and follow-up nodes
- commands, quests, and triggers only reference existing entities or declared flags

### Gameplay integrity

- required lock solutions are reachable before the lock
- no obvious softlocks or circular dependencies
- win conditions are achievable
- quest objectives point to meaningful flags
- trigger cascades do not create runaway loops

### Content integrity

- rooms, items, NPCs, puzzles, quests, and triggers all exist in proportions that match the game scale
- score metadata is internally consistent
- one-shot content is represented with the proper execution guards

## 6. Implementation Notes

The executable pipeline lives in [anyzork/generator/orchestrator.py](/Users/jaden/Developer/anyzork/anyzork/generator/orchestrator.py). If this document and the orchestrator ever disagree, fix both together in the same change.
