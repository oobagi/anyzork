from __future__ import annotations

from pathlib import Path

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
    )


def test_generate_uses_wizard_selected_realism(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli_module,
        "_resolve_generation_inputs",
        lambda *args, **kwargs: ("A moonlit museum heist.", "high"),
    )

    class FakeConfig:
        def __init__(self, **kwargs) -> None:
            self.provider = cli_module.LLMProvider.CLAUDE
            self.seed = kwargs.get("seed")
            self.active_model = "fake-model"
            self.games_dir = tmp_path

        def get_api_key(self) -> str:
            return "test-key"

    def fake_generate_game(prompt, config, output_path, *, realism):
        captured["prompt"] = prompt
        captured["realism"] = realism
        captured["output_path"] = output_path
        return output_path

    monkeypatch.setattr(cli_module, "Config", FakeConfig)
    monkeypatch.setattr(
        "anyzork.generator.orchestrator.generate_game",
        fake_generate_game,
    )

    result = runner.invoke(cli_module.cli, ["generate"])

    assert result.exit_code == 0
    assert captured["prompt"] == "A moonlit museum heist."
    assert captured["realism"] == "high"
    assert captured["output_path"] == tmp_path / "a_moonlit_museum_heist.zork"
