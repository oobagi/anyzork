# AnyZork Design Brief

## The Problem

Using an LLM to play a text adventure in real-time doesn't work well:

1. **Context loss** — the LLM forgets rooms, items, and world state as the conversation grows
2. **State inconsistency** — the LLM hallucinates what the player can/can't do. It lets you open doors that should be locked, use items you don't have, or walk through walls
3. **World drift** — room descriptions change between visits, NPCs forget conversations, puzzles change their solutions mid-game

The core issue: the LLM is simultaneously the world database, the game engine, and the narrator. It's bad at the first two.

## The Solution

Split the responsibilities:

1. **The LLM generates the world** — rooms, exits, items, NPCs, puzzles, lore, and the *commands* that wire them together. All of this is stored as structured data in a SQLite database (a `.zork` file).
2. **A deterministic engine runs the game** — it reads from the database, evaluates commands as structured rules, and manages player state. No LLM involved. No hallucination possible.

The LLM is used where it's strong (creative generation) and removed from where it's weak (state management, consistency).

## Why a Command DSL Instead of Generated Code

The LLM could generate Python code for each command, but that's fragile and a security risk. Instead, commands are structured **precondition/effect rules** stored as JSON in the database:

```
verb: "use"
pattern: "use {item} on {target}"
preconditions: [player has "rusty_key", player in "dungeon_entrance"]
effects: [remove "rusty_key", unlock "dungeon_door", print "The door creaks open..."]
```

The engine interprets these deterministically. The DSL is expressive enough for complex puzzles but impossible to hallucinate at runtime — every command either matches its preconditions or it doesn't.

## Why Multi-Pass Generation

Generating an entire game world in one LLM call is unreliable. Instead, generation happens in passes, each one focused and building on the last:

1. **World concept** — interpret the user's prompt, set theme/tone/scale
2. **Room graph** — generate rooms and connections (the spatial layout)
3. **Locks & gates** — add locks to exits, creating the progression structure
4. **Items** — populate rooms with objects, keys, tools
5. **NPCs** — add characters with dialogue and behavior
6. **Puzzles** — create multi-step challenges with solutions and rewards
7. **Commands** — generate DSL rules that wire everything together
8. **Lore** — layer in discoverable text at three tiers
9. **Validation** — verify consistency (all exits connect, all locks solvable, no orphans)

Each pass has focused context (just the relevant slice of the world), can validate against what already exists, and can be retried independently if it fails.

## Why SQLite

A single `.zork` file = one complete, portable game. Copy it, email it, put it on a USB stick. No server, no connection string, no setup. SQLite gives us:

- ACID transactions (game state is always consistent)
- Foreign keys (rooms reference rooms, items reference rooms, etc.)
- Indexes for fast lookups (find items in a room, commands for a verb)
- WAL mode for concurrent reads during narrator mode
- Zero dependencies (built into Python)

## The Narrator Mode

The engine outputs deterministic text: "You are in the Dungeon Entrance. There is a rusty door to the north." This is functional but bland.

**Narrator mode** is an optional thin LLM layer that takes the deterministic output and flavors it with prose: "The air is thick with the smell of damp stone. Before you, a door of rusted iron hangs on a single hinge, groaning softly in a draft you can't feel."

Critically, the narrator **cannot change game state**. It receives the engine's output as read-only context and produces flavored text. If the narrator hallucinates, the game still works correctly — you just get colorful lies alongside accurate state.

## Provider Strategy

We support three API providers (bring your own key):
- **Claude** (Anthropic API)
- **OpenAI** (OpenAI API)
- **Gemini** (Google GenAI API)

These make direct API calls with structured prompts. The user sets their API key via env var. The generator's orchestrator calls the same interface regardless of which provider is active.

> **Future:** CLI providers (Claude Code, Codex) that invoke agentic tools as subprocesses are deferred to a future version.

## Additional Features

### Save/Load
Trivial — the `.zork` file *is* the save. The player state table tracks position, inventory, health, score, moves, and flags. Copy the file to save, restore it to load.

### Game Export & Sharing
`.zork` files are self-contained. Share them however you want. The engine just needs the file path.

### Seed System
Same user prompt + same seed = same generated world (assuming the same provider/model). Seeds are passed through to the LLM's temperature/seed parameters where supported.

### Scoring
The command DSL supports `add_score` effects. The generator assigns point values to puzzle solutions, lore discoveries, and optional challenges.
