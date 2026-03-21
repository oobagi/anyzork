from __future__ import annotations

import anyzork.config as config_module
from anyzork.cli import CLI_VERSION
from anyzork.config import Config, LLMProvider
from anyzork.versioning import RUNTIME_COMPAT_VERSION, is_runtime_compat_version


def test_cli_version_string_includes_runtime_and_prompt_versions() -> None:
    assert str(RUNTIME_COMPAT_VERSION) in CLI_VERSION
    assert "prompt" in CLI_VERSION


def test_runtime_compat_version_recognizes_expected_shape() -> None:
    assert is_runtime_compat_version("r1")
    assert is_runtime_compat_version("r2.3")
    assert not is_runtime_compat_version("0.1.0")


def test_config_prefers_anyzork_api_key_over_provider_env(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_config_file", lambda: {})
    monkeypatch.setenv("ANYZORK_PROVIDER", "openai")
    monkeypatch.setenv("ANYZORK_OPENAI_API_KEY", "from_anyzork")
    monkeypatch.setenv("OPENAI_API_KEY", "from_provider")

    cfg = Config()

    assert cfg.provider == LLMProvider.OPENAI
    assert cfg.get_api_key() == "from_anyzork"


def test_config_uses_provider_env_when_prefixed_key_missing(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "load_config_file", lambda: {})
    monkeypatch.setenv("ANYZORK_PROVIDER", "gemini")
    monkeypatch.delenv("ANYZORK_GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "from_provider")

    cfg = Config()

    assert cfg.provider == LLMProvider.GEMINI
    assert cfg.get_api_key() == "from_provider"
