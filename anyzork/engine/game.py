"""Main game runtime — the loop that displays rooms, reads input, and dispatches commands.

Uses GameDB for all state and the command resolver for DSL commands.
Rich provides styled terminal output for a polished text adventure experience.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

if TYPE_CHECKING:
    from anyzork.db.schema import GameDB

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

    def __init__(self, db: GameDB) -> None:
        self.db = db
        self.console = Console()
        self._running = False
        # Cache of objective completion states from the previous tick.
        # Maps objective_id -> bool (was complete last tick).
        self._objective_cache: dict[str, bool] = {}

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

        # Show game title and intro text.
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

            intro = meta.get("intro_text", "")
            if intro:
                self.console.print()
                self.console.print(intro, style=STYLE_PROSE)

        self.console.print()

        # Initialize quest state: auto-discover main quest and cache objectives.
        self._init_quest_state()

        # Display the starting room.
        assert player is not None
        self.display_room(player["current_room_id"])

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
                raw = Prompt.ask(f"\n[{STYLE_PROMPT}]>[/]")
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
                continue  # help doesn't cost a move

            if verb == "save" and len(tokens) == 1:
                self.console.print(
                    "Your game is saved automatically. The [bold].zork[/] file "
                    "[italic]is[/] your save — copy it to back up, or share it with a friend.",
                    style=STYLE_SYSTEM,
                )
                continue  # save info doesn't cost a move

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
                result = resolve_command(raw, self.db)
                if result.success or result.messages != ["I don't understand that."]:
                    # DSL matched (success or a meaningful failure message)
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

            # use {item} on {target} — built-in key-on-lock handler
            if verb == "use" and len(tokens) >= 4 and "on" in tokens:
                on_idx = tokens.index("on")
                if on_idx > 1 and on_idx < len(tokens) - 1:
                    item_name = " ".join(tokens[1:on_idx])
                    target_name = " ".join(tokens[on_idx + 1:])
                    handled = self._handle_use_on(item_name, target_name, player["current_room_id"])
                    if handled:
                        self._tick()
                        continue

            # put / place <item> in/into/inside <container>
            if verb in ("put", "place") and len(tokens) >= 4:
                rest_tokens = tokens[1:]
                # Find the split word: "in", "into", or "inside"
                split_idx = None
                for i, t in enumerate(rest_tokens):
                    if t in ("in", "into", "inside"):
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
            self.console.print("I don't understand that.", style=STYLE_SYSTEM)
            self._tick()

    # ------------------------------------------------------------------
    # Room display
    # ------------------------------------------------------------------

    def display_room(self, room_id: str, *, force_full: bool = False) -> None:
        """Render a room to the console.

        On the first visit (or when *force_full* is ``True``), the full
        description is shown.  On revisits, the short description is used.
        """
        room = self.db.get_room(room_id)
        if room is None:
            self.console.print(f"Room '{room_id}' not found.", style=STYLE_ERROR)
            return

        player = self.db.get_player()
        move_num = player["moves"] if player else 0

        # Record the visit and decide which description to show.
        first_visit = self.db.record_visit(room_id, move_num)

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
            rd = it.get("room_description")
            if rd:
                prose_items.append(rd)
            else:
                list_items.append(it)

        if prose_items:
            parts.append(" ".join(prose_items))

        body = "\n\n".join(parts)

        # Display the room panel.
        self.console.print(
            Panel(
                body,
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

        # NPCs present.
        npcs = self.db.get_npcs_in(room_id)
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

        # Hidden exits are excluded by get_exit_by_direction via the schema's
        # get_exits filter, but get_exit_by_direction returns all exits
        # including hidden ones.  Guard against it here.
        if exit_row.get("is_hidden"):
            self.console.print("You can't go that way.", style=STYLE_SYSTEM)
            return

        # Locked?
        if exit_row.get("is_locked"):
            lock = self.db.get_lock_for_exit(exit_row["id"])
            if lock:
                self.console.print(lock["locked_message"], style=STYLE_LOCKED)
            else:
                self.console.print("The way is blocked.", style=STYLE_LOCKED)
            return

        # Move the player.
        dest_room_id = exit_row["to_room_id"]
        self.db.update_player(current_room_id=dest_room_id)
        self.display_room(dest_room_id)

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
            table.add_row(item["name"], item["description"])

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
        """List built-in commands available to the player."""

        c = STYLE_COMMAND  # shorthand for readability in the help block
        self.console.print(
            Panel(
                "[bold]Built-in commands[/]\n"
                f"  [{c}]look[/] (l)           — redisplay the current room\n"
                f"  [{c}]inventory[/] (i)      — show what you're carrying\n"
                f"  [{c}]score[/]              — show your score and stats\n"
                f"  [{c}]quests[/] (j)          — view your quest log\n"
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
                f"  [{c}]search[/] / [{c}]look in[/] {{container}}  — search inside a container\n"
                f"  [{c}]put[/] {{item}} [{c}]in[/] {{container}}  — put something into a container\n"
                f"  [{c}]talk to[/] {{npc}}      — start a conversation\n"
                "\n"
                "[bold]Movement[/]\n"
                f"  Type a direction: [{c}]north[/], [{c}]south[/], [{c}]east[/], "
                f"[{c}]west[/], [{c}]up[/], [{c}]down[/]\n"
                f"  Shortcuts: [{c}]n[/] [{c}]s[/] [{c}]e[/] [{c}]w[/] [{c}]u[/] [{c}]d[/]",
                title=f"[{STYLE_ROOM_NAME}]Help[/]",
                title_align="left",
                border_style=STYLE_ROOM_BORDER,
                padding=(1, 2),
            )
        )


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
            msg = item.get("take_message")
            if msg:
                self.console.print(msg)
            else:
                self.console.print("Taken.")
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
                msg = found.get("take_message")
                if msg:
                    self.console.print(msg)
                else:
                    self.console.print("Taken.")
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
        msg = item.get("drop_message")
        if msg:
            self.console.print(msg)
        else:
            self.console.print("Dropped.")

    def _handle_examine(
        self, target_name: str, current_room_id: str, *, prefer_read: bool = False
    ) -> None:
        """Examine an item, NPC, or room feature.

        When *prefer_read* is ``True`` (triggered by the ``read`` verb), the
        item's ``read_description`` is shown if it exists; otherwise falls back
        to ``examine_description``.
        """
        db = self.db

        # Check items in inventory first.
        item = db.find_item_by_name(target_name, "inventory", "")
        if item is None:
            # Check items in the current room.
            item = db.find_item_by_name(target_name, "room", current_room_id)

        if item is not None:
            if prefer_read and item.get("read_description"):
                desc = item["read_description"]
            else:
                desc = item.get("examine_description") or item.get("description", "")
            self.console.print(desc)

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
                            f"[{STYLE_ITEM}]{c['name']}[/]" for c in contents
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

        # 3. Try matching a container item in the room.
        item = db.find_item_by_name(target_name, "room", current_room_id)
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

        # Find the target in the current room.
        item = db.find_item_by_name(target_name, "room", current_room_id)
        if item is None:
            # Also check inventory (for portable containers like bags).
            item = db.find_item_by_name(target_name, "inventory", "")
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
                self.console.print(f"  - [{STYLE_ITEM}]{c['name']}[/]")
        else:
            if search_msg:
                self.console.print(search_msg)
            self.console.print("It's empty.", style=STYLE_SYSTEM)

    def _handle_take_from(
        self, item_name: str, container_name: str, current_room_id: str
    ) -> None:
        """Take an item from inside a specific container."""
        db = self.db

        # Find the container in the room or inventory.
        container = db.find_item_by_name(container_name, "room", current_room_id)
        if container is None:
            container = db.find_item_by_name(container_name, "inventory", "")
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

        db.move_item_to_container(item["id"], container["id"])
        self.console.print(
            f"You put the [{STYLE_ITEM}]{item['name']}[/] in the"
            f" [{STYLE_ITEM}]{container['name']}[/].",
            style=STYLE_SUCCESS,
        )

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

        # Apply root node flags on entry.
        self._apply_node_flags(root_node)

        current_node = root_node
        in_dialogue = True

        while in_dialogue:
            # Filter options for this node based on flags and inventory.
            visible_options = self._get_visible_options(current_node["id"])

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

            # Apply the new node's set_flags.
            self._apply_node_flags(next_node)
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

        for i, opt in enumerate(visible_options, 1):
            tag = " [bright_yellow]\\[NEW][/]" if opt.get("_is_item_gated") else ""
            lines.append(f"  {i}. {opt['text']}{tag}")

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
            self.db.set_flag(flag, "true")

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
            self.db.set_flag(flag, "true")

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
