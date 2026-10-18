"""Publishing a run's files to a GitHub gist via the `gh` CLI.

This is the only module in `src/cosplay` allowed to shell out to `gh` --
parallel to `omp_client.py` being the only one allowed to shell out to
`omp`, and `providers/pollinations.py` the only one allowed to make
outbound HTTP calls to an image-generation provider.
"""

import subprocess
from pathlib import Path


class GistPublishError(RuntimeError):
    """Raised when `gh gist create` is not usable or fails."""


def publish_gist(files: list[Path], *, public: bool = False) -> str:
    """Create a GitHub gist containing every path in `files` and return its URL.

    Runs `gh gist create <file>...` against the given paths directly (no
    temp-file copy needed, unlike a single rendered document, since these
    are already real files on disk) -- secret by default (`gh`'s own
    default), `public=True` passes `gh`'s `--public` flag instead.

    Args:
        files: Paths to every file the gist should contain, in the order
            `gh` should list them (original photo, Markdown write-up,
            generated image).
        public: Create a public gist instead of the default secret one.

    Returns:
        The new gist's URL, exactly as `gh gist create` printed it
        (trailing whitespace stripped).

    Raises:
        GistPublishError: If `files` is empty, `gh` is not on `PATH`, is not
            authenticated, or exits non-zero for any other reason -- `gh`'s
            own stderr is included in the message rather than a bare
            traceback.
    """
    if not files:
        raise GistPublishError("publish_gist called with no files.")

    argv = ["gh", "gist", "create", *(str(p) for p in files)]
    if public:
        argv.append("--public")

    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise GistPublishError(
            "gh is not installed or not on PATH -- install the GitHub CLI "
            "and run `gh auth login` before publishing."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GistPublishError("gh gist create timed out after 60 seconds.") from exc

    if result.returncode != 0:
        raise GistPublishError(
            f"gh gist create failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()
