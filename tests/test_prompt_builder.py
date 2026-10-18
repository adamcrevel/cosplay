"""Tests for `cosplay.prompt_builder`."""

import pytest

from cosplay.prompt_builder import build_image_prompt
from cosplay.vision import AnalysisResult, Candidate


def _result(people_count=1, chosen_index=0):
    return AnalysisResult(
        people_count=people_count,
        face_visible=True,
        features={"hair": "red"},
        candidates=[Candidate(name="Pirate", reason="bold")],
        chosen_index=chosen_index,
        chosen_reason="best fit",
        image_prompt_hints="tricorn hat, red coat",
    )


def test_build_image_prompt_names_the_chosen_candidate():
    prompt = build_image_prompt(_result())
    assert "Pirate" in prompt


def test_build_image_prompt_includes_hints():
    prompt = build_image_prompt(_result())
    assert "tricorn hat, red coat" in prompt


def test_build_image_prompt_requests_full_body_and_identity_preservation():
    prompt = build_image_prompt(_result())
    assert "full-body" in prompt.lower()
    assert "identity" in prompt.lower() or "recognizable" in prompt.lower()


def test_build_image_prompt_raises_when_no_chosen_candidate():
    with pytest.raises(ValueError, match="no chosen candidate"):
        build_image_prompt(_result(people_count=0, chosen_index=-1))
