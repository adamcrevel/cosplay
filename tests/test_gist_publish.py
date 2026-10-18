"""Tests for `cosplay.gist_publish`."""

import subprocess

import pytest

import cosplay.gist_publish as gist_publish_module
from cosplay.gist_publish import GistPublishError, publish_gist


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_secret_by_default_omits_public_flag(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _FakeCompletedProcess(0, stdout="https://gist.github.com/abc\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    f = tmp_path / "a.txt"
    f.write_text("x")
    publish_gist([f])
    assert captured["argv"][:3] == ["gh", "gist", "create"]
    assert "--public" not in captured["argv"]


def test_public_true_adds_public_flag(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _FakeCompletedProcess(0, stdout="https://gist.github.com/abc\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    f = tmp_path / "a.txt"
    f.write_text("x")
    publish_gist([f], public=True)
    assert "--public" in captured["argv"]


def test_every_file_path_is_passed_to_gh(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _FakeCompletedProcess(0, stdout="https://gist.github.com/abc\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    f1, f2, f3 = tmp_path / "a.jpg", tmp_path / "b.md", tmp_path / "c.png"
    for f in (f1, f2, f3):
        f.write_text("x")
    publish_gist([f1, f2, f3])
    assert str(f1) in captured["argv"]
    assert str(f2) in captured["argv"]
    assert str(f3) in captured["argv"]


def test_empty_file_list_raises():
    with pytest.raises(GistPublishError, match="no files"):
        publish_gist([])


def test_nonzero_exit_raises_gist_publish_error_with_stderr(monkeypatch, tmp_path):
    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess(1, stderr="not authenticated")

    monkeypatch.setattr(subprocess, "run", fake_run)
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(GistPublishError, match="not authenticated"):
        publish_gist([f])


def test_gh_not_found_raises_gist_publish_error_naming_the_problem(monkeypatch, tmp_path):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(GistPublishError, match="not installed"):
        publish_gist([f])


def test_timeout_raises_gist_publish_error(monkeypatch, tmp_path):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=60)

    monkeypatch.setattr(subprocess, "run", fake_run)
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(GistPublishError, match="timed out"):
        publish_gist([f])


def test_url_is_stripped_of_trailing_whitespace(monkeypatch, tmp_path):
    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess(0, stdout="https://gist.github.com/z\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert publish_gist([f]) == "https://gist.github.com/z"


def test_only_this_module_is_allowed_to_import_subprocess():
    """Sanity check for the layering-boundary standing check (see test_layering.py),
    which greps the whole package for `import subprocess`/`requests` usage."""
    assert hasattr(gist_publish_module, "subprocess")
