"""Tests for `cosplay.render`."""

from cosplay.render import render_markdown
from cosplay.vision import AnalysisResult, Candidate


def _result():
    return AnalysisResult(
        people_count=1,
        face_visible=True,
        features={"hair": "red", "build": "tall"},
        candidates=[
            Candidate(name="Pirate", reason="bold vibe"),
            Candidate(name="Wizard", reason="red hair suits robes"),
        ],
        chosen_index=1,
        chosen_reason="robes match best",
        image_prompt_hints="blue robes, staff",
    )


def test_render_markdown_marks_the_chosen_candidate():
    md = render_markdown(_result(), original_filename="original.jpg", result_filename="result.png")
    assert "🏆 **Wizard**" in md
    assert "**Pirate**" in md and "🏆 **Pirate**" not in md


def test_render_markdown_names_both_files():
    md = render_markdown(_result(), original_filename="original.jpg", result_filename="result.png")
    assert "original.jpg" in md
    assert "result.png" in md


def test_render_markdown_includes_features_and_chosen_reason():
    md = render_markdown(_result(), original_filename="o.jpg", result_filename="r.png")
    assert "red" in md
    assert "robes match best" in md


def test_render_markdown_raises_without_chosen_candidate():
    import pytest

    bad = AnalysisResult(
        people_count=0,
        face_visible=False,
        features={},
        candidates=[],
        chosen_index=-1,
        chosen_reason="",
        image_prompt_hints="",
    )
    with pytest.raises(ValueError):
        render_markdown(bad, original_filename="o.jpg", result_filename="r.png")
