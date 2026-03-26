"""Contract tests for general-purpose variables: set_var, change_var, var_check.

Covers:
- ZorkScript parsing of set_var and change_var effects
- ZorkScript parsing of var_check precondition (with comparison operators)
- DB methods: get_var, set_var, change_var
- Engine effect handlers for set_var and change_var
- Engine precondition evaluation for var_check (all six operators)
- Full round-trip: ZorkScript -> compile -> engine execution
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from anyzork.db.schema import GameDB
from anyzork.engine.commands import apply_effect, check_precondition
from anyzork.engine.game import GameEngine
from anyzork.importer import compile_import_spec
from anyzork.zorkscript import parse_zorkscript


def _variable_zorkscript() -> str:
    return """\
game {
  title "Variable Test"
  author "Test"
  max_score 0
  win [game_won]
}

player {
  start tavern
}

room tavern {
  name "Tavern"
  description "A cozy tavern."
  short "A cozy tavern."
  start true
}

npc jaheira {
  name "Jaheira"
  description "A stern half-elf druid."
  examine "She regards you coolly."
  in tavern
  dialogue "Hmph."
  category "character"
}

flag game_won "Victory"

# Approval command: increases approval when player compliments
on "compliment jaheira" {
  effect change_var(jaheira_approval, 10)
  effect print("Jaheira nods approvingly.")
  success "You compliment Jaheira."
}

# Set a specific variable value
on "reset approval" {
  effect set_var(jaheira_approval, 0)
  success "Approval reset."
}

# Gated dialogue: requires high approval
on "ask jaheira for help" {
  require var_check(jaheira_approval, >=, 50)
  effect set_flag(game_won)
  success "Jaheira agrees to help you."
  fail "Jaheira is not interested in helping you."
}

# Trigger: when approval reaches threshold
when flag_set(game_won) {
  effect change_var(jaheira_approval, 5)
  message "Jaheira smiles warmly."
  once
}
"""


# ---- Parse tests ----


def test_parse_set_var_effect() -> None:
    """set_var effect is compiled correctly from ZorkScript."""
    spec = parse_zorkscript(_variable_zorkscript())
    commands = spec["commands"]
    reset_cmd = next(c for c in commands if c["pattern"] == "reset approval")
    effects = reset_cmd["effects"]
    sv_effect = next(e for e in effects if e["type"] == "set_var")
    assert sv_effect["name"] == "jaheira_approval"
    assert sv_effect["value"] == 0


def test_parse_change_var_effect() -> None:
    """change_var effect is compiled correctly from ZorkScript."""
    spec = parse_zorkscript(_variable_zorkscript())
    commands = spec["commands"]
    compliment_cmd = next(c for c in commands if c["pattern"] == "compliment jaheira")
    effects = compliment_cmd["effects"]
    cv_effect = next(e for e in effects if e["type"] == "change_var")
    assert cv_effect["name"] == "jaheira_approval"
    assert cv_effect["delta"] == 10


def test_parse_var_check_precondition() -> None:
    """var_check precondition is compiled correctly from ZorkScript."""
    spec = parse_zorkscript(_variable_zorkscript())
    commands = spec["commands"]
    ask_cmd = next(c for c in commands if c["pattern"] == "ask jaheira for help")
    preconditions = ask_cmd["preconditions"]
    assert len(preconditions) == 1
    vc = preconditions[0]
    assert vc["type"] == "var_check"
    assert vc["name"] == "jaheira_approval"
    assert vc["operator"] == ">="
    assert vc["value"] == 50


def test_parse_var_check_all_operators() -> None:
    """var_check supports all six comparison operators."""
    operators = ["==", "!=", ">", "<", ">=", "<="]
    for op in operators:
        src = f"""\
game {{
  title "Op Test"
  author "Test"
  max_score 0
  win [done]
}}

player {{ start room1 }}

room room1 {{
  name "Room"
  description "A room."
  short "A room."
  start true
}}

flag done "Done"

on "test" {{
  require var_check(score, {op}, 10)
  effect set_flag(done)
  success "OK"
}}
"""
        spec = parse_zorkscript(src)
        commands = spec["commands"]
        assert len(commands) == 1
        vc = commands[0]["preconditions"][0]
        assert vc["operator"] == op, f"Failed for operator {op}"


# ---- DB method tests ----


def test_get_var_default(tmp_path: Path) -> None:
    """get_var returns 0 for a variable that does not exist."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_default.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        assert db.get_var("nonexistent") == 0


def test_set_var_creates_and_updates(tmp_path: Path) -> None:
    """set_var creates a new variable and updates an existing one."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_set.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.set_var("test_var", 42)
        assert db.get_var("test_var") == 42

        db.set_var("test_var", 100)
        assert db.get_var("test_var") == 100


def test_change_var_creates_and_increments(tmp_path: Path) -> None:
    """change_var creates a new variable at delta and increments existing ones."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_change.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        # First change creates the variable with the delta value.
        db.change_var("counter", 5)
        assert db.get_var("counter") == 5

        # Second change increments.
        db.change_var("counter", 3)
        assert db.get_var("counter") == 8

        # Negative delta decrements.
        db.change_var("counter", -2)
        assert db.get_var("counter") == 6


# ---- Engine precondition tests ----


def _vc(op: str, val: int) -> dict:
    """Build a var_check precondition dict for 'level'."""
    return {
        "type": "var_check",
        "name": "level",
        "operator": op,
        "value": val,
    }


def test_var_check_all_operators(tmp_path: Path) -> None:
    """var_check precondition evaluates all six operators correctly."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_precond.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("tavern")
        db.set_var("level", 5)

        # ==
        assert check_precondition(_vc("==", 5), db) is True
        assert check_precondition(_vc("==", 3), db) is False

        # !=
        assert check_precondition(_vc("!=", 3), db) is True
        assert check_precondition(_vc("!=", 5), db) is False

        # >
        assert check_precondition(_vc(">", 3), db) is True
        assert check_precondition(_vc(">", 5), db) is False

        # <
        assert check_precondition(_vc("<", 10), db) is True
        assert check_precondition(_vc("<", 5), db) is False

        # >=
        assert check_precondition(_vc(">=", 5), db) is True
        assert check_precondition(_vc(">=", 6), db) is False

        # <=
        assert check_precondition(_vc("<=", 5), db) is True
        assert check_precondition(_vc("<=", 4), db) is False


def test_var_check_missing_variable(tmp_path: Path) -> None:
    """var_check treats missing variables as 0."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_missing.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("tavern")

        assert check_precondition(
            {"type": "var_check", "name": "nonexistent", "operator": "==", "value": 0}, db
        ) is True
        assert check_precondition(
            {"type": "var_check", "name": "nonexistent", "operator": ">", "value": 0}, db
        ) is False


# ---- Engine effect tests ----


def test_set_var_effect(tmp_path: Path) -> None:
    """set_var effect sets a variable via the engine."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_eff_set.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("tavern")
        apply_effect({"type": "set_var", "name": "score", "value": 42}, db)
        assert db.get_var("score") == 42


def test_change_var_effect(tmp_path: Path) -> None:
    """change_var effect increments a variable via the engine."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_eff_change.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    with GameDB(compiled_path) as db:
        db.init_player("tavern")

        apply_effect({"type": "change_var", "name": "approval", "delta": 10}, db)
        assert db.get_var("approval") == 10

        apply_effect({"type": "change_var", "name": "approval", "delta": -3}, db)
        assert db.get_var("approval") == 7


# ---- Full integration test ----


def _make_engine(zork_path: Path) -> tuple[GameEngine, Console]:
    """Create a non-interactive GameEngine for testing."""
    console = Console(file=StringIO(), force_terminal=True, width=120)
    db = GameDB(zork_path)
    engine = GameEngine(db, console=console, interactive_dialogue=False)
    engine.initialize_session()
    return engine, console


def _get_output(console: Console) -> str:
    """Extract text output from a Console with a StringIO file."""
    return console.file.getvalue()  # type: ignore[union-attr]


def test_variable_gated_command(tmp_path: Path) -> None:
    """Full round-trip: change_var accumulates, var_check gates a command."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_integration.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, console = _make_engine(compiled_path)

    # Approval starts at 0, so asking for help should fail.
    engine.process_command("ask jaheira for help")
    output = _get_output(console)
    assert "not interested" in output

    # Compliment 5 times to reach 50.
    for _ in range(5):
        engine.process_command("compliment jaheira")

    assert engine.db.get_var("jaheira_approval") == 50

    # Now asking for help should succeed.
    engine.process_command("ask jaheira for help")
    output = _get_output(console)
    assert "agrees to help" in output


def test_set_var_resets_value(tmp_path: Path) -> None:
    """set_var resets a previously accumulated variable."""
    spec = parse_zorkscript(_variable_zorkscript())
    output_path = tmp_path / "var_reset.zork"
    compiled_path, _ = compile_import_spec(spec, output_path)

    engine, _console = _make_engine(compiled_path)

    # Build up some approval.
    for _ in range(3):
        engine.process_command("compliment jaheira")
    assert engine.db.get_var("jaheira_approval") == 30

    # Reset it.
    engine.process_command("reset approval")
    assert engine.db.get_var("jaheira_approval") == 0
