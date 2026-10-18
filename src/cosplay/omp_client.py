"""Synchronous wrapper around the `omp` CLI -- the only way this package talks to a model.

This is the only module in `src/cosplay` allowed to shell out to `omp`
(import `subprocess` for that purpose) -- `gist_publish.py` is the only
other module allowed to shell out at all, and only to `gh`, never to `omp`.
The whole run makes exactly one `omp -p` call (the vision/analysis turn), so
this stays synchronous rather than reusing an async pattern built for
concurrent agent turns.
"""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class OmpTimeoutError(TimeoutError):
    """Raised when an `omp -p` subprocess call exceeds its allotted timeout."""


class OmpCallError(RuntimeError):
    """Raised when `omp` is missing from PATH or exits non-zero."""


@dataclass(frozen=True)
class OmpResult:
    """The result of one `omp -p` subprocess call.

    Attributes:
        text: The raw response text from stdout, whitespace-stripped.
        model_used: Whatever `model` was passed in, echoed back unchanged.
        duration_seconds: Wall-clock time the subprocess call took.
    """

    text: str
    model_used: str
    duration_seconds: float


def _build_argv(
    combined_prompt: str,
    *,
    model: str,
    image_path: Path,
) -> list[str]:
    """Build the `omp -p` argv for one vision turn.

    Args:
        combined_prompt: The single prompt string to pass to `omp -p`,
            already combining system instructions and the task.
        model: Passed to `--model`. Unlike a general-purpose agent wrapper,
            this is never omitted: a vision analysis needs a model known to
            accept image input, so `omp`'s own default (which may not) is
            never silently relied on.
        image_path: Path to the image file, passed as its own `@path`
            argument -- `omp`'s own convention for attaching a file
            (`omp @prompt.md @image.png "..."`), kept separate from the text
            prompt rather than concatenated into it.

    Returns:
        The full argv list, ready for `subprocess.run`.
    """
    return [
        "omp",
        "-p",
        "--mode",
        "text",
        "--model",
        model,
        "--thinking",
        "off",
        f"@{image_path}",
        combined_prompt,
    ]


def run_vision_turn(
    system_prompt: str,
    user_prompt: str,
    image_path: Path,
    *,
    model: str,
    timeout: float = 180.0,
) -> OmpResult:
    """Run exactly one vision/analysis turn as a single non-interactive `omp -p` call.

    Combines `system_prompt` and `user_prompt` into one prompt string under
    `[System instructions]` / `[Task]` headers (plain-text `omp -p` accepts
    only one prompt argument, not separate system/user ones), attaches
    `image_path` as a separate `@path` argument, and invokes `omp -p --mode
    text --model <model>` via `subprocess.run` (never a shell, so neither the
    prompt text nor the image path can be interpreted by one).

    Args:
        system_prompt: The analysis agent's instruction text.
        user_prompt: The turn's actual task text (what to look for, the
            output schema to follow).
        image_path: Path to the photo being analyzed.
        model: Passed to `omp --model`; see `_build_argv`.
        timeout: Maximum seconds to wait before raising `OmpTimeoutError`.

    Returns:
        An `OmpResult` carrying the raw response text.

    Raises:
        OmpTimeoutError: If `omp` does not exit within `timeout` seconds.
        OmpCallError: If `omp` is not on `PATH`, or exits non-zero.
    """
    combined_prompt = f"[System instructions]\n{system_prompt}\n\n[Task]\n{user_prompt}"
    argv = _build_argv(combined_prompt, model=model, image_path=image_path)

    start = time.monotonic()
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise OmpCallError("omp is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise OmpTimeoutError(
            f"omp -p call exceeded {timeout}s timeout (model={model!r})"
        ) from exc
    duration = time.monotonic() - start

    if result.returncode != 0:
        raise OmpCallError(
            f"omp -p exited with code {result.returncode} (model={model!r}): "
            f"{result.stderr.strip()}"
        )

    return OmpResult(
        text=result.stdout.strip(),
        model_used=model,
        duration_seconds=duration,
    )
