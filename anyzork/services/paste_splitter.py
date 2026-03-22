"""Split pasted LLM output into individual .zorkscript files."""

from __future__ import annotations

import re

# ZorkScript top-level keywords that start blocks
_ZORKSCRIPT_KEYWORDS = {
    "game", "player", "room", "item", "npc", "quest", "flag", "lock",
    "puzzle", "on", "when", "interaction", "command",
}


def split_pasted_output(
    raw_text: str,
    expected_files: list[str],
) -> dict[str, str]:
    """Split pasted LLM output into named files.

    Returns a dict mapping filename -> content.
    """
    # Try to split by filename markers first (preserves file structure)
    result = _split_by_filename_markers(raw_text, expected_files)
    if result:
        return result

    # No file markers — extract ZorkScript content, stripping markdown
    text = _extract_zorkscript(raw_text)

    # Fallback: put everything in the first file
    return {expected_files[0]: text.strip()}


def _extract_zorkscript(raw_text: str) -> str:
    """Extract ZorkScript content from LLM output that may include markdown.

    If code fences are found, extracts only content inside them.
    Otherwise, strips obvious markdown (headers, prose) and keeps
    lines that look like ZorkScript.
    """
    # Try to extract content from code fences first
    fenced = _extract_from_fences(raw_text)
    if fenced:
        return fenced

    # No fences — filter out markdown prose
    return _strip_markdown_prose(raw_text)


def _extract_from_fences(text: str) -> str | None:
    """Extract content from markdown code fences (```zorkscript ... ```)."""
    pattern = re.compile(
        r"^```(?:zorkscript)?\s*\n(.*?)^```\s*$",
        re.MULTILINE | re.DOTALL,
    )
    blocks = pattern.findall(text)
    if not blocks:
        return None
    return "\n\n".join(block.strip() for block in blocks if block.strip())


def _strip_markdown_prose(text: str) -> str:
    """Remove lines that look like markdown prose, keeping ZorkScript."""
    lines = text.split("\n")
    result: list[str] = []
    in_block = False

    for line in lines:
        stripped = line.strip()

        # Track brace depth — inside a block, keep everything
        if in_block:
            result.append(line)
            if stripped == "}":
                in_block = False
            continue

        # Keep blank lines (spacing between blocks)
        if not stripped:
            result.append(line)
            continue

        # Keep ZorkScript comments (single #) but skip markdown headers (## etc.)
        if stripped.startswith("#") and not stripped.startswith("##"):
            result.append(line)
            continue

        # Keep lines starting with ZorkScript keywords
        first_word = stripped.split()[0] if stripped.split() else ""
        # Handle "quest main:id" and "quest side:id"
        bare_word = first_word.split(":")[0] if ":" in first_word else first_word
        if bare_word in _ZORKSCRIPT_KEYWORDS:
            result.append(line)
            if "{" in stripped:
                in_block = True
            continue

        # Keep lines that look like ZorkScript content (indented key-value)
        if line.startswith("  ") or line.startswith("\t"):
            result.append(line)
            continue

        # Keep closing braces
        if stripped.startswith("}"):
            result.append(line)
            continue

        # Skip everything else (markdown headers, prose, etc.)

    return "\n".join(result)


def _split_by_filename_markers(
    text: str,
    expected_files: list[str],
) -> dict[str, str] | None:
    """Try to split text by lines containing expected filenames."""
    lines = text.split("\n")

    file_starts: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        for filename in expected_files:
            if _is_filename_header(stripped, filename):
                file_starts.append((i, filename))
                break

    if not file_starts:
        return None

    # Extract content between file headers
    result: dict[str, str] = {}
    for idx, (start_line, filename) in enumerate(file_starts):
        end_line = file_starts[idx + 1][0] if idx + 1 < len(file_starts) else len(lines)

        content_lines = lines[start_line + 1 : end_line]
        content = "\n".join(content_lines).strip()
        # Clean any remaining markdown from within the section
        fenced = _extract_from_fences(content)
        if fenced:
            content = fenced
        if content:
            result[filename] = content

    return result if result else None


def _is_filename_header(line: str, filename: str) -> bool:
    """Check if a line is a header/marker for a specific filename."""
    if line == filename:
        return True
    patterns = [
        rf"^#+\s*`?{re.escape(filename)}`?",  # # game.zorkscript
        rf"^---+\s*{re.escape(filename)}",  # --- game.zorkscript
        rf"^`{re.escape(filename)}`",  # `game.zorkscript`
        rf"^\*\*{re.escape(filename)}\*\*",  # **game.zorkscript**
        rf"^File:\s*{re.escape(filename)}",  # File: game.zorkscript
        rf"^// {re.escape(filename)}",  # // game.zorkscript
        rf"^{re.escape(filename)}\s*:",  # game.zorkscript:
        rf"^\d+\.\s*`?{re.escape(filename)}`?",  # 1. game.zorkscript
    ]
    return any(re.match(p, line, re.IGNORECASE) for p in patterns)
