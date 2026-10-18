"""Publishing a run's files to a GitHub gist via the `gh` and `git` CLIs.

This is the only module in `src/cosplay` allowed to shell out to `gh` or
`git` -- parallel to `omp_client.py` being the only one allowed to shell out
to `omp`, and `providers/pollinations.py` the only one allowed to make
outbound HTTP calls to an image-generation provider.

`gh gist create` flatly refuses any file it can't decode as UTF-8 text
("binary file not supported") -- confirmed against a real gist, not assumed
-- so a photo or generated image can never go through it directly. The
actual mechanism: a gist is a plain git repository, so `publish_gist`
creates the gist from its text file(s) via `gh gist create` first, then
`git clone`s that same gist and pushes any binary files into it as a second
commit. The branch name is read back from the clone (`git rev-parse
--abbrev-ref HEAD`) rather than assumed -- confirmed live that new gists
default to `main`, but asserting that as a constant would silently break if
GitHub ever changes it again.
"""

import subprocess
import tempfile
from pathlib import Path


class GistPublishError(RuntimeError):
    """Raised when `gh`/`git` are not usable, or either step fails."""


def _is_text(path: Path) -> bool:
    """Return whether `path`'s contents decode as UTF-8 text.

    This is the same boundary `gh gist create` itself enforces -- used here
    to split `files` into what can go through `gh gist create` directly and
    what needs the git clone/push path instead.
    """
    try:
        path.read_text(encoding="utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _run(
    argv: list[str], *, cwd: Path | None = None, timeout: float
) -> subprocess.CompletedProcess:
    """Run `argv`, translating a missing binary or timeout into `GistPublishError`.

    Args:
        argv: The command and its arguments.
        cwd: Working directory for the subprocess, if any.
        timeout: Seconds to wait before raising.

    Returns:
        The completed process (stdout/stderr captured as text); a non-zero
        return code is left for the caller to interpret with its own
        context-specific message.

    Raises:
        GistPublishError: If `argv[0]` is not on `PATH`, or the call times
            out.
    """
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise GistPublishError(f"{argv[0]} is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GistPublishError(f"{' '.join(argv)} timed out after {timeout}s.") from exc


#: Forces git to delegate HTTPS auth to `gh`'s own token for one invocation,
#: without touching the caller's global git config. Plain `git clone`/`push`
#: against gist.github.com do not automatically pick up `gh auth login`'s
#: token unless `gh auth setup-git` was separately run -- confirmed live
#: (push failed with "terminal prompts disabled" otherwise) -- so this is
#: prepended to every clone/push argv instead of assuming that setup step
#: already happened.
_GH_CREDENTIAL_HELPER_ARGS = [
    "-c",
    "credential.helper=",
    "-c",
    "credential.helper=!gh auth git-credential",
]


def _push_binary_files(gist_url: str, binary_files: list[Path]) -> None:
    """Clone `gist_url` and push `binary_files` into it as a second commit.

    Args:
        gist_url: The gist's web URL, as `gh gist create` printed it.
        binary_files: Paths to copy into the gist's repo and push.

    Raises:
        GistPublishError: If the clone, add, commit, or push step fails.
    """
    gist_id = gist_url.rstrip("/").rsplit("/", 1)[-1]
    clone_url = f"https://gist.github.com/{gist_id}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "gist"

        clone = _run(
            ["git", *_GH_CREDENTIAL_HELPER_ARGS, "clone", clone_url, str(repo_dir)], timeout=60
        )
        if clone.returncode != 0:
            raise GistPublishError(f"git clone of the new gist failed: {clone.stderr.strip()}")

        for f in binary_files:
            (repo_dir / f.name).write_bytes(f.read_bytes())

        add = _run(["git", "add", *(f.name for f in binary_files)], cwd=repo_dir, timeout=30)
        if add.returncode != 0:
            raise GistPublishError(f"git add of image file(s) failed: {add.stderr.strip()}")

        commit = _run(["git", "commit", "-m", "Add generated images"], cwd=repo_dir, timeout=30)
        if commit.returncode != 0:
            raise GistPublishError(f"git commit of image file(s) failed: {commit.stderr.strip()}")

        branch_result = _run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, timeout=10
        )
        branch = branch_result.stdout.strip() or "main"

        push = _run(
            ["git", *_GH_CREDENTIAL_HELPER_ARGS, "push", "origin", branch],
            cwd=repo_dir,
            timeout=60,
        )
        if push.returncode != 0:
            raise GistPublishError(f"git push of image file(s) failed: {push.stderr.strip()}")


def publish_gist(files: list[Path], *, public: bool = False) -> str:
    """Create a GitHub gist containing every path in `files` and return its URL.

    Text files go through `gh gist create` directly (secret by default,
    `public=True` passes `gh`'s `--public` flag); any binary file is pushed
    afterward via `git clone`/`add`/`commit`/`push` against that same gist,
    since `gh gist create` cannot carry one itself.

    Args:
        files: Paths to every file the gist should contain. Order among the
            text files is what `gh` lists them in; binary files are added
            in a second commit after the gist exists.
        public: Create a public gist instead of the default secret one.

    Returns:
        The new gist's URL, exactly as `gh gist create` printed it
        (trailing whitespace stripped).

    Raises:
        GistPublishError: If `files` is empty, none of them are text (there
            is nothing to create the gist from), `gh`/`git` are missing or
            unauthenticated, or any step fails -- the underlying tool's own
            stderr is included in the message rather than a bare traceback.
    """
    if not files:
        raise GistPublishError("publish_gist called with no files.")

    text_files = [f for f in files if _is_text(f)]
    binary_files = [f for f in files if f not in text_files]

    if not text_files:
        raise GistPublishError(
            "publish_gist needs at least one text file to create the gist from "
            "-- gh gist create cannot start from a binary file. Pass a Markdown "
            "write-up alongside any images."
        )

    argv = ["gh", "gist", "create", *(str(p) for p in text_files)]
    if public:
        argv.append("--public")

    result = _run(argv, timeout=60)
    if result.returncode != 0:
        raise GistPublishError(
            f"gh gist create failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    gist_url = result.stdout.strip()

    if binary_files:
        _push_binary_files(gist_url, binary_files)

    return gist_url
