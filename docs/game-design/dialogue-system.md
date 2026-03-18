# Dialogue Tree System

> Replaces the flat topic-based dialogue system entirely. The player types `talk to {npc}` and enters a dialogue mode with numbered options, branching nodes, flag integration, and inventory-reactive choices. This document is the authoritative spec for the dialogue system -- schema, engine behavior, generation, and integration with existing systems.

## Why Replace the Current System

The current dialogue system has four problems:

1. **Players do not know what to type.** The `ask {npc} about {topic}` syntax requires the player to guess valid keywords. The engine shows available topics as a hint ("You could ask about: zombies, gas station, building"), but this turns every NPC interaction into a menu disguised as freeform input. If it is a menu, make it a real menu.

2. **Greeting commands are redundant noise.** Typing "hello", "hi", "hey", or "greetings" when there is one NPC in the room is equivalent to `talk to {npc}`. It is a shortcut nobody asked for that clutters the verb space and adds a code path that accomplishes nothing the primary command does not already do.

3. **Flat topic lists are not conversations.** Real dialogue has flow -- one thing leads to another. The current system lets the player ask about any available topic in any order. There is no sense of a conversation building, no dramatic arc within a single NPC encounter, and no way for the NPC to guide the player toward specific revelations.

4. **No inventory awareness.** The current system gates dialogue with flags only. If the player found bolt cutters, there is no way for that to organically surface in conversation. The player would need to know to type `ask Maria about bolt cutters` -- a topic that may not exist. Inventory-reactive options make conversations feel alive.

---

## Design Pillars

These are the non-negotiable properties of the dialogue tree system:

1. **Conversations are modal.** When the player types `talk to {npc}`, the engine enters dialogue mode. Normal game commands are suspended. The player interacts via numbered choices until they exit. This is a clean state separation -- no ambiguity about whether you are talking or adventuring.

2. **The display does not scroll.** Each dialogue state renders in-place using Rich's `Live` display. The player sees the NPC's current line and their current options. When they pick a number, the display updates. No chat-log scrolling, no re-displaying the room -- just the conversation panel, clean and focused.

3. **Every option is visible.** No guessing syntax. The player sees numbered choices and picks one. Options can appear or disappear based on flags and inventory, but the player never needs to invent a command.

4. **Trees, not flat lists.** Dialogue is a directed graph of nodes. Each node is something the NPC says. Each node has outgoing edges (options) that lead to other nodes. This allows conversations to branch, converge, loop, and terminate naturally.

5. **Inventory and flag reactivity.** Options can require flags (game state) or items (player inventory). If the player has bolt cutters, a new option appears. If the player already learned about zombies from another source, a shortcut option appears. The conversation adapts to the player's state.

6. **Everything is deterministic.** Dialogue trees live in SQLite. Node selection is deterministic. No LLM at runtime (unless narrator mode is active, which only flavors existing text).

---

## What Gets Removed

### From the Engine (`game.py`)

| Component | Lines | Reason |
|---|---|---|
| `_handle_ask()` | ~24 lines | No more `ask {npc} about {topic}` command |
| `_show_available_topics()` | ~27 lines | No more topic hints; replaced by numbered options |
| Greeting handler block | ~18 lines | No more `hello`/`hi`/`hey`/`greetings` shortcuts |
| `ask` verb parsing block | ~9 lines | No more `ask` command parsing in the main loop |
| `STYLE_TOPIC` constant | 1 line | No more topic styling (topics do not exist) |

### Modified in the Engine

| Component | Change |
|---|---|
| `_handle_talk()` | Complete rewrite: enters dialogue mode instead of picking a single line |
| `_pick_dialogue()` | Removed or repurposed: node selection replaces priority-based line selection |
| `_apply_dialogue_flags()` | Kept but refactored: called when entering a node, not when picking a line |
| `talk` verb parsing | Kept as-is: `talk to {npc}` and `talk {npc}` both trigger dialogue mode |
| Help text | Updated: remove `ask` references, mention dialogue mode |

### From the Schema

| Component | Change |
|---|---|
| `dialogue` table | Dropped entirely, replaced by `dialogue_nodes` and `dialogue_options` |
| `topic` column | Gone: topics do not exist in the tree model |
| `priority` column | Gone: node selection is explicit (options point to specific nodes), not priority-based |
| `is_delivered` column | Gone: replaced by tracking which nodes have been visited via flags or a visited-nodes table |
| `idx_dialogue_topic` index | Dropped |

### From the DB Interface (`schema.py`)

| Method | Change |
|---|---|
| `get_npc_dialogue()` | Removed: replaced by `get_dialogue_node()` and `get_dialogue_options()` |
| `get_npc_topics()` | Removed: no topics |
| `mark_dialogue_delivered()` | Removed: no delivery tracking in the old sense |
| `insert_dialogue()` | Removed: replaced by `insert_dialogue_node()` and `insert_dialogue_option()` |

### From the Generator (`npcs.py`)

| Component | Change |
|---|---|
| `dialogue_entries` in JSON schema | Replaced by `dialogue_tree` structure |
| `topic` field in schema | Removed |
| `priority` field in schema | Removed |
| Prompt text about topics and `ask about` | Rewritten for tree-based dialogue |

### From the Test Game (`build_test_game.py`)

| Component | Change |
|---|---|
| All `insert_dialogue()` calls | Replaced by `insert_dialogue_node()` and `insert_dialogue_option()` calls |
| `ask_maria_zombies` command | Removed (handled by dialogue tree) |
| `ask_maria_station` command | Removed (handled by dialogue tree) |
| Any DSL commands that duplicate dialogue functionality | Removed |

---

## Schema Design

### New Table: `dialogue_nodes`

Every node is something the NPC says. One node per NPC is the root (entry point). Terminal nodes have no outgoing options -- the conversation ends or loops back.

```sql
CREATE TABLE IF NOT EXISTS dialogue_nodes (
    id          TEXT PRIMARY KEY,
    npc_id      TEXT    NOT NULL REFERENCES npcs(id),
    content     TEXT    NOT NULL,
    set_flags   TEXT,               -- JSON array of flag IDs to set on entry, or NULL
    is_root     INTEGER NOT NULL DEFAULT 0,  -- 1 = conversation starts here
    is_terminal INTEGER NOT NULL DEFAULT 0   -- 1 = conversation ends after this node
);

CREATE INDEX IF NOT EXISTS idx_dialogue_nodes_npc_id ON dialogue_nodes(npc_id);
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `maria_root`, `maria_zombies_response`. |
| `npc_id` | TEXT REFERENCES npcs(id) | Yes | The NPC this node belongs to. |
| `content` | TEXT | Yes | What the NPC says at this node. This is the dialogue text displayed in the conversation panel. |
| `set_flags` | TEXT | No | JSON array of flag IDs to set when the player enters this node. Example: `["spoke_to_maria", "knows_about_zombies"]`. |
| `is_root` | INTEGER | Yes | `1` = this is the entry point when the player types `talk to {npc}`. Exactly one node per NPC must be the root. Default `0`. |
| `is_terminal` | INTEGER | Yes | `1` = the conversation ends after displaying this node (auto-exit or "press any key to continue"). Default `0`. |

### New Table: `dialogue_options`

Each option is a choice the player can make at a given node. Options point to a target node. Options can be gated by flags and/or inventory.

```sql
CREATE TABLE IF NOT EXISTS dialogue_options (
    id              TEXT PRIMARY KEY,
    node_id         TEXT    NOT NULL REFERENCES dialogue_nodes(id),
    text            TEXT    NOT NULL,
    next_node_id    TEXT    REFERENCES dialogue_nodes(id),  -- NULL = exit conversation
    sort_order      INTEGER NOT NULL DEFAULT 0,
    required_flags  TEXT,   -- JSON array of flag IDs, or NULL (always available)
    required_items  TEXT,   -- JSON array of item IDs, or NULL (always available)
    set_flags       TEXT    -- JSON array of flag IDs to set when chosen, or NULL
);

CREATE INDEX IF NOT EXISTS idx_dialogue_options_node_id ON dialogue_options(node_id);
```

### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | TEXT PRIMARY KEY | Yes | Unique identifier: `maria_opt_ask_zombies`, `maria_opt_show_bolt_cutters`. |
| `node_id` | TEXT REFERENCES dialogue_nodes(id) | Yes | The node this option appears at. |
| `text` | TEXT | Yes | The text shown to the player as a numbered choice. Example: `"What happened at the hospital?"` |
| `next_node_id` | TEXT REFERENCES dialogue_nodes(id) | No | The node to navigate to when this option is chosen. `NULL` = exit the conversation (equivalent to "goodbye"). |
| `sort_order` | INTEGER | Yes | Controls display order. Lower numbers appear first. Default `0`. |
| `required_flags` | TEXT | No | JSON array of flag IDs that must all be set for this option to appear. Example: `["spoke_to_maria"]`. |
| `required_items` | TEXT | No | JSON array of item IDs that must all be in the player's inventory for this option to appear. Example: `["bolt_cutters"]`. |
| `set_flags` | TEXT | No | JSON array of flag IDs to set when the player chooses this option (before navigating to `next_node_id`). |

### Relationship Map Update

```
npcs ──< dialogue_nodes (npc_id)
              │
              └──< dialogue_options (node_id)
                        │
                        └── references dialogue_nodes (next_node_id)
```

### Design Decisions

**Why two tables instead of JSON?** A JSON tree stored on the NPC row would be simpler to insert but harder to query. The engine needs to: (1) find the root node for an NPC, (2) find all options for a node, (3) check flag/item requirements per option, (4) navigate to the next node. Two tables with indexes make each of these a single indexed query. JSON would require parsing the entire tree into memory every time.

**Why `next_node_id = NULL` means exit?** This is the simplest representation for "end the conversation." An option with `text = "[Leave conversation]"` and `next_node_id = NULL` is a natural exit ramp. The engine interprets NULL as "return to the normal game loop."

**Why `sort_order` instead of relying on insertion order?** SQLite does not guarantee row order without ORDER BY. `sort_order` gives the game designer explicit control over which options appear first, and lets the generator interleave inventory-reactive options at specific positions.

**Why `set_flags` on both nodes and options?** Nodes set flags when the player hears information ("you now know about zombies"). Options set flags when the player makes a choice ("you chose to confront Maria about the hospital"). These are different narrative moments. A node's `set_flags` fire on entry regardless of how the player got there. An option's `set_flags` fire on selection before navigating away.

**Why `is_terminal`?** Some nodes are dead ends -- the NPC says their piece and the conversation is over. Without `is_terminal`, the engine would need to check "does this node have any options?" every time. The flag makes intent explicit and lets the engine handle terminal nodes differently (e.g., a brief pause before returning to the game loop, or a "[Continue]" prompt).

---

## Engine Changes

### Dialogue Mode Overview

When the player types `talk to {npc}`:

1. Engine finds the NPC in the current room (existing logic, unchanged).
2. Engine queries `dialogue_nodes` for the root node (`is_root = 1`) for that NPC.
3. Engine enters **dialogue mode** -- a sub-loop that suspends the normal game loop.
4. In dialogue mode, the engine renders the conversation panel and reads numbered input.
5. When the player exits (chooses an exit option, types `0`, `exit`, `leave`, or `bye`), the engine returns to the normal game loop.

### Rendering: Rich Live Display

The conversation renders inside a Rich `Panel`, updated in-place using `Live` (or `Console.clear` + reprint if `Live` causes issues with input).

```
+-- Talking to Maria -----------------------------------------+
|                                                             |
|  Maria: "I'm Maria. I was working the night shift at        |
|  St. Agnes when it all went to hell."                       |
|                                                             |
|  1. "What happened at the hospital?"                        |
|  2. "Do you know about the gas station?"                    |
|  3. "What do you know about them?" (zombies)                |
|  4. "I found bolt cutters." [NEW]                           |
|  5. [Leave conversation]                                    |
|                                                             |
+-------------------------------------------------------------+
> _
```

Implementation notes:

- The panel title is `"Talking to {npc_name}"` styled with `STYLE_NPC`.
- The NPC's line is the `content` field of the current node, prefixed with the NPC's name in `STYLE_NPC`.
- Options are numbered starting at 1. The last option is always `[Leave conversation]` (auto-appended by the engine, not stored in the database).
- Options gated by inventory that are currently visible get a `[NEW]` tag or similar marker to draw attention.
- The prompt is `> ` matching the normal game prompt.

### Input Handling in Dialogue Mode

The dialogue mode sub-loop accepts:

| Input | Behavior |
|---|---|
| `1` through `N` | Select the corresponding option |
| `0` | Exit the conversation |
| `exit`, `leave`, `bye`, `quit` | Exit the conversation |
| Anything else | Redisplay with a gentle "Pick a number" message |

### Node Transition Logic

When the player picks option `N`:

1. Look up the option by its position in the filtered, sorted options list.
2. Apply the option's `set_flags` (if any).
3. Read `next_node_id`. If `NULL`, exit dialogue mode.
4. Load the target node from `dialogue_nodes`.
5. Apply the node's `set_flags` (if any).
6. If `is_terminal = 1`, display the node's content, pause briefly, then exit dialogue mode.
7. Otherwise, query `dialogue_options` for the new node, filter by flags/items, render the updated panel.

### Option Filtering

For each option at the current node:

1. **Check `required_flags`**: Parse the JSON array. For each flag, call `db.has_flag(flag)`. If any flag is not set, hide the option.
2. **Check `required_items`**: Parse the JSON array. For each item ID, check if that item is in `db.get_inventory()`. If any item is missing, hide the option.
3. If both checks pass (or both are NULL), the option is visible.

This filtering happens every time a node is rendered, so the option list adapts in real time to the player's state (though in practice, inventory and flags do not change during a conversation unless a node's `set_flags` unlock something).

### What Happens When a Node Has No Visible Options

If all options at a node are hidden by flag/item requirements and the node is not marked `is_terminal`, the engine treats it as terminal: display the content, then auto-exit. This is a safety net -- well-designed trees should not reach this state, but the engine must not deadlock.

The auto-appended `[Leave conversation]` option is always visible regardless of flags or items, so in practice this situation only arises if the designer sets `is_terminal = 1` explicitly.

### Returning to the Game Loop

When dialogue mode exits:

1. The `Live` display stops (or the screen clears the dialogue panel).
2. The engine does NOT redisplay the room. The player is still in the same room and knows where they are.
3. The game loop resumes from the next iteration. If the player types `look`, they see the room again.
4. One tick (move) is consumed for the entire conversation, not per dialogue choice. Entering a conversation costs one move; navigating within it is free.

---

## Inventory-Reactive Dialogue

### How It Works

Dialogue options can require items via the `required_items` field. The engine checks the player's current inventory when rendering options. If the player has the required item(s), the option appears. If not, it is hidden.

This creates a natural, organic way for items to matter in conversations:

- **Player finds bolt cutters** -> talks to Maria -> new option appears: "I found bolt cutters."
- **Player finds registration papers** -> talks to Maria -> new option appears: "I found some papers in a car."
- **Player has no special items** -> talks to Maria -> only the base conversation tree is visible.

### Design Rules for Inventory-Reactive Options

1. **Additive, not subtractive.** Items add options; they never remove them. The base conversation tree is always available regardless of inventory.

2. **Items are not consumed.** Choosing an inventory-reactive dialogue option does not remove the item from inventory. The conversation acknowledges the item but the player keeps it. If the item needs to change hands, that is a separate DSL command action outside of dialogue.

3. **Combine with flags for one-shot reveals.** To prevent the player from seeing the same inventory-reactive option repeatedly, the option should set a flag on selection, and a subsequent version of that node's options should require that flag to NOT be set (or the option simply does not reappear because the conversation tree has moved past it via flag gating).

4. **Mark new options visually.** Options that appeared because of inventory should be marked in the display (e.g., `[NEW]` suffix) so the player notices them. The engine determines "new" by checking if the option has `required_items` set and the option's `set_flags` have not yet been triggered. This is a display hint, not a database field.

### Example: Bolt Cutters and Maria

When the player has `bolt_cutters` in inventory and talks to Maria, the root node's options include:

```
4. "I found bolt cutters." [NEW]
```

This option leads to a node where Maria reacts:

```
Maria: "Bolt cutters? That's exactly what we need. The gas station
door is chained shut. Cut the chain and you're in."
```

This node sets `maria_knows_about_cutters` flag and returns to the main conversation hub (or exits).

---

## Flag Integration

### Flags on Nodes (`dialogue_nodes.set_flags`)

Set when the player **enters** a node. This represents the player learning information or triggering a story beat by hearing what the NPC says.

Examples:
- `maria_root` sets `["spoke_to_maria"]` -- just talking to Maria counts as meeting her.
- `maria_zombies_response` sets `["knows_about_zombies"]` -- hearing Maria's zombie explanation gives the player that knowledge.

### Flags on Options (`dialogue_options.set_flags`)

Set when the player **chooses** an option. This represents the player making a deliberate choice that the game should remember.

Examples:
- Choosing "I found bolt cutters" sets `["told_maria_about_cutters"]` -- the player chose to share this information.
- Choosing "I don't trust you" sets `["suspicious_of_maria"]` -- this could gate later interactions.

### Flags as Requirements (`required_flags`)

Options can require flags to appear. This enables:

- **Progressive revelation**: After learning about zombies, new questions about zombie behavior become available.
- **Cross-NPC continuity**: Learning something from the radio unlocks a dialogue option with Maria ("I heard a broadcast...").
- **Return conversations**: After the player has explored and set various flags, returning to an NPC reveals new conversation branches they did not have before.

### Flag Interaction with Existing Systems

Dialogue flags integrate with the same flag table used by the command DSL, puzzles, quests, and locks. Setting `spoke_to_maria` in dialogue is the same flag that the quest system checks for the "Talk to Maria" objective. No translation layer needed.

---

## The `default_dialogue` Field on NPCs

The `default_dialogue` field on the `npcs` table is **kept but repurposed**. It serves as the fallback when:

1. The NPC has no dialogue tree at all (e.g., a hostile NPC, or a non-speaking NPC like a zombie).
2. The NPC's root node cannot be found due to data corruption or migration from an older `.zork` format.

For NPCs with dialogue trees, `default_dialogue` is never displayed during normal play. The root node's `content` field serves as the NPC's opening line.

---

## Generation Pipeline Changes

### NPC Pass (`npcs.py`)

The NPC generation pass changes significantly. Instead of generating flat `dialogue_entries` with topics and priorities, the LLM generates a `dialogue_tree` structure.

### Updated JSON Schema for LLM Output

```json
{
  "type": "object",
  "required": ["npcs"],
  "properties": {
    "npcs": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name", "description", "examine_description",
                     "room_id", "default_dialogue", "dialogue_tree"],
        "properties": {
          "id": { "type": "string" },
          "name": { "type": "string" },
          "description": { "type": "string" },
          "examine_description": { "type": "string" },
          "room_id": { "type": "string" },
          "default_dialogue": { "type": "string" },
          "is_blocking": { "type": "integer", "enum": [0, 1] },
          "blocked_exit_id": { "type": ["string", "null"] },
          "unblock_flag": { "type": ["string", "null"] },
          "hp": { "type": ["integer", "null"] },
          "damage": { "type": ["integer", "null"] },
          "dialogue_tree": {
            "type": "object",
            "required": ["nodes", "options"],
            "properties": {
              "nodes": {
                "type": "array",
                "items": {
                  "type": "object",
                  "required": ["id", "content"],
                  "properties": {
                    "id": {
                      "type": "string",
                      "description": "Unique snake_case ID for this node."
                    },
                    "content": {
                      "type": "string",
                      "description": "What the NPC says at this node."
                    },
                    "set_flags": {
                      "type": ["array", "null"],
                      "items": { "type": "string" },
                      "description": "Flags to set when the player enters this node."
                    },
                    "is_root": {
                      "type": "integer",
                      "enum": [0, 1],
                      "description": "1 = conversation entry point. Exactly one per NPC."
                    },
                    "is_terminal": {
                      "type": "integer",
                      "enum": [0, 1],
                      "description": "1 = conversation ends after this node."
                    }
                  }
                }
              },
              "options": {
                "type": "array",
                "items": {
                  "type": "object",
                  "required": ["id", "node_id", "text"],
                  "properties": {
                    "id": {
                      "type": "string",
                      "description": "Unique snake_case ID for this option."
                    },
                    "node_id": {
                      "type": "string",
                      "description": "The node this option appears at."
                    },
                    "text": {
                      "type": "string",
                      "description": "Player-facing choice text."
                    },
                    "next_node_id": {
                      "type": ["string", "null"],
                      "description": "Node to go to. null = exit conversation."
                    },
                    "sort_order": {
                      "type": "integer",
                      "description": "Display order (lower = first)."
                    },
                    "required_flags": {
                      "type": ["array", "null"],
                      "items": { "type": "string" },
                      "description": "Flags required for this option to appear."
                    },
                    "required_items": {
                      "type": ["array", "null"],
                      "items": { "type": "string" },
                      "description": "Item IDs the player must have for this option to appear."
                    },
                    "set_flags": {
                      "type": ["array", "null"],
                      "items": { "type": "string" },
                      "description": "Flags to set when this option is chosen."
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

### Updated Prompt Guidance

The NPC pass prompt needs to instruct the LLM to design dialogue as branching trees. Key changes to the prompt:

1. **Remove** all references to `topic`, `ask about`, and priority-based selection.
2. **Add** dialogue tree design guidance:
   - Each NPC must have exactly one root node (`is_root: 1`).
   - The root node is the NPC's opening line when the player first talks to them.
   - Options at the root should cover the NPC's major conversation topics.
   - Deeper nodes provide detail on specific topics.
   - Use `set_flags` to track what the player has learned.
   - Use `required_flags` on options to create progressive conversations -- not everything is available on the first visit.
   - Use `required_items` on options to make conversations react to the player's inventory.
   - Terminal nodes should be used for final remarks or one-off information.
   - Design for re-entry: if the player talks to the NPC again after exiting, they hit the root node again. Options they already explored can be hidden via flag requirements, or left available for re-reading.

3. **Add** inventory-reactive guidance:
   - Review the items list. Identify items that an NPC would plausibly react to.
   - Create options gated by `required_items` for those items.
   - These options should lead to nodes where the NPC acknowledges the item and provides useful information or advances the story.

4. **Add** structural constraints:
   - Maximum tree depth of 4 levels (root -> level 1 -> level 2 -> level 3). Deeper trees feel like interrogation, not conversation.
   - Maximum 5 options per node (not counting the engine-appended "Leave" option). More than 5 is overwhelming.
   - Every non-terminal node must have at least one option that is always available (no flag or item requirements). The player must never be stuck in a node with all options hidden.

### Validation Changes

The `_validate_npcs()` function needs new checks:

1. **Exactly one root node per NPC.** Zero roots = the NPC cannot be talked to. Multiple roots = ambiguous.
2. **All `next_node_id` references resolve.** Every option's target node must exist in the same NPC's node list.
3. **No orphan nodes.** Every non-root node must be reachable from at least one option. (Warning, not error -- orphan nodes waste space but do not break anything.)
4. **At least one unconditional option per non-terminal node.** If every option at a node has requirements, the player could get stuck with no choices.
5. **Node IDs are globally unique across all NPCs.** Same constraint as the current `dialogue.id` uniqueness.
6. **Option IDs are globally unique across all NPCs.** Prevents collision in the database.

### Database Insertion Changes

The `_insert_npcs()` function changes to insert nodes and options:

```python
for node in npc.get("dialogue_tree", {}).get("nodes", []):
    db.insert_dialogue_node(
        id=node["id"],
        npc_id=npc["id"],
        content=node["content"],
        set_flags=json.dumps(node["set_flags"]) if node.get("set_flags") else None,
        is_root=node.get("is_root", 0),
        is_terminal=node.get("is_terminal", 0),
    )

for option in npc.get("dialogue_tree", {}).get("options", []):
    db.insert_dialogue_option(
        id=option["id"],
        node_id=option["node_id"],
        text=option["text"],
        next_node_id=option.get("next_node_id"),
        sort_order=option.get("sort_order", 0),
        required_flags=json.dumps(option["required_flags"]) if option.get("required_flags") else None,
        required_items=json.dumps(option["required_items"]) if option.get("required_items") else None,
        set_flags=json.dumps(option["set_flags"]) if option.get("set_flags") else None,
    )
```

---

## New DB Interface Methods

### `insert_dialogue_node(**fields)`

Insert a single `dialogue_nodes` row. Same pattern as `insert_dialogue()`.

### `insert_dialogue_option(**fields)`

Insert a single `dialogue_options` row. Same pattern.

### `get_dialogue_root(npc_id: str) -> dict | None`

```sql
SELECT * FROM dialogue_nodes
WHERE npc_id = ? AND is_root = 1
LIMIT 1
```

Returns the root node for an NPC, or `None` if the NPC has no dialogue tree.

### `get_dialogue_node(node_id: str) -> dict | None`

```sql
SELECT * FROM dialogue_nodes WHERE id = ?
```

Returns a single node by ID.

### `get_dialogue_options(node_id: str) -> list[dict]`

```sql
SELECT * FROM dialogue_options
WHERE node_id = ?
ORDER BY sort_order
```

Returns all options for a given node, ordered by `sort_order`. The engine filters by flags/items after fetching.

---

## Full Example: Maria's Dialogue Tree (Zombie Test Game)

This replaces all of Maria's current `insert_dialogue()` calls with a complete dialogue tree.

### Node Map

```
maria_root (ROOT)
  "I'm Maria. I was working the night shift at St. Agnes
   when it all went to hell."
  Sets: [spoke_to_maria]
    |
    +-- opt: "What happened at the hospital?"
    |   -> maria_hospital
    |      "People started biting. Patients, visitors, security.
    |       I grabbed this axe and ran. They're slow during the
    |       day but faster at night."
    |      Sets: [knows_about_zombies]
    |        |
    |        +-- opt: "Faster at night?"
    |        |   -> maria_night_detail
    |        |      "Much faster. You've got maybe two hours of
    |        |       daylight left. Move now or don't move at all."
    |        |      (TERMINAL)
    |        |
    |        +-- opt: (back to hub) -> maria_hub
    |
    +-- opt: "Do you know about the gas station?"
    |   -> maria_gas_station
    |      "The gas station door is chained shut from outside.
    |       You'll need bolt cutters. There was a car on the
    |       street... check the trunk maybe."
    |      Sets: [knows_about_station]
    |        |
    |        +-- opt: (back to hub) -> maria_hub
    |
    +-- opt: "What do you know about this building?"
    |   -> maria_building
    |      "Most apartments are empty. Don't go upstairs past
    |       the third floor. I heard sounds. Not human sounds."
    |        |
    |        +-- opt: (back to hub) -> maria_hub
    |
    +-- opt: "I found bolt cutters." [requires: bolt_cutters]
    |   -> maria_bolt_cutters_reaction
    |      "Bolt cutters? That's exactly what we need. Cut the
    |       chain on the gas station and you're in. Be careful
    |       though -- we don't know what's inside."
    |      Sets: [told_maria_about_cutters]
    |        |
    |        +-- opt: (back to hub) -> maria_hub
    |
    +-- opt: "I found some papers in a car." [requires: car_registration]
    |   -> maria_registration_reaction
    |      "Marcus Webb... I know that name. He ran the gas
    |       station. If he left keys inside, they'd be behind
    |       the counter. That's where he kept everything."
    |      Sets: [maria_confirmed_keys_location]
    |        |
    |        +-- opt: (back to hub) -> maria_hub
    |
    (Engine auto-appends: [Leave conversation])

maria_hub
  "Maria watches you, waiting."
  (Same options as root, minus already-explored ones via flags)
    |
    +-- opt: "What happened at the hospital?" [requires NOT knows_about_zombies]
    |   -> maria_hospital
    |
    +-- opt: "Do you know about the gas station?" [requires NOT knows_about_station]
    |   -> maria_gas_station
    |
    +-- opt: "What do you know about this building?"
    |   -> maria_building
    |
    +-- opt: "I found bolt cutters." [requires: bolt_cutters, requires NOT told_maria_about_cutters]
    |   -> maria_bolt_cutters_reaction
    |
    +-- opt: "I found some papers in a car." [requires: car_registration, requires NOT maria_confirmed_keys_location]
    |   -> maria_registration_reaction
    |
    (Engine auto-appends: [Leave conversation])
```

### Required Schema Addition: `not_flags`

The hub pattern above reveals a need: options that should disappear once a flag is set. Two approaches:

**Option A: Add `not_flags` field.** A JSON array of flags that must NOT be set for the option to appear. This is the inverse of `required_flags`.

**Option B: Use separate hub nodes per state.** Create `maria_hub_fresh`, `maria_hub_after_zombies`, etc. This explodes the node count and is fragile.

**Decision: Option A.** Add `not_flags` (or `excluded_flags`) to `dialogue_options`. This is a minimal, high-value addition that prevents node explosion.

Updated `dialogue_options` schema:

```sql
CREATE TABLE IF NOT EXISTS dialogue_options (
    id              TEXT PRIMARY KEY,
    node_id         TEXT    NOT NULL REFERENCES dialogue_nodes(id),
    text            TEXT    NOT NULL,
    next_node_id    TEXT    REFERENCES dialogue_nodes(id),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    required_flags  TEXT,   -- JSON array: all must be set
    excluded_flags  TEXT,   -- JSON array: none may be set
    required_items  TEXT,   -- JSON array: all must be in inventory
    set_flags       TEXT    -- JSON array: set when chosen
);
```

The engine's option filtering now checks three conditions:

1. All `required_flags` are set (or field is NULL).
2. No `excluded_flags` are set (or field is NULL).
3. All `required_items` are in inventory (or field is NULL).

All three must pass for the option to be visible.

### Database Entries for Maria

#### Nodes

| id | npc_id | content | set_flags | is_root | is_terminal |
|---|---|---|---|---|---|
| `maria_root` | `survivor_maria` | "I'm Maria. I was working the night shift at St. Agnes when it all went to hell." | `["spoke_to_maria"]` | 1 | 0 |
| `maria_hub` | `survivor_maria` | Maria watches you, waiting. | NULL | 0 | 0 |
| `maria_hospital` | `survivor_maria` | "People started biting. Patients, visitors, security. I grabbed this axe and ran." She swallows hard. "They're slow during the day but faster at night." | `["knows_about_zombies"]` | 0 | 0 |
| `maria_night_detail` | `survivor_maria` | "Much faster. If you're going to move, do it now -- you've got maybe two hours of daylight left. After that..." She shakes her head. "Don't be out after dark." | NULL | 0 | 1 |
| `maria_gas_station` | `survivor_maria` | "The gas station door is chained shut from outside. Someone locked it to keep them out -- or to keep something in. You'll need bolt cutters. There was a car parked on the street... check the trunk maybe." She shakes her head. "I'm not going out there. Not again." | `["knows_about_station"]` | 0 | 0 |
| `maria_building` | `survivor_maria` | "Most of the apartments are empty. People either evacuated early or..." She trails off. "Don't go upstairs past the third floor. I heard sounds from up there. Not human sounds." | NULL | 0 | 0 |
| `maria_bolt_cutters_react` | `survivor_maria` | Maria's eyes widen. "Bolt cutters? That's what we need. The gas station door is chained shut -- cut the chain and you're in. Be careful though. We don't know what's inside." | `["told_maria_about_cutters"]` | 0 | 0 |
| `maria_registration_react` | `survivor_maria` | "Marcus Webb..." Maria frowns. "I know that name. He ran the gas station. If he left keys inside, they'd be behind the counter. That's where he kept everything." | `["maria_confirmed_keys_location"]` | 0 | 0 |

#### Options

| id | node_id | text | next_node_id | sort_order | required_flags | excluded_flags | required_items | set_flags |
|---|---|---|---|---|---|---|---|---|
| `maria_root_opt_hospital` | `maria_root` | "What happened at the hospital?" | `maria_hospital` | 10 | NULL | NULL | NULL | NULL |
| `maria_root_opt_station` | `maria_root` | "Do you know about the gas station?" | `maria_gas_station` | 20 | NULL | NULL | NULL | NULL |
| `maria_root_opt_building` | `maria_root` | "What do you know about this building?" | `maria_building` | 30 | NULL | NULL | NULL | NULL |
| `maria_root_opt_cutters` | `maria_root` | "I found bolt cutters." | `maria_bolt_cutters_react` | 40 | NULL | `["told_maria_about_cutters"]` | `["bolt_cutters"]` | NULL |
| `maria_root_opt_papers` | `maria_root` | "I found some papers in a car." | `maria_registration_react` | 50 | NULL | `["maria_confirmed_keys_location"]` | `["car_registration"]` | NULL |
| `maria_hospital_opt_night` | `maria_hospital` | "Faster at night?" | `maria_night_detail` | 10 | NULL | NULL | NULL | NULL |
| `maria_hospital_opt_back` | `maria_hospital` | "Tell me about something else." | `maria_hub` | 90 | NULL | NULL | NULL | NULL |
| `maria_station_opt_back` | `maria_gas_station` | "Tell me about something else." | `maria_hub` | 90 | NULL | NULL | NULL | NULL |
| `maria_building_opt_back` | `maria_building` | "Tell me about something else." | `maria_hub` | 90 | NULL | NULL | NULL | NULL |
| `maria_cutters_opt_back` | `maria_bolt_cutters_react` | "Tell me about something else." | `maria_hub` | 90 | NULL | NULL | NULL | NULL |
| `maria_papers_opt_back` | `maria_registration_react` | "Tell me about something else." | `maria_hub` | 90 | NULL | NULL | NULL | NULL |
| `maria_hub_opt_hospital` | `maria_hub` | "What happened at the hospital?" | `maria_hospital` | 10 | NULL | `["knows_about_zombies"]` | NULL | NULL |
| `maria_hub_opt_station` | `maria_hub` | "Do you know about the gas station?" | `maria_gas_station` | 20 | NULL | `["knows_about_station"]` | NULL | NULL |
| `maria_hub_opt_building` | `maria_hub` | "What do you know about this building?" | `maria_building` | 30 | NULL | NULL | NULL | NULL |
| `maria_hub_opt_cutters` | `maria_hub` | "I found bolt cutters." | `maria_bolt_cutters_react` | 40 | NULL | `["told_maria_about_cutters"]` | `["bolt_cutters"]` | NULL |
| `maria_hub_opt_papers` | `maria_hub` | "I found some papers in a car." | `maria_registration_react` | 50 | NULL | `["maria_confirmed_keys_location"]` | `["car_registration"]` | NULL |

### Conversation Flow Example

**First visit, no special items:**

```
+-- Talking to Maria ------------------------------------------+
|                                                              |
|  Maria: "I'm Maria. I was working the night shift at         |
|  St. Agnes when it all went to hell."                        |
|                                                              |
|  1. "What happened at the hospital?"                         |
|  2. "Do you know about the gas station?"                     |
|  3. "What do you know about this building?"                  |
|  4. [Leave conversation]                                     |
|                                                              |
+--------------------------------------------------------------+
> 1
```

Player picks 1. Engine loads `maria_hospital`, sets `knows_about_zombies`:

```
+-- Talking to Maria ------------------------------------------+
|                                                              |
|  Maria: "People started biting. Patients, visitors,          |
|  security. I grabbed this axe and ran." She swallows hard.   |
|  "They're slow during the day but faster at night."          |
|                                                              |
|  1. "Faster at night?"                                       |
|  2. "Tell me about something else."                          |
|  3. [Leave conversation]                                     |
|                                                              |
+--------------------------------------------------------------+
> 2
```

Player picks 2. Engine loads `maria_hub`. Since `knows_about_zombies` is now set, the hospital option is hidden:

```
+-- Talking to Maria ------------------------------------------+
|                                                              |
|  Maria watches you, waiting.                                 |
|                                                              |
|  1. "Do you know about the gas station?"                     |
|  2. "What do you know about this building?"                  |
|  3. [Leave conversation]                                     |
|                                                              |
+--------------------------------------------------------------+
```

**Second visit, after finding bolt cutters:**

```
+-- Talking to Maria ------------------------------------------+
|                                                              |
|  Maria: "I'm Maria. I was working the night shift at         |
|  St. Agnes when it all went to hell."                        |
|                                                              |
|  1. "Do you know about the gas station?"                     |
|  2. "What do you know about this building?"                  |
|  3. "I found bolt cutters." [NEW]                            |
|  4. [Leave conversation]                                     |
|                                                              |
+--------------------------------------------------------------+
```

The hospital option is hidden (already explored, `knows_about_zombies` is set). The bolt cutters option appeared because the player now has the item.

---

## Re-entry Behavior

When the player exits a conversation and later types `talk to {npc}` again, the engine always starts at the root node. The root node's `set_flags` fire again, but since flags are idempotent (setting an already-true flag is a no-op), this has no side effects.

The conversation adapts to the player's current state because option visibility depends on flags and inventory, which persist. Topics the player already explored are hidden (via `excluded_flags`), and new topics may appear (via `required_flags` or `required_items`).

This means the root node's content might feel repetitive. Two mitigation strategies:

1. **Root content should be brief on return.** The root node's text should work both as an introduction and as a "what do you want?" prompt. Maria's root line works for this -- it is her identity statement, and hearing it twice is not offensive.

2. **Use a flag-gated second root (optional enhancement).** The generator could create a `maria_root_return` node with different content ("Back again? What do you need?") and gate the original root with `excluded_flags: ["spoke_to_maria"]`. This is a generation-time optimization, not an engine feature -- the engine always loads `is_root = 1`.

    If we want to support this, the engine change is: find root node, then check if there is a higher-priority root (e.g., a root node with `required_flags` that are met). But this adds priority-based selection back into the system, which is what we are trying to remove. **Decision: keep it simple. One root, brief content. The LLM can write root content that works on repeat.**

---

## Radio Voice: Non-Conversational NPC

Not every NPC needs a dialogue tree. The radio voice in the gas station is a broadcast -- it speaks at you, not with you. For NPCs like this:

- The NPC has a dialogue tree with a single root node and no options.
- `is_terminal = 1` on the root node.
- The player types `talk to radio` (or `listen to radio`), hears the broadcast, and the conversation auto-exits.
- For the radio's second topic ("checkpoint"), create a second node reachable via one option at the root, gated by `required_flags: ["heard_broadcast"]`.

This keeps the radio within the dialogue tree system without forcing a full conversation tree on a one-directional NPC.

### Radio Dialogue Tree

| Node ID | Content | set_flags | is_root | is_terminal |
|---|---|---|---|---|
| `radio_root` | The radio crackles: "...this is an automated emergency broadcast. Evacuation route: Highway 1 North. Checkpoint at mile marker 40. Bring supplies. Bring fuel. Do not travel after dark. This message will repeat..." | `["heard_broadcast"]` | 1 | 0 |
| `radio_checkpoint` | "...military checkpoint is at mile marker 40. Medical tents, food, water. Armed perimeter. If you can get there, you're safe. Key word: if. The highway is not clear. Drive fast. Don't stop for anything. Over and out." | `["knows_about_checkpoint"]` | 0 | 1 |

| Option ID | node_id | text | next_node_id | required_flags |
|---|---|---|---|---|
| `radio_opt_checkpoint` | `radio_root` | "Listen for more details." | `radio_checkpoint` | `["heard_broadcast"]` |

Wait -- this is the root node, and `heard_broadcast` is set by entering the root. So the option would be visible immediately. That is correct: the player hears the broadcast, then can choose to listen for more.

---

## How This Affects the Test Game

### Changes to `build_test_game.py`

1. **Remove** all 6 `insert_dialogue()` calls (maria_talk_default, maria_about_zombies, maria_about_gas_station, maria_about_building, radio_default, radio_about_checkpoint).

2. **Add** `insert_dialogue_node()` calls for all nodes listed in the Maria and Radio trees above (8 Maria nodes + 2 radio nodes = 10 nodes).

3. **Add** `insert_dialogue_option()` calls for all options listed above (16 Maria options + 1 radio option = 17 options).

4. **Remove** the `ask_maria_zombies` and `ask_maria_station` DSL commands. These are now handled by the dialogue tree. (The score points they awarded should be moved to node/option `set_flags` or to quest objectives.)

5. **Add** new flags: `told_maria_about_cutters`, `maria_confirmed_keys_location`. These integrate with the existing flag table.

6. **Update** quest objectives if any depend on specific dialogue IDs that have changed.

### Score Integration

The current `ask_maria_zombies` command awards 2 points, and `ask_maria_station` awards 2 points. These need to be preserved. Two options:

1. **Move scoring to quest objectives.** The quest "The Survivor's Story" already tracks dialogue-related flags. Add objectives for "Learn about zombies" (flag: `knows_about_zombies`, score: 2) and "Learn about gas station" (flag: `knows_about_station`, score: 2).

2. **Add score effects to dialogue nodes.** This would require adding a `score` field to `dialogue_nodes`. This is scope creep for the dialogue system -- scoring should stay in the quest/command system.

**Decision: option 1.** Move score points to quest objectives. The dialogue tree sets flags; the quest system awards points when those flags are set. This keeps the dialogue system focused on conversation and the quest system focused on progression rewards.

---

## Migration Path

### Old `.zork` Files

Old `.zork` files have the `dialogue` table but not `dialogue_nodes` or `dialogue_options`. The engine should:

1. On startup, check if `dialogue_nodes` exists.
2. If it does not exist, fall back to the old `_handle_talk()` behavior (or simply show `default_dialogue` and skip conversation mode).
3. Never crash on an old file. Graceful degradation.

This is a temporary measure. Once the new system is stable, old files can be considered unsupported for dialogue features.

### Schema Version

The `metadata` table has a `version` field. Bump it from `1.0` to `1.1` (or whatever the next version is). The engine checks the version and adjusts behavior accordingly.

---

## Summary of All Changes

| Component | File | Change Type |
|---|---|---|
| `dialogue` table | `schema.py` | **Drop** (replaced) |
| `dialogue_nodes` table | `schema.py` | **Add** |
| `dialogue_options` table | `schema.py` | **Add** |
| `insert_dialogue()` | `schema.py` | **Remove** |
| `insert_dialogue_node()` | `schema.py` | **Add** |
| `insert_dialogue_option()` | `schema.py` | **Add** |
| `get_npc_dialogue()` | `schema.py` | **Remove** |
| `get_npc_topics()` | `schema.py` | **Remove** |
| `mark_dialogue_delivered()` | `schema.py` | **Remove** |
| `get_dialogue_root()` | `schema.py` | **Add** |
| `get_dialogue_node()` | `schema.py` | **Add** |
| `get_dialogue_options()` | `schema.py` | **Add** |
| `_handle_talk()` | `game.py` | **Rewrite** (enters dialogue mode) |
| `_handle_ask()` | `game.py` | **Remove** |
| `_show_available_topics()` | `game.py` | **Remove** |
| `_pick_dialogue()` | `game.py` | **Remove** |
| `_apply_dialogue_flags()` | `game.py` | **Keep** (minor refactor) |
| `_run_dialogue_mode()` | `game.py` | **Add** (new sub-loop) |
| `_render_dialogue_panel()` | `game.py` | **Add** (Rich panel rendering) |
| `_filter_dialogue_options()` | `game.py` | **Add** (flag + item filtering) |
| Greeting handler | `game.py` | **Remove** |
| `ask` verb parsing | `game.py` | **Remove** |
| Help text | `game.py` | **Update** |
| `STYLE_TOPIC` | `game.py` | **Remove** |
| `STYLE_DIALOGUE_BORDER` | `game.py` | **Add** |
| `STYLE_DIALOGUE_OPTION` | `game.py` | **Add** |
| `STYLE_DIALOGUE_NEW` | `game.py` | **Add** (for `[NEW]` tags) |
| `dialogue_entries` in JSON schema | `npcs.py` | **Replace** with `dialogue_tree` |
| LLM prompt | `npcs.py` | **Rewrite** dialogue section |
| Validation | `npcs.py` | **Rewrite** for tree structure |
| DB insertion | `npcs.py` | **Rewrite** for nodes + options |
| All `insert_dialogue()` calls | `build_test_game.py` | **Replace** with node/option calls |
| `ask_maria_*` commands | `build_test_game.py` | **Remove** |
| `world-schema.md` | `docs/` | **Update** dialogue table docs |
| `command-spec.md` | `docs/` | **Update** remove `ask` command docs |
| `gdd.md` | `docs/` | **Update** dialogue system description |
