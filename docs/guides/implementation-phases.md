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
- Share packages plus official catalog browse/install/upload plumbing
- Optional narrator mode backed by Claude, OpenAI, or Gemini

## Phase 5e: Catalog Moderation and Curation

**Goal:** Turn the shipped sharing pipeline into a curated official library instead of a raw upload bucket.

Security hardening shipped or in progress: upload filename sanitization, slug collision protection, unpublished-by-default uploads, and install source restrictions.

**Remaining tasks:**

- [ ] Add a real moderation workflow so uploads are reviewed before they appear in the public catalog
- [ ] Add admin tooling for approving, rejecting, editing, and unpublishing submissions
- [ ] Define how slug ownership and package updates work once a game is approved
- [ ] Add reporting, featured picks, and richer browsing metadata after moderation exists
- [ ] Decide whether ratings/voting belong in the first public catalog version or a later one

**Likely files:**

- `anyzork/catalog_api.py`
- `anyzork/catalog_store.py`
- `docs/architecture/system-design.md`
- `README.md`

**Done when:** creators can submit packages, moderators can curate them, and the public catalog only shows approved games.

---

## Packaging and Distribution (in progress)

**Goal:** Make installing the AnyZork CLI feel like a normal product install instead of a source checkout workflow.

Active work on `codex/pipx-packaging` branch.

**Tasks:**

- [ ] Publish real CLI releases as wheels and sdists instead of relying on editable installs for normal users
- [ ] Support `pipx install anyzork` as the primary end-user install path
- [ ] Document the install, upgrade, and narrator-extra flow clearly in the README and release docs
- [ ] Decide whether Homebrew is worth supporting after the Python packaging path is stable

**Likely files:**

- `pyproject.toml`
- `.github/workflows/`
- `README.md`

**Done when:** a new user can install, upgrade, and run the CLI without cloning the repo or using editable installs.

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
- `anyzork/engine/providers/`
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
- `anyzork/validation.py`

**Done when:** combat-enabled games are deterministic, fair, optional at the product level, and mechanically coherent with the rest of the engine.

---

## Backlog Notes

- Keep docs lean and current. If a design doc becomes historical, delete it instead of archiving it in-place.
- Prefer extending the existing `generate -> import -> play` flow over reintroducing in-app generation pipelines.
- Treat narrator providers as runtime presentation infrastructure, not world-generation infrastructure.
