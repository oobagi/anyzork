# Narrator Mode

Narrator mode adds an optional LLM prose layer on top of AnyZork's deterministic engine. When enabled, every major player-facing output -- room descriptions, action results, dialogue, inventory, quest logs, and system feedback -- is rewritten into atmospheric, novel-style prose before it reaches your terminal. The narrator is strictly read-only -- it cannot change game state, alter item positions, or influence outcomes. If the LLM call fails for any reason, the engine falls back to its own deterministic output and the game continues normally.

## How it works

Every turn, the engine produces its standard output (room description, item lists, NPC presence, action results). When narrator mode is active, that output is sent to an LLM provider as a prompt, along with a system prompt derived from the game's metadata (title and author prompt). The LLM rewrites the output as grounded prose -- mentioning every item and NPC by name, adding no new information, and never suggesting what the player should do.

Output types that get narrated:

- **Room descriptions** -- the full room body including items and NPCs present. When narration succeeds, UI chrome (item lists, NPC lists, exit bars) is suppressed for a cleaner, more immersive feel.
- **Action results** -- output from commands like `take`, `drop`, `examine`, `use`, `unlock`, `open`, etc.
- **Dialogue** -- NPC speech is rewritten as natural dialogue prose.
- **Inventory** -- the inventory table is replaced with flowing prose that names every carried item.
- **Quest log** -- the structured quest log is summarized as narrative prose.
- **System feedback** -- movement blocks, locked doors, and other engine messages are narrated when long enough.
- **Win/lose endings** -- victory and defeat text is narrated for a cinematic finish.

Short outputs (under 20 characters) are shown as-is without narration.

## Enabling narrator mode

### CLI flag

The simplest way to enable narrator mode for a single session:

```sh
anyzork play --narrator
```

You can also specify the provider and model on the command line:

```sh
anyzork play --narrator --provider openai --model gpt-4o
anyzork play --narrator --provider gemini --model gemini-2.5-flash
```

### Environment variable

To enable narrator mode by default for all sessions:

```sh
export ANYZORK_NARRATOR_ENABLED=true
```

### Config file

Set it in `~/.anyzork/config.toml` (see the [Configuration guide](configuration.md) for full details):

```toml
[anyzork]
provider = "claude"
# model = "claude-sonnet-4-6"  # optional — omit to use provider default
# narrator_temperature = 0.9   # optional — LLM temperature (0.0–2.0)
# narrator_max_tokens = 4096   # optional — max tokens per narrator response
```

### Setup wizard

Run `anyzork narrator` to configure your provider and API key interactively. The wizard walks through provider selection, API key entry, and validation.

## Provider setup

Three LLM providers are supported:

| Provider | Default model | API key variable | Config key |
|---|---|---|---|
| `claude` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | `[keys] anthropic` |
| `openai` | `gpt-4o` | `OPENAI_API_KEY` | `[keys] openai` |
| `gemini` | `gemini-2.5-flash` | `GOOGLE_API_KEY` | `[keys] google` |

Each provider requires its corresponding Python SDK to be installed. If the SDK is missing, you will see a message like:

```
Claude narrator support is not installed. Install the 'narrator' extra.
```

### Setting your API key

You can provide your API key in two ways:

**Environment variable** (recommended):

```sh
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Config file** (`~/.anyzork/config.toml`):

```toml
[keys]
anthropic = "sk-ant-..."
```

The environment variable always takes precedence over the config file value.

### Choosing a provider

The default provider is `claude`. To use a different provider:

```sh
# Via CLI flag (per-session)
anyzork play --narrator --provider gemini

# Via environment variable (persistent)
export ANYZORK_PROVIDER=openai

# Via config file (persistent)
# In ~/.anyzork/config.toml:
# [anyzork]
# provider = "openai"
```

CLI flags override environment variables, which override the config file.

### Overriding the model

Each provider has a sensible default model. To use a different one:

```sh
anyzork play --narrator --provider claude --model claude-sonnet-4-5
```

Or in the config file:

```toml
[anyzork]
provider = "claude"
model = "claude-sonnet-4-5"
```

## Performance tuning

Two settings control the narrator's LLM behavior:

- **`narrator_temperature`** -- Controls randomness in narrated prose. Default `0.9`. Range 0.0--2.0. Lower values produce more predictable, consistent prose; higher values add variety and surprise. A value around 0.7--1.0 works well for most games.
- **`narrator_max_tokens`** -- Maximum tokens the LLM may generate per narrator response. Default `4096`. Minimum 1. Lower values reduce latency and cost but may truncate longer room descriptions.

### Config file

```toml
[anyzork]
narrator_temperature = 0.8
narrator_max_tokens = 2048
```

### Environment variables

```sh
export ANYZORK_NARRATOR_TEMPERATURE=0.8
export ANYZORK_NARRATOR_MAX_TOKENS=2048
```

CLI flags and environment variables override config file values as described in the [Configuration guide](configuration.md).

## World context

The narrator reads game identity from metadata at session start. This includes:

- **Title** -- used in the system prompt to ground the narrator's voice.
- **Author prompt** -- the first sentence is extracted as a setting hint, giving the narrator world-appropriate tone without needing extra metadata columns.
- **Realism level** -- stored from metadata for future use in tuning prose style.

This context is read once and reused for every narration call in the session, avoiding redundant database reads.

## Caching

The narrator caches results aggressively to avoid redundant API calls:

- **Room cache**: Keyed by room ID and the set of items/NPCs present. If you revisit a room and nothing has changed (no items taken or dropped, no NPCs moved), the cached narration is reused. If the room state changes -- say you pick up a key -- the cache is invalidated and a fresh narration is generated.
- **Action cache**: Keyed by verb, target, and the exact message content. Repeating the same action with the same outcome (e.g., trying to open a locked door twice) reuses the cached narration.
- **Dialogue cache**: Keyed by dialogue node ID. Revisiting the same dialogue node reuses the cached narration.
- **Inventory cache**: Keyed by the sorted set of item names. The same inventory state always returns the same prose.
- **Quest cache**: Keyed by the plain-text quest summary. Unchanged quest state returns cached prose.
- **Feedback cache**: Keyed by verb, target, and message. Identical system messages always return cached prose.

All caches are in-memory and last for the duration of the session. They are not persisted to disk.

## Fallback behavior

The narrator is designed to never break your game. If an API call fails:

1. The engine's own deterministic output is shown instead.
2. On the first failure, a notice is printed: `(Narrator unavailable for this turn -- showing engine output.)`
3. Subsequent failures are silent -- you simply see the normal engine text.
4. The failure counter resets on the next successful call.

Transient errors (rate limits, server errors, connection problems) are retried up to 4 times with increasing delays (1s, 2s, 4s) before giving up. Non-transient errors (invalid API key, client errors) fail immediately.

If the narrator cannot be initialized at all (missing API key, missing SDK), a message is shown at startup and the game proceeds without narration.

## UI chrome suppression

In narrator mode, several UI elements are suppressed when narration succeeds to maintain the immersive feel:

- The "Nearby..." item/NPC fallback list below room descriptions
- The "Exits:" direction bar below room panels
- The shortcut bar shown after the first room display
- The structured inventory table (replaced with prose)
- The structured quest log (replaced with prose)

When narration fails, all standard UI chrome appears as usual.

## Limitations

- **Latency**: Each narrated turn requires a round-trip API call. You will see a brief "the narrator contemplates..." spinner while waiting. Cached turns are instant.
- **Cost**: Narrator mode consumes API tokens on every uncached turn. The system prompt is kept compact to reduce per-call cost.
- **No offline mode**: Narrator mode requires an active internet connection and a valid API key.
- **Short outputs are skipped**: Action results shorter than 20 characters are shown as-is without narration.
- **No game state influence**: The narrator cannot unlock doors, move items, or change scores. It is purely cosmetic. If you notice a discrepancy between narrated prose and actual game state, the game state is always authoritative.
