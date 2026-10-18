"""Tests for `cosplay.vision`'s JSON parsing/validation (the schema contract)."""

import json

import pytest

from cosplay.vision import AnalysisParseError, _parse, _strip_fence


def _single_person_payload(candidate_count: int = 2) -> dict:
    return {
        "people_count": 1,
        "face_visible": True,
        "features": {"hair": "red", "build": "tall", "vibe": "bold"},
        "candidates": [
            {"name": "Pirate", "reason": "bold vibe suits it"},
            {"name": "Wizard", "reason": "red hair suits robes"},
        ][:candidate_count],
        "chosen_index": 0,
        "chosen_reason": "most distinctive match",
        "image_prompt_hints": "tricorn hat, red coat, ship deck",
    }


def test_parse_single_person_round_trips_every_field():
    result = _parse(json.dumps(_single_person_payload()), candidate_count=2)
    assert result.people_count == 1
    assert result.face_visible is True
    assert result.features == {"hair": "red", "build": "tall", "vibe": "bold"}
    assert [c.name for c in result.candidates] == ["Pirate", "Wizard"]
    assert result.chosen_index == 0
    assert result.chosen.name == "Pirate"
    assert result.chosen_reason == "most distinctive match"
    assert result.image_prompt_hints == "tricorn hat, red coat, ship deck"


def test_parse_strips_markdown_code_fence():
    raw = "```json\n" + json.dumps(_single_person_payload()) + "\n```"
    result = _parse(raw, candidate_count=2)
    assert result.people_count == 1


def test_parse_zero_people_ignores_other_fields():
    result = _parse(json.dumps({"people_count": 0}), candidate_count=4)
    assert result.people_count == 0
    assert result.features == {}
    assert result.candidates == []
    assert result.chosen_index == -1
    with pytest.raises(ValueError, match="no chosen candidate"):
        _ = result.chosen


def test_parse_multiple_people_ignores_other_fields():
    result = _parse(json.dumps({"people_count": 3}), candidate_count=4)
    assert result.people_count == 3
    assert result.candidates == []


def test_parse_invalid_json_raises():
    with pytest.raises(AnalysisParseError, match="not valid JSON"):
        _parse("not json at all", candidate_count=4)


def test_parse_missing_people_count_raises():
    with pytest.raises(AnalysisParseError, match="people_count"):
        _parse(json.dumps({"features": {}}), candidate_count=4)


def test_parse_wrong_candidate_count_raises():
    with pytest.raises(AnalysisParseError, match="expected 4 candidates"):
        _parse(json.dumps(_single_person_payload(candidate_count=2)), candidate_count=4)


def test_parse_out_of_range_chosen_index_raises():
    payload = _single_person_payload()
    payload["chosen_index"] = 5
    with pytest.raises(AnalysisParseError, match="out of range"):
        _parse(json.dumps(payload), candidate_count=2)


def test_parse_single_person_missing_candidates_raises():
    payload = {"people_count": 1, "features": {}}
    with pytest.raises(AnalysisParseError, match="missing a required field"):
        _parse(json.dumps(payload), candidate_count=2)


def test_strip_fence_handles_plain_json():
    assert _strip_fence('{"a": 1}') == '{"a": 1}'


def test_strip_fence_strips_fence_with_language_tag():
    assert _strip_fence('```json\n{"a": 1}\n```') == '{"a": 1}'
