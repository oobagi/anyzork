"""Google Gemini provider — uses the ``google-genai`` Python SDK."""

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


def _extract_response_text(response: object) -> str:
    """Return concatenated candidate text, tolerating empty Gemini content."""
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        text = "".join(
            part_text
            for part in parts
            if (part_text := getattr(part, "text", None))
        )
        if text:
            return text

    # ``response.text`` is a convenience property, but it may be absent or
    # raise when Gemini returns only non-text candidates.
    try:
        fallback = getattr(response, "text", None)
    except Exception:  # pragma: no cover - SDK-specific property behavior
        return ""
    return fallback or ""


class GeminiProvider(BaseProvider):
    """LLM provider backed by Google's GenAI API."""

    def __init__(self, config: Config) -> None:
        try:
            from google import genai
            from google.genai import errors as genai_errors
            from google.genai import types as genai_types
        except ImportError as exc:  # pragma: no cover - exercised without narrator extra
            raise ProviderError(
                "Gemini narrator support is not installed. Install the 'narrator' extra."
            ) from exc

        self._config = config
        self._genai = genai
        self._genai_errors = genai_errors
        self._genai_types = genai_types
        api_key = config.get_api_key()
        if not api_key:
            raise ProviderError(
                "No API key for Gemini. "
                "Run 'anyzork narrator' to set up, or set GOOGLE_API_KEY."
            )
        self._client = genai.Client(api_key=api_key)
        self._model = config.active_model or "gemini-2.5-flash"

    def generate_text(
        self,
        prompt: str,
        context: NarratorContext | None = None,
    ) -> str:
        ctx = context or NarratorContext()

        config = self._genai_types.GenerateContentConfig(
            system_instruction=ctx.system_prompt or None,
            temperature=ctx.temperature,
            max_output_tokens=ctx.max_tokens,
        )

        return self._call_with_retry(
            contents=prompt,
            config=config,
        )

    def validate_config(self) -> None:
        validate_provider_config(
            self._config,
            expected_provider=LLMProvider.GEMINI,
            provider_name="Gemini",
            missing_key_message=(
                "No API key for Gemini. "
                "Run 'anyzork narrator' to set up, or set GOOGLE_API_KEY."
            ),
        )

    # ------------------------------------------------------------------ internal

    def _call_with_retry(
        self,
        *,
        contents: str,
        config: object,
    ) -> str:
        """Call the Gemini API with retries on transient errors."""
        last_exc: Exception | None = None

        for attempt, delay in enumerate((*RETRY_DELAYS, None)):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
                # Extract text — handle blocked/empty responses
                text = _extract_response_text(response)
                # Check finish reason for truncation
                finish_reason = None
                candidates = getattr(response, "candidates", None) or []
                if candidates:
                    finish_reason = getattr(candidates[0], "finish_reason", None)

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
                        f"Output tokens: "
                        f"{getattr(usage, 'candidates_token_count', '?') if usage else '?'}. "
                        f"Limit was: {config.max_output_tokens}."
                    )

                return text

            except self._genai_errors.ClientError as exc:
                # Rate limit or quota errors are retryable.
                exc_str = str(exc).lower()
                if "rate" in exc_str or "quota" in exc_str or "429" in exc_str:
                    logger.warning("Gemini rate-limited (attempt %d): %s", attempt + 1, exc)
                    last_exc = exc
                else:
                    raise ProviderError(f"Gemini API error: {exc}") from exc
            except self._genai_errors.ServerError as exc:
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
            f"Gemini API failed after {len(RETRY_DELAYS) + 1} attempts"
        ) from last_exc
