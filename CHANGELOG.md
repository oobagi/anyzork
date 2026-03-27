# Changelog

All notable changes to AnyZork are documented here, grouped by roadmap phase.

## Phase 9 — Architecture Cleanup

- Unify interaction responses and command effects into single rules pipeline (#17)
- Break up GameDB into domain-focused persistence layers (#16)
- Break up GameEngine into smaller systems (#15)

## Phase 8 — Catalog and Sharing

- Catalog moderation and curation workflow (#20)
- Admin UI: delete games, view/edit ZorkScript and manifest (#34)

## Phase 7 — Combat

- Optional turn-based combat system (#26)

## Phase 6 — NPC Systems

- NPC behavior loop: autonomous actions each turn (#32)
- NPC faction system: group hostility and mass operations (#31)

## Phase 5 — Engine Depth

- Higher-level deterministic systems: NPC blockers and hints (#19)
- Turn-based triggers: turn_count(N) and schedule_trigger (#30)
- spawn_npc effect for dynamic NPC creation (#29)
- General-purpose variables: set_var, change_var, var_check (#28)
- Reactive NPC triggers: theft, attacks, disposition (#24)
- Trap system: first-class trigger subtype (#25)
- Quest failure states with failure_flag, fail_message, and status guards (#23)

## Phase 4 — Packaging and Distribution

- Packaging and distribution via PyPI (#21)

## Phase 3 — Narrator and Provider UX

- Narrator immersive mode (#22)
- Interactive narrator/provider setup wizard (#11)

## Phase 2 — Author Experience

- Game projects, multi-file archives, and anyzork doctor (#27)
- Author-facing tooling: lint, import --report, diagnostics (#13)
- Deterministic author/debug tooling: doctor, health checks (#18)
- Publisher self-service with email OTP authentication (#57)
- Game ref ergonomics: prefix matching, numeric indices (#59)
- CLI audit: fix docs, extract UI helpers, unify patterns (#67)

## Phase 1 — Harden the Core Loop

- Atomic command execution (#8)
- Split importer.py into layered sub-package (#9)
- Full practical config surface in config.toml (#10)
- Contract/alignment test suite for presets and authoring (#14)

## Initial Release

- ZorkScript DSL: human-readable authoring language for text adventures
- Deterministic engine: rooms, items, NPCs, exits, commands, triggers, dialogue trees
- `anyzork generate`: freeform and wizard-guided prompt builder with genre presets
- `anyzork import`: compile ZorkScript into portable .zork archives
- `anyzork play`: deterministic runtime with save slots and named saves
- Optional narrator mode: Claude, OpenAI, and Gemini support
- Catalog API: publish, browse, and install games
- Rich CLI: tables, panels, color, interactive menus
