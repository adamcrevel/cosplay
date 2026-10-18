"""Tests for `cosplay.cli`.

`vision.analyze`, `providers.pollinations.PollinationsProvider`, and
`gist_publish.publish_gist` are always patched on `cosplay.cli`'s own
namespace so no real `omp`/Pollinations.ai/`gh` call ever happens -- those
are covered by their own modules' tests. These only prove the CLI wires
arguments, exit codes, and store updates correctly. Photo/result fixtures
are real (tiny) PIL-encoded images, not magic-byte placeholders, since
`cli.py` runs every saved/published image through
`image_utils.fit_for_display`, which actually decodes them.
"""

import io

from PIL import Image

import cosplay.cli as cli_module
from cosplay.cli import main
from cosplay.providers.base import ImageProviderError
from cosplay.store import Store
from cosplay.vision import AnalysisResult, Candidate


def _real_image_bytes(fmt: str, size=(10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "blue").save(buf, format=fmt)
    return buf.getvalue()


def _analysis_result(people_count=1, chosen_index=0):
    if people_count != 1:
        return AnalysisResult(
            people_count=people_count,
            face_visible=False,
            features={},
            candidates=[],
            chosen_index=-1,
            chosen_reason="",
            image_prompt_hints="",
        )
    return AnalysisResult(
        people_count=1,
        face_visible=True,
        features={"hair": "red", "build": "tall"},
        candidates=[Candidate(name="Pirate", reason="bold")],
        chosen_index=chosen_index,
        chosen_reason="best fit",
        image_prompt_hints="tricorn hat",
    )


class _FakeProvider:
    def __init__(self, *, model, **kwargs):
        self.model = model

    def edit_image(self, *, image_bytes, image_filename, prompt):
        return _real_image_bytes("PNG")


class _FailingProvider:
    def __init__(self, *, model, **kwargs):
        pass

    def edit_image(self, *, image_bytes, image_filename, prompt):
        raise ImageProviderError("no key set")


def _photo(tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(_real_image_bytes("JPEG"))
    return photo


def _base_argv(photo, tmp_path, extra=()):
    return [
        "run",
        str(photo),
        "--state-dir",
        str(tmp_path / "state"),
        "--db-path",
        str(tmp_path / "cosplay.db"),
        *extra,
    ]


def test_run_missing_image_exits_2(tmp_path, capsys):
    code = main(["run", str(tmp_path / "nope.jpg"), "--db-path", str(tmp_path / "c.db")])
    assert code == 2
    assert "not found" in capsys.readouterr().err.lower()


def test_run_zero_people_rejects_with_exit_0(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "analyze", lambda *a, **k: _analysis_result(people_count=0))
    photo = _photo(tmp_path)
    code = main(_base_argv(photo, tmp_path, extra=["--no-publish"]))
    assert code == 0
    assert "Rejected" in capsys.readouterr().err

    store = Store(tmp_path / "cosplay.db")
    run = store.get_run(1)
    assert run.status == "rejected_no_person"


def test_run_multiple_people_rejects_with_exit_0(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "analyze", lambda *a, **k: _analysis_result(people_count=4))
    photo = _photo(tmp_path)
    code = main(_base_argv(photo, tmp_path, extra=["--no-publish"]))
    assert code == 0
    err = capsys.readouterr().err
    assert "Rejected" in err and "4 people" in err

    store = Store(tmp_path / "cosplay.db")
    assert store.get_run(1).status == "rejected_multiple_people"


def test_run_provider_failure_exits_1_and_marks_failed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "analyze", lambda *a, **k: _analysis_result(people_count=1))
    monkeypatch.setattr(cli_module, "PollinationsProvider", _FailingProvider)
    photo = _photo(tmp_path)
    code = main(_base_argv(photo, tmp_path, extra=["--no-publish"]))
    assert code == 1
    assert "no key set" in capsys.readouterr().err

    store = Store(tmp_path / "cosplay.db")
    assert store.get_run(1).status == "failed"


def test_run_success_no_publish_writes_local_files(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "analyze", lambda *a, **k: _analysis_result(people_count=1))
    monkeypatch.setattr(cli_module, "PollinationsProvider", _FakeProvider)
    photo = _photo(tmp_path)
    code = main(_base_argv(photo, tmp_path, extra=["--no-publish"]))
    assert code == 0
    out = capsys.readouterr().out
    assert "Not published" in out

    run_dir = tmp_path / "state" / "runs" / "1"
    assert (run_dir / "original.jpg").exists()
    assert (run_dir / "result.png").exists()
    assert (run_dir / "analysis.md").exists()
    assert "Pirate" in (run_dir / "analysis.md").read_text()

    store = Store(tmp_path / "cosplay.db")
    assert store.get_run(1).status == "generated"


def test_run_success_publishes_and_records_gist_url(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "analyze", lambda *a, **k: _analysis_result(people_count=1))
    monkeypatch.setattr(cli_module, "PollinationsProvider", _FakeProvider)
    captured_files = {}

    def fake_publish(files, *, public=False):
        captured_files["files"] = files
        captured_files["public"] = public
        return "https://gist.github.com/abc123"

    monkeypatch.setattr(cli_module, "publish_gist", fake_publish)
    photo = _photo(tmp_path)
    code = main(_base_argv(photo, tmp_path))
    assert code == 0
    assert "Published: https://gist.github.com/abc123" in capsys.readouterr().out
    assert len(captured_files["files"]) == 3
    assert captured_files["public"] is False

    store = Store(tmp_path / "cosplay.db")
    run = store.get_run(1)
    assert run.status == "published"
    assert run.gist_url == "https://gist.github.com/abc123"


def test_run_public_flag_passed_through_to_publish(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_module, "analyze", lambda *a, **k: _analysis_result(people_count=1))
    monkeypatch.setattr(cli_module, "PollinationsProvider", _FakeProvider)
    captured = {}

    def fake_publish(files, *, public=False):
        captured["public"] = public
        return "https://gist.github.com/x"

    monkeypatch.setattr(cli_module, "publish_gist", fake_publish)
    photo = _photo(tmp_path)
    main(_base_argv(photo, tmp_path, extra=["--public"]))
    assert captured["public"] is True


def test_list_and_show_report_past_runs(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli_module, "analyze", lambda *a, **k: _analysis_result(people_count=0))
    photo = _photo(tmp_path)
    main(_base_argv(photo, tmp_path, extra=["--no-publish"]))
    capsys.readouterr()

    db_path = str(tmp_path / "cosplay.db")
    code = main(["list", "--db-path", db_path])
    assert code == 0
    assert "rejected_no_person" in capsys.readouterr().out

    code = main(["show", "1", "--db-path", db_path])
    assert code == 0
    assert "rejected_no_person" in capsys.readouterr().out


def test_show_unknown_run_id_exits_1(tmp_path, capsys):
    code = main(["show", "999", "--db-path", str(tmp_path / "c.db")])
    assert code == 1
    assert "no run with id 999" in capsys.readouterr().err
