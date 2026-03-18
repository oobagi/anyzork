# Contextual Item Placement

> Items should look right wherever they are. A baseball bat "leaning against the wall by the door" should not say that when it's lying on the kitchen floor. And dropping specific items in specific places should be able to trigger puzzles.

This document covers two related systems: contextual item descriptions (items display differently depending on where they are) and placement triggers (dropping or placing items in special locations fires game effects).

---

## Problem Statement

### Problem 1: Room descriptions follow items around

The baseball bat in the test game has this `room_description`:

> "An aluminum baseball bat leans against the wall by the door."

That sentence was written for the living room. If the player takes the bat, carries it to the kitchen, and drops it, the kitchen now says "An aluminum baseball bat leans against the wall by the door." There is no wall by any door in the kitchen. The prose is wrong and the immersion breaks.

This happens because `room_description` is a single static field. The engine has no concept of "this description was written for *this specific room*."

### Problem 2: No generic fallback

When `room_description` is NULL, the item appears in the "You see:" list with just its name. There is no middle ground -- either an item has bespoke room prose, or it gets the plain list treatment.

Dropped items deserve a short generic description. "A baseball bat lies on the ground." is better than just "baseball bat" in a noun list.

### Problem 3: No puzzle integration with item placement

Dropping an item is a dumb operation -- it moves the item to the room and prints `drop_message` or "Dropped." There is no way to wire "drop item X in room Y" to trigger a puzzle, set a flag, or advance a quest. Classic text adventure puzzles like "place the crystal on the altar" are impossible without custom DSL commands for every placement interaction.

---

## Design

### 1. Contextual Room Descriptions

#### Concept

Items track their "home room" -- the room they were originally placed in during generation. The engine uses this to decide which description to show:

- **Item is in its home room**: Display `room_description` -- the authored, atmospheric prose.
- **Item is in any other room** (dropped by player): Display `drop_description` -- a generic sentence that works anywhere.
- **Neither field exists**: Fall back to showing the item name in the "You see:" list.

#### Schema Changes

Add two columns to the `items` table:

```sql
ALTER TABLE items ADD COLUMN home_room_id TEXT REFERENCES rooms(id);
ALTER TABLE items ADD COLUMN drop_description TEXT;
```

**`home_room_id`** -- The room this item was originally generated for. Set once during generation, never modified at runtime. When the item is in this room, the engine uses `room_description`. When the item is anywhere else, the engine uses `drop_description`.

**`drop_description`** -- A short, location-agnostic prose sentence describing how the item looks when dropped on the ground by the player. Examples:

| Item | room_description (home) | drop_description (elsewhere) |
|------|------------------------|------------------------------|
| Baseball bat | "An aluminum baseball bat leans against the wall by the door." | "A baseball bat lies on the ground." |
| Bloody note | "A note pinned to the wall near the mailboxes, written in what looks like dried blood." | "A bloodstained note lies crumpled on the floor." |
| Truck keys | (NULL -- starts hidden) | "A set of keys sits on the ground." |

**Why `home_room_id` instead of just comparing `room_id` at generation time:** The item's `room_id` is mutable -- it changes every time the item moves. We need a separate, immutable field to remember where the item was designed to be. This also handles edge cases:

- Items that start in containers (`room_id = NULL`, `container_id = X`): Their `home_room_id` is the room containing the container.
- Items that start hidden (`is_visible = 0`): Their `home_room_id` is the room they will appear in when spawned.
- Items that start in inventory (`room_id = NULL`): Their `home_room_id` is NULL. They never had a home room, so `drop_description` is always used.

**What about scenery items?** Scenery items (`is_takeable = 0`) never move, so they never need `drop_description`. Their `home_room_id` always equals their `room_id`. The LLM can skip `drop_description` for scenery.

#### Engine Changes: `display_room()`

The current logic in `display_room()`:

```python
for it in items:
    rd = it.get("room_description")
    if rd:
        prose_items.append(rd)
    else:
        list_items.append(it)
```

Changes to:

```python
for it in items:
    home = it.get("home_room_id")
    if home == room_id and it.get("room_description"):
        # Item is in its authored home -- use the bespoke prose
        prose_items.append(it["room_description"])
    elif it.get("drop_description"):
        # Item is away from home (or has no home) -- use generic prose
        prose_items.append(it["drop_description"])
    else:
        # No prose at all -- fall back to name list
        list_items.append(it)
```

This is the only engine change needed for contextual descriptions. Three lines of logic replace one.

#### Edge Cases

**Item returned to home room.** If the player drops the bat in the kitchen, then picks it up and drops it back in the living room, it should show the home `room_description` again. This works naturally because the engine checks `home_room_id == room_id` on every render.

**Item with `room_description` but no `drop_description`.** The item shows authored prose in its home room and falls through to the "You see:" list everywhere else. This is acceptable for scenery (which never moves) but the generation prompt should require `drop_description` for all takeable items that have a `room_description`.

**Item with `drop_description` but no `room_description`.** The item shows the generic prose everywhere, including its home room. Unusual but valid -- maybe the item was found in a container and never had a room presence.

**Item spawned into a new room via DSL effect.** `spawn_item` places items into rooms they were not designed for. These items show `drop_description` in their spawn room (unless spawned into their `home_room_id`). This is correct behavior -- a spawned item should look generically placed unless the generator specifically designed it for that room.

**Container contents.** Items inside containers are not displayed by `display_room()` -- they are shown by the examine/search handler. `room_description` and `drop_description` are irrelevant for container contents. No changes needed.

---

### 2. Placement Triggers -- "Place Item on Target"

#### Concept

Certain locations in the game world are "receptive" to specific items. Placing the right item in the right spot triggers a game effect -- solving a puzzle, setting a flag, unlocking a door, advancing a quest.

This is not a new system. It is a pattern built entirely on the existing command DSL.

#### Why Not a New Built-in Mechanic

A dedicated placement trigger system would duplicate what the command DSL already does. The DSL can already express "when the player does X, if conditions Y are true, apply effects Z." Item placement is just another X.

The only question is: what verb does the player use?

#### The Verb Problem

Players might say any of these to place an item:

- `drop crystal`
- `put crystal on altar`
- `place crystal on altar`
- `put crystal in shrine`
- `use crystal on altar`

The engine already handles `put X in Y` and `place X in Y` as built-in container verbs (handled by `_handle_put_in`). The `drop` verb is a built-in that unconditionally moves items to the room. And `use X on Y` goes through the DSL.

The design decision: **placement puzzles use the DSL command system with `use`, `put`, or `place` verbs.** The built-in `drop` verb stays dumb -- it is a utility action, not a puzzle action. The built-in `put/place X in Y` handler is for containers only.

#### How It Works Today (Almost)

The command DSL can already express a placement puzzle:

```json
{
  "id": "place_crystal_on_altar",
  "verb": "use",
  "pattern": "use {item} on altar",
  "preconditions": [
    { "type": "has_item", "item": "red_crystal" },
    { "type": "in_room", "room": "altar_room" }
  ],
  "effects": [
    { "type": "remove_item", "item": "red_crystal" },
    { "type": "set_flag", "flag": "crystal_red_placed" },
    { "type": "add_score", "points": 10 },
    { "type": "print", "message": "You press the red crystal into the altar's socket. It clicks into place and begins to glow with an inner light." }
  ],
  "success_message": null,
  "failure_message": "You need the right crystal for the altar.",
  "one_shot": true,
  "priority": 10
}
```

This works for `use crystal on altar`. But it does not fire when the player types `put crystal on altar` or `place crystal on altar` or `drop crystal` (while standing in the altar room).

#### The Preposition Expansion: `put X on Y` / `place X on Y`

Currently, `put` and `place` are intercepted by the built-in `_handle_put_in` handler, which only understands containers. If the target is not a container, the player gets "You can't put things in that."

The design change: **Before falling through to `_handle_put_in`, the engine should check the DSL for `put` and `place` commands.** This lets the LLM define placement-puzzle commands using natural `put` and `place` verbs.

**Engine change in `main_loop()`:**

The current `put`/`place` handler:

```python
if verb in ("put", "place") and len(tokens) >= 4:
    # ... parse item and container ...
    self._handle_put_in(item_name, container_name, ...)
    continue
```

Changes to a two-step check:

```python
if verb in ("put", "place") and len(tokens) >= 4:
    # Step 1: Try DSL commands first (catches placement puzzles)
    result = resolve_command(raw, self.db)
    if result.success:
        for msg in result.messages:
            self.console.print(msg)
        self._tick()
        continue

    # Step 2: Fall through to built-in container handling
    # ... parse item and container ...
    self._handle_put_in(item_name, container_name, ...)
    continue
```

This means the LLM can generate a command like:

```json
{
  "id": "place_crystal_on_altar",
  "verb": "put",
  "pattern": "put {item} on altar",
  "preconditions": [
    { "type": "has_item", "item": "red_crystal" },
    { "type": "in_room", "room": "altar_room" }
  ],
  "effects": [
    { "type": "remove_item", "item": "red_crystal" },
    { "type": "set_flag", "flag": "crystal_red_placed" },
    { "type": "solve_puzzle", "puzzle": "crystal_altar_puzzle" },
    { "type": "print", "message": "You place the red crystal on the altar. It sinks into the stone socket and pulses with crimson light." }
  ],
  "one_shot": true,
  "priority": 10
}
```

The player types `put crystal on altar`. The engine tries the DSL first. The command matches, preconditions pass, the crystal is removed from inventory, the puzzle flag is set, and the player sees the prose. If no DSL command matches, the engine falls through to the container handler.

#### Supporting `drop` as a Placement Trigger

`drop` should remain a simple built-in verb for most cases. But what about: "The player drops the fuel can in the gas station lot, and the game should recognize this is significant"?

Two approaches:

**Approach A: The LLM generates a DSL command for `drop`.** The built-in `drop` handler would need the same "try DSL first" pattern:

```python
if verb == "drop" and len(tokens) >= 2:
    # Try DSL first (catches special drops)
    result = resolve_command(raw, self.db)
    if result.success:
        for msg in result.messages:
            self.console.print(msg)
        self._tick()
        continue
    # Fall through to built-in drop
    self._handle_drop(item_name, ...)
```

**Approach B: Use `use` or `put` instead.** The LLM designs the puzzle so the player must `use fuel can on truck` or `put fuel can in truck`, not just `drop fuel can`. The `drop` verb stays completely dumb.

**Decision: Approach A.** Both `drop` and `put`/`place` should try the DSL before falling through to built-in handling. The reason: player intent should not be gated by verb choice. If the player is standing at the altar holding the crystal and types `drop crystal`, the game should be smart enough to recognize the special drop. Otherwise the crystal ends up on the floor as a generic item and the player has to pick it up and try `put crystal on altar` instead. That is bad UX.

The DSL command for a drop-triggered placement:

```json
{
  "id": "drop_fuel_at_truck",
  "verb": "drop",
  "pattern": "drop {item}",
  "preconditions": [
    { "type": "has_item", "item": "fuel_can" },
    { "type": "in_room", "room": "gas_station_lot" }
  ],
  "effects": [
    { "type": "move_item", "item": "fuel_can", "from": "_inventory", "to": "gas_station_lot" },
    { "type": "set_flag", "flag": "truck_fueled" },
    { "type": "print", "message": "You set the fuel can next to the truck and pour the gasoline into the tank. The fumes hit you in a wave. That should be enough to get moving." }
  ],
  "one_shot": true,
  "priority": 10
}
```

Note the `priority: 10`. This is higher than a generic `drop` command, so the DSL resolver tries this specific command before any generic drop. The `in_room` precondition scopes it to the gas station lot. If the player drops the fuel can in the kitchen, the specific command's preconditions fail, the engine falls through to the built-in drop, and the can ends up on the kitchen floor with its `drop_description`.

#### Integration with the Quest System

Placement triggers integrate with quests through the flag system, exactly like every other game mechanic. The chain:

1. Player types `put crystal on altar`.
2. DSL command fires. Effects include `set_flag: crystal_red_placed`.
3. Quest tick detects that objective "Place the red crystal" has `completion_flag = crystal_red_placed`.
4. Objective is marked complete. Notification printed.
5. If all objectives for the quest are now complete, the quest completes.

No special wiring needed. The quest system observes flags. Placement commands set flags. The systems compose naturally.

#### Integration with Containers: `put X in Y`

There is a potential conflict. `put crystal in chest` should use the built-in container handler. `put crystal on altar` should use the DSL. How does the engine know the difference?

The answer is already in the design: **try DSL first, then fall through to built-in container handling.** If the LLM generated a DSL command for `put crystal on altar`, the DSL resolver matches it. If not, the engine tries `_handle_put_in`, which looks for a container. If the altar is not a container, the player gets "You can't put things in that." This is the correct fallback -- no silent confusion.

For the `on` preposition specifically: the current `_handle_put_in` only recognizes `in`, `into`, and `inside` as split words. It does not recognize `on`, `onto`, or `upon`. This means `put crystal on altar` would not even reach `_handle_put_in` today -- it would fall through to the generic DSL resolver at the bottom of `main_loop()`. So the DSL approach already works for `on`-preposition placement without any container conflict.

To make the design explicit:

| Input | Handler chain |
|-------|--------------|
| `put X in Y` | DSL first, then `_handle_put_in` (container) |
| `put X on Y` | DSL first, then `_handle_put_in` does not match (no `on` split word), then generic DSL fallback |
| `place X on Y` | Same as `put X on Y` |
| `drop X` | DSL first, then `_handle_drop` |

Adding `on`, `onto`, and `upon` to `_handle_put_in`'s split word list is a separate consideration for general container support (putting things *on top of* containers). That is out of scope for this design -- it would be a container system enhancement.

---

### 3. Generation Pipeline Changes

#### Pass 4 (Items): New Fields

The items pass prompt needs to generate two new fields per item:

**`home_room_id`** -- Set to the item's initial `room_id`. For items starting in containers, set to the room that contains the container. For items starting hidden (to be spawned later), set to the room they will appear in. For items starting in inventory (rare), set to NULL.

**`drop_description`** -- Required for all takeable items that have a `room_description`. A short, location-agnostic sentence. The prompt should instruct the LLM:

> For every takeable item with a `room_description`, also write a `drop_description` -- a short sentence describing how the item looks when lying on the ground in any generic room. This description should NOT reference any specific room features (no "by the door", "on the shelf", "near the window"). Use generic language: "lies on the ground", "sits on the floor", "rests nearby."

Example prompt addition for the items pass output schema:

```json
{
  "id": "baseball_bat",
  "name": "baseball bat",
  "description": "An aluminum baseball bat.",
  "examine_description": "An aluminum Louisville Slugger. Dented near the sweet spot.",
  "room_id": "living_room",
  "home_room_id": "living_room",
  "room_description": "An aluminum baseball bat leans against the wall by the door.",
  "drop_description": "A baseball bat lies on the ground.",
  "is_takeable": 1,
  "category": "weapon"
}
```

**Validation rules for the items pass:**

- Every takeable item with a non-null `room_description` must have a non-null `drop_description`.
- `drop_description` must not contain room-specific spatial references (heuristic check: reject if it contains "by the", "near the", "on the [furniture]", "against the").
- `home_room_id` must reference a valid room ID.
- For items in containers, `home_room_id` must match the container's room.

#### Pass 7 (Commands): Placement Commands

The commands pass already generates `use X on Y` commands for item interactions. The only change: the prompt should explicitly mention placement puzzles as a pattern.

Addition to the commands pass prompt:

> **Placement puzzles**: When the world design requires placing an item at a specific location (putting a crystal on an altar, placing an offering in a shrine, setting a key in a lock), generate commands using the `put`, `place`, or `use` verbs. Give these commands high priority (10) so they take precedence over generic drop/container handling. The preconditions should include both `has_item` and `in_room` to scope the trigger. Effects should include `remove_item` (the item is consumed by the placement), `set_flag` (to track puzzle state), and `print` (to describe what happens). If the placement solves a puzzle, include `solve_puzzle`. If it should award score, include `add_score`.
>
> For important placement interactions, generate commands for MULTIPLE verbs (`put`, `place`, `use`, and optionally `drop`) so the player's phrasing does not block them. All variants should share the same effects.

**Validation rules for placement commands:**

- Placement commands should have `priority >= 10` to take precedence over built-in handling.
- Placement commands with `verb: "drop"` must have an `in_room` precondition (otherwise they would intercept all drops of that item everywhere).
- Placement commands that remove items should use `remove_item` (item consumed by placement) or `move_item` (item placed visibly in the room).

#### Pass 8 (Quests): Placement Objectives

The quest pass already references flags set by commands. No changes needed to the quest pass specifically -- it continues to observe flags. If a placement command sets `crystal_red_placed`, and a quest objective watches for `crystal_red_placed`, the integration happens automatically.

The quest pass prompt should mention placement as a quest pattern:

> **Placement quests**: Some quests require placing items at specific locations. The objectives for these quests should reference the flags set by placement commands. Example: a quest "Restore the Altar" with objectives whose completion_flags are `crystal_red_placed`, `crystal_blue_placed`, `crystal_green_placed`.

---

### 4. Examples from the Zombie Test Game

#### Contextual Descriptions

**Baseball bat (living room)**

| Context | Description shown |
|---------|------------------|
| In living room (home) | "An aluminum baseball bat leans against the wall by the door." |
| Dropped in kitchen | "A baseball bat lies on the ground." |
| Dropped back in living room | "An aluminum baseball bat leans against the wall by the door." |

**Bloody note (building lobby)**

| Context | Description shown |
|---------|------------------|
| In lobby (home) | "A note pinned to the wall near the mailboxes, written in what looks like dried blood." |
| Dropped anywhere else | "A bloodstained note lies crumpled on the floor." |

**Truck keys (starts hidden, no home room)**

| Context | Description shown |
|---------|------------------|
| Spawned inside gas station | "A set of keys sits on the ground." (drop_description, since home_room_id is the gas station interior and they were spawned there) |
| Dropped in any room | "A set of keys sits on the ground." |

Wait -- if the truck keys' `home_room_id` is `gas_station_interior` (where they spawn), and they have no `room_description`, they would always use `drop_description` regardless of room. That is correct. The keys do not have authored room prose because they start hidden inside a container.

#### Placement Puzzle: Fuel Can + Truck

Currently, the test game uses a `use` command: `use fuel can on truck`. With the placement system, the LLM would also generate:

```json
{
  "id": "drop_fuel_at_truck",
  "verb": "drop",
  "pattern": "drop fuel can",
  "preconditions": [
    { "type": "has_item", "item": "fuel_can" },
    { "type": "in_room", "room": "gas_station_lot" }
  ],
  "effects": [
    { "type": "remove_item", "item": "fuel_can" },
    { "type": "set_flag", "flag": "truck_fueled" },
    { "type": "print", "message": "You pour the fuel into the truck's tank. The smell of gasoline fills the air." }
  ],
  "one_shot": true,
  "priority": 10
}
```

And:

```json
{
  "id": "put_fuel_on_truck",
  "verb": "put",
  "pattern": "put fuel can on truck",
  "preconditions": [
    { "type": "has_item", "item": "fuel_can" },
    { "type": "in_room", "room": "gas_station_lot" }
  ],
  "effects": [
    { "type": "remove_item", "item": "fuel_can" },
    { "type": "set_flag", "flag": "truck_fueled" },
    { "type": "print", "message": "You pour the fuel into the truck's tank. The smell of gasoline fills the air." }
  ],
  "one_shot": true,
  "priority": 10
}
```

Three verb variants (`use`, `put`, `drop`) all do the same thing. The player cannot get stuck because of verb choice.

---

### 5. Summary of All Changes

#### Schema

| Change | Table | Column | Type |
|--------|-------|--------|------|
| Add column | `items` | `home_room_id` | `TEXT REFERENCES rooms(id)` |
| Add column | `items` | `drop_description` | `TEXT` |

Both columns are nullable. `home_room_id` is NULL for items that start in inventory or have no meaningful home room. `drop_description` is NULL for scenery items that never move.

#### Engine: `display_room()` in `game.py`

Replace the single `room_description` check with the three-tier logic: home room prose, generic drop prose, name list fallback.

#### Engine: `main_loop()` in `game.py`

For `drop`, `put`, and `place` verbs: try DSL command resolution before falling through to built-in handlers. This is a small change -- add `resolve_command()` calls before the existing built-in handler calls.

#### Generation Pipeline: Pass 4 (Items)

- Prompt instructs LLM to generate `home_room_id` and `drop_description` for every takeable item.
- Validation checks that takeable items with `room_description` also have `drop_description`.
- Validation checks that `drop_description` does not contain room-specific spatial references.

#### Generation Pipeline: Pass 7 (Commands)

- Prompt includes placement puzzle pattern guidance.
- Prompt encourages multi-verb variants for important placement interactions.
- Validation checks that `drop`-verb placement commands include `in_room` preconditions.

#### Test Game: `build_test_game.py`

- Add `home_room_id` to every item (matches initial `room_id` for room items, parent room for container items).
- Add `drop_description` to every takeable item that has a `room_description`.
- Add placement trigger commands for the fuel can puzzle (multi-verb variants).

#### Documentation

- Update `docs/game-design/world-schema.md` to document `home_room_id` and `drop_description`.
- Update `docs/architecture/generation-pipeline.md` Pass 4 output schema to include new fields.
- Update `docs/dsl/command-spec.md` to document the placement puzzle pattern.

---

### 6. Implementation Phasing

This does not warrant a new phase. It fits cleanly into two existing scopes:

**Contextual descriptions** -- This is a direct extension of Phase 2b (Dynamic Room Descriptions). Phase 2b established the `room_description` field and the engine pattern. This design adds `drop_description` and `home_room_id` as refinements. The implementation is small: one schema migration, three lines of engine logic, and test game updates.

**Placement triggers** -- This is a refinement of the existing DSL command system. No new tables, no new effect types, no new precondition types. The only engine change is reordering the handler chain to check DSL before built-in verbs for `drop`/`put`/`place`. This could be done as part of any pass that touches the command resolver.

Suggested order:

1. Schema change + engine display logic + test game updates (contextual descriptions).
2. Engine handler chain reorder (DSL-first for `drop`/`put`/`place`).
3. Generation prompt updates (Pass 4 and Pass 7).
4. Documentation updates.

All four steps are small. Total scope: roughly one focused session of work.

---

### 7. Tuning and Balance Notes

**`drop_description` quality.** The generic drop descriptions are intentionally less atmospheric than `room_description`. This is by design -- they signal to the player that this item is out of place. "A baseball bat lies on the ground" is less immersive than "An aluminum baseball bat leans against the wall by the door" because the bat *is* less immersed. It is displaced. The tonal difference is a feature, not a bug.

**Placement command verb coverage.** The LLM should generate placement commands for at least two verbs (`use` + one of `put`/`place`). Generating all four (`use`, `put`, `place`, `drop`) is ideal for critical-path puzzles but may be overkill for optional side puzzles. The generation prompt should prioritize verb coverage for critical-path placements and allow fewer variants for optional content.

**Priority values for placement commands.** [PLACEHOLDER] -- `priority: 10` is the initial value. Playtest to verify this reliably beats generic drop/put handling without interfering with non-placement uses of those verbs. If a game has both a "drop" placement command and a regular "drop" DSL command for the same item, the higher-priority placement command should always win when the room precondition is met.

**`drop_description` for containers.** Container items (`is_container = 1`) that are also takeable could theoretically be dropped in other rooms. Their `drop_description` should describe the container as an object, not its contents: "A wooden chest sits on the ground." Contents are shown separately via the examine/search handler. In practice, most containers are scenery (`is_takeable = 0`) and this case rarely arises.
