# Roadmap

This roadmap orders open work by leverage and dependency. Each item links to a GitHub issue with full details. Checkboxes are updated automatically when issues are closed or reopened.

## 1. Harden the Core Loop

Stabilize the shipped `generate -> import -> play` pipeline before adding features.

- [x] [#8 Atomic command execution or narrowed docs](https://github.com/oobagi/anyzork/issues/8)
- [x] [#9 Split importer.py into clearer layers](https://github.com/oobagi/anyzork/issues/9)
- [x] [#10 config.toml: support full practical config surface](https://github.com/oobagi/anyzork/issues/10)
- [x] [#14 Canonical contract/alignment test suite for presets and authoring](https://github.com/oobagi/anyzork/issues/14)

## 2. Author Experience

Make it easier to write, fix, and iterate on games.

- [x] [#13 Author-facing tooling: lint, import --report, diagnostics](https://github.com/oobagi/anyzork/issues/13)
- [x] [#27 anyzork doctor: generate LLM fix-it prompt from import errors](https://github.com/oobagi/anyzork/issues/27)
- [x] [#18 Deterministic author/debug tooling: inspect, doctor, playtest/replay](https://github.com/oobagi/anyzork/issues/18)

## 3. Narrator and Provider UX

Improve the optional LLM layer and provider onboarding.

- [ ] [#11 Improve narrator/provider UX for bring-your-own-key users](https://github.com/oobagi/anyzork/issues/11)
- [ ] [#22 Narrator immersive mode](https://github.com/oobagi/anyzork/issues/22)

## 4. Packaging and Distribution

Ship the CLI as a real installable product.

- [ ] [#21 Packaging and distribution: wheels, pipx, Homebrew](https://github.com/oobagi/anyzork/issues/21)

## 5. Engine Depth

Deepen the deterministic engine with new mechanics. Each builds on a stable core.

- [ ] [#23 Quest failure states](https://github.com/oobagi/anyzork/issues/23)
- [ ] [#24 Reactive NPC triggers: theft, attacks, disposition](https://github.com/oobagi/anyzork/issues/24)
- [ ] [#25 Trap system: first-class trigger subtype](https://github.com/oobagi/anyzork/issues/25)
- [ ] [#28 General-purpose variables: set_var, change_var, var_check](https://github.com/oobagi/anyzork/issues/28)
- [ ] [#29 spawn_npc effect for dynamic NPC creation](https://github.com/oobagi/anyzork/issues/29)
- [ ] [#30 Turn-based triggers: when turn_count(N) and schedule_trigger](https://github.com/oobagi/anyzork/issues/30)
- [ ] [#19 Higher-level deterministic systems: clock triggers, NPC blockers, hints](https://github.com/oobagi/anyzork/issues/19)

## 6. NPC Systems

Advanced NPC behavior — depends on reactive triggers (#24) and variables (#28).

- [ ] [#31 NPC faction system: group hostility and mass operations](https://github.com/oobagi/anyzork/issues/31)
- [ ] [#32 NPC behavior loop: autonomous actions each turn](https://github.com/oobagi/anyzork/issues/32)

## 7. Combat

Optional turn-based combat — depends on quest failure (#23), reactive NPCs (#24), and variables (#28).

- [ ] [#26 Optional turn-based combat system](https://github.com/oobagi/anyzork/issues/26)

## 8. Catalog and Sharing

Mature the public catalog once the authoring and engine layers are solid.

- [ ] [#34 Admin UI: delete games, view/edit ZorkScript and manifest](https://github.com/oobagi/anyzork/issues/34)
- [ ] [#20 Catalog moderation and curation workflow](https://github.com/oobagi/anyzork/issues/20)

## 9. Architecture Cleanup

Larger refactors that are safe to defer until the feature surface stabilizes.

- [ ] [#15 Break up GameEngine into smaller systems](https://github.com/oobagi/anyzork/issues/15)
- [ ] [#16 Break up GameDB into domain-focused persistence layers](https://github.com/oobagi/anyzork/issues/16)
- [ ] [#17 Unify interaction responses and command effects into single rules pipeline](https://github.com/oobagi/anyzork/issues/17)
