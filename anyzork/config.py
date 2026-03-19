"""AnyZork configuration — pydantic-settings with ANYZORK_ env prefix."""

from __future__ import annotations

import os
import tomllib
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"


# Default model per provider — kept in sync with docs/providers/integration.md.
_DEFAULT_MODELS: dict[LLMProvider, str] = {
    LLMProvider.CLAUDE: "claude-sonnet-4-6",
    LLMProvider.OPENAI: "gpt-4o",
    LLMProvider.GEMINI: "gemini-2.5-flash",
}

# Path constants.
CONFIG_DIR: Path = Path.home() / ".anyzork"
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"

# Maps config file key names to provider enum / env var names.
_KEY_TYPE_TO_PROVIDER: dict[str, LLMProvider] = {
    "anthropic": LLMProvider.CLAUDE,
    "openai": LLMProvider.OPENAI,
    "google": LLMProvider.GEMINI,
}

_PROVIDER_TO_KEY_TYPE: dict[LLMProvider, str] = {
    LLMProvider.CLAUDE: "anthropic",
    LLMProvider.OPENAI: "openai",
    LLMProvider.GEMINI: "google",
}


def load_config_file() -> dict:
    """Load ``~/.anyzork/config.toml`` if it exists.

    Returns a flat dict with keys that map to Config fields:
      - ``provider``, ``model`` from ``[anyzork]``
      - ``anthropic_api_key``, ``openai_api_key``, ``google_api_key`` from ``[keys]``

    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    if not CONFIG_FILE.is_file():
        return {}

    try:
        with CONFIG_FILE.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}

    result: dict = {}

    # [anyzork] section
    anyzork_section = data.get("anyzork", {})
    if "provider" in anyzork_section:
        result["provider"] = anyzork_section["provider"]
    if "model" in anyzork_section:
        result["model"] = anyzork_section["model"]

    # [keys] section — map to the Config field names
    keys_section = data.get("keys", {})
    if "anthropic" in keys_section:
        result["anthropic_api_key"] = keys_section["anthropic"]
    if "openai" in keys_section:
        result["openai_api_key"] = keys_section["openai"]
    if "google" in keys_section:
        result["google_api_key"] = keys_section["google"]

    return result


def save_config_file(
    provider: str,
    model: str | None,
    api_key: str,
    key_type: str,
) -> Path:
    """Write config to ``~/.anyzork/config.toml``.

    Merges with any existing config file content so that keys for other
    providers are preserved.

    Args:
        provider: Provider name (``claude``, ``openai``, ``gemini``).
        model: Model name, or ``None`` for the provider default.
        api_key: The API key to store.
        key_type: Key section name (``anthropic``, ``openai``, ``google``).

    Returns:
        Path to the written config file.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing keys so we don't clobber other providers.
    existing_keys: dict[str, str] = {}
    if CONFIG_FILE.is_file():
        try:
            with CONFIG_FILE.open("rb") as f:
                existing = tomllib.load(f)
            existing_keys = dict(existing.get("keys", {}))
        except Exception:
            pass

    # Update with new key.
    existing_keys[key_type] = api_key

    # Build TOML content.
    lines: list[str] = ["[anyzork]", f'provider = "{provider}"']
    if model:
        lines.append(f'model = "{model}"')
    lines.append("")
    lines.append("[keys]")
    for k, v in sorted(existing_keys.items()):
        lines.append(f'{k} = "{v}"')
    lines.append("")  # trailing newline

    CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")
    return CONFIG_FILE


class Config(BaseSettings):
    """Central configuration for AnyZork.

    Values are read from environment variables prefixed with ``ANYZORK_``.
    Provider-specific API keys also fall back to their SDK's standard env var
    (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, ``GOOGLE_API_KEY``), and
    finally to ``~/.anyzork/config.toml``.
    """

    model_config = SettingsConfigDict(
        env_prefix="ANYZORK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Provider selection ---
    provider: LLMProvider = LLMProvider.CLAUDE
    model: str | None = None

    # --- API keys (ANYZORK_ANTHROPIC_API_KEY, etc.) ---
    # These are secondary — we also check the standard env vars in get_api_key().
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None

    # --- Generation settings ---
    seed: int | None = None
    max_retries: int = 3

    # --- Runtime settings ---
    narrator_enabled: bool = False

    # --- Paths ---
    games_dir: Path = Field(default_factory=lambda: Path.home() / ".anyzork" / "games")

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _merge_config_file(cls, values: dict) -> dict:
        """Merge values from ``~/.anyzork/config.toml`` as lowest-priority defaults.

        Load order (later overrides earlier):
          1. Defaults (pydantic)
          2. ``~/.anyzork/config.toml``  <-- injected here
          3. ``.env`` file
          4. Environment variables
          5. CLI flags (passed as constructor kwargs)

        Only fill in keys that are not already set by env / .env / kwargs.
        """
        file_values = load_config_file()
        if file_values:
            for key, val in file_values.items():
                if key not in values or values[key] is None:
                    values[key] = val
        return values

    @model_validator(mode="after")
    def _ensure_games_dir_is_absolute(self) -> Config:
        """Resolve games_dir to an absolute path."""
        self.games_dir = self.games_dir.expanduser().resolve()
        return self

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_api_key(self) -> str | None:
        """Return the API key for the active provider.

        Checks (in order):
          1. ANYZORK_-prefixed field (env var or .env)
          2. Provider SDK's standard env var
          3. ``~/.anyzork/config.toml`` ``[keys]`` section
        """
        key_map: dict[LLMProvider, tuple[str | None, str]] = {
            LLMProvider.CLAUDE: (self.anthropic_api_key, "ANTHROPIC_API_KEY"),
            LLMProvider.OPENAI: (self.openai_api_key, "OPENAI_API_KEY"),
            LLMProvider.GEMINI: (self.google_api_key, "GOOGLE_API_KEY"),
        }

        field_value, env_name = key_map.get(self.provider, (None, ""))
        result = field_value or os.environ.get(env_name)
        if result:
            return result

        # Fall back to config file.
        file_values = load_config_file()
        key_type = _PROVIDER_TO_KEY_TYPE.get(self.provider, "")
        config_field = f"{key_type}_api_key"
        return file_values.get(config_field)

    @property
    def default_model(self) -> str | None:
        """Return the default model for the active provider."""
        return _DEFAULT_MODELS.get(self.provider)

    @property
    def active_model(self) -> str | None:
        """The model to use — explicit override or provider default."""
        return self.model or self.default_model

    def get_value_source(self, field_name: str) -> str:
        """Return a human-readable source for a config value.

        Checks env vars, config file, and defaults to determine provenance.
        """
        env_key = f"ANYZORK_{field_name.upper()}"
        if os.environ.get(env_key):
            return "env var"

        file_values = load_config_file()
        if field_name in file_values:
            return "config file"

        return "default"
