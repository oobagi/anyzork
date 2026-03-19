"""Main game runtime — the loop that displays rooms, reads input, and dispatches commands.

Uses GameDB for all state and the command resolver for DSL commands.
Rich provides styled terminal output for a polished text adventure experience.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

if TYPE_CHECKING:
    from anyzork.db.schema import GameDB
    from anyzork.engine.narrator import Narrator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Styling palette — every engine-generated label uses these constants so
# colours stay consistent across the entire play session.
#
# Authored prose (room descriptions, take_message, examine_description,
# dialogue content) is deliberately left UNSTYLED — the game designer
# wrote that text and the engine should not override their intent.
# ---------------------------------------------------------------------------

STYLE_ROOM_NAME = "bold bright_white"       # room name in panel title
STYLE_ROOM_BORDER = "bright_blue"           # room panel border
STYLE_TITLE_BORDER = "bright_cyan"          # game title panel border
STYLE_ITEM = "cyan"                         # item names everywhere
STYLE_NPC = "magenta"                       # NPC names everywhere
STYLE_DIRECTION = "green"                   # exit directions (unlocked)
STYLE_DIRECTION_LOCKED = "red"              # exit directions (locked)
STYLE_SYSTEM = "dim"                        # system messages ("You can't do that")
STYLE_LOCKED = "yellow"                     # locked door/container messages
STYLE_SUCCESS = "green"                     # action confirmations (Unlocked, Opened)
STYLE_SCORE_LABEL = "bold"                  # score/moves/HP labels
STYLE_SCORE_VALUE = "green"                 # score breakdown points
STYLE_QUEST_HEADER = "bold bright_cyan"         # quest notification headers
STYLE_QUEST_COMPLETE = "bold bright_green"      # quest completion panel
STYLE_PROMPT = "bold yellow"                # input prompt ">"
STYLE_COMMAND = "cyan"                      # command/verb names in help text
STYLE_VICTORY_BORDER = "bright_green"       # win panel border
STYLE_VICTORY_TITLE = "bold bright_green"   # win panel title
STYLE_DEFEAT_BORDER = "red"                 # lose panel border
STYLE_DEFEAT_TITLE = "bold red"             # lose panel title
STYLE_ERROR = "bold red"                    # fatal errors
STYLE_PROSE = "italic"                      # intro text / authored prose wrapper

# Directions the engine recognises as movement attempts.
# Maps shorthand aliases to canonical direction names.
DIRECTION_ALIASES: dict[str, str] = {
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "u": "up",
    "d": "down",
}

CANONICAL_DIRECTIONS: set[str] = {
    "north", "south", "east", "west",
    "up", "down",
}

# All recognised direction tokens (canonical + aliases).
ALL_DIRECTION_TOKENS: set[str] = CANONICAL_DIRECTIONS | set(DIRECTION_ALIASES.keys())


class GameEngine:
    """Deterministic text-adventure engine.

    Initialised with a :class:`GameDB` instance that holds the entire game
    world and player state.  The engine never writes game content — it only
    reads world data and mutates runtime state (player position, inventory,
    flags, score, moves).
    """

    def __init__(
        self,
        db: GameDB,
        *,
        narrator_enabled: bool = False,
        narrator_provider: str | None = None,
        narrator_model: str | None = None,
    ) -> None:
        self.db = db
        self.console = Console()
        self._running = False
        # Cache of objective completion states from the previous tick.
        # Maps objective_id -> bool (was complete last tick).
        self._objective_cache: dict[str, bool] = {}
        # Narrator -- optional LLM prose layer.
        self._narrator: Narrator | None = None
        self._narrator_requested = narrator_enabled
        self._narrator_provider_override = narrator_provider
        self._narrator_model_override = narrator_model
        self._shown_shortcut_bar = False
        self._has_seen_help = False
        # Event / trigger system — deferred event queue for cascade-safe
        # processing.  See _emit_event() and _process_event().
        self._event_queue: list[tuple[str, dict[str, str]]] = []
        self._processing_events: bool = False

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise player state (if needed), show the intro, and enter the main loop."""

        # Ensure the player row exists.
        player = self.db.get_player()
        if player is None:
            start_room = self.db.get_start_room()
            if start_room is None:
                self.console.print("Error: No start room defined in this game.", style=STYLE_ERROR)
                return
            self.db.init_player(start_room["id"])
            player = self.db.get_player()

        # Show game title and info panel.
        meta = self.db.get_all_meta()
        if meta:
            title = meta.get("title", "Untitled Adventure")
            self.console.print()
            self.console.print(
                Panel(
                    f"[bold italic]{title}[/]",
                    style=STYLE_TITLE_BORDER,
                    expand=False,
                    padding=(1, 4),
                )
            )

            # Compact game info line below the title.
            from anyzork import __version__ as engine_version

            info_parts: list[str] = []
            save_version = meta.get("version", "?")
            if save_version == engine_version:
                info_parts.append(f"v{engine_version}")
            else:
                info_parts.append(
                    f"Engine v{engine_version} | Save v{save_version} \\[outdated]"
                )
            seed = meta.get("seed")
            if seed:
                info_parts.append(f"Seed: {seed}")
            created = meta.get("created_at", "")
            if created and len(created) >= 10:
                info_parts.append(created[:10])
            max_score = meta.get("max_score", 0)
            if max_score:
                info_parts.append(f"Max score: {max_score}")
            # Show active CLI flags.
            if self._narrator_requested:
                narrator_info = "Narrator: on"
                if self._narrator_provider_override:
                    narrator_info += f" ({self._narrator_provider_override}"
                    if self._narrator_model_override:
                        narrator_info += f"/{self._narrator_model_override}"
                    narrator_info += ")"
                info_parts.append(narrator_info)
            if info_parts:
                self.console.print(
                    "  " + "[dim]  |  [/dim]".join(f"[dim]{p}[/dim]" for p in info_parts)
                )

            intro = meta.get("intro_text", "")
            if intro:
                self.console.print()
                self.console.print(intro, style=STYLE_PROSE)

        self.console.print()

        # Initialize narrator if requested via CLI flag, env var, or saved preference.
        if self._narrator_requested or self.db.has_flag("_narrator_enabled"):
            self._init_narrator()

        # Initialize quest state: auto-discover main quest and cache objectives.
        self._init_quest_state()

        # Display the starting room.
        assert player is not None
        self.display_room(player["current_room_id"])
        self._emit_event("room_enter", room_id=player["current_room_id"])

        # Show shortcut bar once after the very first room display.
        if not self._shown_shortcut_bar:
            self.console.print(
                "  [dim]\\[I]nventory  \\[J]ournal  \\[L]ook  \\[H]elp[/]"
            )
            self._shown_shortcut_bar = True

        # Enter the REPL.
        self.main_loop()

    # ------------------------------------------------------------------
    # Main REPL
    # ------------------------------------------------------------------

    def main_loop(self) -> None:
        """Read-eval-print loop: prompt for input, dispatch, repeat."""

        self._running = True

        while self._running:
            player = self.db.get_player()
            if player is None or player["game_state"] != "playing":
                break

            try:
                raw = self.console.input(f"\n[{STYLE_PROMPT}]> [/]")
            except (EOFError, KeyboardInterrupt):
                self.console.print("\nFarewell, adventurer.")
                break

            raw = raw.strip()
            if not raw:
                continue

            tokens = raw.lower().split()
            verb = tokens[0]

            # ---- Built-in commands (handled before DSL) ----

            if verb in ("quit", "exit", "q"):
                self.console.print("Farewell, adventurer.", style=STYLE_SYSTEM)
                break

            if verb in ("look", "l") and len(tokens) == 1:
                self.display_room(player["current_room_id"], force_full=True)
                self._tick()
                continue

            if verb in ("inventory", "i") and len(tokens) == 1:
                self.show_inventory()
                self._tick()
                continue

            if verb == "score" and len(tokens) == 1:
                self._show_score()
                self._tick()
                continue

            if verb == "help" and len(tokens) == 1:
                self.show_help()
                self._has_seen_help = True
                continue  # help doesn't cost a move

            if verb == "save" and len(tokens) == 1:
                self.console.print(
                    "Your game is saved automatically. The [bold].zork[/] file "
                    "[italic]is[/] your save — copy it to back up, or share it with a friend.",
                    style=STYLE_SYSTEM,
                )
                continue  # save info doesn't cost a move

            if verb == "narrator" and len(tokens) >= 2:
                if tokens[1] == "on":
                    if self._narrator is None:
                        self._init_narrator()
                    if self._narrator is not None:
                        self.console.print("Narrator mode enabled.", style=STYLE_SYSTEM)
                        self.db.set_flag("_narrator_enabled", "true")
                    else:
                        self.console.print(
                            "Cannot enable narrator: no API key configured.",
                            style=STYLE_SYSTEM,
                        )
                elif tokens[1] == "off":
                    self._narrator = None
                    self.console.print("Narrator mode disabled.", style=STYLE_SYSTEM)
                    self.db.set_flag("_narrator_enabled", "false")
                else:
                    status = "ON" if self._narrator is not None else "OFF"
                    self.console.print(
                        f"Narrator: {status}. Use 'narrator on' or 'narrator off'.",
                        style=STYLE_SYSTEM,
                    )
                continue  # narrator toggle doesn't cost a move

            if verb in ("quests", "journal", "quest", "j") and len(tokens) == 1:
                self._show_quests()
                continue  # quest log doesn't cost a move

            # ---- Movement ----

            direction = self._parse_direction(tokens)
            if direction is not None:
                self.handle_movement(direction)
                self._tick()
                continue

            # ---- DSL command resolution (checked BEFORE built-in interaction
            # verbs so game-specific commands take priority) ----
            try:
                from anyzork.engine.commands import resolve_command
            except ImportError:
                resolve_command = None  # type: ignore[assignment]

            dsl_handled = False
            if resolve_command is not None:
                result = resolve_command(
                    raw, self.db, player["current_room_id"],
                    emit_event=self._emit_event,
                )
                if result.success:
                    for msg in result.messages:
                        self.console.print(msg)
                    dsl_handled = True
                elif result.messages and result.messages != ["I don't understand that."]:
                    # DSL matched a command but preconditions failed with a
                    # specific failure message (e.g. "You need a loaded gun
                    # to shoot"). Show it so the player gets useful feedback.
                    for msg in result.messages:
                        self.console.print(msg)
                    dsl_handled = True

            if dsl_handled:
                self._tick()
                continue

            # ---- Built-in interaction verbs (fallbacks when no DSL matched) ----

            # take / get / pick up — with "from <container>" support
            if verb in ("take", "get") and len(tokens) >= 2:
                rest_tokens = tokens[1:]
                # Check for "take X from Y" pattern
                if "from" in rest_tokens:
                    from_idx = rest_tokens.index("from")
                    if from_idx > 0 and from_idx < len(rest_tokens) - 1:
                        item_name = " ".join(rest_tokens[:from_idx])
                        container_name = " ".join(rest_tokens[from_idx + 1:])
                        self._handle_take_from(item_name, container_name, player["current_room_id"])
                        self._tick()
                        continue
                item_name = " ".join(rest_tokens)
                self._handle_take(item_name, player["current_room_id"])
                self._tick()
                continue

            if verb == "pick" and len(tokens) >= 3 and tokens[1] == "up":
                item_name = " ".join(tokens[2:])
                self._handle_take(item_name, player["current_room_id"])
                self._tick()
                continue

            # drop
            if verb == "drop" and len(tokens) >= 2:
                item_name = " ".join(tokens[1:])
                self._handle_drop(item_name, player["current_room_id"])
                self._tick()
                continue

            # examine / look at / x
            if verb == "examine" and len(tokens) >= 2:
                target_name = " ".join(tokens[1:])
                self._handle_examine(target_name, player["current_room_id"])
                self._tick()
                continue

            if verb == "x" and len(tokens) >= 2:
                target_name = " ".join(tokens[1:])
                self._handle_examine(target_name, player["current_room_id"])
                self._tick()
                continue

            # read — routes to examine with read_description preference
            if verb == "read" and len(tokens) >= 2:
                target_name = " ".join(tokens[1:])
                self._handle_examine(target_name, player["current_room_id"], prefer_read=True)
                self._tick()
                continue

            # look in / look inside (search container) — must come BEFORE "look at"
            if verb == "look" and len(tokens) >= 3 and tokens[1] in ("in", "inside"):
                target_name = " ".join(tokens[2:])
                self._handle_search(target_name, player["current_room_id"])
                self._tick()
                continue

            if verb == "look" and len(tokens) >= 3 and tokens[1] == "at":
                target_name = " ".join(tokens[2:])
                self._handle_examine(target_name, player["current_room_id"])
                self._tick()
                continue

            # search
            if verb == "search" and len(tokens) >= 2:
                target_name = " ".join(tokens[1:])
                self._handle_search(target_name, player["current_room_id"])
                self._tick()
                continue

            # open
            if verb == "open" and len(tokens) >= 2:
                target_name = " ".join(tokens[1:])
                self._handle_open(target_name, player["current_room_id"])
                self._tick()
                continue

            # unlock (only tries locked exits/containers — won't "open" something already unlocked)
            if verb == "unlock" and len(tokens) >= 2:
                target_name = " ".join(tokens[1:])
                self._handle_unlock(target_name, player["current_room_id"])
                self._tick()
                continue

            # turn on/off {item} — direct state setters
            if verb == "turn" and len(tokens) >= 3 and tokens[1] in ("on", "off"):
                target_state = tokens[1]
                item_name = " ".join(tokens[2:])
                self._handle_turn(item_name, target_state, player["current_room_id"])
                self._tick()
                continue

            # use {item} on {target} — key-on-lock, then interaction matrix, then put-in
            if verb == "use" and len(tokens) >= 2:
                if len(tokens) >= 4 and "on" in tokens:
                    on_idx = tokens.index("on")
                    if on_idx > 1 and on_idx < len(tokens) - 1:
                        item_name = " ".join(tokens[1:on_idx])
                        target_name = " ".join(tokens[on_idx + 1:])
                        # Try key-on-lock first.
                        handled = self._handle_use_on(item_name, target_name, player["current_room_id"])
                        if handled:
                            self._tick()
                            continue
                        # Try interaction matrix second.
                        handled = self._handle_interaction(
                            item_name, target_name, player["current_room_id"]
                        )
                        if handled:
                            self._tick()
                            continue
                        # Fall back to put-in (use ammo on magazine = put ammo in magazine).
                        self._handle_put_in(item_name, target_name, player["current_room_id"])
                        self._tick()
                        continue
                else:
                    # "use X" without "on Y" — toggle if toggleable, else syntax hint
                    item_name = " ".join(tokens[1:])
                    self._handle_use_bare(item_name, player["current_room_id"])
                    self._tick()
                    continue

            # put / place <item> in/into/inside/on <container>
            if verb in ("put", "place") and len(tokens) >= 4:
                # Try DSL first (catches placement puzzles like "put crystal on altar")
                if resolve_command is not None:
                    result = resolve_command(
                        raw, self.db, player["current_room_id"],
                        emit_event=self._emit_event,
                    )
                    if result.success:
                        for msg in result.messages:
                            self.console.print(msg)
                        self._tick()
                        continue
                # Fall through to built-in container handling
                rest_tokens = tokens[1:]
                # Find the split word: "in", "into", "inside", or "on"
                split_idx = None
                for i, t in enumerate(rest_tokens):
                    if t in ("in", "into", "inside", "on"):
                        split_idx = i
                        break
                if split_idx is not None and split_idx > 0 and split_idx < len(rest_tokens) - 1:
                    item_name = " ".join(rest_tokens[:split_idx])
                    container_name = " ".join(rest_tokens[split_idx + 1:])
                    self._handle_put_in(item_name, container_name, player["current_room_id"])
                    self._tick()
                    continue

            # talk to
            if verb == "talk" and len(tokens) >= 3 and tokens[1] == "to":
                npc_name = " ".join(tokens[2:])
                self._enter_dialogue(npc_name, player["current_room_id"])
                self._tick()
                continue

            if verb == "talk" and len(tokens) >= 2 and tokens[1] != "to":
                npc_name = " ".join(tokens[1:])
                self._enter_dialogue(npc_name, player["current_room_id"])
                self._tick()
                continue

            # ---- Nothing matched ----
            if not self._has_seen_help:
                self.console.print(
                    "I don't understand that. Type 'help' for available commands.",
                    style=STYLE_SYSTEM,
                )
                self._has_seen_help = True
            else:
                self.console.print("I don't understand that.", style=STYLE_SYSTEM)
            self._tick()

    # ------------------------------------------------------------------
    # Room display
    # ------------------------------------------------------------------

    @staticmethod
    def _highlight_interactables(
        text: str, items: list[dict], npcs: list[dict]
    ) -> str:
        """Highlight item and NPC names in room description text.

        Performs case-insensitive replacement, longest names first to avoid
        partial matches (e.g., "AR-15 rifle" before "AR-15").
        """
        # Collect all names, longest first.
        names: list[tuple[str, str]] = []  # (name, style)
        for it in items:
            names.append((it["name"], STYLE_ITEM))
        for npc in npcs:
            names.append((npc["name"], STYLE_NPC))
        names.sort(key=lambda x: len(x[0]), reverse=True)

        for name, style in names:
            # Case-insensitive replace, preserving original case.
            import re as _re
            pattern = _re.compile(_re.escape(name), _re.IGNORECASE)
            text = pattern.sub(f"[{style}]{name}[/]", text)
        return text

    def _is_room_lit(self, room: dict) -> bool:
        """Return ``True`` if the room is visible to the player.

        A room is lit when it is not marked dark, or when the player
        carries an active light source (an inventory item tagged
        ``light_source`` with ``toggle_state = 'on'``).
        """
        if not room.get("is_dark"):
            return True
        if self.db.get_active_light_sources():
            return True
        return False

    def display_room(self, room_id: str, *, force_full: bool = False) -> None:
        """Render a room to the console.

        On the first visit (or when *force_full* is ``True``), the full
        description is shown.  On revisits, the short description is used.
        Dark rooms show a limited view unless the player has a light source.
        """
        room = self.db.get_room(room_id)
        if room is None:
            self.console.print(f"Room '{room_id}' not found.", style=STYLE_ERROR)
            return

        player = self.db.get_player()
        move_num = player["moves"] if player else 0

        # Record the visit and decide which description to show.
        first_visit = self.db.record_visit(room_id, move_num)

        # --- Dark room handling ---
        lit = self._is_room_lit(room)
        if not lit:
            # Dark and unlit — show limited view.
            self.console.print(
                Panel(
                    "It's pitch black. You can't see a thing.",
                    title=f"[{STYLE_ROOM_NAME}]{room['name']}[/]",
                    title_align="left",
                    border_style=STYLE_ROOM_BORDER,
                    padding=(1, 2),
                )
            )
            # Exits with direction only (no destination) — the player can feel walls.
            exits = self.db.get_exits(room_id)
            if exits:
                exit_strs = [
                    f"[{STYLE_DIRECTION}]{ex['direction']}[/]" for ex in exits
                ]
                self.console.print(
                    "[bold]Exits:[/] " + "  |  ".join(exit_strs)
                )
            return

        # --- Normal (lit) room rendering ---

        # Build the room body text.
        parts: list[str] = []

        if first_visit and room.get("first_visit_text"):
            parts.append(room["first_visit_text"])

        if first_visit or force_full:
            parts.append(room["description"])
        else:
            parts.append(room.get("short_description") or room["description"])

        # Append dynamic item prose: items with a room_description blend
        # into the room body text.  Items without one go in the "You see:"
        # list below the panel.
        items = self.db.get_items_in("room", room_id)
        prose_items: list[str] = []
        list_items: list[dict] = []
        for it in items:
            home = it.get("home_room_id")
            if home == room_id and it.get("room_description"):
                # Item is in its authored home — use bespoke prose
                prose_items.append(it["room_description"])
            elif it.get("drop_description"):
                # Item is away from home (or has no home) — use generic prose
                prose_items.append(it["drop_description"])
            else:
                # No prose at all — fall back to name list
                list_items.append(it)

        if prose_items:
            parts.append(" ".join(prose_items))

        # NPCs present — fetched early because the narrator needs them.
        npcs = self.db.get_npcs_in(room_id)

        body = "\n\n".join(parts)

        # If this is a dark room illuminated by a light source, note it.
        light_note = ""
        if room.get("is_dark"):
            active_lights = self.db.get_active_light_sources()
            if active_lights:
                light_name = active_lights[0]["name"]
                light_note = f"\n\n[{STYLE_SYSTEM}](illuminated by your {light_name})[/]"

        # Attempt narration if the narrator is active.
        display_body = body
        if self._narrator is not None:
            with self.console.status("[dim italic]the narrator contemplates...[/]", spinner="dots"):
                narrated = self._narrator.narrate_room(
                    room_id=room_id,
                    room_name=room["name"],
                    description=body,
                    items=items,
                    npcs=npcs,
                    first_visit=first_visit,
                )
            if narrated:
                # Escape Rich markup in LLM output (e.g., [15] in "AR-15").
                from rich.markup import escape
                display_body = escape(narrated)
            elif self._narrator._failure_count == 1:
                self.console.print(
                    "(Narrator unavailable for this turn -- showing engine output.)",
                    style=STYLE_SYSTEM,
                )

        # Highlight interactable names in the room body.
        all_npcs = self.db.get_npcs_in(room_id)
        display_body = self._highlight_interactables(display_body, items, all_npcs)

        # Display the room panel.
        self.console.print(
            Panel(
                display_body + light_note,
                title=f"[{STYLE_ROOM_NAME}]{room['name']}[/]",
                title_align="left",
                border_style=STYLE_ROOM_BORDER,
                padding=(1, 2),
            )
        )

        # Exits.
        exits = self.db.get_exits(room_id)
        if exits:
            exit_strs: list[str] = []
            for ex in exits:
                direction_label = ex["direction"]
                dest_name = ex.get("to_room_name", "???")
                if ex.get("is_locked"):
                    exit_strs.append(
                        f"[{STYLE_DIRECTION_LOCKED}]{direction_label}[/]"
                        f" [{STYLE_LOCKED}](locked)[/]"
                    )
                else:
                    exit_strs.append(
                        f"[{STYLE_DIRECTION}]{direction_label}[/] — {dest_name}"
                    )
            self.console.print(
                "[bold]Exits:[/] " + "  |  ".join(exit_strs)
            )

        # Items in room (only those without room_description).
        if list_items:
            item_names = ", ".join(f"[{STYLE_ITEM}]{it['name']}[/]" for it in list_items)
            self.console.print(f"[bold]You see:[/] {item_names}")

        # NPCs present (already fetched above for the narrator).
        if npcs:
            npc_names = ", ".join(f"[{STYLE_NPC}]{npc['name']}[/]" for npc in npcs)
            self.console.print(f"[bold]Present:[/] {npc_names}")

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def handle_movement(self, direction: str) -> None:
        """Attempt to move the player in *direction*."""
        player = self.db.get_player()
        if player is None:
            return

        current_room = player["current_room_id"]
        exit_row = self.db.get_exit_by_direction(current_room, direction)

        if exit_row is None:
            self.console.print("You can't go that way.", style=STYLE_SYSTEM)
            return

        # Locked?
        if exit_row.get("is_locked"):
            lock = self.db.get_lock_for_exit(exit_row["id"])
            raw_msg = lock["locked_message"] if lock else "The way is blocked."
            self.console.print(raw_msg, style=STYLE_LOCKED)
            return

        # Move the player.
        dest_room_id = exit_row["to_room_id"]
        self.db.update_player(current_room_id=dest_room_id)
        self.display_room(dest_room_id)
        self._emit_event("room_enter", room_id=dest_room_id)

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    def show_inventory(self) -> None:
        """Display the player's inventory as a styled table."""
        items = self.db.get_inventory()

        if not items:
            self.console.print("You are empty-handed.", style=STYLE_SYSTEM)
            return

        table = Table(
            title="Inventory",
            title_style=STYLE_ROOM_NAME,
            border_style=STYLE_SYSTEM,
            show_lines=False,
        )
        table.add_column("Item", style=STYLE_ITEM)
        table.add_column("Description", style=STYLE_SYSTEM)

        for item in items:
            desc = item["description"]
            # Append toggle state indicator.
            if item.get("toggle_state"):
                desc += f" [{item['toggle_state']}]"
            # Append quantity indicator.
            if item.get("quantity") is not None:
                unit = item.get("quantity_unit") or "units"
                max_qty = item.get("max_quantity")
                if max_qty is not None:
                    desc += f" {item['quantity']}/{max_qty} {unit}"
                else:
                    desc += f" {item['quantity']} {unit}"
            table.add_row(item["name"], desc)

        self.console.print(table)

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    def _show_score(self) -> None:
        """Display the current score and breakdown."""
        player = self.db.get_player()
        if player is None:
            return

        meta = self.db.get_all_meta()
        max_score = meta.get("max_score", 0) if meta else 0

        self.console.print(
            f"[{STYLE_SCORE_LABEL}]Score:[/] {player['score']} / {max_score}   "
            f"[{STYLE_SCORE_LABEL}]Moves:[/] {player['moves']}   "
            f"[{STYLE_SCORE_LABEL}]HP:[/] {player['hp']} / {player['max_hp']}"
        )

        breakdown = self.db.get_score_breakdown()
        if breakdown:
            table = Table(
                title="Score Breakdown",
                title_style=STYLE_SCORE_LABEL,
                border_style=STYLE_SYSTEM,
                show_lines=False,
            )
            table.add_column("Reason", style=STYLE_ITEM)
            table.add_column("Points", style=STYLE_SCORE_VALUE, justify="right")
            table.add_column("Move #", style=STYLE_SYSTEM, justify="right")
            for entry in breakdown:
                table.add_row(entry["reason"], str(entry["value"]), str(entry["move_number"]))
            self.console.print(table)

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def show_help(self) -> None:
        """List built-in commands and game-specific DSL commands."""

        c = STYLE_COMMAND  # shorthand for readability in the help block
        narrator_status = "ON" if self._narrator is not None else "OFF"
        sections = (
            "[bold]Built-in commands[/]\n"
            f"  [{c}]look[/] (l)           — redisplay the current room\n"
            f"  [{c}]inventory[/] (i)      — show what you're carrying\n"
            f"  [{c}]score[/]              — show your score and stats\n"
            f"  [{c}]quests[/] (j)          — view your quest log\n"
            f"  [{c}]narrator on[/]/[{c}]off[/]    — toggle narrator mode (currently {narrator_status})\n"
            f"  [{c}]save[/]               — how saving works\n"
            f"  [{c}]help[/]               — this message\n"
            f"  [{c}]quit[/] / [{c}]exit[/]        — leave the game\n"
            "\n"
            "[bold]Interaction[/]\n"
            f"  [{c}]take[/] / [{c}]get[/] / [{c}]pick up[/] {{item}}  — pick up an item\n"
            f"  [{c}]take[/] {{item}} [{c}]from[/] {{container}}  — take from a container\n"
            f"  [{c}]drop[/] {{item}}        — drop an item from inventory\n"
            f"  [{c}]examine[/] / [{c}]x[/] / [{c}]look at[/] {{thing}}  — examine something closely\n"
            f"  [{c}]read[/] {{item}}        — read a document or inscription\n"
            f"  [{c}]open[/] {{thing}}       — open a container or locked exit\n"
            f"  [{c}]unlock[/] {{thing}}     — try to unlock something locked\n"
            f"  [{c}]use[/] {{item}} [{c}]on[/] {{thing}}  — use an item on something\n"
            f"  [{c}]turn on[/]/[{c}]off[/] {{item}}  — toggle an item on or off\n"
            f"  [{c}]search[/] / [{c}]look in[/] {{container}}  — search inside a container\n"
            f"  [{c}]put[/] {{item}} [{c}]in[/] {{container}}  — put something into a container\n"
            f"  [{c}]talk to[/] {{npc}}      — start a conversation\n"
            "\n"
            "[bold]Movement[/]\n"
            f"  Type a direction: [{c}]north[/], [{c}]south[/], [{c}]east[/], "
            f"[{c}]west[/], [{c}]up[/], [{c}]down[/]\n"
            f"  Shortcuts: [{c}]n[/] [{c}]s[/] [{c}]e[/] [{c}]w[/] [{c}]u[/] [{c}]d[/]"
        )

        # Append game-specific DSL commands.
        game_cmds = self._get_dsl_help_lines()
        if game_cmds:
            sections += "\n\n[bold]Game commands[/]\n" + game_cmds

        self.console.print(
            Panel(
                sections,
                title=f"[{STYLE_ROOM_NAME}]Help[/]",
                title_align="left",
                border_style=STYLE_ROOM_BORDER,
                padding=(1, 2),
            )
        )

    def _get_dsl_help_lines(self) -> str:
        """Build help text from DSL commands in the database.

        Shows unique patterns grouped by verb, excluding patterns that
        duplicate built-in verbs (take, drop, open, etc.).
        """
        builtin_verbs = {
            "take", "get", "pick", "drop", "examine", "x", "look",
            "read", "open", "unlock", "use", "search", "put", "place",
            "talk", "go", "north", "south", "east", "west", "up", "down",
            "turn",
        }
        commands = self.db.get_all_commands()
        seen_patterns: set[str] = set()
        lines: list[str] = []
        c = STYLE_COMMAND

        for cmd in commands:
            verb = cmd.get("verb", "")
            pattern = cmd.get("pattern", "")
            if verb in builtin_verbs:
                continue
            if pattern in seen_patterns:
                continue
            seen_patterns.add(pattern)

            # Style the pattern: make literal words cyan, keep {slots} plain
            parts = re.split(r"(\{[^}]+\})", pattern)
            styled = "".join(
                f"[{c}]{p}[/]" if not p.startswith("{") else p
                for p in parts
            )
            lines.append(f"  {styled}")

        return "\n".join(lines)


    # ------------------------------------------------------------------
    # Quest log
    # ------------------------------------------------------------------

    def _show_quests(self) -> None:
        """Display the player's quest log."""
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

        lines: list[str] = []
        lines.append(f"[{STYLE_ROOM_NAME}]{'=' * 12} Quest Log {'=' * 12}[/]")
        lines.append("")

        main_quests = [q for q in visible if q["quest_type"] == "main"]
        side_quests = [q for q in visible if q["quest_type"] == "side"]

        for quest in main_quests:
            lines.append(f"  [{STYLE_QUEST_HEADER}]MAIN QUEST[/]")
            self._format_quest_entry(quest, lines)
            lines.append("")

        if side_quests:
            lines.append(f"  [{STYLE_QUEST_HEADER}]SIDE QUESTS[/]")
            for quest in side_quests:
                self._format_quest_entry(quest, lines)
                lines.append("")

        lines.append(f"[{STYLE_ROOM_NAME}]{'=' * 39}[/]")

        for line in lines:
            self.console.print(line)

    def _format_quest_entry(self, quest: dict, lines: list[str]) -> None:
        """Format a single quest entry for the quest log display."""
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
            lines.append(f"  {quest['description']}")
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

    # ------------------------------------------------------------------
    # Built-in interaction verbs
    # ------------------------------------------------------------------

    def _find_accessible_item(self, name: str, current_room_id: str) -> dict | None:
        """Find an item by name, searching room, inventory, and one level into accessible containers.

        Search order:
        1. Room items.
        2. Inventory items.
        3. Items inside open/lid-less, unlocked containers in the room.
        4. Items inside open/lid-less, unlocked containers in inventory.
        """
        db = self.db

        # 1. Room items.
        item = db.find_item_by_name(name, "room", current_room_id)
        if item is not None:
            return item

        # 2. Inventory items.
        item = db.find_item_by_name(name, "inventory", "")
        if item is not None:
            return item

        # 3. Inside accessible containers in the room.
        for container in db.get_open_containers_in_room(current_room_id):
            found = db.find_item_in_container(name, container["id"])
            if found is not None:
                return found

        # 4. Inside accessible containers in inventory.
        for inv_item in db.get_inventory():
            if (
                inv_item.get("is_container")
                and (inv_item.get("is_open") or not inv_item.get("has_lid"))
                and not inv_item.get("is_locked")
            ):
                found = db.find_item_in_container(name, inv_item["id"])
                if found is not None:
                    return found

        return None

    @staticmethod
    def _container_hint(child: dict, db: GameDB) -> str:
        """Return a hint suffix for a child item that is itself a non-empty, accessible container.

        Returns ``" (contains items)"`` when the child is a container that is
        open or lid-less, not locked, and has at least one visible item inside.
        Returns ``""`` otherwise.
        """
        if not child.get("is_container"):
            return ""
        if child.get("is_locked"):
            return ""
        if not child.get("is_open") and child.get("has_lid"):
            return ""
        contents = db.get_container_contents(child["id"])
        if contents:
            return " (contains items)"
        return ""

    def _handle_take(self, item_name: str, current_room_id: str) -> None:
        """Pick up a takeable item from the current room or open containers."""
        db = self.db

        # Check if the item is in the current room.
        item = db.find_item_by_name(item_name, "room", current_room_id)
        if item is not None:
            if not item["is_takeable"]:
                self.console.print("You can't take that.", style=STYLE_SYSTEM)
                return
            db.move_item(item["id"], "inventory", "")
            msg = item.get("take_message") or "Taken."
            self.console.print(msg)
            self._emit_event("item_taken", item_id=item["id"])
            return

        # Not found directly in room — search inside open containers.
        open_containers = db.get_open_containers_in_room(current_room_id)
        for container in open_containers:
            found = db.find_item_in_container(item_name, container["id"])
            if found is not None:
                if not found["is_takeable"]:
                    self.console.print("You can't take that.", style=STYLE_SYSTEM)
                    return
                db.take_item_from_container(found["id"])
                msg = found.get("take_message") or "Taken."
                self.console.print(msg)
                self._emit_event("item_taken", item_id=found["id"])
                return

        # Maybe they already have it?
        inv_item = db.find_item_by_name(item_name, "inventory", "")
        if inv_item:
            self.console.print("You're already carrying that.", style=STYLE_SYSTEM)
        else:
            self.console.print("You don't see that here.", style=STYLE_SYSTEM)

    def _handle_drop(self, item_name: str, current_room_id: str) -> None:
        """Drop an inventory item into the current room."""
        db = self.db

        item = db.find_item_by_name(item_name, "inventory", "")
        if item is None:
            self.console.print("You're not carrying that.", style=STYLE_SYSTEM)
            return

        db.move_item(item["id"], "room", current_room_id)
        msg = item.get("drop_message") or "Dropped."
        self.console.print(msg)
        self._emit_event("item_dropped", item_id=item["id"], room_id=current_room_id)

    def _handle_examine(
        self, target_name: str, current_room_id: str, *, prefer_read: bool = False
    ) -> None:
        """Examine an item, NPC, or room feature.

        When *prefer_read* is ``True`` (triggered by the ``read`` verb), the
        item's ``read_description`` is shown if it exists; otherwise falls back
        to ``examine_description``.
        """
        db = self.db

        # Find the target in the room, inventory, or inside accessible containers.
        item = self._find_accessible_item(target_name, current_room_id)

        if item is not None:
            if prefer_read and item.get("read_description"):
                desc = item["read_description"]
            else:
                desc = item.get("examine_description") or item.get("description", "")
            self.console.print(desc)

            # Toggle state appendix.
            if item.get("is_toggleable") and item.get("toggle_state"):
                self.console.print(
                    f"Status: {item['toggle_state']}", style=STYLE_SYSTEM
                )

            # Quantity appendix.
            if item.get("quantity") is not None:
                unit = item.get("quantity_unit") or "units"
                max_qty = item.get("max_quantity")
                qty = item["quantity"]
                if qty <= 0:
                    depl_msg = item.get("depleted_message") or "It's empty."
                    self.console.print(depl_msg, style=STYLE_SYSTEM)
                elif item.get("quantity_description"):
                    tmpl = item["quantity_description"]
                    self.console.print(
                        tmpl.format(
                            item=item["name"], quantity=qty, unit=unit
                        )
                    )
                elif max_qty is not None:
                    self.console.print(
                        f"Ammo: {qty}/{max_qty} {unit}", style=STYLE_SYSTEM
                    )
                else:
                    self.console.print(
                        f"It has {qty} {unit}.", style=STYLE_SYSTEM
                    )

            # Container state appendix.
            if item.get("is_container"):
                if item.get("is_locked"):
                    self.console.print("It is locked.", style=STYLE_LOCKED)
                elif not item.get("is_open") and item.get("has_lid"):
                    self.console.print("It is closed.", style=STYLE_SYSTEM)
                else:
                    # Open or lid-less — show contents.
                    contents = db.get_container_contents(item["id"])
                    if contents:
                        names = ", ".join(
                            f"[{STYLE_ITEM}]{c['name']}[/]"
                            f"{self._container_hint(c, db)}"
                            for c in contents
                        )
                        self.console.print(f"Inside, you see: {names}.")
                    else:
                        self.console.print("It's empty.", style=STYLE_SYSTEM)

            return

        # Check NPCs in the current room.
        npc = db.find_npc_by_name(target_name, current_room_id)
        if npc is not None:
            desc = npc.get("examine_description") or npc.get("description", "")
            self.console.print(desc)
            return

        self.console.print("You don't see that here.", style=STYLE_SYSTEM)

    def _handle_open(self, target_name: str, current_room_id: str) -> None:
        """Try to open/unlock something — checks locked exits, then containers."""
        db = self.db
        target_lower = target_name.lower().strip()

        # Resolve direction aliases ("n" -> "north", etc.)
        canonical = DIRECTION_ALIASES.get(target_lower, target_lower)

        locks = db.get_locks_in_room(current_room_id)

        # 1. Try matching against direction name (including aliases).
        for lock in locks:
            direction = lock.get("direction", "").lower()
            if direction == canonical or direction == target_lower:
                self._try_unlock(lock)
                return

        # 2. Try matching lock/exit description text.
        for lock in locks:
            lock_desc = (lock.get("description") or "").lower()
            if target_lower in lock_desc:
                self._try_unlock(lock)
                return

        # 3. Try matching a container item in the room or inventory.
        item = db.find_item_by_name(target_name, "room", current_room_id)
        if item is None:
            item = db.find_item_by_name(target_name, "inventory", "")
        if item is not None and item.get("is_container"):
            if item.get("is_locked"):
                msg = item.get("lock_message") or "It's locked."
                self.console.print(msg, style=STYLE_LOCKED)
                return
            if item.get("is_open"):
                self.console.print("It's already open.", style=STYLE_SYSTEM)
                return
            if not item.get("has_lid"):
                self.console.print("It doesn't need to be opened.", style=STYLE_SYSTEM)
                return
            # Open the container.
            db.open_container(item["id"])
            msg = item.get("open_message") or f"You open the {item['name']}."
            self.console.print(msg, style=STYLE_SUCCESS)
            return

        self.console.print("You can't open that.", style=STYLE_SYSTEM)

    def _handle_unlock(self, target_name: str, current_room_id: str) -> None:
        """Try to unlock something — only handles locked exits and containers."""
        db = self.db
        target_lower = target_name.lower().strip()
        canonical = DIRECTION_ALIASES.get(target_lower, target_lower)

        # 1. Check locked exits.
        locks = db.get_locks_in_room(current_room_id)
        for lock in locks:
            direction = lock.get("direction", "").lower()
            if direction == canonical or direction == target_lower:
                self._try_unlock(lock)
                return

        for lock in locks:
            lock_desc = (lock.get("description") or "").lower()
            if target_lower in lock_desc:
                self._try_unlock(lock)
                return

        # 2. Check locked containers.
        item = db.find_item_by_name(target_name, "room", current_room_id)
        if item is not None and item.get("is_container"):
            if item.get("is_locked"):
                key_id = item.get("key_item_id")
                if key_id:
                    inventory = db.get_inventory()
                    has_key = any(i["id"] == key_id for i in inventory)
                    if has_key:
                        db.open_container(item["id"])
                        if item.get("consume_key"):
                            db.remove_item(key_id)
                        msg = item.get("unlock_message") or "Unlocked."
                        self.console.print(msg)
                        # Auto-list container contents after unlock.
                        contents = db.get_container_contents(item["id"])
                        if contents:
                            names = ", ".join(
                                f"[{STYLE_ITEM}]{c['name']}[/]" for c in contents
                            )
                            self.console.print(
                                f"Inside the [{STYLE_ITEM}]{item['name']}[/]: {names}."
                            )
                        return
                msg = item.get("lock_message") or "It's locked."
                self.console.print(msg, style=STYLE_LOCKED)
                return
            self.console.print("It's not locked.", style=STYLE_SYSTEM)
            return

        self.console.print("There's nothing to unlock.", style=STYLE_SYSTEM)

    def _try_unlock(self, lock: dict) -> None:
        """Attempt to unlock a lock — checks if player has the key."""
        db = self.db

        if lock.get("lock_type") == "key" and lock.get("key_item_id"):
            key_item_id = lock["key_item_id"]
            # Check if the player has the key item.
            inventory = db.get_inventory()
            has_key = any(i["id"] == key_item_id for i in inventory)

            if has_key:
                # Unlock it.
                result = db.unlock(lock["id"])
                if lock.get("consume_key"):
                    db.remove_item(key_item_id)
                msg = lock.get("unlock_message", "")
                if msg:
                    self.console.print(msg, style=STYLE_SUCCESS)
                else:
                    self.console.print("Unlocked.", style=STYLE_SUCCESS)
            else:
                msg = lock.get("locked_message", "")
                if msg:
                    self.console.print(msg, style=STYLE_LOCKED)
                else:
                    self.console.print("It's locked.", style=STYLE_LOCKED)
        else:
            # Non-key lock (puzzle, state, etc.) — just show the locked message.
            msg = lock.get("locked_message", "")
            if msg:
                self.console.print(msg, style=STYLE_LOCKED)
            else:
                self.console.print("It's locked.", style=STYLE_LOCKED)

    def _handle_use_on(
        self, item_name: str, target_name: str, current_room_id: str
    ) -> bool:
        """Built-in handler for ``use {item} on {target}`` — key-on-lock patterns.

        Checks whether the item is a key for a locked exit or locked container
        in the current room. If so, performs the unlock and returns ``True``.
        Returns ``False`` if this is not a key-on-lock interaction, so the
        caller can fall through to other handlers.
        """
        db = self.db

        # Find the item in inventory (fuzzy match).
        inv_item = db.find_item_by_name(item_name, "inventory", "")
        if inv_item is None:
            return False

        # --- Try locked exits in the room ---
        locks = db.get_locks_in_room(current_room_id)
        target_lower = target_name.lower().strip()
        canonical = DIRECTION_ALIASES.get(target_lower, target_lower)

        for lock in locks:
            if lock.get("key_item_id") != inv_item["id"]:
                continue
            # Check if target matches the direction or lock description.
            direction = lock.get("direction", "").lower()
            lock_desc = (lock.get("description") or "").lower()
            if direction == canonical or direction == target_lower or target_lower in lock_desc:
                # Unlock the exit.
                db.unlock(lock["id"])
                if lock.get("consume_key"):
                    db.remove_item(inv_item["id"])
                msg = lock.get("unlock_message", "")
                if msg:
                    self.console.print(msg, style=STYLE_SUCCESS)
                else:
                    self.console.print("Unlocked.", style=STYLE_SUCCESS)
                return True

        # Also try matching target against exit description text.
        for lock in locks:
            if lock.get("key_item_id") != inv_item["id"]:
                continue
            # Check against exit description via the exits table
            exit_row = db.get_exit_by_direction(current_room_id, lock.get("direction", ""))
            if exit_row:
                exit_desc = (exit_row.get("description") or "").lower()
                if target_lower in exit_desc:
                    db.unlock(lock["id"])
                    if lock.get("consume_key"):
                        db.remove_item(inv_item["id"])
                    msg = lock.get("unlock_message", "")
                    if msg:
                        self.console.print(msg, style=STYLE_SUCCESS)
                    else:
                        self.console.print("Unlocked.", style=STYLE_SUCCESS)
                    return True

        # --- Try locked containers in the room ---
        container = db.find_item_by_name(target_name, "room", current_room_id)
        if container is not None and container.get("is_container") and container.get("is_locked"):
            if container.get("key_item_id") == inv_item["id"]:
                # Unlock and open the container.
                db.open_container(container["id"])
                if container.get("consume_key"):
                    db.remove_item(inv_item["id"])
                msg = container.get("unlock_message") or f"You unlock the {container['name']}."
                self.console.print(msg, style=STYLE_SUCCESS)
                return True

        return False

    def _handle_search(self, target_name: str, current_room_id: str) -> None:
        """Search a container — open if needed, then list contents."""
        db = self.db

        # Find the target in the room, inventory, or inside accessible containers.
        item = self._find_accessible_item(target_name, current_room_id)
        if item is None:
            self.console.print("You don't see that here.", style=STYLE_SYSTEM)
            return

        if not item.get("is_container"):
            self.console.print("There's nothing to search.", style=STYLE_SYSTEM)
            return

        # Locked?
        if item.get("is_locked"):
            msg = item.get("lock_message") or "It's locked."
            self.console.print(msg, style=STYLE_LOCKED)
            return

        # Closed with a lid? Open it first.
        if not item.get("is_open") and item.get("has_lid"):
            db.open_container(item["id"])
            msg = item.get("open_message") or f"You open the {item['name']}."
            self.console.print(msg, style=STYLE_SUCCESS)

        # List contents.
        contents = db.get_container_contents(item["id"])
        search_msg = item.get("search_message")
        if contents:
            if search_msg:
                self.console.print(search_msg)
            self.console.print()
            self.console.print(f"Inside the [{STYLE_ITEM}]{item['name']}[/]:")
            for c in contents:
                suffix = self._container_hint(c, db)
                self.console.print(f"  - [{STYLE_ITEM}]{c['name']}[/]{suffix}")
        else:
            if search_msg:
                self.console.print(search_msg)
            self.console.print("It's empty.", style=STYLE_SYSTEM)

    def _handle_take_from(
        self, item_name: str, container_name: str, current_room_id: str
    ) -> None:
        """Take an item from inside a specific container."""
        db = self.db

        # Find the container in the room, inventory, or inside accessible containers.
        container = self._find_accessible_item(container_name, current_room_id)
        if container is None:
            self.console.print("You don't see that here.", style=STYLE_SYSTEM)
            return

        if not container.get("is_container"):
            self.console.print("That's not a container.", style=STYLE_SYSTEM)
            return

        if container.get("is_locked"):
            msg = container.get("lock_message") or "It's locked."
            self.console.print(msg, style=STYLE_LOCKED)
            return

        if not container.get("is_open") and container.get("has_lid"):
            self.console.print("You need to open it first.", style=STYLE_SYSTEM)
            return

        # Find the item inside the container.
        found = db.find_item_in_container(item_name, container["id"])
        if found is None:
            self.console.print(
                f"You don't see that in the {container['name']}.",
                style=STYLE_SYSTEM,
            )
            return

        if not found["is_takeable"]:
            self.console.print("You can't take that.", style=STYLE_SYSTEM)
            return

        db.take_item_from_container(found["id"])
        msg = found.get("take_message")
        if msg:
            self.console.print(msg)
        else:
            self.console.print("Taken.")
        self._emit_event("item_taken", item_id=found["id"])

    def _handle_put_in(
        self, item_name: str, container_name: str, current_room_id: str
    ) -> None:
        """Put an inventory item into a container."""
        db = self.db

        # Find the item in inventory.
        item = db.find_item_by_name(item_name, "inventory", "")
        if item is None:
            self.console.print("You're not carrying that.", style=STYLE_SYSTEM)
            return

        # Find the container in the room or inventory.
        container = db.find_item_by_name(container_name, "room", current_room_id)
        if container is None:
            container = db.find_item_by_name(container_name, "inventory", "")
        if container is None:
            self.console.print("You don't see that here.", style=STYLE_SYSTEM)
            return

        if not container.get("is_container"):
            self.console.print("You can't put things in that.", style=STYLE_SYSTEM)
            return

        if container.get("is_locked"):
            msg = container.get("lock_message") or "It's locked."
            self.console.print(msg, style=STYLE_LOCKED)
            return

        if not container.get("is_open") and container.get("has_lid"):
            self.console.print("You need to open it first.", style=STYLE_SYSTEM)
            return

        success, reject_msg = db.move_item_to_container(item["id"], container["id"])
        if not success:
            self.console.print(reject_msg, style=STYLE_SYSTEM)
            return
        self.console.print(
            f"You put the [{STYLE_ITEM}]{item['name']}[/] in the"
            f" [{STYLE_ITEM}]{container['name']}[/].",
        )

    # ------------------------------------------------------------------
    # Toggle / reload / interaction matrix
    # ------------------------------------------------------------------

    def _handle_use_bare(self, item_name: str, current_room_id: str) -> None:
        """Handle ``use {item}`` without a target -- toggle if toggleable."""
        db = self.db

        item = db.find_item_by_name(item_name, "inventory", "")
        if item is None:
            self.console.print("You're not carrying that.", style=STYLE_SYSTEM)
            return

        if not item.get("is_toggleable"):
            # Not toggleable -- show the existing syntax hint.
            self.console.print(
                f"Use {item['name']} on what? Try: use {{item}} on {{target}}",
                style=STYLE_SYSTEM,
            )
            return

        # Check requires_item_id.
        if item.get("requires_item_id"):
            req_item = db.get_item(item["requires_item_id"])
            if req_item is None or (
                req_item.get("quantity") is not None and req_item["quantity"] <= 0
            ):
                msg = item.get("requires_message") or "It doesn't seem to work."
                self.console.print(msg, style=STYLE_SYSTEM)
                return

        # Determine the new state by cycling.
        current_state = item.get("toggle_state") or "off"
        states = ["off", "on"]
        raw_states = item.get("toggle_states")
        if raw_states:
            try:
                states = json.loads(raw_states)
            except (json.JSONDecodeError, TypeError):
                pass

        if current_state in states:
            idx = states.index(current_state)
            new_state = states[(idx + 1) % len(states)]
        else:
            new_state = states[0]

        db.toggle_item_state(item["id"], new_state)

        # Determine the transition message.
        msg = None
        raw_messages = item.get("toggle_messages")
        if raw_messages:
            try:
                messages_map = json.loads(raw_messages)
                msg = messages_map.get(new_state)
            except (json.JSONDecodeError, TypeError):
                pass
        if msg is None:
            if new_state == "on":
                msg = item.get("toggle_on_message") or f"You turn on the {item['name']}."
            elif new_state == "off":
                msg = item.get("toggle_off_message") or f"You turn off the {item['name']}."
            else:
                msg = f"The {item['name']} is now {new_state}."

        self.console.print(msg)

        # If toggling a light source in a dark room, re-display the room.
        room = db.get_room(current_room_id)
        if room and room.get("is_dark"):
            tags: list[str] = []
            if item.get("item_tags"):
                try:
                    tags = json.loads(item["item_tags"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if "light_source" in tags:
                if new_state == "on":
                    self.display_room(current_room_id, force_full=True)
                else:
                    self.console.print("Darkness swallows the room.", style=STYLE_SYSTEM)

    def _handle_turn(
        self, item_name: str, target_state: str, current_room_id: str
    ) -> None:
        """Handle ``turn on {item}`` / ``turn off {item}`` -- direct state setters."""
        db = self.db

        item = db.find_item_by_name(item_name, "inventory", "")
        if item is None:
            self.console.print("You're not carrying that.", style=STYLE_SYSTEM)
            return

        if not item.get("is_toggleable"):
            self.console.print("You can't turn that on or off.", style=STYLE_SYSTEM)
            return

        current_state = item.get("toggle_state") or "off"
        if current_state == target_state:
            self.console.print(
                f"It's already {target_state}.", style=STYLE_SYSTEM
            )
            return

        # Check requires_item_id (only when turning on).
        if target_state != "off" and item.get("requires_item_id"):
            req_item = db.get_item(item["requires_item_id"])
            if req_item is None or (
                req_item.get("quantity") is not None and req_item["quantity"] <= 0
            ):
                msg = item.get("requires_message") or "It doesn't seem to work."
                self.console.print(msg, style=STYLE_SYSTEM)
                return

        db.toggle_item_state(item["id"], target_state)

        # Determine the transition message.
        msg = None
        raw_messages = item.get("toggle_messages")
        if raw_messages:
            try:
                messages_map = json.loads(raw_messages)
                msg = messages_map.get(target_state)
            except (json.JSONDecodeError, TypeError):
                pass
        if msg is None:
            if target_state == "on":
                msg = item.get("toggle_on_message") or f"You turn on the {item['name']}."
            elif target_state == "off":
                msg = item.get("toggle_off_message") or f"You turn off the {item['name']}."
            else:
                msg = f"The {item['name']} is now {target_state}."

        self.console.print(msg)

        # If toggling a light source in a dark room, re-display the room.
        room = db.get_room(current_room_id)
        if room and room.get("is_dark"):
            tags: list[str] = []
            if item.get("item_tags"):
                try:
                    tags = json.loads(item["item_tags"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if "light_source" in tags:
                if target_state == "on":
                    self.display_room(current_room_id, force_full=True)
                else:
                    self.console.print("Darkness swallows the room.", style=STYLE_SYSTEM)

    def _handle_interaction(
        self, item_name: str, target_name: str, current_room_id: str
    ) -> bool:
        """Resolve ``use {item} on {target}`` via the interaction matrix.

        Returns ``True`` if a response was found and shown, ``False`` if
        the caller should fall through to the next handler.
        """
        db = self.db

        # Find the item in inventory.
        inv_item = db.find_item_by_name(item_name, "inventory", "")
        if inv_item is None:
            return False

        # Get the item's tags.
        tags: list[str] = []
        raw_tags = inv_item.get("item_tags")
        if raw_tags:
            try:
                tags = json.loads(raw_tags)
            except (json.JSONDecodeError, TypeError):
                pass
        if not tags:
            return False

        # Find the target -- room item, NPC, or inventory item.
        target_item = self._find_accessible_item(target_name, current_room_id)
        target_npc = None
        target_category: str | None = None

        if target_item is not None:
            target_category = target_item.get("category")
            target_display = target_item["name"]
        else:
            target_npc = db.find_npc_by_name(target_name, current_room_id)
            if target_npc is not None:
                target_category = target_npc.get("category")
                target_display = target_npc["name"]

        if target_category is None:
            return False

        # Query interaction_responses for each tag until we find a match.
        response: dict | None = None
        for tag in tags:
            response = db.get_interaction_response(tag, target_category)
            if response is not None:
                break

        if response is None:
            return False

        # Substitute placeholders and display.
        text = response["response"]
        text = text.replace("{item}", inv_item["name"])
        text = text.replace("{target}", target_display)
        self.console.print(text)

        # Consume quantity if specified.
        consumes = response.get("consumes", 0)
        if consumes and consumes > 0:
            db.consume_item_quantity(inv_item["id"], consumes)

        # Set flag if specified.
        flag = response.get("flag_to_set")
        if flag:
            was_set = db.has_flag(flag)
            db.set_flag(flag, "true")
            if not was_set:
                self._emit_event("flag_set", flag=flag)

        return True

    def _enter_dialogue(self, npc_name: str, current_room_id: str) -> None:
        """Enter dialogue mode with an NPC.

        Finds the NPC, gets their root dialogue node, then runs a sub-loop
        that renders a Rich Panel with numbered options until the player
        leaves or reaches a terminal node.
        """
        db = self.db

        npc = db.find_npc_by_name(npc_name, current_room_id)
        if npc is None:
            self.console.print("There's no one here by that name.", style=STYLE_SYSTEM)
            return

        # NPCs without a dialogue tree use their default_dialogue as a
        # one-liner (e.g. a zombie that can't talk).
        root_node = db.get_root_dialogue_node(npc["id"])
        if root_node is None:
            default = npc.get("default_dialogue", "")
            if default:
                self.console.print(
                    f"[{STYLE_NPC}]{npc['name']}[/]: {default}"
                )
            else:
                self.console.print(
                    f"{npc['name']} has nothing to say.", style=STYLE_SYSTEM
                )
            return

        # Apply root node flags on entry and emit dialogue_node event.
        self._apply_node_flags(root_node)
        self._emit_event("dialogue_node", node_id=root_node["id"], npc_id=npc["id"])

        current_node = root_node
        in_dialogue = True

        while in_dialogue:
            # Filter options for this node based on flags and inventory.
            visible_options = self._get_visible_options(current_node["id"])

            # Clear the terminal so only the current dialogue panel is visible.
            self.console.clear()

            # Render the dialogue panel.
            self._render_dialogue_panel(npc, current_node, visible_options)

            # If no visible options, show the text and exit.
            if not visible_options:
                self.console.print()
                break

            # Wait for player input.
            try:
                choice = Prompt.ask("[dim]>[/]")
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                break

            choice = choice.strip().lower()

            # Exit dialogue.
            if choice in ("0", "leave", "bye", "exit", "quit"):
                self.console.print()
                break

            # Parse numeric choice.
            try:
                choice_num = int(choice)
            except ValueError:
                self.console.print("  Pick a number.", style=STYLE_SYSTEM)
                continue

            if choice_num < 1 or choice_num > len(visible_options):
                self.console.print("  Pick a number.", style=STYLE_SYSTEM)
                continue

            selected = visible_options[choice_num - 1]

            # Apply the option's set_flags.
            self._apply_option_flags(selected)

            # Navigate to next node.
            next_node_id = selected.get("next_node_id")
            if next_node_id is None:
                # Terminal option -- show nothing more, exit dialogue.
                self.console.print()
                break

            next_node = db.get_dialogue_node(next_node_id)
            if next_node is None:
                # Broken link -- exit gracefully.
                self.console.print()
                break

            # Apply the new node's set_flags and emit dialogue_node event.
            self._apply_node_flags(next_node)
            self._emit_event("dialogue_node", node_id=next_node["id"], npc_id=npc["id"])
            current_node = next_node

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
        lines: list[str] = []
        lines.append(f"\n{node['content']}\n")

        has_terminal = any(opt.get("next_node_id") is None for opt in visible_options)

        for i, opt in enumerate(visible_options, 1):
            tag = " [bright_yellow]\\[NEW][/]" if opt.get("_is_item_gated") else ""
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

    def _apply_node_flags(self, node: dict) -> None:
        """Set any flags defined in a dialogue node's set_flags field."""
        set_raw = node.get("set_flags")
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

    def _apply_option_flags(self, option: dict) -> None:
        """Set any flags defined in a dialogue option's set_flags field."""
        set_raw = option.get("set_flags")
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

    # ------------------------------------------------------------------
    # End conditions
    # ------------------------------------------------------------------

    def check_end_conditions(self) -> None:
        """Check win/lose conditions and transition game state if triggered."""
        player = self.db.get_player()
        if player is None or player["game_state"] != "playing":
            return

        meta = self.db.get_all_meta()
        if meta is None:
            return

        # --- Win conditions: all flags in the win_conditions list must be set ---
        win_raw = meta.get("win_conditions", "[]")
        try:
            win_flags: list[str] = json.loads(win_raw) if win_raw else []
        except (json.JSONDecodeError, TypeError):
            win_flags = []

        if win_flags and all(self.db.has_flag(f) for f in win_flags):
            self.db.update_player(game_state="won")
            win_text = meta.get("win_text", "")
            self.console.print()
            self.console.print(
                Panel(
                    win_text or "Congratulations! You have won the game!",
                    title=f"[{STYLE_VICTORY_TITLE}]Victory[/]",
                    border_style=STYLE_VICTORY_BORDER,
                    padding=(1, 2),
                )
            )
            self._show_score()
            self._running = False
            return

        # --- Lose conditions ---
        lose_raw = meta.get("lose_conditions")
        try:
            lose_flags: list[str] = json.loads(lose_raw) if lose_raw else []
        except (json.JSONDecodeError, TypeError):
            lose_flags = []

        # Flag-based lose condition.
        lost = bool(lose_flags) and all(self.db.has_flag(f) for f in lose_flags)

        # Health-based lose condition (HP <= 0).
        if not lost and player["hp"] <= 0:
            lost = True

        if lost:
            self.db.update_player(game_state="lost")
            lose_text = meta.get("lose_text", "")
            self.console.print()
            self.console.print(
                Panel(
                    lose_text or "You have lost the game.",
                    title=f"[{STYLE_DEFEAT_TITLE}]Defeat[/]",
                    border_style=STYLE_DEFEAT_BORDER,
                    padding=(1, 2),
                )
            )
            self._show_score()
            self._running = False

    # ------------------------------------------------------------------
    # Event / trigger system
    # ------------------------------------------------------------------

    def _emit_event(self, event_type: str, **event_data: str) -> None:
        """Emit a game event and evaluate matching triggers.

        Events are queued and processed iteratively to prevent deep
        recursion from flag cascades.  Re-entrant calls (e.g. a trigger
        effect setting a flag that emits another ``flag_set`` event) are
        appended to the queue and processed by the outer loop.

        A hard limit of 20 queue-drain iterations prevents infinite loops
        from circular flag dependencies.
        """
        self._event_queue.append((event_type, event_data))

        if self._processing_events:
            return  # will be processed by the outer loop

        self._processing_events = True
        iterations = 0
        try:
            while self._event_queue and iterations < 20:
                ev_type, ev_data = self._event_queue.pop(0)
                self._process_event(ev_type, ev_data)
                iterations += 1
            if self._event_queue:
                logger.warning(
                    "Event cascade limit (20) reached — %d events discarded: %s",
                    len(self._event_queue),
                    self._event_queue,
                )
                self._event_queue.clear()
        finally:
            self._processing_events = False

    def _process_event(self, event_type: str, event_data: dict[str, str]) -> None:
        """Find and execute all triggers matching this event."""
        from anyzork.engine.commands import apply_effect, check_precondition

        db = self.db

        # 1. Fetch candidate triggers (enabled, non-executed one-shots).
        triggers = db.get_triggers_for_event(event_type)

        # 2. Filter by event_data partial match.
        matching: list[dict] = []
        for trigger in triggers:
            try:
                trigger_data = json.loads(trigger["event_data"]) if trigger["event_data"] else {}
            except (json.JSONDecodeError, TypeError):
                trigger_data = {}
            if all(event_data.get(k) == v for k, v in trigger_data.items()):
                matching.append(trigger)

        # 3. Already sorted by priority DESC from the query, but ensure it.
        matching.sort(key=lambda t: -t["priority"])

        # 4. Evaluate each trigger.
        for trigger in matching:
            # Double-check one-shot execution (defensive).
            if trigger["one_shot"] and trigger["executed"]:
                continue

            # Check preconditions.
            try:
                preconditions = json.loads(trigger["preconditions"]) if trigger["preconditions"] else []
            except (json.JSONDecodeError, TypeError):
                preconditions = []

            all_pass = all(
                check_precondition(cond, db) for cond in preconditions
            )
            if not all_pass:
                continue

            # Fire the trigger — display message, apply effects.
            if trigger.get("message"):
                self.console.print(trigger["message"])

            try:
                effects = json.loads(trigger["effects"]) if trigger["effects"] else []
            except (json.JSONDecodeError, TypeError):
                effects = []

            for effect in effects:
                try:
                    msgs = apply_effect(
                        effect, db,
                        command_id=f"trigger:{trigger['id']}",
                        emit_event=self._emit_event,
                    )
                    for msg in msgs:
                        self.console.print(msg)
                except Exception:
                    logger.exception(
                        "Trigger effect failed: %s in %s", effect, trigger["id"]
                    )

            # Mark one-shot as executed.
            if trigger["one_shot"]:
                db.mark_trigger_executed(trigger["id"])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def _tick(self) -> None:
        """Increment move counter, run quest state machine, and check end conditions."""
        player = self.db.get_player()
        if player is None:
            return
        self.db.update_player(moves=player["moves"] + 1)
        self._check_quests()
        self.check_end_conditions()

    def _check_quests(self) -> None:
        """Run the quest state machine: discover, advance, and complete quests."""
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
                    self.console.print()
                    self.console.print(
                        f"  [{STYLE_QUEST_HEADER}]-- New Quest: {quest['name']} --[/]"
                    )
                    self.console.print(f"  {quest['description']}")
                    # Initialize objective cache for newly discovered quest.
                    objectives = db.get_quest_objectives(quest["id"])
                    for obj in objectives:
                        self._objective_cache[obj["id"]] = db.has_flag(obj["completion_flag"])

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
                        self.console.print()
                        self.console.print(
                            f"  [{STYLE_QUEST_HEADER}]-- Quest Updated: {quest['name']} --[/]"
                        )
                        self.console.print(
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
                        if obj["is_optional"] and db.has_flag(obj["completion_flag"]):
                            if obj["bonus_score"] > 0:
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
                    self.console.print()
                    self.console.print(
                        Panel(
                            f"Quest Complete: {quest['name']}\n"
                            f"{quest['description']}\n"
                            + (f"+{total_score} points" if total_score > 0 else ""),
                            style=STYLE_QUEST_COMPLETE,
                            padding=(1, 2),
                        )
                    )

    # ------------------------------------------------------------------
    # Narrator integration
    # ------------------------------------------------------------------

    def _init_narrator(self) -> None:
        """Try to create a Narrator instance. Fails silently if no API key.

        Uses --provider/--model from CLI if passed, otherwise falls back to
        the default provider from config/env.
        """
        try:
            from anyzork.config import Config, LLMProvider
            from anyzork.engine.narrator import Narrator
            from anyzork.generator.providers import create_provider

            config = Config()

            # CLI overrides for narrator provider/model.
            if self._narrator_provider_override:
                config.provider = LLMProvider(self._narrator_provider_override)
            if self._narrator_model_override:
                config.model = self._narrator_model_override

            provider = create_provider(config)
            self._narrator = Narrator(provider, self.db)
        except Exception as exc:
            logger.debug("Could not enable narrator: %s", exc)
            self.console.print(
                f"Could not enable narrator: {exc}", style=STYLE_SYSTEM
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
            return [narrated]
        return messages

    @staticmethod
    def _parse_direction(tokens: list[str]) -> str | None:
        """Extract a canonical direction from the tokenised input.

        Accepts bare directions (``north``, ``n``), as well as ``go north``
        and ``go n``.
        """
        if not tokens:
            return None

        # Single-word direction: "north", "n", etc.
        if len(tokens) == 1 and tokens[0] in ALL_DIRECTION_TOKENS:
            raw = tokens[0]
            return DIRECTION_ALIASES.get(raw, raw)

        # "go <direction>" form.
        if tokens[0] == "go" and len(tokens) == 2 and tokens[1] in ALL_DIRECTION_TOKENS:
            raw = tokens[1]
            return DIRECTION_ALIASES.get(raw, raw)

        # Not a direction.
        return None
