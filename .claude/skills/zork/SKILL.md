---
name: zork
description: Generate a complete, playable text adventure game from a concept, or manage existing games. Delegates to the ZorkScript Author agent.
user-invocable: true
argument-hint: <game concept, or command like "publish", "list", "browse">
---

Delegate this to the ZorkScript Author agent.

**User request:** $ARGUMENTS

If the request is a game concept (a theme, setting, tone, or description), the agent should generate a complete game:
1. Read the current ZorkScript grammar from `docs/dsl/ZORKSCRIPT.md` and `docs/dsl/COMMANDS.md`
2. Read `docs/engine/GDD.md` for design principles
3. Design the game world (rooms, items, NPCs, puzzles, quests, scoring)
4. Generate all `.zorkscript` files into a project directory
5. Write the `manifest.toml`
6. Compile with `anyzork import <project-dir>`
7. Fix any validation errors
8. Report the final game to the user with instructions to play

If the request is a management task (publish, list, browse, delete, install, play), the agent should use the appropriate `anyzork` CLI command.

If no arguments are provided, ask the user what kind of game they'd like to create.
