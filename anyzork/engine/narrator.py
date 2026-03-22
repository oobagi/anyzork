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

from anyzork.engine.providers.base import NarratorContext, ProviderError

if TYPE_CHECKING:
    from anyzork.db.schema import GameDB
    from anyzork.engine.providers.base import BaseProvider

logger = logging.getLogger(__name__)

MIN_NARRATION_LENGTH = 20


@dataclass
class NarratorGameContext:
    """Cached game identity -- read once from metadata, stable for the session."""

    title: str = "Untitled"
    author_prompt: str = ""
    realism: str = "medium"


# ---------------------------------------------------------------------------
# System prompt template -- kept tight to reduce token cost.
# The author_prompt line is injected only when the field is non-empty.
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
Narrator for "{title}".{world_line}

Rules: rewrite engine output as grounded prose. Clear, evocative, specific — \
not purple or dramatic. Mention every item and NPC by full name. Add nothing. \
Contradict nothing. Never suggest actions. No markdown. One paragraph.\
"""

# Variant instructions appended per output type so the LLM knows what kind
# of content it is rewriting.  Kept as short fragments.

_VARIANT_ROOM = ""
_VARIANT_ACTION = " Keep it to one or two sentences."
_VARIANT_DIALOGUE = (
    " Rewrite the NPC's speech as natural dialogue. "
    "Preserve every concrete detail and name."
)
_VARIANT_INVENTORY = (
    " Describe what the player is carrying as a brief, "
    "flowing sentence. Name every item."
)
_VARIANT_QUEST = (
    " Summarize the quest status as the player would "
    "think about it. Name every objective."
)
_VARIANT_FEEDBACK = " One sentence, in second person."


class Narrator:
    """Read-only LLM layer that flavors engine output with prose.

    Instantiated by the GameEngine when narrator mode is enabled. Holds a
    reference to a :class:`BaseProvider` and builds prompts from engine output.
    The narrator never writes to the database.
    """

    def __init__(
        self,
        provider: BaseProvider,
        db: GameDB,
        *,
        temperature: float = 0.9,
        max_tokens: int = 4096,
    ) -> None:
        self._provider = provider
        self._db = db
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._room_cache: dict[str, tuple[str, str]] = {}
        self._action_cache: dict[str, str] = {}
        self._failure_count: int = 0
        self._game_ctx = self._load_game_context()
        self._system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------ setup

    def _load_game_context(self) -> NarratorGameContext:
        """Read game identity from metadata. Called once at init."""
        meta = self._db.get_all_meta()
        if not meta:
            return NarratorGameContext()

        return NarratorGameContext(
            title=meta.get("title", "Untitled"),
            author_prompt=meta.get("author_prompt", ""),
            realism=meta.get("realism", "medium"),
        )

    def _build_system_prompt(self) -> str:
        """Construct the session-stable base system prompt from game identity.

        Output-type-specific variant suffixes are appended per-call in
        :meth:`_call_provider`.
        """
        ctx = self._game_ctx

        # Derive a concise world-flavour line from the author prompt.
        world_line = ""
        if ctx.author_prompt:
            # Take the first sentence (or first 120 chars) as a setting hint.
            hint = ctx.author_prompt.split(".")[0].strip()
            if len(hint) > 120:
                hint = hint[:117] + "..."
            world_line = f" Setting: {hint}."

        return _SYSTEM_TEMPLATE.format(
            title=ctx.title,
            world_line=world_line,
        )

    # ---------------------------------------------------------------- public API

    @property
    def failure_count(self) -> int:
        """Number of consecutive provider failures."""
        return self._failure_count

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

        prose = self._call_provider(prompt, _VARIANT_ROOM)
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

        prose = self._call_provider(prompt, _VARIANT_ACTION)
        if prose:
            self._action_cache[cache_key] = prose
        return prose

    def narrate_dialogue(
        self, npc_name: str, content: str, node_id: str
    ) -> str | None:
        """Narrate a dialogue node. Returns prose or None on failure/skip.

        Cached by node_id so revisiting the same dialogue node is free.
        """
        cache_key = f"dlg:{node_id}"
        cached = self._action_cache.get(cache_key)
        if cached:
            return cached

        if len(content) < MIN_NARRATION_LENGTH:
            return None

        prompt = f"{npc_name} says: {content}"
        prose = self._call_provider(prompt, _VARIANT_DIALOGUE)
        if prose:
            self._action_cache[cache_key] = prose
        return prose

    def narrate_inventory(self, items: list[dict]) -> str | None:
        """Narrate an inventory listing. Returns prose or None on failure/skip."""
        if not items:
            return None

        names = [it.get("name", "something") for it in items]
        raw = f"inv:{'|'.join(sorted(names))}"
        cache_key = hashlib.md5(raw.encode()).hexdigest()
        cached = self._action_cache.get(cache_key)
        if cached:
            return cached

        item_lines: list[str] = []
        for it in items:
            desc = it.get("description", "")
            line = it["name"]
            if desc:
                line += f" ({desc})"
            item_lines.append(line)

        prompt = "Inventory: " + ", ".join(item_lines)
        prose = self._call_provider(prompt, _VARIANT_INVENTORY)
        if prose:
            self._action_cache[cache_key] = prose
        return prose

    def narrate_quest_log(self, quest_text: str) -> str | None:
        """Narrate a quest log display. Returns prose or None on failure/skip."""
        if len(quest_text) < MIN_NARRATION_LENGTH:
            return None

        cache_key = hashlib.md5(f"quest:{quest_text}".encode()).hexdigest()
        cached = self._action_cache.get(cache_key)
        if cached:
            return cached

        prompt = f"Quest log:\n{quest_text}"
        prose = self._call_provider(prompt, _VARIANT_QUEST)
        if prose:
            self._action_cache[cache_key] = prose
        return prose

    def narrate_feedback(
        self, verb: str, target: str | None, message: str
    ) -> str | None:
        """Narrate a short system feedback message.

        Unlike narrate_action, this is for single-line outputs like
        "Taken.", "Dropped.", "Unlocked." etc.
        """
        if len(message) < MIN_NARRATION_LENGTH:
            return None

        cache_key = hashlib.md5(
            f"fb:{verb}:{target}:{message}".encode()
        ).hexdigest()
        cached = self._action_cache.get(cache_key)
        if cached:
            return cached

        target_text = f" {target}" if target else ""
        prompt = f"{verb}{target_text}: {message}"
        prose = self._call_provider(prompt, _VARIANT_FEEDBACK)
        if prose:
            self._action_cache[cache_key] = prose
        return prose

    # --------------------------------------------------------------- internals

    def _call_provider(self, prompt: str, variant: str = "") -> str | None:
        """Call the LLM provider with the narrator system prompt and turn prompt.

        Returns the prose string on success, None on any failure.
        Never raises -- all exceptions are caught and logged.
        """
        # Build the system prompt with the output-type variant appended.
        system = self._system_prompt + variant if variant else self._system_prompt

        ctx = NarratorContext(
            system_prompt=system,
            theme="",
            tone="",
            temperature=self._temperature,
            max_tokens=self._max_tokens,
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
        """Format items for the narrator prompt -- names only to save tokens."""
        return ", ".join(it.get("name", "something") for it in items)

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
