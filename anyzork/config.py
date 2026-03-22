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

# Default URLs (single source of truth).
DEFAULT_CATALOG_URL: str = "https://anyzork.com/catalog.json"
DEFAULT_UPLOAD_URL: str = "https://anyzork.com/api/games"

_PROVIDER_TO_KEY_TYPE: dict[LLMProvider, str] = {
    LLMProvider.CLAUDE: "anthropic",
    LLMProvider.OPENAI: "openai",
    LLMProvider.GEMINI: "google",
}


def load_config_file() -> dict:
    """Load ``~/.anyzork/config.toml`` if it exists.

    Returns a flat dict with keys that map to Config fields:
      - ``provider`` and ``model`` from ``[anyzork]``
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

    # [anyzork] section — all Config fields are supported here.
    anyzork_section = data.get("anyzork", {})
    anyzork_keys = (
        "provider",
        "model",
        "narrator_enabled",
        "narrator_temperature",
        "narrator_max_tokens",
        "games_dir",
        "saves_dir",
        "cache_dir",
        "public_catalog_dir",
        "catalog_url",
        "upload_url",
    )
    for key in anyzork_keys:
        if key in anyzork_section:
            result[key] = anyzork_section[key]

    # [keys] section — map to the Config field names
    keys_section = data.get("keys", {})
    for key_type in _PROVIDER_TO_KEY_TYPE.values():
        if key_type in keys_section:
            result[f"{key_type}_api_key"] = keys_section[key_type]

    return result


def _format_toml(data: dict) -> str:
    """Format a simple nested dict as TOML."""
    lines: list[str] = []
    if "anyzork" in data:
        lines.append("[anyzork]")
        for k, v in data["anyzork"].items():
            if isinstance(v, bool):
                lines.append(f"{k} = {str(v).lower()}")
            elif isinstance(v, str):
                lines.append(f'{k} = "{v}"')
        lines.append("")
    if "keys" in data:
        lines.append("[keys]")
        for k, v in data["keys"].items():
            lines.append(f'{k} = "{v}"')
        lines.append("")
    return "\n".join(lines) + "\n" if lines else ""


def save_config_file(
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: tuple[str, str] | None = None,
    narrator_enabled: bool | None = None,
) -> None:
    """Update ~/.anyzork/config.toml, preserving existing values.

    Args:
        provider: Provider name to set in [anyzork] section.
        model: Model name to set in [anyzork] section.
        api_key: Tuple of (key_type, key_value) to set in [keys] section.
                 key_type is "anthropic", "openai", or "google".
        narrator_enabled: Whether narrator is enabled by default.
    """
    # Read existing raw TOML structure.
    if CONFIG_FILE.is_file():
        try:
            with CONFIG_FILE.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            data = {}
    else:
        data = {}

    # Ensure sections exist.
    if "anyzork" not in data:
        data["anyzork"] = {}
    if "keys" not in data:
        data["keys"] = {}

    # Merge updates.
    if provider is not None:
        data["anyzork"]["provider"] = provider
    if model is not None:
        data["anyzork"]["model"] = model
    if narrator_enabled is not None:
        data["anyzork"]["narrator_enabled"] = narrator_enabled
    if api_key is not None:
        key_type, key_value = api_key
        data["keys"][key_type] = key_value

    # Remove empty sections before writing.
    if not data["anyzork"]:
        del data["anyzork"]
    if not data.get("keys"):
        data.pop("keys", None)

    # Write back.
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(_format_toml(data))


def validate_api_key(provider: LLMProvider, api_key: str) -> tuple[bool, str]:
    """Make a minimal API call to verify the key works.

    Returns (success, message) tuple.
    """
    if provider == LLMProvider.CLAUDE:
        try:
            import anthropic
        except ImportError:
            return (False, "anthropic package not installed. Install the 'narrator' extra.")
        try:
            anthropic.Anthropic(api_key=api_key).messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
        except anthropic.AuthenticationError:
            return (False, "Invalid API key.")
        except Exception as exc:
            return (False, str(exc))
        return (True, "Key validated successfully.")

    if provider == LLMProvider.OPENAI:
        try:
            import openai
        except ImportError:
            return (False, "openai package not installed. Install the 'narrator' extra.")
        try:
            openai.OpenAI(api_key=api_key).chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
        except openai.AuthenticationError:
            return (False, "Invalid API key.")
        except Exception as exc:
            return (False, str(exc))
        return (True, "Key validated successfully.")

    if provider == LLMProvider.GEMINI:
        try:
            from google import genai
            from google.genai import errors as genai_errors
        except ImportError:
            return (False, "google-genai package not installed. Install the 'narrator' extra.")
        try:
            genai.Client(api_key=api_key).models.generate_content(
                model="gemini-2.0-flash-lite",
                contents="hi",
            )
        except genai_errors.ClientError:
            return (False, "Invalid API key.")
        except Exception as exc:
            return (False, str(exc))
        return (True, "Key validated successfully.")

    return (False, f"Unknown provider: {provider}")


class Config(BaseSettings):
    """Central configuration for AnyZork.

    Values are read from environment variables prefixed with ``ANYZORK_``.
    Narrator provider settings fall back to ``~/.anyzork/config.toml``.
    Narrator API keys come from provider-standard env vars
    (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, ``GOOGLE_API_KEY``),
    or from the optional ``[keys]`` section in ``~/.anyzork/config.toml``.
    """

    model_config = SettingsConfigDict(
        env_prefix="ANYZORK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Narrator provider selection ---
    provider: LLMProvider = LLMProvider.CLAUDE
    model: str | None = None

    # --- Narrator API keys from config file defaults ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None

    # --- Runtime settings ---
    narrator_enabled: bool = False
    narrator_temperature: float = Field(default=0.9, ge=0.0, le=2.0)
    narrator_max_tokens: int = Field(default=4096, ge=1)

    # --- URLs ---
    catalog_url: str = DEFAULT_CATALOG_URL
    upload_url: str = DEFAULT_UPLOAD_URL

    # --- Paths ---
    games_dir: Path = Field(default_factory=lambda: Path.home() / ".anyzork" / "games")
    saves_dir: Path = Field(default_factory=lambda: Path.home() / ".anyzork" / "saves")
    cache_dir: Path = Field(default_factory=lambda: Path.home() / ".anyzork" / "cache")
    public_catalog_dir: Path = Field(
        default_factory=lambda: Path.home() / ".anyzork" / "public_catalog"
    )

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
        self.cache_dir = self.cache_dir.expanduser().resolve()
        self.public_catalog_dir = self.public_catalog_dir.expanduser().resolve()
        return self

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_api_key(self) -> str | None:
        """Return the API key for the active provider.

        Checks (in order):
          1. Provider SDK's standard env var
          2. ``~/.anyzork/config.toml`` ``[keys]`` section
        """
        key_map: dict[LLMProvider, tuple[str | None, str]] = {
            LLMProvider.CLAUDE: (self.anthropic_api_key, "ANTHROPIC_API_KEY"),
            LLMProvider.OPENAI: (self.openai_api_key, "OPENAI_API_KEY"),
            LLMProvider.GEMINI: (self.google_api_key, "GOOGLE_API_KEY"),
        }

        field_value, env_name = key_map.get(self.provider, (None, ""))
        result = os.environ.get(env_name) or field_value
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
