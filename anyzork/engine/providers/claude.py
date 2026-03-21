"""Anthropic Claude provider — uses the ``anthropic`` Python SDK."""

from __future__ import annotations

import logging
import time

from anyzork.config import Config, LLMProvider
from anyzork.engine.providers.base import (
    RETRY_DELAYS,
    BaseProvider,
    NarratorContext,
    ProviderError,
    validate_provider_config,
)

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseProvider):
    """LLM provider backed by the Anthropic Messages API."""

    def __init__(self, config: Config) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised without narrator extra
            raise ProviderError(
                "Claude narrator support is not installed. Install the 'narrator' extra."
            ) from exc

        self._config = config
        self._anthropic = anthropic
        api_key = config.get_api_key()
        if not api_key:
            raise ProviderError(
                "No API key for Claude. Set ANTHROPIC_API_KEY."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = config.active_model or "claude-sonnet-4-6"

    def generate_text(
        self,
        prompt: str,
        context: NarratorContext | None = None,
    ) -> str:
        ctx = context or NarratorContext()

        messages = [{"role": "user", "content": prompt}]

        return self._call_with_retry(
            system_prompt=ctx.system_prompt or "",
            messages=messages,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
        )

    def validate_config(self) -> None:
        validate_provider_config(
            self._config,
            expected_provider=LLMProvider.CLAUDE,
            provider_name="Claude",
            missing_key_message=(
                "No API key for Claude. Set ANTHROPIC_API_KEY."
            ),
        )

    # ------------------------------------------------------------------ internal

    def _call_with_retry(
        self,
        *,
        system_prompt: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call the Anthropic API with retries on transient errors."""
        last_exc: Exception | None = None

        for attempt, delay in enumerate((*RETRY_DELAYS, None)):
            try:
                # Use streaming to avoid 10-minute timeout on long requests.
                text_parts: list[str] = []
                with self._client.messages.stream(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=messages,
                ) as stream:
                    for text_chunk in stream.text_stream:
                        text_parts.append(text_chunk)
                text = "".join(text_parts)

                return text

            except self._anthropic.RateLimitError as exc:
                logger.warning("Claude rate-limited (attempt %d): %s", attempt + 1, exc)
                last_exc = exc
            except self._anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    logger.warning("Claude server error (attempt %d): %s", attempt + 1, exc)
                    last_exc = exc
                else:
                    raise ProviderError(f"Claude API error: {exc}") from exc
            except self._anthropic.APIConnectionError as exc:
                logger.warning("Claude connection error (attempt %d): %s", attempt + 1, exc)
                last_exc = exc

            if delay is not None:
                time.sleep(delay)

        raise ProviderError(
            f"Claude API failed after {len(RETRY_DELAYS) + 1} attempts"
        ) from last_exc
