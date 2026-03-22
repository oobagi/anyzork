"""Tests for the narrator CLI command and config writer."""

from __future__ import annotations

import textwrap

import anyzork.config as config_module
from anyzork.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    LLMProvider,
    _format_toml,
    load_config_file,
    save_config_file,
)


# ------------------------------------------------------------------
# _format_toml
# ------------------------------------------------------------------


def test_format_toml_anyzork_section() -> None:
    data = {"anyzork": {"provider": "claude", "narrator_enabled": True}}
    result = _format_toml(data)
    assert '[anyzork]' in result
    assert 'provider = "claude"' in result
    assert "narrator_enabled = true" in result


def test_format_toml_keys_section() -> None:
    data = {"keys": {"anthropic": "sk-ant-test"}}
    result = _format_toml(data)
    assert "[keys]" in result
    assert 'anthropic = "sk-ant-test"' in result


def test_format_toml_both_sections() -> None:
    data = {
        "anyzork": {"provider": "openai"},
        "keys": {"openai": "sk-test"},
    }
    result = _format_toml(data)
    assert "[anyzork]" in result
    assert "[keys]" in result


def test_format_toml_empty() -> None:
    assert _format_toml({}) == ""


# ------------------------------------------------------------------
# save_config_file
# ------------------------------------------------------------------


def test_save_config_file_creates_new(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / ".anyzork"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    save_config_file(provider="claude", narrator_enabled=True)

    assert config_file.exists()
    content = config_file.read_text()
    assert 'provider = "claude"' in content
    assert "narrator_enabled = true" in content


def test_save_config_file_preserves_existing(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / ".anyzork"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text(
        '[anyzork]\nprovider = "claude"\n\n[keys]\nanthropic = "existing-key"\n'
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    save_config_file(narrator_enabled=True)

    content = config_file.read_text()
    assert 'provider = "claude"' in content
    assert 'anthropic = "existing-key"' in content
    assert "narrator_enabled = true" in content


def test_save_config_file_writes_api_key(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / ".anyzork"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    save_config_file(api_key=("anthropic", "sk-ant-new-key"))

    content = config_file.read_text()
    assert 'anthropic = "sk-ant-new-key"' in content


def test_save_config_file_updates_provider(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / ".anyzork"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text('[anyzork]\nprovider = "claude"\n')
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    save_config_file(provider="openai")

    content = config_file.read_text()
    assert 'provider = "openai"' in content
    assert "claude" not in content


# ------------------------------------------------------------------
# narrator CLI command — smoke tests via Click runner
# ------------------------------------------------------------------


def test_narrator_shows_status_when_configured(monkeypatch) -> None:
    from click.testing import CliRunner

    from anyzork.cli import cli

    monkeypatch.setattr(
        config_module,
        "load_config_file",
        lambda: {"provider": "claude", "anthropic_api_key": "sk-ant-test1234567890"},
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test1234567890")

    runner = CliRunner()
    result = runner.invoke(cli, ["narrator"], input="q\n")

    assert result.exit_code == 0
    assert "Narrator Settings" in result.output
    assert "claude" in result.output


def test_narrator_launches_wizard_when_no_key(monkeypatch) -> None:
    from click.testing import CliRunner

    from anyzork.cli import cli

    monkeypatch.setattr(config_module, "load_config_file", lambda: {})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(cli, ["narrator"], input="q\n")

    assert result.exit_code == 0
    assert "Narrator Setup" in result.output
