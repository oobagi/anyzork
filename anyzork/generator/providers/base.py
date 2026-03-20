"""Abstract base provider interface for narrator-capable LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anyzork.config import Config, LLMProvider


@dataclass(frozen=True)
class NarratorContext:
    """Context supplied when requesting freeform narrator prose."""

    system_prompt: str = ""
    theme: str = ""
    tone: str = ""
    room_lore: str = ""
    seed: int | None = None
    temperature: float = 0.9
    max_tokens: int = 2_048


class ProviderError(Exception):
    """Raised when a provider encounters an unrecoverable error."""


RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)


def validate_provider_config(
    config: Config,
    *,
    expected_provider: LLMProvider,
    provider_name: str,
    missing_key_message: str,
) -> None:
    """Validate provider selection and credential availability."""
    if config.provider != expected_provider:
        raise ProviderError(
            f"{provider_name} provider created but active provider is {config.provider.value!r}"
        )
    if not config.get_api_key():
        raise ProviderError(missing_key_message)


class BaseProvider(ABC):
    """Interface that all LLM providers implement."""

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        context: NarratorContext | None = None,
    ) -> str:
        """Send a prompt and get back freeform text (narrator mode).

        Args:
            prompt: The narrator prompt with engine output to embellish.
            context: Optional narrator context (theme, tone, lore).

        Returns:
            Prose string.

        Raises:
            ProviderError: On unrecoverable API failures.
        """
        ...

    @abstractmethod
    def validate_config(self) -> None:
        """Check that required credentials and settings are available.

        Raises:
            ProviderError: If the provider cannot operate (missing key, etc.).
        """
        ...
