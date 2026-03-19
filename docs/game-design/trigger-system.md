# Trigger / Event System

How the engine reacts to game events without the player typing a specific command.

---

## 1. The Problem

The command DSL only fires when the **player types matching input**. Every game state change requires a player-initiated command. This creates four concrete gaps:

### 1.1 Dialogue cannot spawn items or unlock doors

When an NPC gives the player a key during dialogue, the dialogue system can only set flags via `_apply_node_flags`. It cannot spawn items, unlock locks, reveal exits, or execute any other effect type. The obvious workaround -- a DSL command on the `talk` verb -- fails because the built-in dialogue handler intercepts `talk to` before DSL resolution runs (see `game.py` line 474: the `_enter_dialogue` call happens in the built-in verb fallback block, which only runs when DSL did not match).

**Example**: An NPC says "Take this key" during a dialogue branch. The dialogue sets `npc_gave_key`. But the key never appears in the player's inventory. There is no mechanism to make `set_flag("npc_gave_key")` trigger a `spawn_item` effect.

### 1.2 Entering a room cannot trigger events

An NPC should comment when the player enters their room. A trap should fire when the player walks in. An ambush should trigger. `first_visit_text` handles one static case (first visit only, text only, no effects), but there is no way to:

- Show text on every entry to a room (not just the first)
- Execute effects (damage, flag set, item spawn) on room entry
- Make room entry conditional (only fire if a flag is set)

### 1.3 Flag changes cannot cascade

Setting flag A should be able to automatically trigger effect B. Example: a training course requires qualifying with two weapons. Passing the P226 qualification sets `p226_qualified`. Passing the AR-15 qualification sets `ar15_qualified`. When both are set, the exit to the next area should automatically unlock. Currently, the quest system watches flags in `_tick()`, but only for quest state transitions -- not for general-purpose effects like unlocking doors or spawning items.

### 1.4 NPCs cannot react to player actions

An NPC should react when the player attacks something, picks up an item, or enters their room. Currently NPCs are completely passive unless the player explicitly talks to them.

---

## 2. What Triggers Are

A trigger is a stored rule:

> **When [event] occurs AND [preconditions] are met, execute [effects].**

Triggers share the same precondition and effect types as DSL commands. They reuse `check_precondition()` and `apply_effect()` from `commands.py`. The difference is how they fire:

| System | Fires when... |
|---|---|
| DSL commands | The **player types matching input** |
| Triggers | A **game event occurs** (room entered, flag set, dialogue node reached, etc.) |

Triggers are **deterministic**. They are generated during world creation (by the LLM) and stored in the database. The engine evaluates them at runtime using the same precondition/effect machinery as DSL commands. No LLM runs at play-time.

### Design pillars for triggers

1. **Reuse, don't reinvent.** Triggers use the same precondition types and effect types as commands. No new effect system.
2. **Deterministic and inspectable.** A trigger is data in SQLite. You can query the triggers table to see every reactive rule in the game.
3. **Simple event bus, not a scripting language.** Events are flat (type + data). There are no event chains, no priority inheritance, no conditional branching within a trigger. If you need complex logic, use multiple triggers with flag-based gating.
4. **Idempotent for one-shot triggers.** A one-shot trigger fires exactly once. If the engine crashes mid-execution and replays, the `executed` flag prevents double-firing.

---

## 3. Event Types

Events are things that happen in the game world. Each event type has a fixed set of fields that identify what happened. Triggers match against these fields.

### 3.1 `room_enter`

Fires when the player enters a room (after `handle_movement` updates `current_room_id` and before `_tick`).

| Field | Type | Description |
|---|---|---|
| `room_id` | string | The room the player just entered. |

**Use cases:**
- NPC greets the player on arrival.
- Trap fires when the player enters a room.
- Atmospheric text on every entry (not just first visit).
- Ambush: enemies appear, health decreases.
- Flag-gated entry text: "Now that you have the amulet, the statues' eyes glow."

**Emission point:** `handle_movement()`, after `db.update_player(current_room_id=dest_room_id)` and `display_room(dest_room_id)`, before the method returns. Also fires in `start()` after displaying the starting room, so triggers on the start room work on game launch.

### 3.2 `flag_set`

Fires when a flag is set to true (via `set_flag` effect, `_apply_node_flags`, `_apply_option_flags`, or any other flag-setting path).

| Field | Type | Description |
|---|---|---|
| `flag` | string | The flag name that was just set. |

**Use cases:**
- Both qualifications done -> unlock exit.
- Quest flag set -> spawn reward item.
- NPC dialogue flag -> unlock new room.
- Cascading state: setting flag A triggers an effect that sets flag B.

**Emission point:** Inside `GameDB.set_flag()`. This is the single bottleneck through which all flag mutations flow, ensuring no flag change goes unobserved. However, to avoid deep recursion during cascade scenarios, emission is deferred -- see section 5.2.

**Important:** `flag_set` fires only when the flag transitions from unset/false to true. Setting an already-true flag does not re-fire the event. This prevents infinite loops when a trigger's effect sets the same flag that triggered it.

### 3.3 `dialogue_node`

Fires when a dialogue node is displayed to the player (after `_apply_node_flags` runs for that node).

| Field | Type | Description |
|---|---|---|
| `node_id` | string | The dialogue node that was just displayed. |

**Use cases:**
- NPC gives the player an item during dialogue.
- Dialogue node spawns an NPC in another room.
- Reaching a specific dialogue branch sets up a puzzle.

**Emission point:** `_enter_dialogue()`, after `_apply_node_flags(current_node)` runs, before rendering the dialogue panel. Also fires for the root node on dialogue entry.

### 3.4 `item_taken`

Fires when the player picks up an item (after the item is moved to inventory).

| Field | Type | Description |
|---|---|---|
| `item_id` | string | The item that was just taken. |

**Use cases:**
- Picking up the artifact triggers a cave-in (damage + flag).
- NPC reacts: "Hey, put that back!"
- Taking the last item from a pedestal reveals a hidden exit.

**Emission point:** `_handle_take()` and `_handle_take_from()`, after `db.move_item()` or `db.take_item_from_container()` succeeds. Also fires when a `move_item` effect moves an item to `_inventory`.

### 3.5 `item_dropped`

Fires when the player drops an item into a room.

| Field | Type | Description |
|---|---|---|
| `item_id` | string | The item that was just dropped. |
| `room_id` | string | The room where it was dropped. |

**Use cases:**
- Dropping the offering on the altar triggers a shrine activation.
- Dropping a light source in a dark room illuminates it for NPCs.

**Emission point:** `_handle_drop()`, after `db.move_item()` succeeds. Also fires when a `move_item` effect moves an item from `_inventory` to a room.

### 3.6 `npc_killed`

Fires when an NPC's `is_alive` flag is set to false (for future combat system integration).

| Field | Type | Description |
|---|---|---|
| `npc_id` | string | The NPC that was just killed. |

**Use cases:**
- Killing the guard drops a key item.
- Killing an NPC triggers a reaction from another NPC.
- Boss death unlocks the final area.

**Emission point:** Deferred to combat system implementation. Will fire from the combat resolution handler after NPC HP reaches zero.

### Event type summary

| Event Type | Fields | Emission Point |
|---|---|---|
| `room_enter` | `room_id` | `handle_movement()`, `start()` |
| `flag_set` | `flag` | `GameDB.set_flag()` (deferred) |
| `dialogue_node` | `node_id` | `_enter_dialogue()` |
| `item_taken` | `item_id` | `_handle_take()`, `move_item` effect |
| `item_dropped` | `item_id`, `room_id` | `_handle_drop()`, `move_item` effect |
| `npc_killed` | `npc_id` | Combat system (future) |

---

## 4. Schema

### 4.1 The `triggers` table

```sql
CREATE TABLE IF NOT EXISTS triggers (
    id              TEXT PRIMARY KEY,
    event_type      TEXT    NOT NULL,  -- room_enter | flag_set | dialogue_node | item_taken | item_dropped | npc_killed
    event_data      TEXT    NOT NULL DEFAULT '{}',  -- JSON: event-specific match fields
    preconditions   TEXT    NOT NULL DEFAULT '[]',   -- JSON array: same format as commands
    effects         TEXT    NOT NULL DEFAULT '[]',   -- JSON array: same format as commands
    message         TEXT,                            -- optional text to display when trigger fires
    priority        INTEGER NOT NULL DEFAULT 0,      -- higher = evaluated first
    one_shot        INTEGER NOT NULL DEFAULT 0,      -- 1 = fire only once
    executed        INTEGER NOT NULL DEFAULT 0,      -- 1 = already fired (for one-shot)
    is_enabled      INTEGER NOT NULL DEFAULT 1       -- 0 = disabled (for debug or conditional activation)
);

CREATE INDEX IF NOT EXISTS idx_triggers_event_type ON triggers(event_type);
CREATE INDEX IF NOT EXISTS idx_triggers_event_data ON triggers(event_data);
```

### 4.2 Field definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PK | yes | Unique identifier. Snake_case. Convention: `trigger_{event_type}_{description}`. Example: `trigger_room_enter_guard_greeting`. |
| `event_type` | TEXT | yes | Which event fires this trigger. One of the event types from section 3. |
| `event_data` | TEXT (JSON) | yes | Event-specific match criteria. The trigger fires only if the event's fields match these values. See section 4.3. |
| `preconditions` | TEXT (JSON) | yes | Array of precondition objects. Same format and types as DSL commands. ALL must be satisfied for the trigger to fire. May be empty `[]` for unconditional triggers. |
| `effects` | TEXT (JSON) | yes | Ordered array of effect objects. Same format and types as DSL commands. Executed sequentially when preconditions pass. Must contain at least one effect. |
| `message` | TEXT | no | Optional text displayed to the player when the trigger fires. Displayed before effect-generated messages. Supports narrator mode. |
| `priority` | INTEGER | no | Evaluation order within the same event. Higher priority triggers are evaluated first. Defaults to `0`. |
| `one_shot` | INTEGER | no | If `1`, this trigger fires only once ever. Defaults to `0`. |
| `executed` | INTEGER | no | Runtime state. Set to `1` after a one-shot trigger fires. Defaults to `0`. |
| `is_enabled` | INTEGER | no | If `0`, this trigger is skipped during evaluation. Defaults to `1`. Used for debug or for triggers that are activated by other triggers via a flag-based precondition. |

### 4.3 `event_data` matching

The `event_data` field is a JSON object whose keys correspond to the event type's fields. When an event fires, the engine checks whether every key in the trigger's `event_data` matches the corresponding value in the emitted event.

**Matching rules:**

- Every key in `event_data` must be present in the event and must match exactly (string equality).
- Keys in the event that are NOT in `event_data` are ignored (partial matching).
- An empty `event_data` (`{}`) matches any event of that type (wildcard trigger).

**Examples:**

```json
// Matches only room_enter for "guard_post"
{"room_id": "guard_post"}

// Matches flag_set for "p226_qualified"
{"flag": "p226_qualified"}

// Matches any item_taken event (wildcard)
{}

// Matches item_dropped in a specific room
{"item_id": "golden_offering", "room_id": "shrine_altar"}
```

### 4.4 Relationship to existing tables

The triggers table is independent -- it does not have foreign keys to other tables. This is deliberate:

- **`event_data` references** (room IDs, item IDs, flag names) are validated at generation time, not enforced by foreign keys. This matches how `commands.preconditions` and `commands.effects` reference IDs without foreign keys.
- **Preconditions and effects** use the same JSON format as commands. The engine calls the same `check_precondition()` and `apply_effect()` functions.
- **No dependency on the commands table.** Triggers and commands are parallel systems. A trigger does not need a corresponding command, and a command does not need a corresponding trigger.

---

## 5. Engine Integration

### 5.1 Event emission

The engine emits events through a single method on `GameEngine`:

```python
def _emit_event(self, event_type: str, **event_data: str) -> None:
    """Emit a game event, evaluate matching triggers, and execute their effects.

    Args:
        event_type: The event type string (e.g., "room_enter").
        **event_data: Event-specific fields as keyword arguments.
    """
```

This method:

1. Queries the `triggers` table for all enabled, non-executed triggers matching `event_type`.
2. Filters to triggers whose `event_data` JSON matches the emitted event fields.
3. Sorts by `priority` descending (highest first).
4. For each matching trigger, checks preconditions via `check_precondition()`.
5. If all preconditions pass, displays the trigger's `message` (if any), then applies effects via `apply_effect()`.
6. If the trigger is `one_shot`, marks it as `executed`.

### 5.2 Emission points in the engine

Each event type has a specific emission point. The key design decision is **where** in the execution flow the event fires:

#### `room_enter`

```
handle_movement():
    1. Check exit exists and is unlocked
    2. db.update_player(current_room_id=dest_room_id)
    3. display_room(dest_room_id)
    4. _emit_event("room_enter", room_id=dest_room_id)   <-- HERE
    // _tick() is called by main_loop after handle_movement returns
```

The event fires **after** the room is displayed. This means trigger messages appear below the room description, which is the natural reading order: "You enter the room. [room description]. [trigger: The guard looks up and scowls.]"

Also fires in `start()` after the starting room is displayed, so triggers on the start room work.

Also fires when a `move_player` effect moves the player (e.g., a teleport trap). The `apply_effect` handler for `move_player` should emit the event after updating the player's position.

#### `flag_set`

Flag-set events are special because they can cascade: trigger A sets flag X, which fires trigger B, which sets flag Y, which fires trigger C. To prevent stack overflow from deep recursion and to guarantee consistent evaluation order, flag-set events use **deferred emission**:

```
_emit_event("flag_set", flag="some_flag")
    -> evaluates matching triggers
    -> trigger effects may call set_flag()
    -> set_flag() appends ("flag_set", flag=new_flag) to a pending queue
    -> after all current triggers finish, process the pending queue
    -> repeat until the queue is empty
```

Implementation:

```python
def _emit_event(self, event_type: str, **event_data: str) -> None:
    # Guard against re-entrant calls during flag cascades.
    if not hasattr(self, '_event_queue'):
        self._event_queue: list[tuple[str, dict[str, str]]] = []
        self._processing_events = False

    self._event_queue.append((event_type, event_data))

    if self._processing_events:
        return  # Will be processed by the outer loop

    self._processing_events = True
    try:
        while self._event_queue:
            ev_type, ev_data = self._event_queue.pop(0)
            self._process_event(ev_type, ev_data)
    finally:
        self._processing_events = False
```

**Cascade depth limit:** The engine tracks cascade depth and stops after 20 iterations of the queue-drain loop. If the limit is hit, a warning is logged. This prevents infinite loops from circular flag dependencies (flag A triggers set flag B, flag B triggers set flag A). 20 is generous -- in practice, well-designed games should never exceed 3-4 cascades.

#### `dialogue_node`

```
_enter_dialogue():
    for each node visited:
        1. _apply_node_flags(current_node)
        2. _emit_event("dialogue_node", node_id=current_node["id"])   <-- HERE
        3. _render_dialogue_panel(...)
        4. wait for player input
```

The event fires **after** node flags are applied but **before** the panel is rendered. This means trigger effects (like spawning an item) take effect before the player sees the dialogue options, and any flag-gated dialogue options reflect the trigger's changes.

The trigger's `message` is displayed within the dialogue flow -- after the node's content text but before the options. This lets NPC dialogue naturally produce side effects: "Here, take this key" -> trigger spawns the key -> player sees "[The guard hands you a heavy iron key.]" before the dialogue options.

#### `item_taken`

```
_handle_take():
    1. Find the item
    2. db.move_item(item["id"], "inventory", "")
    3. Print take_message
    4. _emit_event("item_taken", item_id=item["id"])   <-- HERE
```

Fires **after** the item is in inventory and the take message is printed.

#### `item_dropped`

```
_handle_drop():
    1. Find the item in inventory
    2. db.move_item(item["id"], "room", current_room_id)
    3. Print drop_message
    4. _emit_event("item_dropped", item_id=item["id"], room_id=current_room_id)   <-- HERE
```

Fires **after** the item is in the room and the drop message is printed.

#### Events from DSL effects

When a DSL command's effects cause state changes that should emit events, the engine needs to emit those events too. Specifically:

- `move_player` effect -> emits `room_enter` after moving the player.
- `move_item` effect with `to="_inventory"` -> emits `item_taken`.
- `move_item` effect with `from="_inventory"` and `to` = a room -> emits `item_dropped`.
- `set_flag` effect -> emits `flag_set` (via deferred queue).
- `spawn_item` effect with `location="_inventory"` -> emits `item_taken`.

This is handled by wrapping the emission in `apply_effect` or by having the engine emit events after processing a command result. The preferred approach is to **emit events from `apply_effect`** so that triggers on effects work regardless of whether the effect came from a command or another trigger. The `apply_effect` function receives an optional callback for event emission:

```python
def apply_effect(
    effect: dict,
    db: GameDB,
    slots: dict[str, str] | None = None,
    command_id: str = "",
    emit_event: Callable[[str, ...], None] | None = None,
) -> list[str]:
```

When `emit_event` is provided, `apply_effect` calls it for state changes that warrant events.

### 5.3 Trigger evaluation: `_process_event`

The core evaluation logic:

```python
def _process_event(self, event_type: str, event_data: dict[str, str]) -> None:
    """Find and execute all triggers matching this event."""
    db = self.db

    # 1. Fetch candidate triggers.
    triggers = db.get_triggers_for_event(event_type)

    # 2. Filter by event_data match.
    matching = []
    for trigger in triggers:
        trigger_data = json.loads(trigger["event_data"]) if trigger["event_data"] else {}
        if all(event_data.get(k) == v for k, v in trigger_data.items()):
            matching.append(trigger)

    # 3. Sort by priority (descending).
    matching.sort(key=lambda t: -t["priority"])

    # 4. Evaluate each trigger.
    for trigger in matching:
        # Skip one-shot triggers that already fired.
        if trigger["one_shot"] and trigger["executed"]:
            continue

        # Check preconditions.
        preconditions = json.loads(trigger["preconditions"]) if trigger["preconditions"] else []
        all_pass = all(
            check_precondition(cond, db) for cond in preconditions
        )
        if not all_pass:
            continue

        # Fire the trigger.
        # Display message if present.
        if trigger.get("message"):
            self.console.print(trigger["message"])

        # Apply effects.
        effects = json.loads(trigger["effects"]) if trigger["effects"] else []
        for effect in effects:
            try:
                msgs = apply_effect(
                    effect, db,
                    command_id=f"trigger:{trigger['id']}",
                    emit_event=self._emit_event,
                )
                for msg in msgs:
                    self.console.print(msg)
            except Exception:
                logger.exception("Trigger effect failed: %s in %s", effect, trigger["id"])

        # Mark one-shot as executed.
        if trigger["one_shot"]:
            db.mark_trigger_executed(trigger["id"])
```

### 5.4 New GameDB methods

The following methods are added to `GameDB`:

```python
def get_triggers_for_event(self, event_type: str) -> list[dict]:
    """Return all enabled, non-executed triggers for the given event type."""
    return self._fetchall(
        "SELECT * FROM triggers WHERE event_type = ? AND is_enabled = 1 "
        "AND (one_shot = 0 OR executed = 0) ORDER BY priority DESC",
        (event_type,),
    )

def mark_trigger_executed(self, trigger_id: str) -> None:
    """Mark a one-shot trigger as executed."""
    self._mutate(
        "UPDATE triggers SET executed = 1 WHERE id = ?",
        (trigger_id,),
    )
```

---

## 6. Ordering and Conflict Resolution

### 6.1 Priority

When multiple triggers match the same event, they execute in `priority` order (highest first). Within the same priority, execution order is by database insertion order (rowid).

**Priority conventions:**

| Priority | Usage |
|---|---|
| 100+ | Safety / override triggers (e.g., "if player has no health, block this action") |
| 10-99 | Puzzle-critical triggers (unlock door, spawn key item) |
| 0 | Default. Atmospheric / flavor triggers (NPC comments, ambient text) |
| -1 to -99 | Low-priority cleanup triggers |

### 6.2 All matching triggers fire

Unlike DSL commands (where the first matching command wins), **all matching triggers fire** in priority order. This is intentional:

- Entering a room might trigger an NPC greeting (priority 0) AND a trap (priority 10). Both should fire. The trap fires first (higher priority), then the greeting.
- Setting a flag might trigger an exit unlock (priority 10) AND a quest notification (priority 0). Both fire.

If a trigger's effects change state such that a later trigger's preconditions no longer pass, that later trigger simply does not fire. This is the intended conflict resolution: preconditions are the gating mechanism.

### 6.3 Effect atomicity

Each trigger's effects execute within a single database transaction, matching the atomicity guarantee of DSL commands. If one effect in a trigger fails, the engine logs the error and continues with remaining effects in that trigger (same behavior as DSL commands).

---

## 7. Interaction With Existing Systems

### 7.1 Quest system

The quest system in `_check_quests()` already watches flags in `_tick()`. Triggers do not replace this -- they complement it:

- **Quests** handle discovery, objective tracking, completion notifications, and score awards. This is quest-specific presentation logic.
- **Triggers** handle game-world reactions to events. A trigger might set a flag that completes a quest objective, but the quest system handles the "Quest Updated" notification.

When a trigger sets a flag that completes a quest objective, the flow is:

```
Event fires -> trigger evaluates -> set_flag effect runs
    -> flag_set event queued (deferred)
    -> flag_set triggers evaluate (if any)
    -> _tick() runs -> _check_quests() sees the new flag -> quest notification
```

There is no conflict because `_tick()` runs after all events and triggers have resolved.

### 7.2 Dialogue system

The dialogue system currently sets flags via `_apply_node_flags` and `_apply_option_flags`. With triggers:

1. Dialogue node is displayed.
2. `_apply_node_flags` sets any flags defined on the node.
3. `_emit_event("dialogue_node", node_id=...)` fires.
4. Matching triggers execute (e.g., spawn an item, unlock a door).
5. Any `flag_set` events from step 2 or step 4 are queued and processed.
6. The dialogue panel renders.

This means dialogue options in step 6 reflect all state changes from steps 2-5. If a trigger spawns an item, a subsequent dialogue option gated on `has_item` will correctly appear.

The dialogue system does NOT need modification beyond adding the `_emit_event` call. Triggers extend its capabilities without changing its architecture.

### 7.3 DSL commands

Triggers and DSL commands are parallel systems that share infrastructure:

| Aspect | DSL Commands | Triggers |
|---|---|---|
| Stored in | `commands` table | `triggers` table |
| Fires when | Player types matching input | Game event occurs |
| Preconditions | Same types, same `check_precondition()` | Same types, same `check_precondition()` |
| Effects | Same types, same `apply_effect()` | Same types, same `apply_effect()` |
| One-shot | Supported | Supported |
| Pattern matching | Yes (verb + slots) | No (event_data matching) |
| Slot substitution | Yes | No (no player input to parse) |

When a DSL command's effects cause state changes (set_flag, move_item, etc.), those changes emit events that triggers respond to. This is the intended interaction: commands cause state changes, triggers react to them.

### 7.4 Narrator mode

Trigger messages (`message` field and `print` effects) should be narrated when narrator mode is active, just like DSL command messages. The `_process_event` method collects all messages from a trigger execution and passes them through `_narrate_action` before display.

### 7.5 Move counter

Trigger evaluation does NOT increment the move counter. The move counter increments once per player action (in `_tick()`), regardless of how many triggers fire. Triggers are reactions to the player's action, not separate actions.

---

## 8. Generation Pipeline

### 8.1 Current pass: Pass 10 (Triggers)

Triggers are generated after commands and quests, then validated with the rest of the world. In the current pipeline they run as **Pass 10**, immediately before final validation.

**Why a separate pass (not part of Pass 7):**

- Commands and triggers have different mental models. Commands think "what can the player do?" Triggers think "what happens reactively?" Mixing them in one prompt muddles both.
- The triggers pass needs to see the commands that exist to avoid creating triggers that duplicate command behavior.
- The triggers pass can reference dialogue nodes (from Pass 5) that the commands pass cannot meaningfully use.

**Reads from previous passes:** Everything, with emphasis on:
- Rooms (for `room_enter` triggers)
- Items (for `item_taken` / `item_dropped` triggers)
- NPCs and dialogue nodes (for `dialogue_node` triggers and NPC reaction triggers)
- Flags (for `flag_set` triggers)
- Commands (to avoid duplication)
- Puzzles (triggers often wire puzzle rewards)

**What the LLM prompt should focus on:**

1. **Dialogue side effects.** For every dialogue node where an NPC gives the player something, sets up a puzzle, or changes the world state, generate a `dialogue_node` trigger that executes the mechanical effects.

2. **Room entry events.** For rooms where something should happen on entry (NPC greeting, trap, atmospheric event), generate `room_enter` triggers. Use `one_shot` for events that should only happen once (trap, ambush) and repeating triggers for ongoing reactions (guard challenges player every time).

3. **Flag cascades.** For state-based locks or multi-step quest completions where setting the final flag should automatically produce a result, generate `flag_set` triggers.

4. **Item reactions.** For cursed items, quest items, or items that NPCs care about, generate `item_taken` or `item_dropped` triggers.

**Prompt should instruct the LLM to:**

- Use the same precondition and effect types as commands (reference the DSL spec).
- Prefer `one_shot: true` for events that should not repeat (traps, item gifts, puzzle rewards).
- Use preconditions to prevent triggers from firing at the wrong time (e.g., a greeting trigger should check `not_flag: guard_greeted` to avoid repeating).
- Keep trigger messages concise -- they appear inline with other game text.

### 8.2 Output format

```json
{
  "triggers": [
    {
      "id": "trigger_dialogue_blacksmith_gives_key",
      "event_type": "dialogue_node",
      "event_data": {"node_id": "blacksmith_forges_key"},
      "preconditions": [],
      "effects": [
        {"type": "spawn_item", "item": "forged_key", "location": "_inventory"},
        {"type": "print", "message": "The blacksmith slides a newly forged key across the counter. You pocket it."}
      ],
      "message": null,
      "priority": 10,
      "one_shot": true
    }
  ]
}
```

### 8.3 Validation

The final validation step should check:

- [ ] All `event_data` references point to valid IDs (room IDs, item IDs, NPC IDs, node IDs, flag names).
- [ ] All precondition references point to valid entities.
- [ ] All effect references point to valid entities.
- [ ] `flag_set` triggers do not create circular dependencies (flag A triggers set flag B, flag B triggers set flag A). This can be detected statically by building a dependency graph.
- [ ] One-shot triggers that spawn items reference items that exist in the items table (even if not yet placed in the world).
- [ ] Every dialogue node where the narrative implies a world-state change (NPC gives item, NPC unlocks door) has a corresponding `dialogue_node` trigger.

---

## 9. Worked Examples

### 9.1 Dialogue gives player an item

**Scenario:** The blacksmith NPC forges a key for the player during dialogue. The dialogue node says "Here's your key" and sets the flag `blacksmith_forged_key`. But the key needs to actually appear in the player's inventory.

**Current behavior (broken):** The dialogue sets the flag. The key never appears. The player is confused.

**With triggers:**

The dialogue node `blacksmith_forges_key` has `set_flags: ["blacksmith_forged_key"]` as before.

```json
{
  "id": "trigger_dialogue_blacksmith_gives_key",
  "event_type": "dialogue_node",
  "event_data": {"node_id": "blacksmith_forges_key"},
  "preconditions": [],
  "effects": [
    {"type": "spawn_item", "item": "forged_key", "location": "_inventory"},
    {"type": "add_score", "points": 5}
  ],
  "message": "[You receive a heavy iron key, still warm from the forge.]",
  "priority": 10,
  "one_shot": true
}
```

**Flow:**

1. Player reaches the `blacksmith_forges_key` dialogue node.
2. `_apply_node_flags` sets `blacksmith_forged_key`.
3. `_emit_event("dialogue_node", node_id="blacksmith_forges_key")` fires.
4. Trigger matches: `event_type` = `dialogue_node`, `event_data.node_id` = `blacksmith_forges_key`.
5. No preconditions. Passes.
6. Effects execute: `spawn_item` places `forged_key` in inventory. `add_score` awards 5 points.
7. Message displays: "[You receive a heavy iron key, still warm from the forge.]"
8. Trigger marked as executed (one-shot).
9. Dialogue continues. If any subsequent option checks `has_item: forged_key`, it will correctly appear.

### 9.2 Entering a room triggers NPC greeting

**Scenario:** When the player enters the guard post for the first time, the guard challenges them.

```json
{
  "id": "trigger_room_enter_guard_challenge",
  "event_type": "room_enter",
  "event_data": {"room_id": "guard_post"},
  "preconditions": [
    {"type": "not_flag", "flag": "guard_challenged"},
    {"type": "npc_in_room", "npc": "stern_guard", "room": "guard_post"}
  ],
  "effects": [
    {"type": "set_flag", "flag": "guard_challenged"},
    {"type": "print", "message": "The guard steps forward, blocking your path. \"State your business, stranger. No one passes without the captain's seal.\""}
  ],
  "message": null,
  "priority": 0,
  "one_shot": true
}
```

**Why `one_shot: true` AND `not_flag`:** Belt-and-suspenders. The `not_flag` prevents the trigger from firing if the flag is somehow set by another mechanism. The `one_shot` prevents the trigger from even being evaluated on subsequent visits.

**Why `npc_in_room` precondition:** If the guard is killed or moved before the player enters, the challenge should not fire. The trigger checks that the guard is actually present.

### 9.3 Both flags set -> door unlocks

**Scenario:** The player must qualify with both the P226 pistol and the AR-15 rifle. Each qualification sets a flag. When both flags are set, the exit to the range office should unlock.

Two triggers handle this, one for each flag:

```json
{
  "id": "trigger_flag_p226_qualifies_range",
  "event_type": "flag_set",
  "event_data": {"flag": "p226_qualified"},
  "preconditions": [
    {"type": "has_flag", "flag": "ar15_qualified"}
  ],
  "effects": [
    {"type": "unlock", "lock": "range_office_lock"},
    {"type": "print", "message": "Both qualifications complete. You hear a buzz -- the range office door unlocks."},
    {"type": "add_score", "points": 15}
  ],
  "message": null,
  "priority": 10,
  "one_shot": true
}
```

```json
{
  "id": "trigger_flag_ar15_qualifies_range",
  "event_type": "flag_set",
  "event_data": {"flag": "ar15_qualified"},
  "preconditions": [
    {"type": "has_flag", "flag": "p226_qualified"}
  ],
  "effects": [
    {"type": "unlock", "lock": "range_office_lock"},
    {"type": "print", "message": "Both qualifications complete. You hear a buzz -- the range office door unlocks."},
    {"type": "add_score", "points": 15}
  ],
  "message": null,
  "priority": 10,
  "one_shot": true
}
```

**Why two triggers:** The player can qualify in either order. If they qualify P226 first, then AR-15, the `ar15_qualified` flag-set event fires. That trigger checks `has_flag: p226_qualified` -- it passes. The door unlocks. If they do it in reverse order, the other trigger handles it. Both are one-shot, so only the second qualification trigger actually fires (the other never matches because its flag-set event already happened before the precondition flag existed).

**Alternative design (single trigger):** You could use a single trigger on either flag with both flags in preconditions. But you would need to decide which flag to watch. The two-trigger approach is more robust because it handles both orderings symmetrically.

### 9.4 Picking up cursed item triggers trap

**Scenario:** Picking up the Ancient Idol triggers a cave-in that damages the player and blocks the exit.

```json
{
  "id": "trigger_item_taken_idol_curse",
  "event_type": "item_taken",
  "event_data": {"item_id": "ancient_idol"},
  "preconditions": [
    {"type": "in_room", "room": "hidden_shrine"}
  ],
  "effects": [
    {"type": "change_health", "amount": -20},
    {"type": "set_flag", "flag": "shrine_collapsed"},
    {"type": "print", "message": "The moment the idol leaves the pedestal, the ground shakes. Stones crash down from the ceiling. A section of the passage behind you collapses in a cloud of dust and debris. You stagger, bruised but alive. The way back is sealed."}
  ],
  "message": null,
  "priority": 10,
  "one_shot": true
}
```

A companion `flag_set` trigger hides the exit:

```json
{
  "id": "trigger_flag_shrine_collapse_blocks_exit",
  "event_type": "flag_set",
  "event_data": {"flag": "shrine_collapsed"},
  "preconditions": [],
  "effects": [
    {"type": "set_flag", "flag": "shrine_exit_blocked"}
  ],
  "message": null,
  "priority": 5,
  "one_shot": true
}
```

**Design note:** The cave-in uses two triggers (item-taken -> damage + flag, flag-set -> block exit) rather than one trigger with all effects. This is a style choice. Both approaches work. The two-trigger approach makes the causal chain explicit in the data: taking the idol causes the collapse, and the collapse blocks the exit. The single-trigger approach would combine all effects into one trigger, which is simpler but less inspectable.

### 9.5 Dropping an offering on an altar

**Scenario:** Dropping the golden offering in the shrine room activates the shrine.

```json
{
  "id": "trigger_item_dropped_offering_altar",
  "event_type": "item_dropped",
  "event_data": {"item_id": "golden_offering", "room_id": "ancient_shrine"},
  "preconditions": [
    {"type": "not_flag", "flag": "shrine_activated"}
  ],
  "effects": [
    {"type": "set_flag", "flag": "shrine_activated"},
    {"type": "reveal_exit", "exit": "shrine_to_inner_sanctum"},
    {"type": "add_score", "points": 20},
    {"type": "print", "message": "As the offering touches the altar stone, the shrine comes alive. Light pulses through the carved channels in the floor, tracing patterns you couldn't see before. The wall behind the altar splits open, revealing a narrow passage that descends into warm, golden light."}
  ],
  "message": null,
  "priority": 10,
  "one_shot": true
}
```

**Note on `event_data` matching:** This trigger specifies both `item_id` and `room_id`. Dropping the golden offering in any other room does not fire this trigger. Dropping any other item in the shrine does not fire this trigger. Both fields must match.

---

## 10. Edge Cases and Safety

### 10.1 Infinite loops

**Risk:** Flag A trigger sets flag B. Flag B trigger sets flag A. Both fire endlessly.

**Mitigation:**
1. **`flag_set` fires only on transition.** If flag A is already true and `set_flag("A")` is called, no `flag_set` event is emitted. This breaks most trivial loops.
2. **Cascade depth limit.** The event queue drains loop has a hard limit of 20 iterations. If hit, remaining queued events are discarded and a warning is logged.
3. **Generation-time validation.** The validation pass builds a flag dependency graph and checks for cycles.

### 10.2 Trigger fires during dialogue

`dialogue_node` triggers fire within the dialogue sub-loop. If a trigger's effect moves the player to a different room or ends the game, the dialogue loop must handle this gracefully.

**Mitigation:** After processing `dialogue_node` triggers, check if the player's room has changed or game state is no longer `playing`. If so, break out of the dialogue loop.

### 10.3 Order of operations within `_tick`

The `_tick` method currently does: increment moves -> check quests -> check end conditions. With triggers, the order becomes:

```
Player action
    -> built-in handler or DSL command executes
    -> events emitted (including deferred flag_set events)
    -> all triggers resolve (including cascades)
_tick():
    -> increment move counter
    -> _check_quests() (sees all flag changes from triggers)
    -> check_end_conditions() (sees all state changes from triggers)
```

This ordering guarantees that `_check_quests()` and `check_end_conditions()` see the fully resolved game state after all triggers have fired.

### 10.4 Triggers and save/load

Triggers are stored in the `.zork` file. The `executed` field persists across sessions. One-shot triggers that have already fired will not re-fire when the game is loaded. This is identical to how one-shot commands work.

### 10.5 Triggers and narrator mode

When narrator mode is active, trigger messages and print effects are candidates for narration. The engine collects all messages from a trigger execution and optionally passes them through the narrator. The narrator cannot change game state -- it only flavors the text.

### 10.6 Trigger effects that fail

Same policy as DSL commands: if an effect fails (e.g., trying to spawn an item that already exists, or moving an item that has been removed), the engine logs a warning and continues executing remaining effects. The trigger is not rolled back.

---

## 11. Implementation Plan

### Phase 1: Schema and data access

1. Add the `triggers` table to `SCHEMA_SQL` in `schema.py`.
2. Add `get_triggers_for_event()` and `mark_trigger_executed()` to `GameDB`.
3. Add migration support: existing `.zork` files without a `triggers` table should still load (the table is created with `CREATE TABLE IF NOT EXISTS`).
4. Write unit tests for trigger CRUD and query methods.

### Phase 2: Event emission and trigger evaluation

1. Add `_emit_event()`, `_process_event()`, and the event queue to `GameEngine`.
2. Add emission points for `room_enter` (in `handle_movement` and `start`).
3. Add emission points for `dialogue_node` (in `_enter_dialogue`).
4. Add emission points for `item_taken` (in `_handle_take` and `_handle_take_from`).
5. Add emission points for `item_dropped` (in `_handle_drop`).
6. Add emission for `flag_set` (deferred queue mechanism).
7. Wire `apply_effect` to emit events when effects cause state changes.
8. Write integration tests: create a test `.zork` file with triggers, verify they fire correctly.

### Phase 3: Cascade safety

1. Implement the deferred event queue for `flag_set` cascades.
2. Implement the cascade depth limit (20 iterations).
3. Add `flag_set` transition detection (only emit on false->true transitions).
4. Write tests for cascade scenarios, including the infinite loop case.

### Phase 4: Generation pipeline

1. Create the trigger generation prompt template for the current pipeline slot.
2. Add trigger output parsing and database insertion to the generation orchestrator.
3. Add trigger validation to Pass 9 (entity reference checks, circular dependency detection).
4. Test end-to-end: generate a game with triggers, play it, verify triggers fire.

### Phase 5: Polish

1. Narrator integration for trigger messages.
2. Debug tooling: `triggers` command in the engine that lists all triggers and their status.
3. Documentation updates: update world-schema.md, command-spec.md, and GDD with trigger references.
