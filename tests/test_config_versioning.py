from __future__ import annotations

import anyzork.config as config_module
from anyzork.cli import CLI_VERSION
from anyzork.config import DEFAULT_CATALOG_URL, DEFAULT_UPLOAD_URL, Config, LLMProvider
from anyzork.versioning import RUNTIME_COMPAT_VERSION, is_runtime_compat_version


def test_cli_version_string_includes_runtime_and_prompt_versions() -> None:
    assert str(RUNTIME_COMPAT_VERSION) in CLI_VERSION
    assert "prompt" in CLI_VERSION


def test_runtime_compat_version_recognizes_expected_shape() -> None:
    assert is_runtime_compat_version("r1")
    assert is_runtime_compat_version("r2.3")
    assert not is_runtime_compat_version("0.1.0")


def test_config_uses_provider_env_for_narrator_api_key(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_config_file", lambda: {})
    monkeypatch.setenv("ANYZORK_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "from_provider")

    cfg = Config()

    assert cfg.provider == LLMProvider.OPENAI
    assert cfg.get_api_key() == "from_provider"


def test_config_uses_config_file_key_when_provider_env_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        config_module,
        "load_config_file",
        lambda: {
            "provider": "gemini",
            "google_api_key": "from_config_file",
        },
    )
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    cfg = Config()

    assert cfg.provider == LLMProvider.GEMINI
    assert cfg.get_api_key() == "from_config_file"


def test_config_defaults_for_new_fields(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_config_file", lambda: {})

    cfg = Config()

    assert cfg.narrator_enabled is False
    assert cfg.narrator_temperature == 0.9
    assert cfg.narrator_max_tokens == 4096
    assert cfg.catalog_url == DEFAULT_CATALOG_URL
    assert cfg.upload_url == DEFAULT_UPLOAD_URL


def test_config_reads_narrator_settings_from_toml(monkeypatch) -> None:
    monkeypatch.setattr(
        config_module,
        "load_config_file",
        lambda: {
            "narrator_enabled": True,
            "narrator_temperature": 0.7,
            "narrator_max_tokens": 2048,
        },
    )

    cfg = Config()

    assert cfg.narrator_enabled is True
    assert cfg.narrator_temperature == 0.7
    assert cfg.narrator_max_tokens == 2048


def test_config_reads_urls_from_toml(monkeypatch) -> None:
    monkeypatch.setattr(
        config_module,
        "load_config_file",
        lambda: {
            "catalog_url": "https://custom.example.com/catalog.json",
            "upload_url": "https://custom.example.com/api/games",
        },
    )

    cfg = Config()

    assert cfg.catalog_url == "https://custom.example.com/catalog.json"
    assert cfg.upload_url == "https://custom.example.com/api/games"


def test_config_reads_paths_from_toml(monkeypatch, tmp_path) -> None:
    custom_games = tmp_path / "custom_games"
    custom_saves = tmp_path / "custom_saves"
    custom_catalog = tmp_path / "custom_catalog"

    monkeypatch.setattr(
        config_module,
        "load_config_file",
        lambda: {
            "games_dir": str(custom_games),
            "saves_dir": str(custom_saves),
            "public_catalog_dir": str(custom_catalog),
        },
    )

    cfg = Config()

    assert cfg.games_dir == custom_games
    assert cfg.saves_dir == custom_saves
    assert cfg.public_catalog_dir == custom_catalog


def test_config_env_overrides_toml(monkeypatch) -> None:
    monkeypatch.setattr(
        config_module,
        "load_config_file",
        lambda: {
            "catalog_url": "https://toml.example.com/catalog.json",
            "narrator_temperature": 0.5,
        },
    )
    monkeypatch.setenv("ANYZORK_CATALOG_URL", "https://env.example.com/catalog.json")
    monkeypatch.setenv("ANYZORK_NARRATOR_TEMPERATURE", "0.3")

    cfg = Config()

    assert cfg.catalog_url == "https://env.example.com/catalog.json"
    assert cfg.narrator_temperature == 0.3


def test_load_config_file_reads_all_anyzork_keys(monkeypatch, tmp_path) -> None:
    toml_content = """\
[anyzork]
provider = "openai"
model = "gpt-4"
narrator_enabled = true
narrator_temperature = 0.5
narrator_max_tokens = 1024
games_dir = "/tmp/games"
saves_dir = "/tmp/saves"
public_catalog_dir = "/tmp/catalog"
catalog_url = "https://custom.example.com/catalog.json"
upload_url = "https://custom.example.com/api/games"

[keys]
openai = "sk-test"
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(toml_content)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    from anyzork.config import load_config_file

    result = load_config_file()

    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4"
    assert result["narrator_enabled"] is True
    assert result["narrator_temperature"] == 0.5
    assert result["narrator_max_tokens"] == 1024
    assert result["games_dir"] == "/tmp/games"
    assert result["saves_dir"] == "/tmp/saves"
    assert result["public_catalog_dir"] == "/tmp/catalog"
    assert result["catalog_url"] == "https://custom.example.com/catalog.json"
    assert result["upload_url"] == "https://custom.example.com/api/games"
    assert result["openai_api_key"] == "sk-test"
