"""Dialogue system mixin for GameEngine.

Handles NPC conversations: starting dialogues, rendering dialogue panels,
processing player choices, and applying dialogue-triggered flags/effects.
"""

from __future__ import annotations

import json
import logging

from rich.panel import Panel

logger = logging.getLogger(__name__)


class DialogueMixin:
    """Dialogue handling methods extracted from GameEngine."""

    def _start_dialogue(self, npc_name: str, current_room_id: str) -> None:
        """Initialize dialogue state for an NPC conversation, if available."""
        from anyzork.engine.game import STYLE_NPC, STYLE_SYSTEM, _DialogueState

        db = self.db

        npc = db.find_npc_by_name_any(npc_name, current_room_id)
        if npc is None:
            self.console.print("There's no one here by that name.", style=STYLE_SYSTEM)
            return

        if not npc.get("is_alive", True):
            self.console.print(
                f"{npc['name']} is dead.", style=STYLE_SYSTEM
            )
            return

        # Disposition gating — hostile NPCs refuse conversation.
        disposition = npc.get("disposition", "neutral") or "neutral"
        if disposition == "hostile":
            self.console.print(
                f"{npc['name']} refuses to speak with you.",
                style=STYLE_SYSTEM,
            )
            return

        # NPCs without a dialogue tree use their default_dialogue as a
        # one-liner (e.g. a zombie that can't talk).
        root_node = db.get_root_dialogue_node(npc["id"])
        if root_node is None:
            default = npc.get("default_dialogue", "")
            if default:
                display = default
                if self._narrator is not None:
                    with self.console.status("[dim italic]narrating...[/]", spinner="dots"):
                        narrated = self._narrator.narrate_dialogue(
                            npc["name"], default, f"default:{npc['id']}"
                        )
                    if narrated:
                        from rich.markup import escape
                        display = escape(narrated)
                self.console.print(
                    f"[{STYLE_NPC}]{npc['name']}[/]: {display}"
                )
            else:
                self.console.print(
                    f"{npc['name']} has nothing to say.", style=STYLE_SYSTEM
                )
            return

        # Apply root node flags on entry and emit dialogue_node event.
        self._apply_node_flags(root_node)
        self.db.set_flag(f"_visited_dlg_{root_node['id']}", "true")
        self._emit_event("dialogue_node", node_id=root_node["id"], npc_id=npc["id"])
        self._dialogue_state = _DialogueState(
            npc_id=npc["id"],
            npc_name=npc["name"],
            current_node_id=root_node["id"],
        )
        self._in_dialogue = True

    def _run_dialogue_loop(self) -> None:
        """Drive the CLI dialogue loop using the stateful dialogue API."""
        from rich.prompt import Prompt

        from anyzork.engine.game import STYLE_NPC

        while self._dialogue_state is not None:
            self.console.clear()
            self._render_active_dialogue()
            if self._dialogue_state is None:
                break

            speaker = self._dialogue_state.npc_name
            try:
                choice = Prompt.ask(f"[{STYLE_NPC}]{speaker}[/] [dim]>[/]")
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                self._end_dialogue()
                break

            self._submit_dialogue_choice(choice)

    def _get_dialogue_context(self) -> tuple[dict, dict, list[dict]] | None:
        """Return the current NPC, node, and visible dialogue options."""
        if self._dialogue_state is None:
            return None

        npc = self.db.get_npc(self._dialogue_state.npc_id)
        node = self.db.get_dialogue_node(self._dialogue_state.current_node_id)
        if npc is None or node is None:
            self._end_dialogue()
            return None

        visible_options = self._get_visible_options(node["id"])
        return npc, node, visible_options

    def _render_active_dialogue(self) -> None:
        """Render the current dialogue state, ending immediately if terminal."""
        context = self._get_dialogue_context()
        if context is None:
            return

        npc, node, visible_options = context
        self._render_dialogue_panel(npc, node, visible_options)

    def _submit_dialogue_choice(self, raw: str) -> None:
        """Advance or exit the active dialogue based on the player's input."""
        from anyzork.engine.game import STYLE_SYSTEM

        context = self._get_dialogue_context()
        if context is None:
            return

        npc, _node, visible_options = context

        choice = raw.strip().lower()
        if choice in ("0", "leave", "bye", "exit", "quit"):
            self.console.print()
            self._end_dialogue()
            return

        if not visible_options:
            return

        try:
            choice_num = int(choice)
        except ValueError:
            self.console.print("  Pick a number.", style=STYLE_SYSTEM)
            return

        if choice_num < 1 or choice_num > len(visible_options):
            self.console.print("  Pick a number.", style=STYLE_SYSTEM)
            return

        selected = visible_options[choice_num - 1]
        self._apply_option_flags(selected)

        next_node_id = selected.get("next_node_id")
        if next_node_id is None:
            self.console.print()
            self._end_dialogue()
            return

        next_node = self.db.get_dialogue_node(next_node_id)
        if next_node is None:
            self.console.print()
            self._end_dialogue()
            return

        self._apply_node_flags(next_node)
        self.db.set_flag(f"_visited_dlg_{next_node['id']}", "true")
        self._emit_event("dialogue_node", node_id=next_node["id"], npc_id=npc["id"])
        if self._dialogue_state is None:
            return
        self._dialogue_state.current_node_id = next_node["id"]

    def _handle_force_dialogue(self, npc_id: str, node_id: str) -> None:
        """Force-start a dialogue at a specific node for an NPC.

        Called by the ``force_dialogue`` effect via the event system.
        Renders the dialogue node immediately (non-interactive) so the
        player sees the NPC's reaction text.
        """
        from anyzork.engine.game import _DialogueState

        db = self.db
        npc = db.get_npc(npc_id)
        if npc is None or not npc.get("is_alive", True):
            return

        node = db.get_dialogue_node(node_id)
        if node is None:
            return

        # Apply flags/effects on the forced node.
        self._apply_node_flags(node)
        db.set_flag(f"_visited_dlg_{node_id}", "true")

        # Render the dialogue panel.
        visible_options = self._get_visible_options(node_id)
        self._render_dialogue_panel(npc, node, visible_options)

        # If there are options and we are in interactive mode, enter the
        # dialogue loop so the player can respond.
        if visible_options:
            self._dialogue_state = _DialogueState(
                npc_id=npc["id"],
                npc_name=npc["name"],
                current_node_id=node_id,
            )
            self._in_dialogue = True
            if self._interactive_dialogue:
                self._run_dialogue_loop()

    def _end_dialogue(self) -> None:
        """Clear dialogue state and flush deferred notifications."""
        self._dialogue_state = None
        self._in_dialogue = False
        self._flush_notifications()

    def _get_visible_options(self, node_id: str) -> list[dict]:
        """Return dialogue options visible to the player at this node.

        Filters by required_flags, excluded_flags, and required_items.
        Adds an ``_is_item_gated`` key to options that appeared because
        the player has a required item (for [NEW] tagging).
        """
        db = self.db
        all_options = db.get_dialogue_options(node_id)
        inventory_ids = {item["id"] for item in db.get_inventory()}
        visible: list[dict] = []

        for opt in all_options:
            # Check required_flags -- all must be true.
            req_raw = opt.get("required_flags")
            if req_raw:
                try:
                    required = json.loads(req_raw)
                except (json.JSONDecodeError, TypeError):
                    required = []
                if required and not all(db.has_flag(f) for f in required):
                    continue

            # Check excluded_flags -- if ANY are true, hide this option.
            excl_raw = opt.get("excluded_flags")
            if excl_raw:
                try:
                    excluded = json.loads(excl_raw)
                except (json.JSONDecodeError, TypeError):
                    excluded = []
                if excluded and any(db.has_flag(f) for f in excluded):
                    continue

            # Check required_items -- all must be in inventory.
            items_raw = opt.get("required_items")
            is_item_gated = False
            if items_raw:
                try:
                    req_items = json.loads(items_raw)
                except (json.JSONDecodeError, TypeError):
                    req_items = []
                if req_items:
                    if not all(iid in inventory_ids for iid in req_items):
                        continue
                    is_item_gated = True

            # Copy the dict so we can annotate without mutating DB cache.
            annotated = dict(opt)
            annotated["_is_item_gated"] = is_item_gated
            visible.append(annotated)

        return visible

    def _render_dialogue_panel(
        self,
        npc: dict,
        node: dict,
        visible_options: list[dict],
    ) -> None:
        """Render a dialogue panel showing the NPC's text and options."""
        from anyzork.engine.game import STYLE_NPC

        lines: list[str] = []

        # Narrate the NPC's speech when narrator is active.
        content = node["content"]
        if self._narrator is not None:
            with self.console.status("[dim italic]narrating...[/]", spinner="dots"):
                narrated = self._narrator.narrate_dialogue(
                    npc["name"], content, node["id"]
                )
            if narrated:
                from rich.markup import escape
                content = escape(narrated)

        lines.append(f"\n{content}\n")

        has_terminal = any(opt.get("next_node_id") is None for opt in visible_options)

        for i, opt in enumerate(visible_options, 1):
            tag = " [bright_yellow]\\[NEW][/]" if opt.get("_is_item_gated") else ""
            next_id = opt.get("next_node_id")
            visited = next_id is not None and self.db.has_flag(f"_visited_dlg_{next_id}")
            if visited:
                lines.append(f"  [dim]{i}. {opt['text']}{tag}[/]")
            else:
                lines.append(f"  {i}. {opt['text']}{tag}")

        if not has_terminal:
            lines.append("  0. [dim]\\[Leave][/]")

        body = "\n".join(lines)

        self.console.print(
            Panel(
                body,
                title=f"[{STYLE_NPC}]Talking to {npc['name']}[/]",
                title_align="left",
                border_style=STYLE_NPC,
                padding=(1, 2),
            )
        )

    def _apply_set_flags(self, source: dict) -> None:
        """Set any flags defined in a dialogue node or option."""
        set_raw = source.get("set_flags")
        if not set_raw:
            return
        try:
            flags = json.loads(set_raw)
        except (json.JSONDecodeError, TypeError):
            return
        for flag in flags:
            was_set = self.db.has_flag(flag)
            self.db.set_flag(flag, "true")
            if not was_set:
                self._emit_event("flag_set", flag=flag)

    def _apply_node_flags(self, node: dict) -> None:
        """Set flags and execute effects defined on a dialogue node."""
        self._apply_set_flags(node)
        self._apply_node_effects(node)

    def _apply_node_effects(self, node: dict) -> None:
        """Execute any effects defined in a dialogue node's effects field."""
        from anyzork.engine.commands import evaluate_rule

        effects_raw = node.get("effects")
        if not effects_raw:
            return
        result = evaluate_rule(
            db=self.db,
            effects=effects_raw,
            command_id=f"dialogue:{node['id']}",
            emit_event=self._emit_event,
        )
        for msg in result.messages:
            self.console.print(msg)

    def _apply_option_flags(self, option: dict) -> None:
        """Set any flags defined in a dialogue option's set_flags field."""
        self._apply_set_flags(option)
