"""Tests for `cosplay.omp_client`."""

import subprocess

import pytest

from cosplay.omp_client import OmpCallError, OmpTimeoutError, _build_argv, run_vision_turn


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_build_argv_includes_model_and_image_as_separate_arg(tmp_path):
    image = tmp_path / "photo.jpg"
    argv = _build_argv("prompt text", model="claude", image_path=image)
    assert argv[:4] == ["omp", "-p", "--mode", "text"]
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "claude"
    assert f"@{image}" in argv
    assert argv[-1] == "prompt text"


def test_run_vision_turn_combines_system_and_user_prompt(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _FakeCompletedProcess(0, stdout='{"people_count": 1}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"x")
    result = run_vision_turn("sys", "task", image, model="claude")
    assert "[System instructions]\nsys" in captured["argv"][-1]
    assert "[Task]\ntask" in captured["argv"][-1]
    assert result.text == '{"people_count": 1}'
    assert result.model_used == "claude"


def test_run_vision_turn_strips_stdout_whitespace(monkeypatch, tmp_path):
    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess(0, stdout="  hello  \n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    image = tmp_path / "photo.jpg"
    result = run_vision_turn("sys", "task", image, model="claude")
    assert result.text == "hello"


def test_nonzero_exit_raises_omp_call_error(monkeypatch, tmp_path):
    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess(1, stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    image = tmp_path / "photo.jpg"
    with pytest.raises(OmpCallError, match="boom"):
        run_vision_turn("sys", "task", image, model="claude")


def test_omp_not_found_raises_omp_call_error(monkeypatch, tmp_path):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)
    image = tmp_path / "photo.jpg"
    with pytest.raises(OmpCallError, match="not installed"):
        run_vision_turn("sys", "task", image, model="claude")


def test_timeout_raises_omp_timeout_error(monkeypatch, tmp_path):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=180)

    monkeypatch.setattr(subprocess, "run", fake_run)
    image = tmp_path / "photo.jpg"
    with pytest.raises(OmpTimeoutError, match="timeout"):
        run_vision_turn("sys", "task", image, model="claude")
