"""AnyZork configuration — pydantic-settings with ANYZORK_ env prefix."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
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


class Config(BaseSettings):
    """Central configuration for AnyZork.

    Values are read from environment variables prefixed with ``ANYZORK_``.
    Provider-specific API keys also fall back to their SDK's standard env var
    (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, ``GOOGLE_API_KEY``).
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

        Checks the ANYZORK_-prefixed field first, then falls back to the
        provider SDK's standard env var.
        """
        key_map: dict[LLMProvider, tuple[str | None, str]] = {
            LLMProvider.CLAUDE: (self.anthropic_api_key, "ANTHROPIC_API_KEY"),
            LLMProvider.OPENAI: (self.openai_api_key, "OPENAI_API_KEY"),
            LLMProvider.GEMINI: (self.google_api_key, "GOOGLE_API_KEY"),
        }

        field_value, env_name = key_map.get(self.provider, (None, ""))
        return field_value or os.environ.get(env_name)

    @property
    def default_model(self) -> str | None:
        """Return the default model for the active provider."""
        return _DEFAULT_MODELS.get(self.provider)

    @property
    def active_model(self) -> str | None:
        """The model to use — explicit override or provider default."""
        return self.model or self.default_model
