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


# Default model per provider.
_DEFAULT_MODELS: dict[LLMProvider, str] = {
    LLMProvider.CLAUDE: "claude-sonnet-4-6",
    LLMProvider.OPENAI: "gpt-4o",
    LLMProvider.GEMINI: "gemini-2.5-flash",
}

# Path constants.
CONFIG_DIR: Path = Path.home() / ".anyzork"
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"

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
    for key_type in _PROVIDER_TO_KEY_TYPE.values():
        if key_type in keys_section:
            result[f"{key_type}_api_key"] = keys_section[key_type]

    return result


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

    # --- Runtime settings ---
    narrator_enabled: bool = False

    # --- Paths ---
    games_dir: Path = Field(default_factory=lambda: Path.home() / ".anyzork" / "games")
    saves_dir: Path = Field(default_factory=lambda: Path.home() / ".anyzork" / "saves")

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
    def _ensure_paths_are_absolute(self) -> Config:
        """Resolve managed AnyZork directories to absolute paths."""
        self.games_dir = self.games_dir.expanduser().resolve()
        self.saves_dir = self.saves_dir.expanduser().resolve()
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
