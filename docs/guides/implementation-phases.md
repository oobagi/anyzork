# Implementation Phases

This file is the active roadmap. It is intentionally forward-looking: shipped work should be understood from the codebase and the core docs, not preserved here as historical phase detail.

## Current State

The shipped product loop is:

1. `anyzork generate` builds a ZorkScript authoring prompt.
2. An external LLM returns ZorkScript.
3. `anyzork import` compiles the script into a `.zork` file.
4. `anyzork play` runs that file with a deterministic engine.

What is already in place:

- Deterministic runtime engine with command DSL, quests, triggers, containers, dialogue, and item-state systems
- Guided authoring wizard and preset-backed prompt generation
- ZorkScript parser, importer, and deterministic validation
- Managed save slots and direct-play support
- Optional narrator mode backed by Claude, OpenAI, or Gemini

## Phase 5f: Narrator Immersive Mode

**Goal:** Make `anyzork play --narrator` feel like a fully narrated interactive novel instead of the standard engine UI with prose layered on top.

**Tasks:**

- [ ] Narrate every major player-facing output path: rooms, actions, dialogue, inventory, quests, and system feedback
- [ ] Suppress standard UI chrome in narrator mode when prose output is available
- [ ] Tighten the narrator prompt/context format to reduce token cost and latency
- [ ] Expand caching so repeated room visits and repeated actions avoid duplicate provider calls
- [ ] Keep graceful fallback behavior: if narration fails, deterministic engine output still appears immediately
- [ ] Revisit what stable world context the narrator should read from metadata instead of reconstructing from author prompts

**Likely files:**

- `anyzork/engine/game.py`
- `anyzork/engine/narrator.py`
- `anyzork/generator/providers/`
- `anyzork/cli.py`

**Done when:** narrator mode feels intentionally immersive, remains read-only, and never blocks a playable session when an API call fails.

---

## Phase 6: Optional Combat

**Goal:** Add deterministic turn-based combat without turning AnyZork into a combat-first game.

**Tasks:**

- [ ] Define the smallest combat ruleset that fits the existing engine philosophy
- [ ] Add equip-slot and combat-state schema only where the runtime truly needs it
- [ ] Implement a turn-based combat loop with deterministic outcomes
- [ ] Keep combat puzzle-oriented: weaknesses, preparation, and item use should matter more than raw stat grinding
- [ ] Extend authoring/import validation so combat-enabled games remain winnable and readable
- [ ] Add focused test coverage and at least one representative combat-enabled test world

**Likely files:**

- `anyzork/db/schema.py`
- `anyzork/engine/game.py`
- `anyzork/engine/commands.py`
- `anyzork/importer.py`
- `anyzork/generator/validator.py`

**Done when:** combat-enabled games are deterministic, fair, optional at the product level, and mechanically coherent with the rest of the engine.

---

## Backlog Notes

- Keep docs lean and current. If a design doc becomes historical, delete it instead of archiving it in-place.
- Prefer extending the existing `generate -> import -> play` flow over reintroducing in-app generation pipelines.
- Treat narrator providers as runtime presentation infrastructure, not world-generation infrastructure.
