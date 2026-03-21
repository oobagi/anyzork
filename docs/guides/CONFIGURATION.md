# Configuration

AnyZork reads configuration from a TOML file, environment variables, and an optional `.env` file. Values are resolved in this order (later wins):

1. Built-in defaults
2. `~/.anyzork/config.toml`
3. `.env` file in the working directory
4. Environment variables
5. CLI flags

## Config file

**Path:** `~/.anyzork/config.toml`

The file uses two sections: `[anyzork]` for engine settings and `[keys]` for API credentials.

## Fields

### `[anyzork]` section

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | `"claude"` \| `"openai"` \| `"gemini"` | `"claude"` | LLM provider for the narrator. |
| `model` | string | *(per-provider default)* | Model name override. When unset, uses the provider default (see below). |
| `narrator_temperature` | float | `0.9` | LLM temperature for narrator mode. Range 0.0--2.0. |
| `narrator_max_tokens` | int | `4096` | Max tokens per narrator response. Minimum 1. |
| `catalog_url` | string | `https://anyzork.com/catalog.json` | Game catalog URL. |
| `upload_url` | string | `https://anyzork.com/api/games` | Upload endpoint for publish. |

### `[keys]` section

| Field | Type | Description |
|---|---|---|
| `anthropic` | string | Anthropic API key (Claude). |
| `openai` | string | OpenAI API key. |
| `google` | string | Google API key (Gemini). |

Keys in the config file are lowest priority -- the standard provider environment variables always take precedence.

## Environment variables

All `Config` fields can be set via environment variables prefixed with `ANYZORK_`:

| Variable | Field | Default |
|---|---|---|
| `ANYZORK_PROVIDER` | `provider` | `claude` |
| `ANYZORK_MODEL` | `model` | *(none)* |
| `ANYZORK_NARRATOR_ENABLED` | `narrator_enabled` | `false` |
| `ANYZORK_GAMES_DIR` | `games_dir` | `~/.anyzork/games` |
| `ANYZORK_SAVES_DIR` | `saves_dir` | `~/.anyzork/saves` |
| `ANYZORK_PUBLIC_CATALOG_DIR` | `public_catalog_dir` | `~/.anyzork/public_catalog` |
| `ANYZORK_NARRATOR_TEMPERATURE` | `narrator_temperature` | `0.9` |
| `ANYZORK_NARRATOR_MAX_TOKENS` | `narrator_max_tokens` | `4096` |
| `ANYZORK_CATALOG_URL` | `catalog_url` | `https://anyzork.com/catalog.json` |
| `ANYZORK_UPLOAD_URL` | `upload_url` | `https://anyzork.com/api/games` |

API keys use the standard provider variables (not the `ANYZORK_` prefix):

| Variable | Provider |
|---|---|
| `ANTHROPIC_API_KEY` | Claude |
| `OPENAI_API_KEY` | OpenAI |
| `GOOGLE_API_KEY` | Gemini |

## Provider defaults

Each provider has a default model used when `model` is not set:

| Provider | Default model |
|---|---|
| `claude` | `claude-sonnet-4-6` |
| `openai` | `gpt-4o` |
| `gemini` | `gemini-2.5-flash` |

## Path fields

`games_dir`, `saves_dir`, and `public_catalog_dir` are resolved to absolute paths at startup. Tilde (`~`) expansion is supported.

## Example config

```toml
[anyzork]
provider = "claude"
# model = "claude-sonnet-4-6"  # optional — omit to use provider default

[keys]
anthropic = "sk-ant-..."
# openai = "sk-..."
# google = "AI..."
```

Minimal setup with environment variables only (no config file needed):

```sh
export ANTHROPIC_API_KEY="sk-ant-..."
export ANYZORK_NARRATOR_ENABLED=true
```
