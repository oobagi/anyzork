from __future__ import annotations

from click.testing import CliRunner

from anyzork import cli as cli_module
from anyzork.wizard.assembler import assemble_prompt


def test_assemble_prompt_omits_realism_setting() -> None:
    prompt = assemble_prompt(
        {
            "world_description": "A foggy harbor town with a missing lighthouse keeper.",
            "realism": "high",
            "scale": "medium",
        }
    )

    assert "foggy harbor town" in prompt
    assert "World size:" in prompt
    assert "Realism:" not in prompt
    assert "high" not in prompt


def test_resolve_generation_inputs_uses_preset_realism_on_no_edit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "anyzork.wizard.presets.load_preset",
        lambda _name: {
            "world_description": "A cliffside monastery under siege by ghosts.",
            "realism": "low",
        },
    )

    resolved = cli_module._resolve_generation_inputs(
        prompt=None,
        guided=False,
        preset_name="ghost-monastery",
        no_edit=True,
        console=cli_module.console,
    )

    assert resolved == (
        "A cliffside monastery under siege by ghosts.",
        "low",
        {
            "world_description": "A cliffside monastery under siege by ghosts.",
            "realism": "low",
        },
    )


def test_generate_uses_wizard_selected_realism(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        cli_module,
        "_resolve_generation_inputs",
        lambda *args, **kwargs: (
            "A moonlit museum heist.",
            "high",
            {
                "world_description": "A moonlit museum heist.",
                "scale": "medium",
                "locations": ["Grand gallery", "Archive vault"],
                "items": ["Glass cutter", "Forgery ledger"],
            },
        ),
    )

    monkeypatch.setattr(
        "anyzork.importer.build_zorkscript_prompt",
        lambda prompt, *, realism=None, authoring_fields=None: (
            f"PROMPT::{prompt}::REALISM::{realism}::FIELDS::{authoring_fields}"
        ),
    )

    result = runner.invoke(cli_module.cli, ["generate"])

    assert result.exit_code == 0
    assert "PROMPT::A moonlit museum heist.::REALISM::high" in result.output
    assert "Grand gallery" in result.output
