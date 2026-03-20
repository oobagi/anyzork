"""Narrator -- optional read-only LLM layer for atmospheric prose.

Sits between the engine's deterministic output and the console display.
Cannot change game state. If the LLM call fails for any reason, the engine
falls back to its own deterministic output and the game continues.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anyzork.generator.providers.base import NarratorContext, ProviderError

if TYPE_CHECKING:
    from anyzork.db.schema import GameDB
    from anyzork.generator.providers.base import BaseProvider

logger = logging.getLogger(__name__)

MIN_NARRATION_LENGTH = 20


@dataclass
class NarratorGameContext:
    """Cached game identity -- read once from metadata, stable for the session."""

    title: str = "Untitled"
    theme: str = ""
    tone: str = ""
    era: str = ""
    setting: str = ""


# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
Narrator for "{title}". {tone} tone, {era}, {setting}.

Rewrite room descriptions as grounded, natural prose. Write like a good novel — \
not purple, not flowery, not dramatic. Just clear, evocative, specific. \
Mention every item and NPC by their full name — never group or summarize them. \
Do NOT add anything not in the engine output. Do NOT contradict it. \
Do NOT suggest what the player should do. No markdown. One paragraph.\
"""


class Narrator:
    """Read-only LLM layer that flavors engine output with prose.

    Instantiated by the GameEngine when narrator mode is enabled. Holds a
    reference to a :class:`BaseProvider` and builds prompts from engine output.
    The narrator never writes to the database.
    """

    def __init__(self, provider: BaseProvider, db: GameDB) -> None:
        self._provider = provider
        self._db = db
        self._room_cache: dict[str, tuple[str, str]] = {}
        self._action_cache: dict[str, str] = {}
        self._failure_count: int = 0
        self._game_ctx = self._load_game_context()
        self._system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------ setup

    def _load_game_context(self) -> NarratorGameContext:
        """Read game identity from metadata. Called once at init."""
        meta = self._db.get_all_meta()
        title = meta.get("title", "Untitled") if meta else "Untitled"

        return NarratorGameContext(
            title=title,
        )

    def _build_system_prompt(self) -> str:
        """Construct the session-stable system prompt from game identity."""
        ctx = self._game_ctx
        return _SYSTEM_TEMPLATE.format(
            title=ctx.title,
            tone=ctx.tone or "neutral",
            era=ctx.era or "unspecified",
            setting=ctx.setting or "unspecified",
        )

    # ---------------------------------------------------------------- public API

    def narrate_room(
        self,
        room_id: str,
        room_name: str,
        description: str,
        items: list[dict],
        npcs: list[dict],
        first_visit: bool,
    ) -> str | None:
        """Narrate a room description. Returns prose or None on failure/skip."""
        # Check cache first.
        cache_key = self._make_cache_key(room_id, description, items, npcs)
        cached = self._room_cache.get(room_id)
        if cached and cached[0] == cache_key:
            return cached[1]

        items_text = self._format_item_list(items) if items else "none"
        npcs_text = ", ".join(n.get("name", "someone") for n in npcs) if npcs else "none"
        visit_label = "first visit" if first_visit else "revisit"

        prompt = (
            f"Room: {room_name} ({visit_label})\n"
            f"{description}\n"
            f"Items: {items_text}\n"
            f"NPCs: {npcs_text}"
        )

        prose = self._call_provider(prompt)
        if prose:
            self._room_cache[room_id] = (cache_key, prose)
        return prose

    def narrate_action(
        self, verb: str, target: str | None, messages: list[str]
    ) -> str | None:
        """Narrate an action result. Returns prose or None on failure/skip.

        Caches results by verb + target + message content so repeated actions
        (take/drop the same item) don't re-call the LLM.
        """
        combined = " ".join(messages)

        # Skip narration for short outputs.
        if len(combined) < MIN_NARRATION_LENGTH:
            return None

        # Check action cache.
        cache_key = hashlib.md5(
            f"{verb}:{target}:{combined}".encode()
        ).hexdigest()
        cached = self._action_cache.get(cache_key)
        if cached:
            return cached

        target_text = f" {target}" if target else ""
        prompt = f"{verb}{target_text}: {combined}"

        prose = self._call_provider(prompt)
        if prose:
            self._action_cache[cache_key] = prose
        return prose

    # --------------------------------------------------------------- internals

    def _call_provider(self, prompt: str) -> str | None:
        """Call the LLM provider with the narrator system prompt and turn prompt.

        Returns the prose string on success, None on any failure.
        Never raises -- all exceptions are caught and logged.
        """
        ctx = NarratorContext(
            system_prompt=self._system_prompt,
            theme=self._game_ctx.theme,
            tone=self._game_ctx.tone,
            temperature=0.9,
            max_tokens=4096,
        )
        try:
            result = self._provider.generate_text(
                prompt,
                context=ctx,
            )
            self._failure_count = 0
            return result.strip() if result else None
        except ProviderError as exc:
            self._failure_count += 1
            if self._failure_count == 1:
                logger.warning("Narrator call failed: %s", exc)
            return None
        except Exception as exc:
            self._failure_count += 1
            if self._failure_count == 1:
                logger.warning("Narrator call failed unexpectedly: %s", exc)
            return None

    def _format_item_list(self, items: list[dict]) -> str:
        """Format items for the narrator prompt -- names with descriptions."""
        parts: list[str] = []
        for it in items:
            name = it.get("name", "something")
            desc = it.get("room_description") or it.get("description", "")
            if desc:
                parts.append(f"{name} ({desc})")
            else:
                parts.append(name)
        return ", ".join(parts)

    def _make_cache_key(
        self,
        room_id: str,
        description: str,
        items: list[dict],
        npcs: list[dict],
    ) -> str:
        """Hash room state to detect changes for cache invalidation.

        Uses room_id + item names + NPC names. Deliberately excludes the
        description text because it changes between first visit (long) and
        revisit (short) even when the room state hasn't changed.
        """
        item_names = sorted(i.get("name", "") for i in items)
        npc_names = sorted(n.get("name", "") for n in npcs)
        raw = f"{room_id}:{item_names}:{npc_names}"
        return hashlib.md5(raw.encode()).hexdigest()
