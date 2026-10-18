"""Configuration for a single `cosplay run` invocation."""

from dataclasses import dataclass
from pathlib import Path

#: Default model passed to `omp --model` for the vision/analysis turn. A plain
#: fuzzy name (not a full provider/model id) so `omp` resolves it the same way
#: `omp --model claude "..."` would on the command line. Swap this (or pass
#: `--model` on the CLI) to point analysis at a different provider entirely.
DEFAULT_ANALYSIS_MODEL = "claude"

#: Default Pollinations.ai model for the identity-preserving image edit.
#: See https://gen.pollinations.ai/docs -> Image -> /v1/images/edits.
DEFAULT_IMAGE_MODEL = "black-forest-labs/flux.1-kontext-pro"

#: Default number of candidate costumes the analysis step proposes.
DEFAULT_CANDIDATE_COUNT = 4

#: Local state directory: SQLite store plus one subdirectory per run holding
#: the original photo, the generated image, and the rendered gist Markdown.
DEFAULT_STATE_DIR = Path.home() / ".cosplay"

#: Image extensions `cosplay run` accepts as input.
SUPPORTED_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})


@dataclass
class CosplayConfig:
    """Settings that control how one `cosplay run` is carried out.

    Attributes:
        image_path: Path to the input photo. Must exist and have a supported
            suffix; validated in `__post_init__`.
        candidate_count: How many candidate costumes the analysis step
            proposes before picking one. Must be at least 1.
        analysis_model: Model name passed to `omp --model` for the vision
            analysis turn. Never hardcoded deeper than this one default, so a
            caller can swap providers without touching `vision.py`.
        image_model: Model id passed to the image provider's `model` field.
        publish: Whether to publish a gist via `gh gist create` after a
            successful generation. `cosplay run --no-publish` sets this False
            to leave the run local-only.
        public_gist: Whether the published gist is public instead of the
            default secret.
        state_dir: Root directory for the SQLite store and per-run output
            files.
    """

    image_path: Path
    candidate_count: int = DEFAULT_CANDIDATE_COUNT
    analysis_model: str = DEFAULT_ANALYSIS_MODEL
    image_model: str = DEFAULT_IMAGE_MODEL
    publish: bool = True
    public_gist: bool = False
    state_dir: Path = DEFAULT_STATE_DIR

    def __post_init__(self) -> None:
        """Validate `image_path` and `candidate_count`.

        Raises:
            FileNotFoundError: If `image_path` does not exist.
            ValueError: If `image_path`'s suffix is unsupported, or
                `candidate_count` is less than 1.
        """
        if not self.image_path.exists():
            raise FileNotFoundError(f"image not found: {self.image_path}")
        if self.image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            supported = ", ".join(sorted(SUPPORTED_IMAGE_SUFFIXES))
            raise ValueError(
                f"unsupported image type {self.image_path.suffix!r} "
                f"(supported: {supported})"
            )
        if self.candidate_count < 1:
            raise ValueError("candidate_count must be at least 1")
