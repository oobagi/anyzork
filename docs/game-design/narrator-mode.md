# Narrator Mode Design

An optional, read-only LLM layer that takes the engine's deterministic output and flavors it with atmospheric prose. The narrator sits between the engine and the display. It cannot change game state.

---

## 1. The Problem Narrator Mode Solves

The deterministic engine outputs functional text:

```
You are in the Dungeon Entrance.
A rusty door is to the north.
You see: brass lantern, waterlogged journal
Exits: north (locked) | south -- Cliff Path
```

This is accurate, parseable, and completely devoid of atmosphere. The engine is a state machine -- it does not know about mood, weather, character, or prose rhythm. That is the correct design: the engine's job is correctness, not artistry.

Narrator mode adds artistry without sacrificing correctness. The same engine output, narrated:

> The dungeon's mouth breathes cold air across your face. Before you, a door of rusted iron hangs on a single hinge, groaning softly in a draft you cannot trace. A brass lantern sits on a stone ledge, its glass fogged with age. Beside it, a journal swollen with seawater, its pages fused into a damp brick.
>
> **Exits:** north (locked) | south -- Cliff Path

The deterministic data (exits, items, lock state) remains visible and untouched. The narrator only flavors the descriptive prose.

---

## 2. Architecture

### 2.1 Pipeline Position

The narrator sits after the engine's output formatter and before the console display. It is the last transformation in the output pipeline.

```
Player Input
    |
    v
Game Engine (parse -> evaluate -> apply effects -> compose output)
    |
    v
Engine Output (structured: room name, description, items, exits, action result)
    |
    v
[Narrator Layer] (optional, read-only)
    |   Receives: engine output + narrator context
    |   Produces: prose string flavoring the description
    |   Cannot: mutate DB, add items/exits, change outcomes
    |
    v
Console Display (Rich-formatted terminal output)
```

### 2.2 Data Flow Per Turn

Each turn, the engine produces a structured output dict. When narrator mode is on, this dict is serialized and sent to the narrator along with context metadata. The narrator returns prose. The engine then displays the prose in place of (or alongside) the raw description, while keeping structural data (exits, item lists, NPC presence) rendered by the engine's own formatter.

```python
@dataclass
class EngineOutput:
    """Structured output from a single engine turn."""

    output_type: str  # "room", "action", "error", "system"

    # Room context (always populated when output_type == "room")
    room_id: str | None = None
    room_name: str | None = None
    room_description: str | None = None
    items_present: list[dict] | None = None  # [{name, description}, ...]
    npcs_present: list[dict] | None = None   # [{name, description}, ...]
    exits: list[dict] | None = None          # [{direction, destination, locked}, ...]

    # Action result (populated after take, open, use, DSL commands, etc.)
    action_verb: str | None = None
    action_messages: list[str] | None = None
    action_success: bool = True

    # Flags for what changed this turn
    room_changed: bool = False
    first_visit: bool = False
```

### 2.3 What the Narrator Receives

The narrator LLM call receives two inputs:

1. **System prompt** -- voice and constraint instructions (see section 6).
2. **User prompt** -- the serialized `EngineOutput` plus narrator context (theme, tone, room lore, recent action history).

The narrator returns a single prose string. The engine does not parse, validate, or transform this string -- it displays it directly.

### 2.4 Module Structure

```
anyzork/
  engine/
    narrator.py          # Narrator class, prompt assembly, provider call
    game.py              # GameEngine — calls Narrator after composing output
  generator/
    providers/
      base.py            # BaseProvider.generate_text() — already exists
      claude.py           # ClaudeProvider.generate_text() — already exists
      openai_provider.py  # OpenAIProvider.generate_text() — already exists
      gemini.py           # GeminiProvider.generate_text() — already exists
```

The `Narrator` class lives in `anyzork/engine/narrator.py`. It is instantiated by `GameEngine` when narrator mode is enabled. It holds a reference to a `BaseProvider` instance and builds prompts from engine output.

---

## 3. What Gets Narrated

Not every engine output should pass through the narrator. Some outputs are structural or mechanical and must remain untouched.

### 3.1 Narrated Outputs

| Output Type | When | What the Narrator Receives |
|---|---|---|
| Room description | On enter, on `look` | Full room description, items with prose, NPC descriptions |
| Action feedback | `take`, `drop`, `open`, `search`, `examine` | The action verb, the target, and the engine's result message |
| DSL command results | Custom command success/failure messages | The `print` effect messages from the DSL command |
| Movement blocked | Locked door, no exit | The lock message or "you can't go that way" |
| NPC default dialogue | `talk to` when no dialogue tree | The NPC's `default_dialogue` text |

### 3.2 Not Narrated

These outputs are displayed exactly as the engine produces them. The narrator never sees them.

| Output Type | Why It's Excluded |
|---|---|
| Inventory list | Mechanical -- player needs exact names, not prose |
| Score display | Numerical data, not narratable |
| Help text | UI reference, not fiction |
| Quest log | Structured checklist, needs to be scannable |
| Save/load messages | System messages outside the fiction |
| Dialogue trees (branching) | Player choices must be presented exactly as authored -- the narrator rewriting choice text would change meaning |
| Exit list | Structural -- player needs exact directions and lock states to make decisions |
| "You see:" item list | When items have no prose description, the bare name list is more useful than narrated guesses |
| Error messages | "I don't understand that" is a system message |

### 3.3 The Hybrid Display Rule

The narrator flavors the **prose body** of a room or action result. The **structural elements** -- exits, item lists, NPC presence indicators -- are always rendered by the engine's own formatter, below the narrated prose. This means a narrated room display looks like:

```
+--- The Dungeon Entrance ---+
| [narrated prose here]      |
+----------------------------+
Exits: north (locked) | south -- Cliff Path
You see: brass lantern, waterlogged journal
Present: Old Wizard
```

The panel body is narrated. The lines below the panel are engine-rendered and never touched by the narrator. The player always has accurate, scannable information to act on.

---

## 4. Context Management

The narrator needs context to write coherent, consistent prose. Too little context produces generic output. Too much context wastes tokens and increases latency.

### 4.1 Context Assembly

Each narrator call includes these context layers:

```python
@dataclass
class NarratorTurnContext:
    """Full context assembled for a single narrator call."""

    # Game identity (stable across the session)
    game_title: str
    theme: str        # e.g., "gothic horror"
    tone: str         # e.g., "dark"
    era: str          # e.g., "Victorian"
    setting: str      # one-paragraph world description
    vocabulary_hints: list[str]  # words that fit the tone

    # Room context (changes on room enter)
    room_name: str
    room_description: str      # the engine's raw description
    room_lore: str | None      # tier 1-2 lore associated with this room

    # Turn context (changes every turn)
    engine_output: EngineOutput
    recent_actions: list[str]  # last 3-5 action summaries for continuity

    # Token budget
    max_response_tokens: int = 512
```

### 4.2 Where the Context Comes From

| Field | Source | Retrieved How |
|---|---|---|
| `game_title` | `metadata.title` | `db.get_meta("title")` |
| `theme`, `tone`, `era`, `setting`, `vocabulary_hints` | `metadata.author_prompt` (JSON containing the concept dict) | `json.loads(db.get_meta("author_prompt"))["concept"]` |
| `room_name`, `room_description` | `rooms` table | `db.get_room(room_id)` |
| `room_lore` | `lore` table (when implemented) | Query lore by `location_id = room_id`, tiers 1 and 2 |
| `engine_output` | Constructed by the engine during turn processing | Passed directly to narrator |
| `recent_actions` | In-memory ring buffer on the `Narrator` instance | Appended each turn |

### 4.3 Session-Level Caching

The game identity fields (`game_title`, `theme`, `tone`, `era`, `setting`, `vocabulary_hints`) are read once when the narrator is initialized and cached for the session. They do not change during play.

### 4.4 Token Budget

The narrator prompt should fit comfortably in a small context window. Estimated sizes:

| Component | Approximate Tokens |
|---|---|
| System prompt (voice instructions) | ~200 |
| Game identity context | ~150 |
| Room context + lore | ~200 |
| Engine output (serialized) | ~100-300 |
| Recent actions (3-5 entries) | ~50-100 |
| **Total input** | **~700-950** |
| **Max response** | **512** |
| **Total per call** | **~1,200-1,500** |

This is small. Even the cheapest models handle this comfortably, and latency stays under 1-2 seconds for most providers.

### 4.5 Action History Ring Buffer

The `Narrator` instance maintains a fixed-size deque of recent action summaries. This gives the narrator short-term memory for prose continuity without growing the context unboundedly.

```python
from collections import deque

class Narrator:
    def __init__(self, ...):
        self._recent_actions: deque[str] = deque(maxlen=5)

    def _record_action(self, verb: str, target: str | None, result: str) -> None:
        summary = f"{verb} {target}: {result}" if target else f"{verb}: {result}"
        self._recent_actions.append(summary)
```

Example history buffer contents:

```
["take lantern: Taken.", "go north: Moved to Lighthouse Stairs.", "examine painting: A faded portrait of the lighthouse keeper."]
```

This is not persisted to the database. It resets on game restart. That is intentional -- the narrator's "memory" is ephemeral prose continuity, not game state.

---

## 5. Provider Integration

### 5.1 Reusing the Existing Provider System

The narrator calls `BaseProvider.generate_text()`, which already exists on all three providers (`ClaudeProvider`, `OpenAIProvider`, `GeminiProvider`). The method signature:

```python
# From anyzork/generator/providers/base.py
def generate_text(
    self,
    prompt: str,
    context: NarratorContext | None = None,
) -> str:
    ...
```

The `NarratorContext` dataclass is already defined:

```python
@dataclass(frozen=True)
class NarratorContext:
    theme: str = ""
    tone: str = ""
    room_lore: str = ""
    seed: int | None = None
    temperature: float = 0.9
    max_tokens: int = 2_048
```

This interface is sufficient. The narrator assembles a prompt string and a `NarratorContext`, calls `provider.generate_text()`, and gets back prose.

### 5.2 Provider Instantiation

The narrator needs its own provider instance. It uses the same `Config` as the generator, so it picks up `ANYZORK_PROVIDER` and `ANYZORK_API_KEY` automatically.

```python
# In narrator.py
from anyzork.config import Config
from anyzork.generator.providers import get_provider

class Narrator:
    def __init__(self, config: Config, db: GameDB) -> None:
        self._provider = get_provider(config)
        self._db = db
        # ... cache game identity from metadata ...
```

Future enhancement: allow a separate `ANYZORK_NARRATOR_PROVIDER` and `ANYZORK_NARRATOR_MODEL` so the narrator can use a cheaper/faster model than the generator. For v1, the narrator shares the same provider config.

### 5.3 Streaming vs. Non-Streaming

For v1, narrator calls are **non-streaming** (blocking). The engine waits for the full response before displaying anything.

Rationale: narrator responses are short (< 512 tokens). Streaming adds implementation complexity (async display, partial rendering, cursor management) for a response that takes 1-2 seconds. The user experience difference between "wait 1.5s then see everything" and "see tokens appear over 1.5s" is minimal for this length.

Future enhancement: streaming display where the narrated prose types out character-by-character while the structural data (exits, items) appears immediately below. This would require the engine to render the structural lines first, then stream the prose into the panel above. Deferred to a later version.

### 5.4 Latency Expectations

| Provider | Expected Latency (512 token response) |
|---|---|
| Claude (Haiku-class) | 0.5-1.5s |
| Claude (Sonnet-class) | 1.0-2.5s |
| OpenAI (GPT-4o-mini) | 0.5-1.5s |
| OpenAI (GPT-4o) | 1.0-3.0s |
| Gemini (Flash) | 0.3-1.0s |
| Gemini (Pro) | 1.0-2.5s |

For a text adventure, 1-2s latency per turn is acceptable. If the player finds it slow, they can disable narrator mode mid-game (see section 7).

---

## 6. Prompt Design

### 6.1 System Prompt

The system prompt establishes voice, constraints, and output format. It is constructed once per session (the game identity fields are stable) and reused for every turn.

```python
NARRATOR_SYSTEM_TEMPLATE = """\
You are the narrator of a text adventure game called "{title}".

Theme: {theme}
Tone: {tone}
Era: {era}
Setting: {setting}

Your role:
- Transform the engine's factual output into atmospheric prose that matches \
the game's tone.
- Describe exactly what the engine tells you. Do not add rooms, exits, items, \
NPCs, or information that are not present in the engine output.
- Do not mention items or exits by mechanical name (e.g., "brass_lantern"). Use \
their display names naturally in prose.
- Do not contradict the engine output. If the engine says a door is locked, \
describe it as locked. If the engine says you took the lantern, confirm it.
- Keep responses concise. Two to four sentences for room descriptions. One to \
two sentences for action results. Never write more than a short paragraph.
- Do not address the player as "you" in second person unless the game's tone \
calls for it. Match the narrative voice to the tone.
- Do not include mechanical information in your prose (score, HP, move count). \
That is displayed separately.
- Do not editorialize about the player's choices or suggest what they should do next.

Vocabulary preferences: {vocabulary_csv}

Respond with ONLY the narrated prose. No markdown, no headers, no meta-commentary.\
"""
```

### 6.2 User Prompt (Per-Turn)

The user prompt changes every turn. It contains the engine output and contextual information.

```python
NARRATOR_TURN_TEMPLATE = """\
Current room: {room_name}
Room description: {room_description}
{lore_block}
Engine output to narrate:
{engine_output_text}

Recent context:
{recent_actions_text}\
"""
```

### 6.3 Narration Types

The prompt varies slightly depending on what is being narrated:

**Room entry:**
```
Engine output to narrate:
TYPE: room_enter (first visit)
DESCRIPTION: A circular stone room. A spiral staircase leads up.
ITEMS PRESENT: brass lantern (on a stone ledge), waterlogged journal (on the floor)
NPCS PRESENT: none
```

**Action result:**
```
Engine output to narrate:
TYPE: action_result
ACTION: take brass lantern
RESULT: Taken.
CONTEXT: You are in the Base of the Lighthouse.
```

**Movement blocked:**
```
Engine output to narrate:
TYPE: movement_blocked
DIRECTION: north
REASON: The iron door is sealed shut. A heavy padlock holds it closed.
```

**DSL command result:**
```
Engine output to narrate:
TYPE: command_result
COMMAND: use rusty key on iron door
MESSAGES: ["The rusty key crumbles as the lock gives way. The door groans open."]
```

### 6.4 Voice Consistency

The narrator's voice is anchored by the `tone` and `vocabulary_hints` from the game concept. These are baked into the system prompt, so every call inherits the same voice.

The narrator has no memory between turns (no conversation history). Each call is independent. This prevents drift but means the narrator cannot build on its own previous prose. The `recent_actions` buffer provides enough continuity for coherent transitions ("Having just taken the lantern...") without carrying forward hallucinations.

### 6.5 What the Narrator Must Not Do

These constraints are enforced by prompt instruction, not by code. They represent the contract the narrator must honor:

1. **Do not invent items.** If the engine output lists a brass lantern and a journal, the narrator can describe only those items. It cannot mention a dusty tome, a flickering candle, or any object not in the engine output.

2. **Do not invent exits.** If the engine shows exits north and south, the narrator cannot mention "a passage to the east" or "a gap in the western wall."

3. **Do not change outcomes.** If the engine says "The door is locked," the narrator cannot describe it swinging open.

4. **Do not give gameplay hints.** The narrator does not say "Perhaps the rusty key would work here" unless the engine output explicitly contains that hint.

5. **Do not use Rich markup.** The narrator returns plain text. All styling is applied by the engine's display layer.

If the narrator violates these constraints, the consequences are cosmetic, not functional. The player sees inaccurate prose but the structural data (exits, items, lock states) displayed below the prose panel is always correct. The game remains playable.

---

## 7. Toggle and Configuration

### 7.1 Configuration Layers

Narrator mode is controlled at three levels, in order of precedence:

| Level | Mechanism | Scope |
|---|---|---|
| CLI flag | `anyzork play game.zork --narrator` | Per-session |
| Environment variable | `ANYZORK_NARRATOR=true` | Per-environment |
| In-game toggle | `narrator on` / `narrator off` command | Mid-session |

The `Config` class already has `narrator_enabled: bool = False`. The CLI flag and env var both set this field. The default is **off** -- narrator mode is opt-in.

### 7.2 CLI Flag

```python
@cli.command()
@click.argument("zork_file", type=click.Path(exists=True, path_type=Path))
@click.option("--narrator", is_flag=True, help="Enable narrator mode (requires API key).")
def play(zork_file: Path, narrator: bool) -> None:
    ...
```

### 7.3 In-Game Toggle

The engine registers `narrator on` and `narrator off` as built-in commands (alongside `look`, `inventory`, `help`, etc.).

```python
# In GameEngine.main_loop():
if verb == "narrator":
    if len(tokens) >= 2 and tokens[1] == "on":
        if self._narrator is None:
            self._init_narrator()
        if self._narrator is not None:
            self.console.print("Narrator mode enabled.", style=STYLE_SYSTEM)
        else:
            self.console.print(
                "Cannot enable narrator: no API key configured.",
                style=STYLE_SYSTEM,
            )
        continue
    elif len(tokens) >= 2 and tokens[1] == "off":
        self._narrator = None
        self.console.print("Narrator mode disabled.", style=STYLE_SYSTEM)
        continue
```

Toggling narrator mode mid-game does not cost a move. It is a UI preference, not a game action.

### 7.4 API Key Requirement

Narrator mode requires a valid API key for the configured provider. If the player enables narrator mode without an API key, the engine prints an error and stays in deterministic mode. The game never blocks or crashes due to missing narrator configuration.

### 7.5 Narrator State Display

The `help` command shows the current narrator status:

```
Narrator: ON (claude / claude-haiku-3)
```
or:
```
Narrator: OFF
```

---

## 8. Fallback Behavior

### 8.1 The Core Rule

If the narrator LLM call fails for any reason, the engine displays its original deterministic output. The game never blocks on narrator availability.

### 8.2 Failure Modes and Responses

| Failure | Response |
|---|---|
| Network error (connection refused, timeout) | Show deterministic output. Log warning. |
| Rate limit (429) | Show deterministic output. Log warning. No retry -- the player is waiting. |
| Provider error (500, malformed response) | Show deterministic output. Log warning. |
| API key invalid / expired | Show deterministic output. Print one-time notice: "Narrator unavailable -- falling back to engine output." Disable narrator for the rest of the session. |
| Empty response from LLM | Show deterministic output. Log warning. |

### 8.3 Timeout

The narrator call has a hard timeout of **5 seconds**. If the provider does not respond within 5 seconds, the call is cancelled and the deterministic output is shown. This is shorter than the provider's default timeout because the player is waiting interactively.

```python
class Narrator:
    TIMEOUT_SECONDS: float = 5.0
```

### 8.4 No Retry on Failure

Unlike generation (which retries passes), the narrator does **not** retry failed calls. Rationale: the player is waiting in real-time. A retry adds 2-5 more seconds of latency for a cosmetic feature. The deterministic output is always available as an immediate fallback.

### 8.5 Graceful Degradation Notice

On the first narrator failure in a session, the engine prints a dim notice:

```
(Narrator unavailable for this turn -- showing engine output.)
```

On subsequent failures, the notice is suppressed to avoid repetitive noise. If the narrator recovers (next call succeeds), it resumes silently.

---

## 9. Performance

### 9.1 Latency Budget

Every narrator call adds latency to every player turn. The target latency budget:

| Turn Type | Without Narrator | With Narrator (target) |
|---|---|---|
| Room enter | < 50ms | < 2s |
| Action (take, open, etc.) | < 50ms | < 2s |
| Movement blocked | < 50ms | < 1.5s |
| DSL command | < 50ms | < 2s |

2 seconds per turn is the upper bound for acceptable text adventure pacing. Beyond that, the experience feels sluggish.

### 9.2 Caching Strategy

Room descriptions on revisit can be cached. If the player returns to a room they have already visited and the room state has not changed (no new items, no items removed, no NPCs changed), the narrator can serve the cached prose.

```python
class Narrator:
    def __init__(self, ...):
        # Cache: room_id -> (state_hash, narrated_prose)
        self._room_cache: dict[str, tuple[str, str]] = {}

    def _cache_key(self, room_id: str, engine_output: EngineOutput) -> str:
        """Hash the engine output to detect room state changes."""
        import hashlib
        content = f"{room_id}:{engine_output.room_description}:{engine_output.items_present}:{engine_output.npcs_present}"
        return hashlib.md5(content.encode()).hexdigest()
```

Cache hit behavior: skip the LLM call entirely, return cached prose. Instant.

Cache invalidation: any change to the room's item list, NPC presence, or description (via `update_description` effect) invalidates the cache for that room. The hash comparison handles this automatically.

Cache scope: in-memory, per-session. Not persisted to the database. Cache is lost on game restart. This is acceptable -- the cache is a performance optimization, not a data store.

### 9.3 Skipping Narration for Short Outputs

Some engine outputs are too short to benefit from narration. "Taken." does not improve when narrated to "You reach down and take the lantern, its weight settling into your palm." The player pressed a button and wants confirmation, not prose.

Heuristic: if the engine output's total text content is under 20 characters, skip narration and display the raw output. This avoids LLM calls for trivial confirmations.

```python
MIN_NARRATION_LENGTH = 20  # characters

def _should_narrate(self, engine_output: EngineOutput) -> bool:
    """Decide whether this output is worth narrating."""
    if engine_output.output_type == "system":
        return False
    if engine_output.output_type == "room":
        return True  # always narrate room descriptions
    # For actions, only narrate if the message has substance
    total_text = " ".join(engine_output.action_messages or [])
    return len(total_text) >= MIN_NARRATION_LENGTH
```

This is a tunable threshold. Start conservative (narrate most things) and adjust based on playtest feedback.

### 9.4 Async Display (Future)

A future enhancement: display the structural data (exits, items, NPCs) immediately, then stream the narrated prose into the panel above. This removes perceived latency -- the player sees actionable information instantly and the prose fills in as a bonus.

This requires:
- Rich Live display or similar dynamic terminal rendering
- Streaming support in the provider (all three providers support streaming)
- Cursor management to insert prose above already-rendered lines

Deferred to a future version. For v1, the entire output (prose + structural) renders at once after the narrator call completes.

---

## 10. Schema and Storage

### 10.1 What Gets Persisted

Narrator mode is a display preference, not game state. Almost nothing about the narrator needs to persist in the `.zork` database.

**Persisted:**
- `narrator_enabled` preference -- stored in the `metadata` table (or a new `preferences` table) so the game remembers the player's choice across sessions.

**Not persisted:**
- Narrated prose text -- ephemeral, regenerated each time.
- Action history buffer -- ephemeral, resets on restart.
- Room prose cache -- ephemeral, rebuilt each session.

### 10.2 Metadata Extension

Add an optional `narrator_enabled` field to the metadata table. This is a player preference, not a game design field.

```sql
ALTER TABLE metadata ADD COLUMN narrator_enabled INTEGER NOT NULL DEFAULT 0;
```

On game start, if `narrator_enabled = 1` in the database and a valid API key is present, the narrator activates automatically. The player does not need to pass `--narrator` every time.

When the player toggles narrator mode in-game (`narrator on` / `narrator off`), the preference is written to this column.

### 10.3 No Concept Data Duplication

The narrator reads theme/tone/setting from `metadata.author_prompt`, which already contains the full concept dict (written by Pass 1). No new tables or columns are needed for narrator context -- the data already exists.

---

## 11. Implementation Plan

### Phase 1: Core Narrator (Minimum Viable)

**Files to create:**
- `anyzork/engine/narrator.py` -- the `Narrator` class

**Files to modify:**
- `anyzork/engine/game.py` -- integrate narrator calls into `display_room()` and action result display
- `anyzork/config.py` -- add `narrator_model` field (optional, defaults to the generation model)
- `anyzork/cli.py` -- add `--narrator` flag to the `play` command
- `anyzork/db/schema.py` -- add `narrator_enabled` column to metadata schema

**Implementation order:**

1. **`narrator.py` scaffold** -- `Narrator` class with `__init__`, `narrate_room()`, `narrate_action()`, prompt assembly, provider call, fallback on error.

2. **`game.py` integration** -- `GameEngine.__init__` accepts an optional `Narrator` instance. `display_room()` passes the room data through the narrator before rendering the panel body. Action result messages pass through `narrate_action()` before `console.print()`.

3. **CLI flag** -- `--narrator` flag on `play` command. When set, instantiate a `Narrator` and pass it to `GameEngine`.

4. **In-game toggle** -- `narrator on` / `narrator off` commands in the REPL loop.

5. **Fallback handling** -- wrap every narrator call in try/except, display deterministic output on failure.

### Phase 2: Polish

6. **Room cache** -- implement the hash-based room prose cache to avoid redundant LLM calls on revisits.

7. **Short output skip** -- implement the `MIN_NARRATION_LENGTH` heuristic.

8. **Preference persistence** -- write narrator toggle state to `metadata.narrator_enabled`. Read it on game start.

9. **Help text update** -- show narrator status in `help` output. Document `narrator on/off` commands.

### Phase 3: Future Enhancements (Deferred)

10. **Separate narrator model config** -- `ANYZORK_NARRATOR_MODEL` and `ANYZORK_NARRATOR_PROVIDER` for using a cheaper model.

11. **Streaming display** -- render structural data immediately, stream prose into the panel.

12. **Narrator voice presets** -- stored narrator system prompts per game (the generator could produce a custom narrator voice as part of the concept pass).

13. **Narrated dialogue** -- run NPC dialogue responses through the narrator for atmospheric flavor.

---

## 12. The `Narrator` Class (Code Sketch)

```python
"""Narrator — optional read-only LLM layer for atmospheric prose."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass

from anyzork.config import Config
from anyzork.db.schema import GameDB
from anyzork.generator.providers.base import BaseProvider, NarratorContext, ProviderError

logger = logging.getLogger(__name__)

MIN_NARRATION_LENGTH = 20
MAX_RECENT_ACTIONS = 5


@dataclass
class NarratorGameContext:
    """Cached game identity — read once, stable for the session."""
    title: str
    theme: str
    tone: str
    era: str
    setting: str
    vocabulary_hints: list[str]


class Narrator:
    """Read-only LLM layer that flavors engine output with prose."""

    TIMEOUT_SECONDS: float = 5.0

    def __init__(self, provider: BaseProvider, db: GameDB) -> None:
        self._provider = provider
        self._db = db
        self._recent_actions: deque[str] = deque(maxlen=MAX_RECENT_ACTIONS)
        self._room_cache: dict[str, tuple[str, str]] = {}
        self._failure_count: int = 0
        self._game_ctx = self._load_game_context()
        self._system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------ setup

    def _load_game_context(self) -> NarratorGameContext:
        meta = self._db.get_all_meta()
        title = meta.get("title", "Untitled") if meta else "Untitled"

        concept: dict = {}
        raw = self._db.get_meta("author_prompt")
        if raw:
            try:
                parsed = json.loads(raw)
                concept = parsed.get("concept", {})
            except (json.JSONDecodeError, TypeError):
                pass

        return NarratorGameContext(
            title=title,
            theme=concept.get("theme", ""),
            tone=concept.get("tone", ""),
            era=concept.get("era", ""),
            setting=concept.get("setting", ""),
            vocabulary_hints=concept.get("vocabulary_hints", []),
        )

    def _build_system_prompt(self) -> str:
        ctx = self._game_ctx
        vocab_csv = ", ".join(ctx.vocabulary_hints) if ctx.vocabulary_hints else "none"
        return (
            f'You are the narrator of a text adventure game called "{ctx.title}".\n\n'
            f"Theme: {ctx.theme}\nTone: {ctx.tone}\nEra: {ctx.era}\n"
            f"Setting: {ctx.setting}\n\n"
            "Your role:\n"
            "- Transform the engine's factual output into atmospheric prose "
            "that matches the game's tone.\n"
            "- Describe exactly what the engine tells you. Do not add rooms, "
            "exits, items, NPCs, or information not present in the engine output.\n"
            "- Do not contradict the engine output.\n"
            "- Keep responses concise: 2-4 sentences for rooms, 1-2 for actions.\n"
            "- Do not include mechanical information (score, HP, moves).\n"
            "- Do not suggest what the player should do next.\n\n"
            f"Vocabulary preferences: {vocab_csv}\n\n"
            "Respond with ONLY the narrated prose. No markdown, no headers."
        )

    # ---------------------------------------------------------------- public API

    def narrate_room(
        self, room_id: str, room_name: str, description: str,
        items: list[dict], npcs: list[dict], first_visit: bool,
    ) -> str | None:
        """Narrate a room description. Returns prose or None on failure."""
        cache_key = self._make_cache_key(room_id, description, items, npcs)
        cached = self._room_cache.get(room_id)
        if cached and cached[0] == cache_key:
            return cached[1]

        items_text = ", ".join(i["name"] for i in items) if items else "none"
        npcs_text = ", ".join(n["name"] for n in npcs) if npcs else "none"
        visit_label = "first visit" if first_visit else "revisit"

        prompt = (
            f"Current room: {room_name}\n"
            f"Room description: {description}\n"
            f"Visit type: {visit_label}\n"
            f"Items present: {items_text}\n"
            f"NPCs present: {npcs_text}\n\n"
            f"Recent context:\n{self._format_recent_actions()}"
        )

        prose = self._call_provider(prompt)
        if prose:
            self._room_cache[room_id] = (cache_key, prose)
        return prose

    def narrate_action(self, verb: str, target: str | None, messages: list[str]) -> str | None:
        """Narrate an action result. Returns prose or None on failure."""
        combined = " ".join(messages)
        if len(combined) < MIN_NARRATION_LENGTH:
            return None  # too short to narrate

        target_text = f" {target}" if target else ""
        prompt = (
            f"Action: {verb}{target_text}\n"
            f"Result: {combined}\n\n"
            f"Recent context:\n{self._format_recent_actions()}"
        )

        prose = self._call_provider(prompt)
        self._record_action(verb, target, combined)
        return prose

    def record_action(self, verb: str, target: str | None, result: str) -> None:
        """Record an action in the history buffer (called even when not narrating)."""
        self._record_action(verb, target, result)

    # --------------------------------------------------------------- internals

    def _call_provider(self, prompt: str) -> str | None:
        ctx = NarratorContext(
            theme=self._game_ctx.theme,
            tone=self._game_ctx.tone,
            temperature=0.9,
            max_tokens=512,
        )
        try:
            result = self._provider.generate_text(prompt, context=ctx)
            self._failure_count = 0
            return result.strip() if result else None
        except ProviderError as exc:
            self._failure_count += 1
            if self._failure_count == 1:
                logger.warning("Narrator call failed: %s", exc)
            return None
        except Exception as exc:
            self._failure_count += 1
            if self._failure_count == 1:
                logger.warning("Narrator call failed unexpectedly: %s", exc)
            return None

    def _record_action(self, verb: str, target: str | None, result: str) -> None:
        summary = f"{verb} {target}: {result}" if target else f"{verb}: {result}"
        self._recent_actions.append(summary)

    def _format_recent_actions(self) -> str:
        if not self._recent_actions:
            return "(none)"
        return "\n".join(f"- {a}" for a in self._recent_actions)

    def _make_cache_key(
        self, room_id: str, description: str,
        items: list[dict], npcs: list[dict],
    ) -> str:
        item_ids = sorted(i.get("id", i.get("name", "")) for i in items)
        npc_ids = sorted(n.get("id", n.get("name", "")) for n in npcs)
        raw = f"{room_id}:{description}:{item_ids}:{npc_ids}"
        return hashlib.md5(raw.encode()).hexdigest()
```

---

## 13. Engine Integration (Code Sketch)

The key change in `GameEngine` is wrapping the display methods to optionally pass output through the narrator.

```python
# In GameEngine.__init__:
self._narrator: Narrator | None = None

# In GameEngine.start(), after loading meta:
if config.narrator_enabled:
    self._init_narrator()

def _init_narrator(self) -> None:
    """Try to create a Narrator instance. Fails silently if no API key."""
    try:
        from anyzork.config import Config
        from anyzork.generator.providers import get_provider
        config = Config()
        provider = get_provider(config)
        provider.validate_config()
        self._narrator = Narrator(provider, self.db)
    except Exception as exc:
        self.console.print(
            f"Could not enable narrator: {exc}", style=STYLE_SYSTEM
        )
        self._narrator = None
```

In `display_room()`, after composing the `body` text and before rendering the panel:

```python
# Attempt narration
narrated_body = None
if self._narrator:
    narrated_body = self._narrator.narrate_room(
        room_id=room_id,
        room_name=room["name"],
        description=body,
        items=items,
        npcs=npcs,
        first_visit=first_visit,
    )

display_body = narrated_body or body

self.console.print(
    Panel(
        display_body,
        title=f"[{STYLE_ROOM_NAME}]{room['name']}[/]",
        ...
    )
)
# Exits, item list, NPC list render unchanged below the panel
```

For action results, in the REPL loop after DSL command success:

```python
if result.success:
    display_messages = result.messages
    if self._narrator and result.messages:
        narrated = self._narrator.narrate_action(verb, target, result.messages)
        if narrated:
            display_messages = [narrated]
    for msg in display_messages:
        self.console.print(msg)
```

---

## 14. Design Constraints Summary

These constraints are non-negotiable. They define the boundary of what narrator mode is and is not.

1. **Read-only.** The narrator has no write access to the database. It cannot call `db.update_player()`, `db.move_item()`, `db.set_flag()`, or any mutating method. It receives data, returns a string.

2. **Optional.** The game is fully playable without narrator mode. Every feature, puzzle, dialogue, and ending works identically with narrator on or off. Narrator mode is a display enhancement.

3. **Fallback-safe.** If the narrator fails, the game continues with deterministic output. No error state, no retry loop, no blocking.

4. **Structural data preserved.** Exits, item lists, NPC presence, score, and other mechanical information are always displayed by the engine's own formatter, never replaced by narrator prose.

5. **No cross-turn memory.** The narrator has no conversation history with the LLM. Each call is independent. The `recent_actions` buffer provides prose continuity through prompt context, not through LLM memory.

6. **Provider-agnostic.** Works with all three providers (Claude, OpenAI, Gemini) through the existing `BaseProvider.generate_text()` interface.

7. **No state leakage.** If the narrator hallucinates (mentions a nonexistent item, describes a wrong exit), the game state is unaffected. The player may see cosmetically incorrect prose, but the structural display below always shows the truth.
