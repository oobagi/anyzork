"""OpenAI provider — uses the ``openai`` Python SDK."""

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


class OpenAIProvider(BaseProvider):
    """LLM provider backed by OpenAI's Chat Completions API."""

    def __init__(self, config: Config) -> None:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - exercised without narrator extra
            raise ProviderError(
                "OpenAI narrator support is not installed. Install the 'narrator' extra."
            ) from exc

        self._config = config
        self._openai = openai
        api_key = config.get_api_key()
        if not api_key:
            raise ProviderError(
                "No API key for OpenAI. Run 'anyzork narrator' to set one up, or set OPENAI_API_KEY."
            )
        self._client = openai.OpenAI(api_key=api_key)
        self._model = config.active_model or "gpt-4o"

    def generate_text(
        self,
        prompt: str,
        context: NarratorContext | None = None,
    ) -> str:
        ctx = context or NarratorContext()

        messages = [
            {"role": "system", "content": ctx.system_prompt or ""},
            {"role": "user", "content": prompt},
        ]

        result = self._call_with_retry(
            messages=messages,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
            seed=ctx.seed,
        )
        return result

    def validate_config(self) -> None:
        validate_provider_config(
            self._config,
            expected_provider=LLMProvider.OPENAI,
            provider_name="OpenAI",
            missing_key_message=(
                "No API key for OpenAI. Run 'anyzork narrator' to set one up, or set OPENAI_API_KEY."
            ),
        )

    # ------------------------------------------------------------------ internal

    def _call_with_retry(
        self,
        *,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        seed: int | None = None,
    ) -> str:
        """Call the OpenAI API with retries on transient errors."""
        last_exc: Exception | None = None

        for attempt, delay in enumerate((*RETRY_DELAYS, None)):
            try:
                kwargs: dict = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if seed is not None:
                    kwargs["seed"] = seed

                response = self._client.chat.completions.create(**kwargs)
                text = response.choices[0].message.content or ""

                return text

            except self._openai.RateLimitError as exc:
                logger.warning("OpenAI rate-limited (attempt %d): %s", attempt + 1, exc)
                last_exc = exc
            except self._openai.APIStatusError as exc:
                if exc.status_code >= 500:
                    logger.warning("OpenAI server error (attempt %d): %s", attempt + 1, exc)
                    last_exc = exc
                else:
                    raise ProviderError(f"OpenAI API error: {exc}") from exc
            except self._openai.APIConnectionError as exc:
                logger.warning("OpenAI connection error (attempt %d): %s", attempt + 1, exc)
                last_exc = exc

            if delay is not None:
                time.sleep(delay)

        raise ProviderError(
            f"OpenAI API failed after {len(RETRY_DELAYS) + 1} attempts"
        ) from last_exc
