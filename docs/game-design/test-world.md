# The Gun Range -- Nested Container Test World

> A compact military gun range that exercises the nested container system, weapon assembly/disassembly, cross-loading rejection, and all core engine features. 4 rooms, 2 weapon systems, 1 NPC, 1 quest, 1 locked exit, 2 locked containers.

---

## 1. Overview

### Theme

A military proving ground. The player is a recruit who must assemble two weapon systems, qualify at the firing range, and earn clearance to leave. The aesthetic is concrete, steel, fluorescent lighting, and spent brass.

### Purpose

This is a hand-crafted test game that validates:

1. **Nested containers (primary focus):** Gun holds magazine, magazine holds ammo. Two independent weapon systems that must not cross-load. Items start un-nested; the player assembles them.
2. **Whitelist rejection:** Putting the wrong magazine in a gun, or the wrong ammo in a magazine, produces a specific rejection message.
3. **Containment preconditions:** `item_in_container`, `not_item_in_container`, `container_has_contents`, `container_empty`.
4. **Containment effects:** `move_item_to_container`, `take_item_from_container`.
5. **Flat container:** A weapons locker that accepts anything (`accepts_items: null`).
6. **Locked container:** A supply crate that requires a key to open.
7. **Locked exit:** The range exit requires a state-based lock (qualification flags).
8. **NPC dialogue tree:** Branching dialogue with flag-gated and item-gated options.
9. **Quest with objectives:** Track player progress through flag-based objectives.
10. **Custom DSL verbs:** `load`, `shoot`, `unload` with containment-aware preconditions.
11. **Room descriptions that never mention interactable items** (items self-describe via `room_description`).

### What this does NOT test

- Combat system (not yet implemented).
- Narrator mode (optional LLM overlay, not deterministically testable).
- Generation pipeline (this is hand-built).
- Dark rooms (no `is_dark` rooms in this compact layout).
- Hidden exits (kept out to stay compact).

---

## 2. Room Layout

### Map

```
[armory] --(east)--> [firing_range] --(north)--> [range_office]
                          |
                       (south, locked -- state lock)
                          |
                     [exit_corridor]
```

### Room Definitions

#### Room: `armory`

| Field | Value |
|-------|-------|
| `id` | `armory` |
| `name` | Armory |
| `description` | A windowless concrete room lined with steel weapon racks and metal shelving. The air smells of gun oil and solvent. Fluorescent tubes buzz overhead, casting flat white light across every surface. A reinforced door leads east toward the range. |
| `short_description` | The concrete armory. Steel racks and shelving line the walls. The range is east. |
| `first_visit_text` | You step through the blast door and it seals behind you with a hydraulic hiss. The proving grounds qualification course begins here. Arm up, qualify, get out. |
| `region` | gun_range |
| `is_dark` | 0 |
| `is_start` | 1 |

**Design intent:** Starting room. The player collects all weapon components and the locker key here. Every item needed for weapon assembly is in this room, spread across containers and the floor. The room description establishes atmosphere without naming specific items -- the items announce themselves via `room_description`.

**Connections:**
- East -> `firing_range`

---

#### Room: `firing_range`

| Field | Value |
|-------|-------|
| `id` | `firing_range` |
| `name` | Firing Range |
| `description` | A long, narrow range with shooting lanes separated by thick concrete dividers. Halogen floods illuminate paper targets hanging at the far end. Spent brass casings litter the floor. The air is heavy with the smell of burnt powder. The armory is back to the west, and a door to the north is marked RANGE OFFICE. |
| `short_description` | The firing range. Shooting lanes stretch out ahead. West to the armory, north to the range office. A door to the south is marked EXIT. |
| `first_visit_text` | null |
| `region` | gun_range |
| `is_dark` | 0 |
| `is_start` | 0 |

**Design intent:** The shoot-target room. Both weapons are fired here. The locked south exit is the win-condition gate -- the player must qualify with both weapons before the exit opens. This room also contains the paper targets as non-takeable scenery.

**Connections:**
- West -> `armory`
- North -> `range_office`
- South -> `exit_corridor` (locked, state lock: requires `p226_qualified` AND `ar15_qualified`)

---

#### Room: `range_office`

| Field | Value |
|-------|-------|
| `id` | `range_office` |
| `name` | Range Office |
| `description` | A small office behind reinforced glass. A metal desk is buried under paperwork, and a corkboard on the wall is pinned with range schedules and safety violations. A coffee mug sits on the desk, still warm. |
| `short_description` | The range office. Paperwork covers every surface. South returns to the range. |
| `first_visit_text` | null |
| `region` | gun_range |
| `is_dark` | 0 |
| `is_start` | 0 |

**Design intent:** NPC room. Sergeant Chen is here. The dialogue tree and quest assignment happen in this room. Contains the supply crate key as a quest reward (given through dialogue). Also contains a locked supply crate with bonus items.

**Connections:**
- South -> `firing_range`

---

#### Room: `exit_corridor`

| Field | Value |
|-------|-------|
| `id` | `exit_corridor` |
| `name` | Exit Corridor |
| `description` | A short corridor of bare concrete. Daylight leaks under the heavy steel door at the far end. A sign above it reads: QUALIFICATION COMPLETE -- PROCEED TO DEBRIEFING. |
| `short_description` | The exit corridor. Daylight ahead. |
| `first_visit_text` | You push through the door and daylight floods in. The qualification course is behind you. Well done, recruit. |
| `region` | gun_range |
| `is_dark` | 0 |
| `is_start` | 0 |

**Design intent:** Win-condition room. Reaching this room triggers the win condition. The `first_visit_text` serves as the victory fanfare. The room is only accessible after both qualification flags are set.

**Connections:**
- North -> `firing_range`

---

### Exits Table

| ID | from_room_id | to_room_id | direction | is_locked | is_hidden |
|----|-------------|------------|-----------|-----------|-----------|
| `armory_to_range` | `armory` | `firing_range` | east | 0 | 0 |
| `range_to_armory` | `firing_range` | `armory` | west | 0 | 0 |
| `range_to_office` | `firing_range` | `range_office` | north | 0 | 0 |
| `office_to_range` | `range_office` | `firing_range` | south | 0 | 0 |
| `range_to_exit` | `firing_range` | `exit_corridor` | south | 1 | 0 |
| `exit_to_range` | `exit_corridor` | `firing_range` | north | 0 | 0 |

---

## 3. Items

### 3.1 Weapon System: P226 Pistol

#### `p226`

| Field | Value |
|-------|-------|
| `id` | `p226` |
| `name` | P226 pistol |
| `description` | A SIG Sauer P226 service pistol. Matte black finish, polymer grip. |
| `examine_description` | A full-size SIG Sauer P226 in 9mm. The slide is clean, the bore is bright, and the grip panels show light wear from holster draw. The magazine well is empty -- it needs a P226 magazine to function. |
| `room_description` | A P226 pistol sits on one of the weapon racks. |
| `room_id` | `armory` |
| `container_id` | null |
| `is_container` | 1 |
| `accepts_items` | `["p226_magazine"]` |
| `reject_message` | That magazine doesn't fit the P226. |
| `has_lid` | 0 |
| `is_open` | 1 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | weapon |
| `take_message` | You pick up the P226. It has good weight. |
| `drop_message` | You set the P226 down. |

#### `p226_magazine`

| Field | Value |
|-------|-------|
| `id` | `p226_magazine` |
| `name` | P226 magazine |
| `description` | A 15-round detachable magazine for the P226. |
| `examine_description` | A steel-body 15-round magazine for the SIG P226. Double-stack design. The feed lips are clean and the spring has good tension. It's empty -- you'd need 9mm ammo to load it. |
| `room_description` | A P226 magazine rests on a metal shelf. |
| `room_id` | `armory` |
| `container_id` | null |
| `is_container` | 1 |
| `accepts_items` | `["9mm_ammo"]` |
| `reject_message` | That ammo doesn't fit this magazine. |
| `has_lid` | 0 |
| `is_open` | 1 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | weapon |
| `take_message` | You pick up the P226 magazine. |
| `drop_message` | You set the P226 magazine down. |

#### `9mm_ammo`

| Field | Value |
|-------|-------|
| `id` | `9mm_ammo` |
| `name` | 9mm ammo |
| `description` | A box of 9mm full metal jacket rounds. |
| `examine_description` | Standard 9x19mm Parabellum, full metal jacket. Brass casings, copper jackets. The box is full. These fit the P226 magazine. |
| `room_description` | A box of 9mm ammo sits on the shelf beside the magazine. |
| `room_id` | `armory` |
| `container_id` | null |
| `is_container` | 0 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 0 |
| `is_open` | 0 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | ammo |
| `take_message` | You pick up the box of 9mm ammo. |
| `drop_message` | You set the 9mm ammo down. |

---

### 3.2 Weapon System: AR-15 Rifle

#### `ar15`

| Field | Value |
|-------|-------|
| `id` | `ar15` |
| `name` | AR-15 rifle |
| `description` | An AR-15 semi-automatic rifle with a black polymer stock. |
| `examine_description` | A standard AR-15 platform in 5.56 NATO. Flat-top upper receiver, M4 profile barrel, six-position collapsible stock. The bolt carrier group is clean and lubricated. The magazine well is empty -- it needs an AR-15 magazine. |
| `room_description` | An AR-15 rifle is propped against the weapon rack. |
| `room_id` | null |
| `container_id` | `weapons_locker` |
| `is_container` | 1 |
| `accepts_items` | `["ar15_magazine"]` |
| `reject_message` | That magazine doesn't fit the AR-15. |
| `has_lid` | 0 |
| `is_open` | 1 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | weapon |
| `take_message` | You pick up the AR-15. It's heavier than the pistol. |
| `drop_message` | You set the AR-15 down. |

**Note:** The AR-15 starts inside the `weapons_locker` container. The player must open/search the locker to find it.

#### `ar15_magazine`

| Field | Value |
|-------|-------|
| `id` | `ar15_magazine` |
| `name` | AR-15 magazine |
| `description` | A 30-round STANAG magazine for the AR-15. |
| `examine_description` | A 30-round aluminum STANAG magazine. Curved body, anti-tilt follower. Standard NATO spec. It's empty -- you'd need 5.56mm ammo to load it. |
| `room_description` | An AR-15 magazine lies on a workbench. |
| `room_id` | `armory` |
| `container_id` | null |
| `is_container` | 1 |
| `accepts_items` | `["556_ammo"]` |
| `reject_message` | That ammo doesn't fit this magazine. |
| `has_lid` | 0 |
| `is_open` | 1 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | weapon |
| `take_message` | You pick up the AR-15 magazine. |
| `drop_message` | You set the AR-15 magazine down. |

#### `556_ammo`

| Field | Value |
|-------|-------|
| `id` | `556_ammo` |
| `name` | 5.56mm ammo |
| `description` | A box of 5.56x45mm NATO rounds. |
| `examine_description` | Standard 5.56x45mm NATO, 55-grain full metal jacket. Green-tip penetrator. The box is full. These fit the AR-15 magazine. |
| `room_description` | A box of 5.56mm ammo is stacked on a lower shelf. |
| `room_id` | `armory` |
| `container_id` | null |
| `is_container` | 0 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 0 |
| `is_open` | 0 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | ammo |
| `take_message` | You pick up the box of 5.56mm ammo. |
| `drop_message` | You set the 5.56mm ammo down. |

---

### 3.3 Containers

#### `weapons_locker` (flat container, accepts anything)

| Field | Value |
|-------|-------|
| `id` | `weapons_locker` |
| `name` | weapons locker |
| `description` | A tall steel weapons locker, the kind you see in every military armory. |
| `examine_description` | A full-height steel weapons locker with a reinforced door and a heavy padlock. Standard military issue. It can hold just about anything. The padlock looks like it needs a key. |
| `room_description` | A tall steel weapons locker stands in the corner. |
| `room_id` | `armory` |
| `container_id` | null |
| `is_container` | 1 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 1 |
| `is_open` | 0 |
| `is_locked` | 1 |
| `is_takeable` | 0 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | `locker_key` |
| `consume_key` | 0 |
| `unlock_message` | You turn the key in the padlock. It clicks open and you swing the locker door wide. |
| `lock_message` | The weapons locker is padlocked shut. You need a key. |
| `open_message` | You open the weapons locker. |
| `search_message` | null |
| `weight` | null |
| `category` | furniture |

**Tests exercised:**
- Flat container with `accepts_items: null` (accepts anything)
- Locked container with `key_item_id` (auto-unlock)
- `has_lid: 1` -- must be opened to search
- Contains the AR-15 (item starts with `container_id: weapons_locker`)
- Non-takeable scenery container

#### `locker_key`

| Field | Value |
|-------|-------|
| `id` | `locker_key` |
| `name` | locker key |
| `description` | A small steel key on a ring. |
| `examine_description` | A standard padlock key. The tag reads "WPN LOCKER -- ARM-01." It fits the weapons locker in the armory. |
| `room_description` | A small key hangs from a hook on the wall. |
| `room_id` | `armory` |
| `container_id` | null |
| `is_container` | 0 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 0 |
| `is_open` | 0 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | key |
| `take_message` | You take the locker key. |
| `drop_message` | You set the key down. |

#### `supply_crate` (locked container, key required)

| Field | Value |
|-------|-------|
| `id` | `supply_crate` |
| `name` | supply crate |
| `description` | A heavy-duty plastic supply crate with a combination lock. |
| `examine_description` | A Pelican-style hard case with reinforced latches and a small combination lock. A label on the side reads: SUPPLY -- SGT. CHEN. You would need the crate key from Sergeant Chen to open this. |
| `room_description` | A locked supply crate sits under the desk. |
| `room_id` | `range_office` |
| `container_id` | null |
| `is_container` | 1 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 1 |
| `is_open` | 0 |
| `is_locked` | 1 |
| `is_takeable` | 0 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | `crate_key` |
| `consume_key` | 0 |
| `unlock_message` | The key turns and the latches pop open. |
| `lock_message` | The supply crate is locked. You need the key from Sergeant Chen. |
| `open_message` | You open the supply crate. |
| `search_message` | null |
| `weight` | null |
| `category` | furniture |

#### `crate_key`

| Field | Value |
|-------|-------|
| `id` | `crate_key` |
| `name` | crate key |
| `description` | A small key with a tag that reads "SUPPLY." |
| `examine_description` | A small brass key. The tag reads "SUPPLY -- ARM OFFICE." It looks like it fits the supply crate in the range office. |
| `room_description` | null |
| `room_id` | null |
| `container_id` | null |
| `is_container` | 0 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 0 |
| `is_open` | 0 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 0 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | key |
| `take_message` | You take the crate key. |
| `drop_message` | You set the crate key down. |

**Note:** The `crate_key` starts with `is_visible: 0` and `room_id: null`. It is spawned into the player's inventory by a dialogue option (Sergeant Chen gives it to the player). This tests the `spawn_item` effect through dialogue.

#### `ear_protection`

| Field | Value |
|-------|-------|
| `id` | `ear_protection` |
| `name` | ear protection |
| `description` | A pair of over-ear hearing protectors. |
| `examine_description` | Standard-issue Peltor over-ear hearing protectors, olive drab. Required on the firing range. These have seen some use but the foam seals are still good. |
| `room_description` | A pair of ear protection hangs from a peg inside the crate. |
| `room_id` | null |
| `container_id` | `supply_crate` |
| `is_container` | 0 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 0 |
| `is_open` | 0 |
| `is_locked` | 0 |
| `is_takeable` | 1 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | 1 |
| `category` | equipment |
| `take_message` | You take the ear protection. Safety first. |
| `drop_message` | You set the ear protection down. |

**Note:** The ear protection starts inside the locked supply crate. It is an optional bonus item -- not required for the critical path, but obtaining it from Chen via dialogue and the crate exercises the locked-container-with-key flow.

---

### 3.4 Range Items (Non-Takeable Scenery)

#### `pistol_target`

| Field | Value |
|-------|-------|
| `id` | `pistol_target` |
| `name` | pistol target |
| `description` | A paper silhouette target hanging from a motorized track. |
| `examine_description` | A standard B-27 paper silhouette target, human-shaped, hanging at 25 yards. The scoring zones are clearly marked. It's unmarked -- no one has qualified yet today. |
| `room_description` | A paper silhouette target hangs in the left lane. |
| `room_id` | `firing_range` |
| `container_id` | null |
| `is_container` | 0 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 0 |
| `is_open` | 0 |
| `is_locked` | 0 |
| `is_takeable` | 0 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | null |
| `category` | scenery |

#### `rifle_target`

| Field | Value |
|-------|-------|
| `id` | `rifle_target` |
| `name` | rifle target |
| `description` | A steel plate target mounted on a spring stand. |
| `examine_description` | An AR500 steel plate, 12 inches in diameter, mounted on a heavy spring stand at 100 yards. A clean hit would make it ring and swing. It's untouched. |
| `room_description` | A steel plate target stands at the far end of the right lane. |
| `room_id` | `firing_range` |
| `container_id` | null |
| `is_container` | 0 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 0 |
| `is_open` | 0 |
| `is_locked` | 0 |
| `is_takeable` | 0 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | null |
| `category` | scenery |

#### `range_safety_poster`

| Field | Value |
|-------|-------|
| `id` | `range_safety_poster` |
| `name` | safety poster |
| `description` | A faded safety poster on the wall. |
| `examine_description` | The poster lists the four rules of firearm safety in large block letters: 1. Treat every weapon as if it is loaded. 2. Never point at anything you do not intend to destroy. 3. Keep your finger off the trigger until ready to fire. 4. Know your target and what is beyond it. Someone has written "ALSO: WEAR YOUR EARS" in marker at the bottom. |
| `read_description` | FOUR RULES OF FIREARM SAFETY. 1. Treat every weapon as if it is loaded. 2. Never point at anything you do not intend to destroy. 3. Keep your finger off the trigger until ready to fire. 4. Know your target and what is beyond it. |
| `room_description` | A faded safety poster is tacked to the concrete divider. |
| `room_id` | `firing_range` |
| `container_id` | null |
| `is_container` | 0 |
| `accepts_items` | null |
| `reject_message` | null |
| `has_lid` | 0 |
| `is_open` | 0 |
| `is_locked` | 0 |
| `is_takeable` | 0 |
| `is_visible` | 1 |
| `is_consumed_on_use` | 0 |
| `key_item_id` | null |
| `weight` | null |
| `category` | scenery |

---

### 3.5 Item Summary Table

| ID | Name | Location | is_container | accepts_items | has_lid | is_takeable | category |
|----|------|----------|-------------|---------------|---------|-------------|----------|
| `p226` | P226 pistol | armory (room) | 1 | `["p226_magazine"]` | 0 | 1 | weapon |
| `p226_magazine` | P226 magazine | armory (room) | 1 | `["9mm_ammo"]` | 0 | 1 | weapon |
| `9mm_ammo` | 9mm ammo | armory (room) | 0 | null | 0 | 1 | ammo |
| `ar15` | AR-15 rifle | weapons_locker (container) | 1 | `["ar15_magazine"]` | 0 | 1 | weapon |
| `ar15_magazine` | AR-15 magazine | armory (room) | 1 | `["556_ammo"]` | 0 | 1 | weapon |
| `556_ammo` | 5.56mm ammo | armory (room) | 0 | null | 0 | 1 | ammo |
| `weapons_locker` | weapons locker | armory (room) | 1 | null | 1 | 0 | furniture |
| `locker_key` | locker key | armory (room) | 0 | null | 0 | 1 | key |
| `supply_crate` | supply crate | range_office (room) | 1 | null | 1 | 0 | furniture |
| `crate_key` | crate key | not placed (spawned) | 0 | null | 0 | 1 | key |
| `ear_protection` | ear protection | supply_crate (container) | 0 | null | 0 | 1 | equipment |
| `pistol_target` | pistol target | firing_range (room) | 0 | null | 0 | 0 | scenery |
| `rifle_target` | rifle target | firing_range (room) | 0 | null | 0 | 0 | scenery |
| `range_safety_poster` | safety poster | firing_range (room) | 0 | null | 0 | 0 | scenery |

---

## 4. NPCs

### Sergeant Chen

| Field | Value |
|-------|-------|
| `id` | `sgt_chen` |
| `name` | Sergeant Chen |
| `description` | A compact woman in fatigues leans against the desk, arms crossed. Her nametape reads CHEN. |
| `examine_description` | Sergeant Chen is mid-thirties, wiry, with close-cropped hair and the kind of economy of movement that comes from years of training. Her sleeves are rolled to the elbow and there's a pen behind her ear. Qualification records are spread across the desk in front of her. She looks like she has been waiting for you. |
| `room_id` | `range_office` |
| `is_alive` | 1 |
| `is_blocking` | 0 |
| `blocked_exit_id` | null |
| `unblock_flag` | null |
| `default_dialogue` | Chen glances up. "You need something, recruit? Talk to me." |
| `hp` | null |
| `damage` | null |

---

### Dialogue Tree

The dialogue tree uses the `dialogue_nodes` / `dialogue_options` schema (branching tree, not topic-based).

#### Node: `chen_root` (root node)

| Field | Value |
|-------|-------|
| `id` | `chen_root` |
| `npc_id` | `sgt_chen` |
| `content` | Chen looks you over. "You're the new recruit for qualification. Here's how it works: assemble your weapons in the armory, bring them out to the range, and put rounds on target. Pistol and rifle. Both must qualify. Questions?" |
| `set_flags` | `["talked_to_chen"]` |
| `is_root` | 1 |

**Options:**

| ID | text | next_node_id | required_flags | excluded_flags | required_items | set_flags | sort_order |
|----|------|-------------|----------------|----------------|----------------|-----------|------------|
| `chen_opt_weapons` | "Where are the weapons?" | `chen_weapons` | null | null | null | null | 1 |
| `chen_opt_supply` | "I need the supply crate key." | `chen_supply` | null | `["has_crate_key"]` | null | null | 2 |
| `chen_opt_qualified_p226` | "I've qualified with the P226." | `chen_p226_done` | `["p226_qualified"]` | null | null | null | 3 |
| `chen_opt_qualified_ar15` | "I've qualified with the AR-15." | `chen_ar15_done` | `["ar15_qualified"]` | null | null | null | 4 |
| `chen_opt_done` | "Nothing. I'm good." | null | null | null | null | null | 5 |

---

#### Node: `chen_weapons`

| Field | Value |
|-------|-------|
| `id` | `chen_weapons` |
| `npc_id` | `sgt_chen` |
| `content` | "Everything you need is in the armory, west of the range. Pistol and mags are on the racks and shelves. The rifle is in the weapons locker -- key should be hanging on the wall. Ammo is on the shelves too. Assemble each weapon: load the ammo into the magazine, then load the magazine into the gun. Do not mix calibers." |
| `set_flags` | null |
| `is_root` | 0 |

**Options:**

| ID | text | next_node_id | required_flags | excluded_flags | required_items | set_flags | sort_order |
|----|------|-------------|----------------|----------------|----------------|-----------|------------|
| `chen_weapons_back` | "Got it. What else?" | `chen_root` | null | null | null | null | 1 |

---

#### Node: `chen_supply`

| Field | Value |
|-------|-------|
| `id` | `chen_supply` |
| `npc_id` | `sgt_chen` |
| `content` | Chen pulls a small key from her pocket and tosses it to you. "Here. There's ear protection in the crate. Not required, but your hearing will thank you." |
| `set_flags` | `["has_crate_key"]` |
| `is_root` | 0 |

**Note:** When this node is visited, the engine sets the `has_crate_key` flag. A companion DSL command triggers on this flag to spawn the `crate_key` into inventory (see section 6, command `spawn_crate_key`).

**Options:**

| ID | text | next_node_id | required_flags | excluded_flags | required_items | set_flags | sort_order |
|----|------|-------------|----------------|----------------|----------------|-----------|------------|
| `chen_supply_back` | "Thanks. Anything else?" | `chen_root` | null | null | null | null | 1 |

---

#### Node: `chen_p226_done`

| Field | Value |
|-------|-------|
| `id` | `chen_p226_done` |
| `npc_id` | `sgt_chen` |
| `content` | Chen checks a box on her clipboard. "P226 qual, confirmed. Good shooting. Now do the rifle." |
| `set_flags` | null |
| `is_root` | 0 |

**Options:**

| ID | text | next_node_id | required_flags | excluded_flags | required_items | set_flags | sort_order |
|----|------|-------------|----------------|----------------|----------------|-----------|------------|
| `chen_p226_back` | "Will do." | null | null | null | null | null | 1 |

---

#### Node: `chen_ar15_done`

| Field | Value |
|-------|-------|
| `id` | `chen_ar15_done` |
| `npc_id` | `sgt_chen` |
| `content` | Chen checks another box. "AR-15 qual, confirmed. Nice work, recruit. If both quals are done, the exit should be unlocked. Head south from the range." |
| `set_flags` | null |
| `is_root` | 0 |

**Options:**

| ID | text | next_node_id | required_flags | excluded_flags | required_items | set_flags | sort_order |
|----|------|-------------|----------------|----------------|----------------|-----------|------------|
| `chen_ar15_back` | "On my way." | null | null | null | null | null | 1 |

---

### Dialogue Test Coverage

| Feature Tested | Where |
|---|---|
| Root node with multiple options | `chen_root` |
| Flag-gated option (appears after qualification) | `chen_opt_qualified_p226`, `chen_opt_qualified_ar15` |
| Excluded-flag option (disappears after used) | `chen_opt_supply` (hidden after `has_crate_key` is set) |
| Node sets flags | `chen_root` sets `talked_to_chen`, `chen_supply` sets `has_crate_key` |
| Terminal option (null next_node_id) | `chen_opt_done`, `chen_p226_back`, `chen_ar15_back` |
| Non-terminal option (loops back) | `chen_weapons_back`, `chen_supply_back` |
| Item spawn triggered by dialogue flag | `crate_key` spawned when `has_crate_key` is set |

---

## 5. Quests

### Quest: Weapons Qualification

| Field | Value |
|-------|-------|
| `id` | `weapons_qualification` |
| `name` | Weapons Qualification |
| `description` | Assemble both weapon systems, qualify at the firing range with each, and exit the proving grounds. |
| `quest_type` | main |
| `status` | `active` |
| `discovery_flag` | null |
| `completion_flag` | `qualification_complete` |
| `score_value` | 10 |
| `sort_order` | 1 |

**Objectives:**

| ID | quest_id | description | completion_flag | order_index | is_optional | bonus_score |
|----|----------|-------------|-----------------|-------------|-------------|-------------|
| `obj_assemble_p226` | `weapons_qualification` | Assemble the P226 pistol (load magazine, load gun). | `p226_assembled` | 1 | 0 | 0 |
| `obj_qualify_p226` | `weapons_qualification` | Qualify with the P226 at the firing range. | `p226_qualified` | 2 | 0 | 0 |
| `obj_assemble_ar15` | `weapons_qualification` | Assemble the AR-15 rifle (load magazine, load gun). | `ar15_assembled` | 3 | 0 | 0 |
| `obj_qualify_ar15` | `weapons_qualification` | Qualify with the AR-15 at the firing range. | `ar15_qualified` | 4 | 0 | 0 |
| `obj_ear_protection` | `weapons_qualification` | Obtain ear protection from Sergeant Chen's supply crate. | `has_ear_protection` | 5 | 1 | 5 |

**Objective flag sources:**

| Flag | Set By |
|------|--------|
| `p226_assembled` | `load_p226` command (when magazine inserted into gun) |
| `p226_qualified` | `shoot_pistol_target` command |
| `ar15_assembled` | `load_ar15` command (when magazine inserted into gun) |
| `ar15_qualified` | `shoot_rifle_target` command |
| `has_ear_protection` | `take_ear_protection` DSL command |
| `qualification_complete` | Set by the state lock system when both `p226_qualified` AND `ar15_qualified` are true, which unlocks the exit |

---

## 6. DSL Commands

### 6.1 Load P226 Magazine (ammo into magazine)

```json
{
  "id": "load_p226_magazine",
  "verb": "load",
  "pattern": "load {target}",
  "preconditions": [
    {"type": "has_item", "item": "p226_magazine"},
    {"type": "has_item", "item": "9mm_ammo"},
    {"type": "not_item_in_container", "item": "9mm_ammo", "container": "p226_magazine"}
  ],
  "effects": [
    {"type": "move_item_to_container", "item": "9mm_ammo", "container": "p226_magazine"},
    {"type": "print", "message": "You press the 9mm rounds into the P226 magazine one by one. The spring tension builds with each round until the magazine is full."}
  ],
  "success_message": "",
  "failure_message": "You need the P226 magazine and 9mm ammo to load it.",
  "priority": 10,
  "one_shot": 0,
  "done_message": "",
  "context_room_ids": null
}
```

**Why `one_shot: 0`:** The `not_item_in_container` precondition naturally prevents double-loading. If the ammo is already in the magazine, the precondition fails. This is more robust than one-shot because the player can unload and reload.

---

### 6.2 Load AR-15 Magazine (ammo into magazine)

```json
{
  "id": "load_ar15_magazine",
  "verb": "load",
  "pattern": "load {target}",
  "preconditions": [
    {"type": "has_item", "item": "ar15_magazine"},
    {"type": "has_item", "item": "556_ammo"},
    {"type": "not_item_in_container", "item": "556_ammo", "container": "ar15_magazine"}
  ],
  "effects": [
    {"type": "move_item_to_container", "item": "556_ammo", "container": "ar15_magazine"},
    {"type": "print", "message": "You push the 5.56mm rounds into the AR-15 magazine. The follower clicks down with each round. Full."}
  ],
  "success_message": "",
  "failure_message": "You need the AR-15 magazine and 5.56mm ammo to load it.",
  "priority": 10,
  "one_shot": 0,
  "done_message": "",
  "context_room_ids": null
}
```

---

### 6.3 Load P226 (magazine into gun)

```json
{
  "id": "load_p226",
  "verb": "load",
  "pattern": "load {target}",
  "preconditions": [
    {"type": "has_item", "item": "p226"},
    {"type": "has_item", "item": "p226_magazine"},
    {"type": "item_in_container", "item": "9mm_ammo", "container": "p226_magazine"},
    {"type": "not_item_in_container", "item": "p226_magazine", "container": "p226"}
  ],
  "effects": [
    {"type": "move_item_to_container", "item": "p226_magazine", "container": "p226"},
    {"type": "set_flag", "flag": "p226_assembled"},
    {"type": "print", "message": "You slam the loaded magazine into the P226's grip. It seats with a satisfying click. The P226 is ready to fire."}
  ],
  "success_message": "",
  "failure_message": "You need the P226 and a loaded P226 magazine to do that.",
  "priority": 5,
  "one_shot": 0,
  "done_message": "",
  "context_room_ids": null
}
```

**Priority 5 (lower than magazine load at 10):** When the player types "load P226", `{target}` resolves to `p226`. When the player types "load P226 magazine", `{target}` resolves to `p226_magazine`, and the magazine-load command at priority 10 takes precedence. Priority ordering ensures the right command fires.

**Precondition `item_in_container`:** The ammo must already be in the magazine. This forces the player to load the magazine first.

---

### 6.4 Load AR-15 (magazine into gun)

```json
{
  "id": "load_ar15",
  "verb": "load",
  "pattern": "load {target}",
  "preconditions": [
    {"type": "has_item", "item": "ar15"},
    {"type": "has_item", "item": "ar15_magazine"},
    {"type": "item_in_container", "item": "556_ammo", "container": "ar15_magazine"},
    {"type": "not_item_in_container", "item": "ar15_magazine", "container": "ar15"}
  ],
  "effects": [
    {"type": "move_item_to_container", "item": "ar15_magazine", "container": "ar15"},
    {"type": "set_flag", "flag": "ar15_assembled"},
    {"type": "print", "message": "You rock the loaded magazine into the AR-15's mag well and slap it home. The rifle is ready to fire."}
  ],
  "success_message": "",
  "failure_message": "You need the AR-15 and a loaded AR-15 magazine to do that.",
  "priority": 5,
  "one_shot": 0,
  "done_message": "",
  "context_room_ids": null
}
```

---

### 6.5 Shoot Pistol Target

```json
{
  "id": "shoot_pistol_target",
  "verb": "shoot",
  "pattern": "shoot {target}",
  "preconditions": [
    {"type": "has_item", "item": "p226"},
    {"type": "item_in_container", "item": "p226_magazine", "container": "p226"},
    {"type": "item_in_container", "item": "9mm_ammo", "container": "p226_magazine"},
    {"type": "in_room", "room": "firing_range"},
    {"type": "not_flag", "flag": "p226_qualified"}
  ],
  "effects": [
    {"type": "set_flag", "flag": "p226_qualified"},
    {"type": "add_score", "points": 15},
    {"type": "solve_puzzle", "puzzle": "p226_qualification"},
    {"type": "print", "message": "You raise the P226, align the sights, and squeeze. The pistol barks and bucks in your hand. Downrange, the paper target jerks -- a clean hole punched dead center mass. Pistol qualification: PASS."}
  ],
  "success_message": "",
  "failure_message": "You need a loaded P226 pistol and you need to be at the firing range.",
  "priority": 0,
  "one_shot": 1,
  "done_message": "You've already qualified with the P226.",
  "context_room_ids": ["firing_range"]
}
```

**Tests exercised:**
- `item_in_container` precondition: magazine must be in gun AND ammo must be in magazine
- `in_room` precondition
- `not_flag` precondition (prevents re-qualification)
- `one_shot` with `done_message`
- `add_score` effect
- `solve_puzzle` effect
- `context_room_ids`

---

### 6.6 Shoot Rifle Target

```json
{
  "id": "shoot_rifle_target",
  "verb": "shoot",
  "pattern": "shoot {target}",
  "preconditions": [
    {"type": "has_item", "item": "ar15"},
    {"type": "item_in_container", "item": "ar15_magazine", "container": "ar15"},
    {"type": "item_in_container", "item": "556_ammo", "container": "ar15_magazine"},
    {"type": "in_room", "room": "firing_range"},
    {"type": "not_flag", "flag": "ar15_qualified"}
  ],
  "effects": [
    {"type": "set_flag", "flag": "ar15_qualified"},
    {"type": "add_score", "points": 15},
    {"type": "solve_puzzle", "puzzle": "ar15_qualification"},
    {"type": "print", "message": "You shoulder the AR-15, press your cheek to the stock, and fire. The rifle cracks sharply. A hundred yards out, the steel plate rings like a bell and swings on its stand. Rifle qualification: PASS."}
  ],
  "success_message": "",
  "failure_message": "You need a loaded AR-15 rifle and you need to be at the firing range.",
  "priority": 0,
  "one_shot": 1,
  "done_message": "You've already qualified with the AR-15.",
  "context_room_ids": ["firing_range"]
}
```

---

### 6.7 Unload P226 (magazine from gun)

```json
{
  "id": "unload_p226",
  "verb": "unload",
  "pattern": "unload {target}",
  "preconditions": [
    {"type": "has_item", "item": "p226"},
    {"type": "item_in_container", "item": "p226_magazine", "container": "p226"}
  ],
  "effects": [
    {"type": "take_item_from_container", "item": "p226_magazine"},
    {"type": "set_flag", "flag": "p226_assembled", "value": false},
    {"type": "print", "message": "You press the magazine release and the P226 magazine drops into your hand."}
  ],
  "success_message": "",
  "failure_message": "The P226 doesn't have a magazine in it.",
  "priority": 5,
  "one_shot": 0,
  "done_message": "",
  "context_room_ids": null
}
```

**Tests exercised:**
- `take_item_from_container` effect
- Unsetting a flag with `"value": false`
- Reversible assembly (load, unload, reload)

---

### 6.8 Unload AR-15 (magazine from gun)

```json
{
  "id": "unload_ar15",
  "verb": "unload",
  "pattern": "unload {target}",
  "preconditions": [
    {"type": "has_item", "item": "ar15"},
    {"type": "item_in_container", "item": "ar15_magazine", "container": "ar15"}
  ],
  "effects": [
    {"type": "take_item_from_container", "item": "ar15_magazine"},
    {"type": "set_flag", "flag": "ar15_assembled", "value": false},
    {"type": "print", "message": "You press the mag release and strip the AR-15 magazine free."}
  ],
  "success_message": "",
  "failure_message": "The AR-15 doesn't have a magazine in it.",
  "priority": 5,
  "one_shot": 0,
  "done_message": "",
  "context_room_ids": null
}
```

---

### 6.9 Unload P226 Magazine (ammo from magazine)

```json
{
  "id": "unload_p226_magazine",
  "verb": "unload",
  "pattern": "unload {target}",
  "preconditions": [
    {"type": "has_item", "item": "p226_magazine"},
    {"type": "item_in_container", "item": "9mm_ammo", "container": "p226_magazine"}
  ],
  "effects": [
    {"type": "take_item_from_container", "item": "9mm_ammo"},
    {"type": "print", "message": "You strip the 9mm rounds from the P226 magazine. The spring pushes each one up as you pull them free."}
  ],
  "success_message": "",
  "failure_message": "The P226 magazine is empty.",
  "priority": 10,
  "one_shot": 0,
  "done_message": "",
  "context_room_ids": null
}
```

---

### 6.10 Unload AR-15 Magazine (ammo from magazine)

```json
{
  "id": "unload_ar15_magazine",
  "verb": "unload",
  "pattern": "unload {target}",
  "preconditions": [
    {"type": "has_item", "item": "ar15_magazine"},
    {"type": "item_in_container", "item": "556_ammo", "container": "ar15_magazine"}
  ],
  "effects": [
    {"type": "take_item_from_container", "item": "556_ammo"},
    {"type": "print", "message": "You strip the 5.56mm rounds from the AR-15 magazine."}
  ],
  "success_message": "",
  "failure_message": "The AR-15 magazine is empty.",
  "priority": 10,
  "one_shot": 0,
  "done_message": "",
  "context_room_ids": null
}
```

---

### 6.11 Spawn Crate Key (triggered by dialogue flag)

```json
{
  "id": "spawn_crate_key",
  "verb": "talk",
  "pattern": "talk to {npc}",
  "preconditions": [
    {"type": "npc_in_room", "npc": "sgt_chen", "room": "_current"},
    {"type": "has_flag", "flag": "has_crate_key"},
    {"type": "not_flag", "flag": "crate_key_given"}
  ],
  "effects": [
    {"type": "spawn_item", "item": "crate_key", "location": "_inventory"},
    {"type": "set_flag", "flag": "crate_key_given"},
    {"type": "print", "message": ""}
  ],
  "success_message": "",
  "failure_message": "",
  "priority": 100,
  "one_shot": 1,
  "done_message": "",
  "context_room_ids": ["range_office"]
}
```

**Design note:** This command has very high priority (100) so it fires as a side-effect when the dialogue system sets `has_crate_key`. The dialogue node `chen_supply` sets the flag, and then the next time the talk command processes, this spawns the key. In practice, the dialogue system's `set_flags` and this command may need to be coordinated -- the implementation should ensure the key appears in inventory when the dialogue node is visited. If the engine processes dialogue node flags before DSL commands, a simpler approach is to have the dialogue node's `set_flags` include a flag that triggers a post-dialogue hook to spawn the item. The implementer should choose the cleanest integration path.

**Alternative (simpler):** If the engine supports spawning items directly from dialogue node effects, skip this DSL command and add a spawn effect to the `chen_supply` node. The implementer should decide based on the engine's dialogue capabilities.

---

### 6.12 Take Ear Protection (quest tracking)

```json
{
  "id": "take_ear_protection",
  "verb": "take",
  "pattern": "take {target}",
  "preconditions": [
    {"type": "not_flag", "flag": "has_ear_protection"}
  ],
  "effects": [
    {"type": "set_flag", "flag": "has_ear_protection"},
    {"type": "print", "message": ""}
  ],
  "success_message": "",
  "failure_message": "",
  "priority": 1,
  "one_shot": 1,
  "done_message": "",
  "context_room_ids": null
}
```

**Design note:** Priority 1 (low) so the built-in take handler runs its normal item-pickup logic, and this DSL command fires as an additional side effect to set the quest-tracking flag. The implementer should verify that both the built-in handler and the DSL command fire, or consolidate into one path.

---

### 6.13 Command Summary Table

| ID | Verb | What It Does | Key Preconditions | Key Effects |
|----|------|-------------|-------------------|-------------|
| `load_p226_magazine` | load | Put 9mm ammo into P226 mag | `has_item` x2, `not_item_in_container` | `move_item_to_container` |
| `load_ar15_magazine` | load | Put 5.56 ammo into AR-15 mag | `has_item` x2, `not_item_in_container` | `move_item_to_container` |
| `load_p226` | load | Put P226 mag into P226 gun | `has_item` x2, `item_in_container`, `not_item_in_container` | `move_item_to_container`, `set_flag` |
| `load_ar15` | load | Put AR-15 mag into AR-15 gun | `has_item` x2, `item_in_container`, `not_item_in_container` | `move_item_to_container`, `set_flag` |
| `shoot_pistol_target` | shoot | Fire P226 at paper target | `has_item`, `item_in_container` x2, `in_room`, `not_flag` | `set_flag`, `add_score`, `solve_puzzle` |
| `shoot_rifle_target` | shoot | Fire AR-15 at steel target | `has_item`, `item_in_container` x2, `in_room`, `not_flag` | `set_flag`, `add_score`, `solve_puzzle` |
| `unload_p226` | unload | Eject P226 mag from gun | `has_item`, `item_in_container` | `take_item_from_container`, `set_flag(false)` |
| `unload_ar15` | unload | Eject AR-15 mag from gun | `has_item`, `item_in_container` | `take_item_from_container`, `set_flag(false)` |
| `unload_p226_magazine` | unload | Strip ammo from P226 mag | `has_item`, `item_in_container` | `take_item_from_container` |
| `unload_ar15_magazine` | unload | Strip ammo from AR-15 mag | `has_item`, `item_in_container` | `take_item_from_container` |
| `spawn_crate_key` | talk | Spawn crate key after dialogue | `has_flag`, `not_flag` | `spawn_item`, `set_flag` |
| `take_ear_protection` | take | Track quest objective | `not_flag` | `set_flag` |

---

### 6.14 Precondition and Effect Coverage

**Precondition types exercised:**

| Precondition Type | Used In |
|---|---|
| `has_item` | All load/unload/shoot commands |
| `in_room` | Shoot commands |
| `has_flag` | `spawn_crate_key` |
| `not_flag` | Shoot commands, `spawn_crate_key`, `take_ear_protection` |
| `item_in_container` | Load-gun commands, shoot commands, unload commands |
| `not_item_in_container` | Load-magazine commands, load-gun commands |
| `npc_in_room` | `spawn_crate_key` |

**Effect types exercised:**

| Effect Type | Used In |
|---|---|
| `move_item_to_container` | All load commands |
| `take_item_from_container` | All unload commands |
| `set_flag` | Load-gun commands, shoot commands, `spawn_crate_key`, `take_ear_protection` |
| `set_flag` (value: false) | Unload-gun commands |
| `add_score` | Shoot commands |
| `solve_puzzle` | Shoot commands |
| `spawn_item` | `spawn_crate_key` |
| `print` | All commands |

**Not exercised by DSL (handled by built-in engine verbs):**

| Feature | How Tested |
|---|---|
| `move_item` | Built-in take/drop |
| `unlock` (exit lock) | State-based lock auto-unlocks on flag |
| Container `key_item_id` auto-unlock | Built-in open/unlock on `weapons_locker` and `supply_crate` |

---

## 7. Locks

### 7.1 Exit Lock: Range Exit

| Field | Value |
|-------|-------|
| `id` | `range_exit_lock` |
| `lock_type` | state |
| `target_exit_id` | `range_to_exit` |
| `key_item_id` | null |
| `puzzle_id` | null |
| `combination` | null |
| `required_flags` | `["p226_qualified", "ar15_qualified"]` |
| `locked_message` | The exit door is sealed. A panel beside it reads: QUALIFICATION INCOMPLETE. Both pistol and rifle quals are required. |
| `unlock_message` | The panel beside the exit door flashes green: QUALIFICATION COMPLETE. The lock disengages with a heavy clunk. |
| `is_locked` | 1 |
| `consume_key` | 0 |

**Test coverage:** State-based lock requiring multiple flags. Auto-unlocks when the engine detects both `p226_qualified` and `ar15_qualified` are set.

### 7.2 Container Lock: Weapons Locker

The weapons locker is locked via the item's own `is_locked` / `key_item_id` fields (see item definition in section 3.3). This is the built-in container lock system, not the exit lock table.

| Feature | Value |
|---|---|
| Container | `weapons_locker` |
| `is_locked` | 1 |
| `key_item_id` | `locker_key` |
| `consume_key` | 0 |
| `lock_message` | The weapons locker is padlocked shut. You need a key. |
| `unlock_message` | You turn the key in the padlock. It clicks open and you swing the locker door wide. |

### 7.3 Container Lock: Supply Crate

| Feature | Value |
|---|---|
| Container | `supply_crate` |
| `is_locked` | 1 |
| `key_item_id` | `crate_key` |
| `consume_key` | 0 |
| `lock_message` | The supply crate is locked. You need the key from Sergeant Chen. |
| `unlock_message` | The key turns and the latches pop open. |

---

## 8. Puzzles

### 8.1 P226 Qualification

| Field | Value |
|-------|-------|
| `id` | `p226_qualification` |
| `name` | P226 Pistol Qualification |
| `description` | Assemble the P226 pistol (load ammo into magazine, load magazine into gun) and fire at the pistol target in the firing range. |
| `room_id` | `firing_range` |
| `is_solved` | 0 |
| `solution_steps` | `["Take 9mm ammo, P226 magazine, and P226 pistol from the armory", "Load the 9mm ammo into the P226 magazine", "Load the P226 magazine into the P226 pistol", "Go to the firing range", "Shoot the pistol target"]` |
| `hint_text` | `["You need to assemble a pistol. Check the armory for parts.", "Load the ammo into the magazine first, then the magazine into the gun.", "Take the loaded P226 to the firing range and shoot the target."]` |
| `difficulty` | 2 |
| `score_value` | 15 |
| `is_optional` | 0 |

### 8.2 AR-15 Qualification

| Field | Value |
|-------|-------|
| `id` | `ar15_qualification` |
| `name` | AR-15 Rifle Qualification |
| `description` | Assemble the AR-15 rifle (load ammo into magazine, load magazine into gun) and fire at the rifle target in the firing range. |
| `room_id` | `firing_range` |
| `is_solved` | 0 |
| `solution_steps` | `["Find the AR-15 in the weapons locker (unlock with locker key)", "Take 5.56mm ammo and AR-15 magazine from the armory", "Load the 5.56mm ammo into the AR-15 magazine", "Load the AR-15 magazine into the AR-15 rifle", "Go to the firing range", "Shoot the rifle target"]` |
| `hint_text` | `["You need to assemble a rifle. The AR-15 is in the locked weapons locker in the armory.", "Find the locker key hanging on the wall in the armory. The ammo and magazine are on the shelves and workbench.", "Load ammo into mag, mag into gun. Take the loaded AR-15 to the range and shoot the steel target."]` |
| `difficulty` | 2 |
| `score_value` | 15 |
| `is_optional` | 0 |

---

## 9. Flags

| Flag ID | Initial Value | Set By | Description |
|---------|---------------|--------|-------------|
| `talked_to_chen` | false | `chen_root` dialogue node | Player has talked to Sergeant Chen. |
| `has_crate_key` | false | `chen_supply` dialogue node | Chen has offered the crate key. |
| `crate_key_given` | false | `spawn_crate_key` command | Crate key has been spawned to inventory. |
| `p226_assembled` | false | `load_p226` command | P226 magazine is loaded into P226. |
| `ar15_assembled` | false | `load_ar15` command | AR-15 magazine is loaded into AR-15. |
| `p226_qualified` | false | `shoot_pistol_target` command | Player passed P226 qualification. |
| `ar15_qualified` | false | `shoot_rifle_target` command | Player passed AR-15 qualification. |
| `has_ear_protection` | false | `take_ear_protection` command | Player obtained ear protection (optional). |
| `qualification_complete` | false | Engine (state lock auto-sets when both quals pass) | Both qualifications complete. |

---

## 10. Scoring

| Source | Points | Command/Event |
|--------|--------|--------------|
| P226 qualification | 15 | `shoot_pistol_target` |
| AR-15 qualification | 15 | `shoot_rifle_target` |
| Quest completion (Weapons Qualification) | 10 | All required objectives met |
| Optional: Ear protection obtained | 5 | `take_ear_protection` |
| **Total possible** | **45** | |

**Score balance:** 30 points (67%) from critical path (both qualifications), 10 points (22%) from quest completion, 5 points (11%) from optional content. The critical path plus quest gives 40/45 (89%). The optional ear protection adds the remaining 5 points.

---

## 11. Metadata

```json
{
  "id": 1,
  "title": "The Gun Range",
  "author_prompt": "A military gun range qualification course that tests nested container weapon assembly.",
  "seed": "gun-range-test-v2",
  "version": "2.0",
  "created_at": "2026-03-18T00:00:00Z",
  "max_score": 45,
  "win_conditions": ["p226_qualified", "ar15_qualified"],
  "lose_conditions": null,
  "intro_text": "PROVING GROUNDS -- WEAPONS QUALIFICATION COURSE\n\nYour objective: assemble and qualify with both assigned weapon systems. P226 pistol and AR-15 rifle. Load your magazines, load your weapons, and put rounds on target.\n\nReport to the armory to begin.",
  "win_text": "QUALIFICATION COMPLETE\n\nBoth weapon systems qualified. You are cleared to proceed.\n\nFinal score: {score} / {max_score}",
  "lose_text": null,
  "region_count": 1,
  "max_nesting_depth": 3
}
```

---

## 12. Cross-Loading Rejection Matrix

This table documents every invalid cross-loading attempt and the expected rejection message. These are all handled by the `accepts_items` whitelist on each container -- no DSL commands needed.

| Player Action | Target Container | Item | In Whitelist? | Result |
|---|---|---|---|---|
| `put 9mm in p226 mag` | p226_magazine | 9mm_ammo | Yes | Success |
| `put 556 in p226 mag` | p226_magazine | 556_ammo | No | "That ammo doesn't fit this magazine." |
| `put 556 in ar15 mag` | ar15_magazine | 556_ammo | Yes | Success |
| `put 9mm in ar15 mag` | ar15_magazine | 9mm_ammo | No | "That ammo doesn't fit this magazine." |
| `put p226 mag in p226` | p226 | p226_magazine | Yes | Success |
| `put ar15 mag in p226` | p226 | ar15_magazine | No | "That magazine doesn't fit the P226." |
| `put p226 mag in ar15` | ar15 | p226_magazine | No | "That magazine doesn't fit the AR-15." |
| `put ar15 mag in ar15` | ar15 | ar15_magazine | Yes | Success |
| `put p226 in p226` | p226 | p226 | No (self) | Cycle detection: "You can't put something inside itself." |
| `put ar15 in weapons locker` | weapons_locker | ar15 | Yes (null = any) | Success |
| `put p226 in weapons locker` | weapons_locker | p226 | Yes (null = any) | Success |
| `put 9mm in weapons locker` | weapons_locker | 9mm_ammo | Yes (null = any) | Success |

---

## 13. Walkthrough

### Optimal Path (minimum moves)

**Starting room: Armory**

```
1.  look
    -- See room description + item room_descriptions (P226, P226 magazine,
       9mm ammo, AR-15 magazine, 5.56mm ammo, locker key, weapons locker)

2.  take locker key
    -- "You take the locker key."

3.  open weapons locker
    -- Engine auto-uses locker_key: "You turn the key in the padlock..."

4.  search weapons locker
    -- "Inside the weapons locker: AR-15 rifle"

5.  take ar15
    -- "You pick up the AR-15. It's heavier than the pistol."

6.  take p226
    -- "You pick up the P226. It has good weight."

7.  take p226 magazine
    -- "You pick up the P226 magazine."

8.  take 9mm ammo
    -- "You pick up the box of 9mm ammo."

9.  take ar15 magazine
    -- "You pick up the AR-15 magazine."

10. take 556 ammo
    -- "You pick up the box of 5.56mm ammo."

11. load p226 magazine
    -- "You press the 9mm rounds into the P226 magazine..."
    -- (9mm_ammo moves into p226_magazine container)

12. load p226
    -- "You slam the loaded magazine into the P226's grip..."
    -- (p226_magazine moves into p226 container, p226_assembled flag set)

13. load ar15 magazine
    -- "You push the 5.56mm rounds into the AR-15 magazine..."
    -- (556_ammo moves into ar15_magazine container)

14. load ar15
    -- "You rock the loaded magazine into the AR-15's mag well..."
    -- (ar15_magazine moves into ar15 container, ar15_assembled flag set)

15. east
    -- Move to Firing Range.

16. shoot pistol target
    -- "You raise the P226, align the sights, and squeeze..."
    -- (p226_qualified flag set, 15 points, p226_qualification puzzle solved)

17. shoot rifle target
    -- "You shoulder the AR-15, press your cheek to the stock..."
    -- (ar15_qualified flag set, 15 points, ar15_qualification puzzle solved)
    -- State lock auto-checks: both flags true -> range_exit_lock unlocks.
    -- "The panel beside the exit door flashes green: QUALIFICATION COMPLETE..."

18. south
    -- Move to Exit Corridor. first_visit_text fires.
    -- "You push through the door and daylight floods in..."
    -- Win condition met. Game ends.
```

**Score: 40/45** (missed optional ear protection)

### Optional: Ear Protection Side Path

Insert between steps 14 and 15 (or at any point):

```
a.  east
    -- Move to Firing Range.

b.  north
    -- Move to Range Office.

c.  talk to chen
    -- Dialogue tree root. Chen explains the qualification.

d.  (select "I need the supply crate key.")
    -- Chen gives you the key. has_crate_key flag set, crate_key spawned.

e.  (select "Nothing. I'm good." to end dialogue)

f.  open supply crate
    -- Engine auto-uses crate_key: "The key turns and the latches pop open."

g.  search supply crate
    -- "Inside the supply crate: ear protection"

h.  take ear protection
    -- "You take the ear protection. Safety first."
    -- (has_ear_protection flag set, 5 points)

i.  south
    -- Back to Firing Range.
```

**Score with optional: 45/45**

### Full Walkthrough With All Content

```
 1. [armory]         look
 2. [armory]         take locker key
 3. [armory]         open weapons locker
 4. [armory]         search weapons locker
 5. [armory]         take ar15
 6. [armory]         take p226
 7. [armory]         take p226 magazine
 8. [armory]         take 9mm ammo
 9. [armory]         take ar15 magazine
10. [armory]         take 556 ammo
11. [armory]         load p226 magazine
12. [armory]         load p226
13. [armory]         load ar15 magazine
14. [armory]         load ar15
15. [armory]         east                    -> firing_range
16. [firing_range]   examine pistol target
17. [firing_range]   examine rifle target
18. [firing_range]   examine safety poster
19. [firing_range]   north                   -> range_office
20. [range_office]   talk to chen
21. [range_office]   (select "Where are the weapons?")
22. [range_office]   (select "Got it. What else?")
23. [range_office]   (select "I need the supply crate key.")
24. [range_office]   (select "Thanks. Anything else?")
25. [range_office]   (select "Nothing. I'm good.")
26. [range_office]   open supply crate
27. [range_office]   search supply crate
28. [range_office]   take ear protection
29. [range_office]   examine ear protection
30. [range_office]   south                   -> firing_range
31. [firing_range]   shoot pistol target
32. [firing_range]   north                   -> range_office
33. [range_office]   talk to chen
34. [range_office]   (select "I've qualified with the P226.")
35. [range_office]   (select "Will do.")
36. [range_office]   south                   -> firing_range
37. [firing_range]   shoot rifle target
38. [firing_range]   south                   -> exit_corridor (lock opens)
39. [exit_corridor]  -- WIN --
```

**Final score: 45/45**

---

## 14. Negative Test Cases

These are interactions the implementer should verify produce the correct rejection behavior.

### Cross-Loading (whitelist rejection)

| Input | Expected Output |
|---|---|
| `put 556 ammo in p226 magazine` | "That ammo doesn't fit this magazine." |
| `put 9mm ammo in ar15 magazine` | "That ammo doesn't fit this magazine." |
| `put ar15 magazine in p226` | "That magazine doesn't fit the P226." |
| `put p226 magazine in ar15` | "That magazine doesn't fit the AR-15." |

### Missing Prerequisites

| Input | Context | Expected Output |
|---|---|---|
| `load p226` | Magazine not loaded with ammo | "You need the P226 and a loaded P226 magazine to do that." |
| `load p226` | Magazine not in inventory | "You need the P226 and a loaded P226 magazine to do that." |
| `shoot pistol target` | Not at firing range | "You need a loaded P226 pistol and you need to be at the firing range." |
| `shoot pistol target` | Gun not loaded | "You need a loaded P226 pistol and you need to be at the firing range." |
| `south` (from firing range) | Not yet qualified | "The exit door is sealed. A panel beside it reads: QUALIFICATION INCOMPLETE..." |

### Double Actions (one-shot / precondition guards)

| Input | Context | Expected Output |
|---|---|---|
| `shoot pistol target` | Already qualified | "You've already qualified with the P226." |
| `shoot rifle target` | Already qualified | "You've already qualified with the AR-15." |
| `load p226 magazine` | Already loaded | Precondition `not_item_in_container` fails: "You need the P226 magazine and 9mm ammo to load it." |

### Container State

| Input | Context | Expected Output |
|---|---|---|
| `search weapons locker` | Locker still locked | "The weapons locker is padlocked shut. You need a key." |
| `take ar15` | Locker still locked/closed | Cannot reach item inside locked container |
| `open supply crate` | No crate key | "The supply crate is locked. You need the key from Sergeant Chen." |

### Self-Insertion (cycle detection)

| Input | Expected Output |
|---|---|
| `put p226 in p226` | "You can't put something inside itself." |

---

## 15. Engine Feature Coverage Checklist

| Feature | Test Case | Section |
|---------|-----------|---------|
| Nested container (3-level: gun > mag > ammo) | P226 system, AR-15 system | 3.1, 3.2 |
| `accepts_items` whitelist | All weapons and magazines | 3.1, 3.2 |
| `reject_message` custom text | Cross-loading attempts | 12 |
| `has_lid: 0` (always accessible) | All guns and magazines | 3.1, 3.2 |
| `has_lid: 1` (must open) | weapons_locker, supply_crate | 3.3 |
| Flat container (`accepts_items: null`) | weapons_locker | 3.3 |
| Locked container (`is_locked`, `key_item_id`) | weapons_locker, supply_crate | 3.3 |
| State-based exit lock | range_exit_lock | 7.1 |
| `move_item_to_container` effect | All load commands | 6.1-6.4 |
| `take_item_from_container` effect | All unload commands | 6.7-6.10 |
| `item_in_container` precondition | Load-gun, shoot commands | 6.3-6.6 |
| `not_item_in_container` precondition | Load-magazine, load-gun commands | 6.1-6.4 |
| `container_has_contents` precondition | (Available for extension) | -- |
| `container_empty` precondition | (Available for extension) | -- |
| NPC dialogue tree (branching) | Sergeant Chen | 4 |
| Flag-gated dialogue option | Qualification reports | 4 |
| Excluded-flag dialogue option | Crate key (disappears after given) | 4 |
| Dialogue sets flags | `talked_to_chen`, `has_crate_key` | 4 |
| Quest with objectives | Weapons Qualification | 5 |
| Optional quest objective | Ear protection | 5 |
| `spawn_item` effect | crate_key | 6.11 |
| `add_score` effect | Shoot commands | 6.5, 6.6 |
| `solve_puzzle` effect | Shoot commands | 6.5, 6.6 |
| `set_flag` with value:false | Unload commands | 6.7, 6.8 |
| `one_shot` with `done_message` | Shoot commands | 6.5, 6.6 |
| `context_room_ids` | Shoot commands | 6.5, 6.6 |
| `first_visit_text` | armory (start), exit_corridor (win) | 2 |
| Room `is_start` | armory | 2 |
| `room_description` on items | All items | 3 |
| Non-takeable scenery items | Targets, safety poster | 3.4 |
| `read_description` | safety poster | 3.4 |
| Bidirectional exits | All connections | 2 |
| Custom verbs (load, shoot, unload) | All DSL commands | 6 |
| Win condition (flag-based) | `p226_qualified` + `ar15_qualified` | 11 |
| `container_has_contents` precondition | Not used (available) | -- |
| `container_empty` precondition | Not used (available) | -- |

**Note on `container_has_contents` / `container_empty`:** These precondition types are defined in the nested-containers spec but are not strictly needed for this test world. The `item_in_container` precondition (which checks for a specific item) is sufficient because each container has a known, specific expected content. A future test world or generated game could exercise `container_has_contents` / `container_empty` for scenarios where the container's contents are variable (e.g., "is the bag empty?" without caring what was in it). If the implementer wants to exercise these now, the unload commands could use `container_has_contents` as an alternative to `item_in_container`:

```json
{"type": "container_has_contents", "container": "p226_magazine"}
```

This would be equivalent to `item_in_container` for the single-ammo-type case but exercises a different code path.
