"""Tests for `cosplay.store`."""

import pytest

from cosplay.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "cosplay.db")
    yield s
    s.close()


def test_create_run_returns_incrementing_ids(store):
    first = store.create_run(image_path="a.jpg")
    second = store.create_run(image_path="b.jpg")
    assert second == first + 1


def test_get_run_returns_none_for_unknown_id(store):
    assert store.get_run(999) is None


def test_create_run_defaults_status_to_analyzing(store):
    run_id = store.create_run(image_path="a.jpg")
    run = store.get_run(run_id)
    assert run.status == "analyzing"
    assert run.image_path == "a.jpg"
    assert run.features == {}
    assert run.candidates == []


def test_update_run_round_trips_features_and_candidates(store):
    run_id = store.create_run(image_path="a.jpg")
    store.update_run(
        run_id,
        status="generated",
        people_count=1,
        features={"hair": "red", "build": "tall"},
        candidates=[{"name": "Wizard", "reason": "robes suit them"}],
        chosen_index=0,
        chosen_name="Wizard",
        result_image_path="/tmp/result.png",
        gist_url="https://gist.github.com/abc",
    )
    run = store.get_run(run_id)
    assert run.status == "generated"
    assert run.people_count == 1
    assert run.features == {"hair": "red", "build": "tall"}
    assert run.candidates == [{"name": "Wizard", "reason": "robes suit them"}]
    assert run.chosen_index == 0
    assert run.chosen_name == "Wizard"
    assert run.result_image_path == "/tmp/result.png"
    assert run.gist_url == "https://gist.github.com/abc"


def test_update_run_rejects_unknown_field(store):
    run_id = store.create_run(image_path="a.jpg")
    with pytest.raises(ValueError, match="unknown run field"):
        store.update_run(run_id, nonsense="x")


def test_update_run_rejects_empty_fields(store):
    run_id = store.create_run(image_path="a.jpg")
    with pytest.raises(ValueError, match="no fields"):
        store.update_run(run_id)


def test_list_runs_returns_oldest_first(store):
    first = store.create_run(image_path="a.jpg")
    second = store.create_run(image_path="b.jpg")
    runs = store.list_runs()
    assert [r.id for r in runs] == [first, second]


def test_list_runs_empty_store(store):
    assert store.list_runs() == []
