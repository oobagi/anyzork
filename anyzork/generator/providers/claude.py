"""Anthropic Claude provider — uses the ``anthropic`` Python SDK."""

from __future__ import annotations

import json
import logging
import re
import time

import anthropic

from anyzork.config import Config, LLMProvider
from anyzork.generator.providers.base import (
    BaseProvider,
    GenerationContext,
    NarratorContext,
    ProviderError,
)

logger = logging.getLogger(__name__)

# Retry parameters for transient API errors.
_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)


def _extract_json(text: str) -> dict:
    """Extract a JSON object from *text*, tolerating markdown fences.

    Tries ``json.loads`` on the raw text first.  If that fails, looks for
    a fenced code block (```json ... ```) and parses its contents.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Look for fenced JSON block.
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Claude returned invalid JSON inside code fence: {exc}") from exc

    raise ProviderError(
        f"Claude response did not contain parseable JSON. First 200 chars: {text[:200]!r}"
    )


class ClaudeProvider(BaseProvider):
    """LLM provider backed by the Anthropic Messages API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        api_key = config.get_api_key()
        if not api_key:
            raise ProviderError(
                "No API key for Claude. Set ANTHROPIC_API_KEY or ANYZORK_ANTHROPIC_API_KEY."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = config.active_model or "claude-sonnet-4-6"

    # ------------------------------------------------------------------ core

    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        context: GenerationContext | None = None,
    ) -> dict:
        ctx = context or GenerationContext()

        system_prompt = (
            "You are a world-building assistant for a text adventure game generator. "
            "Respond with ONLY valid JSON matching the schema below. "
            "Do not include any explanation, markdown formatting, or text outside the JSON object.\n\n"
            f"Required JSON schema:\n{json.dumps(schema, indent=2)}"
        )
        if ctx.seed is not None:
            system_prompt += f"\n\nGeneration seed: {ctx.seed}. Use this seed to guide deterministic choices."

        user_content = prompt
        if ctx.existing_data:
            user_content += (
                "\n\n--- Context from previous generation passes ---\n"
                + json.dumps(ctx.existing_data, indent=2)
            )

        messages = [{"role": "user", "content": user_content}]

        return self._call_with_retry(
            system_prompt=system_prompt,
            messages=messages,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
            parse_json=True,
        )

    def generate_text(
        self,
        prompt: str,
        context: NarratorContext | None = None,
    ) -> str:
        ctx = context or NarratorContext()

        system_prompt = (
            "You are a narrator for a text adventure game. "
            f"Theme: {ctx.theme}. Tone: {ctx.tone}. "
            "Describe exactly what the engine tells you — no more, no less. "
            "Do not add items, exits, or information not present in the engine output."
        )
        if ctx.room_lore:
            system_prompt += f"\n\nRoom lore context:\n{ctx.room_lore}"

        messages = [{"role": "user", "content": prompt}]

        return self._call_with_retry(
            system_prompt=system_prompt,
            messages=messages,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
            parse_json=False,
        )

    def validate_config(self) -> None:
        if self._config.provider != LLMProvider.CLAUDE:
            raise ProviderError(
                f"ClaudeProvider created but active provider is {self._config.provider.value!r}"
            )
        if not self._config.get_api_key():
            raise ProviderError(
                "No API key for Claude. Set ANTHROPIC_API_KEY or ANYZORK_ANTHROPIC_API_KEY."
            )

    # ------------------------------------------------------------------ internal

    def _call_with_retry(
        self,
        *,
        system_prompt: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        parse_json: bool,
    ) -> dict | str:
        """Call the Anthropic API with retries on transient errors."""
        last_exc: Exception | None = None

        for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
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

                if parse_json:
                    return _extract_json(text)
                return text

            except anthropic.RateLimitError as exc:
                logger.warning("Claude rate-limited (attempt %d): %s", attempt + 1, exc)
                last_exc = exc
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    logger.warning("Claude server error (attempt %d): %s", attempt + 1, exc)
                    last_exc = exc
                else:
                    raise ProviderError(f"Claude API error: {exc}") from exc
            except anthropic.APIConnectionError as exc:
                logger.warning("Claude connection error (attempt %d): %s", attempt + 1, exc)
                last_exc = exc

            if delay is not None:
                time.sleep(delay)

        raise ProviderError(f"Claude API failed after {len(_RETRY_DELAYS) + 1} attempts") from last_exc
