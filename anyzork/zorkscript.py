"""ZorkScript parser and compiler for AnyZork.

Parses ZorkScript DSL source text and returns the normalized import-spec
shape expected by ``compile_import_spec``. The parser is a hand-written
recursive descent tokenizer + block parser.

Public API::

    from anyzork.zorkscript import parse_zorkscript, ZorkScriptError

    spec = parse_zorkscript(source_text)
    # spec is ready for compile_import_spec
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class ZorkScriptError(ValueError):
    """Raised on parse errors with line number context."""

    def __init__(self, message: str, line: int | None = None):
        if line is not None:
            message = f"line {line}: {message}"
        super().__init__(message)
        self.line = line


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_SPEC = [
    ("STRING",   r'"(?:[^"\\]|\\.)*"'),
    ("ARROW",    r"->"),
    ("LBRACE",   r"\{"),
    ("RBRACE",   r"\}"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("LPAREN",   r"\("),
    ("RPAREN",   r"\)"),
    ("COMMA",    r","),
    ("COLON",    r":"),
    ("EQUALS",   r"="),
    ("NUMBER",   r"-?[0-9]+"),
    ("IDENT",    r"[a-zA-Z_][a-zA-Z0-9_]*"),
    ("SKIP",     r"[ \t]+"),
    ("NEWLINE",  r"\n"),
    ("COMMENT",  r"#[^\n]*"),
]

_TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC))


class _Token:
    __slots__ = ("kind", "line", "value")

    def __init__(self, kind: str, value: str, line: int):
        self.kind = kind
        self.value = value
        self.line = line

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r}, line={self.line})"


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    line_num = 1
    pos = 0
    while pos < len(source):
        m = _TOKEN_RE.match(source, pos)
        if m is None:
            raise ZorkScriptError(f"unexpected character {source[pos]!r}", line_num)
        kind = m.lastgroup
        assert kind is not None
        value = m.group()
        if kind == "NEWLINE":
            line_num += 1
        elif kind == "STRING":
            # Count newlines inside multi-line strings
            line_num += value.count("\n")
        if kind not in ("SKIP", "NEWLINE", "COMMENT"):
            tokens.append(_Token(kind, value, line_num))
        pos = m.end()
    tokens.append(_Token("EOF", "", line_num))
    return tokens


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class _Parser:
    """Recursive descent parser for ZorkScript."""

    def __init__(self, tokens: list[_Token]):
        self._tokens = tokens
        self._pos = 0

        # Output collections
        self._game: dict[str, Any] | None = None
        self._player: dict[str, Any] | None = None
        self._rooms: list[dict[str, Any]] = []
        self._exits: list[dict[str, Any]] = []
        self._items: list[dict[str, Any]] = []
        self._npcs: list[dict[str, Any]] = []
        self._dialogue_nodes: list[dict[str, Any]] = []
        self._dialogue_options: list[dict[str, Any]] = []
        self._locks: list[dict[str, Any]] = []
        self._puzzles: list[dict[str, Any]] = []
        self._flags: list[dict[str, Any]] = []
        self._commands: list[dict[str, Any]] = []
        self._quests: list[dict[str, Any]] = []
        self._triggers: list[dict[str, Any]] = []
        self._interaction_responses: list[dict[str, Any]] = []

        # Deferred resolution: lock exit routes and NPC blocking routes
        self._lock_exit_routes: list[tuple[dict[str, Any], str, str, str]] = []
        self._npc_blocking_routes: list[tuple[dict[str, Any], str, str, str]] = []

    # -- Helpers --

    def _peek(self) -> _Token:
        if self._pos >= len(self._tokens):
            line = self._tokens[-1].line if self._tokens else 0
            raise ZorkScriptError("unexpected end of input", line)
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        if self._pos >= len(self._tokens):
            line = self._tokens[-1].line if self._tokens else 0
            raise ZorkScriptError("unexpected end of input", line)
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, kind: str, value: str | None = None) -> _Token:
        tok = self._advance()
        if tok.kind != kind:
            expected = f"{kind} {value!r}" if value else kind
            raise ZorkScriptError(
                f"expected {expected} but found {tok.kind} {tok.value!r}",
                tok.line,
            )
        if value is not None and tok.value != value:
            raise ZorkScriptError(
                f"expected {value!r} but found {tok.value!r}",
                tok.line,
            )
        return tok

    def _at(self, kind: str, value: str | None = None) -> bool:
        tok = self._peek()
        if tok.kind != kind:
            return False
        return not (value is not None and tok.value != value)

    def _match(self, kind: str, value: str | None = None) -> _Token | None:
        if self._at(kind, value):
            return self._advance()
        return None

    def _error(self, msg: str) -> ZorkScriptError:
        return ZorkScriptError(msg, self._peek().line)

    # -- Value parsing --

    def _parse_string(self) -> str:
        tok = self._expect("STRING")
        raw = tok.value[1:-1]
        # Handle escape sequences
        raw = raw.replace('\\"', '"').replace("\\\\", "\\")
        # Handle multi-line: collapse runs of whitespace around newlines
        raw = re.sub(r"\s*\n\s*", " ", raw)
        return raw.strip()

    def _parse_value(self) -> Any:
        """Parse a value: string, number, boolean, identifier, or list."""
        tok = self._peek()
        if tok.kind == "STRING":
            return self._parse_string()
        if tok.kind == "NUMBER":
            self._advance()
            return int(tok.value)
        if tok.kind == "IDENT" and tok.value in ("true", "false"):
            self._advance()
            return tok.value == "true"
        if tok.kind == "IDENT":
            self._advance()
            return tok.value
        if tok.kind == "LBRACKET":
            return self._parse_list()
        raise self._error(f"expected a value but found {tok.kind} {tok.value!r}")

    def _parse_list(self) -> list[Any]:
        """Parse [item, item, ...] -- ID list or string list."""
        self._expect("LBRACKET")
        items: list[Any] = []
        while not self._at("RBRACKET"):
            if items:
                self._match("COMMA")
            items.append(self._parse_value())
        self._expect("RBRACKET")
        return items

    def _parse_func_call(self) -> tuple[str, list[Any]]:
        """Parse name(arg, arg, ...)"""
        name_tok = self._expect("IDENT")
        name = name_tok.value
        self._expect("LPAREN")
        args: list[Any] = []
        while not self._at("RPAREN"):
            if args:
                self._match("COMMA")
            tok = self._peek()
            if tok.kind == "LBRACE":
                # Slot reference: {slot_name}
                self._advance()
                slot_tok = self._expect("IDENT")
                self._expect("RBRACE")
                args.append(f"{{{slot_tok.value}}}")
            elif tok.kind == "STRING":
                args.append(self._parse_string())
            elif tok.kind == "NUMBER":
                self._advance()
                args.append(int(tok.value))
            elif tok.kind == "IDENT" and tok.value in ("true", "false"):
                self._advance()
                args.append(tok.value == "true")
            elif tok.kind == "IDENT":
                self._advance()
                args.append(tok.value)
            else:
                raise self._error(f"unexpected {tok.kind} in function arguments")
        self._expect("RPAREN")
        return name, args

    # -- Precondition / effect compilation --

    _PRECONDITION_ARGS: ClassVar[dict[str, list[str]]] = {
        "in_room":                ["room"],
        "has_item":               ["item"],
        "has_flag":               ["flag"],
        "not_flag":               ["flag"],
        "item_in_room":           ["item", "room"],
        "item_accessible":        ["item"],
        "npc_in_room":            ["npc", "room"],
        "lock_unlocked":          ["lock"],
        "puzzle_solved":          ["puzzle"],
        "health_above":           ["threshold"],
        "container_open":         ["container"],
        "item_in_container":      ["item", "container"],
        "not_item_in_container":  ["item", "container"],
        "container_has_contents": ["container"],
        "container_empty":        ["container"],
        "has_quantity":           ["item", "min"],
        "toggle_state":           ["item", "state"],
    }

    _EFFECT_ARGS: ClassVar[dict[str, list[str]]] = {
        "move_item":               ["item", "from", "to"],
        "remove_item":             ["item"],
        "set_flag":                ["flag", "value"],
        "unlock":                  ["lock"],
        "move_player":             ["room"],
        "spawn_item":              ["item", "location"],
        "change_health":           ["amount"],
        "add_score":               ["points"],
        "reveal_exit":             ["exit"],
        "solve_puzzle":            ["puzzle"],
        "discover_quest":          ["quest"],
        "print":                   ["message"],
        "open_container":          ["container"],
        "move_item_to_container":  ["item", "container"],
        "take_item_from_container": ["item"],
        "consume_quantity":        ["item", "amount"],
        "restore_quantity":        ["item", "amount"],
        "set_toggle_state":        ["item", "state"],
        # Visibility / NPC movement
        "make_visible":            ["item"],
        "make_hidden":             ["item"],
        "make_takeable":           ["item"],
        "move_npc":                ["npc", "room"],
        # Explicit NPC effects
        "kill_npc":                ["npc"],
        "remove_npc":              ["npc"],
        # Quest effects
        "fail_quest":              ["quest"],
        "complete_quest":          ["quest"],
        # Exit effects
        "lock_exit":               ["exit"],
        "hide_exit":               ["exit"],
        # Entity description
        "change_description":      ["entity", "text"],
        # Target-aware effects (interaction response context only)
        "kill_target":             [],
        "damage_target":           ["amount"],
        "destroy_target":          [],
        "open_target":             [],
    }

    def _compile_precondition(self, name: str, args: list[Any]) -> dict[str, Any]:
        arg_names = self._PRECONDITION_ARGS.get(name)
        if arg_names is None:
            raise self._error(f"unknown precondition type {name!r}")
        result: dict[str, Any] = {"type": name}
        for i, arg_name in enumerate(arg_names):
            if i < len(args):
                result[arg_name] = args[i]
        return result

    def _compile_effect(self, name: str, args: list[Any]) -> dict[str, Any]:
        arg_names = self._EFFECT_ARGS.get(name)
        if arg_names is None:
            raise self._error(f"unknown effect type {name!r}")
        result: dict[str, Any] = {"type": name}
        for i, arg_name in enumerate(arg_names):
            if i < len(args):
                result[arg_name] = args[i]
        # set_flag with no value argument defaults to true
        if name == "set_flag" and "value" not in result:
            result["value"] = True
        return result

    # -- Top-level dispatch --

    def parse(self) -> dict[str, Any]:
        while not self._at("EOF"):
            tok = self._peek()
            if tok.kind != "IDENT":
                raise self._error(f"expected a block keyword but found {tok.kind} {tok.value!r}")
            keyword = tok.value
            if keyword == "game":
                self._parse_game_block()
            elif keyword == "player":
                self._parse_player_block()
            elif keyword == "room":
                self._parse_room_block()
            elif keyword == "item":
                self._parse_item_block()
            elif keyword == "npc":
                self._parse_npc_block()
            elif keyword == "lock":
                self._parse_lock_block()
            elif keyword == "puzzle":
                self._parse_puzzle_block()
            elif keyword == "flag":
                self._parse_flag_line()
            elif keyword == "quest":
                self._parse_quest_block()
            elif keyword == "on":
                self._parse_on_block()
            elif keyword == "when":
                self._parse_when_block()
            elif keyword == "interaction":
                self._parse_interaction_block()
            elif keyword == "exit":
                self._parse_standalone_exit_block()
            elif keyword == "command":
                self._parse_command_block()
            elif keyword == "trigger":
                self._parse_trigger_block()
            elif keyword == "dialogue":
                self._parse_standalone_dialogue_block()
            elif keyword == "option":
                self._parse_standalone_option_block()
            else:
                raise self._error(f"unknown top-level keyword {keyword!r}")

        self._resolve_exit_routes()
        self._fix_container_refs()
        return self._build_output()

    # -- Game block --

    _GAME_FIELD_MAP: ClassVar[dict[str, str]] = {
        "author": "author_prompt",
        "intro": "intro_text",
        "win": "win_conditions",
        "lose": "lose_conditions",
    }

    def _parse_game_block(self) -> None:
        self._expect("IDENT", "game")
        self._expect("LBRACE")
        game: dict[str, Any] = {}
        while not self._at("RBRACE"):
            key_tok = self._expect("IDENT")
            key = self._GAME_FIELD_MAP.get(key_tok.value, key_tok.value)
            game[key] = self._parse_value()
        self._expect("RBRACE")
        self._game = game

    # -- Player block --

    _PLAYER_FIELD_MAP: ClassVar[dict[str, str]] = {
        "start": "start_room_id",
        "start_room": "start_room_id",
    }

    def _parse_player_block(self) -> None:
        self._expect("IDENT", "player")
        self._expect("LBRACE")
        player: dict[str, Any] = {}
        while not self._at("RBRACE"):
            key_tok = self._expect("IDENT")
            key = self._PLAYER_FIELD_MAP.get(key_tok.value, key_tok.value)
            player[key] = self._parse_value()
        self._expect("RBRACE")
        self._player = player

    # -- Room block --

    _ROOM_FIELD_MAP: ClassVar[dict[str, str]] = {
        "short": "short_description",
        "first_visit": "first_visit_text",
        "dark": "is_dark",
        "start": "is_start",
    }

    def _parse_room_block(self) -> None:
        self._expect("IDENT", "room")
        room_id_tok = self._expect("IDENT")
        room_id = room_id_tok.value
        self._expect("LBRACE")

        room: dict[str, Any] = {"id": room_id}

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "exit":
                self._parse_inline_exit(room_id)
                continue

            key_tok = self._expect("IDENT")
            key = self._ROOM_FIELD_MAP.get(key_tok.value, key_tok.value)
            room[key] = self._parse_value()

        self._expect("RBRACE")
        self._rooms.append(room)

    def _parse_inline_exit(self, from_room: str) -> None:
        """Parse: exit direction -> target_room (modifiers) "description" """
        self._expect("IDENT", "exit")
        direction_tok = self._expect("IDENT")
        direction = direction_tok.value
        self._expect("ARROW")
        target_tok = self._expect("IDENT")
        target_room = target_tok.value

        exit_id = f"{from_room}_{direction}"
        exit_data: dict[str, Any] = {
            "id": exit_id,
            "from_room_id": from_room,
            "to_room_id": target_room,
            "direction": direction,
            "is_locked": False,
            "is_hidden": False,
        }

        # Optional parenthetical modifiers
        if self._at("LPAREN"):
            self._advance()
            while not self._at("RPAREN"):
                mod_tok = self._expect("IDENT")
                mod = mod_tok.value.lower()
                if mod == "locked":
                    exit_data["is_locked"] = True
                elif mod == "hidden":
                    exit_data["is_hidden"] = True
                self._match("COMMA")
            self._expect("RPAREN")

        # Optional description string
        if self._at("STRING"):
            exit_data["description"] = self._parse_string()

        self._exits.append(exit_data)

    def _parse_standalone_exit_block(self) -> None:
        """Parse a standalone exit block (from the Architect's spec)."""
        self._expect("IDENT", "exit")
        exit_id_tok = self._expect("IDENT")
        exit_id = exit_id_tok.value
        self._expect("LBRACE")

        exit_data: dict[str, Any] = {"id": exit_id}
        field_map = {
            "from": "from_room_id",
            "to": "to_room_id",
        }

        while not self._at("RBRACE"):
            key_tok = self._expect("IDENT")
            key = field_map.get(key_tok.value, key_tok.value)
            exit_data[key] = self._parse_value()

        self._expect("RBRACE")
        exit_data.setdefault("is_locked", False)
        exit_data.setdefault("is_hidden", False)
        self._exits.append(exit_data)

    # -- Item block --

    _ITEM_FIELD_MAP: ClassVar[dict[str, str]] = {
        "examine": "examine_description",
        "examine_text": "examine_description",
        "in": "room_id",
        "takeable": "is_takeable",
        "visible": "is_visible",
        "consumable": "is_consumed_on_use",
        # Container fields
        "container": "is_container",
        "open": "is_open",
        "has_lid": "has_lid",
        "locked": "is_locked",
        "key": "key_item_id",
        "consume_key": "consume_key",
        "code": "combination",
        "accepts": "accepts_items",
        "reject_msg": "reject_message",
        # Toggle fields
        "toggle": "is_toggleable",
        "toggle_default": "toggle_state",
        "on_msg": "toggle_on_message",
        "off_msg": "toggle_off_message",
        "states": "toggle_states",
        "state_msgs": "toggle_messages",
        "requires": "requires_item_id",
        "requires_msg": "requires_message",
        # Messaging fields
        "take_msg": "take_message",
        "drop_msg": "drop_message",
        "room_desc": "room_description",
        "drop_desc": "drop_description",
        "home": "home_room_id",
        "read_text": "read_description",
        "open_msg": "open_message",
        "lock_msg": "lock_message",
        "unlock_msg": "unlock_message",
        "search_msg": "search_message",
        # Tags and categories
        "tags": "item_tags",
        "category": "category",
        # Quantity fields
        "quantity_unit": "quantity_unit",
        "depleted_msg": "depleted_message",
        "quantity_desc": "quantity_description",
    }

    def _parse_item_block(self) -> None:
        self._expect("IDENT", "item")
        item_id_tok = self._expect("IDENT")
        item_id = item_id_tok.value
        self._expect("LBRACE")

        item: dict[str, Any] = {"id": item_id}

        while not self._at("RBRACE"):
            key_tok = self._expect("IDENT")
            key = self._ITEM_FIELD_MAP.get(key_tok.value, key_tok.value)
            item[key] = self._parse_value()

        self._expect("RBRACE")
        self._items.append(item)

    # -- NPC block --

    _NPC_FIELD_MAP: ClassVar[dict[str, str]] = {
        "examine": "examine_description",
        "examine_text": "examine_description",
        "in": "room_id",
        "dialogue": "default_dialogue",
        "room_desc": "room_description",
        "drop_desc": "drop_description",
        "home": "home_room_id",
    }

    def _parse_npc_block(self) -> None:
        self._expect("IDENT", "npc")
        npc_id_tok = self._expect("IDENT")
        npc_id = npc_id_tok.value
        self._expect("LBRACE")

        npc: dict[str, Any] = {"id": npc_id}
        talk_blocks: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "talk":
                label, node, options = self._parse_talk_block(npc_id)
                talk_blocks.append((label, node, options))
                continue

            if tok.kind == "IDENT" and tok.value == "blocking":
                self._advance()
                # Parse: from_room -> to_room direction
                from_tok = self._expect("IDENT")
                self._expect("ARROW")
                to_tok = self._expect("IDENT")
                dir_tok = self._expect("IDENT")
                npc["is_blocking"] = True
                self._npc_blocking_routes.append(
                    (npc, from_tok.value, to_tok.value, dir_tok.value)
                )
                continue

            key_tok = self._expect("IDENT")
            raw_key = key_tok.value
            key = self._NPC_FIELD_MAP.get(raw_key, raw_key)
            npc[key] = self._parse_value()

        self._expect("RBRACE")
        self._npcs.append(npc)

        # Process talk blocks
        for i, (label, node, options) in enumerate(talk_blocks):
            node_id = f"{npc_id}_{label}"
            node["id"] = node_id
            node["npc_id"] = npc_id
            if i == 0:
                node["is_root"] = True
            self._dialogue_nodes.append(node)
            for j, opt in enumerate(options):
                opt["id"] = f"{node_id}_opt_{j}"
                opt["node_id"] = node_id
                opt["sort_order"] = j
                self._dialogue_options.append(opt)

    def _parse_talk_block(
        self, npc_id: str
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        """Parse: talk label { content; sets; effect; options }"""
        self._expect("IDENT", "talk")
        label_tok = self._expect("IDENT")
        label = label_tok.value
        self._expect("LBRACE")

        node: dict[str, Any] = {"is_root": False}
        options: list[dict[str, Any]] = []
        effects: list[dict[str, Any]] = []

        # First string in the block is the content
        if self._at("STRING"):
            node["content"] = self._parse_string()

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "option":
                opt = self._parse_talk_option(npc_id)
                options.append(opt)
                continue

            if tok.kind == "IDENT" and tok.value == "sets":
                self._advance()
                node["set_flags"] = self._parse_list()
                continue

            if tok.kind == "IDENT" and tok.value == "effect":
                self._advance()
                name, args = self._parse_func_call()
                effects.append(self._compile_effect(name, args))
                continue

            if tok.kind == "IDENT" and tok.value == "content":
                self._advance()
                node["content"] = self._parse_string()
                continue

            # Unknown field in talk block -- treat as key/value
            key_tok = self._advance()
            node[key_tok.value] = self._parse_value()

        self._expect("RBRACE")
        if "content" not in node:
            node["content"] = ""
        if effects:
            node["effects"] = effects
        return label, node, options

    def _parse_talk_option(self, npc_id: str) -> dict[str, Any]:
        """Parse: option "text" -> label { sub-fields }"""
        self._expect("IDENT", "option")
        text = self._parse_string()
        opt: dict[str, Any] = {"text": text}

        # Optional arrow -> next label
        if self._at("ARROW"):
            self._advance()
            next_tok = self._expect("IDENT")
            if next_tok.value == "end":
                opt["next_node_id"] = None
            else:
                opt["next_node_id"] = f"{npc_id}_{next_tok.value}"

        # Optional sub-block with conditions
        if self._at("LBRACE"):
            self._advance()
            while not self._at("RBRACE"):
                key_tok = self._expect("IDENT")
                key = key_tok.value
                if key == "require_flag":
                    opt.setdefault("required_flags", []).append(self._parse_value())
                elif key == "exclude_flag":
                    opt.setdefault("excluded_flags", []).append(self._parse_value())
                elif key == "require_item":
                    opt.setdefault("required_items", []).append(self._parse_value())
                elif key == "set_flags":
                    opt["set_flags"] = self._parse_list()
                elif key == "required_flags":
                    opt["required_flags"] = self._parse_list()
                elif key == "excluded_flags":
                    opt["excluded_flags"] = self._parse_list()
                elif key == "required_items":
                    opt["required_items"] = self._parse_list()
                else:
                    opt[key] = self._parse_value()
            self._expect("RBRACE")

        return opt

    # -- Lock block --

    _LOCK_FIELD_MAP: ClassVar[dict[str, str]] = {
        "type": "lock_type",
        "key": "key_item_id",
        "consume": "consume_key",
        "locked": "locked_message",
        "unlocked": "unlock_message",
        "puzzle": "puzzle_id",
        "flags": "required_flags",
        "target_exit": "target_exit_id",
        "code": "combination",
    }

    def _parse_lock_block(self) -> None:
        self._expect("IDENT", "lock")
        lock_id_tok = self._expect("IDENT")
        lock_id = lock_id_tok.value
        self._expect("LBRACE")

        lock: dict[str, Any] = {"id": lock_id}
        exit_route: tuple[str, str, str] | None = None

        while not self._at("RBRACE"):
            key_tok = self._expect("IDENT")
            raw_key = key_tok.value

            # exit field: from -> to direction
            if raw_key == "exit":
                from_tok = self._expect("IDENT")
                self._expect("ARROW")
                to_tok = self._expect("IDENT")
                dir_tok = self._expect("IDENT")
                exit_route = (from_tok.value, to_tok.value, dir_tok.value)
                continue

            key = self._LOCK_FIELD_MAP.get(raw_key, raw_key)
            lock[key] = self._parse_value()

        self._expect("RBRACE")

        if exit_route is not None:
            self._lock_exit_routes.append(
                (lock, exit_route[0], exit_route[1], exit_route[2])
            )
        self._locks.append(lock)

    # -- Puzzle block --

    _PUZZLE_FIELD_MAP: ClassVar[dict[str, str]] = {
        "in": "room_id",
        "score": "score_value",
        "steps": "solution_steps",
        "hint": "hint_text",
    }

    def _parse_puzzle_block(self) -> None:
        self._expect("IDENT", "puzzle")
        puzzle_id_tok = self._expect("IDENT")
        puzzle_id = puzzle_id_tok.value
        self._expect("LBRACE")

        puzzle: dict[str, Any] = {"id": puzzle_id}

        while not self._at("RBRACE"):
            key_tok = self._expect("IDENT")
            key = self._PUZZLE_FIELD_MAP.get(key_tok.value, key_tok.value)
            puzzle[key] = self._parse_value()

        self._expect("RBRACE")
        self._puzzles.append(puzzle)

    # -- Flag line (single-line) --

    def _parse_flag_line(self) -> None:
        self._expect("IDENT", "flag")
        flag_id_tok = self._expect("IDENT")
        flag_id = flag_id_tok.value

        description = ""
        if self._at("STRING"):
            description = self._parse_string()

        # Also support block form: flag id { description "..." }
        if self._at("LBRACE"):
            self._advance()
            flag_data: dict[str, Any] = {"id": flag_id, "value": False}
            while not self._at("RBRACE"):
                key_tok = self._expect("IDENT")
                flag_data[key_tok.value] = self._parse_value()
            self._expect("RBRACE")
            flag_data.setdefault("description", description)
            self._flags.append(flag_data)
            return

        self._flags.append({
            "id": flag_id,
            "description": description,
            "value": False,
        })

    # -- Quest block --

    def _parse_quest_block(self) -> None:
        self._expect("IDENT", "quest")

        # Parse quest ID, possibly with type prefix: main:id or side:id
        id_tok = self._expect("IDENT")
        quest_id = id_tok.value
        quest_type: str | None = None

        if self._at("COLON"):
            # The first IDENT was the type prefix
            self._advance()
            quest_type = quest_id
            id_tok = self._expect("IDENT")
            quest_id = id_tok.value

        self._expect("LBRACE")

        quest: dict[str, Any] = {"id": quest_id}
        if quest_type:
            quest["quest_type"] = quest_type

        objectives: list[dict[str, Any]] = []
        obj_index = 0

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "objective":
                obj = self._parse_inline_objective(quest_id, obj_index)
                objectives.append(obj)
                obj_index += 1
                continue

            key_tok = self._expect("IDENT")
            key = key_tok.value
            field_map = {
                "completion": "completion_flag",
                "discovery": "discovery_flag",
                "score": "score_value",
            }
            mapped_key = field_map.get(key, key)
            quest[mapped_key] = self._parse_value()

        self._expect("RBRACE")
        quest["objectives"] = objectives
        self._quests.append(quest)

    def _parse_inline_objective(
        self, quest_id: str, index: int
    ) -> dict[str, Any]:
        """Parse: objective "desc" -> flag (optional, bonus: N)"""
        self._expect("IDENT", "objective")
        description = self._parse_string()
        obj: dict[str, Any] = {
            "id": f"{quest_id}_obj_{index}",
            "description": description,
            "order_index": index,
            "is_optional": False,
            "bonus_score": 0,
        }

        if self._at("ARROW"):
            self._advance()
            flag_tok = self._expect("IDENT")
            obj["completion_flag"] = flag_tok.value

        # Optional parenthetical modifiers
        if self._at("LPAREN"):
            self._advance()
            while not self._at("RPAREN"):
                mod_tok = self._peek()
                if mod_tok.kind == "IDENT" and mod_tok.value == "optional":
                    self._advance()
                    obj["is_optional"] = True
                elif mod_tok.kind == "IDENT" and mod_tok.value == "bonus":
                    self._advance()
                    self._match("COLON")
                    num_tok = self._expect("NUMBER")
                    obj["bonus_score"] = int(num_tok.value)
                elif mod_tok.kind == "IDENT" and mod_tok.value == "order":
                    self._advance()
                    self._match("COLON")
                    num_tok = self._expect("NUMBER")
                    obj["order_index"] = int(num_tok.value)
                else:
                    self._advance()
                self._match("COMMA")
            self._expect("RPAREN")

        return obj

    # -- Command (on) block --

    def _parse_on_block(self) -> None:
        """Parse: on "pattern" in [rooms] { require/effect/success/fail/once }"""
        self._expect("IDENT", "on")
        pattern = self._parse_string()

        context_rooms: list[str] | None = None
        if self._at("IDENT") and self._peek().value == "in":
            self._advance()
            if self._at("LBRACKET"):
                context_rooms = self._parse_list()
            else:
                room_tok = self._expect("IDENT")
                context_rooms = [room_tok.value]

        self._expect("LBRACE")

        preconditions: list[dict[str, Any]] = []
        effects: list[dict[str, Any]] = []
        cmd: dict[str, Any] = {
            "one_shot": False,
            "priority": 0,
            "executed": False,
        }

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "require":
                self._advance()
                name, args = self._parse_func_call()
                preconditions.append(self._compile_precondition(name, args))
                continue
            if tok.kind == "IDENT" and tok.value == "effect":
                self._advance()
                name, args = self._parse_func_call()
                effects.append(self._compile_effect(name, args))
                continue
            if tok.kind == "IDENT" and tok.value == "once":
                self._advance()
                cmd["one_shot"] = True
                continue
            if tok.kind == "IDENT" and tok.value == "success":
                self._advance()
                cmd["success_message"] = self._parse_string()
                continue
            if tok.kind == "IDENT" and tok.value == "fail":
                self._advance()
                cmd["failure_message"] = self._parse_string()
                continue
            if tok.kind == "IDENT" and tok.value == "done":
                self._advance()
                cmd["done_message"] = self._parse_string()
                continue
            if tok.kind == "IDENT" and tok.value == "priority":
                self._advance()
                cmd["priority"] = int(self._expect("NUMBER").value)
                continue

            # Skip unknown fields
            self._advance()
            if (
                self._at("STRING")
                or self._at("NUMBER")
                or self._at("IDENT")
                or self._at("LBRACKET")
            ):
                self._parse_value()

        self._expect("RBRACE")

        # Auto-generate ID from pattern, deduplicate.
        slug = re.sub(r"[^a-z0-9]+", "_", pattern.lower()).strip("_")
        base_id = f"on_{slug}_{context_rooms[0]}" if context_rooms else f"on_{slug}"
        existing_ids = {c["id"] for c in self._commands}
        cmd_id = base_id
        counter = 2
        while cmd_id in existing_ids:
            cmd_id = f"{base_id}_{counter}"
            counter += 1

        # Extract verb
        verb = pattern.split()[0].lower() if pattern.split() else "do"
        # Strip {braces} from verb
        verb = re.sub(r"[{}]", "", verb)

        cmd.update({
            "id": cmd_id,
            "verb": verb,
            "pattern": pattern,
            "preconditions": preconditions,
            "effects": effects,
            "context_room_ids": context_rooms or [],
        })
        cmd.setdefault("success_message", "")
        cmd.setdefault("failure_message", "")
        cmd.setdefault("done_message", "")

        self._commands.append(cmd)

    # -- Trigger (when) block --

    _EVENT_TYPE_ARGS: ClassVar[dict[str, str]] = {
        "room_enter": "room_id",
        "flag_set": "flag",
        "item_taken": "item_id",
        "item_dropped": "item_id",
        "dialogue_node": "node_id",
    }

    def _parse_when_block(self) -> None:
        """Parse: when event_type(event_arg) { require/effect/message/once }"""
        self._expect("IDENT", "when")

        # Parse event_type(arg) function-call syntax
        event_name, event_args = self._parse_func_call()

        self._expect("LBRACE")

        preconditions: list[dict[str, Any]] = []
        effects: list[dict[str, Any]] = []
        trigger: dict[str, Any] = {
            "one_shot": False,
            "priority": 0,
            "executed": False,
            "is_enabled": True,
        }

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "require":
                self._advance()
                name, args = self._parse_func_call()
                preconditions.append(self._compile_precondition(name, args))
                continue
            if tok.kind == "IDENT" and tok.value == "effect":
                self._advance()
                name, args = self._parse_func_call()
                effects.append(self._compile_effect(name, args))
                continue
            if tok.kind == "IDENT" and tok.value == "once":
                self._advance()
                trigger["one_shot"] = True
                continue
            if tok.kind == "IDENT" and tok.value == "message":
                self._advance()
                trigger["message"] = self._parse_string()
                continue
            if tok.kind == "IDENT" and tok.value == "priority":
                self._advance()
                trigger["priority"] = int(self._expect("NUMBER").value)
                continue

            # Skip unknown fields
            self._advance()
            if (
                self._at("STRING")
                or self._at("NUMBER")
                or self._at("IDENT")
                or self._at("LBRACKET")
            ):
                self._parse_value()

        self._expect("RBRACE")

        # Build event_data
        event_data: dict[str, Any] = {}
        data_key = self._EVENT_TYPE_ARGS.get(event_name)
        if data_key and event_args:
            event_data[data_key] = str(event_args[0])

        base_id = f"when_{event_name}"
        if event_args:
            base_id += f"_{event_args[0]}"
        # Deduplicate: append _2, _3, etc. if the ID already exists.
        existing_ids = {t["id"] for t in self._triggers}
        trigger_id = base_id
        counter = 2
        while trigger_id in existing_ids:
            trigger_id = f"{base_id}_{counter}"
            counter += 1

        trigger.update({
            "id": trigger_id,
            "event_type": event_name,
            "event_data": event_data,
            "preconditions": preconditions,
            "effects": effects,
        })
        trigger.setdefault("message", "")

        self._triggers.append(trigger)

    # -- Standalone command block (from Architect spec) --

    def _parse_command_block(self) -> None:
        """Parse: command id { verb, pattern, require, effect, ... }"""
        self._expect("IDENT", "command")
        cmd_id_tok = self._expect("IDENT")
        cmd_id = cmd_id_tok.value
        self._expect("LBRACE")

        preconditions: list[dict[str, Any]] = []
        effects: list[dict[str, Any]] = []
        cmd: dict[str, Any] = {
            "id": cmd_id,
            "one_shot": False,
            "priority": 0,
            "executed": False,
        }

        field_map = {
            "in_rooms": "context_room_ids",
            "on_fail": "failure_message",
            "on_done": "done_message",
        }

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "require":
                self._advance()
                name, args = self._parse_func_call()
                preconditions.append(self._compile_precondition(name, args))
                continue
            if tok.kind == "IDENT" and tok.value == "effect":
                self._advance()
                name, args = self._parse_func_call()
                effects.append(self._compile_effect(name, args))
                continue

            key_tok = self._expect("IDENT")
            key = field_map.get(key_tok.value, key_tok.value)
            cmd[key] = self._parse_value()

        self._expect("RBRACE")
        cmd["preconditions"] = preconditions
        cmd["effects"] = effects

        # Ensure verb is set
        if "verb" not in cmd and "pattern" in cmd:
            pattern_str = str(cmd["pattern"])
            words = pattern_str.split()
            cmd["verb"] = re.sub(r"[{}]", "", words[0]).lower() if words else "do"

        cmd.setdefault("success_message", "")
        cmd.setdefault("failure_message", "")
        cmd.setdefault("done_message", "")
        cmd.setdefault("context_room_ids", [])
        self._commands.append(cmd)

    # -- Standalone trigger block (from Architect spec) --

    def _parse_trigger_block(self) -> None:
        """Parse: trigger id { on, when, require, effect, ... }"""
        self._expect("IDENT", "trigger")
        trigger_id_tok = self._expect("IDENT")
        trigger_id = trigger_id_tok.value
        self._expect("LBRACE")

        preconditions: list[dict[str, Any]] = []
        effects: list[dict[str, Any]] = []
        trigger: dict[str, Any] = {
            "id": trigger_id,
            "one_shot": False,
            "priority": 0,
            "executed": False,
            "is_enabled": True,
        }
        event_data: dict[str, Any] = {}

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "require":
                self._advance()
                name, args = self._parse_func_call()
                preconditions.append(self._compile_precondition(name, args))
                continue
            if tok.kind == "IDENT" and tok.value == "effect":
                self._advance()
                name, args = self._parse_func_call()
                effects.append(self._compile_effect(name, args))
                continue
            if tok.kind == "IDENT" and tok.value == "when":
                self._advance()
                wd_key = self._expect("IDENT").value
                self._expect("EQUALS")
                wd_val = self._parse_value()
                event_data[wd_key] = wd_val
                continue

            key_tok = self._expect("IDENT")
            key = key_tok.value
            if key == "on":
                trigger["event_type"] = self._parse_value()
            elif key == "one_shot":
                trigger["one_shot"] = self._parse_value()
            elif key == "message":
                trigger["message"] = self._parse_string()
            elif key == "priority":
                trigger["priority"] = int(self._expect("NUMBER").value)
            else:
                trigger[key] = self._parse_value()

        self._expect("RBRACE")
        trigger["event_data"] = event_data
        trigger["preconditions"] = preconditions
        trigger["effects"] = effects
        trigger.setdefault("message", "")
        self._triggers.append(trigger)

    # -- Standalone dialogue / option blocks (from Architect spec) --

    def _parse_standalone_dialogue_block(self) -> None:
        self._expect("IDENT", "dialogue")
        node_id_tok = self._expect("IDENT")
        node_id = node_id_tok.value
        self._expect("LBRACE")

        node: dict[str, Any] = {"id": node_id}
        field_map = {"npc": "npc_id"}

        while not self._at("RBRACE"):
            key_tok = self._expect("IDENT")
            key = field_map.get(key_tok.value, key_tok.value)
            node[key] = self._parse_value()

        self._expect("RBRACE")
        self._dialogue_nodes.append(node)

    def _parse_standalone_option_block(self) -> None:
        self._expect("IDENT", "option")
        opt_id_tok = self._expect("IDENT")
        opt_id = opt_id_tok.value
        self._expect("LBRACE")

        opt: dict[str, Any] = {"id": opt_id}
        field_map = {
            "node": "node_id",
            "next_node": "next_node_id",
            "require_flags": "required_flags",
            "exclude_flags": "excluded_flags",
            "require_items": "required_items",
        }

        while not self._at("RBRACE"):
            key_tok = self._expect("IDENT")
            key = field_map.get(key_tok.value, key_tok.value)
            opt[key] = self._parse_value()

        self._expect("RBRACE")
        self._dialogue_options.append(opt)

    # -- Interaction response block --

    _INTERACTION_FIELD_MAP: ClassVar[dict[str, str]] = {
        "tag": "item_tag",
        "target": "target_category",
        "response": "response",
        "consumes": "consumes",
        "score": "score_change",
        "sets_flag": "flag_to_set",
    }

    def _parse_interaction_block(self) -> None:
        self._expect("IDENT", "interaction")
        resp_id_tok = self._expect("IDENT")
        resp_id = resp_id_tok.value
        self._expect("LBRACE")

        resp: dict[str, Any] = {"id": resp_id}
        effects: list[dict[str, Any]] = []

        while not self._at("RBRACE"):
            tok = self._peek()
            if tok.kind == "IDENT" and tok.value == "effect":
                self._advance()
                name, args = self._parse_func_call()
                effects.append(self._compile_effect(name, args))
                continue

            key_tok = self._expect("IDENT")
            key = self._INTERACTION_FIELD_MAP.get(key_tok.value, key_tok.value)
            resp[key] = self._parse_value()

        self._expect("RBRACE")
        if effects:
            resp["effects"] = effects
        self._interaction_responses.append(resp)

    # -- Exit route resolution --

    def _resolve_exit_routes(self) -> None:
        """Resolve lock exit routes and NPC blocking routes to exit IDs."""
        # Build exit lookup: (from_room, direction) -> exit_id
        exit_lookup: dict[tuple[str, str], str] = {}
        for exit_data in self._exits:
            key = (exit_data["from_room_id"], exit_data["direction"])
            exit_lookup[key] = exit_data["id"]

        for lock, from_room, _to_room, direction in self._lock_exit_routes:
            key = (from_room, direction)
            exit_id = exit_lookup.get(key)
            if exit_id:
                lock["target_exit_id"] = exit_id
            else:
                # Fallback: construct the expected ID
                lock["target_exit_id"] = f"{from_room}_{direction}"

        for npc, from_room, _to_room, direction in self._npc_blocking_routes:
            key = (from_room, direction)
            exit_id = exit_lookup.get(key)
            if exit_id:
                npc["blocked_exit_id"] = exit_id
            else:
                npc["blocked_exit_id"] = f"{from_room}_{direction}"

    def _fix_container_refs(self) -> None:
        """If an item's room_id points to another item, reclassify as container_id."""
        room_ids = {room["id"] for room in self._rooms}
        item_ids = {item["id"] for item in self._items}
        for item in self._items:
            rid = item.get("room_id")
            if rid and rid not in room_ids and rid in item_ids:
                item["container_id"] = rid
                item.pop("room_id", None)

    # -- Output assembly --

    def _build_output(self) -> dict[str, Any]:
        return {
            "format": "anyzork.import.v1",
            "game": self._game or {},
            "player": self._player or {},
            "rooms": self._rooms,
            "exits": self._exits,
            "items": self._items,
            "npcs": self._npcs,
            "dialogue_nodes": self._dialogue_nodes,
            "dialogue_options": self._dialogue_options,
            "locks": self._locks,
            "puzzles": self._puzzles,
            "flags": self._flags,
            "commands": self._commands,
            "quests": self._quests,
            "triggers": self._triggers,
            "interactions": [],
            "interaction_responses": self._interaction_responses,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _strip_fences(source: str) -> str:
    """Strip markdown code fences that LLMs sometimes wrap output in."""
    text = source.strip()
    if text.startswith("```"):
        # Remove opening fence (```zorkscript, ```text, ```, etc.)
        first_nl = text.index("\n") if "\n" in text else len(text)
        text = text[first_nl + 1:]
    if text.rstrip().endswith("```"):
        text = text.rstrip()[:-3]
    return text.strip()


def parse_zorkscript(source: str) -> dict[str, Any]:
    """Parse ZorkScript source and return a normalized import spec dict."""
    tokens = _tokenize(_strip_fences(source))
    parser = _Parser(tokens)
    return parser.parse()
