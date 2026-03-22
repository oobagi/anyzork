"""Tests for paste_splitter — splitting pasted LLM output into files."""

from __future__ import annotations

from anyzork.services.paste_splitter import split_pasted_output


class TestSplitByHashHeaders:
    def test_two_files_with_hash_headers(self) -> None:
        raw = (
            "# game.zorkscript\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
            "\n"
            "# rooms.zorkscript\n"
            "room foyer {\n"
            '  name "Foyer"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript", "rooms.zorkscript"])
        assert "game.zorkscript" in result
        assert "rooms.zorkscript" in result
        assert 'title "Test"' in result["game.zorkscript"]
        assert 'name "Foyer"' in result["rooms.zorkscript"]

    def test_three_files_with_hash_headers(self) -> None:
        raw = (
            "# puzzles.zorkscript\n"
            "puzzle box_puzzle {\n"
            '  name "Box"\n'
            "}\n"
            "\n"
            "# quests.zorkscript\n"
            "quest main_quest {\n"
            '  name "Main"\n'
            "}\n"
            "\n"
            "# commands.zorkscript\n"
            "on examine mirror {\n"
            '  say "You see yourself."\n'
            "}\n"
        )
        expected = ["puzzles.zorkscript", "quests.zorkscript", "commands.zorkscript"]
        result = split_pasted_output(raw, expected)
        assert len(result) == 3
        assert "box_puzzle" in result["puzzles.zorkscript"]
        assert "main_quest" in result["quests.zorkscript"]
        assert "examine mirror" in result["commands.zorkscript"]


class TestSplitStripsMarkdownFences:
    def test_strips_opening_and_closing_fences(self) -> None:
        raw = (
            "# game.zorkscript\n"
            "```zorkscript\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
            "```\n"
            "\n"
            "# rooms.zorkscript\n"
            "```zorkscript\n"
            "room foyer {\n"
            '  name "Foyer"\n'
            "}\n"
            "```\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript", "rooms.zorkscript"])
        assert "game.zorkscript" in result
        assert "rooms.zorkscript" in result
        # Code fences should be stripped
        assert "```" not in result["game.zorkscript"]
        assert "```" not in result["rooms.zorkscript"]
        assert 'title "Test"' in result["game.zorkscript"]

    def test_strips_bare_code_fences(self) -> None:
        raw = (
            "# game.zorkscript\n"
            "```\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
            "```\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript", "rooms.zorkscript"])
        assert "```" not in result["game.zorkscript"]


class TestSplitFallbackSingleFile:
    def test_no_markers_puts_all_in_first_file(self) -> None:
        raw = (
            "game {\n"
            '  title "Test"\n'
            "}\n"
            "\n"
            "room foyer {\n"
            '  name "Foyer"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript", "rooms.zorkscript"])
        assert len(result) == 1
        assert "game.zorkscript" in result
        assert 'title "Test"' in result["game.zorkscript"]
        assert 'name "Foyer"' in result["game.zorkscript"]


class TestSplitVariousHeaderFormats:
    def test_backtick_header(self) -> None:
        raw = (
            "`game.zorkscript`\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript"])
        assert "game.zorkscript" in result

    def test_bold_header(self) -> None:
        raw = (
            "**game.zorkscript**\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript"])
        assert "game.zorkscript" in result

    def test_file_colon_header(self) -> None:
        raw = (
            "File: game.zorkscript\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript"])
        assert "game.zorkscript" in result

    def test_numbered_header(self) -> None:
        raw = (
            "1. game.zorkscript\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
            "\n"
            "2. rooms.zorkscript\n"
            "room foyer {\n"
            '  name "Foyer"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript", "rooms.zorkscript"])
        assert len(result) == 2

    def test_numbered_backtick_header(self) -> None:
        raw = (
            "1. `game.zorkscript`\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript"])
        assert "game.zorkscript" in result

    def test_dash_separator_header(self) -> None:
        raw = (
            "--- game.zorkscript\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript"])
        assert "game.zorkscript" in result

    def test_comment_header(self) -> None:
        raw = (
            "// game.zorkscript\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript"])
        assert "game.zorkscript" in result

    def test_filename_colon_header(self) -> None:
        raw = (
            "game.zorkscript:\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript"])
        assert "game.zorkscript" in result

    def test_bare_filename_header(self) -> None:
        raw = (
            "game.zorkscript\n"
            "game {\n"
            '  title "Test"\n'
            "}\n"
        )
        result = split_pasted_output(raw, ["game.zorkscript"])
        assert "game.zorkscript" in result
