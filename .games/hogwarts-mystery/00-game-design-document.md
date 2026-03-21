# Harry Potter and the Founders' Convergence

## Game Design Document

**Version**: 1.0
**Status**: Draft
**Engine**: AnyZork (ZorkScript DSL)
**Target max_score**: 500
**Realism**: medium

---

## Changelog

| Version | Date       | Changes                          |
|---------|------------|----------------------------------|
| 1.0     | 2026-03-21 | Initial GDD — full design pass   |

---

## Table of Contents

1. [Game Overview](#1-game-overview)
2. [Core Gameplay Loop](#2-core-gameplay-loop)
3. [Game Regions and Room Map](#3-game-regions-and-room-map)
4. [Puzzle Design](#4-puzzle-design)
5. [NPC Design](#5-npc-design)
6. [Item Design](#6-item-design)
7. [Multiple Endings](#7-multiple-endings)
8. [Scoring System](#8-scoring-system)
9. [Quest Structure](#9-quest-structure)
10. [World Aliveness — Triggers and Events](#10-world-aliveness--triggers-and-events)
11. [Interaction Matrix](#11-interaction-matrix)
12. [Win and Lose Conditions](#12-win-and-lose-conditions)
13. [Onboarding Flow](#13-onboarding-flow)
14. [Flag Registry](#14-flag-registry)
15. [Balance Notes and Open Questions](#15-balance-notes-and-open-questions)

---

## 1. Game Overview

### Concept

The player controls Harry Potter, returning to Hogwarts to find the castle destabilizing. Ancient protective wards are failing because the Convergence Stone — an artifact forged by the four Founders to anchor Hogwarts' defenses — has been corrupted by a curse laid centuries ago by Malachar the Undying. To re-seal the Stone, Harry must complete four hidden trial chambers, each testing a different Founder's core virtue: courage, wisdom, loyalty, and cunning. Draco Malfoy is racing to reach the Stone first for his own reasons. The choices Harry makes throughout the trials determine how the story ends.

### Target Experience

The player should feel like they are **inside Hogwarts** — a place that is simultaneously familiar and uncanny. The castle they know is shifting, revealing ancient layers beneath its surface. The game rewards curiosity, careful reading, and lateral thinking. Combat is minimal. The primary verbs are explore, examine, talk, and solve. The emotional arc moves from wonder (exploring the castle) through tension (the trials) to resolution (confronting the corruption and choosing an ending).

### Design Pillars

These are the five non-negotiable player experiences. Every design decision is measured against them.

1. **The Castle Is Alive** — Hogwarts is not a static backdrop. Corridors shift, rooms appear and vanish, portraits comment on events, ghosts carry secrets. The world changes in response to player progress. Triggers and atmospheric text make the castle feel like a character, not a container.

2. **Exploration Rewards Curiosity** — Players who examine everything, talk to everyone, and revisit areas after story beats are rewarded with clues, side quests, lore, shortcuts, and score. The critical path is completable without exhaustive exploration, but the best endings and highest scores require it.

3. **Every Choice Has Weight** — The game tracks moral and strategic choices through flags. Helping Draco vs. competing with him, sacrificing resources for others vs. hoarding them, choosing mercy vs. ruthlessness in the Slytherin Trial — these accumulate toward distinct endings. The player should feel the consequences, not just observe them.

4. **Magic Feels Magical** — Spells, potions, and enchanted objects should surprise the player. Using the right spell in the right context should produce a satisfying, world-consistent result. The interaction matrix and DSL commands should cover enough magical interactions that the player rarely hits a flat "nothing happens" wall.

5. **Fair Challenge, No Pixel Hunts** — Every puzzle is solvable with information available in the game world. Clues exist in examine descriptions, NPC dialogue, and environmental details. Hints escalate progressively. The player never needs Harry Potter lore knowledge from outside the game — everything required is self-contained.

---

## 2. Core Gameplay Loop

### Moment-to-Moment (0-30 seconds)

- **Action**: The player moves between rooms, examines objects and room features, talks to NPCs, picks up items, and attempts to use items on targets.
- **Feedback**: Rich textual descriptions. Examine descriptions embed clues. NPCs respond with personality. Failed actions give specific, informative messages ("The door resists your push — ancient runes glow along its frame, as if waiting for something.").
- **Reward**: New information (a clue, a lore fragment, a hint), a new item, a score increment, or a world-state change (a door unlocking, a new NPC appearing, a room description changing).

### Session Loop (5-30 minutes)

- **Goal**: Complete one Founder's Trial. Each trial is a self-contained region of 5-7 rooms with 3-4 interconnected puzzles and a climactic choice.
- **Tension**: Each trial tests a specific virtue. The puzzles require items and knowledge gathered from the Hogwarts Commons and Grounds. The player must have explored thoroughly before entering a trial, or they will lack the tools to complete it.
- **Resolution**: Completing a trial yields a Founder's Token (artifact), unlocks the next trial, changes the state of Hogwarts (new areas accessible, NPCs react differently), and awards a significant score block.

### Long-Term Loop (1-3 hours total play)

- **Progression**: Commons/Grounds exploration (Act 1) -> Four Trials in any order (Act 2) -> The Depths and Convergence Chamber (Act 3). Each completed trial makes the castle more unstable (new atmospheric triggers) but also more navigable (shortcuts open).
- **Retention Hook**: Multiple endings based on accumulated flags. Side quests that reveal Malachar's backstory and the Founders' secrets. Optional puzzles that unlock the best ending. Score completionism — 500 points requires finding everything.
- **Completion**: The game ends when the player reaches the Convergence Chamber with the required tokens and makes a final choice. The ending text varies based on flags. The score breakdown shows what was missed.

---

## 3. Game Regions and Room Map

### Region Overview

| Region               | Room Count | Purpose                                                |
|----------------------|------------|--------------------------------------------------------|
| Hogwarts Commons     | 12         | Hub area, NPC interactions, clue gathering, early items |
| Hogwarts Grounds     | 6          | Outdoor exploration, side quests, trial prerequisites   |
| Gryffindor Trial     | 6          | Courage-themed challenge chamber                        |
| Ravenclaw Trial      | 6          | Wisdom-themed challenge chamber                         |
| Hufflepuff Trial     | 6          | Loyalty-themed challenge chamber                        |
| Slytherin Trial      | 6          | Cunning-themed challenge chamber                        |
| The Depths           | 4          | Ancient passages, final preparation                     |
| Convergence Chamber  | 2          | Final confrontation and ending                          |
| **Total**            | **48**     |                                                         |

### Region 1: Hogwarts Commons (12 rooms)

The hub of the game. The player starts here and returns between trials. NPCs populate these rooms and their dialogue evolves as the story progresses.

| Room ID               | Name                    | Connections                                             | Notes |
|------------------------|-------------------------|---------------------------------------------------------|-------|
| `great_hall`           | The Great Hall          | north -> entrance_hall, east -> kitchen_corridor        | Start room. Dumbledore delivers the premise. Enchanted ceiling reflects castle instability. |
| `entrance_hall`        | Entrance Hall           | south -> great_hall, north -> grand_staircase, east -> corridor_east, west -> corridor_west | Central hub. Marble staircase. Portraits whisper warnings. |
| `grand_staircase`      | The Grand Staircase     | south -> entrance_hall, up -> seventh_floor_corridor    | Moving staircases. First-visit text establishes the shifting. |
| `corridor_east`        | East Corridor           | west -> entrance_hall, north -> library, east -> hospital_wing | Suits of armor, some displaced by the magical disturbances. |
| `corridor_west`        | West Corridor           | east -> entrance_hall, north -> trophy_room, west -> dungeon_stairs | Drafty. Torches flicker unnaturally. |
| `library`              | The Library             | south -> corridor_east                                  | Hermione's domain. Restricted Section access requires a flag. Key lore items. |
| `restricted_section`   | The Restricted Section  | south -> library (exit hidden until flag set)           | Dark room. Contains critical lore about Malachar and the Convergence Stone. |
| `trophy_room`          | Trophy Room             | south -> corridor_west                                  | Historical artifacts. Clues to trial locations. A trophy case with a locked compartment. |
| `hospital_wing`        | Hospital Wing           | west -> corridor_east                                   | Madam Pomfrey-adjacent. Healing potions available. |
| `dungeon_stairs`       | Dungeon Stairway        | east -> corridor_west, down -> potions_classroom        | Cold, descending stone steps. |
| `potions_classroom`    | Potions Classroom       | up -> dungeon_stairs                                    | Snape's domain. Potion ingredients and recipes. |
| `kitchen_corridor`     | Kitchen Corridor        | west -> great_hall, east -> kitchens                     | Painting of a fruit bowl (tickle the pear). |
| `kitchens`             | The Kitchens            | west -> kitchen_corridor                                | Dobby is here. Food items, a side quest. |
| `dumbledore_office`    | Headmaster's Office     | (accessible via gargoyle from grand_staircase, locked)  | Dumbledore gives the main quest briefing and key items. Requires password. |

> **Note**: `dumbledore_office` is accessed via a locked exit from `grand_staircase` (combination lock — password). The password is discoverable from McGonagall.

**Total**: 14 rooms (slightly over target; `restricted_section` and `dumbledore_office` are locked-off sub-areas that justify the count).

### Region 2: Hogwarts Grounds (6 rooms)

Outdoor areas. Lighter tone, side quest content, and items needed for the trials.

| Room ID               | Name                    | Connections                                             | Notes |
|------------------------|-------------------------|---------------------------------------------------------|-------|
| `courtyard`            | The Courtyard           | east -> entrance_hall, south -> greenhouse, west -> clock_tower_base | Open air. The Whomping Willow is visible in the distance. Stone benches, a broken sundial. |
| `greenhouse`           | Greenhouse Three        | north -> courtyard                                      | Magical plants. Neville is here. Herbology ingredients for potions. |
| `clock_tower_base`     | Clock Tower Base        | east -> courtyard, north -> hagrid_hut                  | Ancient clock. The mechanism is jammed. Optional puzzle. |
| `hagrid_hut`           | Hagrid's Hut            | south -> clock_tower_base, east -> forest_edge          | Hagrid offers backstory and a key item. Fang is here but serves no mechanical purpose. |
| `forest_edge`          | Edge of the Forbidden Forest | west -> hagrid_hut, north -> lake_shore             | Ominous. Centaur hoofprints. Entry to forest is blocked (NPC lock — Hagrid warns you away unless flagged). |
| `lake_shore`           | The Black Lake Shore    | south -> forest_edge                                    | View of the castle from outside. A small boat. An item half-buried in the mud. |

### Region 3: The Gryffindor Trial (6 rooms)

**Theme**: Courage — facing fear, protecting others, acting despite danger.
**Entry**: Hidden exit from `trophy_room` (revealed by solving the Trophy Room puzzle).
**Atmosphere**: A crumbling tower interior buffeted by magical wind. Heights, exposed edges, illusory threats. Red and gold motifs.

| Room ID                  | Name                          | Connections                                    | Notes |
|--------------------------|-------------------------------|------------------------------------------------|-------|
| `gryffindor_antechamber` | Gryffindor Antechamber        | south -> trophy_room, north -> lion_corridor   | Entry room. A stone lion guards the path. Inscription about courage. |
| `lion_corridor`          | The Lion's Corridor           | south -> gryffindor_antechamber, north -> bridge_of_flames, east -> fear_chamber | Narrow hall with animated tapestries depicting acts of bravery. |
| `fear_chamber`           | The Chamber of Fears          | west -> lion_corridor                          | Boggart puzzle. Player must confront an illusory threat. Dark room until light source activated. |
| `bridge_of_flames`       | The Bridge of Flames          | south -> lion_corridor, north -> guardian_hall  | A stone bridge over a chasm, wreathed in magical fire. Crossing requires the correct action. |
| `guardian_hall`           | The Guardian's Hall           | south -> bridge_of_flames, north -> gryffindor_vault | Ron is trapped here. Player must choose to help Ron (costs a resource) or press on alone. Moral choice. |
| `gryffindor_vault`       | Gryffindor's Vault            | south -> guardian_hall                         | The Sword of Gryffindor replica. Gryffindor's Token is here. Completing this room solves the trial. |

### Region 4: The Ravenclaw Trial (6 rooms)

**Theme**: Wisdom — logic, riddles, knowledge, patience.
**Entry**: Hidden exit from `library` (revealed after acquiring the Ravenclaw Riddle from the Grey Lady).
**Atmosphere**: An impossible space — rooms that fold in on themselves, staircases that lead sideways, bookshelves that extend infinitely. Blue and bronze motifs.

| Room ID                   | Name                           | Connections                                    | Notes |
|---------------------------|--------------------------------|------------------------------------------------|-------|
| `ravenclaw_antechamber`   | Ravenclaw Antechamber          | south -> library, north -> riddle_hall         | Entry. An eagle door-knocker poses a riddle to proceed. |
| `riddle_hall`             | The Hall of Riddles            | south -> ravenclaw_antechamber, east -> mirror_maze, north -> logic_chamber | Three pedestals, three riddles. Answers found in lore items from the library. |
| `mirror_maze`             | The Mirror Maze                | west -> riddle_hall                            | Mirrors reflect not the player but scenes from Hogwarts history. One mirror shows the answer to the Logic Chamber puzzle. |
| `logic_chamber`           | The Logic Chamber              | south -> riddle_hall, north -> celestial_room  | Snape's potions puzzle homage — seven bottles, clues in verse. Choose the correct potion. |
| `celestial_room`          | The Celestial Room             | south -> logic_chamber, north -> ravenclaw_vault | A room of floating star charts. Hermione is here, having found a separate path. Knowledge-sharing puzzle. |
| `ravenclaw_vault`         | Ravenclaw's Vault              | south -> celestial_room                        | Rowena Ravenclaw's Lost Diadem replica. Ravenclaw's Token is here. |

### Region 5: The Hufflepuff Trial (6 rooms)

**Theme**: Loyalty — sacrifice, helping others, patience, humility.
**Entry**: Hidden exit from `kitchens` (revealed by Dobby after completing his side quest).
**Atmosphere**: Warm underground passages, root-woven walls, the smell of earth and honey. Yellow and black motifs. Feels safe but tests resolve.

| Room ID                    | Name                            | Connections                                     | Notes |
|----------------------------|---------------------------------|-------------------------------------------------|-------|
| `hufflepuff_antechamber`   | Hufflepuff Antechamber          | north -> kitchens, south -> loyalty_passage     | Entry. A badger carved in stone. Inscription: "Those who are patient shall find the way." |
| `loyalty_passage`          | The Loyalty Passage             | north -> hufflepuff_antechamber, south -> crossroads_of_need | A long tunnel. Items found here must be given away later — keeping them blocks progress. |
| `crossroads_of_need`       | The Crossroads of Need          | north -> loyalty_passage, east -> wounded_stranger, west -> garden_of_patience | A junction. Both paths must be completed. An NPC (a ghostly student) asks for help. |
| `wounded_stranger`         | The Wounded Stranger's Chamber  | west -> crossroads_of_need                      | A spectral figure is injured. Player must sacrifice a healing potion (consumable). Tests generosity. |
| `garden_of_patience`       | The Garden of Patience          | east -> crossroads_of_need, south -> hufflepuff_vault | A magical garden where nothing grows quickly. A puzzle that requires waiting (performing other actions first). Cannot be brute-forced. |
| `hufflepuff_vault`         | Hufflepuff's Vault              | north -> garden_of_patience                     | Helga Hufflepuff's Cup replica. Hufflepuff's Token is here. Only accessible after both branches complete. |

### Region 6: The Slytherin Trial (6 rooms)

**Theme**: Cunning — deception, resourcefulness, ambition, moral ambiguity.
**Entry**: Hidden exit from `potions_classroom` (revealed by using a specific potion on the dungeon wall).
**Atmosphere**: Waterlogged stone passages beneath the lake. Green torchlight. Serpent carvings. Whispers in Parseltongue. Draco Malfoy is encountered here.

| Room ID                    | Name                            | Connections                                      | Notes |
|----------------------------|---------------------------------|--------------------------------------------------|-------|
| `slytherin_antechamber`    | Slytherin Antechamber           | north -> potions_classroom, south -> serpent_hall | Entry. A serpent door that opens only to those who demonstrate cunning (use correct item). |
| `serpent_hall`              | The Serpent's Hall              | north -> slytherin_antechamber, south -> deception_room, east -> ambition_stair | Walls lined with mirrors that show distorted reflections. Draco is here — confrontation or alliance. |
| `deception_room`           | The Room of Deception           | north -> serpent_hall                             | Nothing is as it seems. Items look like other items. Player must identify the real from the fake. |
| `ambition_stair`           | The Stair of Ambition           | west -> serpent_hall, south -> bargain_chamber    | A staircase that only ascends when the player sacrifices something from inventory. Tests what the player is willing to give up. |
| `bargain_chamber`          | The Bargain Chamber             | north -> ambition_stair, south -> slytherin_vault | An enchanted contract. The player must make a deal — what they agree to affects the ending. Draco may be convinced to cooperate here. |
| `slytherin_vault`          | Slytherin's Vault               | north -> bargain_chamber                         | Salazar Slytherin's Locket replica. Slytherin's Token is here. |

### Region 7: The Depths (4 rooms)

**Entry**: Unlocked from `dungeon_stairs` after all four trials are complete (flag-locked exit).
**Atmosphere**: Ancient, pre-Hogwarts stonework. The air hums with raw magic. Malachar's influence is visible — black veins in the stone, whispering shadows.

| Room ID                  | Name                          | Connections                                      | Notes |
|--------------------------|-------------------------------|--------------------------------------------------|-------|
| `ancient_passage`        | The Ancient Passage           | up -> dungeon_stairs, south -> ward_chamber      | Entry to the Depths. First-visit text describes the transition from Hogwarts to something older. |
| `ward_chamber`           | The Ward Chamber              | north -> ancient_passage, south -> malachar_gallery | The failing ward stones are visible here. A puzzle to stabilize them temporarily. |
| `malachar_gallery`       | Malachar's Gallery            | north -> ward_chamber, south -> convergence_antechamber | Murals depicting Malachar's war with the Founders. Critical lore. The full backstory is here. |
| `convergence_antechamber`| The Convergence Antechamber   | north -> malachar_gallery, south -> convergence_chamber | Final preparation room. The four tokens must be placed on a pedestal to open the way forward. |

### Region 8: The Convergence Chamber (2 rooms)

**Entry**: From `convergence_antechamber` after placing all four tokens.

| Room ID                  | Name                          | Connections                                      | Notes |
|--------------------------|-------------------------------|--------------------------------------------------|-------|
| `convergence_chamber`    | The Convergence Chamber       | north -> convergence_antechamber, south -> stone_heart | The Convergence Stone is here, pulsing with corrupted energy. The final choice is made here. |
| `stone_heart`            | Heart of the Stone            | north -> convergence_chamber                     | The innermost point. Accessible only during the Unity Ending path. Where the permanent seal is forged. |

---

## 4. Puzzle Design

### Puzzle Summary Table

| #  | Puzzle ID                    | Name                              | Region           | Difficulty | Score | Optional | Type          |
|----|------------------------------|-----------------------------------|------------------|------------|-------|----------|---------------|
| 1  | `gargoyle_password`          | The Gargoyle's Password           | Commons          | 1          | 10    | No       | Knowledge     |
| 2  | `restricted_section_access`  | The Restricted Section            | Commons          | 2          | 15    | No       | NPC-gated     |
| 3  | `trophy_compartment`         | The Locked Trophy Case            | Commons          | 2          | 15    | No       | Key           |
| 4  | `potions_recipe`             | The Revealer Potion               | Commons          | 3          | 20    | No       | Combination   |
| 5  | `clock_tower_mechanism`      | The Jammed Clock                  | Grounds          | 2          | 15    | Yes      | State-based   |
| 6  | `forest_passage`             | Into the Forest                   | Grounds          | 2          | 10    | Yes      | NPC-gated     |
| 7  | `lake_shore_dig`             | The Buried Artifact               | Grounds          | 1          | 10    | Yes      | Use-on        |
| 8  | `boggart_confrontation`      | Facing the Boggart                | Gryffindor       | 3          | 25    | No       | State-based   |
| 9  | `bridge_crossing`            | Crossing the Flames               | Gryffindor       | 2          | 20    | No       | Use-on        |
| 10 | `guardian_rescue`            | Rescue Ron                        | Gryffindor       | 2          | 20    | No       | Fetch/Choice  |
| 11 | `eagle_doorknock`            | The Eagle's Riddle                | Ravenclaw        | 2          | 15    | No       | Knowledge     |
| 12 | `three_pedestals`            | The Three Pedestals               | Ravenclaw        | 3          | 25    | No       | Knowledge     |
| 13 | `potions_logic`              | The Seven Bottles                 | Ravenclaw        | 4          | 30    | No       | Sequence      |
| 14 | `star_chart_alignment`       | The Celestial Alignment           | Ravenclaw        | 3          | 20    | No       | State-based   |
| 15 | `stranger_healing`           | The Wounded Stranger              | Hufflepuff       | 2          | 20    | No       | Fetch         |
| 16 | `patience_garden`            | The Patient Gardener              | Hufflepuff       | 3          | 25    | No       | State-based   |
| 17 | `loyalty_gift`               | The Gift of Loyalty               | Hufflepuff       | 2          | 15    | No       | Fetch/Choice  |
| 18 | `serpent_door`               | The Serpent's Demand              | Slytherin        | 2          | 15    | No       | Use-on        |
| 19 | `real_or_fake`               | The Room of Deception             | Slytherin        | 4          | 30    | No       | Knowledge     |
| 20 | `ambition_sacrifice`         | The Price of Ambition             | Slytherin        | 2          | 15    | No       | Choice        |
| 21 | `ward_stabilization`         | Stabilizing the Wards             | Depths           | 4          | 30    | No       | Sequence      |
| 22 | `token_placement`            | The Four Tokens                   | Depths           | 3          | 25    | No       | Fetch         |
| 23 | `convergence_seal`           | Sealing the Stone                 | Chamber          | 5          | 35    | No       | Multi-step    |

**Total puzzle score**: 500 (matches max_score, with optional puzzles providing alternate routes to points rather than additive overflow — see Scoring section).

---

### Puzzle Specifications

#### Puzzle 1: The Gargoyle's Password

**ID**: `gargoyle_password`
**Region**: Hogwarts Commons
**Room**: `grand_staircase`
**Difficulty**: 1
**Score**: 10
**Type**: Knowledge (combination lock)

**Purpose**: Teach the player that information gathered from NPCs unlocks progression. This is the first real puzzle and should be solvable within 5 minutes.

**Player Experience**: "I need to get into Dumbledore's office, but the gargoyle wants a password. Who would know the password? McGonagall — she's the deputy headmistress."

**Setup**: The exit from `grand_staircase` to `dumbledore_office` is locked with a combination lock. The gargoyle asks for a password. The password is "Sherbet Lemon."

**Solution Steps**:
1. Talk to McGonagall (in `great_hall`). Her dialogue tree has a node that reveals the password when asked about Dumbledore. Sets flag `knows_gargoyle_password`.
2. At the gargoyle, type `say sherbet lemon` or `enter sherbet lemon`. Precondition: `has_flag(knows_gargoyle_password)`. The gargoyle steps aside.

**Clue Placement**: McGonagall's dialogue. Additionally, examining the gargoyle mentions "It seems to be waiting for a sweet word."

**Hints** (progressive):
1. "Perhaps someone on the staff knows the password."
2. "Professor McGonagall is Dumbledore's deputy. She might help."
3. "Talk to McGonagall and ask about the Headmaster's office."

**Edge Cases**:
- Player tries the password without learning it first: Fails. "The gargoyle doesn't budge. Perhaps you should learn the password before guessing."
- Player tries wrong words: "The gargoyle stares at you stonily."

**Implementation**:
- Lock type: `combination`, combination: `"sherbet lemon"`
- Command: verb `say`, pattern `say {word} {word2}`, precondition `has_flag(knows_gargoyle_password)` + `in_room(grand_staircase)`, effect `unlock(gargoyle_lock)` + `solve_puzzle(gargoyle_password)` + `add_score(10)`

---

#### Puzzle 2: The Restricted Section

**ID**: `restricted_section_access`
**Region**: Hogwarts Commons
**Room**: `library`
**Difficulty**: 2
**Score**: 15
**Type**: NPC-gated (fetch)

**Purpose**: Gate access to critical lore. Teach the player that NPCs trade favors for access.

**Player Experience**: "Hermione says the books about the Convergence Stone are in the Restricted Section, but it is roped off. I need permission — maybe a signed note from a professor."

**Setup**: The exit from `library` to `restricted_section` is hidden. Hermione (in `library`) tells the player they need a Signed Permission Slip. The slip is obtainable from Dumbledore (in `dumbledore_office`) after receiving the main quest briefing.

**Solution Steps**:
1. Complete Puzzle 1 (gargoyle password) to access Dumbledore's office.
2. Talk to Dumbledore. His dialogue grants the `permission_slip` item and sets `has_main_quest`.
3. Show the `permission_slip` to Hermione (or use it on the rope barrier). Effect: `reveal_exit(library_north)`, `set_flag(restricted_unlocked)`, `solve_puzzle(restricted_section_access)`.

**Hints**:
1. "Hermione mentioned needing written permission for the Restricted Section."
2. "A professor — perhaps the Headmaster — could grant access."
3. "Show the permission slip to Hermione in the library."

**Implementation**:
- The `restricted_section` exit from `library` is initially `is_hidden = true`.
- Command: `show {item} to {npc}`, with item = `permission_slip`, npc = `hermione`, effects reveal the exit.

---

#### Puzzle 3: The Locked Trophy Case

**ID**: `trophy_compartment`
**Region**: Hogwarts Commons
**Room**: `trophy_room`
**Difficulty**: 2
**Score**: 15
**Type**: Key (container unlock)

**Purpose**: Reveal the entrance to the Gryffindor Trial. Teach container mechanics.

**Player Experience**: "There is a locked compartment in the trophy case. What key opens it? The inscription mentions 'the key carried by the brave at heart.'"

**Setup**: The trophy case (`trophy_case` item, container, locked) holds the `gryffindor_map` — a diagram revealing the trial entrance. The key is the `prefect_badge` found in Ron's possession (given by Ron after a dialogue).

**Solution Steps**:
1. Examine the trophy case — description mentions the locked compartment and the inscription.
2. Talk to Ron (in `great_hall` or following the player). Ask about the badge. Ron gives the player the `prefect_badge`.
3. Use `prefect_badge` on `trophy_case` or `unlock trophy case`. Opens the case, revealing the `gryffindor_map`.
4. Examine `gryffindor_map` — reveals the hidden exit in the `trophy_room`. Effect: `reveal_exit(trophy_room_north)` (to `gryffindor_antechamber`), `solve_puzzle(trophy_compartment)`.

**Hints**:
1. "The inscription mentions bravery. Who among your friends embodies that?"
2. "Ron's prefect badge might be the key the inscription describes."
3. "Talk to Ron and ask about his badge, then use it on the trophy case."

---

#### Puzzle 4: The Revealer Potion

**ID**: `potions_recipe`
**Region**: Hogwarts Commons
**Room**: `potions_classroom`
**Difficulty**: 3
**Score**: 20
**Type**: Combination (multi-step)

**Purpose**: Create a potion that reveals the Slytherin Trial entrance. Teach the combine verb and consumable mechanics.

**Player Experience**: "The dungeon wall has a faint shimmer — something is hidden there. I need a potion to reveal it. The recipe is in the Restricted Section. The ingredients are in the greenhouse and the potions classroom."

**Setup**: The Slytherin Trial entrance is hidden behind an enchanted wall in `potions_classroom`. The `revealer_potion` makes it visible. The recipe is in a book in the `restricted_section`. Ingredients are `moonpetal` (from `greenhouse`) and `ashwinder_egg` (from `potions_classroom` shelf).

**Solution Steps**:
1. Read `revealer_recipe` in `restricted_section`. Sets flag `knows_revealer_recipe`.
2. Take `moonpetal` from `greenhouse`.
3. Take `ashwinder_egg` from `potions_classroom` (inside `ingredient_cabinet`, unlocked).
4. `combine moonpetal with ashwinder_egg` (requires `has_flag(knows_revealer_recipe)`). Produces `revealer_potion`.
5. `use revealer_potion on dungeon wall` (in `potions_classroom`). Reveals hidden exit to `slytherin_antechamber`. Consumes the potion.

**Hints**:
1. "That shimmer on the wall suggests concealment magic. A revealing potion might help."
2. "The Restricted Section likely has a recipe for such a potion."
3. "You need a moonpetal and an ashwinder egg. Try the greenhouse and the potions stores."

---

#### Puzzle 5: The Jammed Clock (Optional)

**ID**: `clock_tower_mechanism`
**Region**: Hogwarts Grounds
**Room**: `clock_tower_base`
**Difficulty**: 2
**Score**: 15
**Type**: State-based (toggle)

**Purpose**: Optional puzzle. Fixing the clock reveals a hidden message and a lore item about the Founders. Rewards curiosity.

**Player Experience**: "The clock mechanism is jammed. If I could find a tool to fix it..."

**Setup**: The clock is a toggleable item (jammed/running). A `wrench` is found in `hagrid_hut`. Using the wrench on the clock unjams it. The clock chimes and a panel opens, revealing `founders_journal_page_1`.

**Solution Steps**:
1. Examine the clock mechanism — "A gear is misaligned. A sturdy tool could set it right."
2. Find the `wrench` in Hagrid's hut (on the workbench).
3. `use wrench on clock mechanism` in `clock_tower_base`. Effect: `set_toggle_state(clock_mechanism, "running")`, `spawn_item(founders_journal_page_1, clock_tower_base)`, `solve_puzzle(clock_tower_mechanism)`.

---

#### Puzzle 6: Into the Forest (Optional)

**ID**: `forest_passage`
**Region**: Hogwarts Grounds
**Room**: `forest_edge`
**Difficulty**: 2
**Score**: 10
**Type**: NPC-gated

**Purpose**: Side quest access. Hagrid blocks the forest path until the player proves they have protection.

**Player Experience**: "Hagrid won't let me into the forest — says it's too dangerous. Maybe if I had some kind of protection..."

**Setup**: Hagrid is blocking the exit from `forest_edge` deeper into the forest (one-way, leads to a hidden grove with a lore item). The `shield_charm_scroll` (found in `hospital_wing`) convinces Hagrid.

**Solution Steps**:
1. Find `shield_charm_scroll` in `hospital_wing`.
2. Show it to Hagrid at `forest_edge`. Hagrid relents. Sets flag `hagrid_allows_forest`. Reveals exit.

> **Note**: The forest itself is a single optional room (`forbidden_grove`) with a lore item and atmosphere. It connects back to `forest_edge`. Not included in the room count for the Grounds region as it is extremely optional, but it exists.

---

#### Puzzle 7: The Buried Artifact (Optional)

**ID**: `lake_shore_dig`
**Region**: Hogwarts Grounds
**Room**: `lake_shore`
**Difficulty**: 1
**Score**: 10
**Type**: Use-on

**Purpose**: Discover a lore item. Teach the "use item on environment" pattern.

**Player Experience**: "Something is half-buried in the mud by the lake. If I had a tool to dig it out..."

**Setup**: A `rusted_amulet` is buried at `lake_shore`. The player needs the `small_shovel` (found in `greenhouse`) to dig it out.

**Solution Steps**:
1. Examine the muddy shore — "Something metallic glints beneath the mud."
2. Find `small_shovel` in `greenhouse`.
3. `use small_shovel on mud` or `dig mud` at `lake_shore`. Spawns `rusted_amulet`. The amulet is a lore item — examining it reveals text about Malachar's defeat and a hint for the Ward Stabilization puzzle.

---

#### Puzzle 8: Facing the Boggart

**ID**: `boggart_confrontation`
**Region**: Gryffindor Trial
**Room**: `fear_chamber`
**Difficulty**: 3
**Score**: 25
**Type**: State-based (dark room + toggle + use-on)

**Purpose**: Courage test. The player must light a dark room, face a fear manifestation, and dispel it.

**Player Experience**: "The room is pitch black. I hear something moving. I need light, and then I need to face whatever is in here."

**Setup**: `fear_chamber` is dark. The player needs an active light source (the `enchanted_lantern`, obtainable from Dumbledore's office). Once lit, the room description reveals a Boggart taking a terrifying form. The player must `cast riddikulus` (a command) to dispel it.

**Solution Steps**:
1. Enter `fear_chamber` with `enchanted_lantern` toggled to "on". Room becomes visible.
2. The room description reveals the Boggart. Examining it shows it shifting between fears.
3. `cast riddikulus` — requires `has_item(wand)` + `in_room(fear_chamber)` + `toggle_state(enchanted_lantern, "on")`. Effect: `set_flag(boggart_defeated)`, `solve_puzzle(boggart_confrontation)`, `remove_npc(boggart)`.

**Edge Cases**:
- Player enters without light: "It's pitch black. Something shifts in the darkness. You can't see to act."
- Player tries to cast without wand: "You need your wand for spellcasting."
- Player enters with light but has already defeated boggart: Boggart is gone, room is safe.

---

#### Puzzle 9: Crossing the Flames

**ID**: `bridge_crossing`
**Region**: Gryffindor Trial
**Room**: `bridge_of_flames`
**Difficulty**: 2
**Score**: 20
**Type**: Use-on (consumable)

**Purpose**: Resource-management test. The player must use a limited consumable (Flame-Freezing Potion) to cross safely.

**Player Experience**: "The bridge is engulfed in magical fire. Walking through will hurt me. I need protection — maybe a potion?"

**Setup**: The bridge deals damage if crossed without protection. The `flame_freezing_potion` (found in `potions_classroom` or brewed) protects the player.

**Solution Steps**:
1. Attempting to cross north without protection: `change_health(-40)`. Dangerous but not lethal at full HP.
2. `use flame_freezing_potion` or `drink flame_freezing_potion` (in `bridge_of_flames`). Sets flag `flame_protected`. Consumes one charge.
3. Move north — succeeds without damage. `solve_puzzle(bridge_crossing)`.

**Failure State**: Player can technically cross by tanking the damage if they have enough HP. This is a valid (painful) alternative. The puzzle is "solved" either way upon reaching the other side, but using the potion awards full score. Brute-forcing it awards half score (10 instead of 20).

**Implementation**:
- Trigger on `room_enter` for `guardian_hall`: if `not_flag(flame_protected)`, effect `change_health(-40)`, message "Flames sear your robes and skin. You stumble through, badly burned."
- If `has_flag(flame_protected)`: message "The flames wash over you harmlessly, feeling like warm bathwater.", `solve_puzzle(bridge_crossing)` with full score.
- Separate trigger for the brute-force path: `solve_puzzle(bridge_crossing)` with `add_score(10)` instead of 20.

---

#### Puzzle 10: Rescue Ron

**ID**: `guardian_rescue`
**Region**: Gryffindor Trial
**Room**: `guardian_hall`
**Difficulty**: 2
**Score**: 20
**Type**: Fetch / Moral Choice

**Purpose**: Test courage as selflessness. Ron is trapped under rubble. Helping him costs a healing potion. Leaving him sets a flag that affects the ending.

**Player Experience**: "Ron is pinned under fallen stones. He says to go on without him, but I can see he's hurt. I could use my healing potion on him, but then I won't have it for myself..."

**Setup**: Ron (NPC) is trapped in `guardian_hall`. The player can `give healing_potion to ron` or `use healing_potion on ron` to free him. Or they can proceed north without helping.

**Solution Steps (Courage Path)**:
1. `give healing_potion to ron` or `use healing_potion on ron`. Consumes the potion. Sets flag `ron_rescued`. Ron thanks the player and gives the `gryffindor_crest` (needed later as a hint).

**Solution Steps (Selfish Path)**:
1. Move north without helping Ron. Sets flag `ron_abandoned`. Ron says "I understand, mate. Go." Dialogue changes for the rest of the game.

**Moral Choice**: `ron_rescued` counts toward the Unity Ending. `ron_abandoned` counts toward the Compromise Ending. Both paths complete the trial, but the emotional and mechanical weight differs.

**Score**: 20 points for rescuing Ron. 0 for abandoning him (the puzzle is "solved" either way, but the score difference reflects the choice).

---

#### Puzzle 11: The Eagle's Riddle

**ID**: `eagle_doorknock`
**Region**: Ravenclaw Trial
**Room**: `ravenclaw_antechamber`
**Difficulty**: 2
**Score**: 15
**Type**: Knowledge (riddle)

**Purpose**: Gatekeeping entry to the Ravenclaw Trial proper. Tests lateral thinking.

**Player Experience**: "The eagle door-knocker asks a riddle. If I answer correctly, the door opens."

**Setup**: The exit from `ravenclaw_antechamber` to `riddle_hall` is locked. The eagle poses a riddle. The answer is discoverable from Luna Lovegood (she mentions it in passing dialogue) or by pure reasoning.

**Riddle**: "I have cities, but no houses. I have mountains, but no trees. I have water, but no fish. What am I?"
**Answer**: "a map"

**Solution Steps**:
1. Examine the eagle door-knocker — it speaks the riddle.
2. `answer a map` or `say a map` — precondition: `in_room(ravenclaw_antechamber)`. Effect: `unlock(eagle_door_lock)`, `solve_puzzle(eagle_doorknock)`.

**Clue Placement**: Luna (in `corridor_east` or `courtyard`) mentions in dialogue: "I rather like maps. They have everything — cities, mountains, water — but none of it is real." This is a hint, not a direct answer.

---

#### Puzzle 12: The Three Pedestals

**ID**: `three_pedestals`
**Region**: Ravenclaw Trial
**Room**: `riddle_hall`
**Difficulty**: 3
**Score**: 25
**Type**: Knowledge (multi-item placement)

**Purpose**: Test accumulated knowledge. Three riddles require three answers — objects that represent Hogwarts values.

**Player Experience**: "Three pedestals, each with an inscription. I need to place the correct object on each one."

**Setup**: Three pedestals require three specific items:
- Pedestal of Bravery: requires the `gryffindor_crest` (from Ron, if rescued — otherwise a substitute exists in `trophy_room`).
- Pedestal of Knowledge: requires `founders_journal_page_1` (from the Clock Tower optional puzzle or the Restricted Section).
- Pedestal of Unity: requires `rusted_amulet` (from Lake Shore optional puzzle or a second copy in the `mirror_maze` for players who skipped the optional content).

**Solution Steps**:
1. `put gryffindor_crest on pedestal_bravery`
2. `put founders_journal on pedestal_knowledge`
3. `put rusted_amulet on pedestal_unity`
4. When all three are placed: `set_flag(pedestals_complete)`, `unlock(riddle_hall_north)`, `solve_puzzle(three_pedestals)`.

**Failsafe**: Alternate items exist for each pedestal so optional puzzles are never required for critical-path progression.

---

#### Puzzle 13: The Seven Bottles

**ID**: `potions_logic`
**Region**: Ravenclaw Trial
**Room**: `logic_chamber`
**Difficulty**: 4
**Score**: 30
**Type**: Sequence (logic deduction)

**Purpose**: The hardest Ravenclaw puzzle. A direct homage to Snape's potions puzzle from Philosopher's Stone.

**Player Experience**: "Seven bottles. A poem gives me the rules. I need to figure out which bottle lets me go forward."

**Setup**: Seven bottles on a table. A poem on the wall provides logical constraints. Only one bottle advances the player. Two are harmless. One is harmful (deals damage). Three are empty.

**The Verse** (examined from `logic_poem` item on the wall):
> "Three of us are empty vessels, void of use or trick.
> One will harm the drinker — choose that one and you'll feel sick.
> Two will do nothing, neither help nor hinder thee.
> The one you want stands second from the left of what is three.
> The poison never neighbors the passage ahead.
> The smallest of the lot holds nothing in its stead."

**Answer**: Bottle 5 (the second from the left of the three empty ones, which occupy positions 1, 4, 7; but the "three" is contextual — see below). The implementation simplifies this to a command: `drink bottle five` or `drink fifth bottle`.

**Solution Steps**:
1. Read the poem carefully.
2. Examine individual bottles — descriptions give size/color clues that map to the verse.
3. `drink fifth bottle` or `use bottle_five`. Effect: `set_flag(logic_potion_drunk)`, `solve_puzzle(potions_logic)`. The exit north unlocks.

**Wrong Choices**:
- Bottle 3 (poison): `change_health(-30)`, message about burning sensation.
- Others: "The bottle is empty" or "Nothing happens. You feel no different."

**Hints** (from examining the `mirror_maze` mirror, which shows Snape writing the verse):
1. "Snape's puzzle relies on elimination. The verse tells you what each bottle is NOT."
2. "Start by identifying the smallest bottle — the poem says it's empty."
3. "The poison cannot be next to the correct bottle. Use that to narrow down."

---

#### Puzzle 14: The Celestial Alignment

**ID**: `star_chart_alignment`
**Region**: Ravenclaw Trial
**Room**: `celestial_room`
**Difficulty**: 3
**Score**: 20
**Type**: State-based (NPC collaboration)

**Purpose**: Hermione puzzle. The player and Hermione must work together.

**Player Experience**: "Hermione found a path here too. She has half the star chart, I have half. Together we can align the constellations."

**Setup**: Hermione is in `celestial_room`. She has the `star_chart_north`. The player found `star_chart_south` (in `library`, examine the astronomy shelf). Combining them through dialogue with Hermione solves the puzzle.

**Solution Steps**:
1. Have `star_chart_south` in inventory.
2. Talk to Hermione in `celestial_room`. A dialogue option appears (gated by `has_item(star_chart_south)`): "I have the southern chart. Let's combine them."
3. Selecting this option: `set_flag(charts_combined)`, `solve_puzzle(star_chart_alignment)`, reveals exit north to `ravenclaw_vault`.

---

#### Puzzle 15: The Wounded Stranger

**ID**: `stranger_healing`
**Region**: Hufflepuff Trial
**Room**: `wounded_stranger`
**Difficulty**: 2
**Score**: 20
**Type**: Fetch (consumable sacrifice)

**Purpose**: Test generosity. The player must give up a healing resource to help a stranger.

**Player Experience**: "A ghostly figure is hurt. They ask for help. I have a healing potion... but I might need it later."

**Setup**: The `spectral_student` (NPC) in `wounded_stranger` is injured. Using or giving `healing_potion` to them heals them and sets `stranger_healed`.

**Solution Steps**:
1. `give healing_potion to spectral_student` or `use healing_potion on spectral_student`. Consumes 1 charge of healing_potion. Sets `stranger_healed`.
2. The stranger thanks the player and vanishes, leaving behind `hufflepuff_charm` (needed for the Patience Garden).

**Edge Case**: If the player used all healing potions on Ron and/or themselves, a backup exists — the stranger also accepts `magical_candy` (found in kitchens from Dobby).

---

#### Puzzle 16: The Patient Gardener

**ID**: `patience_garden`
**Region**: Hufflepuff Trial
**Room**: `garden_of_patience`
**Difficulty**: 3
**Score**: 25
**Type**: State-based (flag accumulation)

**Purpose**: Test patience. The garden requires the player to perform actions elsewhere and return. It cannot be solved by staying in the room.

**Player Experience**: "A seedling in enchanted soil. The plaque says 'Patience bears fruit.' Nothing I do makes it grow. Maybe I need to go do other things and come back?"

**Setup**: A magical seedling. The player must `plant hufflepuff_charm` in the soil, then leave the room and solve at least one other puzzle (any puzzle — tracked by flag count). Upon returning, the plant has bloomed, revealing the path forward.

**Solution Steps**:
1. `use hufflepuff_charm on seedling` or `plant hufflepuff_charm`. Sets flag `charm_planted`.
2. Leave the room. Solve any other puzzle (the trigger checks for any new `puzzle_solved` flag set after `charm_planted`).
3. Return to `garden_of_patience`. A room_enter trigger fires: if `charm_planted` AND at least one puzzle solved since planting, the plant blooms. `set_flag(garden_bloomed)`, `reveal_exit(garden_of_patience_south)`, `solve_puzzle(patience_garden)`.

**Design Note**: This puzzle deliberately frustrates players who try to brute-force it. The hint system gently nudges: "Perhaps this plant needs time, not attention. Go attend to other matters and return."

---

#### Puzzle 17: The Gift of Loyalty

**ID**: `loyalty_gift`
**Region**: Hufflepuff Trial
**Room**: `loyalty_passage`
**Difficulty**: 2
**Score**: 15
**Type**: Fetch / Moral Choice

**Purpose**: Test loyalty through letting go. The player finds a valuable item but must give it to the ghostly student at the crossroads.

**Player Experience**: "I found a golden locket in the passage. It is beautiful and probably valuable. But the ghost at the crossroads seems to recognize it..."

**Setup**: A `golden_locket` is found in `loyalty_passage`. At `crossroads_of_need`, the `ghostly_student_2` (different from the wounded stranger) recognizes it — it was theirs in life. Giving it sets `loyalty_proven`.

**Solution Steps**:
1. Take `golden_locket` from `loyalty_passage`.
2. At `crossroads_of_need`, talk to `ghostly_student_2`. They mention the locket.
3. `give golden_locket to ghostly_student_2`. Sets `loyalty_proven`, `solve_puzzle(loyalty_gift)`. The ghost blesses the player and fades.

**Alternative**: Keeping the locket sets `locket_kept` and the Hufflepuff vault has an alternate (harder) unlock mechanism. The puzzle is completable either way but the ending flags differ.

---

#### Puzzle 18: The Serpent's Demand

**ID**: `serpent_door`
**Region**: Slytherin Trial
**Room**: `slytherin_antechamber`
**Difficulty**: 2
**Score**: 15
**Type**: Use-on

**Purpose**: Gate the Slytherin Trial. The serpent door demands proof of cunning — not force.

**Player Experience**: "The serpent carved in the door hisses. It won't open to brute force. What does it want?"

**Setup**: The serpent door examines to: "The serpent's stone eyes seem to follow your movements. Its mouth is open, as if expecting something to be placed inside." The answer is the `slytherin_ring` — a ring found in the `trophy_room` (inside the trophy case, alongside the Gryffindor map).

**Solution Steps**:
1. `use slytherin_ring on serpent door`. Effect: `unlock(slytherin_antechamber_south)`, `solve_puzzle(serpent_door)`.

---

#### Puzzle 19: The Room of Deception

**ID**: `real_or_fake`
**Region**: Slytherin Trial
**Room**: `deception_room`
**Difficulty**: 4
**Score**: 30
**Type**: Knowledge (examination + deduction)

**Purpose**: Test discernment. Three chests in the room — one contains the real key to progress, two are traps.

**Player Experience**: "Three identical chests. The inscription says 'The cunning see through lies.' I need to figure out which chest is real."

**Setup**: Three container items: `silver_chest`, `gold_chest`, `iron_chest`. Each has examine text with subtle tells:
- `silver_chest`: "Polished to a mirror shine. Your reflection looks... slightly wrong. As if it is grinning when you are not."
- `gold_chest`: "Ornate and heavy. The gold is warm to the touch — too warm, as if heated from within."
- `iron_chest`: "Plain and unassuming. A faint scratch on the lid forms what might be the letter 'S'."

The iron chest is correct (Slytherin valued substance over showiness). The scratch is Slytherin's mark.

**Solution Steps**:
1. Examine all three chests. Clue: the "S" scratch on the iron chest.
2. `open iron_chest`. Contains `serpent_key`. `solve_puzzle(real_or_fake)`.
3. Opening `silver_chest`: triggers a trap — `change_health(-20)`, message about a biting illusion.
4. Opening `gold_chest`: triggers a trap — `change_health(-15)`, spawns fake key that dissolves.

**Clue Placement**: A note in the `serpent_hall` reads: "Salazar despised ostentation. His mark was simple: a single stroke, a single letter."

---

#### Puzzle 20: The Price of Ambition

**ID**: `ambition_sacrifice`
**Region**: Slytherin Trial
**Room**: `ambition_stair`
**Difficulty**: 2
**Score**: 15
**Type**: Choice (item sacrifice)

**Purpose**: The staircase demands the player give up an inventory item to proceed. Which item is sacrificed affects later options.

**Player Experience**: "The staircase rises but has no top. A voice says: 'To rise, you must leave something behind.' What do I give up?"

**Setup**: The player must drop any takeable item on the `offering_stone` (a container). The stair extends. Some items are more costly to lose than others, affecting later puzzles.

**Solution Steps**:
1. `put [any item] on offering_stone` or `use [any item] on offering_stone`. Sets flag `sacrifice_made`. The item is consumed (removed from game).
2. The staircase extends. Exit south to `bargain_chamber` is revealed.

**Design Note**: Sacrificing the `enchanted_lantern` makes the Depths harder (dark rooms). Sacrificing a healing potion reduces health reserves. Sacrificing a lore item removes score opportunity. The player must choose what they value least — a test of cunning resource management.

---

#### Puzzle 21: Ward Stabilization

**ID**: `ward_stabilization`
**Region**: The Depths
**Room**: `ward_chamber`
**Difficulty**: 4
**Score**: 30
**Type**: Sequence (toggle states)

**Purpose**: Stabilize the failing ward stones. Mechanical climax of Act 2.

**Player Experience**: "Four ward stones, each pulsing with a different color. They need to be activated in the right order, or the instability worsens."

**Setup**: Four toggleable items: `ward_stone_red`, `ward_stone_blue`, `ward_stone_yellow`, `ward_stone_green` (mapping to the four Houses). They must be activated in the order the Founders built them: Yellow (Hufflepuff), Blue (Ravenclaw), Red (Gryffindor), Green (Slytherin). The order is revealed by the murals in `malachar_gallery`.

**Solution Steps**:
1. Visit `malachar_gallery`. Examine the murals — they depict the Founders in the order they laid the ward stones. Sets flag `knows_ward_order`.
2. Return to `ward_chamber`.
3. `activate yellow stone` -> `activate blue stone` -> `activate red stone` -> `activate green stone`. Each step sets a flag. After the fourth, `solve_puzzle(ward_stabilization)`.

**Wrong Order**: Activating in wrong order resets all stones. Message: "The stones flare and go dark. The ward energy dissipates. You'll need to start the sequence again."

**Implementation**: Four commands with chained preconditions. `activate yellow stone` requires `in_room(ward_chamber)` and `has_flag(knows_ward_order)`. `activate blue stone` requires `has_flag(ward_yellow_active)`. And so on.

---

#### Puzzle 22: The Four Tokens

**ID**: `token_placement`
**Region**: The Depths
**Room**: `convergence_antechamber`
**Difficulty**: 3
**Score**: 25
**Type**: Fetch (multi-item gate)

**Purpose**: Final gate before the Convergence Chamber. All four Founder Tokens must be placed.

**Player Experience**: "Four alcoves in the wall, each shaped for a specific artifact. I need all four Founder Tokens."

**Setup**: A container with `accepts_items` whitelist: `gryffindor_token`, `ravenclaw_token`, `hufflepuff_token`, `slytherin_token`.

**Solution Steps**:
1. `put gryffindor_token in token_alcove`
2. `put ravenclaw_token in token_alcove`
3. `put hufflepuff_token in token_alcove`
4. `put slytherin_token in token_alcove`
5. When all four are placed: trigger fires. `set_flag(tokens_placed)`, `reveal_exit(convergence_antechamber_south)`, `solve_puzzle(token_placement)`.

---

#### Puzzle 23: Sealing the Stone

**ID**: `convergence_seal`
**Region**: Convergence Chamber
**Room**: `convergence_chamber`
**Difficulty**: 5
**Score**: 35
**Type**: Multi-step (ending-dependent)

**Purpose**: The final puzzle. How the player seals (or fails to seal) the Stone determines the ending. This puzzle has multiple valid solutions with different outcomes.

**Player Experience**: "The Convergence Stone pulses with dark energy. Malachar's curse is visible as black veins through the crystal. I need to act — but how I act matters."

**Solution Paths**:

**Path A — Unity (requires flags: `ron_rescued`, `loyalty_proven`, `stranger_healed`, `draco_allied`)**:
1. `cast unity charm` (requires all four cooperation flags). All four Tokens resonate. The curse is purged completely.
2. Effect: `set_flag(stone_sealed_unity)`, `solve_puzzle(convergence_seal)`.

**Path B — Sacrifice (requires flag: `sacrifice_made`, at least 2 trial cooperation flags)**:
1. `touch convergence stone`. Harry channels his magic directly. The curse is sealed but Harry's magic is spent.
2. Effect: `set_flag(stone_sealed_sacrifice)`, `solve_puzzle(convergence_seal)`.

**Path C — Draco's Help (requires flag: `draco_allied` but NOT all cooperation flags)**:
1. `cast seal with draco` or talk to Draco here (he appears if `draco_allied`). Combined effort partially seals.
2. Effect: `set_flag(stone_sealed_rival)`, `solve_puzzle(convergence_seal)`.

**Path D — Partial Seal (default — any remaining combination)**:
1. `cast seal`. Harry alone partially contains the corruption.
2. Effect: `set_flag(stone_sealed_partial)`, `solve_puzzle(convergence_seal)`.

**Path E — Failure (player HP < 20 when reaching chamber, OR `malachar_awakened` flag set)**:
1. If player arrives weakened or delayed too long, the curse overwhelms. `set_flag(stone_corrupted)`.

---

## 5. NPC Design

### NPC Summary Table

| #  | NPC ID               | Name                      | Location(s)                  | Role                                     |
|----|----------------------|---------------------------|------------------------------|------------------------------------------|
| 1  | `ron`                | Ron Weasley               | `great_hall`, `guardian_hall` | Companion, item giver, moral choice      |
| 2  | `hermione`           | Hermione Granger          | `library`, `celestial_room`  | Companion, knowledge source, puzzle aid  |
| 3  | `dumbledore`         | Albus Dumbledore          | `dumbledore_office`          | Quest giver, key item provider           |
| 4  | `mcgonagall`         | Professor McGonagall      | `great_hall`                 | Information source (password), quest aid  |
| 5  | `snape`              | Professor Snape           | `potions_classroom`          | Information source (potions), foil       |
| 6  | `hagrid`             | Rubeus Hagrid             | `hagrid_hut`, `forest_edge`  | Item giver, NPC blocker, side quest      |
| 7  | `flitwick`           | Professor Flitwick        | `corridor_east`              | Spell teacher, charm info                |
| 8  | `neville`            | Neville Longbottom        | `greenhouse`                 | Herbology info, ingredient guidance      |
| 9  | `luna`               | Luna Lovegood             | `courtyard`                  | Riddle hints, lore, side quest           |
| 10 | `draco`              | Draco Malfoy              | `serpent_hall`, `convergence_chamber` | Rival, potential ally, moral choice |
| 11 | `ginny`              | Ginny Weasley             | `great_hall`                 | Side quest giver, emotional support      |
| 12 | `fred_george`        | Fred and George Weasley   | `corridor_west`              | Item traders, comic relief, secret info  |
| 13 | `nick`               | Nearly Headless Nick      | `entrance_hall`              | Lore source, atmosphere, trail guide     |
| 14 | `grey_lady`          | The Grey Lady             | `library`                    | Ravenclaw Trial entry clue, lore         |
| 15 | `fat_friar`          | The Fat Friar             | `kitchen_corridor`           | Hufflepuff Trial hints                   |
| 16 | `bloody_baron`       | The Bloody Baron          | `dungeon_stairs`             | Slytherin Trial atmosphere, warning      |
| 17 | `dobby`              | Dobby                     | `kitchens`                   | Side quest, Hufflepuff Trial entry       |
| 18 | `peeves`             | Peeves                    | (roaming — multiple rooms)   | Chaos, misdirection, comic relief        |
| 19 | `filch`              | Argus Filch               | `corridor_west`              | Blocker (confiscates items if caught)    |
| 20 | `myrtle`             | Moaning Myrtle            | `hospital_wing`              | Lore source, hints about the Depths      |
| 21 | `boggart`            | The Boggart               | `fear_chamber`               | Puzzle enemy (not a dialogue NPC)        |
| 22 | `spectral_student`   | Spectral Student          | `wounded_stranger`           | Puzzle NPC (Hufflepuff Trial)            |
| 23 | `ghostly_student_2`  | Ghostly Student           | `crossroads_of_need`         | Puzzle NPC (Hufflepuff Trial)            |

---

### NPC Specifications

#### Ron Weasley

**ID**: `ron`
**Starting Location**: `great_hall`
**Category**: `character`

**Purpose**: Ron serves three roles: (1) gives the player the `prefect_badge` for the trophy case puzzle, (2) appears trapped in the Gryffindor Trial as a moral choice, (3) provides comic relief and emotional grounding.

**Dialogue Tree**:
- **Root Node** (initial): "Harry! Things have gone barmy. The staircases won't stop moving, and I swear I saw a corridor that wasn't there yesterday."
  - Option: "What do you know about the disturbances?" -> Node about the wards failing. Sets flag `ron_warned`.
  - Option: "I need your prefect badge." (requires `has_flag(has_main_quest)`) -> Ron hands it over. Effect: `spawn_item(prefect_badge, inventory)`. "My badge? Take it. Not like I was using it for anything useful."
  - Option: "Come with me." -> "Wherever you need me, mate." (flavor — Ron does not physically follow as a companion NPC in the engine, but his presence is narratively implied).

**Gryffindor Trial appearance**: Ron is moved to `guardian_hall` via trigger when the player enters the trial. He is trapped — not a dialogue NPC in this context but a target for item use.

---

#### Hermione Granger

**ID**: `hermione`
**Starting Location**: `library`
**Category**: `character`

**Purpose**: Hermione is the player's knowledge lifeline. She explains the Restricted Section requirement, provides the star chart puzzle collaboration, and offers progressive hints if the player talks to her at various stages.

**Dialogue Tree**:
- **Root Node**: "Harry, I've been researching. The Convergence Stone is mentioned in 'Hogwarts: A Hidden History' — but the relevant chapter is in the Restricted Section."
  - Option: "How do I get into the Restricted Section?" -> "You'll need a signed permission slip from a professor. Dumbledore would be your best bet."
  - Option: "What have you found so far?" -> Lore dump about the Founders and the Stone. Sets flag `hermione_lore_1`.
  - Option: "Have you seen anything strange?" -> "The castle is... shifting. I saw a corridor fold in on itself near the library. It is like the magic that holds Hogwarts together is coming undone."

**Celestial Room appearance**: Hermione is moved to `celestial_room` via trigger when the player reaches the Ravenclaw Trial's later rooms.

---

#### Albus Dumbledore

**ID**: `dumbledore`
**Starting Location**: `dumbledore_office`
**Category**: `character`

**Purpose**: Main quest giver. Provides the `enchanted_lantern`, the `permission_slip`, the `wand` (if the player does not already have it — the wand is also available as a starting inventory item), and the quest briefing.

**Dialogue Tree**:
- **Root Node**: "Ah, Harry. I feared you would come. The wards are failing — you can feel it, can't you? The Convergence Stone, hidden in the depths of the castle for a thousand years, has been corrupted."
  - Option: "What is the Convergence Stone?" -> Detailed explanation. Sets flag `knows_stone_lore`.
  - Option: "What do I need to do?" -> Explains the Founders' Trial. Gives `permission_slip` and `enchanted_lantern`. Sets flag `has_main_quest`. Discovers main quest.
  - Option: "Why can't you fix it yourself?" -> "My magic is needed to hold the wards. If I leave this office, the castle may not survive until morning."
  - Option: "What about Malachar?" (requires `has_flag(restricted_lore_read)`) -> Detailed backstory about Malachar the Undying. Sets flag `dumbledore_malachar_info`.

---

#### Professor Snape

**ID**: `snape`
**Starting Location**: `potions_classroom`
**Category**: `character`

**Purpose**: Provides potion recipe hints and ingredients. Reluctant helper. His dialogue is terse and dismissive but contains critical information.

**Dialogue Tree**:
- **Root Node**: "Potter. I assume you're here for something other than your dismal academic record."
  - Option: "I need help with a potion." -> "Which potion? Be specific." -> Sub-node with options for Revealer Potion (requires `has_flag(knows_revealer_recipe)`), Flame-Freezing Potion, Healing Potion.
  - Option: "Do you know about the Convergence Stone?" -> "I know enough to stay out of its way. Unlike certain students." Sets flag `snape_warned`.
  - Option: "Never mind." -> "Then stop wasting my time."

**Revealer Potion sub-node** (gated by `knows_revealer_recipe`): "The Revealer Draught. Moonpetal from the greenhouse, ashwinder egg from my stores. Combine them carefully. The instructions are in the recipe — do try to follow them." Sets flag `snape_potion_help`.

---

#### Hagrid

**ID**: `hagrid`
**Starting Location**: `hagrid_hut`
**Category**: `character`

**Purpose**: Provides the `wrench` (for the clock puzzle), blocks the forest path until conditions are met, offers backstory about the Founders.

**Dialogue Tree**:
- **Root Node**: "Harry! Blimey, the castle's in a state. Come in, come in. Fang's been whimperin' all day."
  - Option: "What do you know about the Founders' Trials?" -> "Dumbledore told me once — said the Founders hid challenges deep in the castle. Never thought they'd need findin'." Sets flag `hagrid_founder_info`.
  - Option: "Can I borrow that wrench?" -> "The one on the bench? Sure, take it. Mind you bring it back." Effect: `make_takeable(wrench)`.
  - Option: "I need to get into the forest." -> "Not a chance, Harry. Too dangerous." (Gated dialogue option appears when player has `shield_charm_scroll`: "I have a shield charm." -> "Well... if yer prepared. Be careful." Sets flag `hagrid_allows_forest`.)

---

#### Draco Malfoy

**ID**: `draco`
**Starting Location**: `serpent_hall` (appears only when player enters Slytherin Trial)
**Category**: `character`

**Purpose**: The rival. Draco is racing to reach the Convergence Stone. In the Slytherin Trial, the player can choose to fight him, trick him, or ally with him. The choice has major ending implications.

**Dialogue Tree** (in `serpent_hall`):
- **Root Node**: "Potter. I might have known you'd show up. I found this trial weeks ago — I've been working through it alone."
  - Option: "Why do you want the Stone?" -> "Because my family's legacy depends on it. The Malfoys helped fund Hogwarts — did you know that? We deserve a say in its protection."
  - Option: "We should work together." (requires `has_flag(ron_rescued)` — showing a pattern of cooperation) -> "Together? With you?" Long pause. "...Fine. But I'm not doing this for you." Sets flag `draco_allied`.
  - Option: "Get out of my way, Malfoy." -> "Make me, Potter." Sets flag `draco_hostile`. Draco moves to block the exit south temporarily.
  - Option: "There's room for both of us." -> "Is there? We'll see about that." Neutral — Draco doesn't help or hinder. Sets flag `draco_neutral`.

**Convergence Chamber appearance**: If `draco_allied`, Draco appears in `convergence_chamber` as an ally, enabling Ending C. If `draco_hostile`, he appears as an obstacle (NPC blocking, requires dialogue to pass). If `draco_neutral`, he is absent.

---

#### Luna Lovegood

**ID**: `luna`
**Starting Location**: `courtyard`
**Category**: `character`

**Purpose**: Provides oblique hints. Her dialogue contains riddle answers and lore wrapped in her characteristic dreaminess. Side quest giver (the Nargle Hunt).

**Dialogue Tree**:
- **Root Node**: "Hello, Harry. The Wrackspurts are very thick today. Something is troubling the castle."
  - Option: "Have you noticed anything strange?" -> "Strange? Everything is strange, Harry. But I did see a corridor that was pretending to be a wall. Very rude of it."
  - Option: "Do you know any riddles?" -> "I like riddles. Maps are rather like riddles, aren't they? They have cities but no houses, mountains but no trees..." Sets flag `luna_riddle_hint`.
  - Option: "What are Wrackspurts?" -> Side quest dialogue. Discovers side quest `nargle_hunt`. "They float in through your ears and make your brain go fuzzy. I've been tracking them through the castle."

---

#### Dobby

**ID**: `dobby`
**Starting Location**: `kitchens`
**Category**: `character`

**Purpose**: Side quest NPC. Reveals the Hufflepuff Trial entrance after the player helps him.

**Dialogue Tree**:
- **Root Node**: "Harry Potter, sir! Dobby is so happy to see you! But Dobby is worried — the kitchens are shaking, sir, and the house-elves are frightened."
  - Option: "Is there anything I can help with?" -> "The cold stores have sealed themselves shut, sir. Strange magic. If Harry Potter could open them..." Discovers side quest `dobby_cold_stores`.
  - Option: "Have you seen anything unusual down here?" -> "Dobby has, sir. There is a door behind the biggest barrel — Dobby has never seen it before. It appeared yesterday." (After `dobby_helped` flag set): "Dobby opened the door for Harry Potter, sir! It leads somewhere old and warm." Effect: `reveal_exit(kitchens_south)` to `hufflepuff_antechamber`.

**Side Quest**: The cold stores puzzle — a locked container in `kitchens` that requires a specific item (a `warming_charm_token` from Flitwick) to open.

---

#### Nearly Headless Nick

**ID**: `nick`
**Starting Location**: `entrance_hall`
**Category**: `ghost`

**Purpose**: Atmospheric lore NPC. Tells stories about the Founders. His dialogue changes as the player progresses.

**Dialogue Tree**:
- **Root Node**: "Good evening! Dreadful business, this ward trouble. In my day — well, in my death — Hogwarts never shook like this."
  - Option: "What do you know about the Founders?" -> Lengthy lore about the founding era. Sets flag `nick_founder_lore`.
  - Option: "Have you seen anything in the corridors?" -> "Rooms appearing where there were none. I floated through a wall last night and found myself in a chamber I've never seen in four hundred years of haunting."
  - Option (after `trial_gryffindor_complete`): "The Gryffindor Trial is done." -> "Is it now? Godric would be proud. Or furious. Hard to tell with Gryffindors."

---

#### The Grey Lady (Helena Ravenclaw)

**ID**: `grey_lady`
**Starting Location**: `library`
**Category**: `ghost`

**Purpose**: Reveals the Ravenclaw Trial entrance. Her dialogue is guarded — she reveals information reluctantly.

**Dialogue Tree**:
- **Root Node**: "You seek something. They all do."
  - Option: "I'm looking for Ravenclaw's Trial." -> "My mother's trial. She hid it well." Requires `has_flag(has_main_quest)`. -> Sub-node: "The entrance responds to a question properly asked. Look for the eagle where knowledge is kept." Sets flag `grey_lady_clue`. Reveals hidden exit from `library` to `ravenclaw_antechamber`.
  - Option: "Tell me about Rowena Ravenclaw." -> Lore about Ravenclaw's philosophy. Sets flag `ravenclaw_lore`.

---

#### Fred and George Weasley

**ID**: `fred_george`
**Starting Location**: `corridor_west`
**Category**: `character`

**Purpose**: Item traders. They offer useful consumables in exchange for items or information. Comic relief.

**Dialogue Tree**:
- **Root Node**: "Oi, Harry!" "Fancy meeting you here!" "We've got stock to move—" "—and you look like a customer."
  - Option: "What do you have?" -> Inventory: `magical_candy` (x3, healing consumable), `peruvian_darkness_powder` (creates temporary darkness — useful as a distraction), `trick_wand` (cosmetic, no use). Trade requires `galleons` (found in various rooms).
  - Option: "Do you know any secret passages?" -> "You've got the Marauder's Map, don't you? We gave it to you." -> If player has the Map: "Check the seventh floor." Sets flag `twins_hint`.
  - Option: "Any news?" -> Flavor dialogue about the castle chaos.

---

#### Peeves

**ID**: `peeves`
**Starting Location**: `corridor_east` (moves via triggers)
**Category**: `ghost`

**Purpose**: Chaos agent. Peeves cannot be talked to productively. He appears in rooms via triggers and causes mischief — dropping items, changing descriptions, providing comic misdirection. He is more of an atmospheric system than a traditional NPC.

**Behavior**: Peeves moves between rooms on specific triggers. When encountered, he delivers a one-liner and may `move_item` something to a different room (forcing the player to track it down). He can be scared off with the Bloody Baron's name (a flag-gated dialogue option available after talking to the Baron).

---

#### Moaning Myrtle

**ID**: `myrtle`
**Starting Location**: `hospital_wing`
**Category**: `ghost`

**Purpose**: Lore source about the Depths. Myrtle knows about the ancient passages beneath the castle because she's explored them as a ghost.

**Dialogue Tree**:
- **Root Node**: "Oh, it's you. Nobody ever visits just to see me."
  - Option: "What do you know about the passages beneath the castle?" -> "There are tunnels below the dungeons. Old ones. They smell like wet stone and something... electric. I went down once. Something whispered my name. I left." Sets flag `myrtle_depths_hint`.
  - Option: "Have you been to the Chamber of Secrets recently?" -> "Don't mention that place." (Dead end, flavor.)

---

## 6. Item Design

### Item Summary Table

| #  | Item ID                    | Name                         | Type        | Location                  | Takeable | Purpose |
|----|----------------------------|------------------------------|-------------|---------------------------|----------|---------|
| 1  | `wand`                     | Harry's Wand                 | Tool        | Starting inventory        | Yes      | Required for spell commands |
| 2  | `marauders_map`            | The Marauder's Map           | Tool        | Starting inventory        | Yes      | Reveals room connections when used |
| 3  | `enchanted_lantern`        | Enchanted Lantern            | Toggle/Light| `dumbledore_office`       | Yes      | Light source for dark rooms |
| 4  | `permission_slip`          | Signed Permission Slip       | Key item    | `dumbledore_office` (via dialogue) | Yes | Unlocks Restricted Section |
| 5  | `prefect_badge`            | Ron's Prefect Badge          | Key item    | Ron (via dialogue)        | Yes      | Opens trophy case |
| 6  | `gryffindor_map`           | Map to the Gryffindor Trial  | Lore        | `trophy_case` (container) | Yes      | Reveals Gryffindor Trial exit |
| 7  | `slytherin_ring`           | Slytherin's Signet Ring      | Key item    | `trophy_case` (container) | Yes      | Opens serpent door |
| 8  | `revealer_recipe`          | Revealer Potion Recipe       | Lore        | `restricted_section`      | Yes      | Teaches Revealer Potion |
| 9  | `moonpetal`                | Moonpetal                    | Ingredient  | `greenhouse`              | Yes      | Revealer Potion ingredient |
| 10 | `ashwinder_egg`            | Ashwinder Egg                | Ingredient  | `potions_classroom`       | Yes      | Revealer Potion ingredient |
| 11 | `revealer_potion`          | Revealer Potion              | Consumable  | (crafted)                 | Yes      | Reveals Slytherin Trial entrance |
| 12 | `healing_potion`           | Healing Potion               | Consumable  | `hospital_wing`           | Yes      | Restores 30 HP. Quantity: 3 |
| 13 | `flame_freezing_potion`    | Flame-Freezing Potion        | Consumable  | `potions_classroom`       | Yes      | Protects from fire. Quantity: 1 |
| 14 | `wrench`                   | Hagrid's Wrench              | Tool        | `hagrid_hut`              | Yes      | Fixes clock mechanism |
| 15 | `small_shovel`             | Small Shovel                 | Tool        | `greenhouse`              | Yes      | Digs at lake shore |
| 16 | `shield_charm_scroll`      | Shield Charm Scroll          | Key item    | `hospital_wing`           | Yes      | Convinces Hagrid to allow forest entry |
| 17 | `star_chart_south`         | Southern Star Chart          | Key item    | `library`                 | Yes      | Celestial puzzle half |
| 18 | `gryffindor_token`         | Gryffindor's Token           | Quest item  | `gryffindor_vault`        | Yes      | Founder artifact (sword emblem) |
| 19 | `ravenclaw_token`          | Ravenclaw's Token            | Quest item  | `ravenclaw_vault`         | Yes      | Founder artifact (diadem emblem) |
| 20 | `hufflepuff_token`         | Hufflepuff's Token           | Quest item  | `hufflepuff_vault`        | Yes      | Founder artifact (cup emblem) |
| 21 | `slytherin_token`          | Slytherin's Token            | Quest item  | `slytherin_vault`         | Yes      | Founder artifact (locket emblem) |
| 22 | `golden_locket`            | Golden Locket                | Key/Choice  | `loyalty_passage`         | Yes      | Loyalty puzzle item |
| 23 | `hufflepuff_charm`         | Hufflepuff's Charm           | Key item    | `wounded_stranger` (reward) | Yes   | Patience Garden seed |
| 24 | `serpent_key`              | Serpent Key                  | Key item    | `iron_chest` (deception room) | Yes | Unlocks Slytherin vault path |
| 25 | `founders_journal_page_1`  | Founder's Journal (Page 1)  | Lore        | `clock_tower_base` (puzzle reward) | Yes | Pedestal puzzle, lore |
| 26 | `founders_journal_page_2`  | Founder's Journal (Page 2)  | Lore        | `restricted_section`      | Yes      | Malachar backstory |
| 27 | `rusted_amulet`            | Rusted Amulet                | Lore/Key    | `lake_shore` (puzzle reward) | Yes   | Pedestal puzzle, ward hint |
| 28 | `galleons`                 | Galleons                     | Consumable  | Various rooms             | Yes      | Currency for Fred & George. Quantity: 10 |
| 29 | `magical_candy`            | Magical Candy                | Consumable  | Fred & George (trade)     | Yes      | Heals 10 HP. Quantity: 3 |
| 30 | `warming_charm_token`      | Warming Charm Token          | Key item    | Flitwick (via dialogue)   | Yes      | Opens Dobby's cold stores |
| 31 | `malachar_journal`         | Malachar's Journal           | Lore        | `malachar_gallery`        | Yes      | Full Malachar backstory, ward order hint |
| 32 | `gryffindor_crest`         | Gryffindor Crest             | Key item    | Ron (in guardian_hall, if rescued) | Yes | Pedestal puzzle |
| 33 | `logic_poem`               | The Logic Verse              | Scenery     | `logic_chamber`           | No       | Seven Bottles puzzle clue |
| 34 | `peruvian_darkness_powder` | Peruvian Darkness Powder     | Consumable  | Fred & George (trade)     | Yes      | Creates darkness; distracts Filch |
| 35 | `invisibility_cloak`       | Invisibility Cloak           | Tool        | `dumbledore_office`       | Yes      | Bypasses Filch, optional stealth |

### Container Items (non-takeable scenery)

| #  | Item ID               | Name                   | Location              | Locked | Key              | Contents |
|----|-----------------------|------------------------|-----------------------|--------|------------------|----------|
| 36 | `trophy_case`         | Trophy Case            | `trophy_room`         | Yes    | `prefect_badge`  | `gryffindor_map`, `slytherin_ring` |
| 37 | `ingredient_cabinet`  | Ingredient Cabinet     | `potions_classroom`   | No     | —                | `ashwinder_egg`, `flame_freezing_potion` |
| 38 | `cold_stores`         | Enchanted Cold Stores  | `kitchens`            | Yes    | `warming_charm_token` | Food items for Dobby quest |
| 39 | `iron_chest`          | Iron Chest             | `deception_room`      | No     | —                | `serpent_key` |
| 40 | `silver_chest`        | Silver Chest           | `deception_room`      | No     | —                | Trap (empty, damages player) |
| 41 | `gold_chest`          | Gold Chest             | `deception_room`      | No     | —                | Trap (fake key, damages player) |
| 42 | `token_alcove`        | Token Alcove           | `convergence_antechamber` | No | —               | Accepts four Founder Tokens |
| 43 | `offering_stone`      | Offering Stone         | `ambition_stair`      | No     | —                | Accepts any item (sacrifice puzzle) |

### Toggleable Items

| Item ID               | States         | Light Source | Notes |
|-----------------------|----------------|--------------|-------|
| `enchanted_lantern`   | off / on       | Yes          | Required for dark rooms (`fear_chamber`, `restricted_section`) |
| `clock_mechanism`     | jammed / running | No         | Fixed by wrench. Scenery, not takeable. |
| `ward_stone_red`      | inactive / active | No        | Ward puzzle |
| `ward_stone_blue`     | inactive / active | No        | Ward puzzle |
| `ward_stone_yellow`   | inactive / active | No        | Ward puzzle |
| `ward_stone_green`    | inactive / active | No        | Ward puzzle |

### Item Tag Assignments

Tags enable the interaction matrix (see Section 11).

| Tag           | Items |
|---------------|-------|
| `spell`       | `wand` |
| `potion`      | `healing_potion`, `flame_freezing_potion`, `revealer_potion` |
| `light_source`| `enchanted_lantern` |
| `food`        | `magical_candy` |
| `lore`        | `revealer_recipe`, `founders_journal_page_1`, `founders_journal_page_2`, `malachar_journal`, `gryffindor_map`, `star_chart_south` |
| `tool`        | `wrench`, `small_shovel` |
| `founder_artifact` | `gryffindor_token`, `ravenclaw_token`, `hufflepuff_token`, `slytherin_token` |
| `key`         | `prefect_badge`, `slytherin_ring`, `serpent_key`, `warming_charm_token` |
| `stealth`     | `invisibility_cloak`, `peruvian_darkness_powder` |
| `currency`    | `galleons` |

---

## 7. Multiple Endings

### Ending Summary

| Ending | Name                  | Required Flags                                                                 | Tone        | Score Bonus |
|--------|-----------------------|--------------------------------------------------------------------------------|-------------|-------------|
| A      | The Unity Ending      | `ron_rescued` + `loyalty_proven` + `stranger_healed` + `draco_allied` + `stone_sealed_unity` | Triumphant | +50 |
| B      | The Sacrifice Ending  | `stone_sealed_sacrifice`                                                       | Bittersweet | +30 |
| C      | The Rival's Redemption| `draco_allied` + `stone_sealed_rival`                                          | Hopeful     | +25 |
| D      | The Compromise        | `stone_sealed_partial`                                                         | Somber      | +10 |
| E      | The Fall              | `stone_corrupted`                                                              | Tragic      | +0  |

> **Note**: Score bonuses from endings are additive to puzzle/quest scores but are capped by `max_score = 500`. The bonus rewards the best ending paths while keeping the maximum achievable.

---

### Ending A: The Unity Ending (Best)

**Win Flag**: `stone_sealed_unity`

**Requirements**: The player must have demonstrated all four Founder virtues through their choices:
- **Courage**: Rescued Ron in the Gryffindor Trial (`ron_rescued`)
- **Loyalty**: Healed the stranger AND returned the locket (`stranger_healed`, `loyalty_proven`)
- **Wisdom**: Combined charts with Hermione (`charts_combined`)
- **Cunning/Empathy**: Allied with Draco in the Slytherin Trial (`draco_allied`)

**What Happens**: In the Convergence Chamber, Harry channels all four tokens simultaneously. The combined virtue magic of the Founders overwhelms Malachar's curse. The Stone is purged and permanently re-sealed. Hogwarts' wards strengthen beyond their original power. Draco and Harry shake hands — not friends, but no longer enemies.

**Win Text**:
> "The four tokens blaze with light — gold, blue, yellow, green — and the Convergence Stone sings. Malachar's curse shatters like black glass, its shards dissolving into nothing. The castle shudders once, twice, and then... stillness. A stillness that feels like safety.
>
> Dumbledore finds you in the Convergence Chamber an hour later, the wards humming with renewed strength. 'You did what the Founders intended,' he says quietly. 'Not with power, but with unity.'
>
> Draco catches your eye across the Great Hall that evening. He doesn't smile. But he nods. And somehow, that is enough."

---

### Ending B: The Sacrifice Ending

**Win Flag**: `stone_sealed_sacrifice`

**Requirements**: The player reaches the Convergence Chamber and chooses to channel their own magic directly into the Stone. This requires at least two cooperation flags (partial virtue) but not all four.

**What Happens**: Harry touches the Stone and pours his magic into it. The curse is sealed, but Harry's magical ability is permanently burned out. He survives but can no longer cast spells. The wards hold. Hogwarts is saved at personal cost.

**Win Text**:
> "You press your hand to the Convergence Stone and push. Everything you are — every spell you've ever cast, every magical instinct you've ever trusted — flows out through your palm and into the crystal. The curse screams. And then it stops.
>
> The Stone pulses with clean, steady light. The wards reform. Hogwarts is safe.
>
> You try to cast Lumos that evening. Nothing happens. Hermione holds your hand and says nothing. Ron tells you that you're still the bravest person he knows, magic or not.
>
> Some things are worth more than power."

---

### Ending C: The Rival's Redemption

**Win Flag**: `stone_sealed_rival`

**Requirements**: `draco_allied` is set, but the player lacks the full set of cooperation flags for the Unity Ending. Draco and Harry work together to contain (not purge) the curse.

**What Happens**: Draco and Harry channel their magic together. The curse is contained but not destroyed — it will need tending. Draco volunteers to stay and maintain the seal, finding purpose in protecting the school his ancestors helped build.

**Win Text**:
> "'Together, Potter. On three.'
>
> You've never cast a spell in tandem with Draco Malfoy before. It should feel wrong. It doesn't. His magic is precise where yours is forceful. The curse buckles under the combined pressure, retreating into the deepest layer of the Stone.
>
> 'It'll hold,' Draco says, breathing hard. 'But someone will need to reinforce the seal. Regularly.'
>
> 'You're volunteering?'
>
> 'Someone has to. And you've got better things to do than babysit a rock.' He almost smiles. Almost."

---

### Ending D: The Compromise

**Win Flag**: `stone_sealed_partial`

**Requirements**: Default ending when the player reaches the Convergence Chamber without enough cooperation flags for any other path and is not in a failure state.

**What Happens**: Harry seals the Stone alone, but the seal is imperfect. The curse is weakened but not destroyed. Hogwarts survives, but the wards are permanently diminished. The castle will never be quite as safe as it was.

**Win Text**:
> "You cast the sealing charm alone. It holds — barely. The curse retreats but doesn't break. The Stone's light is dimmer than it should be, flickering at the edges.
>
> 'It's not perfect,' Dumbledore says, examining the seal. 'The wards will hold for years, perhaps decades. But Hogwarts will need protectors who remember what happened here.'
>
> You look at Ron and Hermione. They look back. That, at least, hasn't changed."

---

### Ending E: The Fall

**Lose Flag**: `stone_corrupted`

**Requirements**: The player arrives at the Convergence Chamber with HP below 20, OR has set the `malachar_awakened` flag (triggered by making certain very destructive choices — abandoning Ron AND keeping the locket AND allying with Draco for selfish reasons).

**What Happens**: Malachar's curse overwhelms the Stone. The wards shatter. Hogwarts is left unprotected.

**Lose Text**:
> "The Convergence Stone cracks. A sound like a thousand windows breaking fills the chamber, and the air turns cold — colder than any winter you've felt. The curse spreads through the cracks like ink through water.
>
> You feel the wards fall. Not gradually, but all at once, like a held breath released. The castle groans. Somewhere above, you hear shouting.
>
> Dumbledore's Patronus finds you in the dark. 'Get out,' it says. 'Get everyone out.'
>
> Hogwarts endures. It has endured for a thousand years. But its magic — the magic the Founders wove into every stone — is gone. What remains is just a building. A ruin on a Scottish hillside, open to whatever darkness comes next."

---

## 8. Scoring System

### Score Budget: 500 points

| Category                    | Points | % of Total | Notes |
|-----------------------------|--------|------------|-------|
| Required puzzles (15)       | 340    | 68%        | Critical path |
| Optional puzzles (3)        | 35     | 7%         | Curiosity rewards |
| Side quests (5)             | 50     | 10%        | Exploration rewards |
| Moral choices               | 25     | 5%         | Encouraging virtuous play |
| Best ending bonus           | 50     | 10%        | Only achievable via Unity Ending |
| **Total**                   | **500**| **100%**   | |

### Required Puzzle Score Breakdown

| Puzzle                     | Points | Cumulative |
|----------------------------|--------|------------|
| Gargoyle Password          | 10     | 10         |
| Restricted Section Access  | 15     | 25         |
| Trophy Compartment         | 15     | 40         |
| Revealer Potion            | 20     | 60         |
| Boggart Confrontation      | 25     | 85         |
| Bridge Crossing            | 20     | 105        |
| Guardian Rescue (Ron)      | 20     | 125        |
| Eagle's Riddle             | 15     | 140        |
| Three Pedestals            | 25     | 165        |
| Seven Bottles              | 30     | 195        |
| Celestial Alignment        | 20     | 215        |
| Stranger Healing           | 20     | 235        |
| Patience Garden            | 25     | 260        |
| Loyalty Gift               | 15     | 275        |
| Serpent Door               | 15     | 290        |
| Room of Deception          | 30     | 320        |
| Ambition Sacrifice         | 15     | 335        |
| Ward Stabilization         | 30     | 365        |
| Token Placement            | 25     | 390        |
| Convergence Seal           | 35     | 425        |

> **Note**: The table above shows 20 puzzles rather than 15 because some are choice-based and may award 0 points depending on path. The effective minimum critical-path score is approximately 340.

### Optional Puzzle Scores

| Puzzle                     | Points |
|----------------------------|--------|
| Jammed Clock               | 15     |
| Into the Forest            | 10     |
| Buried Artifact            | 10     |

### Side Quest Scores

| Quest                      | Points |
|----------------------------|--------|
| Dobby's Cold Stores        | 10     |
| The Nargle Hunt            | 10     |
| Malachar's History         | 10     |
| Fred & George's Trade      | 10     |
| The Founder's Journal      | 10     |

### Moral Choice Scores

| Choice                     | Points |
|----------------------------|--------|
| Rescuing Ron               | +5     |
| Healing the stranger       | +5     |
| Returning the locket       | +5     |
| Allying with Draco         | +5     |
| Entering Stone Heart (Unity)| +5    |

### Score Curves

- **Minimum completable score** (critical path, no optional, no moral): ~340
- **Good playthrough** (critical path + some optional + some moral): ~420
- **Excellent playthrough** (critical path + all optional + all moral): ~475
- **Perfect score** (everything + Unity Ending): 500

---

## 9. Quest Structure

### Main Quest: The Founders' Trial

**ID**: `founders_trial`
**Type**: `main`
**Auto-discovered**: Yes (no `discovery_flag`)
**Score**: 0 (component puzzles carry all the score)

**Description**: "The Convergence Stone has been corrupted. Complete the four Founders' Trials and re-seal the Stone before Hogwarts' wards fail completely."

**Objectives**:

| #  | Description                               | Completion Flag            | Optional |
|----|-------------------------------------------|----------------------------|----------|
| 1  | Speak with Dumbledore about the crisis     | `has_main_quest`           | No       |
| 2  | Access the Restricted Section for research | `restricted_unlocked`      | No       |
| 3  | Complete the Gryffindor Trial              | `trial_gryffindor_complete`| No       |
| 4  | Complete the Ravenclaw Trial               | `trial_ravenclaw_complete` | No       |
| 5  | Complete the Hufflepuff Trial              | `trial_hufflepuff_complete`| No       |
| 6  | Complete the Slytherin Trial               | `trial_slytherin_complete` | No       |
| 7  | Stabilize the ward stones in the Depths    | `wards_stabilized`         | No       |
| 8  | Place the four Founder Tokens              | `tokens_placed`            | No       |
| 9  | Seal the Convergence Stone                 | `stone_sealed`             | No       |

> **Note**: `stone_sealed` is a meta-flag set by any of the sealing paths (unity, sacrifice, rival, partial). The main quest completes regardless of which ending is achieved.

---

### Side Quest 1: Dobby's Cold Stores

**ID**: `dobby_cold_stores`
**Type**: `side`
**Discovery Flag**: `dobby_quest_discovered` (set when talking to Dobby)
**Completion Flag**: `dobby_helped`
**Score**: 10

**Description**: "Dobby needs help opening the enchanted cold stores in the kitchens."

**Objectives**:

| # | Description                                | Completion Flag        | Optional |
|---|---------------------------------------------|------------------------|----------|
| 1 | Get a Warming Charm Token from Flitwick     | `has_warming_token`    | No       |
| 2 | Use the token on the cold stores            | `cold_stores_opened`   | No       |

**Reward**: Dobby reveals the Hufflepuff Trial entrance. Food items for the stranger healing puzzle.

---

### Side Quest 2: The Nargle Hunt

**ID**: `nargle_hunt`
**Type**: `side`
**Discovery Flag**: `nargle_quest_discovered` (set via Luna dialogue)
**Completion Flag**: `nargles_found`
**Score**: 10

**Description**: "Luna believes Wrackspurts are infesting the castle. Help her find evidence."

**Objectives**:

| # | Description                                | Completion Flag          | Optional |
|---|--------------------------------------------|--------------------------|----------|
| 1 | Examine the strange shimmer in the corridor | `shimmer_examined`       | No       |
| 2 | Report findings to Luna                     | `nargles_found`          | No       |

**Reward**: Luna gives the player a pair of `spectrespecs` — a cosmetic/lore item. More importantly, the quest dialogue from Luna contains the riddle answer for the Eagle Doorknock puzzle.

---

### Side Quest 3: Malachar's History

**ID**: `malachar_history`
**Type**: `side`
**Discovery Flag**: `malachar_quest_discovered` (set when reading `founders_journal_page_2` in the Restricted Section)
**Completion Flag**: `malachar_history_complete`
**Score**: 10

**Description**: "Piece together the history of Malachar the Undying and understand his curse."

**Objectives**:

| # | Description                                | Completion Flag            | Optional |
|---|---------------------------------------------|----------------------------|----------|
| 1 | Read the Founder's Journal in the Restricted Section | `restricted_lore_read` | No   |
| 2 | Find Malachar's Journal in the Depths       | `malachar_journal_read`   | No       |
| 3 | Ask Dumbledore about Malachar               | `dumbledore_malachar_info`| Yes (bonus) |

**Reward**: Full understanding of the backstory. The journal contains the ward activation order (hint for Puzzle 21).

---

### Side Quest 4: Fred and George's Trade

**ID**: `twins_trade`
**Type**: `side`
**Discovery Flag**: `twins_quest_discovered` (set when first talking to Fred & George)
**Completion Flag**: `twins_trade_complete`
**Score**: 10

**Description**: "Fred and George have useful supplies. Find enough Galleons to trade with them."

**Objectives**:

| # | Description                              | Completion Flag           | Optional |
|---|------------------------------------------|---------------------------|----------|
| 1 | Collect at least 5 Galleons              | `has_enough_galleons`     | No       |
| 2 | Trade with Fred and George               | `twins_trade_complete`    | No       |

**Reward**: `magical_candy` (x3), `peruvian_darkness_powder`. The candy serves as an alternate solution for the Wounded Stranger puzzle.

---

### Side Quest 5: The Founder's Journal

**ID**: `founders_journal`
**Type**: `side`
**Discovery Flag**: `journal_quest_discovered` (set when finding `founders_journal_page_1` from the clock puzzle)
**Completion Flag**: `journal_complete`
**Score**: 10

**Description**: "Fragments of a journal written by one of the Founders are scattered through the castle. Collect them all."

**Objectives**:

| # | Description                              | Completion Flag              | Optional |
|---|------------------------------------------|------------------------------|----------|
| 1 | Find Journal Page 1 (Clock Tower)        | `journal_page_1_found`       | No       |
| 2 | Find Journal Page 2 (Restricted Section) | `journal_page_2_found`       | No       |
| 3 | Find Journal Page 3 (Malachar's Gallery) | `journal_page_3_found`       | Yes (bonus) |

**Reward**: Full Founder lore. The complete journal provides the ward activation sequence hint.

---

## 10. World Aliveness — Triggers and Events

### Atmospheric Room Entry Triggers

These fire `once` on first entry to set the tone.

| Trigger ID                   | Room                    | Message | One-Shot |
|------------------------------|-------------------------|---------|----------|
| `great_hall_arrival`         | `great_hall`            | "The enchanted ceiling churns with storm clouds that have no business being indoors. The candles flicker in unison, as if the castle itself is breathing." | Yes |
| `entrance_hall_shift`        | `entrance_hall`         | "As you step into the Entrance Hall, the staircase to your left groans and shifts three feet to the right. The portraits gasp in their frames." | Yes |
| `library_whispers`           | `library`               | "The books are restless. You can hear pages turning by themselves, deep in the stacks. Hermione doesn't seem to find this unusual." | Yes |
| `dungeon_cold`               | `dungeon_stairs`        | "The temperature drops sharply as you descend. Your breath mists. Something in the stones hums at a frequency you can feel in your teeth." | Yes |
| `courtyard_sky`              | `courtyard`             | "The sky above the courtyard is the wrong color — a faint amber, like parchment held up to a lamp. The sundial's shadow points in a direction that doesn't correspond to any compass point." | Yes |
| `forest_edge_sound`          | `forest_edge`           | "The Forbidden Forest is louder than usual. Not with animal sounds — with whispers, as if the trees are discussing something amongst themselves." | Yes |
| `ancient_passage_transition` | `ancient_passage`       | "The stonework changes abruptly. Hogwarts' neat masonry gives way to rough-hewn rock, ancient beyond reckoning. The air tastes of copper and old magic. You are now beneath the castle's foundations, in a place the Founders built before Hogwarts existed." | Yes |
| `convergence_approach`       | `convergence_chamber`   | "The chamber is vast and circular. At its center, the Convergence Stone floats three feet above a basalt pedestal, veined with pulsing black corruption. The air crackles. Every hair on your body stands on end." | Yes |

### Story Progression Triggers

These fire when specific flags are set, changing the world state.

| Trigger ID                    | Event Type   | Event Data / Preconditions              | Effects | One-Shot |
|-------------------------------|--------------|-----------------------------------------|---------|----------|
| `trial_gryffindor_done`       | `flag_set`   | `trial_gryffindor_complete`             | `print("The castle shudders. In the Great Hall, the Gryffindor hourglass fills with rubies — but the rubies glow an unsettling crimson, as if the castle is both grateful and in pain.")`, `change_description(great_hall, ...)` | Yes |
| `trial_ravenclaw_done`        | `flag_set`   | `trial_ravenclaw_complete`              | `print("A wave of cold clarity passes through the corridors. For a moment, every book in the library opens to the same page — then slams shut.")`, `change_description(library, ...)` | Yes |
| `trial_hufflepuff_done`       | `flag_set`   | `trial_hufflepuff_complete`             | `print("Warmth spreads through the lower floors. The kitchen fires burn brighter. Dobby whispers: 'The castle is thanking someone, sir.'")` | Yes |
| `trial_slytherin_done`        | `flag_set`   | `trial_slytherin_complete`              | `print("The dungeons flood with green light for an instant, then go dark. When the torches relight, the Slytherin serpent on the dungeon wall has opened its mouth wider, as if screaming — or laughing.")` | Yes |
| `all_trials_complete`         | `flag_set`   | requires all four trial flags           | `reveal_exit(dungeon_stairs_down)` (to `ancient_passage`), `print("The floor beneath your feet vibrates. Deep in the castle, something ancient stirs — the path to the Depths is open.")` | Yes |
| `ron_moved_to_trial`          | `room_enter` | player enters `gryffindor_antechamber`  | `move_npc(ron, guardian_hall)`, `print("Somewhere ahead, you hear Ron's voice: 'Harry? Is that you? I found another way in, but — something went wrong!'")` | Yes |
| `hermione_moved_to_trial`     | `room_enter` | player enters `riddle_hall`             | `move_npc(hermione, celestial_room)` | Yes |
| `draco_appears`               | `room_enter` | player enters `serpent_hall`            | `move_npc(draco, serpent_hall)` (if not already there) | Yes |

### Peeves Mischief Triggers

Peeves appears in various rooms at specific story moments to add chaos.

| Trigger ID              | Event Type    | Condition                          | Effect |
|-------------------------|---------------|------------------------------------|--------|
| `peeves_corridor`       | `room_enter`  | player enters `corridor_east`, after `has_main_quest` | `print("CRASH! Peeves swoops down from the ceiling, cackling. 'Ickle students playing heroes! Peeves knows a secret — but Peeves won't tell!' He blows a raspberry and vanishes through the wall.")`, `move_npc(peeves, corridor_west)` |
| `peeves_steals`         | `room_enter`  | player enters `corridor_west`, `npc_in_room(peeves, corridor_west)` | `print("Peeves grabs at your pockets! 'Give Peeves something shiny!' He snatches a Galleon and throws it down the corridor.")`, `consume_quantity(galleons, 1)` |
| `peeves_scared`         | `flag_set`    | `baron_name_known`                 | `print("At the mention of the Bloody Baron, Peeves goes pale — well, paler — and zooms away without another word.")`, `remove_npc(peeves)` |

### Environmental Change Triggers

The castle changes as trials are completed, reflecting the ward instability.

| Trigger ID               | Event Type   | Condition                        | Effect |
|--------------------------|--------------|----------------------------------|--------|
| `corridor_shift_1`       | `flag_set`   | `trial_gryffindor_complete`      | `change_description(corridor_east, "The corridor has changed since you were last here. The suits of armor have rearranged themselves, and a door that was on the left is now on the right.")` |
| `corridor_shift_2`       | `flag_set`   | `trial_ravenclaw_complete`       | `change_description(corridor_west, "The west corridor feels narrower than before. The ceiling is lower. One of the torches burns blue instead of orange.")` |
| `staircase_shift`        | `flag_set`   | two or more trials complete      | `change_description(grand_staircase, "The staircases have abandoned all pretense of order. They swing in wide arcs, connecting floors that shouldn't connect. You can see the seventh floor from here — the staircase is, for once, cooperating.")` |

### Dialogue Node Triggers

Fire when specific dialogue nodes are visited, creating cascading effects.

| Trigger ID                | Event Type        | Event Data                          | Effect |
|---------------------------|-------------------|-------------------------------------|--------|
| `dumbledore_quest_given`  | `dialogue_node`   | Dumbledore's quest briefing node    | `discover_quest(founders_trial)`, `set_flag(has_main_quest)`, `spawn_item(enchanted_lantern, dumbledore_office)`, `spawn_item(permission_slip, dumbledore_office)` |
| `grey_lady_reveal`        | `dialogue_node`   | Grey Lady's trial clue node         | `reveal_exit(library_east)` (to `ravenclaw_antechamber`), `set_flag(ravenclaw_entrance_known)` |

---

## 11. Interaction Matrix

The interaction matrix provides fallback responses for `use <item> on <target>` combinations not covered by specific DSL commands. These are tag-based: the item's tags and the target's category determine the response.

### Matrix Entries

| Item Tag           | Target Category | Response                                                                                      | Consumes | Score | Flag Set | Additional Effects |
|--------------------|-----------------|-----------------------------------------------------------------------------------------------|----------|-------|----------|-------------------|
| `spell`            | `character`     | "You point your wand at {target}. They raise an eyebrow. 'I'd rather you didn't, Potter.'"   | No       | 0     | —        | — |
| `spell`            | `ghost`         | "The spell passes through {target} without effect. Being dead has its advantages."            | No       | 0     | —        | — |
| `spell`            | `furniture`     | "Your spell strikes {target}. Sparks fly, but nothing useful happens."                        | No       | 0     | —        | — |
| `spell`            | `door`          | "You try a spell on {target}. The door resists — it's warded against casual magic."           | No       | 0     | —        | — |
| `potion`           | `character`     | "You offer the potion to {target}. They decline politely — or not so politely."               | No       | 0     | —        | — |
| `potion`           | `ghost`         | "You try to give the potion to {target}, but it passes through their translucent hand."       | No       | 0     | —        | — |
| `potion`           | `furniture`     | "You pour the potion on {target}. It sizzles briefly and evaporates. What a waste."           | Yes (1)  | 0     | —        | — |
| `food`             | `character`     | "You offer food to {target}. 'Not right now, thanks,' they say."                              | No       | 0     | —        | — |
| `food`             | `ghost`         | "You hold the food out to {target}. They stare at it with transparent longing. 'I miss eating,' they sigh." | No | 0 | — | — |
| `tool`             | `character`     | "You brandish {item} at {target}. They look at you with concern."                             | No       | 0     | —        | — |
| `tool`             | `furniture`     | "You try using {item} on {target}. It doesn't seem to accomplish anything useful."            | No       | 0     | —        | — |
| `key`              | `character`     | "You show the key to {target}. They don't seem interested."                                   | No       | 0     | —        | — |
| `key`              | `furniture`     | "You try {item} on {target}. It doesn't fit — this isn't the right lock."                     | No       | 0     | —        | — |
| `lore`             | `character`     | "You show {item} to {target}. They glance at it briefly. 'Interesting,' they say, noncommittally." | No | 0 | — | — |
| `founder_artifact` | `character`     | "{target} stares at the {item}. 'Where did you find that?' they whisper. 'That's Founder magic.'" | No | 0 | — | — |
| `founder_artifact` | `furniture`     | "You place the {item} near {target}. It hums softly, as if recognizing something, but nothing else happens." | No | 0 | — | — |
| `stealth`          | `character`     | "Using {item} near {target} seems unnecessary — they can already see you."                    | No       | 0     | —        | — |
| `currency`         | `character`     | "You offer Galleons to {target}. 'I'm not for sale,' they say."                               | No       | 0     | —        | — |
| `light_source`     | `character`     | "You shine the lantern at {target}. They squint. 'Do you mind?'"                              | No       | 0     | —        | — |

### Design Rationale

The matrix is deliberately conservative. It provides a characterful "nothing useful happens" for every reasonable item-on-target combination, preventing the flat engine default of "I don't understand that." Every response is in-world and in-character. The matrix does not award score or set flags — it exists purely to make the world feel responsive even when the player is experimenting.

Specific, meaningful interactions (using the healing potion on Ron, using the revealer potion on the dungeon wall) are handled by DSL commands, which take priority over the matrix.

---

## 12. Win and Lose Conditions

### Win Conditions

The game defines multiple win condition flag sets, one per ending:

```
win_conditions: [stone_sealed]
```

The `stone_sealed` flag is a meta-flag set by any of the following triggers:
- `stone_sealed_unity` -> sets `stone_sealed`
- `stone_sealed_sacrifice` -> sets `stone_sealed`
- `stone_sealed_rival` -> sets `stone_sealed`
- `stone_sealed_partial` -> sets `stone_sealed`

Each sealing flag triggers the corresponding ending text. The `stone_sealed` flag triggers the generic win condition check, which then branches to the appropriate `win_text` based on which specific sealing flag is set.

**Implementation Note**: Since the engine supports only a single `win_text`, the ending-specific text must be delivered via triggers that fire on the specific sealing flags (printing the ending text) before the generic `stone_sealed` flag triggers the win condition. The generic `win_text` serves as the score summary frame.

```
win_text: "Your quest is complete. The Convergence Stone is sealed. Hogwarts endures."
```

### Lose Conditions

```
lose_conditions: [player_died, stone_corrupted]
```

| Flag              | Trigger                                                          |
|-------------------|------------------------------------------------------------------|
| `player_died`     | Player HP reaches 0 (automatic engine behavior)                 |
| `stone_corrupted` | Player reaches `convergence_chamber` in a failure state (HP < 20 AND specific anti-virtue flags set) |

```
lose_text: "The wards have fallen. Hogwarts' magic is no more."
```

### Death Avoidance Design

The game follows the engine's no-lose design preference. HP damage occurs only from:
1. Opening the wrong chest in the Deception Room (-15 or -20)
2. Crossing the Bridge of Flames without protection (-40)
3. Peeves stealing a Galleon (resource loss, not HP)

None of these are lethal from full HP (100). The player can only die by repeatedly making harmful choices without healing. Healing potions are available in multiple locations.

The `stone_corrupted` flag requires a very specific combination of anti-virtue choices. A normal playthrough — even a careless one — will not trigger it. It is the "you deliberately tried to fail" ending.

---

## 13. Onboarding Flow

### First Five Minutes

The player starts in the Great Hall. The room description establishes the setting and tone. The enchanted ceiling is visibly disturbed.

**Beat 1 — Look (0-30 seconds)**:
- The room description mentions NPCs (Ron, McGonagall), items (the player's wand, which is in inventory), and exits.
- The player naturally types `look` or reads the description.
- **Success guaranteed**: Looking always works.

**Beat 2 — Talk (30-60 seconds)**:
- McGonagall and Ron are present. The player talks to one of them.
- McGonagall reveals the gargoyle password (first puzzle clue).
- Ron provides context and personality.
- **Success guaranteed**: Talking always works and always gives useful information.

**Beat 3 — Move (60-90 seconds)**:
- The player moves north to the Entrance Hall. Nick is here for atmosphere.
- The staircase shifting trigger fires (first evidence of the castle being "alive").
- **Success guaranteed**: Moving to an open exit always works.

**Beat 4 — Examine (90-120 seconds)**:
- In the Entrance Hall, examining the portraits or the staircase yields atmospheric clues.
- The player learns that `examine` reveals detail beyond what `look` shows.
- **Discovery moment**: Examine is where clues hide.

**Beat 5 — First Puzzle (2-5 minutes)**:
- The gargoyle blocks the way to Dumbledore's office. The player already has the password from McGonagall.
- Typing `say sherbet lemon` solves it. First puzzle success. First score increment.
- **Lesson learned**: NPCs give you information you need to progress.

### Onboarding Checklist

- [x] Core verbs introduced within 30 seconds: look (room description), inventory (wand is there), move (exits listed)
- [x] First success guaranteed: looking and moving require no puzzle solving
- [x] Each new mechanic introduced in safe context: talk to NPCs in the Great Hall (no stakes), examine items (no penalty)
- [x] Player discovers a mechanic through exploration: examining the gargoyle reveals it wants something; talking to McGonagall provides the answer
- [x] First session ends on a hook: Dumbledore's briefing sets the main quest, provides key items, and establishes urgency

### Verb Introduction Sequence

| Verb     | First Natural Use          | Room                |
|----------|----------------------------|---------------------|
| `look`   | Initial room display       | `great_hall`        |
| `talk`   | McGonagall/Ron present     | `great_hall`        |
| `move`   | Exits listed in description| `great_hall`        |
| `examine`| Portraits, staircase       | `entrance_hall`     |
| `take`   | Enchanted lantern          | `dumbledore_office` |
| `use`    | Permission slip on barrier | `library`           |
| `open`   | Trophy case                | `trophy_room`       |
| `combine`| Potion ingredients         | `potions_classroom` |

---

## 14. Flag Registry

### Core Story Flags

| Flag ID                       | Set By                         | Used By                                                    |
|-------------------------------|--------------------------------|------------------------------------------------------------|
| `has_main_quest`              | Dumbledore dialogue            | Unlocks trial-related dialogue, enables quest tracking     |
| `knows_gargoyle_password`     | McGonagall dialogue            | Gargoyle password puzzle precondition                      |
| `restricted_unlocked`         | Permission slip + Hermione     | Access to Restricted Section                               |
| `restricted_lore_read`        | Examining books in Restricted  | Unlocks Dumbledore's Malachar dialogue                     |
| `knows_revealer_recipe`       | Reading recipe in Restricted   | Enables potion combining                                   |
| `ravenclaw_entrance_known`    | Grey Lady dialogue             | Reveals Ravenclaw Trial entrance                           |
| `grey_lady_clue`              | Grey Lady dialogue             | Companion flag for entrance reveal                         |
| `dobby_helped`                | Completing Dobby's quest       | Reveals Hufflepuff Trial entrance                          |

### Trial Completion Flags

| Flag ID                       | Set By                         | Used By                                           |
|-------------------------------|--------------------------------|---------------------------------------------------|
| `trial_gryffindor_complete`   | Taking Gryffindor Token        | Main quest, progression triggers                  |
| `trial_ravenclaw_complete`    | Taking Ravenclaw Token         | Main quest, progression triggers                  |
| `trial_hufflepuff_complete`   | Taking Hufflepuff Token        | Main quest, progression triggers                  |
| `trial_slytherin_complete`    | Taking Slytherin Token         | Main quest, progression triggers                  |
| `all_trials_complete`         | Trigger (all four trial flags) | Unlocks the Depths                                |

### Moral Choice Flags

| Flag ID                       | Set By                          | Used By                                          |
|-------------------------------|---------------------------------|--------------------------------------------------|
| `ron_rescued`                 | Giving healing potion to Ron    | Unity Ending, score, NPC dialogue changes        |
| `ron_abandoned`               | Leaving Ron in guardian_hall    | Dialogue changes, blocks Unity Ending            |
| `stranger_healed`             | Healing spectral student        | Unity Ending, score                              |
| `loyalty_proven`              | Giving golden locket to ghost   | Unity Ending, score                              |
| `locket_kept`                 | Keeping the golden locket       | Alternate Hufflepuff vault access, blocks Unity  |
| `draco_allied`                | Cooperation dialogue with Draco | Rival's Redemption Ending, Unity Ending, score   |
| `draco_hostile`               | Confrontation with Draco        | Draco blocks path, no cooperation                |
| `draco_neutral`               | Dismissive response to Draco    | Draco absent from endgame                        |
| `sacrifice_made`              | Putting item on offering_stone  | Sacrifice Ending availability                    |

### Puzzle-State Flags

| Flag ID                       | Set By                          | Purpose                                          |
|-------------------------------|---------------------------------|--------------------------------------------------|
| `boggart_defeated`            | Casting riddikulus              | Fear chamber cleared                             |
| `flame_protected`             | Drinking flame-freezing potion  | Safe bridge crossing                             |
| `pedestals_complete`          | Placing all three items         | Unlocks riddle hall exit                         |
| `logic_potion_drunk`          | Drinking correct bottle         | Unlocks logic chamber exit                       |
| `charts_combined`             | Hermione dialogue               | Celestial room solved                            |
| `charm_planted`               | Using charm on seedling         | Patience garden step 1                           |
| `garden_bloomed`              | Returning after puzzle solved   | Patience garden complete                         |
| `knows_ward_order`            | Examining Malachar gallery mural| Ward stabilization puzzle precondition           |
| `ward_yellow_active`          | Activating yellow ward stone    | Ward sequence step 1                             |
| `ward_blue_active`            | Activating blue ward stone      | Ward sequence step 2                             |
| `ward_red_active`             | Activating red ward stone       | Ward sequence step 3                             |
| `ward_green_active`           | Activating green ward stone     | Ward sequence step 4                             |
| `wards_stabilized`            | Completing ward sequence        | Main quest objective                             |
| `tokens_placed`               | Placing all four tokens         | Opens Convergence Chamber                        |

### Ending Flags

| Flag ID                       | Set By                          | Purpose                                          |
|-------------------------------|---------------------------------|--------------------------------------------------|
| `stone_sealed`                | Any sealing path trigger        | Win condition                                    |
| `stone_sealed_unity`          | Unity seal command              | Best ending                                      |
| `stone_sealed_sacrifice`      | Touch stone command             | Sacrifice ending                                 |
| `stone_sealed_rival`          | Joint seal with Draco           | Rival's redemption ending                        |
| `stone_sealed_partial`        | Solo partial seal               | Compromise ending                                |
| `stone_corrupted`             | Failure state trigger           | Lose condition                                   |
| `player_died`                 | HP reaches 0                    | Lose condition (engine automatic)                |

### Side Quest Flags

| Flag ID                       | Set By                          | Purpose                                          |
|-------------------------------|---------------------------------|--------------------------------------------------|
| `dobby_quest_discovered`      | Dobby dialogue                  | Side quest discovery                             |
| `has_warming_token`           | Flitwick dialogue               | Dobby quest step 1                               |
| `cold_stores_opened`          | Using token on cold stores      | Dobby quest step 2                               |
| `nargle_quest_discovered`     | Luna dialogue                   | Side quest discovery                             |
| `shimmer_examined`            | Examining shimmer in corridor   | Nargle quest step 1                              |
| `nargles_found`               | Reporting to Luna               | Nargle quest completion                          |
| `malachar_quest_discovered`   | Reading founders journal page 2 | Side quest discovery                             |
| `malachar_journal_read`       | Examining Malachar's journal    | Malachar quest step 2                            |
| `twins_quest_discovered`      | Fred & George dialogue          | Side quest discovery                             |
| `has_enough_galleons`         | Galleon quantity check           | Twins trade step 1                               |
| `twins_trade_complete`        | Completing trade dialogue       | Twins trade completion                           |
| `journal_quest_discovered`    | Finding journal page 1          | Side quest discovery                             |
| `journal_page_1_found`        | Taking page 1                   | Journal quest step 1                             |
| `journal_page_2_found`        | Taking page 2                   | Journal quest step 2                             |
| `journal_page_3_found`        | Taking page 3 (in Depths)       | Journal quest step 3 (bonus)                     |
| `journal_complete`            | All pages found trigger         | Journal quest completion                         |

### NPC/World State Flags

| Flag ID                       | Set By                          | Purpose                                          |
|-------------------------------|---------------------------------|--------------------------------------------------|
| `ron_warned`                  | Ron dialogue                    | Flavor                                           |
| `hermione_lore_1`            | Hermione dialogue               | Tracks lore given                                |
| `snape_warned`                | Snape dialogue                  | Flavor                                           |
| `snape_potion_help`           | Snape dialogue (potion node)    | Flavor                                           |
| `hagrid_founder_info`         | Hagrid dialogue                 | Lore flag                                        |
| `hagrid_allows_forest`        | Hagrid dialogue + item shown    | Forest passage NPC lock                          |
| `nick_founder_lore`           | Nick dialogue                   | Lore flag                                        |
| `luna_riddle_hint`            | Luna dialogue                   | Eagle riddle clue                                |
| `baron_name_known`            | Bloody Baron dialogue           | Scares off Peeves                                |
| `knows_stone_lore`            | Dumbledore dialogue             | Tracks lore given                                |
| `dumbledore_malachar_info`    | Dumbledore dialogue             | Malachar backstory complete                      |
| `twins_hint`                  | Fred & George dialogue          | Secret passage hint                              |
| `myrtle_depths_hint`          | Myrtle dialogue                 | Depths lore                                      |
| `ravenclaw_lore`              | Grey Lady dialogue              | Ravenclaw backstory                              |

---

## 15. Balance Notes and Open Questions

### Open Design Questions

These are flagged for resolution during playtesting.

1. **Trial ordering**: Should the four trials be completable in any order, or should there be a soft recommended order? Current design allows any order, but the Ravenclaw Trial assumes the player has items from the Commons that require multiple prior puzzles. Consider gating the trial entrances in a suggested but not mandatory sequence.

2. **Healing economy**: Three healing potions (30 HP each) plus three magical candies (10 HP each) = 120 HP of healing available. Total possible damage: Bridge of Flames (40) + Deception Room traps (35) + Peeves theft (Galleons, not HP). Is 120 HP generous enough? `[PLACEHOLDER]` — test at target difficulty.

3. **Draco alliance requirements**: Currently requires `ron_rescued` as a prerequisite. Is this too restrictive? The design intent is that showing mercy in the Gryffindor Trial earns the credibility to propose cooperation in the Slytherin Trial. If playtesters find this connection unintuitive, consider alternate paths to the alliance.

4. **Patience Garden timing**: The current design requires solving "any puzzle" after planting the charm. Should it require a specific puzzle, or is "any puzzle" too vague? The intent is to force the player to leave and come back, simulating patience. A specific puzzle requirement might feel too arbitrary.

5. **Offering Stone sacrifice**: Which items should be valid? Currently "any takeable item." Should certain items be rejected (wand, quest-critical items)? The design intent is that the player chooses what to sacrifice, but losing the wand or a Founder Token could create a softlock. Solution: `accepts_items` whitelist that excludes critical items.

6. **Room count**: The design specifies 48 rooms plus a few optional/hidden rooms (Restricted Section, Dumbledore's Office, Forbidden Grove). Final count is approximately 50-52. This is within the 40-60 target but on the higher end. Monitor for pacing bloat during playtesting.

7. **Score calibration**: The current score budget allocates 500 points across required puzzles (340), optional puzzles (35), side quests (50), moral choices (25), and ending bonus (50). The 340-point critical path floor means a player who skips all optional content and makes no moral choices still gets 68% of the maximum score. Is this too generous? `[PLACEHOLDER]` — adjust after first playtest.

### Known Softlock Risks

The design has been reviewed for softlocks. The following areas require careful implementation:

1. **Healing Potion for Ron AND Stranger**: Both puzzles consume a healing potion charge. With 3 charges, the player can heal Ron, heal the stranger, and have one left for themselves. If the player uses all 3 on themselves before reaching the trials, they cannot get the full Unity Ending. **Mitigation**: Magical candy serves as an alternate for the stranger healing. Ron rescue has no alternate — this is by design (the sacrifice of resources IS the courage test).

2. **Offering Stone in Slytherin Trial**: If the player sacrifices a critical item, they may be unable to complete later puzzles. **Mitigation**: The Offering Stone's `accepts_items` whitelist must exclude `wand`, `enchanted_lantern`, and all four Founder Tokens.

3. **Revealer Potion is one-use**: If the player uses it on something other than the dungeon wall, it is wasted and the Slytherin Trial becomes inaccessible. **Mitigation**: The `use revealer_potion on {target}` command should only consume the potion when used on the correct target. On incorrect targets: "The potion fizzes briefly but finds nothing hidden here. It settles back into the bottle." (No consumption.)

4. **Grey Lady dialogue is one-path**: The Ravenclaw Trial entrance is only revealed through the Grey Lady. If the player never talks to her, the trial is inaccessible. **Mitigation**: Hermione also mentions the Grey Lady in her dialogue as a secondary hint. The Grey Lady's location (library) is on the critical path. Additionally, examining the eagle carving in the library (scenery item) provides the same exit reveal if the player has `has_main_quest`.

### Placeholder Values

All numerical values in this document are initial estimates. The following require playtesting:

| Variable                    | Current Value | Test Range | Notes |
|-----------------------------|---------------|------------|-------|
| Player starting HP          | 100           | 80-120     | Standard engine default |
| Healing potion restore      | 30            | 20-40      | Should heal ~1 hit worth of damage |
| Bridge of Flames damage     | 40            | 30-50      | Should be scary but not lethal |
| Deception Room trap damage  | 15-20         | 10-25      | Should sting but not threaten death |
| Healing potion quantity     | 3             | 2-4        | Must support Ron rescue + stranger + self |
| Magical candy heal          | 10            | 5-15       | Should be worse than potions but still useful |
| Galleon total available     | 10            | 8-15       | Must allow Fred & George trade with some margin |
| Fred & George trade cost    | 5             | 3-7        | Should require some collection effort |

---

*End of Game Design Document*
*Version 1.0 — 2026-03-21*
