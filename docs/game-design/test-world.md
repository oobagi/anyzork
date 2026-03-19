# The Lantern Archive

The Lantern Archive is the single official AnyZork human-testing world.

It is a compact archive-and-observatory scenario built to exercise the current deterministic feature set in one playable fixture:
- key lock: `workshop_lock`
- locked container: `archive_case`
- nested container flow: `archive_case` -> `tool_satchel` -> `repair_coil`
- container whitelist rejection: `tool_satchel` only accepts `repair_coil`
- dark room: `black_stacks`
- toggleable + required-item flow: `field_lantern` + `battery_pack`
- quantity-backed items: `battery_pack`, `chalk_stick`
- dialogue tree and dialogue-triggered rewards: Curator Rowan, `trigger_issue_badge`
- trigger-driven state lock unlock: `observatory_lock`
- interaction responses: chalk-on-mural reveal, generic light-source response
- main + side quests with deterministic completion flags
- world-specific commands: `install repair coil`, `study mural`, `calibrate lens`

Room graph:

```text
Entrance Hall <-> Workshop
Entrance Hall <-> Black Stacks <-> Generator Room
Entrance Hall <-> Observatory
```

Progression:
1. Meet Curator Rowan in `entrance_hall`.
2. Take the `brass_key` and unlock the workshop.
3. Reach the `archive_case`, recover the `tool_satchel`, and extract the `repair_coil`.
4. Use the lantern and chalk to explore `black_stacks` and reveal the mural.
5. Trigger Rowan's badge branch to receive the `archive_badge` and `crate_key`.
6. Install the repair coil in `generator_room` to restore power.
7. Once `badge_received` and `power_restored` are both true, the observatory unlocks.
8. Enter `observatory` and optionally calibrate the lens.

This world replaces the older gun-range-style fixture and should be treated as the only hand-authored test-world source of truth.
