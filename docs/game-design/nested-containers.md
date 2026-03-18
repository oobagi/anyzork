# Nested Container Design

> Extension to the container system that allows containers to hold other containers. The motivating use case is a gun/magazine/ammo chain (gun holds magazine, magazine holds ammo), but the design is general enough to support any nesting scenario: a backpack holding a pouch, a toolbox holding a case, a desk drawer holding a lockbox.

---

## 1. Design Goals

### What problem this solves

The v1 container system is flat. An item can be inside a container, but a container cannot be inside another container. This limitation was deliberate -- it avoided recursive complexity in the engine, schema, and generation prompts. But it forces workarounds for multi-level containment.

The gun/magazine/ammo system in the test world demonstrates the cost. The current implementation uses three flags (`magazine_loaded`, `gun_loaded`, `target_destroyed`) and removes items from the game entirely when "loaded" (the magazine is `remove_item`-ed when inserted into the gun). This works, but it has three problems:

1. **The magazine disappears.** Once loaded into the gun, the magazine ceases to exist as an item. The player cannot examine it, unload it, or reference it. It is a flag, not an object. This breaks spatial plausibility.

2. **The ammo disappears.** Same problem. The ammo is `remove_item`-ed when loaded into the magazine. The player cannot count rounds, examine them, or recover them.

3. **The system does not generalize.** Every multi-level containment scenario (gun/magazine/ammo, backpack/pouch/gem, toolbox/case/drill-bit) requires a bespoke set of flags and DSL commands that simulate containment without actually using the container system. This is engineering effort that the container system was supposed to eliminate.

With nested containers, the gun literally holds the magazine, and the magazine literally holds the ammo. The engine's existing `search`, `take from`, `put in`, and `examine` verbs work naturally. No flags needed for assembly state -- the state is the containment hierarchy itself.

### Design pillars this serves

- **Deterministic integrity** (Pillar 1): Nesting state is stored in SQLite as `container_id` foreign keys. The engine resolves the hierarchy deterministically. No LLM at runtime.
- **Discoverable depth** (Pillar 2): Nested containers create layered discovery. Search the gun, find the magazine. Search the magazine, find the ammo. Each layer rewards curiosity.
- **Fair challenge** (Pillar 3): The containment hierarchy is inspectable. The player can always `search` to see what is inside.

### What this does NOT change

- **Capacity limits.** Containers still have no weight or slot limit. The generation pipeline controls what goes where.
- **Player-created containers.** Players still cannot designate items as containers. Container status is authored at generation time.
- **Flat containers.** Existing flat containers (drawers, chests, gloveboxes) continue to work identically. Nesting is opt-in -- a container only becomes nested when the generation pipeline places a container inside it.

---

## 2. Depth Limit

### The rule

Maximum nesting depth is **3 levels**. This is an engine-enforced hard limit.

```
Level 1: Container (gun)
  Level 2: Container (magazine)
    Level 3: Item (ammo)
```

A container at depth 3 can hold items but those items MUST NOT themselves be containers. The engine rejects any `put` or `move_item_to_container` operation that would create depth 4.

### Why 3

- The gun/magazine/ammo use case requires exactly 3: gun (1) -> magazine (2) -> ammo (3).
- Real-world nesting beyond 3 levels adds tedium, not depth. A bag inside a pouch inside a chest inside a vault is four `search` commands before the player finds anything. That is not fun.
- 3 levels keeps the recursive logic bounded. Engine functions need at most 3 iterations to walk the tree, not unbounded recursion.

### How depth is computed

Depth is the count of `container_id` links from the item to the root. An item in a room or inventory has depth 0. An item inside a container has depth 1. An item inside a container that is inside another container has depth 2.

```
depth(item) = 0                          if item.container_id IS NULL
depth(item) = 1 + depth(parent)          if item.container_id IS NOT NULL
```

The engine computes this with an iterative walk, not SQL recursion. Given the depth limit of 3, the walk is at most 3 hops.

### Where depth is enforced

1. **`move_item_to_container` (GameDB method):** Before writing, compute the depth of the target container. If the item being placed is itself a container, check that `depth(target) + max_subtree_depth(item) + 1 <= 3`. If the item is a plain item (not a container), check that `depth(target) + 1 <= 3`. Reject with an error if violated.

2. **`_handle_put_in` (engine verb handler):** Before calling `move_item_to_container`, check the depth constraint. Print a player-facing message if rejected: "That won't fit."

3. **Generation pipeline validation (post-Pass 4):** After items are generated, walk every `container_id` chain and verify no chain exceeds depth 3. Flag violations for retry.

---

## 3. Schema Changes

### 3.1 No new columns required for nesting

The existing schema already supports nesting. The `container_id` FK on the `items` table references `items(id)`. There is no constraint that prevents `container_id` from pointing to an item where `is_container = 1`. The v1 prohibition was enforced by validation rules and generation prompts, not by the schema itself.

The CHECK constraint `NOT (room_id IS NOT NULL AND container_id IS NOT NULL)` remains correct. A nested container has `room_id = NULL` and `container_id = <parent_container_id>`, which satisfies the constraint.

### 3.2 New metadata field: `max_nesting_depth`

Add to the `metadata` table:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `max_nesting_depth` | INTEGER | 3 | Engine-enforced maximum nesting depth. Stored in metadata so future games can override if needed. |

This is informational -- the engine reads it at startup and uses it for validation. Default is 3.

### 3.3 New column: `accepts_items`

Add to the `items` table:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `accepts_items` | TEXT | NULL | JSON array of item IDs this container accepts. `NULL` = accepts anything (no restrictions). A JSON array like `["p226_magazine"]` = only accepts those specific items. |

**Default behavior is unrestricted.** When `accepts_items` is `NULL`, the container accepts any item, including other containers. A nightstand, chest, drawer, backpack -- all accept anything by default. You can put a gun in a nightstand. You can put a bag in a chest. No flag needed.

**A whitelist restricts what goes in.** When `accepts_items` contains a JSON array, only the items whose IDs appear in that array can be placed inside the container. Everything else is rejected.

This replaces the binary `accepts_container` flag from the earlier design. The whitelist is strictly more expressive:

| Old approach | New approach | Why better |
|---|---|---|
| `accepts_container = 0` (flat only) | `accepts_items: NULL` (accepts anything) | Most containers should accept anything. The old default was too restrictive -- it blocked putting a gun in a nightstand unless the nightstand was flagged. |
| `accepts_container = 1` (accepts containers) | `accepts_items: NULL` (accepts anything) | Same result, but no flag needed. |
| No way to restrict WHICH container fits | `accepts_items: ["p226_magazine"]` | A P226 only accepts a P226 magazine, not an AR-15 magazine. The old flag could not express this. |

### 3.4 Optional column: `reject_message`

Add to the `items` table:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `reject_message` | TEXT | NULL | Custom message shown when an item is rejected by the `accepts_items` whitelist. If `NULL`, the engine uses the default: "That doesn't fit in the {container}." |

This enables flavor text for rejection. A gun rejects the wrong magazine with "The magazine is the wrong caliber." A potion bottle rejects the wrong ingredient with "That liquid won't mix." Without this field, the generic message is fine for most cases.

### 3.5 Updated schema SQL

```sql
CREATE TABLE IF NOT EXISTS items (
    id                  TEXT PRIMARY KEY,
    name                TEXT    NOT NULL,
    description         TEXT    NOT NULL,
    examine_description TEXT    NOT NULL,
    room_id             TEXT    REFERENCES rooms(id),
    container_id        TEXT    REFERENCES items(id),
    is_takeable         INTEGER NOT NULL DEFAULT 1,
    is_visible          INTEGER NOT NULL DEFAULT 1,
    is_consumed_on_use  INTEGER NOT NULL DEFAULT 0,
    is_container        INTEGER NOT NULL DEFAULT 0,
    is_open             INTEGER NOT NULL DEFAULT 0,
    has_lid             INTEGER NOT NULL DEFAULT 1,
    is_locked           INTEGER NOT NULL DEFAULT 0,
    lock_message        TEXT,
    open_message        TEXT,
    search_message      TEXT,
    take_message        TEXT,
    drop_message        TEXT,
    weight              INTEGER DEFAULT 1,
    category            TEXT,
    room_description    TEXT,
    key_item_id         TEXT    REFERENCES items(id),
    consume_key         INTEGER NOT NULL DEFAULT 0,
    unlock_message      TEXT,
    accepts_items       TEXT,                             -- NEW: JSON array of accepted item IDs, NULL = accepts anything
    reject_message      TEXT,                             -- NEW: custom rejection text when whitelist blocks an item
    CHECK (NOT (room_id IS NOT NULL AND container_id IS NOT NULL))
);
```

---

## 4. Engine Changes

### 4.1 Depth computation utility

Add a `get_container_depth` method to `GameDB`:

```python
def get_container_depth(self, container_id: str) -> int:
    """Walk the container_id chain upward and return the depth.

    An item in a room or inventory has depth 0.
    An item inside a container has depth 1.
    And so on.
    """
    depth = 0
    current_id = container_id
    while current_id is not None:
        depth += 1
        parent = self._fetchone("SELECT container_id FROM items WHERE id = ?", (current_id,))
        if parent is None:
            break
        current_id = parent["container_id"]
    return depth
```

Maximum 3 iterations given the depth cap. No risk of infinite loops because the depth limit is enforced on write.

### 4.2 Updated `move_item_to_container`

Before performing the move, validate:

1. **Is the target a container?** Check `is_container = 1`. (Already implicitly true since the caller checked, but defense in depth.)

2. **Does the container accept this item?** Check `accepts_items`:
   ```python
   if container.accepts_items is not None:
       accepted = json.loads(container.accepts_items)
       if item.id not in accepted:
           return Rejection(
               container.reject_message or f"That doesn't fit in the {container.name}."
           )
   ```
   If `accepts_items` is `NULL`, skip this check -- the container accepts anything.

3. **Depth limit.** If the item is itself a container:
   - Compute `depth(target) + max_subtree_depth(item) + 1`. If this exceeds `max_nesting_depth` (from metadata, default 3), reject.
   If the item is a plain item:
   - Compute `depth(target) + 1`. If this exceeds `max_nesting_depth`, reject.

4. **Cycle detection.** Verify the target container is not the item itself, and the target is not inside the item (would create a cycle). Walk the target's `container_id` chain upward and verify the item's id does not appear.

If all checks pass, perform the existing update:
```sql
UPDATE items SET room_id = NULL, container_id = ? WHERE id = ?
```

`max_subtree_depth(item)` walks downward from the item to find the deepest nested child. For the gun use case: placing a magazine (which contains ammo) into a gun means `max_subtree_depth(magazine) = 1` (the ammo is one level below). So the check is `depth(gun) + 1 + 1 = 2`, which is within the limit of 3.

### 4.3 Updated `_handle_search`

Currently, `_handle_search` lists the direct contents of a container. With nesting, the question is: should search show nested contents?

**Decision: Single-level search.** `search gun` shows "magazine." `search magazine` shows "ammo." Search does NOT flatten the hierarchy.

**Rationale:**
- Flattening breaks the discovery pacing that containers exist to create. If `search gun` shows both the magazine AND the ammo, there is no reason to search the magazine separately. The player skips a discovery step.
- Single-level search matches real-world intuition. If you look inside a gun, you see the magazine. You do not see individual rounds -- you would have to eject the magazine and inspect it.
- Single-level search keeps the engine simple. The query is the same: `SELECT * FROM items WHERE container_id = ? AND is_visible = 1`. No recursion.

**Change to search display for nested containers:** When a search result item is itself a container, the display should hint at this:

```
Inside the M9 pistol:
  - pistol magazine (contains items)
```

The "(contains items)" suffix is added only when the child container is non-empty and open/lid-less. If the child container is closed or locked, no hint is shown -- the player must interact with it to discover what is inside.

**Searching containers inside containers:** The player can search a nested container if they can reference it. Two access patterns:

1. **Container is in the room.** `search magazine` works if the magazine is in a container that is in the room. But wait -- the current engine only finds items by name in the room or inventory, not inside containers. This is the key question.

2. **Container is in inventory.** `search magazine` works if the magazine is in the player's inventory.

The problem: when the magazine is inside the gun, it is neither in the room nor in inventory. It is inside a container. The current `find_item_by_name` does not search inside containers.

**Solution: Extend search target resolution.** When the player types `search magazine`, the engine should look for the target in three places, in this order:

1. Room items (current behavior).
2. Inventory items (current behavior).
3. Items inside containers the player can access -- specifically, items inside open/lid-less containers in the room or inventory. This is a one-level-deep search into accessible containers.

This mirrors how `_handle_take` already searches inside open containers when the item is not found in the room. Apply the same pattern to `_handle_search`.

**Worked example:**

```
> search gun
Inside the M9 pistol:
  - pistol magazine (contains items)

> search magazine
Inside the pistol magazine:
  - 9mm ammo
```

The second command works because the magazine is inside the gun, and the gun is in the player's inventory (or in the room). The engine finds "magazine" by searching inside accessible containers.

### 4.4 Updated `_handle_take_from`

`take ammo from magazine` -- the player wants ammo from the magazine, but the magazine is inside the gun.

**Decision: Require the container to be accessible.**

The container (magazine) must be findable by the engine. Using the same extended resolution from 4.3, the engine looks in the room, inventory, and then inside accessible containers.

If the magazine is inside the gun, and the gun is in the room or inventory, the engine finds the magazine inside the gun. Then it looks for ammo inside the magazine. If found, it takes the ammo to inventory.

The key constraint: the intermediate containers must be open or lid-less. If the gun is a closed, lidded container, the player must open it first before they can reference the magazine inside it.

**New flow:**

```
> take ammo from magazine
```

1. Find "magazine" -- check room, inventory, then inside accessible containers. Found inside the gun (which is in inventory, open/lid-less).
2. Check magazine is a container, not locked, open or lid-less.
3. Find "ammo" inside magazine.
4. Move ammo to inventory.
5. Print: "Taken."

**What if the player says `take magazine from gun`?**

1. Find "gun" -- in room or inventory. Found.
2. Check gun is a container, not locked, open or lid-less.
3. Find "magazine" inside gun.
4. Move magazine to inventory. The magazine's `container_id` is set to NULL.
5. **Critical:** The magazine's contents (ammo) move with it. They stay inside the magazine. Their `container_id` still points to the magazine.
6. Print: "Taken."

This is correct behavior. When you eject a magazine from a gun, the ammo stays in the magazine. The engine does not need to do anything special -- the ammo's `container_id` still references the magazine, and the magazine is now in inventory.

### 4.5 Updated `_handle_put_in`

`put magazine in gun` -- putting a container inside a container.

**Current behavior:** Finds item in inventory, finds container in room or inventory, validates container state, calls `move_item_to_container`.

**Changes needed:**

1. **Check the whitelist.** Before placing, check the target container's `accepts_items` field. If it is not `NULL`, parse the JSON array and verify the item's ID is in the list. If not, print the container's `reject_message` or the default: "That doesn't fit in the {container}."

2. **Check depth limit.** The updated `move_item_to_container` handles this (see 4.2). If rejected, print: "That won't fit."

3. **Contents travel with the container.** When the player puts the magazine in the gun, the ammo inside the magazine stays inside the magazine. No special handling needed -- the ammo's `container_id` points to the magazine, and that FK does not change.

**Engine logic for `put X in Y`:**

```python
def _handle_put_in(self, item, container):
    # Whitelist check
    if container.accepts_items is not None:
        accepted = json.loads(container.accepts_items)
        if item.id not in accepted:
            msg = container.reject_message or f"That doesn't fit in the {container.name}."
            self.print(msg)
            return
    # Proceed with existing put logic (depth check, cycle detection, etc.)
    ...
```

**Worked example:**

```
> put magazine in gun
You put the pistol magazine in the M9 pistol.
```

The magazine (which might contain ammo) is now inside the gun. `search gun` shows the magazine. `search magazine` shows the ammo.

### 4.6 Updated `_handle_examine`

When examining a container that contains another container, the display should indicate nesting:

```
> examine gun
A standard-issue M9 Beretta. The grip is worn but the action is clean. The magazine well is accessible.
Inside, you see: pistol magazine.

> examine magazine
A 15-round detachable magazine for the M9 pistol. Currently loaded.
Inside, you see: 9mm ammo.
```

No change to the examine logic itself -- it already calls `get_container_contents` and lists the results. The only addition is the "(contains items)" hint when listing a child that is itself a non-empty, accessible container. This matches the search display behavior from 4.3.

### 4.7 Updated `show_inventory`

When the player's inventory contains a container that holds other containers, the inventory display should reflect this. Two options:

**Option A: Flat list (recommended).** Inventory shows only top-level items. The magazine inside the gun does not appear separately in inventory -- it is inside the gun. The player must `search gun` to see it.

```
Inventory:
  M9 pistol      A standard-issue sidearm.
  flashlight     A heavy-duty tactical flashlight.
```

This is already the current behavior. Items with `container_id IS NOT NULL` are excluded from the inventory query (`WHERE room_id IS NULL AND container_id IS NULL`). No change needed.

**Option B: Indented tree.** Inventory shows nested items with indentation. Rejected -- this adds visual complexity and reveals contents the player has not searched for. It undermines the discovery mechanic.

### 4.8 Updated `_handle_take` (bare `take`)

The bare `take <item>` command searches room items, then open containers in the room. With nesting, it should also search one level deeper.

**Decision: Keep single-level search for bare `take`.** The current behavior searches inside open room containers. Do NOT extend this to search recursively into nested containers. If the player wants ammo that is inside a magazine that is inside a gun, they must use explicit `take ammo from magazine`.

**Rationale:** Automatic deep search creates confusing side effects. If `take ammo` automatically reaches into the gun, through the magazine, and extracts the ammo, the player never learns the containment hierarchy exists. The explicit `take from` verb forces the player to understand the structure.

**Exception:** If the nested container is in inventory (not in the room), and the player types `take <item>`, the engine should NOT dig into inventory containers. Items inside inventory containers are not "here" -- they are inside the container. The player must search the container and use `take from`.

### 4.9 Dropping containers with contents

When the player drops a container that holds items (and possibly nested containers), the contents stay inside.

```
> drop gun
Dropped.
```

The gun is now in the room. The magazine stays inside the gun (`container_id` unchanged). The ammo stays inside the magazine. The `move_item` call only changes the gun's `room_id`. All children retain their `container_id` pointing to their parent.

This is already correct behavior -- the current engine sets `room_id` on the dropped item and clears `container_id`. Child items are not affected.

### 4.10 Extended item resolution: `_find_accessible_item`

Several handlers need the same pattern: "find this item in the room, inventory, or inside an accessible container." Factor this into a shared method:

```python
def _find_accessible_item(self, name: str, current_room_id: str) -> dict | None:
    """Find an item by name, searching room, inventory, and one level into accessible containers."""
    db = self.db

    # 1. Room items.
    item = db.find_item_by_name(name, "room", current_room_id)
    if item is not None:
        return item

    # 2. Inventory items.
    item = db.find_item_by_name(name, "inventory", "")
    if item is not None:
        return item

    # 3. Inside accessible containers in the room.
    for container in db.get_open_containers_in_room(current_room_id):
        found = db.find_item_in_container(name, container["id"])
        if found is not None:
            return found

    # 4. Inside accessible containers in inventory.
    for inv_item in db.get_inventory():
        if inv_item.get("is_container") and (inv_item.get("is_open") or not inv_item.get("has_lid")) and not inv_item.get("is_locked"):
            found = db.find_item_in_container(name, inv_item["id"])
            if found is not None:
                return found

    return None
```

Use this method in `_handle_search`, `_handle_take_from` (for resolving the container argument), and `_handle_examine`.

---

## 5. How the Gun System Works with Real Nesting

### 5.1 Single-weapon example (M9 pistol)

| ID | Name | Category | is_container | accepts_items | reject_message | has_lid | Location |
|----|------|----------|-------------|---------------|----------------|---------|----------|
| `m9_pistol` | M9 pistol | weapon | 1 | `["pistol_magazine"]` | "The magazine is the wrong type for this pistol." | 0 | weapons_locker (locked container) |
| `pistol_magazine` | pistol magazine | weapon | 1 | `["9mm_ammo"]` | "That ammo doesn't fit this magazine." | 0 | weapons_bench (container) |
| `9mm_ammo` | 9mm ammo | ammo | 0 | -- | -- | -- | armory_shelves (container) |

Key properties:
- The gun is a container with `accepts_items = ["pistol_magazine"]` (it only accepts the matching magazine) and `has_lid = 0` (always accessible -- you do not "open" a gun to see the magazine).
- The magazine is a container with `accepts_items = ["9mm_ammo"]` (it only accepts matching ammo) and `has_lid = 0` (always accessible -- you do not "open" a magazine to see the ammo).
- Both are `is_takeable = 1` (the player picks them up).
- Ammo is a plain item, not a container.
- A nightstand or drawer has `accepts_items = NULL` -- it accepts anything, including the gun.

### 5.2 Multi-weapon example (P226 + AR-15)

This is the design's stress test. Two weapon systems share the same world. Each gun accepts only its matching magazine. Each magazine accepts only its matching ammo. Cross-loading is rejected with specific feedback.

| ID | Name | Category | is_container | accepts_items | reject_message | has_lid |
|----|------|----------|-------------|---------------|----------------|---------|
| `p226` | P226 pistol | weapon | 1 | `["p226_magazine"]` | "That magazine doesn't fit the P226." | 0 |
| `p226_magazine` | P226 magazine | weapon | 1 | `["9mm_ammo"]` | "That ammo doesn't fit this magazine." | 0 |
| `9mm_ammo` | 9mm ammo | ammo | 0 | -- | -- | -- |
| `ar15` | AR-15 rifle | weapon | 1 | `["ar15_magazine"]` | "That magazine doesn't fit the AR-15." | 0 |
| `ar15_magazine` | AR-15 magazine | weapon | 1 | `["556_ammo"]` | "That ammo doesn't fit this magazine." | 0 |
| `556_ammo` | 5.56mm ammo | ammo | 0 | -- | -- | -- |
| `nightstand` | nightstand | furniture | 1 | NULL | -- | 0 |

**Interaction walkthrough:**

```
> put 9mm in p226 mag
You put the 9mm ammo in the P226 magazine.

> put 556 in p226 mag
That ammo doesn't fit this magazine.

> put p226 mag in ar15
That magazine doesn't fit the AR-15.

> put p226 mag in p226
You put the P226 magazine in the P226 pistol.

> put ar15 mag in p226
That magazine doesn't fit the P226.

> put ar15 in nightstand
You put the AR-15 rifle in the nightstand.

> put p226 in nightstand
You put the P226 pistol in the nightstand.
```

The nightstand accepts anything because `accepts_items` is `NULL`. The guns reject the wrong magazines. The magazines reject the wrong ammo. Each rejection uses a specific `reject_message` that tells the player *why* it failed, not just *that* it failed.

### 5.3 Player experience walkthrough (single weapon)

```
ARMORY
You're in a concrete-walled armory. Metal shelves line the walls, stocked with
ammunition. A weapons bench sits against the far wall. A heavy weapons locker
stands in the corner, padlocked shut.

You see:
  - armory shelves
  - weapons bench
  - weapons locker (locked)

> search shelves
Inside the armory shelves:
  - 9mm ammo

> take ammo
Taken.

> search bench
Inside the weapons bench:
  - pistol magazine

> take magazine
Taken.

> use locker key on weapons locker
The padlock falls away. The locker swings open.

> search locker
Inside the weapons locker:
  - M9 pistol

> take pistol
Taken.

> inventory
Inventory:
  M9 pistol          A standard-issue M9 Beretta.
  pistol magazine    A 15-round detachable magazine.
  9mm ammo           A box of 9mm full metal jacket rounds.

> put ammo in magazine
You put the 9mm ammo in the pistol magazine.

> put magazine in gun
You put the pistol magazine in the M9 pistol.

> search gun
Inside the M9 pistol:
  - pistol magazine (contains items)

> search magazine
Inside the pistol magazine:
  - 9mm ammo

> inventory
Inventory:
  M9 pistol          A standard-issue M9 Beretta.
  flashlight         A heavy-duty tactical flashlight.
```

The magazine and ammo no longer appear in inventory -- they are inside the gun.

### 5.4 Flags replaced by containment state

| Old flag | New equivalent | How the engine checks it |
|----------|---------------|--------------------------|
| `magazine_loaded` | Ammo is inside the magazine | `get_container_contents("pistol_magazine")` is non-empty |
| `gun_loaded` | Magazine is inside the gun | `get_container_contents("m9_pistol")` is non-empty |

The DSL precondition system needs a new precondition type to check containment state (see section 6).

### 5.5 Revised DSL commands

The gun system no longer needs `load` commands with flag manipulation. Instead, the built-in `put in` verb handles assembly. But we still need:

1. **Custom verbs as aliases.** `load magazine` should work as a synonym for `put ammo in magazine`. `load gun` should work as a synonym for `put magazine in gun`.

2. **The `shoot` command.** This still needs a precondition check -- the gun must be loaded. But instead of checking a flag, it checks containment.

**Load magazine (DSL alias):**

```json
{
  "id": "load_magazine",
  "verb": "load",
  "pattern": "load {target}",
  "preconditions": [
    {"type": "has_item", "item": "pistol_magazine"},
    {"type": "has_item", "item": "9mm_ammo"},
    {"type": "not_item_in_container", "item": "9mm_ammo", "container": "pistol_magazine"}
  ],
  "effects": [
    {"type": "move_item_to_container", "item": "9mm_ammo", "container": "pistol_magazine"},
    {"type": "print", "message": "You slide the 9mm rounds into the magazine one by one until it clicks full."}
  ],
  "success_message": "",
  "failure_message": "You need both the magazine and ammo to do that.",
  "priority": 10,
  "one_shot": false,
  "done_message": ""
}
```

Note: `one_shot` is false because the precondition `not_item_in_container` already prevents re-loading. If the ammo is already in the magazine, the precondition fails.

**Load gun (DSL alias):**

```json
{
  "id": "load_gun",
  "verb": "load",
  "pattern": "load {target}",
  "preconditions": [
    {"type": "has_item", "item": "m9_pistol"},
    {"type": "has_item", "item": "pistol_magazine"},
    {"type": "item_in_container", "item": "9mm_ammo", "container": "pistol_magazine"},
    {"type": "not_item_in_container", "item": "pistol_magazine", "container": "m9_pistol"}
  ],
  "effects": [
    {"type": "move_item_to_container", "item": "pistol_magazine", "container": "m9_pistol"},
    {"type": "print", "message": "You slam the loaded magazine into the pistol grip. It seats with a satisfying click. The M9 is ready to fire."}
  ],
  "success_message": "",
  "failure_message": "You need the pistol and a loaded magazine to do that.",
  "priority": 5,
  "one_shot": false,
  "done_message": ""
}
```

The precondition `item_in_container` for ammo-in-magazine ensures the player loaded the magazine first. The precondition `not_item_in_container` for magazine-in-gun prevents double-loading.

**Shoot target:**

```json
{
  "id": "shoot_target",
  "verb": "shoot",
  "pattern": "shoot {target}",
  "preconditions": [
    {"type": "has_item", "item": "m9_pistol"},
    {"type": "item_in_container", "item": "pistol_magazine", "container": "m9_pistol"},
    {"type": "item_in_container", "item": "9mm_ammo", "container": "pistol_magazine"},
    {"type": "in_room", "room": "firing_range"},
    {"type": "not_flag", "flag": "target_destroyed"}
  ],
  "effects": [
    {"type": "set_flag", "flag": "target_destroyed"},
    {"type": "add_score", "points": 10},
    {"type": "set_flag", "flag": "range_qualified"},
    {"type": "solve_puzzle", "puzzle": "weapons_qualification"},
    {"type": "print", "message": "You raise the M9, sight down the barrel, and squeeze the trigger. The report echoes off the concrete walls. Downrange, the silhouette target jerks and a hole appears dead center. Qualified."}
  ],
  "success_message": "",
  "failure_message": "You need a loaded gun to shoot, and you need to be at the firing range.",
  "priority": 0,
  "one_shot": true,
  "done_message": "The target is already destroyed. You've qualified."
}
```

The shoot command checks two containment preconditions: magazine is in gun, and ammo is in magazine. This replaces the old `has_flag: gun_loaded` check. The `target_destroyed` flag and one-shot remain because destroying the target is a permanent world-state change, not a containment change.

### 5.6 What `has_item` means with nesting

**Critical semantic question:** When the precondition `has_item: m9_pistol` is evaluated, does it pass if the gun is in the player's inventory?

Currently, `has_item` checks `room_id IS NULL AND container_id IS NULL AND is_visible = 1` -- the item is in inventory. This is correct for the gun: the gun is a top-level inventory item. It is not inside another container.

But what about `has_item: pistol_magazine` after the magazine is loaded into the gun? The magazine has `container_id = m9_pistol`. It is NOT in the player's inventory -- it is inside the gun, which is in the player's inventory.

**Decision: `has_item` checks top-level inventory only.** If the magazine is inside the gun, `has_item: pistol_magazine` returns false. The DSL commands for loading the gun use `has_item: pistol_magazine` as a precondition because the player must be holding the magazine separately to load it. Once the magazine is in the gun, `has_item: pistol_magazine` fails, which is correct -- the player is no longer "carrying" the magazine as a separate item.

The new `item_in_container` precondition handles the "is this item inside that container" check. This is the correct way to query nested state.

---

## 6. New DSL Precondition and Effect Types

### 6.1 Precondition: `item_in_container`

Checks whether a specific item is inside a specific container.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"item_in_container"` |
| `item` | string | yes | The item ID that should be inside the container. |
| `container` | string | yes | The container item ID. |

```json
{"type": "item_in_container", "item": "pistol_magazine", "container": "m9_pistol"}
```

**Evaluation:** `SELECT 1 FROM items WHERE id = ? AND container_id = ? AND is_visible = 1`. Returns true if a row exists.

This checks direct containment only (one level). It does NOT check transitive containment. `item_in_container: 9mm_ammo, m9_pistol` would return false if the ammo is inside the magazine which is inside the gun. The ammo's `container_id` is `pistol_magazine`, not `m9_pistol`. This is intentional -- the containment hierarchy is explicit, not flattened.

### 6.2 Precondition: `not_item_in_container`

The negation of `item_in_container`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"not_item_in_container"` |
| `item` | string | yes | The item ID that should NOT be inside the container. |
| `container` | string | yes | The container item ID. |

```json
{"type": "not_item_in_container", "item": "pistol_magazine", "container": "m9_pistol"}
```

Used to prevent double-loading: the magazine is not already in the gun.

### 6.3 Precondition: `container_has_contents`

Checks whether a container is non-empty (has at least one visible item inside).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"container_has_contents"` |
| `container` | string | yes | The container item ID. |

```json
{"type": "container_has_contents", "container": "pistol_magazine"}
```

**Evaluation:** `SELECT 1 FROM items WHERE container_id = ? AND is_visible = 1 LIMIT 1`. Returns true if a row exists.

This is a generalized "is the container loaded/filled/non-empty" check. Useful for the gun system ("is the magazine loaded?") without naming the specific ammo item.

### 6.4 Precondition: `container_empty`

The negation of `container_has_contents`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"container_empty"` |
| `container` | string | yes | The container item ID. |

```json
{"type": "container_empty", "container": "pistol_magazine"}
```

### 6.5 Effect: `move_item_to_container` (already exists)

The existing `move_item_to_container` effect type works for nesting without changes. The engine already sets `room_id = NULL, container_id = ?`. The only addition is the whitelist validation and depth validation in the GameDB method (see 4.2).

### 6.6 Effect: `take_item_from_container` (new)

Moves an item from inside a container to the player's inventory.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"take_item_from_container"` |
| `item` | string | yes | The item ID to extract. |

```json
{"type": "take_item_from_container", "item": "pistol_magazine"}
```

**Execution:** `UPDATE items SET container_id = NULL, room_id = NULL WHERE id = ?` (moves to inventory).

This enables "unload" commands: `unload gun` could extract the magazine.

---

## 7. Generation Pipeline Changes

### 7.1 Pass 4 (Items) prompt update

Replace the nesting prohibition with nesting guidance:

---

**Container nesting:**

Containers can hold other containers, up to 3 levels deep. This is used for multi-step assembly systems like weapons (gun holds magazine, magazine holds ammo) or complex storage (backpack holds pouch, pouch holds gem).

When creating a container that accepts specific items:
- Set `is_container: true` (as with all containers).
- Set `accepts_items` to a JSON array of item IDs this container accepts. Use `null` (or omit the field) if the container should accept anything.
- Set `reject_message` to a custom string explaining why the rejected item does not fit. Use `null` (or omit) to use the engine's default message.
- Set `container_id` on the inner item to the outer container's ID if it starts nested.

**Default behavior -- accepts anything:**
Most containers (nightstands, chests, drawers, shelves, bags) should have `accepts_items: null`. They accept any item, including other containers. Only use a whitelist when the design requires specific item restrictions.

**Whitelist -- restricts what fits:**
A P226 pistol has `accepts_items: ["p226_magazine"]` -- only a P226 magazine fits. An AR-15 has `accepts_items: ["ar15_magazine"]`. A P226 magazine has `accepts_items: ["9mm_ammo"]`. This prevents cross-loading between incompatible weapon systems.

**Nesting rules:**
- Maximum depth is 3 levels. A container at depth 2 (inside another container) can hold items but those items MUST NOT be containers.
- `has_lid: false` is typical for nested containers (a gun does not have a "lid" you open to access the magazine).
- Both the outer and inner containers should have `is_takeable: true` if the player needs to assemble/disassemble them (put magazine in gun, take magazine from gun).

**Example: Gun/magazine/ammo chain:**

```json
[
  {
    "id": "p226",
    "name": "P226 pistol",
    "is_container": true,
    "accepts_items": ["p226_magazine"],
    "reject_message": "That magazine doesn't fit the P226.",
    "has_lid": false,
    "is_open": true,
    "is_takeable": true,
    "room_id": "armory",
    "container_id": null
  },
  {
    "id": "p226_magazine",
    "name": "P226 magazine",
    "is_container": true,
    "accepts_items": ["9mm_ammo"],
    "reject_message": "That ammo doesn't fit this magazine.",
    "has_lid": false,
    "is_open": true,
    "is_takeable": true,
    "room_id": null,
    "container_id": null
  },
  {
    "id": "9mm_ammo",
    "name": "9mm ammo",
    "is_container": false,
    "is_takeable": true,
    "room_id": null,
    "container_id": null
  }
]
```

**Example: Unrestricted container (nightstand):**

```json
{
  "id": "nightstand",
  "name": "nightstand",
  "is_container": true,
  "accepts_items": null,
  "has_lid": false,
  "is_open": true,
  "is_takeable": false,
  "room_id": "bedroom",
  "container_id": null
}
```

The nightstand has no whitelist. The player can put a gun, a magazine, a book, or any other item inside it.

In the above example, all three weapon items start un-nested (the player assembles them via `put ammo in magazine`, `put magazine in gun`). If the design wants the gun to start loaded, set `container_id` on the magazine to `p226` and `container_id` on the ammo to `p226_magazine`.

---

### 7.2 Pass 7 (Commands) prompt update

Add guidance for generating nesting-aware commands:

---

**Container nesting commands:**

When the world contains nested containers, generate DSL commands for assembly and disassembly verbs:

- **`load {target}`**: Alias for `put {item} in {target}`. Use `move_item_to_container` effect.
- **`unload {target}`**: Alias for `take {item} from {target}`. Use `take_item_from_container` effect.
- **`eject {target}`**: Another alias for disassembly.

Use the new precondition types to gate these commands:
- `item_in_container`: check that an item is inside a specific container (e.g., magazine is in gun).
- `not_item_in_container`: check that an item is NOT inside a container (e.g., prevent double-loading).
- `container_has_contents`: check that a container is non-empty (e.g., magazine has ammo).
- `container_empty`: check that a container is empty.

---

### 7.3 Validation updates

Replace the nesting prohibition validation with depth and whitelist validation:

**Old rule (remove):**
> No item with `is_container = 1` may have a `container_id` set (no nesting).

**New rules:**
- Every `container_id` chain must terminate within `max_nesting_depth` (default 3) hops.
- An item with `container_id` pointing to item X requires that X has `is_container = 1`.
- An item with `container_id` pointing to item X requires that item's ID appears in X's `accepts_items` array (if `accepts_items` is not `NULL`). If the whitelist would reject the item, the generation is invalid.
- No cycles in `container_id` chains (an item cannot be inside itself, directly or transitively).
- The CHECK constraint `NOT (room_id IS NOT NULL AND container_id IS NOT NULL)` remains.
- Every container with a non-`NULL` `accepts_items` should have at least one corresponding item whose ID appears in the whitelist (otherwise, why does it restrict?). This is a warning, not a hard error.

---

## 8. Edge Cases

### 8.1 Player tries to put a container inside itself

```
> put gun in gun
```

The cycle detection in `move_item_to_container` catches this. Print: "You can't put something inside itself."

### 8.2 Player tries to create a cycle

```
> put gun in magazine
> put magazine in gun
```

The first command succeeds (gun goes inside magazine -- assuming the magazine's `accepts_items` allows it, or is `NULL`). The second command would create a cycle (magazine inside gun, gun inside magazine). The cycle detection walk finds `gun` in the target's ancestry chain. Print: "You can't do that."

### 8.3 Player puts a container with contents into another container, exceeding depth

```
> put magazine in gun          (magazine contains ammo: depth would be 3)
```

If the gun is at depth 0 (in inventory), putting the magazine in creates depth 1 for the magazine and depth 2 for the ammo. Total depth: 2. Within the limit of 3. Allowed.

If the gun is itself inside something at depth 1:
```
gun (depth 1) -> magazine (depth 2) -> ammo (depth 3)
```

This is exactly at the limit. Allowed.

If the gun is at depth 2 (inside a container inside a container), putting the magazine in would create depth 4 for the ammo. The `move_item_to_container` check catches this. Print: "That won't fit."

### 8.4 Container inside a container is locked

The magazine is inside the gun. The magazine is locked. The player tries `search magazine`.

The engine finds the magazine (via extended item resolution), checks `is_locked`, prints the lock message. The player must unlock the magazine before searching it. This works correctly with no special handling.

### 8.5 Player drops a container that holds nested containers

```
> drop gun
```

The gun is placed in the room. The magazine stays inside the gun. The ammo stays inside the magazine. All `container_id` FKs are unchanged. Only the gun's `room_id` is set.

If another player (or the same player later) enters the room, they see the gun. They search it, find the magazine. They search the magazine, find the ammo. The hierarchy is preserved.

### 8.6 `remove_item` on a container with contents

When a container is removed from the game (hidden via `is_visible = 0`), its contents become orphaned -- they have a `container_id` pointing to a now-invisible item.

**Decision:** When removing a container, also recursively remove its contents. Update `remove_item` in GameDB:

```python
def remove_item(self, item_id: str) -> None:
    """Remove an item from the game. If it is a container, recursively remove contents."""
    # First, recursively remove contents.
    contents = self.get_container_contents(item_id)
    for child in contents:
        self.remove_item(child["id"])
    # Then hide this item.
    self._mutate(
        "UPDATE items SET room_id = NULL, container_id = NULL, is_visible = 0 WHERE id = ?",
        (item_id,),
    )
```

This prevents orphaned items. The depth limit (max 3) guarantees the recursion terminates quickly.

### 8.7 `take` bare command finds item inside a nested container in the room

Player types `take ammo`. The ammo is inside a magazine that is inside a gun that is sitting in the room.

Per the decision in 4.8, bare `take` only searches one level into open room containers. The gun is an open container in the room, so the engine searches its contents. It finds the magazine, not the ammo. The ammo is inside the magazine (two levels deep). Bare `take` does not find it.

The player must use `take ammo from magazine` or first `take magazine from gun`, then `take ammo from magazine`.

### 8.8 Whitelist rejection with default message

A container has `accepts_items: ["p226_magazine"]` and `reject_message: NULL`. The player tries `put ar15_magazine in p226`.

The engine checks the whitelist, finds `ar15_magazine` is not in `["p226_magazine"]`, and prints the default message: "That doesn't fit in the P226 pistol."

### 8.9 Whitelist rejection with custom message

Same scenario but `reject_message: "The magazine is the wrong caliber."` The engine prints: "The magazine is the wrong caliber."

### 8.10 Unrestricted container accepts everything

A nightstand has `accepts_items: NULL`. The player puts a gun, a magazine, a book, and a lamp inside it. All succeed. The player then puts a backpack (which is itself a container holding items) inside the nightstand. This also succeeds, assuming the depth limit is not violated.

### 8.11 `move_item_to_container` DSL effect targets a whitelist-restricted container

A DSL command tries to place an item inside a container, but the item's ID is not in the container's `accepts_items` list. The engine rejects it at the GameDB level. The DSL effect fails silently (logs a warning). The command's `failure_message` is not shown because the preconditions passed -- only the effect failed.

**Mitigation:** The generation pipeline validation should catch mismatched commands. If a command's `move_item_to_container` effect targets a container whose `accepts_items` whitelist does not include the item being placed, flag it as a validation error.

### 8.12 Counting items inside nested containers for score/completion

Some games might want to check "are all components assembled?" as a win condition. With nesting, the check is: is the magazine in the gun AND is the ammo in the magazine?

This is handled by chaining `item_in_container` preconditions. The DSL already supports multiple preconditions per command. A "check weapon" command or win condition can require both containment states.

---

## 9. Migration Path

### 9.1 Schema migration

Add the `accepts_items` and `reject_message` columns with `ALTER TABLE`:

```sql
ALTER TABLE items ADD COLUMN accepts_items TEXT;
ALTER TABLE items ADD COLUMN reject_message TEXT;
```

Default `NULL` means all existing containers accept anything. No data migration needed. Existing flat containers work identically to before.

Add the `max_nesting_depth` metadata field:

```sql
-- Only if metadata table is already populated:
-- No column change needed; store as a new key or add to the metadata row.
```

Alternatively, define `max_nesting_depth` as an engine constant (not a database field) and promote it to a database field later if per-game customization is needed.

### 9.2 Existing games

Games generated before this change have `accepts_items = NULL` on all containers. They accept anything -- including other containers. This is the desired default. No nesting restrictions exist in old games unless the generation pipeline placed items inside containers with explicit whitelists.

### 9.3 Test world update

The test world's gun/magazine/ammo system should be updated to use real nesting instead of flags. This means:

1. Remove the `magazine_loaded` and `gun_loaded` flags.
2. Set `is_container = 1` on the gun.
3. Set `accepts_items = '["pistol_magazine"]'` on the gun.
4. Set `reject_message = 'The magazine is the wrong type for this pistol.'` on the gun.
5. Set `is_container = 1` on the magazine.
6. Set `accepts_items = '["9mm_ammo"]'` on the magazine.
7. Set `reject_message = 'That ammo doesn''t fit this magazine.'` on the magazine.
8. Replace the `load_magazine` DSL command with one that uses `move_item_to_container` effect.
9. Replace the `load_gun` DSL command with one that uses `move_item_to_container` effect.
10. Update the `shoot_target` command to use `item_in_container` preconditions instead of `has_flag`.
11. Keep the `target_destroyed` flag -- target destruction is a world-state change, not a containment change.

---

## 10. Summary of Changes

| Area | Change | Backward compatible? |
|------|--------|---------------------|
| Schema: `items` table | Add `accepts_items TEXT` (NULL default = accepts anything) | Yes -- NULL default preserves unrestricted behavior |
| Schema: `items` table | Add `reject_message TEXT` (NULL default = use engine default) | Yes -- no effect when NULL |
| Schema: metadata | Add `max_nesting_depth` (optional, can be engine constant) | Yes |
| GameDB: `move_item_to_container` | Add whitelist check, depth check, cycle detection | Yes -- NULL whitelist passes all checks |
| GameDB: `remove_item` | Recursively remove contents of containers | Yes -- flat containers have at most one level |
| GameDB: new method | `get_container_depth(container_id)` | New method, no existing callers |
| Engine: `_handle_search` | Extend target resolution to find items inside accessible containers | Yes -- adds a fallback after existing lookups |
| Engine: `_handle_take_from` | Extend container resolution to find containers inside other containers | Yes -- adds a fallback |
| Engine: `_handle_put_in` | Check `accepts_items` whitelist before placing | Yes -- NULL whitelist allows everything |
| Engine: `_handle_examine` | Add "(contains items)" hint for nested container children | Yes -- only triggers for nested containers |
| Engine: new method | `_find_accessible_item` shared resolution | New method |
| DSL: preconditions | Add `item_in_container`, `not_item_in_container`, `container_has_contents`, `container_empty` | Yes -- new types, no old types changed |
| DSL: effects | Add `take_item_from_container` | Yes -- new type |
| Generation: Pass 4 | Replace nesting prohibition with whitelist guidance | N/A (prompt change) |
| Generation: Pass 7 | Add nesting command guidance | N/A (prompt change) |
| Validation | Replace "no nesting" rule with depth/cycle/whitelist checks | Stricter for new games, unchanged for old |
