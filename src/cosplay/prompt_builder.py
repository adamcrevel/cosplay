"""Build the image-edit prompt for the chosen candidate.

Kept as its own module (rather than inlined in `cli.py`) so the wording can
be tuned, tested, and swapped independently of which provider ultimately
receives it -- the resulting string is provider-agnostic text, nothing
Pollinations-specific.
"""

from cosplay.vision import AnalysisResult


def build_image_prompt(result: AnalysisResult) -> str:
    """Build the text prompt for an identity-preserving, full-body costume edit.

    Args:
        result: An `AnalysisResult` with `people_count == 1` (see
            `AnalysisResult.chosen`, which raises otherwise).

    Returns:
        A single prompt string for an image-edit provider: keep the person's
        face/identity, show them full-body in the chosen costume, using the
        analysis's own visual hints for the outfit and setting.

    Raises:
        ValueError: If `result.people_count != 1` (propagated from
            `AnalysisResult.chosen`).
    """
    chosen = result.chosen
    return (
        f"Edit this photo so the same person is shown full-body, dressed as "
        f"{chosen.name} for cosplay/Halloween. Keep their face, identity, "
        f"skin tone, and body proportions exactly recognizable -- only the "
        f"outfit, pose, and background change. Costume and setting details: "
        f"{result.image_prompt_hints}. Clean, well-lit, photorealistic, "
        f"full-body framing from head to feet."
    )
