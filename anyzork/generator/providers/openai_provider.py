"""OpenAI provider — uses the ``openai`` Python SDK."""

from __future__ import annotations

import json
import logging
import time

import openai

from anyzork.config import Config, LLMProvider
from anyzork.generator.providers.base import (
    BaseProvider,
    GenerationContext,
    NarratorContext,
    ProviderError,
)

logger = logging.getLogger(__name__)

_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)


class OpenAIProvider(BaseProvider):
    """LLM provider backed by OpenAI's Chat Completions API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        api_key = config.get_api_key()
        if not api_key:
            raise ProviderError(
                "No API key for OpenAI. Set OPENAI_API_KEY or ANYZORK_OPENAI_API_KEY."
            )
        self._client = openai.OpenAI(api_key=api_key)
        self._model = config.active_model or "gpt-4o"

    # ------------------------------------------------------------------ core

    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        context: GenerationContext | None = None,
    ) -> dict:
        ctx = context or GenerationContext()

        system_content = (
            "You are a world-building assistant for a text adventure game generator. "
            "Respond with ONLY valid JSON matching the schema provided. "
            "Do not include any explanation or text outside the JSON object.\n\n"
            f"Required JSON schema:\n{json.dumps(schema, indent=2)}"
        )

        user_content = prompt
        if ctx.existing_data:
            user_content += (
                "\n\n--- Context from previous generation passes ---\n"
                + json.dumps(ctx.existing_data, indent=2)
            )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        return self._call_with_retry(
            messages=messages,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
            response_format={"type": "json_object"},
        )

    def generate_text(
        self,
        prompt: str,
        context: NarratorContext | None = None,
    ) -> str:
        ctx = context or NarratorContext()

        system_content = (
            "You are a narrator for a text adventure game. "
            f"Theme: {ctx.theme}. Tone: {ctx.tone}. "
            "Describe exactly what the engine tells you — no more, no less. "
            "Do not add items, exits, or information not present in the engine output."
        )
        if ctx.room_lore:
            system_content += f"\n\nRoom lore context:\n{ctx.room_lore}"

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        result = self._call_with_retry(
            messages=messages,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
        )
        # When no response_format is set, result is a string.
        return result

    def validate_config(self) -> None:
        if self._config.provider != LLMProvider.OPENAI:
            raise ProviderError(
                f"OpenAIProvider created but active provider is {self._config.provider.value!r}"
            )
        if not self._config.get_api_key():
            raise ProviderError(
                "No API key for OpenAI. Set OPENAI_API_KEY or ANYZORK_OPENAI_API_KEY."
            )

    # ------------------------------------------------------------------ internal

    def _call_with_retry(
        self,
        *,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        response_format: dict | None = None,
    ) -> dict | str:
        """Call the OpenAI API with retries on transient errors."""
        last_exc: Exception | None = None

        for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
            try:
                kwargs: dict = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if response_format is not None:
                    kwargs["response_format"] = response_format

                response = self._client.chat.completions.create(**kwargs)
                text = response.choices[0].message.content or ""

                if response_format is not None:
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise ProviderError(
                            f"OpenAI returned invalid JSON despite json_object format: {exc}"
                        ) from exc

                return text

            except openai.RateLimitError as exc:
                logger.warning("OpenAI rate-limited (attempt %d): %s", attempt + 1, exc)
                last_exc = exc
            except openai.APIStatusError as exc:
                if exc.status_code >= 500:
                    logger.warning("OpenAI server error (attempt %d): %s", attempt + 1, exc)
                    last_exc = exc
                else:
                    raise ProviderError(f"OpenAI API error: {exc}") from exc
            except openai.APIConnectionError as exc:
                logger.warning("OpenAI connection error (attempt %d): %s", attempt + 1, exc)
                last_exc = exc

            if delay is not None:
                time.sleep(delay)

        raise ProviderError(
            f"OpenAI API failed after {len(_RETRY_DELAYS) + 1} attempts"
        ) from last_exc
