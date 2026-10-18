"""Tests for `cosplay.gist_publish`."""

import subprocess
from pathlib import Path

import pytest

import cosplay.gist_publish as gist_publish_module
from cosplay.gist_publish import GistPublishError, _is_text, publish_gist

_JPEG_MAGIC = b"\xff\xd8\xff\xe0\x00\x10JFIF fake jpeg bytes"


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_is_text_true_for_utf8_content(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# hello")
    assert _is_text(f) is True


def test_is_text_false_for_jpeg_magic_bytes(tmp_path):
    f = tmp_path / "a.jpg"
    f.write_bytes(_JPEG_MAGIC)
    assert _is_text(f) is False


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


def test_text_file_paths_are_passed_to_gh(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _FakeCompletedProcess(0, stdout="https://gist.github.com/abc\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    f1, f2 = tmp_path / "a.md", tmp_path / "b.txt"
    for f in (f1, f2):
        f.write_text("x")
    publish_gist([f1, f2])
    assert str(f1) in captured["argv"]
    assert str(f2) in captured["argv"]


def test_empty_file_list_raises():
    with pytest.raises(GistPublishError, match="no files"):
        publish_gist([])


def test_all_binary_files_raises_needs_text_file(monkeypatch, tmp_path):
    f = tmp_path / "a.jpg"
    f.write_bytes(_JPEG_MAGIC)
    with pytest.raises(GistPublishError, match="at least one text file"):
        publish_gist([f])


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


def _git_subcommand(argv):
    """Return `(subcommand, args_after_it)` for a `git` argv that may carry
    leading `-c key=value` credential-helper overrides before the verb."""
    i = 1
    while i < len(argv) and argv[i] == "-c":
        i += 2
    return argv[i], argv[i + 1 :]


def _dispatching_fake_run(calls, *, clone_dir_factory, fail_at=None):
    """Build a fake `subprocess.run` that mimics `gh gist create` + the
    git clone/add/commit/push sequence `_push_binary_files` drives."""

    def fake_run(argv, cwd=None, **kwargs):
        calls.append((list(argv), cwd))
        if argv[0] == "gh":
            step = "gh"
            subargs = argv[1:]
        else:
            step_name, subargs = _git_subcommand(argv)
            step = f"git-{step_name}"
        if fail_at == step:
            return _FakeCompletedProcess(1, stderr=f"{step} failed")
        if step == "gh":
            return _FakeCompletedProcess(0, stdout="https://gist.github.com/xyz123\n")
        if step == "git-clone":
            dest = Path(subargs[1])
            clone_dir_factory(dest)
            return _FakeCompletedProcess(0)
        if step in ("git-add", "git-commit"):
            return _FakeCompletedProcess(0)
        if step == "git-rev-parse":
            return _FakeCompletedProcess(0, stdout="main\n")
        if step == "git-push":
            return _FakeCompletedProcess(0)
        raise AssertionError(f"unexpected call: {argv}")

    return fake_run


def test_binary_file_is_pushed_via_git_clone_add_commit_push(monkeypatch, tmp_path):
    calls = []

    def make_clone_dir(dest: Path):
        dest.mkdir(parents=True)

    monkeypatch.setattr(
        subprocess, "run", _dispatching_fake_run(calls, clone_dir_factory=make_clone_dir)
    )

    md = tmp_path / "analysis.md"
    md.write_text("# notes")
    img = tmp_path / "result.png"
    img.write_bytes(b"\x89PNG fake png bytes")

    url = publish_gist([md, img])

    assert url == "https://gist.github.com/xyz123"
    steps = [_git_subcommand(c[0])[0] if c[0][0] == "git" else c[0][0] for c in calls]
    assert "gh" in steps
    assert "clone" in steps
    assert "add" in steps
    assert "commit" in steps
    assert "push" in steps
    clone_call = next(c for c in calls if c[0][0] == "git" and _git_subcommand(c[0])[0] == "clone")
    _, clone_args = _git_subcommand(clone_call[0])
    assert clone_args[0] == "https://gist.github.com/xyz123.git"
    # Confirms the credential-helper override is actually present, not just
    # that auth happens to work in this mocked test.
    assert any("!gh auth git-credential" in arg for arg in clone_call[0])
    push_call = next(c for c in calls if c[0][0] == "git" and _git_subcommand(c[0])[0] == "push")
    assert any("!gh auth git-credential" in arg for arg in push_call[0])


def test_binary_push_clone_failure_raises(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        _dispatching_fake_run(
            calls, clone_dir_factory=lambda d: d.mkdir(parents=True), fail_at="git-clone"
        ),
    )
    md = tmp_path / "a.md"
    md.write_text("x")
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG bytes")
    with pytest.raises(GistPublishError, match="git clone"):
        publish_gist([md, img])


def test_binary_push_commit_failure_raises(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        _dispatching_fake_run(
            calls, clone_dir_factory=lambda d: d.mkdir(parents=True), fail_at="git-commit"
        ),
    )
    md = tmp_path / "a.md"
    md.write_text("x")
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG bytes")
    with pytest.raises(GistPublishError, match="git commit"):
        publish_gist([md, img])


def test_binary_push_push_failure_raises(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        _dispatching_fake_run(
            calls, clone_dir_factory=lambda d: d.mkdir(parents=True), fail_at="git-push"
        ),
    )
    md = tmp_path / "a.md"
    md.write_text("x")
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG bytes")
    with pytest.raises(GistPublishError, match="git push"):
        publish_gist([md, img])


def test_text_only_files_never_invoke_git(monkeypatch, tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _FakeCompletedProcess(0, stdout="https://gist.github.com/abc\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    f = tmp_path / "a.md"
    f.write_text("x")
    publish_gist([f])
    assert all(c[0] != "git" for c in calls)


def test_only_this_module_is_allowed_to_import_subprocess():
    """Sanity check for the layering-boundary standing check (see test_layering.py),
    which greps the whole package for `import subprocess`/`requests` usage."""
    assert hasattr(gist_publish_module, "subprocess")
