"""Google Gemini provider — uses the ``google-genai`` Python SDK."""

from __future__ import annotations

import json
import logging
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from anyzork.config import Config, LLMProvider
from anyzork.generator.providers.base import (
    BaseProvider,
    GenerationContext,
    NarratorContext,
    ProviderError,
)

logger = logging.getLogger(__name__)

_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)


def _extract_json(text: str) -> dict:
    """Extract a JSON object from *text*, tolerating markdown fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Gemini returned invalid JSON inside code fence: {exc}"
            ) from exc

    raise ProviderError(
        f"Gemini response did not contain parseable JSON. First 200 chars: {text[:200]!r}"
    )


class GeminiProvider(BaseProvider):
    """LLM provider backed by Google's GenAI API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        api_key = config.get_api_key()
        if not api_key:
            raise ProviderError(
                "No API key for Gemini. Set GOOGLE_API_KEY or ANYZORK_GOOGLE_API_KEY."
            )
        self._client = genai.Client(api_key=api_key)
        self._model = config.active_model or "gemini-2.5-flash"

    # ------------------------------------------------------------------ core

    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        context: GenerationContext | None = None,
    ) -> dict:
        ctx = context or GenerationContext()

        system_instruction = (
            "You are a world-building assistant for a text adventure game generator. "
            "Respond with ONLY valid JSON matching the schema provided. "
            "Do not include any explanation, markdown formatting, or text outside the JSON object.\n\n"
            f"Required JSON schema:\n{json.dumps(schema, indent=2)}"
        )
        if ctx.seed is not None:
            system_instruction += f"\n\nGeneration seed: {ctx.seed}. Use this seed to guide deterministic choices."

        user_content = prompt
        if ctx.existing_data:
            user_content += (
                "\n\n--- Context from previous generation passes ---\n"
                + json.dumps(ctx.existing_data, indent=2)
            )

        # Gemini 2.5 Flash supports up to 65K output tokens — use the higher
        # of the requested max_tokens and 65K to avoid truncation.
        max_out = max(ctx.max_tokens, 65_536)
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=ctx.temperature,
            max_output_tokens=max_out,
            response_mime_type="application/json",
        )

        text = self._call_with_retry(
            contents=user_content,
            config=config,
        )

        return _extract_json(text)

    def generate_text(
        self,
        prompt: str,
        context: NarratorContext | None = None,
    ) -> str:
        ctx = context or NarratorContext()

        config = genai_types.GenerateContentConfig(
            system_instruction=ctx.system_prompt or None,
            temperature=ctx.temperature,
            max_output_tokens=ctx.max_tokens,
        )

        return self._call_with_retry(
            contents=prompt,
            config=config,
        )

    def validate_config(self) -> None:
        if self._config.provider != LLMProvider.GEMINI:
            raise ProviderError(
                f"GeminiProvider created but active provider is {self._config.provider.value!r}"
            )
        if not self._config.get_api_key():
            raise ProviderError(
                "No API key for Gemini. Set GOOGLE_API_KEY or ANYZORK_GOOGLE_API_KEY."
            )

    # ------------------------------------------------------------------ internal

    def _call_with_retry(
        self,
        *,
        contents: str,
        config: genai_types.GenerateContentConfig,
    ) -> str:
        """Call the Gemini API with retries on transient errors."""
        last_exc: Exception | None = None

        for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
                # Extract text — handle blocked/empty responses
                text = ""
                if response.candidates:
                    parts = response.candidates[0].content.parts
                    if parts:
                        text = "".join(p.text for p in parts if p.text)
                if not text and response.text:
                    text = response.text
                # Check finish reason for truncation
                finish_reason = None
                if response.candidates:
                    finish_reason = getattr(response.candidates[0], "finish_reason", None)

                if not text:
                    logger.warning(
                        "Gemini returned empty response (attempt %d). "
                        "Finish reason: %s",
                        attempt + 1,
                        finish_reason or "no candidates",
                    )
                    last_exc = ProviderError("Gemini returned empty response")
                    if delay is not None:
                        time.sleep(delay)
                    continue

                # Log token usage for debugging.
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    logger.info(
                        "Gemini tokens — input: %s, output: %s, finish: %s",
                        getattr(usage, "prompt_token_count", "?"),
                        getattr(usage, "candidates_token_count", "?"),
                        finish_reason,
                    )

                # Detect truncated output — finish reason MAX_TOKENS.
                if finish_reason and "MAX_TOKENS" in str(finish_reason):
                    raise ProviderError(
                        f"Gemini output was truncated (MAX_TOKENS). "
                        f"Output tokens: {getattr(usage, 'candidates_token_count', '?') if usage else '?'}. "
                        f"Limit was: {config.max_output_tokens}."
                    )

                return text

            except genai_errors.ClientError as exc:
                # Rate limit or quota errors are retryable.
                exc_str = str(exc).lower()
                if "rate" in exc_str or "quota" in exc_str or "429" in exc_str:
                    logger.warning("Gemini rate-limited (attempt %d): %s", attempt + 1, exc)
                    last_exc = exc
                else:
                    raise ProviderError(f"Gemini API error: {exc}") from exc
            except genai_errors.ServerError as exc:
                logger.warning("Gemini server error (attempt %d): %s", attempt + 1, exc)
                last_exc = exc
            except Exception as exc:
                # Catch connection-level errors from the SDK.
                exc_str = str(exc).lower()
                if "connection" in exc_str or "timeout" in exc_str:
                    logger.warning("Gemini connection error (attempt %d): %s", attempt + 1, exc)
                    last_exc = exc
                else:
                    raise ProviderError(f"Gemini API error: {exc}") from exc

            if delay is not None:
                time.sleep(delay)

        raise ProviderError(
            f"Gemini API failed after {len(_RETRY_DELAYS) + 1} attempts"
        ) from last_exc
