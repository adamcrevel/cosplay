"""Render the gist-ready Markdown write-up for one run."""

from cosplay.vision import AnalysisResult


def render_markdown(
    result: AnalysisResult,
    *,
    original_filename: str,
    result_filename: str,
) -> str:
    """Render the Markdown document published alongside the two image files.

    The gist itself carries three files (see `gist_publish.publish_gist`):
    `original_filename` (the input photo), this Markdown document, and
    `result_filename` (the generated costume image) -- GitHub's gist viewer
    shows every file in one page, images included, so this document only
    needs to narrate the analysis, not re-embed the images itself.

    Args:
        result: An `AnalysisResult` with `people_count == 1`.
        original_filename: The original photo's filename, as uploaded to the
            gist (named in the text so a reader knows which file is which).
        result_filename: The generated image's filename, as uploaded to the
            gist.

    Returns:
        The full Markdown document text.

    Raises:
        ValueError: If `result.people_count != 1` (propagated from
            `AnalysisResult.chosen`).
    """
    chosen = result.chosen
    f = result.features

    lines = [
        "# Cosplay pick",
        "",
        f"Original photo: `{original_filename}` · Result: `{result_filename}`",
        "",
        "## Features noticed",
        f"- **Hair:** {f.get('hair', '—')}",
        f"- **Build:** {f.get('build', '—')}",
        f"- **Skin tone:** {f.get('skin_tone', '—')}",
        f"- **Apparent age range:** {f.get('apparent_age_range', '—')}",
        f"- **Notable features:** {f.get('notable_features', '—')}",
        f"- **Vibe:** {f.get('vibe', '—')}",
        "",
        "## Candidates",
        "",
    ]
    for i, candidate in enumerate(result.candidates):
        mark = "🏆 " if i == result.chosen_index else ""
        lines.append(f"- {mark}**{candidate.name}** — {candidate.reason}")
    lines += [
        "",
        f"## Chosen: {chosen.name}",
        "",
        result.chosen_reason,
        "",
        f"*Costume/setting hints used for the generated image: {result.image_prompt_hints}*",
    ]
    return "\n".join(lines) + "\n"
