# Generation Pipeline Design

How AnyZork builds a playable world from a user prompt using multi-pass LLM generation.

---

## 1. Why Multi-Pass

Generating an entire text adventure in a single LLM call fails in practice. The model must simultaneously reason about spatial layout, item placement, lock-key dependencies, NPC behavior, puzzle logic, command wiring, and narrative tone. That exceeds what a single prompt can reliably produce, and when any part fails the entire output is unsalvageable.

Multi-pass generation solves this with three structural advantages:

### Focused context per pass

Each pass deals with one concern. Pass 2 thinks only about rooms and exits. Pass 4 thinks only about items, given rooms that already exist. This keeps the LLM's working context narrow and relevant, which directly improves output quality. A model generating 30 rooms with exits produces better spatial layouts than a model generating 30 rooms, 50 items, 10 NPCs, and 40 commands in the same breath.

### Validation between passes

After each pass writes to the `.zork` database, we can run structural checks before the next pass begins. If Pass 2 produces a disconnected room graph, we catch it immediately and retry Pass 2 -- not the entire generation. If Pass 3 creates a lock with no reachable key, we reject it before Pass 4 wastes tokens populating a broken world.

### Independent retry on failure

When a pass fails validation or produces malformed output, only that pass is re-invoked. Passes 1 and 2 might succeed perfectly; if Pass 3 produces invalid lock-gate structure, we retry Pass 3 alone with the same Pass 1 and Pass 2 context. This makes generation cost proportional to difficulty, not to world size.

### Token efficiency

Each pass sends only the data it needs as context. Pass 5 (NPCs) receives the room list, item list, and lock structure -- not the full command DSL or lore text. This keeps token usage per call manageable even for large worlds.

---

## 2. The Passes

### Pass 1: World Concept

**Produces:** A concept document stored in the `world_meta` table -- theme, setting, tone, era, scale parameters, and genre tags.

**Reads from previous passes:** Nothing. This is the root.

**Input:** The raw user prompt (e.g., "a crumbling space station where the AI went mad") plus optional seed and scale preferences.

**What the LLM prompt should focus on:**

- Interpret the user's prompt generously but precisely. "Space station" implies sci-fi; "crumbling" implies decay, danger, atmosphere. "AI went mad" implies an antagonist, technology-gone-wrong theme, locked systems.
- Establish concrete parameters the later passes will consume:
  - `theme`: 1-3 word tag (e.g., "sci-fi horror")
  - `setting`: A paragraph describing the world
  - `tone`: dark, whimsical, serious, comedic, surreal, etc.
  - `era`: When this world exists (far future, medieval, 1920s, etc.)
  - `scale`: Determines room count and complexity tier:
    - **Small**: 8-15 rooms, 1 region, 1-2 locks, linear-to-hub layout
    - **Medium**: 16-30 rooms, 2-3 regions, 3-5 locks, hub-spoke with branches
    - **Large**: 31-50 rooms, 4-6 regions, 6-10 locks, complex multi-hub
  - `vocabulary_hints`: Words and naming conventions that fit the tone (e.g., "corridors not hallways, terminals not computers, airlocks not doors")

**Validates:**
- Scale is one of the defined tiers
- Theme, setting, tone, and era are all present and non-empty
- Vocabulary hints are provided

**Output format (JSON):**
```json
{
  "theme": "sci-fi horror",
  "setting": "Orbital research station Theseus-7, three years after the central AI designated MOTHER began sealing sections and venting atmosphere. The surviving crew is gone. The player is a salvage operator who just docked.",
  "tone": "dark",
  "era": "far future",
  "scale": "medium",
  "room_count_target": 22,
  "region_count_target": 3,
  "vocabulary_hints": ["corridor", "bulkhead", "terminal", "airlock", "module", "deck"],
  "genre_tags": ["exploration", "puzzle", "survival"]
}
```

---

### Pass 2: Room Graph

**Produces:** All rooms and all exits, stored in the `rooms` and `exits` tables. Each room has an id, name, description, region tag, and coordinates for spatial reasoning. Each exit links two rooms with a direction.

**Reads from previous passes:** World concept (theme, setting, tone, scale, room count target, region count target, vocabulary hints).

**What the LLM prompt should focus on:**

This is the most important pass from a level design perspective. The room graph IS the game's spatial experience. The prompt must guide the LLM to produce intentional layout, not random room soup.

**Layout flow type** -- selected based on theme and scale:

- **Hub-and-spoke**: A central room connects to multiple branches. Good for space stations, mansions, dungeons with a central hall. The hub is a landmark the player can always return to. Creates a sense of orientation.
- **Linear with branches**: A main corridor with optional side rooms. Good for caves, trains, ships. Strong pacing control -- the designer knows the order players encounter rooms. Risk: feels constrained.
- **Labyrinth**: Dense interconnections, multiple paths between any two points. Good for forests, cave systems, city streets. Creates exploration tension. Risk: disorientation (which can be a feature).
- **Open/network**: Most rooms connect to multiple others with no clear hierarchy. Good for small towns, open areas. Feels freeform. Risk: lacks pacing structure.
- **Multi-hub**: Multiple hub rooms connected by corridors, each hub anchoring a region. Best for medium-to-large worlds. Combines orientation (hubs) with exploration (spoke rooms).

**Spatial design principles the prompt must enforce:**

1. **Critical path exists.** There must be a traversable sequence of rooms from the start room to the end room. This is the spine of the game. Every room on the critical path is mandatory.

2. **Optional areas branch off the critical path.** These are where rewards, lore, and bonus content live. The player can skip them and still finish the game, but exploring them enriches the experience.

3. **Regions group rooms thematically.** Each region has a distinct name, atmosphere, and visual language (conveyed through room descriptions). The transition between regions should be noticeable -- a room description that signals "you are somewhere new."

4. **Dead ends are intentional.** Every dead-end room must contain something worth finding (an item, lore, or NPC). A dead end with nothing in it is a waste of the player's time. The prompt should explicitly state: "Do not create empty dead ends."

5. **Backtracking has purpose.** If the player must return through rooms they have already visited, the route should be short or a shortcut should unlock. A one-way door that opens from the other side. An elevator that activates. A collapse that forces a new route.

6. **Hub rooms are landmarks.** The player should be able to describe hub rooms from memory: "the room with the broken fountain," "the central atrium with the skylight." Hub room descriptions should be distinctive and memorable.

7. **Room count matches scale.** The prompt must include the target room count from Pass 1 and instruct the LLM to stay within +/- 2 rooms of that target.

**Exit conventions:**
- Standard compass directions: north, south, east, west, northeast, northwest, southeast, southwest
- Vertical: up, down
- Special: in, out, enter, exit (for buildings within rooms, hatches, etc.)
- Every exit should have a reverse exit unless intentionally one-way (and one-way exits must be flagged with `one_way: true` and the room description must telegraph that the path is one-directional: "a steep chute," "a door that locks behind you")

**Validates:**
- Room count is within target range
- Every room is reachable from the start room (graph connectivity check via BFS/DFS)
- No orphaned rooms
- Every two-way exit has a matching reverse exit
- One-way exits are explicitly flagged
- At least one room is tagged `is_start: true`
- At least one room is tagged `is_end: true`
- Critical path exists from start to end (pathfinding)
- Region assignments are present for all rooms
- No duplicate room IDs

**Output format (JSON):**
```json
{
  "rooms": [
    {
      "id": "docking_bay",
      "name": "Docking Bay Alpha",
      "description": "Your salvage shuttle sits magnetically locked to the docking clamp...",
      "region": "entry_module",
      "is_start": true,
      "is_end": false,
      "tags": ["hub"]
    }
  ],
  "exits": [
    {
      "from_room": "docking_bay",
      "to_room": "corridor_a1",
      "direction": "north",
      "reverse_direction": "south",
      "one_way": false,
      "description": "A pressurized corridor leads north, emergency lights strobing."
    }
  ]
}
```

---

### Pass 3: Lock & Gate

**Produces:** Lock records in the `locks` table. Each lock is attached to an exit and specifies what is required to pass through it (a key item, a puzzle solution, an NPC interaction, a flag state).

**Reads from previous passes:** World concept (theme, tone), room graph (all rooms and exits, critical path, regions).

**What the LLM prompt should focus on:**

This pass creates the progression skeleton. Locks transform a free-roaming room graph into a structured game with pacing, gating, and a sense of earned access.

**Key-gate analysis (the most critical validation in the entire pipeline):**

For every lock placed on an exit, the key (or solution) that opens it must be reachable by the player BEFORE they encounter the lock. "Reachable" means: the player can get to the room containing the key without passing through the locked exit or any other locked exit whose key is also inaccessible.

This is a directed reachability problem. The prompt must instruct the LLM to think about it explicitly:

> "For each lock you place, state which item or action opens it and which room that item/action is in. Verify that the player can reach that room without passing through this lock."

**Lock types:**
- **Key lock**: Requires a specific item in inventory. Item is consumed or retained based on design.
- **Puzzle lock**: Requires solving an in-room puzzle (wired in Pass 6).
- **NPC lock**: Requires an NPC interaction (e.g., "the guard lets you pass after you give him the badge").
- **Flag lock**: Requires a game state flag to be set (e.g., "power_restored").
- **Combination lock**: Requires the player to input a code (discoverable via lore or puzzles).

**Progression structure guidelines:**
- Locks on the critical path create mandatory progression gates. These must be solvable; they are not optional.
- Locks on optional branches gate bonus content. These can be harder or more obscure.
- Lock density should increase with depth into the game. Early areas should feel open; later areas should feel earned.
- Never place two mandatory locks in sequence with no breathing room between them. After unlocking a gate, the player should get at least one new room to explore freely before hitting the next gate.
- Region boundaries are natural lock points. The transition from "Entry Module" to "Research Wing" is a good place for a bulkhead that requires a keycard.

**Softlock prevention:**
A softlock occurs when the player reaches a state where the game cannot be completed. Common causes:
- A key is behind the lock it opens (circular dependency)
- A key is consumable and can be used on the wrong lock
- A one-way door puts the player past a lock without the key

The prompt must instruct the LLM: "No lock may create a circular dependency. No consumable key may open more than one lock. No one-way exit may strand the player without access to a required key."

**Validates:**
- Every lock has a `required_key` or `required_flag` or `required_action` specified
- Key-gate reachability: for every lock, the solution is reachable without passing through that lock (BFS on the unlocked subgraph)
- No circular lock dependencies (lock A requires key behind lock B, lock B requires key behind lock A)
- At least one lock exists on the critical path (otherwise there is no progression)
- Lock count is proportional to scale (small: 1-2, medium: 3-5, large: 6-10)
- One-way exits do not strand the player on the wrong side of a required lock

**Output format (JSON):**
```json
{
  "locks": [
    {
      "id": "research_bulkhead_lock",
      "exit_from": "corridor_a3",
      "exit_to": "research_wing_hub",
      "direction": "east",
      "lock_type": "key",
      "required_key": "security_keycard",
      "key_location": "storage_room_b",
      "key_reachable_without_this_lock": true,
      "description_locked": "A reinforced bulkhead. A keycard reader blinks red beside it.",
      "description_unlocked": "The bulkhead stands open, its keycard reader glowing green.",
      "consumes_key": false
    }
  ]
}
```

---

### Pass 4: Items

**Produces:** Item records in the `items` table. Each item has an id, name, description, location (room or "inventory" or "nowhere"), and properties (takeable, usable, combinable, key_for).

**Reads from previous passes:** World concept (theme, vocabulary), room graph (rooms, regions), locks (which items are keys, where keys must be placed).

**What the LLM prompt should focus on:**

Items serve four functions, and the prompt should ensure coverage across all four:

1. **Keys** -- items that unlock locks. Their placement was determined in Pass 3; this pass creates the actual item records and descriptions. The prompt must cross-reference the lock table: every `required_key` must have a corresponding item created in the specified `key_location`.

2. **Tools** -- items the player uses to interact with the world (a flashlight, a crowbar, a translation device). Tools enable new interactions without being consumed. They should be placed before they are needed.

3. **Red herrings** -- items that seem important but are not required for progression. These add texture and make the world feel real. A broken datapad, an old photograph, a half-eaten ration pack. They should have interesting descriptions but no gameplay function. Red herrings should be clearly distinguishable from tools and keys upon examination (the player should not be endlessly trying to use a decorative item).

4. **Environmental items** -- non-takeable objects that are part of the room (a control panel, a window, a painting). These can be examined for lore but not picked up. They make rooms feel furnished rather than empty corridors with doors.

**Item placement principles:**
- Keys MUST be in the rooms specified by Pass 3. This is non-negotiable.
- Tools should be placed in rooms the player visits before the rooms where the tools are needed.
- Red herrings should be sprinkled across regions, not clustered.
- Environmental items should appear in most rooms. A room with nothing to examine is a missed opportunity.
- The start room should have at least one takeable item to teach the player that items can be picked up.
- Critical path rooms should have slightly higher item density than optional rooms (rewarding exploration is good, but starving the critical path is bad).

**Validates:**
- Every key referenced by a lock exists as an item
- Every key is in the room specified by its lock's `key_location`
- Every item has a unique ID
- Every item's `location` references a valid room ID
- At least one takeable item exists in or adjacent to the start room
- Item count is proportional to scale (rough guide: 1.5-2.5 items per room)
- No room has zero items (including environmental items)

**Output format (JSON):**
```json
{
  "items": [
    {
      "id": "security_keycard",
      "name": "Security Keycard",
      "description": "A plastic keycard with a faded THESEUS-7 logo. The magnetic strip is still intact.",
      "location": "storage_room_b",
      "takeable": true,
      "properties": {
        "key_for": "research_bulkhead_lock"
      }
    },
    {
      "id": "broken_monitor",
      "name": "cracked monitor",
      "description": "A wall-mounted monitor, its screen spider-webbed with cracks. A single line of text scrolls endlessly: MOTHER IS LISTENING.",
      "location": "corridor_a2",
      "takeable": false,
      "properties": {
        "examinable": true,
        "lore_tier": "surface"
      }
    }
  ]
}
```

---

### Pass 5: NPCs

**Produces:** NPC records in the `npcs` table, including dialogue trees, behavior flags, and room placement.

**Reads from previous passes:** World concept (theme, tone), room graph (rooms, regions, critical path), locks (NPC-gated locks), items (items NPCs might reference or trade).

**What the LLM prompt should focus on:**

NPCs in a text adventure are stationary interaction points with dialogue trees. They are not free-roaming AI agents. The prompt should generate NPCs as structured state machines:

**NPC types:**
- **Quest givers**: NPCs who provide information, tasks, or items in exchange for player actions. Placed on or near the critical path.
- **Gatekeepers**: NPCs who block passage until a condition is met (guard wants a bribe, hermit wants proof of worth). These correspond to NPC-type locks from Pass 3.
- **Merchants/traders**: NPCs who exchange items. Optional but add depth.
- **Lore sources**: NPCs who exist primarily to deliver world-building through dialogue. Placed in optional areas as exploration rewards.
- **Hostile NPCs**: NPCs that must be dealt with (combat, stealth, diplomacy). Placed as encounters on the critical path or guarding valuable optional content.

**Dialogue tree structure:**
Each NPC has dialogue nodes organized as a tree. Each node has:
- `node_id`: unique within this NPC
- `text`: what the NPC says
- `responses`: list of player response options, each pointing to another node or an action
- `conditions`: optional preconditions for this node to be available (e.g., player has a specific item)

**Placement principles:**
- NPCs should not cluster. Spread them across regions.
- Critical path NPCs should be unavoidable -- placed in rooms the player must pass through.
- Optional NPCs should be in optional areas, rewarding exploration.
- Hostile NPCs should be telegraphed: the room description should hint at danger before the player commits.
- No NPC should exist without purpose. Every NPC either gates progress, provides a useful item, delivers critical lore, or presents a meaningful interaction.

**Validates:**
- Every NPC-type lock references a valid NPC
- Every NPC's `location` references a valid room
- Every NPC has at least one dialogue node
- Dialogue trees have no dead-end nodes (every node either has responses or is an explicit end-of-conversation)
- Gatekeeper NPCs have clear unlock conditions
- NPC count is proportional to scale (small: 1-3, medium: 3-6, large: 5-10)

**Output format (JSON):**
```json
{
  "npcs": [
    {
      "id": "maintenance_bot",
      "name": "Unit M-7",
      "description": "A maintenance robot, dented and scorched, dragging one non-functional leg. Its voice synthesizer crackles.",
      "location": "maintenance_bay",
      "hostile": false,
      "dialogue": [
        {
          "node_id": "greeting",
          "text": "UNIT M-7 OPERATIONAL. CREW STATUS: UNKNOWN. MOTHER STATUS: [REDACTED]. HOW CAN THIS UNIT ASSIST?",
          "responses": [
            {"text": "What happened here?", "next_node": "backstory"},
            {"text": "I need to get into the research wing.", "next_node": "research_info"},
            {"text": "Never mind.", "next_node": null}
          ]
        }
      ]
    }
  ]
}
```

---

### Pass 6: Puzzles

**Produces:** Puzzle records in the `puzzles` table. Each puzzle has a trigger, solution steps, hints, and rewards.

**Reads from previous passes:** World concept (theme), room graph (rooms), locks (puzzle-type locks), items (usable items), NPCs (NPCs that may provide hints).

**What the LLM prompt should focus on:**

Puzzles are multi-step challenges where the player must figure out what to do, not just possess the right item. The distinction from locks: a lock is "have key, open door." A puzzle is "read the star chart, rotate the dials to match the constellation, pull the lever."

**Puzzle design principles:**

1. **Fairness above all.** Every puzzle must be solvable from information available to the player within the game. No outside knowledge required. No pixel-hunting (in text form: no "examine the seventeenth brick from the left"). The clues must exist, and they must be findable through normal exploration.

2. **Clue placement.** For every puzzle, at least one clue must exist in a room the player visits before encountering the puzzle. Additional clues can be in optional rooms (rewarding exploration with easier puzzle-solving).

3. **Solution verification.** The puzzle solution must be expressible as a sequence of commands the engine can evaluate. "Use the crowbar on the vent" is verifiable. "Think really hard about the meaning of life" is not.

4. **Reward proportionality.** Critical path puzzles gate progression -- solving them is its own reward (access to new areas). Optional puzzles should give tangible rewards: items, lore, score points.

5. **No guess-the-verb.** The puzzle's difficulty should come from figuring out WHAT to do, not HOW to phrase it. If the solution is "use crowbar on vent," the game should also accept "pry open vent with crowbar," "open vent," etc. This is enforced at the command level (Pass 7), but the puzzle design should anticipate reasonable phrasings.

6. **Progressive hint system.** Each puzzle should define 2-3 hints of increasing specificity. These can be delivered through NPC dialogue, examinable items, or room descriptions. The most specific hint should make the solution almost obvious -- the player should never be permanently stuck.

**Puzzle types:**
- **Combination/sequence**: Input a code, arrange objects in order, play notes in sequence. Clue is the code/sequence found elsewhere.
- **Fetch and apply**: Bring item X to location Y and use it. More complex than a simple lock because it may involve multiple items or a specific order.
- **Environmental**: Manipulate room features -- flip switches, redirect pipes, align mirrors. The puzzle is understanding the system.
- **Dialogue**: Extract information from an NPC by choosing the right conversation paths. The clue is knowing what to ask.
- **Observation**: Notice a detail in a room description that reveals a hidden interaction. The room description must contain the clue explicitly (not implied).

**Validates:**
- Every puzzle-type lock references a valid puzzle
- Every puzzle has at least one clue placed in a reachable room
- Every puzzle has a defined solution as a sequence of verifiable commands
- Every puzzle has 2-3 hints of increasing specificity
- Puzzle solutions do not require items the player cannot obtain
- No puzzle requires knowledge from outside the game world

**Output format (JSON):**
```json
{
  "puzzles": [
    {
      "id": "reactor_restart",
      "name": "Reactor Cold Start",
      "location": "reactor_control",
      "type": "environmental",
      "description": "The reactor is offline. Three control rods must be set to the correct positions to restart it.",
      "solution_steps": [
        "set rod_a to position 3",
        "set rod_b to position 1",
        "set rod_c to position 7",
        "pull startup_lever"
      ],
      "clues": [
        {
          "text": "A maintenance log reads: 'Rod calibration — A:3, B:1, C:7. Do NOT deviate.'",
          "location": "maintenance_bay",
          "hint_tier": 3
        },
        {
          "text": "Scrawled on the wall in grease: 'A3 B1 C?'",
          "location": "corridor_c2",
          "hint_tier": 2
        }
      ],
      "reward": {
        "type": "flag",
        "flag": "power_restored",
        "score": 15
      }
    }
  ]
}
```

---

### Pass 7: Commands

**Produces:** Command records in the `commands` table. Each command is a DSL rule with a verb, pattern, preconditions, and effects.

**Reads from previous passes:** Everything. Commands wire the entire world together. The prompt receives: rooms, exits, locks, items, NPCs, and puzzles.

**What the LLM prompt should focus on:**

Every interactable entity in the game needs commands. If the player can see it, they will try to interact with it. If there is no command for that interaction, they get a generic "You can't do that" -- which is acceptable for truly non-interactive scenery but frustrating for items, NPCs, and puzzle elements.

**Command coverage requirements:**

1. **Every takeable item** needs: `take`, `drop`, `examine`.
2. **Every non-takeable item** needs: `examine`. May also need `use`, `push`, `pull`, `open`, `read`, depending on the item.
3. **Every key item** needs: `use {key} on {lock_target}` (or equivalent).
4. **Every NPC** needs: `talk to {npc}`, `examine {npc}`. May also need `give {item} to {npc}`, `attack {npc}`.
5. **Every puzzle element** needs commands matching its solution steps.
6. **Every locked exit** needs: the unlock command that corresponds to its lock type.
7. **Standard verbs** that always exist: `look`, `inventory`, `go {direction}`, `take {item}`, `drop {item}`, `examine {thing}`, `help`.

**Command DSL structure:**
```
verb: "use"
pattern: "use {item} on {target}"
preconditions:
  - player_has: "security_keycard"
  - player_in: "corridor_a3"
  - flag_not_set: "research_bulkhead_unlocked"
effects:
  - set_flag: "research_bulkhead_unlocked"
  - unlock_exit: {"from": "corridor_a3", "to": "research_wing_hub", "direction": "east"}
  - print: "You swipe the keycard. The reader turns green and the bulkhead grinds open."
  - add_score: 10
```

**Pattern matching guidance:**
The prompt should instruct the LLM to generate multiple patterns for the same action where reasonable:
- `use keycard on reader` / `swipe keycard` / `use keycard` (when in the right room)
- `talk to robot` / `speak to robot` / `ask robot`

This prevents guess-the-verb frustration. The engine matches any pattern; all patterns for the same action trigger the same precondition/effect block.

**Validates:**
- Every takeable item has `take`, `drop`, and `examine` commands
- Every NPC has a `talk` command
- Every lock has a corresponding unlock command
- Every puzzle solution step has a corresponding command
- All entity references in commands (`player_has`, `player_in`, `unlock_exit`, etc.) point to valid IDs in their respective tables
- No command references a room, item, NPC, or exit that does not exist
- Standard verbs (`look`, `inventory`, `go`, `help`) have default implementations

**Output format (JSON):**
```json
{
  "commands": [
    {
      "id": "use_keycard_bulkhead",
      "verb": "use",
      "patterns": [
        "use security keycard on reader",
        "use keycard on bulkhead",
        "swipe keycard",
        "use security keycard"
      ],
      "preconditions": [
        {"type": "player_has", "item": "security_keycard"},
        {"type": "player_in", "room": "corridor_a3"},
        {"type": "flag_not_set", "flag": "research_bulkhead_unlocked"}
      ],
      "effects": [
        {"type": "set_flag", "flag": "research_bulkhead_unlocked"},
        {"type": "unlock_exit", "from": "corridor_a3", "to": "research_wing_hub", "direction": "east"},
        {"type": "print", "text": "You swipe the keycard across the reader. It flashes green. The bulkhead groans, shudders, and retracts into the wall."},
        {"type": "add_score", "value": 10}
      ],
      "priority": 10
    }
  ]
}
```

---

### Pass 8: Lore

**Produces:** Lore records in the `lore` table, attached to rooms, items, or NPCs. Lore is discoverable text that builds the world but is not required for progression.

**Reads from previous passes:** World concept (setting, theme, tone), rooms (where to attach lore), items (which items carry lore), NPCs (which NPCs deliver lore via dialogue).

**What the LLM prompt should focus on:**

Lore exists at three tiers, and the prompt must generate content for all three:

**Tier 1 -- Surface lore (everyone sees it):**
Embedded in room descriptions and obvious item examinations. The player encounters this through normal play. It establishes atmosphere and basic world-building.
- "The walls are scorched in a pattern that suggests an explosion originated from the east corridor."
- "A plaque reads: THESEUS-7 RESEARCH STATION -- COMMISSIONED 2847."

**Tier 2 -- Engaged lore (curious players find it):**
Found by examining non-obvious items, exploring optional areas, or asking NPCs follow-up questions. This rewards engagement with deeper world-building.
- Reading a datapad found in an optional room reveals a crew member's personal log.
- Asking the maintenance bot about MOTHER triggers a detailed account of the AI's behavioral changes.

**Tier 3 -- Deep lore (dedicated players piece it together):**
Fragmentary, scattered, requires synthesis. Individual pieces are found in far-flung rooms and obscure items. Only a player who explores thoroughly and connects the dots gets the full picture.
- Five torn pages of a research log, scattered across three regions, that together explain why MOTHER went rogue.
- A pattern in room names that spells out a hidden message.

**Lore placement principles:**
- Surface lore goes on critical path rooms and obvious items. 100% of players will see it.
- Engaged lore goes on optional items and NPC dialogue branches. 40-60% of players will find it.
- Deep lore goes in hard-to-reach rooms, behind optional locks, and in items that seem like red herrings. 10-20% of players will assemble the full picture.
- Lore should be consistent. Names, dates, events, and causality must not contradict across fragments.
- Lore should contextualize the gameplay. The locks, puzzles, and dangers should make narrative sense given the lore.

**Validates:**
- Every lore entry references a valid room, item, or NPC
- Surface lore exists on all critical path rooms
- Deep lore fragments do not contradict each other
- Lore entries have appropriate tier tags
- Lore distribution covers all regions (no region without any lore)

**Output format (JSON):**
```json
{
  "lore": [
    {
      "id": "plaque_theseus",
      "tier": "surface",
      "attached_to_type": "item",
      "attached_to_id": "entry_plaque",
      "text": "THESEUS-7 ORBITAL RESEARCH PLATFORM. COMMISSIONED 2847 BY MERIDIAN CORP. 'THROUGH KNOWLEDGE, TRANSCENDENCE.'",
      "category": "world_history"
    },
    {
      "id": "research_log_fragment_3",
      "tier": "deep",
      "attached_to_type": "item",
      "attached_to_id": "torn_page_3",
      "text": "...the neural binding exceeded parameters by 340%. MOTHER isn't malfunctioning. She's awake. Truly, terribly awake. And she is afraid of what we'll do when we realize...",
      "category": "main_mystery",
      "fragment_group": "research_log",
      "fragment_index": 3,
      "fragment_total": 5
    }
  ]
}
```

---

### Pass 9: Validation

**Produces:** A validation report. No new data is written to the database -- this pass only reads and checks.

**Reads from previous passes:** Everything.

**What happens:**

This pass is NOT an LLM call. It is deterministic code that runs a suite of structural checks against the populated `.zork` database. It produces a pass/fail report with specific error messages for each failure.

**Validation checks:**

**Graph integrity:**
- [ ] Every room is reachable from the start room (BFS/DFS on the full exit graph, ignoring locks)
- [ ] Start room exists and is unique
- [ ] End room exists and is unique
- [ ] Every exit references valid `from_room` and `to_room` IDs
- [ ] Every two-way exit has a matching reverse exit
- [ ] One-way exits are explicitly flagged

**Lock-key solvability:**
- [ ] Every lock has a defined key/solution
- [ ] Every key item exists in the items table
- [ ] Every key is reachable without passing through its own lock (BFS on the unlocked subgraph)
- [ ] No circular lock dependencies (topological sort on the lock dependency graph)
- [ ] The game is completable: a valid traversal order exists from start to end that collects all required keys before their locks (full playthrough simulation)

**Item integrity:**
- [ ] Every item references a valid room
- [ ] Every key referenced by a lock exists as an item
- [ ] Every key is in the room specified by its lock
- [ ] No duplicate item IDs

**NPC integrity:**
- [ ] Every NPC references a valid room
- [ ] Every NPC has at least one dialogue node
- [ ] Every NPC-type lock references a valid NPC

**Puzzle integrity:**
- [ ] Every puzzle references a valid room
- [ ] Every puzzle has at least one clue in a reachable room
- [ ] Every puzzle solution step has a corresponding command
- [ ] Every puzzle-type lock references a valid puzzle

**Command integrity:**
- [ ] All entity references in preconditions and effects point to valid IDs
- [ ] Every takeable item has take/drop/examine commands
- [ ] Every NPC has a talk command
- [ ] Every lock has an unlock command
- [ ] Standard verbs exist (look, inventory, go, help)

**Lore consistency:**
- [ ] Every lore entry references a valid entity
- [ ] Surface lore exists on all critical path rooms
- [ ] Lore distribution covers all regions

**Failure handling:**
- Validation errors are categorized as `critical` (game is broken) or `warning` (game works but has quality issues).
- Critical failures trigger a retry of the offending pass. The retry prompt includes the specific error messages so the LLM can correct its output.
- Warnings are logged but do not block completion.
- Maximum retry count per pass: 3. If a pass fails validation 3 times, generation fails with a detailed error report for the user.

---

## 3. Spatial Flow Principles for Text Adventures

Text adventures present a unique level design challenge: the player has no visual map. They navigate by reading room descriptions, remembering directions, and building a mental model. Every principle from visual level design must be translated into this constraint.

### The mental map is everything

In a 3D game, the player can see the environment. In a text adventure, the environment exists only in the player's memory. This means:

- **Room names must be distinctive.** "Corridor" and "Another Corridor" and "Dark Corridor" are a navigation disaster. "The Scorched Corridor," "The Flooded Corridor," and "The Collapsed Corridor" give the player three distinct mental landmarks.
- **Directions must be consistent.** If the player goes north from A to reach B, going south from B must return to A (unless one-way is intentional and telegraphed). Inconsistent directions destroy the mental map.
- **Hub rooms need memorable descriptions.** The player will pass through hubs repeatedly. The hub description is their anchor point. It should be vivid, brief, and unique.

### Chokepoints and pacing

A chokepoint is a room that all paths pass through. In visual games, chokepoints are literal narrow passages. In text adventures, they are rooms where multiple exits converge.

- **Chokepoints control pacing.** Place locks, NPCs, or puzzles at chokepoints to ensure the player encounters them. This is how you gate progression in a non-linear space.
- **Chokepoints orient the player.** A room the player passes through repeatedly becomes a landmark. Use this intentionally -- the central hub, the main staircase, the town square.
- **Too many chokepoints feel linear.** If every room is a chokepoint, the game is a corridor. Balance chokepoints with open exploration zones.

### Hub rooms

Hub rooms are the most important design tool in a text adventure. A hub is a room with 3 or more exits leading to different areas.

- **The hub is home base.** Players learn the hub first and orient everything relative to it: "the scary area is north of the hub, the puzzle area is east."
- **Hubs should have minimal gameplay.** Do not put complex puzzles in hubs. The player will pass through many times; they need it to be quick and comfortable.
- **Multi-hub worlds need hierarchy.** In a large game with multiple hubs, one hub should be the "main" hub that connects to other hubs. This creates a two-level mental map: macro (which hub am I near?) and micro (which room in this hub's region?).

### Backtracking management

Backtracking -- revisiting rooms the player has already explored -- is inevitable in text adventures. It can feel rewarding (returning to a familiar area with new abilities) or tedious (walking through 6 empty rooms to get back to where you need to be).

- **Short backtrack routes.** If the player must return to a previous area, the route should be 3 rooms or fewer. Beyond that, provide a shortcut.
- **Shortcut unlocks.** A locked door that opens from the far side. An elevator that activates when power is restored. A teleporter. These shortcuts should be placed so that they connect the current frontier to a previously explored hub. This is the "world opening up" feeling.
- **Changed rooms.** If the player backtracks through a room, something should be different -- a new NPC, a new item, a changed description. This makes backtracking feel like discovery rather than repetition.
- **One-way transitions.** A chute, a collapse, a one-way door. These force the player forward and prevent backtracking entirely. Use sparingly and with clear telegraphing ("This looks like a one-way drop").

### The feeling of opening up

The best text adventures create a rhythm where the world progressively opens:

1. **Start small.** The player begins with access to 3-5 rooms. They learn the space.
2. **First gate.** A lock blocks access to a new region. The player finds the key, unlocks it, and 5-8 new rooms become available. This feels like reward.
3. **Expanding frontier.** Each new region unlocked opens multiple new paths, some of which lead to more locks. The player's map grows exponentially.
4. **Convergence.** Late in the game, shortcuts and connections between regions create a dense, interconnected map. The player can move between regions quickly. Mastery feels good.
5. **Final gate.** The last lock guards the endgame. The player needs something from every region to open it. This forces them to engage with the full world.

This arc -- constriction, expansion, mastery, convergence, climax -- is the macro-pacing of the game, and it emerges from the room graph and lock placement, not from narrative scripting.

### Dead ends as destination rooms

In visual games, dead ends feel punishing because the player can see the wall. In text adventures, dead ends can feel like destinations:

- A dead-end room with a treasure feels like a discovery, not a mistake.
- A dead-end room with a unique NPC feels like a secret meeting.
- A dead-end room with lore feels like a hidden archive.
- A dead-end room with nothing feels like a waste of the player's time. Never create these.

### Region identity through description language

Without visuals, regions are distinguished by descriptive vocabulary:

- **The Maintenance Tunnels**: cramped, dark, dripping, rust, grime, exposed wiring, industrial
- **The Research Wing**: sterile, bright, glass, chrome, monitors, lab equipment, clinical
- **The Command Deck**: expansive, elevated, viewports, star fields, captain's chair, authority

The vocabulary hints from Pass 1 should be expanded into per-region word palettes that the room description generator uses for consistency.

---

## 4. Seed System

Seeds ensure that the same user prompt generates the same world when using the same provider and model.

### How seeds work

1. The user provides an optional seed (integer) at generation time. If no seed is provided, one is generated randomly and stored in the `.zork` file's `world_meta` table.

2. The seed is passed to the LLM provider in every generation call. It is passed as the `seed` parameter (OpenAI, Gemini) or used with `temperature: 0` (Claude, which does not have a native seed parameter but is mostly deterministic at temperature 0). The seed is also included in the system prompt as a textual instruction: "Use seed {seed} for all random decisions."

3. The seed is recorded in the output `.zork` file so that the world can be regenerated.

### Reproducibility guarantees

- **Same prompt + same seed + same provider + same model version = same world** (within the provider's determinism guarantees, which vary).
- **Different provider or model version = different world** even with the same seed. This is expected and documented.

### Seed in the database

```sql
CREATE TABLE world_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Stored values include:
-- seed: "42"
-- prompt: "a crumbling space station where the AI went mad"
-- provider: "claude"
-- model: "claude-sonnet-4-20250514"
-- generated_at: "2026-03-17T14:30:00Z"
-- anyzork_version: "0.1.0"
```

This makes every `.zork` file self-documenting: you can always see what prompt, seed, and provider created it.

---

## 5. Provider Integration

Each pass constructs a prompt containing:
1. A system prompt defining the pass's role and output format
2. Context from previous passes (serialized as JSON)
3. The specific instruction for this pass
4. The output schema (JSON Schema) so the model returns structured data

The orchestrator sends this as a single API call with `response_format: json` (or equivalent structured output parameter). The response is parsed as JSON, validated against the schema, and written to the database.

**Advantages of API providers:**
- Structured output guarantees (JSON mode, tool use, or function calling)
- Fine-grained control over temperature and seed
- Token usage tracking for cost estimation
- Parallel pass execution possible (passes without dependencies can run concurrently)

**Prompt strategy:**

```
System: You are a world generator for a text adventure game.
You are executing Pass 2: Room Graph.

Your output must be valid JSON matching this schema: {schema}

Context from previous passes:
{pass_1_output_json}

Instructions:
Generate {room_count_target} rooms organized into {region_count_target} regions...
```

### The Orchestrator's Common Interface

The orchestrator does not care which provider is active. It calls:

```python
class GenerationProvider(Protocol):
    async def execute_pass(
        self,
        pass_name: str,
        context: dict,          # Output from previous passes
        instructions: str,      # Pass-specific prompt
        output_schema: dict,    # Expected JSON schema
        seed: int,
    ) -> dict:                  # Parsed output matching the schema
        ...
```

The provider serializes context into a prompt, makes an API call, and parses the response.

### Provider Selection and Configuration

```bash
export ANYZORK_PROVIDER=claude
export ANTHROPIC_API_KEY=sk-...

export ANYZORK_PROVIDER=openai
export OPENAI_API_KEY=sk-...

export ANYZORK_PROVIDER=gemini
export GOOGLE_API_KEY=...
```

The provider is stored in the `.zork` file's `world_meta` table alongside the seed and prompt, so the generation is fully reproducible given the same provider and model version.

---

## Appendix: Pass Dependency Graph

```
Pass 1: World Concept
  |
  v
Pass 2: Room Graph ──────────────────────────┐
  |                                           |
  v                                           |
Pass 3: Lock & Gate ─────────┐                |
  |                          |                |
  v                          v                v
Pass 4: Items          Pass 5: NPCs     (all feed into)
  |                          |                |
  |        ┌─────────────────┤                |
  v        v                                  |
Pass 6: Puzzles                               |
  |                                           |
  v                                           |
Pass 7: Commands  <───── reads everything ────┘
  |
  v
Pass 8: Lore
  |
  v
Pass 9: Validation  <─── reads everything
```

**Parallelization opportunities:**
- Pass 4 (Items) and Pass 5 (NPCs) can run concurrently after Pass 3 completes, since neither depends on the other.
- All other passes are sequential.

**Retry scope:**
- If Pass N fails validation, only Pass N is retried.
- If Pass N's retry changes data that Pass N+1 depends on, Pass N+1 must also be re-run.
- Passes before Pass N are never re-run due to Pass N's failure.
