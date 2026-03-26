"""Narrator integration mixin for GameEngine.

Handles LLM-based prose narration for actions, rooms, and feedback.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NarratorMixin:
    """Narrator integration methods extracted from GameEngine."""

    def _init_narrator(self) -> None:
        """Try to create a Narrator instance. Fails silently if no API key.

        Uses --provider/--model from CLI if passed, otherwise falls back to
        the default provider from config/env.
        """
        from anyzork.engine.game import STYLE_SYSTEM

        try:
            from anyzork.config import Config, LLMProvider
            from anyzork.engine.narrator import Narrator
            from anyzork.engine.providers import create_provider

            config = Config()

            # CLI overrides for narrator provider/model.
            if self._narrator_provider_override:
                config.provider = LLMProvider(self._narrator_provider_override)
            if self._narrator_model_override:
                config.model = self._narrator_model_override

            provider = create_provider(config)
            self._narrator = Narrator(
                provider,
                self.db,
                temperature=config.narrator_temperature,
                max_tokens=config.narrator_max_tokens,
            )
        except Exception as exc:
            logger.debug("Could not enable narrator: %s", exc)
            self.console.print(
                f"Could not enable narrator: {exc}\n"
                "Run 'anyzork narrator' to configure your provider and API key.",
                style=STYLE_SYSTEM,
            )
            self._narrator = None

    def _narrate_action(
        self, verb: str, target: str | None, messages: list[str]
    ) -> list[str]:
        """Optionally narrate action messages through the narrator.

        Returns the narrated version as a single-element list if narration
        succeeded, or the original messages list as-is if the narrator is
        disabled or the call failed.
        """
        if self._narrator is None or not messages:
            return messages
        with self.console.status("[dim italic]narrating...[/]", spinner="dots"):
            narrated = self._narrator.narrate_action(verb, target, messages)
        if narrated:
            from rich.markup import escape
            return [escape(narrated)]
        return messages

    def _narrate_single(
        self, verb: str, target: str | None, message: str
    ) -> str:
        """Narrate a single feedback message. Returns original on failure."""
        if self._narrator is None:
            return message
        with self.console.status("[dim italic]narrating...[/]", spinner="dots"):
            narrated = self._narrator.narrate_feedback(verb, target, message)
        if narrated:
            from rich.markup import escape
            return escape(narrated)
        return message
