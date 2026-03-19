# Unified Item Dynamics System

> Unifies three previously separate planned features -- item states, interaction matrix, and consumables -- into one cohesive system. Also introduces the realism dial and activates the dormant dark room mechanic.

---

## 1. Design Goals

### What problem this solves

The current item model is static. An item exists, it has a description, it can be taken or dropped, it can live inside a container. But items cannot *change state* (a flashlight cannot be turned on), they cannot *interact broadly* with the world (a gun cannot shoot arbitrary targets), and they cannot *deplete* (a battery cannot run out).

These three capabilities are tightly related. A flashlight that can be turned on (state) needs batteries that run out (quantity) and illuminates dark rooms (interaction). A gun that fires (state) needs loaded ammo (quantity) and can shoot any NPC or object (interaction). Designing them as separate systems would create redundant schema, overlapping engine logic, and conflicting generation prompts.

### What this replaces

This design replaces three planned features from the implementation phases:

- **Phase 5b: Item Dynamics** -- the placeholder for this exact document
- **Phase 6: Combat prep** -- the gun/shoot/weapon mechanics are subsumed by the interaction matrix. Combat itself (HP, turns, attack/defend) remains separate, but the "use weapon on target" pattern is handled here
- **Phase 7: Dark rooms** -- was never a separate phase, but the `is_dark` column on rooms has been dormant since Phase 1. This design activates it

### Design pillars

1. **One schema extension, three capabilities.** Every new column serves at least two of the three sub-systems. No column exists for only one feature.
2. **Deterministic at runtime.** The LLM generates state definitions, interaction templates, and quantity values at generation time. The engine resolves them without any LLM call.
3. **Graceful degradation.** Games generated before this system still play correctly. New columns default to NULL or 0, which means "this item has no states, no interactions, no quantity."
4. **Tunable via the realism dial.** The same game prompt produces different item dynamics at low/medium/high realism. The dial affects generation prompts, not engine logic.

---

## 2. Item States

### Player experience

The player encounters items that can be toggled between states. A flashlight can be turned on or off. A radio can be tuned. A lantern can be lit or extinguished. The player types `use flashlight` or `turn on flashlight` and the item changes state, producing immediate feedback ("The flashlight clicks on, casting a narrow beam.").

State changes affect the game world. Turning on a flashlight in a dark room reveals the room description. Turning off a lantern plunges the room back into darkness. The engine checks item state as part of its room display logic.

### Schema

New columns on the `items` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `is_toggleable` | INTEGER | 0 | Whether this item supports on/off state changes |
| `toggle_state` | TEXT | NULL | Current state: `"off"`, `"on"`, or a custom value (e.g., `"empty"`, `"loaded"`, `"tuned"`). NULL means not toggleable |
| `toggle_on_message` | TEXT | NULL | Message displayed when toggled to "on" state |
| `toggle_off_message` | TEXT | NULL | Message displayed when toggled to "off" state |
| `requires_item_id` | TEXT (FK items) | NULL | Item that must be present (in inventory or inside this item's container chain) and have quantity > 0 for this item to function. E.g., flashlight requires batteries |
| `requires_message` | TEXT | NULL | Message shown when the required item is missing or depleted. E.g., "The flashlight won't turn on -- the batteries are dead." |

### Engine behavior

**`use {item}` (bare, no target):**

1. Check if the item is in inventory. If not: "You're not carrying that."
2. Check if the item is toggleable (`is_toggleable = 1`). If not: fall through to DSL resolution (existing behavior).
3. Check `requires_item_id`. If set, verify the required item exists and has `quantity > 0`. If the requirement fails: show `requires_message` or "It doesn't seem to work."
4. Toggle the state:
   - If `toggle_state` is `"off"` -> set to `"on"`, show `toggle_on_message`
   - If `toggle_state` is `"on"` -> set to `"off"`, show `toggle_off_message`
   - For custom states: cycle between the first two states defined in the item's configuration (see Custom States below)
5. Persist the new `toggle_state` to the database.

**`turn on {item}` / `turn off {item}`:**

Aliases that skip the toggle cycle and go directly to the requested state. If the item is already in the requested state: "It's already on/off."

**Custom states:**

Some items have more than two states. A radio might have states `"off"`, `"static"`, `"tuned"`. Custom state cycling is handled by a new column:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `toggle_states` | TEXT (JSON) | NULL | JSON array of valid states in cycle order. E.g., `["off", "static", "tuned"]`. When NULL, defaults to `["off", "on"]` |

Each state can have its own message via a new column:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `toggle_messages` | TEXT (JSON) | NULL | JSON object mapping state names to transition messages. E.g., `{"on": "The flashlight clicks on.", "off": "The flashlight goes dark."}`. Overrides `toggle_on_message`/`toggle_off_message` when present |

For the common two-state case (on/off), `toggle_on_message` and `toggle_off_message` are sufficient. `toggle_states` and `toggle_messages` exist for the uncommon multi-state case and can be NULL for most items.

### State persistence

`toggle_state` is a mutable column that the engine writes to during gameplay. Since the `.zork` file is the save, state persists automatically.

---

## 3. Interaction Matrix

### Player experience

The player can use items on targets they were not specifically designed for, and get a meaningful response. Pointing a gun at an NPC produces "Sergeant Chen dives behind cover." Shining a flashlight on a dark corner produces "The beam cuts through the shadows." Using a knife on a piece of rope produces "You cut through the rope."

These are not DSL commands with specific preconditions. They are *category-level response templates* that the LLM generates at world-creation time. The engine resolves them by matching the item's tags against the target's category.

### Why this matters

Without the interaction matrix, the LLM must generate a separate DSL command for every item-target pair. A game with 5 weapons and 20 targetable objects needs 100 commands. With the interaction matrix, the LLM generates ~5 tag-category response templates and the engine handles all 100 combinations.

The interaction matrix handles the "soft" interactions -- the ones that produce flavor text but don't change game state. DSL commands still handle the "hard" interactions -- the ones that unlock doors, solve puzzles, and advance the game. The resolution order makes this explicit: DSL first, then interaction matrix, then built-in fallback.

### Schema

New columns on the `items` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `item_tags` | TEXT (JSON) | NULL | JSON array of tag strings. E.g., `["weapon", "firearm", "loud"]`. Tags are freeform but the LLM is guided toward a standard vocabulary (see Tag Vocabulary below) |

The `category` column already exists on items. Extend its usage:

- Items already have `category` (TEXT). Currently used informally. Now it becomes the target-side key for interaction matrix lookups.
- NPCs need a `category` column:

New column on the `npcs` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `category` | TEXT | NULL | Category for interaction matrix matching. E.g., `"character"`, `"hostile"`, `"animal"` |

New table for interaction responses:

```sql
CREATE TABLE IF NOT EXISTS interaction_responses (
    id              TEXT PRIMARY KEY,
    item_tag        TEXT NOT NULL,       -- tag on the item being used
    target_category TEXT NOT NULL,       -- category on the target
    response        TEXT NOT NULL,       -- template text with {item} and {target} placeholders
    priority        INTEGER NOT NULL DEFAULT 0,  -- higher = tried first
    room_id         TEXT REFERENCES rooms(id),   -- NULL = global, non-NULL = room-specific
    requires_state  TEXT,                -- item must be in this toggle_state (e.g., "on"). NULL = any state
    consumes        INTEGER NOT NULL DEFAULT 0,  -- 1 = triggers quantity consumption on the item
    consume_amount  INTEGER NOT NULL DEFAULT 1   -- how many units to consume
);

CREATE INDEX IF NOT EXISTS idx_interaction_tag ON interaction_responses(item_tag);
CREATE INDEX IF NOT EXISTS idx_interaction_cat ON interaction_responses(target_category);
```

### Resolution order

When the player types `use {item} on {target}`:

1. **DSL commands first.** The engine checks all DSL commands for a matching pattern, verb, and passing preconditions. If a DSL command fires, it wins. This preserves all existing puzzle logic.
2. **Interaction matrix second.** If no DSL command matched (or all matched commands failed preconditions), the engine checks the interaction matrix:
   a. Get the item's `item_tags` (JSON array).
   b. Get the target's `category` (from items table or npcs table).
   c. Query `interaction_responses` for rows where `item_tag` is in the item's tags AND `target_category` matches the target's category. Filter by `room_id` (NULL = global, or matching current room). Filter by `requires_state` (NULL = any, or matching item's current `toggle_state`).
   d. Order by `priority` DESC. Take the first match.
   e. Substitute `{item}` with the item's display name and `{target}` with the target's display name.
   f. If `consumes = 1`, reduce the item's `quantity` by `consume_amount`. If quantity reaches 0, force toggle_state to "off" and show the depletion message (see Consumables section).
   g. Display the response text.
3. **Built-in put-in fallback third.** If no interaction response matched, try the container put-in logic (existing behavior).
4. **Generic failure last.** "That doesn't seem to work."

### Tag vocabulary

The LLM is guided toward these standard tags during generation, but can create custom tags when needed:

**Functional tags** (what the item does):
- `weapon` -- can be used aggressively on targets
- `firearm` -- a ranged weapon (subset of weapon)
- `blade` -- a cutting/slashing weapon (subset of weapon)
- `light_source` -- produces light when active
- `tool` -- general-purpose utility item
- `key` -- unlocks something
- `healing` -- restores health or cures conditions
- `container` -- already handled by the container system, but tagged for interaction purposes

**Behavioral tags** (how it interacts):
- `loud` -- using this item makes noise (can alert NPCs in adjacent rooms)
- `fragile` -- can break if used roughly
- `consumable` -- has limited uses

**Category vocabulary** (for targets):
- `character` -- friendly or neutral NPC
- `hostile` -- enemy NPC
- `animal` -- non-humanoid creature
- `furniture` -- immovable room fixture
- `mechanism` -- lever, switch, button, valve
- `document` -- readable text
- `barrier` -- door, gate, wall, blockage
- `scenery` -- decorative, non-interactive by default

### Example interaction responses

```
item_tag     | target_category | response
-------------|-----------------|----------------------------------------------
weapon       | character       | {target} flinches and backs away. "What are you doing?!"
weapon       | hostile         | You strike at {target} with the {item}.
firearm      | character       | {target} dives behind cover. "Don't shoot!"
firearm      | furniture       | The bullet punches through the {target}, leaving a ragged hole.
firearm      | scenery         | The shot ricochets off the {target} with a sharp crack.
light_source | character       | You shine the {item} at {target}. They squint and shield their eyes.
light_source | furniture       | The beam of the {item} plays across the {target}, revealing nothing unusual.
blade        | barrier         | You hack at the {target} with the {item}, but it holds firm.
tool         | mechanism       | You work at the {target} with the {item}. Nothing happens.
```

### Placeholder and default responses

Every game should have a default response row with `item_tag = "*"` and `target_category = "*"`:

```
item_tag | target_category | response                    | priority
---------|-----------------|-----------------------------|---------
*        | *               | Nothing interesting happens. | -1
```

The `*` wildcard matches any tag/category. Priority -1 ensures it loses to all specific matches. The LLM generates this default row as part of the interaction responses pass.

---

## 4. Consumables and Quantities

### Player experience

Some items have a limited supply. A flashlight has battery charges. A gun has loaded rounds. A medical kit has uses. The player sees the remaining quantity when examining the item: "The flashlight has 3 charges remaining." Using the item depletes the resource. When the resource hits zero, the item stops working and the player gets feedback: "The flashlight flickers and dies -- the batteries are spent."

### Schema

New columns on the `items` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `quantity` | INTEGER | NULL | Current quantity. NULL means the item is not quantified (infinite use). 0 means depleted |
| `max_quantity` | INTEGER | NULL | Maximum capacity. Used for reload/recharge mechanics. NULL means no maximum (not quantified) |
| `quantity_unit` | TEXT | NULL | Display label for the quantity. E.g., `"rounds"`, `"charges"`, `"uses"`, `"doses"`. Shown in examine output |
| `depleted_message` | TEXT | NULL | Message shown when quantity reaches 0. E.g., "The flashlight flickers and dies." |
| `quantity_description` | TEXT | NULL | Template for examine display. E.g., `"The {item} has {quantity} {unit} remaining."`. When NULL, the engine uses a default template |

### Engine behavior

**Quantity display in examine:**

When `_handle_examine` encounters an item with `quantity IS NOT NULL`:
- If `quantity > 0`: show `quantity_description` (substituting `{item}`, `{quantity}`, `{unit}`) or the default: "It has {quantity} {unit}."
- If `quantity = 0`: show "It's empty." or the `depleted_message`.

**Consumption on use:**

When a toggleable item's `use` handler fires (or an interaction matrix response has `consumes = 1`):
1. If the item has `requires_item_id`, check the *required item's* quantity, not the item's own quantity. (The flashlight's charge is tracked on the batteries item, not the flashlight itself.) Decrement the required item's quantity by 1.
2. If the item itself has `quantity IS NOT NULL`, decrement the item's own quantity by the amount specified (default 1).

**Depletion:**

When any item's `quantity` reaches 0:
1. If the item is toggleable and currently "on": force `toggle_state` to `"off"`.
2. Display the `depleted_message` or a default: "The {item} is spent."
3. The item remains in inventory (it is not destroyed). The player can still examine it, drop it, etc. It simply no longer functions.

**Reload mechanic:**

`reload {item}` is a new built-in verb:
1. Check that the item has `max_quantity IS NOT NULL` (it's a quantified item that can be refilled).
2. Check for a source item. The engine looks for an item in inventory with matching `category` and positive `quantity`. E.g., reloading a magazine looks for an item with category `"ammunition"` (or matching the magazine's `accepts_items` whitelist from the container system).
3. Transfer quantity from source to target, up to `max_quantity`.
4. Display a message: "You reload the {item}. {quantity}/{max_quantity} {unit}."

Alternatively, reload can be handled entirely via DSL commands for games that need specific reload sequences (e.g., the nested container gun/magazine/ammo chain). The built-in reload is a convenience for simple cases.

### DSL extensions

New precondition type:

```json
{
  "type": "has_quantity",
  "item": "flashlight_batteries",
  "min": 1
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"has_quantity"` |
| `item` | string | yes | Item ID (supports `{slot}` references) |
| `min` | integer | yes | Minimum quantity required (inclusive) |

New effect type:

```json
{
  "type": "consume_quantity",
  "item": "flashlight_batteries",
  "amount": 1
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"consume_quantity"` |
| `item` | string | yes | Item ID (supports `{slot}` references) |
| `amount` | integer | yes | How many units to consume |

New effect type for restoring quantity:

```json
{
  "type": "restore_quantity",
  "item": "flashlight_batteries",
  "amount": 5,
  "source": "spare_batteries"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"restore_quantity"` |
| `item` | string | yes | Item ID to restore |
| `amount` | integer | yes | How many units to add (capped at `max_quantity`) |
| `source` | string | no | Item ID to consume from. If present, the source loses the same amount. If source has insufficient quantity, only the available amount transfers |

---

## 5. Dark Rooms

### Player experience

Some rooms are dark. When the player enters a dark room without an active light source, they see: "It's pitch black. You can't see a thing." They know the room name (from the panel title) but cannot see the description, items, NPCs, or exits (exits are still listed, since the player can feel walls, but destinations are hidden).

Turning on a flashlight immediately reveals the room. The description, items, NPCs, and exits are displayed as if the player just arrived. Turning the flashlight off plunges the room back into darkness.

The player can still move and interact in the dark -- they just can't see. Typing `take sword` in the dark produces "You can't see well enough to do that." Typing `north` still works (you can feel your way). Typing `examine` anything produces the darkness message.

### Schema

No new columns needed. The `is_dark` column on rooms (INTEGER, default 0) has existed since Phase 1 but was never checked by the engine. This design activates it.

### Engine behavior

**Dark room check in `display_room()`:**

After fetching the room data, before rendering:

1. If `room.is_dark` is 0: render normally (no change to existing logic).
2. If `room.is_dark` is 1: check for an active light source.
   - Query the player's inventory for any item where `item_tags` contains `"light_source"` AND `toggle_state = "on"`.
   - If found: the room is illuminated. Render normally.
   - If not found: the room is dark. Show the dark room panel:
     - Panel title: room name (the player knows where they are)
     - Panel body: "It's pitch black. You can't see a thing."
     - No items listed
     - No NPCs listed
     - Exits listed with direction only (no destination name): "Exits: north | south | east"

**Dark room check in interaction handlers:**

When the current room is dark and unlit:
- `take`, `examine`, `read`, `open`, `search`, `look at`: "You can't see well enough to do that."
- `drop`: works (you can drop what you're holding by feel)
- `use {item}`: works (you can use an item you're holding)
- `use {item} on {target}`: "You can't see well enough to do that." (unless the target is in inventory)
- Movement: works normally
- `talk to {npc}`: works if the NPC speaks first / is known to be present (debatable -- see Open Question below)
- `inventory`: works (you know what you're carrying)

**Light state change triggers re-display:**

When `use {item}` toggles a light source to "on" and the current room is dark, the engine immediately calls `display_room()` to reveal the room. This gives the player instant feedback: "The flashlight clicks on, casting a narrow beam." followed by the full room description.

When `use {item}` toggles a light source to "off" and the current room is dark, the engine displays: "Darkness swallows the room."

### Open question: talking in the dark

Two reasonable positions:

**Option A: Allow talking.** The player can hear NPCs. "You hear someone breathing nearby." When the player enters a dark room with an NPC, mention the NPC's presence audibly. Talking works normally. This is more forgiving and avoids frustration.

**Option B: Block talking.** The player cannot initiate conversation in the dark. They don't know who's there. This is more realistic but risks softlocking if an NPC is the only source of a clue needed to find a light source.

**Decision: Option A.** The GDD's design pillar is "fair challenge." Blocking conversation in the dark risks unfairness. NPCs in dark rooms are mentioned via sound cues: "You hear the shuffle of boots nearby." The NPC's name is shown if the player has met them before (has a flag for prior interaction).

---

## 6. Realism Dial

### Player experience

When generating a game, the player (or the person generating the game) chooses a realism level:

```
anyzork generate "A post-apocalyptic bunker" --realism medium
```

This affects how the LLM generates item dynamics. It does not change the engine's logic -- the engine is always capable of handling states, quantities, and interactions. The realism dial controls how *complex* the generated items are.

### Levels

**Low realism:**
- Flashlights always work. No batteries needed. `requires_item_id` is NULL.
- Guns always fire. No ammo tracking. `quantity` is NULL.
- Items have states (on/off) but no resource requirements.
- Dark rooms exist but light sources are abundant and never run out.
- Interaction matrix generates simple, forgiving responses.
- Best for: narrative-focused games, younger audiences, casual play.

**Medium realism (default):**
- Some items need fuel/ammo but quantities are generous (`quantity` starts high, `max_quantity` is high).
- Light sources need batteries but they last a long time (20+ charges).
- Guns need ammo but it's plentiful.
- Dark rooms require active light sources, but multiple sources are available.
- Interaction matrix generates contextually appropriate responses.
- Best for: balanced gameplay, the default experience.

**High realism:**
- Realistic resource management. Batteries deplete after 5-10 uses. Ammo is scarce.
- Items can break or degrade (future extension point -- not in this phase).
- Dark rooms are genuinely threatening. Light sources are limited.
- `requires_item_id` is used extensively. Items have dependencies.
- Interaction matrix generates realistic, consequence-aware responses (shooting a wall might attract attention via a flag-set effect).
- Best for: survival games, tension-focused gameplay, experienced players.

### Storage

New column on the `metadata` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `realism` | TEXT | `"medium"` | One of `"low"`, `"medium"`, `"high"`. Stored so the engine can reference it if needed (e.g., adjusting feedback verbosity) |

The engine reads this value but does not change behavior based on it -- the realism dial affects *generation*, not *runtime*. The engine always applies the same deterministic rules regardless of realism level. The distinction is in what the LLM generates: how many items have quantities, how generous those quantities are, how many items have dependencies, etc.

### Generation prompt guidance

The realism level is injected into every relevant generation pass prompt. Example fragment for the items pass:

```
Realism level: {realism}

If realism is "low":
  - Do NOT set requires_item_id on any item
  - Do NOT set quantity on any item (leave NULL)
  - Light sources should be toggleable but always work
  - Weapons should be toggleable but never need ammo

If realism is "medium":
  - Set requires_item_id on items that logically need fuel/power
  - Set quantity to generous values (batteries: 20 charges, ammo: 30 rounds)
  - Ensure at least 2 light sources are available per dark area

If realism is "high":
  - Set requires_item_id on all items that logically need fuel/power
  - Set quantity to realistic values (batteries: 8 charges, ammo: 12 rounds)
  - Light sources are scarce (1 per dark area, barely enough)
  - Include depleted_message for all quantified items
```

---

## 7. Schema Changes Summary

### Items table -- new columns

```sql
-- Item states
is_toggleable       INTEGER NOT NULL DEFAULT 0,
toggle_state        TEXT,        -- "off", "on", or custom
toggle_on_message   TEXT,
toggle_off_message  TEXT,
toggle_states       TEXT,        -- JSON array for multi-state items, NULL = ["off", "on"]
toggle_messages     TEXT,        -- JSON object mapping state -> message, NULL = use toggle_on/off
requires_item_id    TEXT REFERENCES items(id),
requires_message    TEXT,

-- Interaction matrix tags
item_tags           TEXT,        -- JSON array of tag strings

-- Consumables
quantity            INTEGER,     -- NULL = not quantified, 0 = depleted
max_quantity        INTEGER,     -- NULL = not quantified
quantity_unit       TEXT,        -- "rounds", "charges", "uses"
depleted_message    TEXT,
quantity_description TEXT         -- template for examine display
```

### NPCs table -- new column

```sql
category            TEXT         -- "character", "hostile", "animal", etc.
```

### Metadata table -- new column

```sql
realism             TEXT NOT NULL DEFAULT 'medium'  -- "low", "medium", "high"
```

### New table: interaction_responses

```sql
CREATE TABLE IF NOT EXISTS interaction_responses (
    id              TEXT PRIMARY KEY,
    item_tag        TEXT    NOT NULL,
    target_category TEXT    NOT NULL,
    response        TEXT    NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 0,
    room_id         TEXT    REFERENCES rooms(id),
    requires_state  TEXT,
    consumes        INTEGER NOT NULL DEFAULT 0,
    consume_amount  INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_interaction_tag ON interaction_responses(item_tag);
CREATE INDEX IF NOT EXISTS idx_interaction_cat ON interaction_responses(target_category);
```

### New DSL precondition

| Type | Required Fields | Description |
|------|----------------|-------------|
| `has_quantity` | `item`, `min` | Item has at least `min` quantity |

### New DSL effects

| Type | Required Fields | Description |
|------|----------------|-------------|
| `consume_quantity` | `item`, `amount` | Reduce item quantity by `amount` |
| `restore_quantity` | `item`, `amount` | Increase item quantity by `amount` (capped at max). Optional `source` field |
| `set_toggle_state` | `item`, `state` | Set an item's toggle_state to a specific value |

The `set_toggle_state` effect is needed for DSL commands that change item state as a side effect (e.g., a puzzle that extinguishes all lanterns in the room):

```json
{
  "type": "set_toggle_state",
  "item": "brass_lantern",
  "state": "off"
}
```

### Migration path

For existing `.zork` files: all new columns have NULL or 0 defaults. No migration script is needed. Existing games will play identically -- items with NULL `toggle_state` are not toggleable, items with NULL `quantity` are not quantified, items with NULL `item_tags` have no interaction matrix entries.

The `interaction_responses` table simply won't exist in old files. The engine checks for the table's existence before querying it:

```python
# In GameDB
def _has_table(self, table_name: str) -> bool:
    row = self._fetchone(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return row is not None
```

---

## 8. Engine Changes

### Modified files

**`anyzork/engine/game.py`:**

1. `display_room()` -- add dark room check before rendering. If room is dark and no active light source in inventory, show darkness panel.
2. `_handle_examine()` -- append quantity display for quantified items. Dark room gating.
3. `main_loop()` -- add `turn on/off {item}` recognition. Add `reload {item}` recognition.
4. New `_handle_use_bare()` method for `use {item}` without a target -- toggleable item handler.
5. New `_is_room_lit()` helper that checks room darkness and inventory light sources.
6. New `_handle_reload()` method for the reload verb.
7. `show_help()` -- add new verbs to help text.
8. `show_inventory()` -- show toggle state and quantity for relevant items.

**`anyzork/engine/commands.py`:**

1. `check_precondition()` -- add `has_quantity` precondition type.
2. `apply_effect()` -- add `consume_quantity`, `restore_quantity`, `set_toggle_state` effect types.

**`anyzork/db/schema.py`:**

1. `SCHEMA_SQL` -- add new columns and table.
2. `GameDB` class -- new methods:
   - `toggle_item_state(item_id, new_state)` -- update toggle_state column
   - `consume_item_quantity(item_id, amount)` -- decrement quantity, return new value
   - `restore_item_quantity(item_id, amount, source_id=None)` -- increment quantity
   - `get_interaction_response(item_tags, target_category, room_id, item_state)` -- query interaction matrix
   - `get_active_light_source()` -- check inventory for active light source
   - `_has_table(table_name)` -- check if a table exists (for backward compatibility)
   - `get_item_quantity(item_id)` -- return quantity info for an item

### Resolution chain for `use {item}` (bare)

```
Player types "use flashlight"
  |
  v
Is item in inventory? --NO--> "You're not carrying that."
  |
  YES
  v
Is item toggleable? --NO--> Try DSL resolution (existing behavior)
  |
  YES
  v
Does item have requires_item_id? --YES--> Is required item present
  |                                        with quantity > 0?
  NO                                         |
  |                                    NO: show requires_message
  v                                          |
Toggle state (off->on, on->off)             YES
  |                                          |
  v                                          v
Show toggle message                    Toggle state + show message
  |                                          |
  v                                          v
If item has quantity: consume 1        If required item has quantity:
  |                                    consume 1 from required item
  v                                          |
If quantity hit 0: force off,                v
show depleted_message                  Same depletion check on
  |                                    required item
  v
If this changed a light_source
in a dark room: re-display room
```

### Resolution chain for `use {item} on {target}`

```
Player types "use gun on guard"
  |
  v
DSL command match? --YES--> Execute DSL (existing behavior)
  |
  NO (or all preconditions failed)
  |
  v
Get item.item_tags --> ["weapon", "firearm"]
Get target.category --> "hostile"
  |
  v
Query interaction_responses
WHERE item_tag IN ("weapon", "firearm")
AND target_category = "hostile"
AND (room_id IS NULL OR room_id = current_room)
AND (requires_state IS NULL OR requires_state = item.toggle_state)
ORDER BY priority DESC
LIMIT 1
  |
  v
Found? --NO--> Try built-in put-in fallback
  |              |
  YES            NO match --> "That doesn't seem to work."
  |
  v
Substitute {item} and {target} placeholders
  |
  v
If consumes = 1: consume quantity from item
  |
  v
Display response
```

---

## 9. Generation Pipeline

### New generation pass: Interaction Responses

**Position in pipeline:** After the items pass (Pass 4) and NPC pass (Pass 5), before the commands pass (Pass 7). This pass needs to know what items exist (with their tags) and what NPCs/targets exist (with their categories).

**Pass number:** 5b (between NPCs and puzzles).

**Input context:**
- All items (id, name, item_tags, category)
- All NPCs (id, name, category)
- Realism level
- World concept (theme, tone)

**Output:** Rows for the `interaction_responses` table.

**Prompt guidance:**

```
Generate interaction response templates for this game world.

For each item tag that appears in the world, create response templates
for every target category that makes sense. Responses should:
- Match the game's tone and setting
- Use {item} and {target} placeholders for the item and target names
- Be 1-2 sentences
- Not change game state (state changes are handled by DSL commands)
- Feel natural and specific to the world

Always include a default (*/*) response at priority -1.

Realism level: {realism}
- Low: responses are brief and functional
- Medium: responses are atmospheric and contextual
- High: responses include consequences (noise attracting attention, damage descriptions)
```

### Modified passes

**Items pass (Pass 4):**

Extended to generate new columns:
- `is_toggleable`, `toggle_state`, `toggle_on_message`, `toggle_off_message`
- `requires_item_id`, `requires_message`
- `item_tags`
- `quantity`, `max_quantity`, `quantity_unit`, `depleted_message`, `quantity_description`
- `toggle_states`, `toggle_messages` (only for multi-state items)

The realism level is injected into the prompt to control how many items get quantities and how generous those quantities are.

**NPCs pass (Pass 5):**

Extended to generate the `category` column on each NPC.

**Commands pass (Pass 7):**

Extended to use the new precondition (`has_quantity`) and effects (`consume_quantity`, `restore_quantity`, `set_toggle_state`) where appropriate. The LLM is instructed to prefer interaction matrix responses for broad interactions and reserve DSL commands for state-changing, puzzle-solving interactions.

**Rooms pass (Pass 2):**

No change to schema, but the prompt is updated to be more intentional about `is_dark` placement when the realism level is medium or high. At low realism, `is_dark` is rarely used.

### Validation additions

The validation pass gains new checks:

- Every item with `is_toggleable = 1` must have `toggle_state` set to a non-NULL value
- Every item with `requires_item_id` must reference an item that exists
- Every item with `quantity IS NOT NULL` must have `max_quantity IS NOT NULL`
- Every item with `quantity IS NOT NULL` must have `quantity_unit` set
- Every dark room (`is_dark = 1`) must have at least one light-source-tagged item reachable before or at that room (checked via room graph traversal)
- The `interaction_responses` table must contain at least a default (`*`/`*`) row
- No `item_tag` referenced in `interaction_responses` is absent from all items' `item_tags`

---

## 10. Worked Examples

### Example A: Flashlight in a dark cave

**Items generated (medium realism):**

```json
{
  "id": "tactical_flashlight",
  "name": "Tactical Flashlight",
  "is_toggleable": 1,
  "toggle_state": "off",
  "toggle_on_message": "The flashlight clicks on, casting a narrow white beam.",
  "toggle_off_message": "The flashlight goes dark.",
  "requires_item_id": "flashlight_batteries",
  "requires_message": "The flashlight won't turn on -- the batteries are dead.",
  "item_tags": ["light_source", "tool"],
  "quantity": null,
  "category": "equipment"
}
```

```json
{
  "id": "flashlight_batteries",
  "name": "AA Batteries",
  "quantity": 20,
  "max_quantity": 20,
  "quantity_unit": "charges",
  "depleted_message": "The batteries are completely dead.",
  "item_tags": ["consumable"],
  "category": "supply"
}
```

**Player session:**

```
> use flashlight
The flashlight won't turn on -- the batteries are dead.

> take batteries
Taken.

> use flashlight
The flashlight clicks on, casting a narrow white beam.

[Cave Entrance]
A narrow passage opens into a vaulted chamber. Stalactites hang from the
ceiling like stone teeth. A pool of still water reflects your light. To
the north, the cave continues into darkness.

Exits: north -- Deep Cave  |  south -- Forest Trail
You see: rusty pickaxe
```

### Example B: Gun with interaction matrix

**Items generated:**

```json
{
  "id": "service_pistol",
  "name": "Service Pistol",
  "is_toggleable": 0,
  "item_tags": ["weapon", "firearm", "loud"],
  "quantity": 6,
  "max_quantity": 6,
  "quantity_unit": "rounds",
  "depleted_message": "Click. The pistol is empty.",
  "category": "weapon"
}
```

**Interaction responses generated:**

| item_tag | target_category | response | consumes |
|----------|----------------|----------|----------|
| firearm | character | {target} throws their hands up. "Don't shoot! I'm unarmed!" | 0 |
| firearm | hostile | You fire the {item} at {target}. The shot echoes through the room. | 1 |
| firearm | furniture | The bullet punches a hole in the {target}. Splinters fly. | 1 |
| firearm | scenery | The shot ricochets off the {target}. The noise is deafening. | 1 |
| firearm | mechanism | The bullet strikes the {target} with a metallic ping. | 1 |

**Player session:**

```
> use gun on guard
Don't shoot! I'm unarmed!

> use gun on wooden_crate
The bullet punches a hole in the Wooden Crate. Splinters fly.

> examine gun
A standard-issue 9mm service pistol. Well-maintained.
It has 4 rounds remaining.

> use gun on locked_door
The bullet strikes the Locked Door with a metallic ping.

> examine gun
A standard-issue 9mm service pistol. Well-maintained.
It has 3 rounds remaining.
```

Note: shooting the guard (a character) did not consume ammo (consumes = 0, because you're just threatening). Shooting objects and mechanisms does consume ammo.

If a DSL command exists for `use pistol on locked_door` (because shooting the lock is a puzzle solution), the DSL command fires first and the interaction matrix response is never reached. The DSL command would handle the state change (unlocking the door) while the interaction matrix handles the flavor text for non-puzzle interactions.

### Example C: Multi-state radio

**Items generated:**

```json
{
  "id": "shortwave_radio",
  "name": "Shortwave Radio",
  "is_toggleable": 1,
  "toggle_state": "off",
  "toggle_states": ["off", "static", "tuned"],
  "toggle_messages": {
    "off": "You switch the radio off. Silence returns.",
    "static": "The radio hisses to life with a wash of static.",
    "tuned": "You turn the dial carefully. A faint voice emerges from the static."
  },
  "requires_item_id": "radio_batteries",
  "item_tags": ["tool"],
  "category": "equipment"
}
```

**Player session:**

```
> use radio
The radio hisses to life with a wash of static.

> use radio
You turn the dial carefully. A faint voice emerges from the static.

> use radio
You switch the radio off. Silence returns.

> turn on radio
The radio hisses to life with a wash of static.

> turn off radio
You switch the radio off. Silence returns.
```

The radio cycles through `off -> static -> tuned -> off`. `turn on` jumps to the first non-off state (`static`). `turn off` jumps to `off`.

---

## 11. Implementation Plan

### Step 1: Schema changes

**Files:** `anyzork/db/schema.py`, `docs/game-design/world-schema.md`

- Add all new columns to `SCHEMA_SQL`
- Add `interaction_responses` table
- Add `realism` column to metadata
- Add new GameDB methods: `toggle_item_state`, `consume_item_quantity`, `restore_item_quantity`, `get_interaction_response`, `get_active_light_source`, `_has_table`, `get_item_quantity`
- Update `initialize()` to accept realism parameter

### Step 2: DSL extensions

**Files:** `anyzork/engine/commands.py`, `docs/dsl/command-spec.md`

- Add `has_quantity` precondition
- Add `consume_quantity`, `restore_quantity`, `set_toggle_state` effects

### Step 3: Engine -- item states and toggle handler

**Files:** `anyzork/engine/game.py`

- Add `_handle_use_bare()` for toggleable items
- Add `turn on/off` verb recognition in `main_loop()`
- Update `_handle_examine()` to show quantity info
- Update `show_inventory()` to show toggle state and quantity
- Update `show_help()` with new verbs

### Step 4: Engine -- dark rooms

**Files:** `anyzork/engine/game.py`

- Add `_is_room_lit()` helper
- Update `display_room()` with dark room check
- Add dark room gating to interaction handlers

### Step 5: Engine -- interaction matrix

**Files:** `anyzork/engine/game.py`, `anyzork/db/schema.py`

- Add interaction matrix resolution to `use {item} on {target}` handler
- Wire it between DSL resolution and put-in fallback
- Add quantity consumption from interaction matrix responses

### Step 6: Engine -- reload

**Files:** `anyzork/engine/game.py`

- Add `_handle_reload()` method
- Add `reload` verb recognition in `main_loop()`

### Step 7: Generation pipeline

**Files:** `anyzork/generator/passes/items.py`, `anyzork/generator/passes/npcs.py`, `anyzork/generator/passes/commands.py`, new file `anyzork/generator/passes/interactions.py`

- Update items pass prompt for new columns
- Update NPCs pass prompt for category column
- Create interactions pass for interaction_responses
- Update commands pass for new precondition/effect types
- Add realism level injection to all relevant passes
- Update orchestrator to include new pass

### Step 8: Validation

**Files:** `anyzork/generator/validator.py`

- Add validation checks for new schema constraints
- Add dark room / light source reachability check

### Step 9: Test world

**Files:** `tests/build_test_game.py`

- Update test world with toggleable items, quantities, interaction responses
- Add at least one dark room with a light source puzzle
- Test all three realism levels via generation

### Step 10: Documentation

**Files:** `docs/game-design/world-schema.md`, `docs/dsl/command-spec.md`, `docs/architecture/generation-pipeline.md`, `docs/guides/implementation-phases.md`

- Update world schema with new columns and table
- Update command spec with new precondition/effect types
- Update generation pipeline with new pass
- Update implementation phases to reflect unified system

---

## 12. What This Does Not Cover

- **Combat.** Turn-based HP combat (attack, defend, flee) is a separate system. This design handles "use weapon on target" for flavor text and ammo consumption, but actual combat resolution (damage calculation, enemy turns, death) is Phase 6.
- **Item degradation.** Items breaking after extended use (weapon durability, tool wear) is a future extension. The `quantity` column could be repurposed for durability, but the semantics differ enough to warrant separate design.
- **Crafting.** Combining items to create new items is already handled by the `combine` verb and DSL commands. This design does not extend crafting.
- **Status effects.** Player conditions (poisoned, blinded, strengthened) that modify interactions are a future system. The `toggle_state` concept could extend to player state, but that is out of scope here.
- **Sound propagation.** The `loud` tag on items hints at a future system where noise attracts NPCs from adjacent rooms. This design defines the tag but does not implement the propagation mechanic.

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-18 | Initial design document |
