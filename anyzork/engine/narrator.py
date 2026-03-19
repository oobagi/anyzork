"""Narrator -- optional read-only LLM layer for atmospheric prose.

Sits between the engine's deterministic output and the console display.
Cannot change game state. If the LLM call fails for any reason, the engine
falls back to its own deterministic output and the game continues.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from anyzork.generator.providers.base import NarratorContext, ProviderError

if TYPE_CHECKING:
    from anyzork.db.schema import GameDB
    from anyzork.generator.providers.base import BaseProvider

logger = logging.getLogger(__name__)

MIN_NARRATION_LENGTH = 20
MAX_RECENT_ACTIONS = 5


@dataclass
class NarratorGameContext:
    """Cached game identity -- read once from metadata, stable for the session."""

    title: str = "Untitled"
    theme: str = ""
    tone: str = ""
    era: str = ""
    setting: str = ""
    vocabulary_hints: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
You are the narrator of a text adventure game called "{title}".

Theme: {theme}
Tone: {tone}
Era: {era}
Setting: {setting}

Your role:
- Transform the engine's factual output into atmospheric prose that matches \
the game's tone.
- Describe exactly what the engine tells you. Do not add rooms, exits, items, \
NPCs, or information not present in the engine output.
- Do not mention items or exits by mechanical name (e.g., "brass_lantern"). Use \
their display names naturally in prose.
- Do not contradict the engine output. If the engine says a door is locked, \
describe it as locked. If the engine says you took the lantern, confirm it.
- Keep responses concise. Two to four sentences for room descriptions. One to \
two sentences for action results. Never write more than a short paragraph.
- Do not include mechanical information in your prose (score, HP, move count). \
That is displayed separately.
- Do not suggest what the player should do next.

Vocabulary preferences: {vocabulary_csv}

Respond with ONLY the narrated prose. No markdown, no headers, no meta-commentary.\
"""


class Narrator:
    """Read-only LLM layer that flavors engine output with prose.

    Instantiated by the GameEngine when narrator mode is enabled. Holds a
    reference to a :class:`BaseProvider` and builds prompts from engine output.
    The narrator never writes to the database.
    """

    TIMEOUT_SECONDS: float = 5.0

    def __init__(self, provider: BaseProvider, db: GameDB) -> None:
        self._provider = provider
        self._db = db
        self._recent_actions: deque[str] = deque(maxlen=MAX_RECENT_ACTIONS)
        self._room_cache: dict[str, tuple[str, str]] = {}
        self._failure_count: int = 0
        self._game_ctx = self._load_game_context()
        self._system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------ setup

    def _load_game_context(self) -> NarratorGameContext:
        """Read game identity from metadata. Called once at init."""
        meta = self._db.get_all_meta()
        title = meta.get("title", "Untitled") if meta else "Untitled"

        concept: dict = {}
        raw = self._db.get_meta("author_prompt")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    concept = parsed.get("concept", parsed)
            except (json.JSONDecodeError, TypeError):
                pass

        return NarratorGameContext(
            title=title,
            theme=concept.get("theme", ""),
            tone=concept.get("tone", ""),
            era=concept.get("era", ""),
            setting=concept.get("setting", ""),
            vocabulary_hints=concept.get("vocabulary_hints", []),
        )

    def _build_system_prompt(self) -> str:
        """Construct the session-stable system prompt from game identity."""
        ctx = self._game_ctx
        vocab_csv = ", ".join(ctx.vocabulary_hints) if ctx.vocabulary_hints else "none"
        return _SYSTEM_TEMPLATE.format(
            title=ctx.title,
            theme=ctx.theme,
            tone=ctx.tone,
            era=ctx.era,
            setting=ctx.setting,
            vocabulary_csv=vocab_csv,
        )

    # ---------------------------------------------------------------- public API

    @property
    def enabled(self) -> bool:
        """Whether the narrator is active. Always True for a live instance."""
        return True

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
            f"Current room: {room_name}\n"
            f"Room description: {description}\n\n"
            f"Engine output to narrate:\n"
            f"TYPE: room_enter ({visit_label})\n"
            f"DESCRIPTION: {description}\n"
            f"ITEMS PRESENT: {items_text}\n"
            f"NPCS PRESENT: {npcs_text}\n\n"
            f"Recent context:\n{self._format_recent_actions()}"
        )

        prose = self._call_provider(prompt)
        if prose:
            self._room_cache[room_id] = (cache_key, prose)
        return prose

    def narrate_action(
        self, verb: str, target: str | None, messages: list[str]
    ) -> str | None:
        """Narrate an action result. Returns prose or None on failure/skip.

        Also records the action in the history buffer.
        """
        combined = " ".join(messages)

        # Skip narration for short outputs.
        if len(combined) < MIN_NARRATION_LENGTH:
            self._record_action(verb, target, combined)
            return None

        target_text = f" {target}" if target else ""
        prompt = (
            f"Engine output to narrate:\n"
            f"TYPE: action_result\n"
            f"ACTION: {verb}{target_text}\n"
            f"RESULT: {combined}\n\n"
            f"Recent context:\n{self._format_recent_actions()}"
        )

        prose = self._call_provider(prompt)
        self._record_action(verb, target, combined)
        return prose

    def record_action(self, verb: str, target: str | None, result: str) -> None:
        """Record an action in the history buffer (called even when not narrating)."""
        self._record_action(verb, target, result)

    # --------------------------------------------------------------- internals

    def _call_provider(self, prompt: str) -> str | None:
        """Call the LLM provider with the narrator system prompt and turn prompt.

        Returns the prose string on success, None on any failure.
        Never raises -- all exceptions are caught and logged.
        """
        ctx = NarratorContext(
            theme=self._game_ctx.theme,
            tone=self._game_ctx.tone,
            temperature=0.9,
            max_tokens=512,
        )
        try:
            result = self._provider.generate_text(
                self._system_prompt + "\n\n" + prompt,
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

    def _record_action(self, verb: str, target: str | None, result: str) -> None:
        """Append a short action summary to the ring buffer."""
        summary = f"{verb} {target}: {result}" if target else f"{verb}: {result}"
        # Truncate long results to keep the context small.
        if len(summary) > 120:
            summary = summary[:117] + "..."
        self._recent_actions.append(summary)

    def _format_recent_actions(self) -> str:
        """Format the action history for inclusion in the turn prompt."""
        if not self._recent_actions:
            return "(none)"
        return "\n".join(f"- {a}" for a in self._recent_actions)

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
        """Hash room state to detect changes for cache invalidation."""
        item_names = sorted(i.get("name", "") for i in items)
        npc_names = sorted(n.get("name", "") for n in npcs)
        raw = f"{room_id}:{description}:{item_names}:{npc_names}"
        return hashlib.md5(raw.encode()).hexdigest()
