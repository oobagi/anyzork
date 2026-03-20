from __future__ import annotations

from types import SimpleNamespace

from anyzork.generator.providers.gemini import _extract_response_text


def test_extract_response_text_handles_missing_candidate_content_parts() -> None:
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(content=None),
            SimpleNamespace(content=SimpleNamespace(parts=None)),
        ],
        text="",
    )

    assert _extract_response_text(response) == ""


def test_extract_response_text_returns_first_non_empty_part_text() -> None:
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text=None),
                        SimpleNamespace(text="hello "),
                        SimpleNamespace(text="world"),
                    ]
                )
            )
        ],
        text="ignored fallback",
    )

    assert _extract_response_text(response) == "hello world"


def test_extract_response_text_tolerates_response_text_property_errors() -> None:
    class ExplodingResponse:
        def __init__(self) -> None:
            self.candidates = []

        @property
        def text(self) -> str:
            raise RuntimeError("blocked")

    assert _extract_response_text(ExplodingResponse()) == ""
