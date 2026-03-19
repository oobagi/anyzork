# Provider Integration Guide

AnyZork's generation pipeline is provider-agnostic. The orchestrator calls the same interface regardless of which API provider is active. This guide covers how that works, what each provider expects, and how to add your own.

## Provider Architecture

Every provider implements a base interface with two responsibilities:

1. **Generate structured output** -- accept a generation prompt and return JSON conforming to the pass's schema (rooms, items, commands, etc.)
2. **Generate narrative text** -- accept a narrator prompt and return prose (used in narrator mode)

```python
class BaseProvider(ABC):
    """Interface that all LLM providers implement."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        schema: dict,
        context: GenerationContext,
    ) -> dict:
        """Send a prompt and get back structured JSON matching `schema`."""
        ...

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        context: NarratorContext,
    ) -> str:
        """Send a prompt and get back freeform text."""
        ...

    @abstractmethod
    def validate_config(self) -> None:
        """Check that required credentials/tools are available. Raise on failure."""
        ...
```

The generation orchestrator never talks to Claude, OpenAI, or Gemini directly. It holds a `BaseProvider` reference and calls `generate_structured()` for each pass (concept, rooms, locks, items, NPCs, interactions, puzzles, commands, quests, triggers). The provider is responsible for translating that call into whatever its backend expects and parsing the response back into a Python dict.

### Why This Matters

- Swapping providers is a config change, not a code change.
- Each generation pass does not care which LLM produced the data -- it validates the output against the schema either way.
- Tests can inject a mock provider that returns canned responses.

## API Providers

API providers make direct HTTP calls to an LLM service. You supply your own API key via environment variable.

### Claude (Anthropic API)

| Setting | Value |
|---------|-------|
| Env var | `ANTHROPIC_API_KEY` |
| Default model | `claude-sonnet-4-6` |
| SDK | `anthropic` (Python) |
| Override model | `ANYZORK_MODEL=claude-opus-4-20250918` |

The Claude provider uses the Anthropic Python SDK. For structured output, it sends the generation prompt as a user message and passes the JSON schema to the API so the response is constrained to valid JSON. Temperature and seed parameters are forwarded when the seed system is active.

### OpenAI

| Setting | Value |
|---------|-------|
| Env var | `OPENAI_API_KEY` |
| Default model | `gpt-4o` |
| SDK | `openai` (Python) |
| Override model | `ANYZORK_MODEL=gpt-4.1` |

The OpenAI provider uses the OpenAI Python SDK. Structured output is enforced via the `response_format` parameter with a JSON schema. The provider maps AnyZork's schema format into OpenAI's expected structure and parses the response.

### Gemini (Google GenAI)

| Setting | Value |
|---------|-------|
| Env var | `GOOGLE_API_KEY` |
| Default model | `gemini-2.5-flash` |
| SDK | `google-genai` (Python) |
| Override model | `ANYZORK_MODEL=gemini-2.5-pro` |

The Gemini provider uses Google's GenAI Python SDK. JSON schema enforcement is applied through the SDK's structured output support. The provider handles Gemini-specific formatting (e.g., `Part` objects, safety settings).

### How API Calls Work

All three API providers follow the same flow:

1. The orchestrator calls `generate_structured(prompt, schema, context)`.
2. The provider **formats the prompt** -- wraps it in the API's message format, attaches the JSON schema for response constraining, and sets model parameters (temperature, seed, max tokens).
3. The provider **sends the request** to the API using its SDK.
4. The provider **parses the response** -- extracts the JSON from the API response, deserializes it, and returns a plain Python dict.
5. The orchestrator **validates** the dict against the pass's schema. If validation fails, it can retry the call.

JSON schema enforcement is critical. Without it, the LLM might return valid JSON that doesn't match the expected structure (wrong field names, missing required fields, extra nesting). All three APIs support schema-constrained responses, which eliminates most parse failures.

## Configuration

All AnyZork config uses environment variables with the `ANYZORK_` prefix, managed by pydantic-settings.

### Core Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANYZORK_PROVIDER` | Which provider to use | `claude` |
| `ANYZORK_MODEL` | Override the provider's default model | (provider default) |
| `ANYZORK_SEED` | Seed for reproducible generation | (random) |
| `ANYZORK_MAX_RETRIES` | Retries per generation pass on failure | `3` |

### Provider-Specific Auth

| Variable | Provider |
|----------|----------|
| `ANTHROPIC_API_KEY` | Claude (API) |
| `OPENAI_API_KEY` | OpenAI (API) |
| `GOOGLE_API_KEY` | Gemini (API) |

### Provider Names

Use these values for `ANYZORK_PROVIDER`:

| Value | Provider |
|-------|----------|
| `claude` | Claude API (Anthropic) |
| `openai` | OpenAI API |
| `gemini` | Gemini API (Google) |

### Example

```bash
# Use Claude API with a specific model
export ANTHROPIC_API_KEY="sk-ant-..."
export ANYZORK_PROVIDER="claude"
export ANYZORK_MODEL="claude-sonnet-4-6"

# Generate a game
anyzork generate "a haunted lighthouse on a rocky coast"
```

## Adding a New Provider

To add a provider, you need to:

### 1. Implement the BaseProvider Interface

Create a new module (e.g., `providers/my_provider.py`) with a class that extends `BaseProvider`:

```python
from anyzork.providers.base import BaseProvider, GenerationContext, NarratorContext


class MyProvider(BaseProvider):
    def __init__(self, config):
        self.model = config.model or "my-default-model"
        # Initialize your SDK client here

    async def generate_structured(
        self,
        prompt: str,
        schema: dict,
        context: GenerationContext,
    ) -> dict:
        # Call your LLM API/CLI with the prompt
        # Enforce the JSON schema on the response
        # Return a parsed dict
        ...

    async def generate_text(
        self,
        prompt: str,
        context: NarratorContext,
    ) -> str:
        # Call your LLM for freeform text (narrator mode)
        ...

    def validate_config(self) -> None:
        # Check that credentials are set, CLI is installed, etc.
        # Raise a clear error if not
        if not os.environ.get("MY_API_KEY"):
            raise ConfigError("Set MY_API_KEY to use the My provider")
```

### 2. Register the Provider

Add your provider to the provider registry so it can be selected via `ANYZORK_PROVIDER`:

```python
# In providers/__init__.py or the config module
PROVIDERS = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "my-provider": MyProvider,  # Add this
}
```

### 3. Handle Schema Enforcement

The most important detail: your provider must return JSON that matches the schema. How you enforce this depends on your backend:

- **API with native schema support** -- pass the schema to the API (like OpenAI's `response_format` or Anthropic's tool use). This is the most reliable approach.
- **API without schema support** -- include the schema in the prompt and parse/validate the response. Retry on validation failure.

### 4. Add Config

If your provider needs new environment variables, add them to the pydantic-settings config model:

```python
class AnyZorkConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANYZORK_")

    provider: str = "claude"
    model: str | None = None
    # ...
    my_api_key: str | None = None  # reads ANYZORK_MY_API_KEY
```

Or, if the key follows the SDK's own convention (like `ANTHROPIC_API_KEY`), read it directly in your provider's `__init__` or `validate_config`.

### 5. Test

At minimum, test:

- `validate_config()` raises when credentials are missing.
- `generate_structured()` returns valid JSON matching a test schema.
- `generate_text()` returns a non-empty string.
- The provider handles API errors (rate limits, timeouts, malformed responses) gracefully with retries.

## Future: CLI Providers

CLI providers (Claude Code, Codex) that invoke agentic tools as subprocesses are deferred to a future version. These providers would use their own authentication, can read/write project files directly, and offer multi-step reasoning within a single generation pass. The `BaseProvider` interface is designed to accommodate them when they are added.
