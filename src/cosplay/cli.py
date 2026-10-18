"""The `cosplay` console script: `run`, `list`, and `show` subcommands."""

import argparse
import sys
from pathlib import Path

from cosplay.config import (
    DEFAULT_ANALYSIS_MODEL,
    DEFAULT_CANDIDATE_COUNT,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_STATE_DIR,
    CosplayConfig,
)
from cosplay.gist_publish import GistPublishError, publish_gist
from cosplay.image_utils import fit_for_display
from cosplay.omp_client import OmpCallError, OmpTimeoutError
from cosplay.prompt_builder import build_image_prompt
from cosplay.providers.base import ImageProviderError
from cosplay.providers.pollinations import PollinationsProvider
from cosplay.render import render_markdown
from cosplay.store import DEFAULT_DB_PATH, Store
from cosplay.vision import AnalysisParseError, AnalysisResult, analyze


def _sniff_extension(data: bytes) -> str:
    """Guess a file extension for raw image bytes from their magic number.

    Args:
        data: The image's raw bytes.

    Returns:
        `".png"`, `".jpg"`, or `".webp"`, defaulting to `".png"` when none of
        the known signatures match.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def _print_analysis(result: AnalysisResult) -> None:
    """Print the analysis summary (features and candidates) to stdout."""
    print("\nFeatures noticed:")
    for key, value in result.features.items():
        print(f"  - {key}: {value}")
    print("\nCandidates:")
    for i, candidate in enumerate(result.candidates):
        mark = " <-- chosen" if i == result.chosen_index else ""
        print(f"  [{i}] {candidate.name}{mark}")
        print(f"      {candidate.reason}")
    print(f"\nChosen: {result.chosen.name}")
    print(f"  {result.chosen_reason}")


def cmd_run(args: argparse.Namespace) -> int:
    """Run the full pipeline: analyze, reject or generate, optionally publish.

    Returns:
        Process exit code: `0` on success (including a clean 0/multiple-people
        rejection, which is expected, correct behavior, not an error), `1` on
        a pipeline failure (model/provider/publish error), `2` on bad input.
    """
    try:
        config = CosplayConfig(
            image_path=Path(args.image),
            candidate_count=args.candidates,
            analysis_model=args.model,
            image_model=args.image_model,
            publish=not args.no_publish,
            public_gist=args.public,
            state_dir=Path(args.state_dir),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    store = Store(Path(args.db_path))
    run_id = store.create_run(image_path=str(config.image_path))
    print(f"Run {run_id}: analyzing {config.image_path} with model={config.analysis_model}...")

    try:
        result = analyze(
            config.image_path, model=config.analysis_model, candidate_count=config.candidate_count
        )
    except (OmpTimeoutError, OmpCallError, AnalysisParseError) as exc:
        store.update_run(run_id, status="failed", error=str(exc))
        print(f"error: analysis failed: {exc}", file=sys.stderr)
        return 1

    store.update_run(run_id, people_count=result.people_count, omp_model=config.analysis_model)

    if result.people_count < 1:
        store.update_run(run_id, status="rejected_no_person")
        print(f"\nRejected: no person detected in {config.image_path}.", file=sys.stderr)
        return 0
    if result.people_count > 1:
        store.update_run(run_id, status="rejected_multiple_people")
        print(
            f"\nRejected: {result.people_count} people detected in {config.image_path} "
            "(need exactly one).",
            file=sys.stderr,
        )
        return 0

    store.update_run(
        run_id,
        status="generating",
        features=result.features,
        candidates=[{"name": c.name, "reason": c.reason} for c in result.candidates],
        chosen_index=result.chosen_index,
        chosen_name=result.chosen.name,
        image_model=config.image_model,
    )
    _print_analysis(result)

    original_bytes = config.image_path.read_bytes()
    prompt = build_image_prompt(result)

    try:
        provider = PollinationsProvider(model=config.image_model)
        result_bytes = provider.edit_image(
            image_bytes=original_bytes, image_filename=config.image_path.name, prompt=prompt
        )
    except ImageProviderError as exc:
        store.update_run(run_id, status="failed", error=str(exc))
        print(f"\nerror: image generation failed: {exc}", file=sys.stderr)
        return 1

    run_dir = config.state_dir / "runs" / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Full-resolution `original_bytes`/`result_bytes` already did their job
    # (analysis, generation); what's saved and published is a display copy
    # -- GitHub's gist viewer renders an image at native size with no
    # responsive scaling, confirmed live against a real gist, so an
    # unresized phone photo overflows the page with scrollbars.
    original_display_bytes = fit_for_display(original_bytes)
    result_display_bytes = fit_for_display(result_bytes)

    original_path = run_dir / f"original{_sniff_extension(original_display_bytes)}"
    result_path = run_dir / f"result{_sniff_extension(result_display_bytes)}"
    md_path = run_dir / "analysis.md"

    original_path.write_bytes(original_display_bytes)
    result_path.write_bytes(result_display_bytes)
    md_path.write_text(
        render_markdown(
            result, original_filename=original_path.name, result_filename=result_path.name
        )
    )

    store.update_run(run_id, status="generated", result_image_path=str(result_path))
    print(f"\nSaved: {original_path}, {result_path}, {md_path}")

    if not config.publish:
        print("Not published (--no-publish).")
        return 0

    try:
        gist_url = publish_gist([original_path, md_path, result_path], public=config.public_gist)
    except GistPublishError as exc:
        store.update_run(run_id, status="failed", error=str(exc))
        print(f"\nerror: gist publish failed: {exc}", file=sys.stderr)
        return 1

    store.update_run(run_id, status="published", gist_url=gist_url)
    print(f"Published: {gist_url}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Print every persisted run: id, created_at, status, chosen character, gist URL."""
    store = Store(Path(args.db_path))
    runs = store.list_runs()
    if not runs:
        print("No runs yet.")
        return 0
    for run in runs:
        chosen = run.chosen_name or "-"
        gist = run.gist_url or "-"
        print(f"{run.id}\t{run.created_at}\t{run.status}\t{chosen}\t{gist}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Print one persisted run's full detail.

    Returns:
        `0` if the run exists, `1` if `args.run_id` is not a known run.
    """
    store = Store(Path(args.db_path))
    run = store.get_run(args.run_id)
    if run is None:
        print(f"error: no run with id {args.run_id}", file=sys.stderr)
        return 1

    print(f"Run {run.id}  ({run.created_at})")
    print(f"  image:        {run.image_path}")
    print(f"  status:       {run.status}")
    print(f"  people_count: {run.people_count}")
    if run.features:
        print("  features:")
        for key, value in run.features.items():
            print(f"    - {key}: {value}")
    if run.candidates:
        print("  candidates:")
        for i, candidate in enumerate(run.candidates):
            mark = " <-- chosen" if i == run.chosen_index else ""
            print(f"    [{i}] {candidate['name']}{mark}")
    if run.result_image_path:
        print(f"  result image: {run.result_image_path}")
    if run.gist_url:
        print(f"  gist:         {run.gist_url}")
    if run.error:
        print(f"  error:        {run.error}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser and its three subcommands."""
    parser = argparse.ArgumentParser(
        prog="cosplay", description="Turn a photo of one person into a matching cosplay look."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Analyze a photo and generate a costume image")
    run_parser.add_argument("image", help="Path to the input photo")
    run_parser.add_argument(
        "--candidates",
        type=int,
        default=DEFAULT_CANDIDATE_COUNT,
        help=f"Number of candidate costumes to propose (default: {DEFAULT_CANDIDATE_COUNT})",
    )
    run_parser.add_argument(
        "--model",
        default=DEFAULT_ANALYSIS_MODEL,
        help=f"Model passed to `omp --model` for analysis (default: {DEFAULT_ANALYSIS_MODEL!r})",
    )
    run_parser.add_argument(
        "--image-model",
        default=DEFAULT_IMAGE_MODEL,
        help=f"Image provider model id (default: {DEFAULT_IMAGE_MODEL!r})",
    )
    run_parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Skip publishing a gist; keep the run local-only",
    )
    run_parser.add_argument(
        "--public",
        action="store_true",
        help="Publish a public gist instead of the default secret one",
    )
    run_parser.add_argument(
        "--state-dir",
        default=str(DEFAULT_STATE_DIR),
        help=f"Directory for per-run output files (default: {DEFAULT_STATE_DIR})",
    )
    run_parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite store path (default: {DEFAULT_DB_PATH})",
    )
    run_parser.set_defaults(func=cmd_run)

    list_parser = subparsers.add_parser("list", help="List every past run")
    list_parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite store path (default: {DEFAULT_DB_PATH})",
    )
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="Show one past run's full detail")
    show_parser.add_argument("run_id", type=int, help="Run id, from `cosplay list`")
    show_parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite store path (default: {DEFAULT_DB_PATH})",
    )
    show_parser.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `cosplay` console script."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
