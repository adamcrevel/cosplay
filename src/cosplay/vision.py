"""Vision analysis: count people in a photo, describe features, pick a costume.

One `omp -p` call (see `omp_client.py`) does all three jobs at once: count
distinct individuals, describe the single person's visible features when
there is exactly one, propose `candidate_count` costumes suited to those
features, and pick the single best match. The model is instructed to answer
with nothing but one JSON object, which `analyze` parses against the schema
below -- never a free-text fallback, so a malformed reply is a loud
`AnalysisParseError`, not a silently wrong guess.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from cosplay.omp_client import run_vision_turn

_SYSTEM_PROMPT = """\
You are a costume/cosplay stylist with sharp visual judgement. You will be \
shown one photo. Your only output is a single JSON object -- no prose \
before or after it, no Markdown code fence around it. Every string value is \
short (a phrase, not a paragraph)."""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class AnalysisParseError(ValueError):
    """Raised when the model's reply is not valid JSON matching the schema."""


@dataclass(frozen=True)
class Candidate:
    """One proposed costume.

    Attributes:
        name: The character or costume's name.
        reason: One to two sentences on why it suits the photographed
            person's features.
    """

    name: str
    reason: str


@dataclass(frozen=True)
class AnalysisResult:
    """The full result of one vision analysis turn.

    Attributes:
        people_count: Number of distinct human individuals visible, counted
            whether or not each one's face is visible.
        face_visible: True only when `people_count == 1` and that person's
            face is visible in the photo.
        features: A short phrase per visual attribute (hair, build, skin
            tone, apparent age range, notable features, vibe). Empty when
            `people_count != 1`.
        candidates: The proposed costumes. Empty when `people_count != 1`.
        chosen_index: Index into `candidates` of the single best match. `-1`
            when `people_count != 1`.
        chosen_reason: Why `candidates[chosen_index]` specifically, beyond
            its own `reason`. Empty when `people_count != 1`.
        image_prompt_hints: Short, comma-separated visual descriptors (outfit
            details, palette, setting) meant to be folded into the image-edit
            prompt. Empty when `people_count != 1`.
    """

    people_count: int
    face_visible: bool
    features: dict[str, str]
    candidates: list[Candidate]
    chosen_index: int
    chosen_reason: str
    image_prompt_hints: str

    @property
    def chosen(self) -> Candidate:
        """Return the chosen candidate.

        Raises:
            ValueError: If `people_count != 1` (there is nothing chosen).
        """
        if self.people_count != 1 or not (0 <= self.chosen_index < len(self.candidates)):
            raise ValueError("no chosen candidate: people_count was not exactly 1")
        return self.candidates[self.chosen_index]


def _build_user_prompt(candidate_count: int) -> str:
    """Build the task prompt instructing the model on the exact JSON schema.

    Args:
        candidate_count: How many entries `candidates` must contain when
            `people_count == 1`.

    Returns:
        The task prompt text.
    """
    return f"""\
Look at the attached photo and respond with exactly one JSON object shaped \
like this:

{{
  "people_count": <integer, the number of distinct human individuals \
visible in the photo, counted whether or not each one's face is visible>,
  "face_visible": <true only if people_count is exactly 1 AND that \
person's face is visible; false otherwise>,
  "features": {{
    "hair": "<short phrase>",
    "build": "<short phrase>",
    "skin_tone": "<short phrase>",
    "apparent_age_range": "<a broad band such as 'child', 'teen', 'adult', \
'older adult' -- never a specific number>",
    "notable_features": "<glasses, beard, visible tattoos, etc., or 'none'>",
    "vibe": "<their expression/style/aesthetic in a short phrase>"
  }},
  "candidates": [
    {{"name": "<a specific character or costume concept>", \
"reason": "<1-2 sentences on why it suits the features above>"}}
    ... exactly {candidate_count} entries total ...
  ],
  "chosen_index": <0-based index into candidates of the single best match>,
  "chosen_reason": "<1-2 sentences on why this one specifically, beyond \
what its own reason already says>",
  "image_prompt_hints": "<short, comma-separated visual descriptors of the \
costume's outfit, palette, and a fitting setting, written for an image \
generation prompt>"
}}

Rules:
- Count every distinct person you can see, even if only an arm, legs, or \
the back of their head is visible -- a person does not need a visible face \
to be counted.
- If people_count is 0 or 2 or more, omit "features", "candidates", \
"chosen_index", "chosen_reason", and "image_prompt_hints" entirely (or set \
them to null) -- there is nothing to analyze.
- If people_count is exactly 1, every other field is required, and \
"candidates" must contain exactly {candidate_count} entries.
- Candidates must be varied and genuinely suited to the person's visible \
features (coloring, build, vibe) -- not generic or interchangeable.
- Output nothing but the JSON object: no surrounding prose, no Markdown \
code fence."""


def _strip_fence(text: str) -> str:
    """Strip a leading/trailing Markdown code fence from `text`, if present."""
    return _FENCE_RE.sub("", text).strip()


def _parse(raw_text: str, candidate_count: int) -> AnalysisResult:
    """Parse and validate the model's raw reply against the schema.

    Args:
        raw_text: The model's raw stdout text.
        candidate_count: The `candidate_count` the prompt required, used to
            validate `candidates`' length when `people_count == 1`.

    Returns:
        The parsed `AnalysisResult`.

    Raises:
        AnalysisParseError: If `raw_text` is not valid JSON, or is missing a
            required field, or `people_count == 1` with a malformed
            `candidates`/`chosen_index`.
    """
    cleaned = _strip_fence(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AnalysisParseError(f"model reply was not valid JSON: {exc}\n---\n{raw_text}") from exc

    if not isinstance(data, dict) or "people_count" not in data:
        raise AnalysisParseError(f"model reply missing 'people_count': {raw_text}")

    try:
        people_count = int(data["people_count"])
    except (TypeError, ValueError) as exc:
        raise AnalysisParseError(f"'people_count' was not an integer: {data!r}") from exc

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

    try:
        features = dict(data["features"])
        raw_candidates = list(data["candidates"])
        chosen_index = int(data["chosen_index"])
        chosen_reason = str(data["chosen_reason"])
        image_prompt_hints = str(data["image_prompt_hints"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AnalysisParseError(
            f"model reply missing a required field for people_count == 1: {data!r}"
        ) from exc

    if len(raw_candidates) != candidate_count:
        raise AnalysisParseError(
            f"expected {candidate_count} candidates, got {len(raw_candidates)}: {raw_candidates!r}"
        )
    try:
        candidates = [
            Candidate(name=str(c["name"]), reason=str(c["reason"])) for c in raw_candidates
        ]
    except (KeyError, TypeError) as exc:
        raise AnalysisParseError(f"malformed candidate entry: {raw_candidates!r}") from exc

    if not 0 <= chosen_index < len(candidates):
        raise AnalysisParseError(
            f"chosen_index {chosen_index} out of range for {len(candidates)} candidates"
        )

    return AnalysisResult(
        people_count=people_count,
        face_visible=bool(data.get("face_visible", False)),
        features={str(k): str(v) for k, v in features.items()},
        candidates=candidates,
        chosen_index=chosen_index,
        chosen_reason=chosen_reason,
        image_prompt_hints=image_prompt_hints,
    )


def analyze(image_path: Path, *, model: str, candidate_count: int) -> AnalysisResult:
    """Run the vision analysis turn on `image_path` and return its parsed result.

    Args:
        image_path: Path to the photo to analyze.
        model: Passed to `omp --model` (see `omp_client.run_vision_turn`).
        candidate_count: How many candidate costumes to request.

    Returns:
        The parsed `AnalysisResult`.

    Raises:
        AnalysisParseError: If the model's reply does not match the schema.
        cosplay.omp_client.OmpTimeoutError: If the `omp` call times out.
        cosplay.omp_client.OmpCallError: If `omp` is missing or exits
            non-zero.
    """
    user_prompt = _build_user_prompt(candidate_count)
    result = run_vision_turn(_SYSTEM_PROMPT, user_prompt, image_path, model=model)
    return _parse(result.text, candidate_count)
