"""Abstract base provider interface for LLM providers.

Every provider (Claude, OpenAI, Gemini) implements this interface.  The
orchestrator and pass modules only depend on ``BaseProvider`` -- never on a
concrete provider class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GenerationContext:
    """Immutable bag of context passed alongside a generation prompt.

    Providers may use these fields to tune API parameters (temperature,
    seed) or to inject prior-pass output into the conversation.
    """

    existing_data: dict = field(default_factory=dict)
    seed: int | None = None
    temperature: float = 0.7
    max_tokens: int = 32_768


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


class BaseProvider(ABC):
    """Interface that all LLM providers implement."""

    # -------------------------------------------------------------- core API

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        context: GenerationContext | None = None,
    ) -> dict:
        """Send a prompt and get structured JSON output matching *schema*.

        Args:
            prompt: The generation instructions for this pass.
            schema: JSON schema describing the expected output format.
            context: Optional generation context (existing data, seed, etc.).

        Returns:
            Parsed JSON ``dict`` conforming to *schema*.

        Raises:
            ProviderError: On unrecoverable API/parse failures.
        """
        ...

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
