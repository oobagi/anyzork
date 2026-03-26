"""Quest system mixin for GameEngine.

Handles quest discovery, objective tracking, completion/failure
notifications, and the quest log display.
"""

from __future__ import annotations

from typing import Any

from rich.panel import Panel


class QuestMixin:
    """Quest management methods extracted from GameEngine."""

    def _init_quest_state(self) -> None:
        """Initialize quest state at game start.

        Auto-discovers the main quest (discovery_flag=NULL) and caches
        the current objective completion states so the tick handler can
        detect changes.
        """
        db = self.db
        all_quests = db.get_all_quests()
        for quest in all_quests:
            if quest["status"] == "undiscovered" and quest["discovery_flag"] is None:
                db.update_quest_status(quest["id"], "active")
            # Cache objective states for active quests.
            if quest["status"] in ("active",) or (
                quest["status"] == "undiscovered" and quest["discovery_flag"] is None
            ):
                objectives = db.get_quest_objectives(quest["id"])
                for obj in objectives:
                    self._objective_cache[obj["id"]] = db.has_flag(obj["completion_flag"])

    def _notify(self, content: Any) -> None:
        """Print or defer a notification depending on dialogue state."""
        if self._in_dialogue:
            self._pending_notifications.append(content)
        else:
            self.console.print(content)

    def _flush_notifications(self) -> None:
        """Print any notifications that were deferred during dialogue."""
        for text in self._pending_notifications:
            self.console.print(text)
        self._pending_notifications.clear()

    def _check_quests(self) -> None:
        """Run the quest state machine: discover, advance, and complete quests."""
        from anyzork.engine.game import (
            STYLE_QUEST_COMPLETE,
            STYLE_QUEST_FAILED,
            STYLE_QUEST_HEADER,
            STYLE_SUCCESS,
        )

        db = self.db
        player = db.get_player()
        if player is None:
            return
        move_num = player["moves"]

        all_quests = db.get_all_quests()

        for quest in all_quests:
            status = quest["status"]

            # Skip completed or failed quests.
            if status in ("completed", "failed"):
                continue

            # --- Undiscovered quests: check for discovery ---
            if status == "undiscovered":
                if quest["discovery_flag"] is None:
                    # Auto-discover (main quest).
                    db.update_quest_status(quest["id"], "active")
                    quest["status"] = "active"
                    # Don't print notification for auto-discovered main quest.
                elif db.has_flag(quest["discovery_flag"]):
                    db.update_quest_status(quest["id"], "active")
                    quest["status"] = "active"
                    self._notify("")
                    self._notify(
                        f"  [{STYLE_QUEST_HEADER}]-- New Quest: {quest['name']} --[/]"
                    )
                    self._notify(f"  {quest['description']}")
                    # Initialize objective cache for newly discovered quest.
                    objectives = db.get_quest_objectives(quest["id"])
                    for obj in objectives:
                        self._objective_cache[obj["id"]] = db.has_flag(obj["completion_flag"])

            # --- Check failure_flag (active or undiscovered) ---
            failure_flag = quest.get("failure_flag")
            if (
                failure_flag
                and db.has_flag(failure_flag)
                and quest["status"] in ("active", "undiscovered")
            ):
                db.update_quest_status(quest["id"], "failed")
                quest["status"] = "failed"
                # Notify if the player was already tracking the quest, or just
                # discovered it this tick (discovery_flag set simultaneously).
                discovered_this_tick = (
                    status == "undiscovered"
                    and quest.get("discovery_flag")
                    and db.has_flag(quest["discovery_flag"])
                )
                if status == "active" or discovered_this_tick:
                    fail_text = quest.get("fail_message") or quest["description"]
                    self._notify("")
                    self._notify(
                        Panel(
                            f"Quest Failed: {quest['name']}\n"
                            f"{fail_text}",
                            style=STYLE_QUEST_FAILED,
                            padding=(1, 2),
                        )
                    )
                continue

            # --- Active quests: check objective progress ---
            if quest["status"] == "active":
                objectives = db.get_quest_objectives(quest["id"])
                required_done = 0
                required_total = 0

                for obj in objectives:
                    current_done = db.has_flag(obj["completion_flag"])
                    was_done = self._objective_cache.get(obj["id"], False)

                    if current_done and not was_done:
                        # Newly completed objective -- notify.
                        req_done_count = sum(
                            1 for o in objectives
                            if not o["is_optional"] and db.has_flag(o["completion_flag"])
                        )
                        req_total_count = sum(1 for o in objectives if not o["is_optional"])
                        self._notify("")
                        self._notify(
                            f"  [{STYLE_QUEST_HEADER}]-- Quest Updated: {quest['name']} --[/]"
                        )
                        self._notify(
                            f"  [{STYLE_SUCCESS}]Completed: {obj['description']} "
                            f"({req_done_count}/{req_total_count})[/]"
                        )

                    self._objective_cache[obj["id"]] = current_done

                    if not obj["is_optional"]:
                        required_total += 1
                        if current_done:
                            required_done += 1

                # Check if all required objectives are done.
                if required_total > 0 and required_done >= required_total:
                    db.update_quest_status(quest["id"], "completed")
                    db.set_flag(quest["completion_flag"], "true")

                    # Award quest score.
                    if quest["score_value"] > 0:
                        db.add_score_entry(
                            f"quest:{quest['id']}",
                            quest["score_value"],
                            move_num,
                        )

                    # Award bonus score for completed optional objectives.
                    for obj in objectives:
                        if (
                            obj["is_optional"]
                            and db.has_flag(obj["completion_flag"])
                            and obj["bonus_score"] > 0
                        ):
                            db.add_score_entry(
                                f"quest_bonus:{obj['id']}",
                                obj["bonus_score"],
                                move_num,
                            )

                    # Print quest completion notification.
                    total_bonus = sum(
                        o["bonus_score"] for o in objectives
                        if o["is_optional"] and db.has_flag(o["completion_flag"])
                    )
                    total_score = quest["score_value"] + total_bonus
                    self._notify("")
                    self._notify(
                        Panel(
                            f"Quest Complete: {quest['name']}\n"
                            f"{quest['description']}\n"
                            + (f"+{total_score} points" if total_score > 0 else ""),
                            style=STYLE_QUEST_COMPLETE,
                            padding=(1, 2),
                        )
                    )

    def _show_quests(self) -> None:
        """Display the player's quest log.

        In narrator mode, the structured quest log is replaced with
        flowing prose that summarizes the player's active objectives.
        """
        from anyzork.engine.game import (
            STYLE_QUEST_HEADER,
            STYLE_ROOM_NAME,
            STYLE_SYSTEM,
        )

        db = self.db
        all_quests = db.get_all_quests()

        # Filter to quests the player knows about (active, completed, failed).
        visible = [q for q in all_quests if q["status"] != "undiscovered"]
        if not visible:
            self.console.print(
                "No quests discovered yet. Explore and talk to people.",
                style=STYLE_SYSTEM,
            )
            return

        # Build a plain-text summary for narrator consumption.
        plain_parts: list[str] = []

        lines: list[str] = []
        lines.append(f"[{STYLE_ROOM_NAME}]{'=' * 12} Quest Log {'=' * 12}[/]")
        lines.append("")

        main_quests = [q for q in visible if q["quest_type"] == "main"]
        side_quests = [q for q in visible if q["quest_type"] == "side"]

        for quest in main_quests:
            lines.append(f"  [{STYLE_QUEST_HEADER}]MAIN QUEST[/]")
            self._format_quest_entry(quest, lines)
            lines.append("")
            plain_parts.append(f"Main: {quest['name']} ({quest['status']}): {quest['description']}")

        if side_quests:
            lines.append(f"  [{STYLE_QUEST_HEADER}]SIDE QUESTS[/]")
            for quest in side_quests:
                self._format_quest_entry(quest, lines)
                lines.append("")
                plain_parts.append(
                    f"Side: {quest['name']} ({quest['status']}): {quest['description']}"
                )

        lines.append(f"[{STYLE_ROOM_NAME}]{'=' * 39}[/]")

        # Narrator path -- replace the structured log with prose.
        if self._narrator is not None and plain_parts:
            with self.console.status("[dim italic]narrating...[/]", spinner="dots"):
                narrated = self._narrator.narrate_quest_log("\n".join(plain_parts))
            if narrated:
                from rich.markup import escape
                self.console.print(escape(narrated))
                return

        for line in lines:
            self.console.print(line)

    def _format_quest_entry(self, quest: dict, lines: list[str]) -> None:
        """Format a single quest entry for the quest log display."""
        from anyzork.engine.game import STYLE_QUEST_COMPLETE, STYLE_SUCCESS

        db = self.db
        status = quest["status"]

        if status == "completed":
            lines.append(
                f"  {quest['name']}            [{STYLE_QUEST_COMPLETE}][COMPLETED][/]"
            )
            lines.append(f"  {quest['description']}")
            return

        if status == "failed":
            lines.append(
                f"  {quest['name']}            [bold red][FAILED][/]"
            )
            fail_msg = quest.get("fail_message")
            lines.append(f"  {fail_msg}" if fail_msg else f"  {quest['description']}")
            return

        # Active quest -- show objectives with checkboxes.
        lines.append(f"  {quest['name']}")
        lines.append(f"  {quest['description']}")

        objectives = db.get_quest_objectives(quest["id"])
        required_total = 0
        required_done = 0
        for obj in objectives:
            done = db.has_flag(obj["completion_flag"])
            check = "[x]" if done else "[ ]"
            optional_tag = " (bonus)" if obj["is_optional"] else ""
            if done:
                lines.append(f"  [{STYLE_SUCCESS}]{check}[/] {obj['description']}{optional_tag}")
            else:
                lines.append(f"  {check} {obj['description']}{optional_tag}")
            if not obj["is_optional"]:
                required_total += 1
                if done:
                    required_done += 1
        lines.append(f"  Progress: {required_done}/{required_total}")
