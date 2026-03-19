# AnyZork Design Brief

## The Problem

Using an LLM to run a text adventure in real time fails in the same ways over and over:

1. Context loss: the model forgets rooms, items, flags, and prior conversations.
2. State inconsistency: it lets the player do things that should be impossible.
3. World drift: descriptions, puzzle logic, and NPC behavior change over time.

The core issue is role overload. A single model is trying to be the world database, the game engine, and the narrator at once.

## The Solution

Split the system into two phases:

1. The LLM generates a world as structured data: rooms, exits, locks, items, NPCs, interaction rules, puzzles, commands, quests, and triggers. That data is stored in a portable SQLite `.zork` file.
2. A deterministic engine runs the game: it reads the database, evaluates DSL rules, applies state changes, and renders output consistently.

The LLM is used once for creativity. The engine handles all runtime state.

## Why a DSL Instead of Generated Code

Commands are stored as structured precondition/effect rules instead of generated Python:

```text
verb: "use"
pattern: "use {item} on {target}"
preconditions: [player has "rusty_key", player in "dungeon_entrance"]
effects: [remove "rusty_key", unlock "dungeon_door", print "The door creaks open..."]
```

This keeps runtime deterministic, auditable, and safe. The model can compose valid mechanics, but it cannot invent arbitrary executable behavior.

## Why Multi-Pass Generation

A whole game generated in one call is fragile. AnyZork breaks generation into focused passes so each step can validate and retry independently.

Current pipeline:

1. World concept
2. Room graph
3. Locks and gates
4. Items
5. NPCs and dialogue
6. Interaction responses
7. Puzzles
8. Commands
9. Quests
10. Triggers
11. Validation

This keeps prompts smaller, reduces cascading failures, and makes retries cheap.

## Why SQLite

A single `.zork` file is a complete game and a save file:

- Portable: copy it, share it, archive it.
- Transactional: generation passes can commit or roll back cleanly.
- Relational: rooms, exits, items, quests, and triggers reference each other safely.
- Fast enough: the game world is small, but lookups still benefit from indexes.

## Narrator Mode

Narrator mode is an optional read-only LLM layer on top of deterministic output. It can rewrite presentation, but it cannot change state, outcomes, inventory, exits, or quest progress.

If narrator mode fails, the deterministic engine output is still enough to play.

## Provider Strategy

The generator and narrator both use the same provider abstraction. Today the supported providers are:

- Claude
- OpenAI
- Gemini

Users bring their own API keys. Provider choice is configuration, not architecture.

## Additional Features

### Save/Load

The `.zork` file is the save. Runtime tables track room position, inventory, health, score, moves, quest status, flags, and trigger execution state.

### Seed System

The same prompt plus the same seed should produce the same world shape, subject to provider/model determinism.

### Scoring

The DSL supports `add_score`, and the engine records score events deterministically. Typical score sources are puzzle solutions, optional discoveries, quest completion, and bonus objectives.
