"""Provider factory — select the right LLM backend from config."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anyzork.config import LLMProvider
from anyzork.generator.providers.base import BaseProvider, ProviderError

if TYPE_CHECKING:
    from anyzork.config import Config


def create_provider(config: Config) -> BaseProvider:
    """Create the appropriate provider based on *config*.

    Raises:
        ProviderError: If the provider value is unrecognised or if the
            selected provider fails its own config validation.
    """
    if config.provider == LLMProvider.CLAUDE:
        from anyzork.generator.providers.claude import ClaudeProvider

        provider = ClaudeProvider(config)

    elif config.provider == LLMProvider.OPENAI:
        from anyzork.generator.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider(config)

    elif config.provider == LLMProvider.GEMINI:
        from anyzork.generator.providers.gemini import GeminiProvider

        provider = GeminiProvider(config)

    else:
        raise ProviderError(f"Unknown provider: {config.provider!r}")

    provider.validate_config()
    return provider


__all__ = [
    "BaseProvider",
    "ProviderError",
    "create_provider",
]
