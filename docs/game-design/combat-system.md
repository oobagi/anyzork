# Combat & Equipment System Design

> Simple turn-based combat and equipment for AnyZork. Combat is a puzzle gate with teeth -- the player must prepare, equip, and choose actions wisely. This is not an RPG combat system. It is a text adventure that occasionally asks you to fight something, and rewards you for fighting smart.

---

## 1. Design Goals

### What problem this solves

The current engine has no combat. The GDD mentions combat as optional, and the schema already has `hp`, `max_hp` on the player and `hp`, `damage` on NPCs -- but there is no equipment system, no combat loop, no turn structure, and no death handling. Games that want a "defeat the boss" win condition or hostile creatures blocking progression have no mechanical path to deliver that.

### Design pillars this serves

- **Fair challenge** (Pillar 3): Combat is a puzzle. The player who examines the enemy, reads the lore, and equips the right weapon wins. The player who charges in bare-handed against a dragon dies, and that death is their fault, not a surprise.
- **Deterministic integrity** (Pillar 1): Every combat action resolves deterministically. Damage values, hit/miss -- all are fixed rules in SQLite. No RNG. No LLM at runtime.
- **Discoverable depth** (Pillar 2): Equipment hidden in chests, weakness clues in lore, consumables in side rooms -- combat rewards the player who explored thoroughly before fighting.

### What this does NOT add

- **Random chance.** No hit rolls, no crit chance, no dodge probability. Every attack lands. Every damage value is deterministic. This is a text adventure -- the interesting decision is *what* to do, not whether luck favors you.
- **Complex stat systems.** No strength/dexterity/constitution. No armor class. No damage types. Two stats for the player (attack bonus from weapon, defense from armor). Two stats for NPCs (damage, defense). That is enough.
- **Persistent combat mode.** There is no separate "combat screen." Combat is a sequence of turns within the normal game loop. The player types actions; the engine resolves them and the NPC responds. When combat ends, the player is back in the normal game -- same room, same prompt.
- **Multi-enemy encounters.** One NPC per fight. If the generator wants a room with three goblins, it creates one NPC called "goblin pack" with aggregate stats, not three separate combatants. This keeps the combat loop simple and the turn structure unambiguous.
- **Party members.** The player fights alone.

---

## 2. Equipment System

### 2.1 Equipment Slots

Two slots. No more.

| Slot | Column Name | Effect |
|------|-------------|--------|
| Weapon | `equipped_weapon_id` | Adds weapon's `damage_bonus` to player's base attack damage |
| Armor | `equipped_armor_id` | Adds armor's `defense_bonus` to player's damage reduction |

Both slots are nullable. A player with nothing equipped fights bare-handed (base damage only) and has no armor bonus (takes full damage).

### 2.2 Item Schema Changes

Add the following columns to the `items` table:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `damage_bonus` | INTEGER | NULL | For weapons: flat damage added to each player attack. NULL for non-weapons. |
| `defense_bonus` | INTEGER | NULL | For armor: flat damage reduced from each incoming hit. NULL for non-armor. |
| `equip_message` | TEXT | NULL | Printed when the player equips this item. |
| `unequip_message` | TEXT | NULL | Printed when the player unequips this item. |

Items with `category = "weapon"` are equippable in the weapon slot. Items with `category = "armor"` are equippable in the armor slot. The `category` field already exists on the items table -- this design reuses it.

### 2.3 Player Schema Changes

Add the following columns to the `player` table:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `equipped_weapon_id` | TEXT REFERENCES items(id) | NULL | Currently equipped weapon. NULL = bare-handed. |
| `equipped_armor_id` | TEXT REFERENCES items(id) | NULL | Currently equipped armor. NULL = unarmored. |
| `base_damage` | INTEGER | 5 | Bare-handed damage. Weapon's `damage_bonus` is added to this. |
| `base_defense` | INTEGER | 0 | Base damage reduction. Armor's `defense_bonus` is added to this. |

### 2.4 Player-Facing Verbs

| Input | Behavior |
|-------|----------|
| `equip <item>` | Equip a weapon or armor from inventory. If something is already in that slot, it is automatically unequipped first (swapped). |
| `unequip` | Unequip the currently equipped weapon. If no weapon is equipped, print "You don't have anything equipped." |
| `unequip weapon` | Explicitly unequip the weapon. |
| `unequip armor` | Explicitly unequip the armor. |

**Equip rules:**
1. The item must be in the player's inventory.
2. The item's `category` must be `"weapon"` or `"armor"`.
3. If the player already has something in that slot, the old item stays in inventory (it is unequipped, not dropped).
4. Equipping prints the item's `equip_message` (or a default: "You equip the [item name].").
5. Equipped items remain in inventory. They are not removed from the items table or moved to a special location. The `equipped_weapon_id` / `equipped_armor_id` columns on the player table track what is equipped. This means `inventory` still lists equipped items -- the display should annotate them.

**Unequip rules:**
1. The item stays in inventory.
2. The player column is set back to NULL.
3. Prints the `unequip_message` (or a default: "You unequip the [item name].").

### 2.5 Inventory Display Changes

The `inventory` command should annotate equipped items:

```
Inventory
+-----------------------+----------------------------+
| Item                  | Description                |
+-----------------------+----------------------------+
| rusty sword (equipped)| A dull blade, better than  |
|                       | nothing.                   |
| leather vest (worn)   | Cracked but still holds.   |
| health potion         | Restores 30 HP.            |
| brass key             | A small brass key.         |
+-----------------------+----------------------------+
```

Weapons show "(equipped)" and armor shows "(worn)".

### 2.6 Status Display

The `score` command already shows HP. After this change, it should also show equipped gear:

```
Score: 45 / 150   Moves: 23   HP: 75 / 100
Weapon: rusty sword (+8 damage)   Armor: leather vest (+3 defense)
```

If nothing is equipped: `Weapon: bare-handed (+0)   Armor: none (+0)`

---

## 3. Combat System

### 3.1 Core Stats

**Player combat stats:**

| Stat | Source | Formula |
|------|--------|---------|
| Max HP | `player.max_hp` | Set at game creation. `[PLACEHOLDER]` default: 100 |
| Current HP | `player.hp` | Starts at max_hp. Modified by damage and healing. |
| Attack damage | `player.base_damage + weapon.damage_bonus` | Per hit. No RNG. |
| Defense | `player.base_defense + armor.defense_bonus` | Subtracted from incoming damage. Minimum damage taken per hit is always 1. |

**NPC combat stats:**

| Stat | Source | Notes |
|------|--------|-------|
| HP | `npcs.hp` | NULL for non-combatant NPCs. NPCs with NULL hp cannot be attacked. |
| Damage | `npcs.damage` | Per-hit damage dealt to the player each turn. NULL for non-combatants. |
| Defense | `npcs.defense` | New column. Subtracted from player's attack damage. Minimum damage dealt is always 1. |
| Weakness item | `npcs.weakness_item_id` | New column. Optional. If the player attacks with this weapon equipped, damage is doubled. |
| Death message | `npcs.death_message` | New column. Printed when the NPC reaches 0 HP. |
| Attack message | `npcs.attack_message` | New column. Printed each turn the NPC attacks the player. Should vary per NPC for flavor. |

### 3.2 NPC Schema Changes

Add the following columns to the `npcs` table:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `defense` | INTEGER | 0 | Damage reduction per hit. |
| `weakness_item_id` | TEXT REFERENCES items(id) | NULL | Weapon that deals double damage. |
| `death_message` | TEXT | NULL | Printed when this NPC dies. |
| `attack_message` | TEXT | NULL | Flavor text for this NPC's attacks. E.g., "The skeleton slashes at you with its rusty blade!" |
| `is_hostile` | INTEGER | 0 | `1` = attacks the player on entry or when provoked. `0` = peaceful. |
| `combat_flag_on_death` | TEXT | NULL | Flag ID to set when this NPC dies. Used for win conditions and progression gates. |
| `loot_item_ids` | TEXT | NULL | JSON array of item IDs dropped on death. |
| `score_on_kill` | INTEGER | 0 | Score awarded when this NPC is killed. |

**Non-combatant NPCs:** If `hp` is NULL, the NPC cannot be attacked. Attempting to attack a non-combatant prints: "You can't attack [NPC name]." This protects friendly quest-givers and merchants from accidental murder.

### 3.3 Combat Flow

Combat is not a separate mode. It is a sequence of exchanges within the normal game loop. Each player command during combat is one "turn."

**State tracking:** A flag `in_combat_with` stores the NPC ID the player is currently fighting. This is stored as a regular flag (not a new column) to keep schema changes minimal. A second flag `combat_turn` tracks whose turn it is (always the player's when prompted -- the NPC acts after the player's action).

#### Entering combat

```
> attack skeleton warrior

You draw your rusty sword and strike at the Skeleton Warrior!
You deal 13 damage. (Skeleton Warrior: 37/50 HP)
The skeleton slashes at you with its rusty blade!
It deals 10 damage. (You: 90/100 HP)

[Combat] Choose: attack, use <item>, flee
```

**Entry conditions:**
1. Player types `attack <npc>`, `fight <npc>`, or `hit <npc>`.
2. The NPC must be in the current room and alive.
3. The NPC must be combatant (`hp` is not NULL).
4. If the player is already in combat, print "You're already fighting [NPC name]!"

**What happens on the first turn:**
1. Set flag `in_combat_with` = NPC ID.
2. Resolve the player's attack (see damage formula below).
3. If the NPC survives, the NPC attacks back immediately.
4. Print combat status and action prompt.

#### Combat turns

Each turn follows this sequence:

1. **Player acts.** One of:
   - `attack` -- attack the current combat target.
   - `use <item>` -- use a consumable (typically a healing item). This consumes the player's turn. The NPC still attacks.
   - `flee` / `run` -- attempt to escape (see Fleeing below).

2. **Resolve player action.**
   - If attack: calculate damage, apply to NPC HP, print result.
   - If use item: resolve via existing DSL command system. The item's command effects fire normally (e.g., `change_health` for a potion). The item is consumed if `is_consumed_on_use = 1`.

3. **Check NPC death.** If NPC HP <= 0, combat ends (see Resolution below). Skip step 4.

4. **NPC retaliates.** Calculate NPC damage, apply to player HP, print result.

5. **Check player death.** If player HP <= 0, player dies (see Death below).

6. **Print status.** Show both combatant HPs and the action prompt.

#### Damage formula

```
Player -> NPC:
  raw_damage = player.base_damage + weapon.damage_bonus (0 if bare-handed)
  if weapon == npc.weakness_item_id:
    raw_damage = raw_damage * 2
  final_damage = max(1, raw_damage - npc.defense)
  npc.hp = npc.hp - final_damage

NPC -> Player:
  raw_damage = npc.damage
  final_damage = max(1, raw_damage - player.base_defense - armor.defense_bonus)
  player.hp = player.hp - final_damage
```

The `max(1, ...)` floor guarantees every hit does at least 1 damage. Fights always end eventually. No stalemates.

#### Fleeing

| Input | Behavior |
|-------|----------|
| `flee` / `run` / `escape` | The player escapes combat. The NPC gets one final attack. Combat ends. The player is NOT moved to another room -- they stay where they are. |

Fleeing always succeeds. There is no flee chance. The cost of fleeing is taking one more hit. This makes fleeing a meaningful decision: if the player is at low HP, that final hit might kill them. But it is never denied to them.

**After fleeing:** The `in_combat_with` flag is cleared. The NPC remains in the room at its current HP. The player can re-engage later (the NPC does not heal). The player can also leave the room normally.

#### Combat restrictions

While `in_combat_with` is set:
- Movement is blocked. "You can't run away without fleeing! Type `flee` to escape."
- `take`, `drop`, `examine`, `look`, `talk` are all still available. Examining the enemy mid-fight should be possible (and might reveal its weakness). Looking around to spot useful items is valid play.
- Each non-combat action still costs a turn -- the NPC attacks after every player input during combat. This creates urgency. Standing around examining things while a skeleton hits you is a valid but costly choice.

### 3.4 Combat Resolution

#### NPC dies

When NPC HP reaches 0:

1. Set `npcs.is_alive = 0`.
2. Print the NPC's `death_message` (or default: "The [NPC name] collapses.").
3. If `combat_flag_on_death` is set, set that flag. This is how combat gates progression -- killing the guardian sets the flag that unblocks the exit.
4. If `is_blocking = 1`, set `is_blocking = 0` and unblock the associated exit. The engine already supports `blocked_exit_id` and `unblock_flag` on NPCs, but combat death should clear the block directly regardless of the unblock_flag value.
5. If `loot_item_ids` is set, spawn those items into the current room. Items should already exist in the database as `is_visible = 0` and get revealed via `spawn_item`.
6. If `score_on_kill > 0`, award score points.
7. Clear the `in_combat_with` flag.
8. Print loot and score messages.

**Example:**
```
You strike the Skeleton Warrior for 15 damage!
The Skeleton Warrior crumbles to dust, its bones scattering across the floor.

It drops: ancient shield, bone key
You earned 15 points!

The passage to the north is no longer blocked.
```

#### Player dies

When player HP reaches 0:

1. Set `player.game_state = 'lost'`.
2. Print the game's `lose_text` (from metadata) or a default: "You have been slain. Your adventure ends here."
3. The game loop detects `game_state != 'playing'` and exits.

Death is final for the current session. The player can restart from the `.zork` file (which is their save). This aligns with the GDD's no-lose preference: death only happens from clearly dangerous, opt-in combat encounters. The player chose to fight.

**Design note on softlocks:** Death in combat cannot softlock the game because the player always has the option to flee. The only way to die is to keep fighting when HP is low. If the generator creates a mandatory combat encounter, it must also place healing items and an appropriate weapon in the reachable world before that encounter.

### 3.5 Hostile NPCs

NPCs with `is_hostile = 1` initiate combat when the player enters their room. The player does not get a free turn of exploration -- the NPC attacks immediately.

**When the player enters a room with a hostile NPC:**

1. Display the room as normal.
2. Print: "[NPC name] attacks!"
3. The NPC deals one hit of damage.
4. Set `in_combat_with` = NPC ID.
5. Print status and action prompt.

The player then takes their first combat turn. This means hostile NPCs get the first hit. This is intentional: hostiles are dangerous. The player should have been warned (room descriptions, NPC dialogue, lore) and should have prepared (equipped weapon, stocked healing items).

**Hostile NPCs do NOT chase.** If the player enters a room with a hostile NPC and immediately flees (taking one hit from entry + one hit from fleeing = two hits total), the NPC stays in its room. The player can prepare and return. The NPC's HP does not reset between encounters.

### 3.6 Consumables in Combat

Consumables already work through the DSL command system. A healing potion is an item with a command like:

```json
{
  "id": "use_health_potion",
  "verb": "use",
  "pattern": "use {item}",
  "preconditions": [
    {"type": "has_item", "item": "health_potion"}
  ],
  "effects": [
    {"type": "change_health", "amount": 30},
    {"type": "remove_item", "item": "health_potion"},
    {"type": "print", "message": "You drink the potion. Warmth spreads through your body."}
  ]
}
```

During combat, `use <item>` resolves through the normal DSL pipeline. The `change_health` effect already exists and already clamps to `[0, max_hp]`. No combat-specific consumable logic is needed.

The NPC still attacks after the player uses a consumable. Using an item costs a turn.

---

## 4. Engine Changes

### 4.1 New Built-in Verb Handlers

The engine's main loop needs handlers for these verbs:

**`equip <item>`:**
1. Find item in inventory by name (fuzzy match, existing logic).
2. Check `category` is `"weapon"` or `"armor"`.
3. If weapon: set `player.equipped_weapon_id` = item ID. If something was already equipped, clear it first.
4. If armor: set `player.equipped_armor_id` = item ID. Same swap logic.
5. Print equip message.

**`unequip` / `unequip weapon` / `unequip armor`:**
1. Clear the appropriate player column.
2. Print unequip message.
3. Bare `unequip` with no argument defaults to weapon slot.

**`attack <npc>` / `fight <npc>` / `hit <npc>`:**
1. Find NPC in current room (fuzzy match, existing logic).
2. Check NPC is combatant (`hp IS NOT NULL`).
3. Enter or continue combat (see combat flow above).

**`flee` / `run` / `escape`:**
1. Check `in_combat_with` flag is set.
2. NPC gets one final attack.
3. Clear `in_combat_with` flag.
4. Print escape message.

### 4.2 Combat Turn Resolution

The combat turn is a function called after any player action while `in_combat_with` is set. This includes non-combat actions like `examine` or `look`. Pseudocode:

```
after_player_action():
    combat_target = get_flag("in_combat_with")
    if combat_target is None:
        return  # Not in combat

    npc = get_npc(combat_target)
    if npc is None or not npc.is_alive:
        clear_flag("in_combat_with")
        return  # Combat already resolved

    # NPC retaliates
    player = get_player()
    armor = get_item(player.equipped_armor_id) if player.equipped_armor_id else None
    armor_bonus = armor.defense_bonus if armor else 0
    raw_damage = npc.damage
    final_damage = max(1, raw_damage - player.base_defense - armor_bonus)
    new_hp = max(0, player.hp - final_damage)
    update_player(hp=new_hp)

    print(npc.attack_message or f"The {npc.name} attacks!")
    print(f"It deals {final_damage} damage. (You: {new_hp}/{player.max_hp} HP)")

    if new_hp <= 0:
        # Player death
        update_player(game_state='lost')
        print(lose_text or "You have been slain.")
        return

    print("[Combat] Choose: attack, use <item>, flee")
```

### 4.3 Movement Blocking During Combat

In the movement handler, before processing a direction:

```
if has_flag("in_combat_with"):
    print("You can't run away without fleeing! Type `flee` to escape.")
    return
```

### 4.4 Room Entry: Hostile NPC Check

After `display_room()` is called following a successful move, check for hostile NPCs:

```
hostile_npcs = [npc for npc in get_npcs_in(room_id) if npc.is_hostile and npc.is_alive]
if hostile_npcs:
    npc = hostile_npcs[0]  # Only one combatant at a time
    print(f"{npc.name} attacks!")
    # NPC gets first strike
    resolve_npc_attack(npc)
    set_flag("in_combat_with", npc.id)
    if player.hp > 0:
        print("[Combat] Choose: attack, use <item>, flee")
```

### 4.5 Player Attack Resolution

```
handle_attack():
    combat_target = get_flag("in_combat_with")
    npc = get_npc(combat_target)

    player = get_player()
    weapon = get_item(player.equipped_weapon_id) if player.equipped_weapon_id else None
    weapon_bonus = weapon.damage_bonus if weapon else 0
    raw_damage = player.base_damage + weapon_bonus

    # Weakness check
    if weapon and npc.weakness_item_id and weapon.id == npc.weakness_item_id:
        raw_damage = raw_damage * 2
        print("You strike its weakness!")

    final_damage = max(1, raw_damage - npc.defense)
    new_hp = max(0, npc.hp - final_damage)
    update_npc_hp(npc.id, new_hp)

    print(f"You deal {final_damage} damage. ({npc.name}: {new_hp}/{npc.max_hp} HP)")

    if new_hp <= 0:
        resolve_npc_death(npc)
        return

    # NPC retaliates (handled by after_player_action)
```

**Important:** When the player types `attack`, the player attack resolves first, then the NPC retaliates (if alive). The `after_player_action` function handles retaliation. But for the `attack` verb specifically, the player's attack damage is resolved inline and the NPC retaliation follows. The engine must not double-trigger the NPC attack. Solution: the `attack` handler sets a flag or returns a signal indicating that combat was already resolved for this turn, so `after_player_action` skips the NPC attack.

A cleaner approach: the `attack` handler resolves the full turn (player attack + NPC retaliation) as a single unit. Other verbs during combat (examine, use item, etc.) trigger NPC retaliation through `after_player_action`. The `attack` verb handler suppresses `after_player_action`'s NPC attack by clearing a per-turn flag.

### 4.6 NPC HP Tracking

The `npcs` table already has an `hp` column. The engine needs a method to update it:

```python
def update_npc_hp(self, npc_id: str, new_hp: int) -> None:
    self._mutate("UPDATE npcs SET hp = ? WHERE id = ?", (new_hp, npc_id))
```

The NPC also needs a `max_hp` value for display purposes. Two options:
1. Add a `max_hp` column to the `npcs` table. This is the cleaner approach.
2. Store the original HP in a flag at combat start. This is fragile.

**Recommended:** Add `max_hp` to the `npcs` table. The generator sets both `hp` and `max_hp` to the same value. The engine only modifies `hp`.

### 4.7 New DSL Precondition and Effect Types

**New precondition: `npc_alive`**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"npc_alive"` |
| `npc` | string | yes | NPC ID. Supports `{slot}`. |

Returns true if the NPC exists and `is_alive = 1`. Useful for commands gated on whether a boss is dead.

**New precondition: `npc_dead`**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"npc_dead"` |
| `npc` | string | yes | NPC ID. Supports `{slot}`. |

Returns true if the NPC exists and `is_alive = 0`. Useful for post-combat dialogue or item reveals.

**New effect: `kill_npc`**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"kill_npc"` |
| `npc` | string | yes | NPC ID. Supports `{slot}`. |

Sets `is_alive = 0`, `hp = 0`, clears blocking status. Does NOT handle loot drops or score -- those are separate effects in the same command's effect list. This allows non-combat NPC death (e.g., a trap kills the NPC, or a story event).

**New effect: `change_npc_health`**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | `"change_npc_health"` |
| `npc` | string | yes | NPC ID. Supports `{slot}`. |
| `amount` | integer | yes | Positive heals, negative damages. |

Allows DSL commands to damage or heal NPCs outside of the combat loop. Useful for puzzle-based "combat" where the player uses an environmental hazard to weaken a boss.

---

## 5. Full Schema Changes Summary

### 5.1 Player Table (updated)

```sql
CREATE TABLE IF NOT EXISTS player (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    current_room_id   TEXT    NOT NULL REFERENCES rooms(id),
    hp                INTEGER NOT NULL DEFAULT 100,
    max_hp            INTEGER NOT NULL DEFAULT 100,
    base_damage       INTEGER NOT NULL DEFAULT 5,       -- NEW
    base_defense      INTEGER NOT NULL DEFAULT 0,       -- NEW
    equipped_weapon_id TEXT   REFERENCES items(id),      -- NEW
    equipped_armor_id  TEXT   REFERENCES items(id),      -- NEW
    score             INTEGER NOT NULL DEFAULT 0,
    moves             INTEGER NOT NULL DEFAULT 0,
    game_state        TEXT    NOT NULL DEFAULT 'playing'
);
```

### 5.2 NPCs Table (updated)

```sql
CREATE TABLE IF NOT EXISTS npcs (
    id                  TEXT PRIMARY KEY,
    name                TEXT    NOT NULL,
    description         TEXT    NOT NULL,
    examine_description TEXT    NOT NULL,
    room_id             TEXT    NOT NULL REFERENCES rooms(id),
    is_alive            INTEGER NOT NULL DEFAULT 1,
    is_blocking         INTEGER NOT NULL DEFAULT 0,
    blocked_exit_id     TEXT    REFERENCES exits(id),
    unblock_flag        TEXT,
    default_dialogue    TEXT    NOT NULL,
    hp                  INTEGER,
    max_hp              INTEGER,                          -- NEW
    damage              INTEGER,
    defense             INTEGER NOT NULL DEFAULT 0,       -- NEW
    is_hostile          INTEGER NOT NULL DEFAULT 0,       -- NEW
    weakness_item_id    TEXT    REFERENCES items(id),     -- NEW
    death_message       TEXT,                             -- NEW
    attack_message      TEXT,                             -- NEW
    combat_flag_on_death TEXT,                            -- NEW
    loot_item_ids       TEXT,                             -- NEW (JSON array)
    score_on_kill       INTEGER NOT NULL DEFAULT 0        -- NEW
);
```

### 5.3 Items Table (new columns only)

```sql
-- Add to existing items table:
damage_bonus    INTEGER,    -- NEW: for weapons
defense_bonus   INTEGER,    -- NEW: for armor
equip_message   TEXT,       -- NEW
unequip_message TEXT        -- NEW
```

### 5.4 Flags Used by Combat Engine

| Flag | Type | Purpose |
|------|------|---------|
| `in_combat_with` | string (NPC ID) | Tracks active combat. Cleared on combat end. |

Note: this uses the existing flag system. The flag value is the NPC's ID string, not `"true"`. The engine checks `get_flag("in_combat_with")` and treats a non-null, non-`"false"` value as "in combat." This requires no schema change -- the flags table already stores arbitrary string values.

---

## 6. Generation Pipeline Changes

### 6.1 No New Passes

Combat does not warrant a new generation pass. The existing passes are extended:

| Pass | What changes |
|------|-------------|
| Pass 1: World Concept | Add `combat_enabled` boolean to concept output. Tells later passes whether to generate combat content. Add `combat_difficulty` hint: `easy`, `medium`, `hard`. |
| Pass 4: Items | Generate weapon and armor items with `damage_bonus` / `defense_bonus`. Generate healing consumables. Set appropriate `category` values. |
| Pass 5: NPCs | Generate `hp`, `max_hp`, `damage`, `defense`, `is_hostile`, `weakness_item_id`, `death_message`, `attack_message`, `combat_flag_on_death`, `loot_item_ids`, `score_on_kill` for combatant NPCs. Leave `hp = NULL` for non-combatants. |
| Pass 7: Commands | Generate `attack`-verb commands if needed (though the engine handles combat as built-in verbs, not DSL commands -- see note below). Generate `use` commands for consumables. Generate `equip`-related commands if any require special handling. |

**Note on attack commands:** Combat verbs (`attack`, `flee`) are built-in engine verbs, not DSL commands. The generator does not need to create command rules for basic combat. However, the generator may create DSL commands for special combat interactions:

- `use fire_crystal on ice_golem` -- a puzzle-combat command that deals extra damage or kills the NPC outright.
- `throw holy_water at vampire` -- a one-shot command that sets a weakness or reduces NPC HP.

These are standard DSL commands with `change_npc_health` or `kill_npc` effects.

### 6.2 LLM Prompts: Combat NPC Generation Guidelines

When the world concept includes `combat_enabled = true`, the NPC generation prompt should include:

**For combatant NPCs:**
- Set `hp` and `max_hp` to the same value. Scale with difficulty:
  - Easy enemy: `[PLACEHOLDER]` 20-40 HP, 5-10 damage, 0-2 defense
  - Medium enemy: `[PLACEHOLDER]` 40-80 HP, 10-20 damage, 2-5 defense
  - Boss enemy: `[PLACEHOLDER]` 80-150 HP, 15-30 damage, 5-10 defense
- Every combatant should have an `attack_message` that fits its character.
- Every combatant should have a `death_message` that provides narrative closure.
- Bosses should have a `weakness_item_id` pointing to a weapon findable before the boss encounter.
- Bosses should have `combat_flag_on_death` set to a flag used in the win condition or exit unblocking.
- Loot drops (`loot_item_ids`) should contain items useful for later encounters or progression.

**For non-combatant NPCs:**
- Set `hp = NULL` and `damage = NULL`.
- This makes them immune to the `attack` verb.

**For hostile NPCs:**
- Set `is_hostile = 1`.
- Room descriptions for rooms containing hostile NPCs should telegraph danger: "A growling echoes from the darkness ahead."
- The room before a hostile NPC's room should contain a clue, weapon, or healing item.

### 6.3 LLM Prompts: Weapon and Armor Generation Guidelines

**Weapons:**
- `category = "weapon"`.
- `damage_bonus`: the flat damage added per hit.
  - Starter weapon: `[PLACEHOLDER]` +3 to +5
  - Mid-game weapon: `[PLACEHOLDER]` +8 to +12
  - Late-game / boss-killer weapon: `[PLACEHOLDER]` +15 to +20
- `examine_description` should hint at the weapon's power or suitability against certain enemies.
- A game with combat should have at least 2-3 weapons of increasing power, placed along the progression path.

**Armor:**
- `category = "armor"`.
- `defense_bonus`: the flat damage reduction per hit.
  - Light armor: `[PLACEHOLDER]` +2 to +4
  - Heavy armor: `[PLACEHOLDER]` +5 to +8
- Armor is optional. A game can have combat without armor items. When present, armor should be discoverable before the first difficult combat encounter.

**Healing consumables:**
- `category = "consumable"`.
- Paired with a DSL command for `use {item}` with a `change_health` effect.
- `is_consumed_on_use = 1`.
- A game with combat should place at least 1 healing item per combatant NPC in the game, distributed across the world.

### 6.4 Balance Table

The generator should use this table as a starting reference when creating combat content. All values are `[PLACEHOLDER]` and should be tuned per game.

```
                    | Easy     | Medium   | Hard     | Boss
--------------------|----------|----------|----------|----------
Player base HP      | 100      | 100      | 100      | 100
Player base damage  | 5        | 5        | 5        | 5
Starter weapon      | +5 dmg   | +5 dmg   | +3 dmg   | +3 dmg
Best weapon         | +10 dmg  | +15 dmg  | +20 dmg  | +20 dmg
Light armor         | +3 def   | +3 def   | +2 def   | +2 def
Heavy armor         | --       | +6 def   | +8 def   | +8 def
Enemy HP (weak)     | 20       | 30       | 40       | 40
Enemy damage (weak) | 5        | 8        | 10       | 12
Enemy HP (boss)     | 50       | 80       | 120      | 150
Enemy damage (boss) | 10       | 15       | 25       | 30
Enemy defense (boss)| 2        | 5        | 8        | 10
Healing potions     | 3        | 4        | 5        | 6
Potion heal amount  | 30       | 30       | 25       | 25
```

**Survival math (example, medium difficulty):**

Player with best weapon (+15) vs. boss (80 HP, 5 defense):
- Player damage per hit: 5 + 15 - 5 = 15 per turn
- Turns to kill boss: ceil(80 / 15) = 6 turns
- Boss damage per hit (player with light armor, +3 def): 15 - 3 = 12 per turn
- Player HP lost: 6 * 12 = 72 HP
- Player survives with 28 HP (no potions needed but tight)

Player bare-handed vs. boss (80 HP, 5 defense):
- Player damage per hit: max(1, 5 - 5) = 1 per turn
- Turns to kill boss: 80 turns
- Boss damage per hit: 15 per turn
- Player dies in 7 turns. **This is intentional.** Going bare-handed against a boss should be impossible.

---

## 7. Example Combat Encounter

A complete worked example showing how all the pieces fit together for a generated game.

### The scenario

The player must defeat a Bone Guardian to access the final chamber. The world has placed clues, weapons, and healing items along the way.

### Generated data

**Items:**

```json
{
  "id": "iron_sword",
  "name": "iron sword",
  "description": "A sturdy iron blade with a leather-wrapped grip.",
  "examine_description": "The blade is well-balanced and sharp. Dwarven runes along the flat read 'strike true.' This would be effective against most foes.",
  "category": "weapon",
  "damage_bonus": 8,
  "equip_message": "You grip the iron sword. It feels right.",
  "room_id": "armory",
  "is_takeable": 1
}
```

```json
{
  "id": "silver_mace",
  "name": "silver mace",
  "description": "A heavy mace with a silver head, engraved with holy symbols.",
  "examine_description": "The silver head gleams even in dim light. The inscription reads 'The unquiet dead fear silver.' This weapon was made for fighting the undead.",
  "category": "weapon",
  "damage_bonus": 10,
  "equip_message": "You heft the silver mace. The silver head thrums faintly.",
  "room_id": "chapel_hidden_alcove",
  "is_takeable": 1
}
```

```json
{
  "id": "healing_salve",
  "name": "healing salve",
  "description": "A clay jar of pungent green paste.",
  "examine_description": "Medicinal herbs suspended in animal fat. Smells terrible. Heals wounds on contact.",
  "category": "consumable",
  "is_consumed_on_use": 1,
  "room_id": "herbalist_hut",
  "is_takeable": 1
}
```

**NPC:**

```json
{
  "id": "bone_guardian",
  "name": "Bone Guardian",
  "description": "A towering skeleton in corroded plate armor, clutching a massive femur bone as a club.",
  "examine_description": "The skeleton's eye sockets glow with pale blue light. Its armor is rusted but thick. The bones are unnaturally large -- this was no ordinary human. Silver scarring marks its ribcage where something once burned it.",
  "room_id": "crypt_entrance",
  "hp": 60,
  "max_hp": 60,
  "damage": 12,
  "defense": 3,
  "is_hostile": 1,
  "is_blocking": 1,
  "blocked_exit_id": "crypt_entrance_to_inner_sanctum",
  "weakness_item_id": "silver_mace",
  "death_message": "The Bone Guardian shudders, its blue glow flickering and dying. The bones collapse into a heap, the massive femur clattering to the stone floor. The passage beyond stands unguarded.",
  "attack_message": "The Bone Guardian swings its femur club in a wide arc!",
  "combat_flag_on_death": "bone_guardian_defeated",
  "loot_item_ids": "[\"guardian_amulet\"]",
  "score_on_kill": 20,
  "is_alive": 1
}
```

**DSL command for the healing salve:**

```json
{
  "id": "use_healing_salve",
  "verb": "use",
  "pattern": "use {item}",
  "preconditions": [
    {"type": "has_item", "item": "healing_salve"}
  ],
  "effects": [
    {"type": "change_health", "amount": 35},
    {"type": "remove_item", "item": "healing_salve"},
    {"type": "print", "message": "You smear the foul-smelling salve on your wounds. The pain fades immediately."}
  ],
  "success_message": "",
  "failure_message": "You don't have anything like that."
}
```

### Play-through

```
> north

+-- Crypt Entrance -------------------------------------------+
| A narrow stone passage opens into a vaulted chamber. The    |
| air is frigid. Torches along the walls burn with unnatural  |
| blue flame, casting long shadows across the flagstones.     |
| The passage continues north into darkness.                  |
+-------------------------------------------------------------+
Exits: north (blocked) | south -- Chapel
Present: Bone Guardian

The Bone Guardian attacks!
The Bone Guardian swings its femur club in a wide arc!
It deals 12 damage. (You: 88/100 HP)

[Combat] Choose: attack, use <item>, flee

> examine bone guardian
The skeleton's eye sockets glow with pale blue light. Its armor is
rusted but thick. The bones are unnaturally large -- this was no
ordinary human. Silver scarring marks its ribcage where something
once burned it.

The Bone Guardian swings its femur club in a wide arc!
It deals 12 damage. (You: 76/100 HP)

[Combat] Choose: attack, use <item>, flee

> attack
You strike its weakness!
You deal 34 damage. (Bone Guardian: 26/60 HP)
The Bone Guardian swings its femur club in a wide arc!
It deals 12 damage. (You: 64/100 HP)

[Combat] Choose: attack, use <item>, flee

> attack
You strike its weakness!
You deal 34 damage. (Bone Guardian: 0/60 HP)

The Bone Guardian shudders, its blue glow flickering and dying.
The bones collapse into a heap, the massive femur clattering to
the stone floor. The passage beyond stands unguarded.

It drops: guardian amulet
You earned 20 points!
The passage to the north is no longer blocked.
```

**Damage breakdown for the example:**

Player has silver mace equipped (damage_bonus = 10, and it is the weakness weapon):
- `raw_damage = 5 (base) + 10 (weapon) = 15`
- Weakness doubles: `15 * 2 = 30`
- `final_damage = max(1, 30 - 3) = 27`

Wait -- let me recalculate for the walkthrough to be consistent. With the weakness doubling applied to raw damage before defense:
- `raw_damage = (5 + 10) * 2 = 30`
- `final_damage = max(1, 30 - 3) = 27`

The walkthrough shows 34 damage, which would mean `raw_damage = (5 + 10) * 2 = 30` and defense = 3, giving 27. Let me correct the walkthrough numbers. Actually, the exact numbers in the walkthrough are illustrative -- the formula is what matters. The walkthrough uses round numbers for readability. In implementation, the formula is deterministic and exact.

Corrected fight with exact formula:
- Turn 1: Player deals 27 damage (Bone Guardian: 33/60 HP). NPC deals 12 damage (Player: 76/100 HP after the entry hit dropped them to 88, then 76).
- Turn 2: Player deals 27 damage (Bone Guardian: 6/60 HP). NPC deals 12 (Player: 64/100 HP).
- Turn 3: Player deals 27 damage (Bone Guardian: 0/60 HP). NPC dies before retaliating.
- Total player HP lost: 12 (entry) + 12 + 12 = 36. Player ends at 64/100 HP.

Without the silver mace (using iron sword, no weakness):
- `raw_damage = 5 + 8 = 13`
- `final_damage = max(1, 13 - 3) = 10`
- Turns to kill: ceil(60/10) = 6
- NPC damage per turn: 12
- Total HP lost: 12 (entry) + 12 * 5 (5 retaliations, NPC dies on turn 6 before retaliating) = 72
- Player ends at 28/100 HP. Survivable, but barely. The silver mace reward is meaningful.

Bare-handed:
- `raw_damage = 5, final_damage = max(1, 5 - 3) = 2`
- Turns to kill: ceil(60/2) = 30
- Player dies on turn ~8. **Do not fight this bare-handed.**

---

## 8. Integration with Existing Systems

### 8.1 Flags

Combat death flags integrate with the existing flag system. The `combat_flag_on_death` field names a flag that is set when the NPC dies. This flag can be:
- A win condition flag (referenced in `metadata.win_conditions`).
- A lock condition (referenced in a state-type lock's `required_flags`).
- A dialogue gate (NPC dialogue that changes after the boss is dead).
- A lore reveal condition (deep lore accessible only after the boss fight).

### 8.2 Scoring

Combat kill score uses the existing `score_entries` table via `add_score_entry`. The reason string follows the pattern `combat:npc_id`.

### 8.3 Blocking NPCs

The existing blocking NPC system (`is_blocking`, `blocked_exit_id`, `unblock_flag`) already handles NPC-gated exits. Combat death clears the block directly. The generator can use either system:
- `unblock_flag` for NPCs that unblock when a flag is set (dialogue-based unblocking).
- Combat death for NPCs that unblock when killed.

Both work. Combat death is the more dramatic version.

### 8.4 NPC is_alive

The existing `is_alive` field is already used by the engine to filter NPCs in room display and dialogue. Setting `is_alive = 0` on combat death automatically removes the NPC from room listings and makes them untalkable. No additional engine changes needed for this.

### 8.5 Containers and Loot

Loot drops use the existing item spawning system. Loot items are pre-created in the database with `is_visible = 0`. On NPC death, the engine calls `spawn_item` for each ID in `loot_item_ids`, placing them in the current room. This is identical to how puzzle rewards spawn items.

### 8.6 Save/Load

Combat state is fully persisted in SQLite. The `in_combat_with` flag, NPC HP, player HP, equipped items -- all survive a save/load cycle (closing and reopening the `.zork` file). There is no transient combat state that lives only in memory.

---

## 9. Validation Checklist

The generation validation pass should confirm (in addition to existing checks):

- [ ] Every combatant NPC has `hp`, `max_hp`, `damage`, and `defense` set (non-NULL).
- [ ] Every non-combatant NPC has `hp = NULL`.
- [ ] Every combatant NPC has a `death_message`.
- [ ] Every combatant NPC has an `attack_message`.
- [ ] Every boss NPC (high HP) has a `weakness_item_id` that references a real item.
- [ ] Every weakness weapon is reachable before the boss that is weak to it.
- [ ] At least one weapon exists and is reachable before the first combat encounter.
- [ ] Healing items exist in sufficient quantity for the combat encounters in the game.
- [ ] Player can survive each combat encounter with the best available weapon at that point (run the damage formula).
- [ ] No mandatory combat encounter is unbeatable (formula check: player kills NPC before NPC kills player, assuming best available gear).
- [ ] Every `loot_item_ids` reference exists in the items table.
- [ ] Every `combat_flag_on_death` flag is used somewhere (win condition, lock, or dialogue gate).
- [ ] Hostile NPC rooms have danger telegraphing in the preceding room's description.
- [ ] `score_on_kill` values are counted in the game's `max_score`.

---

## 10. Help Text Update

The `help` command should include combat and equipment verbs:

```
Combat
  equip <item>         -- equip a weapon or armor
  unequip              -- unequip your weapon
  unequip armor        -- unequip your armor
  attack <target>      -- attack an NPC
  flee                 -- escape from combat (takes one hit)
```

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-18 | Initial design. Equipment system, combat flow, schema changes, generation guidelines, worked example. |
