from __future__ import annotations

from anyzork.generator.orchestrator import _build_context


def test_build_context_merges_flags_from_multiple_passes() -> None:
    context = _build_context(
        "triggers",
        {
            "commands": {
                "commands": [{"id": "cmd_a"}],
                "flags": [{"id": "flag_from_commands", "description": "cmd flag"}],
            },
            "quests": {
                "quests": [{"id": "quest_a"}],
                "flags": [{"id": "flag_from_quests", "description": "quest flag"}],
            },
        },
    )

    assert context["commands"] == [{"id": "cmd_a"}]
    assert context["quests"] == [{"id": "quest_a"}]
    assert context["flags"] == [
        {"id": "flag_from_commands", "description": "cmd flag"},
        {"id": "flag_from_quests", "description": "quest flag"},
    ]
