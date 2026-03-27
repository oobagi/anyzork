# Changelog

All notable changes to AnyZork are documented here, grouped by roadmap phase.

## Phase 14 — Public Landing Page

- Static asset serving: favicon, OG meta tags, StaticFiles mount (#125)
- Wire landing page into FastAPI: GET / serves HTML, GET /api for descriptor (#124)
- Landing page with catalog browser, hero, how-it-works, install (#123)

## Phase 13 — Admin Dashboard: Polish

- Keyboard shortcuts: Cmd/Ctrl+K, Escape, R (#122)
- Loading skeletons and context-aware empty states (#121)
- Confirm dialog: variant prop, Enter/Escape keyboard support (#120)
- Toast notifications replacing all alert() calls (#119)

## Phase 12 — Admin Dashboard: Metadata Editing

- Inline metadata editor with save/cancel (#118)
- Admin metadata PATCH endpoint without status reset (#117)

## Phase 11 — Admin Dashboard: Bulk Operations

- Bulk feature/unfeature endpoint and UI (#116)
- Bulk approve/reject/delete with per-slug results (#115)

## Phase 10 — Admin Dashboard: Display & Navigation

- Review queue view with pending count badge and FIFO sort (#114)
- Sort controls: 6 options applied client-side after search/filter (#113)
- Client-side text search with debounce across all game fields (#112)
- Improved stats bar: all status counts, clickable filter shortcuts (#111)
- Rich game detail panel with full metadata grid (#110)

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
