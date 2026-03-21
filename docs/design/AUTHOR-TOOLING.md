# Design: Author-Facing Tooling (Issue #13)

## Problem

Authors working with ZorkScript have poor feedback loops. When something is wrong with their script, they discover it only after a full `anyzork import` cycle -- which creates a temporary SQLite database, inserts every entity, runs post-import validation, and then either succeeds or throws a terse error message. The specific problems:

1. **Parse errors lose context.** `ZorkScriptError` carries a line number, but the CLI catches it as a generic `Exception` and prints `Import failed: line 42: expected IDENT but found RBRACE`. No source snippet. No suggestion.

2. **No way to check without compiling.** Validation only runs against the populated `.zork` database. If an author just wants to know "is my script well-formed and internally consistent?", they must pay the full import cost and get a `.zork` file they don't want.

3. **Warnings are opaque.** Post-import warnings are plain strings stripped of their severity, category, and structure. The CLI shows at most 8 and hides the rest.

4. **Three unrelated error types.** `ZorkScriptError` (parser), `ImportSpecError` (normalizer/compiler), and `ValidationError` (post-import checks) each have different shapes. Tooling that wants to present all diagnostics uniformly has to special-case each one.


## Design

### 1. Unified Diagnostic Type

A single `Diagnostic` dataclass that every stage of the pipeline can produce. It replaces nothing -- `ZorkScriptError` stays an exception (you can't parse past a syntax error), `ImportSpecError` stays an exception (the compile is aborted), and `ValidationError` stays a dataclass (multiple findings are collected). But all three can be converted into `Diagnostic` for uniform presentation.

```python
# anyzork/diagnostics.py

@dataclass(frozen=True)
class Diagnostic:
    severity: str          # "error" | "warning" | "info"
    category: str          # "parse", "normalize", "spatial", "lock", "item", ...
    message: str           # Human-readable, no formatting markup
    line: int | None       # Source line number, if known
    hint: str | None       # Optional fix suggestion

    def __str__(self) -> str:
        tag = self.severity.upper()
        loc = f"line {self.line}: " if self.line else ""
        base = f"[{tag}][{self.category}] {loc}{self.message}"
        if self.hint:
            base += f"\n  hint: {self.hint}"
        return base
```

**Conversion functions** in the same module:

```python
def from_zorkscript_error(exc: ZorkScriptError) -> Diagnostic:
    return Diagnostic(
        severity="error",
        category="parse",
        message=exc.args[0] if not exc.line else exc.args[0].removeprefix(f"line {exc.line}: "),
        line=exc.line,
        hint=None,
    )

def from_import_spec_error(exc: ImportSpecError) -> Diagnostic:
    return Diagnostic(
        severity="error",
        category="compile",
        message=str(exc),
        line=None,
        hint=None,
    )

def from_validation_error(ve: ValidationError) -> Diagnostic:
    return Diagnostic(
        severity=ve.severity,
        category=ve.category,
        message=ve.message,
        line=None,
        hint=None,
    )
```

**Why a flat dataclass and not a class hierarchy:** The three source types have fundamentally different roles (two are exceptions, one is a collected finding). Forcing them into a shared base class would be architecture astronautics. A simple conversion function at the boundary is clearer and keeps each module independent.

**Why `hint` is `str | None` and not a structured object:** Hints are for human consumption. A plain string ("Did you mean 'forest_clearing'?") is sufficient. If we later want machine-actionable fixes (auto-correct), that's a different feature with different data needs.


### 2. `anyzork lint` Command

#### What It Checks

Lint runs two phases, both without creating a database:

**Phase 1: Parse.** Run the existing `parse_zorkscript()` parser. If it raises `ZorkScriptError`, convert to `Diagnostic` and stop (the script is syntactically broken, further checks are meaningless).

**Phase 2: Spec-level checks.** Operate on the parsed spec dict (the output of `parse_zorkscript()`). These are static checks that don't need a populated database -- they only need the spec's entity lists and their cross-references.

Spec-level checks to implement:

| Check | Category | Severity | Description |
|-------|----------|----------|-------------|
| Missing game block | `structure` | error | `spec["game"]` is empty or missing `title` |
| Missing player block | `structure` | error | No `player` with `start_room_id` |
| No rooms defined | `structure` | error | `spec["rooms"]` is empty |
| Start room exists | `reference` | error | `player.start_room_id` is not in the rooms list |
| Exit references valid rooms | `reference` | error | `from_room_id` / `to_room_id` not in rooms |
| Item room references | `reference` | error | `item.room_id` not in rooms (when set) |
| NPC room references | `reference` | error | `npc.room_id` not in rooms (when set) |
| Lock target exit exists | `reference` | error | `lock.target_exit_id` not in exits |
| Key item exists | `reference` | error | `lock.key_item_id` not in items |
| Duplicate entity IDs | `structure` | error | Two rooms/items/etc. with the same `id` |
| Unknown precondition/effect types | `dsl` | error | Types not in the known sets from `validation.py` |
| Exit direction validity | `reference` | error | Directions not in `ALLOWED_EXIT_DIRECTIONS` |
| Missing reverse exits | `spatial` | warning | One-way exits (may be intentional) |
| Command/trigger references | `reference` | error | Preconditions/effects referencing nonexistent entity IDs |

These checks can reuse the entity ID sets and precondition/effect type constants already defined in `validation.py` (`VALID_PRECONDITION_TYPES`, `VALID_EFFECT_TYPES`, etc.) and `_constants.py` (`ALLOWED_EXIT_DIRECTIONS`).

#### Where It Lives

```
anyzork/
    lint.py              # lint_spec(spec) -> list[Diagnostic]
    diagnostics.py       # Diagnostic dataclass + converters
```

`lint.py` exports a single function:

```python
def lint_spec(spec: dict[str, Any]) -> list[Diagnostic]:
    """Run static checks on a parsed ZorkScript spec. No DB required."""
```

The function collects all findings and returns them. It does not raise exceptions for validation failures.

#### CLI Integration

```python
@cli.command()
@click.argument("source", required=False, default="-")
def lint(source: str) -> None:
    """Check ZorkScript for errors without importing."""
```

Behavior:
- Reads from file path or stdin (same resolution as `import`)
- Parses with `parse_zorkscript()`, catching `ZorkScriptError`
- If parse succeeds, runs `lint_spec()` on the result
- Prints diagnostics grouped by severity: errors first, then warnings
- Exit code 0 if no errors (warnings are OK), exit code 1 if any errors

Output format (plain text, no JSON):

```
myworld.zs:42: [ERROR][parse] expected IDENT but found RBRACE '}'
```

or for spec-level checks (no line number available):

```
[ERROR][reference] Exit 'forest_to_cave' references non-existent room 'deep_cave'
[WARN][spatial] Exit 'cave_entrance' (village -> cave) has no matching reverse exit
```

Summary line at the end:

```
2 errors, 1 warning
```

or:

```
No issues found.
```

#### What Lint Does NOT Check

Lint deliberately skips anything that requires a populated database:
- BFS reachability (needs the exit graph built from DB queries)
- Lock solvability simulation (needs full item/lock/exit state)
- Container nesting depth (needs recursive DB queries)
- Win condition reachability

These remain the domain of full `validate_game()` during import. The boundary is clean: lint checks the spec dict, validation checks the compiled database.


### 3. `anyzork import --report`

#### What the Report Contains

`--report` extends the existing import flow. It does not replace it. The game is still compiled and validated exactly as today, but instead of printing a one-line success message plus truncated warnings, it prints a structured report.

Report sections:

1. **Summary** -- game title, room count, item count, NPC count, exit count, command count
2. **Lint diagnostics** -- run `lint_spec()` against the parsed spec before compiling (these are fast and can catch issues before the DB is created)
3. **Compile result** -- success/failure, output path
4. **Post-import validation** -- full list of `ValidationError` findings, converted to `Diagnostic` with severity and category
5. **Totals** -- error count, warning count

The report always shows all diagnostics (no 8-item cap). This is the "give me everything" mode.

#### CLI Integration

```python
@cli.command("import")
@click.argument("spec_source", required=False, default="-")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--print-template", is_flag=True)
@click.option("--report", is_flag=True, help="Print detailed import diagnostics.")
def import_game(spec_source, output, print_template, report):
```

When `--report` is set:
- Run lint checks first (spec-level), collect diagnostics
- If lint finds errors, still attempt compilation (the author may want to see the full picture)
- Run compilation and validation as normal
- Convert all `ValidationError` results to `Diagnostic`
- Print the combined report
- Exit code follows the same rule: 0 if the game compiled and has no validation errors, 1 otherwise

When `--report` is not set, behavior is identical to today (backward compatible).

#### Output Format

```
=== Import Report: The Haunted Manor ===

Entities: 12 rooms, 8 exits, 15 items, 3 NPCs, 5 commands, 2 quests

--- Lint (spec-level) ---
No issues found.

--- Compile ---
OK -> ~/.anyzork/games/the_haunted_manor.zork

--- Validation (post-import) ---
[WARN][spatial] Exit 'hall_to_cellar' (hall -> cellar) has no matching reverse exit
[WARN][item] Item 'dusty_key' is already named in room 'attic' prose

--- Totals ---
0 errors, 2 warnings

Play it with:  anyzork play the_haunted_manor
```

If compilation fails:

```
=== Import Report ===

--- Lint (spec-level) ---
[ERROR][reference] Lock 'cellar_lock' targets non-existent exit 'cellar_door'
[ERROR][reference] Item 'gold_key' references non-existent room 'treasury'

--- Compile ---
FAILED: Imported game failed validation: ...

--- Totals ---
2 errors, 0 warnings
```


### 4. Error Message Improvements

These are incremental changes to existing code, not new infrastructure.

#### 4a. Catch `ZorkScriptError` Explicitly in CLI

The import command currently catches `ImportSpecError` twice and then has a bare `except Exception`. `ZorkScriptError` is a `ValueError` subclass and falls through to the generic handler, losing the line number in the formatted output.

Change `import_game` in `cli.py`:

```python
from anyzork.zorkscript import ZorkScriptError

try:
    spec = load_import_source(resolved_source)
except ZorkScriptError as exc:
    diag = from_zorkscript_error(exc)
    _print_diagnostic(diag)
    sys.exit(1)
except ImportSpecError as exc:
    ...
```

This gives parse errors their own formatting path with line numbers prominently displayed.

#### 4b. Diagnostic Printer

A small helper in `diagnostics.py` that uses Rich markup:

```python
def render_diagnostic(diag: Diagnostic, console: Console) -> None:
    color = {"error": "red", "warning": "yellow", "info": "dim"}.get(diag.severity, "white")
    tag = diag.severity.upper()
    loc = f"line {diag.line}: " if diag.line else ""
    console.print(f"[{color}][{tag}][{diag.category}][/{color}] {loc}{diag.message}")
    if diag.hint:
        console.print(f"  [dim]hint: {diag.hint}[/dim]")
```

#### 4c. Hints for Common Errors

Add hints to specific lint checks where the fix is obvious:

- Unknown room ID in exit -> `hint: "Known rooms: cave, forest, village. Did you mean 'forest'?"` (only when there are few rooms and one is close by edit distance)
- Unknown precondition type -> `hint: "Valid precondition types: in_room, has_item, has_flag, ..."`
- Missing `title` in game block -> `hint: "Add 'title \"My Game\"' inside the game { } block"`
- Duplicate ID -> `hint: "Rename one of the duplicates to a unique identifier"`

Hint generation is best-effort. Not every diagnostic needs a hint. Start with the 5 most common errors and expand based on author feedback.

Edit distance suggestions should only fire when the entity set is small (say, < 50 entries) to avoid performance surprises on large specs. Use `difflib.get_close_matches` from the standard library.


### 5. What NOT to Build

**No LSP / language server.** This is a CLI tool. Authors paste ZorkScript from LLM output. A language server for an AI-generated DSL is overhead without an audience.

**No `--fix` flag.** Auto-fixing ZorkScript requires understanding authorial intent. The fixes would be wrong often enough to erode trust. Print hints; let the author (or their LLM) fix it.

**No `--format` json/sarif output.** If someone asks for machine-readable diagnostics, add `--format json` later. Start with human-readable text. YAGNI.

**No incremental / watch mode.** Authors are not editing ZorkScript in a tight loop like application code. They generate it from an LLM, paste it, lint it, fix it, import it. A watch mode solves a problem that doesn't exist.

**No diagnostic codes.** Diagnostic codes (E001, W002) are useful when you have hundreds of rules and need to suppress specific ones. We have ~15 lint checks. Category + message is sufficient.

**No changes to `ValidationError`.** It stays as-is. The conversion to `Diagnostic` happens at the boundary (in `diagnostics.py`). Changing `ValidationError` would require touching every check function in `validation.py` (1600+ lines) for no user-facing benefit.

**No changes to the parser.** The parser already produces good line numbers. Adding column numbers or multi-error recovery would be significant complexity for marginal gain. Parse errors are rare (LLMs produce syntactically valid ZorkScript most of the time). When they do occur, a single error with a line number and the parser's existing message is enough.


## File Plan

```
anyzork/
    diagnostics.py     # NEW: Diagnostic dataclass, converters, render helper
    lint.py            # NEW: lint_spec() function with spec-level checks
    cli.py             # MODIFY: add `lint` command, add `--report` to `import`, catch ZorkScriptError
    validation.py      # NO CHANGES
    zorkscript.py      # NO CHANGES
    importer/
        compile.py     # NO CHANGES
        validate.py    # NO CHANGES
        _constants.py  # NO CHANGES
```

Two new files (~150 lines each), one modified file. No changes to the parser, validation engine, or import pipeline internals.


## Sequencing

1. **`diagnostics.py`** -- Diagnostic type and converters. No dependencies on anything new.
2. **`lint.py`** -- Spec-level checks. Depends on diagnostics.py and reads constants from validation.py and _constants.py.
3. **`cli.py` changes** -- `lint` command, `--report` flag, `ZorkScriptError` catch. Depends on both new modules.
4. **Hint generation** -- Add hints to lint checks iteratively. Can be done after the initial PR ships.

Steps 1-3 can ship in a single PR. Step 4 is a follow-up.
