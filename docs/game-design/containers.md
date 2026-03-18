# Container System Design

> Containers are items that hold other items. A chest, a drawer, a glovebox, a backpack. The player discovers them in a room, opens or searches them, and finds items inside. This document specifies the full container mechanic: player-facing behavior, schema changes, engine changes, generation pipeline updates, and a worked example (the Car).

---

## 1. Design Goals

### What problem this solves

The current item system is flat. Every item sits directly in a room or in the player's inventory. There is no concept of "an item inside another item." This limits world-building in two important ways:

1. **Discovery pacing.** Without containers, every item in a room is immediately visible. The player sees everything at once. Containers let the designer hide items behind an interaction step -- the player must search the desk, open the chest, look under the seat. This creates micro-discoveries that sustain moment-to-moment engagement.

2. **Spatial plausibility.** Real spaces have containers. A kitchen has drawers. A car has a glovebox. A desk has a drawer. Without containers, items float in rooms without spatial grounding. Containers let the LLM generate worlds that feel furnished and logical.

### Design pillars this serves

- **Discoverable depth** (Pillar 2): Containers add a layer of exploration within rooms. The player who searches thoroughly finds more than the player who rushes through.
- **Fair challenge** (Pillar 3): Items hidden in containers are still findable. The container is visible in the room. Searching it is a natural verb. No pixel hunts.
- **Deterministic integrity** (Pillar 1): Container state (open/closed/locked) is stored in SQLite. The engine evaluates it deterministically. No LLM at runtime.

### What this does NOT add

- **Nesting.** Containers cannot hold other containers. A bag inside a chest is out of scope. This avoids recursive complexity in the engine, the schema, and the generation prompts. If a future design requires nesting, it can be added as a separate pass, but the v1 container system explicitly forbids it.
- **Capacity limits.** Containers have no weight or slot limit. They hold whatever the LLM puts in them. This keeps the mechanic simple and avoids tedious inventory management.
- **Player-created containers.** The player cannot designate an arbitrary item as a container. Containers are authored by the LLM at generation time.

---

## 2. Player-Facing Mechanics

### 2.1 Discovery

Containers are items. They appear in the room exactly like any other item -- either in the "You see:" list or via a `room_description` prose sentence woven into the room text. The player knows a container exists the same way they know any item exists: by entering the room.

The container's `description` (the short text shown in room listings) should hint that it can be searched. Examples:
- "a wooden chest with iron hinges"
- "a cluttered desk with drawers"
- "the car's glovebox, latched shut"

The container's `examine_description` should explicitly state it can be opened or searched:
- "The chest is old but sturdy. The lid is closed. You could open it or search inside."
- "The glovebox latch is stiff but functional. You could open it."

### 2.2 Opening / Searching

The player interacts with containers using these verbs:

| Input | Behavior |
|-------|----------|
| `open <container>` | Opens the container if closed. If locked, shows the lock message. If already open, says so. |
| `search <container>` | If the container is open (or has no lid -- see below), lists its contents. If closed, opens it first then lists contents. If locked, shows the lock message. |
| `look in <container>` | Synonym for `search`. |
| `examine <container>` | Shows the container's examine_description. If the container is open, also lists its contents. |

**Open vs. search distinction:**
- `open` changes the container's state from closed to open. It prints the open message but does not list contents unless the container was already open.
- `search` / `look in` is the "show me what's inside" verb. It implicitly opens a closed container first, then lists contents.
- Some containers have no lid (a shelf, a pile of clothes, "under the seat"). These are always considered open. Searching them works immediately with no open step.

**The "always-open" container:**
Not all containers have a meaningful open/close state. A bookshelf, a pile of rubble, the space under a car seat -- these are always searchable. The schema supports this via `is_open = 1` at creation time combined with a flag `has_lid = 0` that tells the engine this container cannot be opened or closed -- it just is.

### 2.3 Taking Items from Containers

| Input | Behavior |
|-------|----------|
| `take <item> from <container>` | Takes the item from inside the container and adds it to inventory. The container must be open. The item must be takeable. |
| `take <item>` | If the item is inside an open container in the current room, this also works. The engine searches open containers when the item is not found directly in the room. |

**Disambiguation:** If an item name matches both a room item and a container item, the room-level item wins. The player can use `take <item> from <container>` to be explicit.

### 2.4 Putting Items into Containers

| Input | Behavior |
|-------|----------|
| `put <item> in <container>` | Moves an inventory item into the container. The container must be open. |

This is a secondary verb. It exists for completeness and for puzzle support (a puzzle might require placing an item inside a specific container), but it is not a core exploration mechanic. The engine should support it; the generation pipeline does not need to generate games that require it unless a puzzle demands it.

### 2.5 Locked Containers

Containers can be locked. A locked container cannot be opened or searched until unlocked.

**How locking works:**
- The container has `is_locked = 1` in the database.
- The container has a `lock_message` field: text shown when the player tries to open/search a locked container.
- Unlocking uses the existing lock/key infrastructure. A lock row in the `locks` table can reference a container item via a new `target_container_id` field (see Schema Changes below). The player uses a key item on the container, or a DSL command unlocks it.
- Once unlocked, `is_locked` is set to `0` and the container behaves normally.

**Verb behavior with locked containers:**

| Input | Locked behavior |
|-------|-----------------|
| `open <container>` | Prints `lock_message` |
| `search <container>` | Prints `lock_message` |
| `look in <container>` | Prints `lock_message` |
| `examine <container>` | Shows examine_description (which should mention the lock) |
| `use <key> on <container>` | Handled by DSL command: unlocks the container |
| `open <container> with <key>` | Handled by DSL command: unlocks and opens |

### 2.6 Room Display with Containers

**Items inside closed containers are invisible.** They do not appear in the room's "You see:" list. They do not appear in the room description. They exist in the database but are hidden from the player until the container is opened and searched.

**Items inside open containers are semi-visible.** They appear when the player searches the container, but they do NOT appear in the room's top-level "You see:" list. The container itself appears in the "You see:" list. The player must interact with the container to discover its contents.

**When a container is opened or searched, the engine displays:**

```
You open the wooden chest.

Inside the chest:
  - a brass key
  - a rolled parchment
  - a handful of coins
```

If the container is empty:

```
You search the glovebox. It's empty.
```

### 2.7 Examining a Container

When the player examines a container, the output includes:
1. The container's `examine_description` (as with any item).
2. If the container is open and non-empty: "Inside, you see: [item list]."
3. If the container is open and empty: "It's empty."
4. If the container is closed: "It is currently closed."
5. If the container is locked: "It is locked." (already covered by examine_description, but the engine should add this if the description doesn't mention it).

---

## 3. Schema Changes

### 3.1 Items Table: New Columns

Add the following columns to the `items` table:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `is_container` | INTEGER | 0 | `1` if this item can hold other items. `0` for normal items. |
| `container_id` | TEXT REFERENCES items(id) | NULL | If this item is inside a container, the ID of the containing item. `NULL` means the item is in a room or inventory (existing behavior). |
| `is_open` | INTEGER | 0 | For containers: `1` = open, `0` = closed. Ignored for non-containers. |
| `has_lid` | INTEGER | 1 | For containers: `1` = can be opened/closed. `0` = always accessible (a shelf, a pile, "under the seat"). Ignored for non-containers. |
| `is_locked` | INTEGER | 0 | For containers: `1` = locked (cannot open until unlocked). `0` = not locked. Ignored for non-containers. |
| `lock_message` | TEXT | NULL | For locked containers: message shown when the player tries to open/search while locked. |
| `open_message` | TEXT | NULL | For containers: message shown when the container is opened. If NULL, engine uses default: "Opened." |
| `search_message` | TEXT | NULL | For containers: message shown before listing contents when searched. If NULL, engine constructs a default. |

### 3.2 Items Table: Updated Schema SQL

```sql
CREATE TABLE IF NOT EXISTS items (
    id                  TEXT PRIMARY KEY,
    name                TEXT    NOT NULL,
    description         TEXT    NOT NULL,
    examine_description TEXT    NOT NULL,
    room_id             TEXT    REFERENCES rooms(id),
    container_id        TEXT    REFERENCES items(id),  -- NEW
    is_takeable         INTEGER NOT NULL DEFAULT 1,
    is_visible          INTEGER NOT NULL DEFAULT 1,
    is_consumed_on_use  INTEGER NOT NULL DEFAULT 0,
    is_container        INTEGER NOT NULL DEFAULT 0,    -- NEW
    is_open             INTEGER NOT NULL DEFAULT 0,    -- NEW
    has_lid             INTEGER NOT NULL DEFAULT 1,    -- NEW
    is_locked           INTEGER NOT NULL DEFAULT 0,    -- NEW
    lock_message        TEXT,                          -- NEW
    open_message        TEXT,                          -- NEW
    search_message      TEXT,                          -- NEW
    take_message        TEXT,
    drop_message        TEXT,
    weight              INTEGER DEFAULT 1,
    category            TEXT,
    room_description    TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_room_id      ON items(room_id);
CREATE INDEX IF NOT EXISTS idx_items_container_id  ON items(container_id);  -- NEW
```

### 3.3 Location Model Update

Currently, an item's location is determined by `room_id`:
- `room_id = <room_id>` means the item is in that room.
- `room_id = NULL` means the item is in the player's inventory (if visible) or unspawned (if not visible).

With containers, location gains a third state:
- `room_id = NULL` AND `container_id = <item_id>` means the item is inside a container.
- `room_id` and `container_id` are mutually exclusive. An item is in a room, in inventory, or in a container -- never more than one.

**Constraint:** An item MUST NOT have both `room_id` and `container_id` set simultaneously. The engine should enforce this. A CHECK constraint in the schema can catch it:

```sql
CHECK (NOT (room_id IS NOT NULL AND container_id IS NOT NULL))
```

**Container location:** A container item itself has a `room_id` (it sits in a room) or `room_id = NULL` (it's in inventory -- a bag the player carries). Containers in inventory are searchable from anywhere.

### 3.4 Locks Table: Container Lock Support

Add an optional column to the `locks` table:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `target_container_id` | TEXT REFERENCES items(id) | NULL | If this lock gates a container instead of an exit. Mutually exclusive with `target_exit_id` -- one must be set, not both. |

Alternatively, container locking can be handled entirely through the `is_locked` field on the item itself, with DSL commands handling the unlock logic (a `use key on chest` command that sets `is_locked = 0`). This avoids modifying the locks table.

**Recommended approach:** Use the item-level `is_locked` field plus DSL commands. This is simpler and more consistent with how the engine already handles item interactions through the command DSL. The `locks` table remains exit-only. Container unlocking is handled by:
1. A DSL command with pattern `use {item} on {target}` or `open {target} with {item}`.
2. Preconditions: `has_item` for the key, `item_in_room` for the container.
3. Effects: a new effect type `open_container` (see Engine Changes), plus optionally `remove_item` to consume the key.

### 3.5 New Effect Type: `open_container`

Add to the Command DSL effect types:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"open_container"` |
| `container` | string | yes | The item ID of the container to unlock and open. Supports `{slot}` references. |

```json
{
  "type": "open_container",
  "container": "locked_chest"
}
```

This effect sets `is_locked = 0` and `is_open = 1` on the target container item. It is the canonical way to unlock a container via a DSL command.

### 3.6 New Precondition Type: `container_open`

Add to the Command DSL precondition types:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"container_open"` |
| `container` | string | yes | The item ID of the container that must be open. Supports `{slot}` references. |

```json
{
  "type": "container_open",
  "container": "old_desk_drawer"
}
```

This allows commands to gate on whether a container has been opened. Useful for puzzles where opening a container is a prerequisite for a subsequent action.

### 3.7 New Effect Type: `move_item_to_container`

Add to the Command DSL effect types:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"move_item_to_container"` |
| `item` | string | yes | The item ID to place inside the container. Supports `{slot}` references. |
| `container` | string | yes | The container item ID. Supports `{slot}` references. |

```json
{
  "type": "move_item_to_container",
  "item": "gem",
  "container": "jewel_box"
}
```

This effect sets `container_id = <container>` and `room_id = NULL` on the target item. Used for puzzle commands where the player must place an item inside a container.

---

## 4. Engine Changes

### 4.1 Room Display: Filter Out Container Contents

**Current behavior:** `get_items_in("room", room_id)` returns all visible items with `room_id = <room_id>`.

**New behavior:** This query must also exclude items where `container_id IS NOT NULL`. Items inside containers are not "in the room" from the player's perspective -- they are inside the container.

Updated query:
```sql
SELECT * FROM items
WHERE room_id = ? AND is_visible = 1 AND container_id IS NULL
```

This one change ensures that items inside containers never appear in the room's "You see:" list.

### 4.2 New Verb: `search` / `look in`

Add a new built-in verb handler for `search <target>` and `look in <target>`.

**Algorithm:**

1. Find the target item in the current room (by name, using existing fuzzy matching).
2. If not found, print "You don't see that here."
3. If found but `is_container = 0`, print "There's nothing to search." (or fall through to DSL).
4. If found and `is_container = 1`:
   a. If `is_locked = 1`: print `lock_message` (or "It's locked.").
   b. If `is_open = 0` and `has_lid = 1`: open it first. Set `is_open = 1`. Print `open_message` (or "You open the [name].").
   c. Query items where `container_id = <container_id>` and `is_visible = 1`.
   d. If items found: print `search_message` (or "Inside the [name]:") followed by a bulleted list of item names.
   e. If no items: print "It's empty."

**Verb registration:**

```
search <target>       -> _handle_search(target_name, current_room_id)
look in <target>      -> _handle_search(target_name, current_room_id)
look inside <target>  -> _handle_search(target_name, current_room_id)
```

The parser should recognize these patterns:
- `search X` -- tokens[0] == "search", target = tokens[1:]
- `look in X` -- tokens[0] == "look", tokens[1] == "in", target = tokens[2:]
- `look inside X` -- tokens[0] == "look", tokens[1] == "inside", target = tokens[2:]

### 4.3 Modified Verb: `open`

The existing `_handle_open` method currently only handles locked exits. It must be extended to also handle containers.

**Algorithm (updated):**

1. (Existing) Check if the target matches a locked exit direction. If so, handle as before.
2. (New) If no exit matched, find the target item in the current room.
3. If found and `is_container = 1`:
   a. If `is_locked = 1`: print `lock_message`.
   b. If `is_open = 1`: print "It's already open."
   c. If `has_lid = 0`: print "It doesn't need to be opened." (always-accessible container).
   d. Otherwise: set `is_open = 1`, print `open_message` (or "You open the [name].").
4. If found but `is_container = 0`: print "You can't open that." (or fall through to DSL).

### 4.4 Modified Verb: `take`

The existing `_handle_take` method searches for items in the room. It must be extended to also search inside open containers.

**Algorithm (updated):**

1. (Existing) Search for the item in the current room by name. If found, take it as before.
2. (New) If not found in the room, search inside open containers in the current room:
   a. Get all container items in the current room where `is_container = 1` and (`is_open = 1` or `has_lid = 0`).
   b. For each open container, search its contents for the item name.
   c. If found, take the item from the container (set `container_id = NULL`, `room_id = NULL` for inventory).
   d. Print a contextual message: "Taken (from the [container name])."
3. If not found in any open container either, proceed with existing behavior (check inventory, print "You don't see that here.").

### 4.5 New Verb: `take <item> from <container>`

Add parsing for the `take X from Y` pattern.

**Pattern recognition:**

Parse `take <words> from <words>` by splitting on the word "from":
- tokens[0] == "take" (or "get")
- Find the index of "from" in tokens
- item_name = tokens[1:from_index]
- container_name = tokens[from_index+1:]

**Algorithm:**

1. Find the container in the current room by name. If not found, try inventory (for portable containers like bags).
2. If not found or `is_container = 0`: print "That's not a container."
3. If `is_locked = 1`: print `lock_message`.
4. If `is_open = 0` and `has_lid = 1`: print "You need to open it first." (do NOT auto-open on explicit `take from` -- the player was specific, so be specific back).
5. Search the container's contents for the item name.
6. If found and `is_takeable = 1`: move to inventory. Print take_message or "Taken."
7. If found but not takeable: print "You can't take that."
8. If not found: print "You don't see that in the [container name]."

### 4.6 New Verb: `put <item> in <container>`

**Pattern recognition:**

Parse `put <words> in <words>` by splitting on "in":
- tokens[0] == "put" (or "place")
- Find the index of "in" or "into" or "inside" in tokens
- item_name = tokens[1:split_index]
- container_name = tokens[split_index+1:]

**Algorithm:**

1. Find the item in inventory. If not found: print "You're not carrying that."
2. Find the container in the current room or inventory. If not found: print "You don't see that here."
3. If `is_container = 0`: print "You can't put things in that."
4. If `is_locked = 1`: print `lock_message`.
5. If `is_open = 0` and `has_lid = 1`: print "You need to open it first."
6. Move the item: set `room_id = NULL`, `container_id = <container_id>`.
7. Print "You put the [item name] in the [container name]."

### 4.7 Modified Verb: `examine`

The existing `_handle_examine` method should be updated so that when examining a container, it also reports the container's state and contents.

**Additions to examine output for containers:**

After printing the `examine_description`, if `is_container = 1`:
- If `is_locked = 1`: append "It is locked."
- If `is_open = 0` and `has_lid = 1` and `is_locked = 0`: append "It is closed."
- If `is_open = 1` or `has_lid = 0`:
  - Get contents (items where `container_id = <this item's id>` and `is_visible = 1`).
  - If contents exist: append "Inside, you see: [comma-separated item names]."
  - If empty: append "It's empty."

### 4.8 GameDB: New Query Methods

Add the following methods to `GameDB`:

**`get_container_contents(container_id: str) -> list[dict]`**
```sql
SELECT * FROM items WHERE container_id = ? AND is_visible = 1
```

**`open_container(container_id: str) -> None`**
```sql
UPDATE items SET is_open = 1, is_locked = 0 WHERE id = ?
```

**`move_item_to_container(item_id: str, container_id: str) -> None`**
```sql
UPDATE items SET room_id = NULL, container_id = ? WHERE id = ?
```

**`take_item_from_container(item_id: str) -> None`**
```sql
UPDATE items SET container_id = NULL, room_id = NULL WHERE id = ?
```
(Sets to inventory -- room_id NULL, container_id NULL, is_visible stays 1.)

**`get_open_containers_in_room(room_id: str) -> list[dict]`**
```sql
SELECT * FROM items
WHERE room_id = ? AND is_container = 1 AND is_visible = 1
  AND (is_open = 1 OR has_lid = 0)
  AND is_locked = 0
```

### 4.9 Help Text Update

Add the following to the help output:

```
  search / look in {container}  -- search inside a container
  take {item} from {container}  -- take something from a container
  put {item} in {container}     -- put something into a container
```

---

## 5. Generation Pipeline Changes

### 5.1 No New Pass Required

Containers are items. They are generated in **Pass 4 (Items)**. The items pass prompt needs additional guidance, not a separate pass.

### 5.2 Pass 4 Prompt Additions

Add the following section to the Pass 4 (Items) LLM prompt:

---

**Container items:**

Some items are containers -- objects that hold other items inside them. Chests, drawers, bags, desks, gloveboxes, shelves, piles of debris.

When creating a container:
- Set `is_container: true`
- Set `has_lid: true` if it can be meaningfully opened/closed (a chest, a drawer, a glovebox). Set `has_lid: false` if it's always accessible (a shelf, a pile, "under the seat").
- Set `is_open: false` for lidded containers (player must open or search them). Set `is_open: true` for lid-less containers.
- Set `is_locked: true` if the container should require a key or puzzle to open. Provide a `lock_message`. Also create a DSL command (in Pass 7) that unlocks it.
- Set `is_takeable: false` for most containers (they are furniture/fixtures). Set `is_takeable: true` only for portable containers like bags or satchels.
- Write the `examine_description` to hint that the container can be searched: "You could look inside" or "It might be worth searching."
- Container items have `room_id` set to the room they're in, like any item.

When creating items inside a container:
- Set `container_id` to the container item's ID.
- Set `room_id` to NULL (the item is inside the container, not in the room).
- These items are hidden from the player until the container is opened and searched.
- Items inside containers should still have full descriptions and examine_descriptions.

**Container placement guidelines:**
- Use containers to hide items that the player should discover through active exploration, not passively by entering a room.
- Key items (items needed for puzzle solutions or lock-opening) MAY be inside containers, but the container must be clearly visible and obviously searchable. Never hide a critical-path key inside a locked container that requires another critical-path key.
- Containers add room-level depth. A room with 2-3 visible items and 1-2 containers (each holding 1-3 items) feels richer than a room with 5-6 visible items.
- Locked containers are mini-puzzles. Use them sparingly -- one or two per game, not one per room.

**Nesting prohibition:**
- A container MUST NOT be placed inside another container. `container_id` must never reference an item where `is_container = 1`. This is a hard rule -- the engine does not support nested containers.

---

### 5.3 Pass 7 (Commands) Prompt Additions

For locked containers, the LLM must also generate the DSL commands that unlock them. Add to the Pass 7 prompt:

---

**Container unlock commands:**

For each locked container, create a command that unlocks it:

```json
{
  "id": "unlock_locked_chest_with_brass_key",
  "verb": "use",
  "pattern": "use {item} on {target}",
  "preconditions": [
    { "type": "has_item", "item": "brass_key" },
    { "type": "item_in_room", "item": "locked_chest", "room": "_current" }
  ],
  "effects": [
    { "type": "open_container", "container": "locked_chest" },
    { "type": "remove_item", "item": "brass_key" },
    { "type": "set_flag", "flag": "chest_unlocked" },
    { "type": "print", "message": "The brass key turns in the lock with a satisfying click. The chest lid swings open." }
  ],
  "one_shot": true
}
```

Also create an `open <container> with <key>` variant:

```json
{
  "id": "open_locked_chest_with_brass_key",
  "verb": "open",
  "pattern": "open {target} with {item}",
  "preconditions": [
    { "type": "has_item", "item": "brass_key" },
    { "type": "item_in_room", "item": "locked_chest", "room": "_current" }
  ],
  "effects": [
    { "type": "open_container", "container": "locked_chest" },
    { "type": "remove_item", "item": "brass_key" },
    { "type": "set_flag", "flag": "chest_unlocked" },
    { "type": "print", "message": "You fit the brass key into the lock and turn. The chest opens." }
  ],
  "one_shot": true
}
```

---

### 5.4 Validation Additions

Add the following checks to the post-Pass-4 validation:

- Every item with `container_id` set must reference a valid item where `is_container = 1`.
- No item with `is_container = 1` may have a `container_id` set (no nesting).
- Every item with `container_id` set must have `room_id = NULL`.
- Every container with `is_locked = 1` must have a `lock_message`.
- Every locked container must have a corresponding unlock command in the commands table (checked after Pass 7).
- The unlock command's key item must be reachable without first opening the locked container (no circular dependency).

---

## 6. Worked Example: The Car

The user wants a car that the player can enter and explore, with multiple searchable areas containing hidden items.

### 6.1 Spatial Model

The car is modeled as a **room** (not a container). The player "enters" the car from the street/parking lot via an exit. Inside the car room, the searchable areas are **container items**.

```
[Street / Parking Lot]
        |
     (enter car / exit)
        |
   [Inside the Car]  <-- Room. Contains container items.
```

The car room has exits:
- `exit` / `out` -- returns to the street/parking lot.
- No compass directions inside the car (it would be weird to go "north" inside a car).

### 6.2 Room Definition

```json
{
  "id": "inside_car",
  "name": "Inside the Car",
  "description": "You're sitting in the driver's seat of a beat-up sedan. The vinyl seats are cracked and sun-faded. The dashboard is dusty, the rearview mirror hangs at an angle. The glovebox is latched shut. A center console sits between the front seats, its lid slightly ajar. You can see the backseat through the gap between the headrests. The trunk release lever is near your left knee.",
  "short_description": "Inside the beat-up sedan. Glovebox, center console, backseat, and trunk release are within reach.",
  "first_visit_text": "You slide into the driver's seat. The car smells like old cigarettes and pine air freshener. Something rattles under the seat as you settle in.",
  "region": "Parking Lot",
  "is_dark": 0,
  "is_start": 0,
  "visited": 0
}
```

The **trunk** and **engine bay** are separate considerations. The trunk could be modeled as:
- Option A: A container item in the car room (the player "pops" the trunk from inside using the lever, then searches it). This is simpler.
- Option B: A separate room accessed by going "around back" from the parking lot, with its own exit. This is more spatially realistic but adds complexity.

**Recommended: Option A.** The trunk is a container item inside the car room. The player interacts with it from the driver's seat. The trunk release lever is a separate scenery item; a DSL command handles `pull lever` to unlock/open the trunk container.

The **engine bay** is modeled similarly as a container item. A DSL command handles `open hood` or `pop hood`.

### 6.3 Container Items

#### Glovebox (locked)

```json
{
  "id": "car_glovebox",
  "name": "glovebox",
  "description": "The car's glovebox, latched shut.",
  "examine_description": "A standard glovebox in the dashboard. The latch is stiff. It's locked -- you'd need a key or something to pry it open.",
  "room_id": "inside_car",
  "container_id": null,
  "is_takeable": 0,
  "is_visible": 1,
  "is_container": 1,
  "is_open": 0,
  "has_lid": 1,
  "is_locked": 1,
  "lock_message": "The glovebox is locked. The latch won't budge.",
  "open_message": "The glovebox drops open, revealing its contents.",
  "category": "scenery"
}
```

#### Center Console (unlocked, closed)

```json
{
  "id": "car_center_console",
  "name": "center console",
  "description": "A center console between the front seats, its lid slightly ajar.",
  "examine_description": "A plastic console with a hinged lid. It's slightly open -- you could search inside.",
  "room_id": "inside_car",
  "container_id": null,
  "is_takeable": 0,
  "is_visible": 1,
  "is_container": 1,
  "is_open": 0,
  "has_lid": 1,
  "is_locked": 0,
  "open_message": "You flip open the center console lid.",
  "category": "scenery"
}
```

#### Under the Seat (always open, no lid)

```json
{
  "id": "car_under_seat",
  "name": "under the seat",
  "description": "The dark space under the driver's seat.",
  "examine_description": "You lean down and peer under the seat. It's dark and dusty under there. You could reach in and search around.",
  "room_id": "inside_car",
  "container_id": null,
  "is_takeable": 0,
  "is_visible": 1,
  "is_container": 1,
  "is_open": 1,
  "has_lid": 0,
  "is_locked": 0,
  "search_message": "You reach under the seat and feel around in the dark...",
  "category": "scenery"
}
```

#### Backseat (always open, no lid)

```json
{
  "id": "car_backseat",
  "name": "backseat",
  "description": "The car's backseat, strewn with old newspapers and fast food wrappers.",
  "examine_description": "The backseat is covered in junk -- crumpled newspapers, a few fast food bags, an empty soda can. There might be something buried under all that garbage.",
  "room_id": "inside_car",
  "container_id": null,
  "is_takeable": 0,
  "is_visible": 1,
  "is_container": 1,
  "is_open": 1,
  "has_lid": 0,
  "is_locked": 0,
  "search_message": "You dig through the mess on the backseat...",
  "category": "scenery"
}
```

#### Trunk (locked, opened via lever)

```json
{
  "id": "car_trunk",
  "name": "trunk",
  "description": "The car's trunk. The release lever is near your left knee.",
  "examine_description": "You can't see the trunk from here, but there's a release lever near your left knee. You could pull it to pop the trunk, then search inside.",
  "room_id": "inside_car",
  "container_id": null,
  "is_takeable": 0,
  "is_visible": 1,
  "is_container": 1,
  "is_open": 0,
  "has_lid": 1,
  "is_locked": 1,
  "lock_message": "The trunk is closed. There's a release lever by your knee.",
  "open_message": "You hear a thunk from behind as the trunk pops open.",
  "category": "scenery"
}
```

#### Engine Bay (closed, opened via hood release)

```json
{
  "id": "car_engine_bay",
  "name": "engine bay",
  "description": "Under the hood of the car.",
  "examine_description": "You can't see under the hood from here. There should be a hood release somewhere.",
  "room_id": "inside_car",
  "container_id": null,
  "is_takeable": 0,
  "is_visible": 1,
  "is_container": 1,
  "is_open": 0,
  "has_lid": 1,
  "is_locked": 1,
  "lock_message": "The hood is closed. You need to find the release latch.",
  "open_message": "You pop the hood. It rises with a creak, revealing the engine bay.",
  "category": "scenery"
}
```

### 6.4 Items Inside Containers

```json
[
  {
    "id": "car_registration",
    "name": "registration papers",
    "description": "A folded set of vehicle registration papers.",
    "examine_description": "The registration is made out to a 'J. Dalton' at 1847 Birchwood Lane. The car is a 1998 Buick LeSabre. Expired three years ago.",
    "room_id": null,
    "container_id": "car_glovebox",
    "is_takeable": 1,
    "is_visible": 1,
    "category": "document"
  },
  {
    "id": "small_flashlight",
    "name": "small flashlight",
    "description": "A cheap plastic flashlight. The batteries might still work.",
    "examine_description": "A dollar-store flashlight, red plastic, about six inches long. You click it on -- it produces a weak but functional beam. Better than nothing.",
    "room_id": null,
    "container_id": "car_glovebox",
    "is_takeable": 1,
    "is_visible": 1,
    "category": "tool"
  },
  {
    "id": "loose_change",
    "name": "loose change",
    "description": "A handful of quarters and dimes.",
    "examine_description": "About $1.75 in assorted coins. Three quarters, six dimes, and a nickel. One of the quarters is from 1976 -- bicentennial. Probably not worth anything extra.",
    "room_id": null,
    "container_id": "car_center_console",
    "is_takeable": 1,
    "is_visible": 1,
    "category": "treasure"
  },
  {
    "id": "crumpled_note",
    "name": "crumpled note",
    "description": "A crumpled piece of paper with handwriting on it.",
    "examine_description": "The note reads: 'Dock 7. After midnight. Bring the package. DO NOT open it.' The handwriting is hurried and angular.",
    "room_id": null,
    "container_id": "car_backseat",
    "is_takeable": 1,
    "is_visible": 1,
    "category": "document"
  },
  {
    "id": "tire_iron",
    "name": "tire iron",
    "description": "A heavy steel tire iron.",
    "examine_description": "A standard L-shaped tire iron, heavy and cold. One end is a lug wrench; the other is a flat pry bar. Could be useful for more than changing tires.",
    "room_id": null,
    "container_id": "car_trunk",
    "is_takeable": 1,
    "is_visible": 1,
    "category": "tool"
  },
  {
    "id": "old_key",
    "name": "old key",
    "description": "A small brass key on a leather fob.",
    "examine_description": "A worn brass key. The leather fob is stamped with the number '7'. Could this match a locker? A door?",
    "room_id": null,
    "container_id": "car_under_seat",
    "is_takeable": 1,
    "is_visible": 1,
    "category": "key"
  }
]
```

### 6.5 Scenery Items (Non-Container)

```json
[
  {
    "id": "trunk_release_lever",
    "name": "trunk release lever",
    "description": "A small lever near your left knee, by the door.",
    "examine_description": "A plastic lever labeled with a trunk icon. Pull it to pop the trunk.",
    "room_id": "inside_car",
    "is_takeable": 0,
    "is_visible": 1,
    "is_container": 0,
    "category": "scenery"
  },
  {
    "id": "hood_release_latch",
    "name": "hood release latch",
    "description": "A latch under the dashboard, near the steering column.",
    "examine_description": "A small metal latch with a cable attached. Pulling it should release the hood.",
    "room_id": "inside_car",
    "is_takeable": 0,
    "is_visible": 1,
    "is_container": 0,
    "category": "scenery"
  },
  {
    "id": "car_rearview_mirror",
    "name": "rearview mirror",
    "description": "The rearview mirror, hanging at an angle.",
    "examine_description": "The mirror is cracked in one corner but still reflective. You can see the backseat behind you -- and for a moment, you think you see something move in the shadows outside the rear window. But when you look again, nothing.",
    "room_id": "inside_car",
    "is_takeable": 0,
    "is_visible": 1,
    "is_container": 0,
    "category": "scenery"
  }
]
```

### 6.6 DSL Commands for the Car

**Pull trunk release lever:**

```json
{
  "id": "pull_trunk_release",
  "verb": "pull",
  "pattern": "pull {target}",
  "preconditions": [
    { "type": "in_room", "room": "inside_car" },
    { "type": "item_in_room", "item": "trunk_release_lever", "room": "_current" },
    { "type": "not_flag", "flag": "trunk_popped" }
  ],
  "effects": [
    { "type": "open_container", "container": "car_trunk" },
    { "type": "set_flag", "flag": "trunk_popped" },
    { "type": "print", "message": "You pull the lever. There's a muffled thunk from behind -- the trunk pops open." }
  ],
  "one_shot": true
}
```

**Pop the hood:**

```json
{
  "id": "pull_hood_release",
  "verb": "pull",
  "pattern": "pull {target}",
  "preconditions": [
    { "type": "in_room", "room": "inside_car" },
    { "type": "item_in_room", "item": "hood_release_latch", "room": "_current" },
    { "type": "not_flag", "flag": "hood_popped" }
  ],
  "effects": [
    { "type": "open_container", "container": "car_engine_bay" },
    { "type": "set_flag", "flag": "hood_popped" },
    { "type": "print", "message": "You pull the latch. The hood releases with a click. You can now search the engine bay." }
  ],
  "one_shot": true
}
```

**Unlock glovebox with screwdriver (example -- requires a tool found elsewhere):**

```json
{
  "id": "pry_open_glovebox",
  "verb": "use",
  "pattern": "use {item} on {target}",
  "preconditions": [
    { "type": "in_room", "room": "inside_car" },
    { "type": "has_item", "item": "flathead_screwdriver" },
    { "type": "item_in_room", "item": "car_glovebox", "room": "_current" },
    { "type": "not_flag", "flag": "glovebox_opened" }
  ],
  "effects": [
    { "type": "open_container", "container": "car_glovebox" },
    { "type": "set_flag", "flag": "glovebox_opened" },
    { "type": "print", "message": "You wedge the screwdriver into the glovebox latch and twist. The cheap lock snaps. The glovebox drops open." }
  ],
  "one_shot": true
}
```

### 6.7 Player Experience Walkthrough

Here is what the player sees when they explore the car:

```
> enter car

  Inside the Car
  You're sitting in the driver's seat of a beat-up sedan. The vinyl seats
  are cracked and sun-faded. The dashboard is dusty, the rearview mirror
  hangs at an angle...

Exits: out -- Parking Lot
You see: glovebox, center console, under the seat, backseat, trunk,
         engine bay, trunk release lever, hood release latch, rearview mirror

> search center console
You flip open the center console lid.

Inside the center console:
  - loose change

> take loose change
Taken (from the center console).

> search glovebox
The glovebox is locked. The latch won't budge.

> search under the seat
You reach under the seat and feel around in the dark...

Inside under the seat:
  - old key

> take old key
Taken (from under the seat).

> pull trunk release lever
You pull the lever. There's a muffled thunk from behind -- the trunk
pops open.

> search trunk
Inside the trunk:
  - tire iron

> take tire iron from trunk
Taken.

> search backseat
You dig through the mess on the backseat...

Inside the backseat:
  - crumpled note

> examine crumpled note
The note reads: 'Dock 7. After midnight. Bring the package. DO NOT
open it.' The handwriting is hurried and angular.
```

---

## 7. Edge Cases and Failure States

### 7.1 Dropping a Container

If a container is takeable (a bag) and the player drops it in a room:
- The container's `room_id` changes to the current room.
- Items inside the container remain inside (their `container_id` is unchanged).
- The items are still not visible in the room listing -- they are inside the container.
- The player can still search the container in the new room.

### 7.2 Searching in the Dark

If the room is dark (`is_dark = 1`) and the player has no light source:
- Searching containers should be blocked, consistent with existing dark-room behavior.
- The engine should print: "It's too dark to search anything."

### 7.3 Taking the Last Item from a Container

When the player takes the last item from a container:
- The container is now empty.
- Subsequent `search` prints "It's empty."
- The container remains open. It does not auto-close.

### 7.4 Container in Inventory

If a container is takeable and in the player's inventory:
- The player can `search` it at any time (no room requirement).
- Items inside move with the container implicitly (their `container_id` still references the container).
- `search bag` works anywhere.

### 7.5 DSL Commands and Container Items

DSL commands that reference items inside containers work as expected:
- `has_item` precondition: only checks inventory, NOT container contents. An item inside a container in the player's bag is NOT "had" by the player until they take it out.
- `item_in_room` precondition: only checks room-level items, NOT container contents. An item inside a container in the room is NOT "in the room" from a precondition perspective.
- This is intentional. It forces the player to physically take items from containers before using them.

---

## 8. Summary of All Changes

### Schema
- `items` table: add columns `is_container`, `container_id`, `is_open`, `has_lid`, `is_locked`, `lock_message`, `open_message`, `search_message`
- `items` table: add index on `container_id`
- `items` table: add CHECK constraint preventing `room_id` and `container_id` both being non-NULL

### Command DSL
- New effect type: `open_container`
- New effect type: `move_item_to_container`
- New precondition type: `container_open`

### Engine (built-in verbs)
- New verb: `search` / `look in` / `look inside`
- New verb pattern: `take <item> from <container>`
- New verb: `put <item> in <container>`
- Modified verb: `open` (handle containers, not just exits)
- Modified verb: `take` (fall through to open containers if item not found in room)
- Modified verb: `examine` (show container state and contents)
- Modified query: `get_items_in` (exclude items with `container_id` set)

### GameDB
- New method: `get_container_contents()`
- New method: `open_container()`
- New method: `move_item_to_container()`
- New method: `take_item_from_container()`
- New method: `get_open_containers_in_room()`

### Generation Pipeline
- Pass 4 prompt: add container item guidance
- Pass 7 prompt: add container unlock command guidance
- Post-generation validation: add container integrity checks

### World Schema Doc
- Add container fields to items table reference
- Add container relationship to the relationship map
- Add container examples
