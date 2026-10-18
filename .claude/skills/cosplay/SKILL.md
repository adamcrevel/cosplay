---
name: cosplay
description: Turn a photo of one person into a matching cosplay/Halloween costume idea via the `cosplay` CLI, generate a full-body image of them in it, and publish the result as a GitHub gist. Trigger whenever the user gives you a photo (a file path) and wants a costume suggestion, wants to "cosplay-ify" or "Halloween-ify" someone, or asks what costume would suit a photo. Also covers listing or inspecting past runs.
user-invocable: true
---

# cosplay — suggest and generate a costume from a photo

Wraps the `cosplay` console script (`uv run cosplay ...`, run from the
project root). Given a photo, it checks there's exactly one person in it,
analyzes their visible features, proposes several costume candidates, picks
the best match, generates a full-body image of them wearing it, and
publishes a gist showing the whole process.

## `cosplay run <image>` — the whole pipeline, one call

```sh
uv run cosplay run /path/to/photo.jpg
```

This single command does everything: analyze, reject-or-pick, generate,
publish. There is nothing to orchestrate across multiple calls — run it once
per photo.

**Read the exit behavior correctly before reporting a result:**

- **Exit 0 with a gist URL on the last line (`Published: https://gist.github.com/...`)**
  — success. Report that URL to the user; that is the shareable result.
- **Exit 0 with a `Rejected: ...` line on stderr, no gist URL** — this is
  *expected, correct* behavior, not a failure: the photo had zero people or
  more than one. Tell the user plainly why (quoting the rejection line) and
  ask for a different photo. Do not retry the same image or treat this as a
  bug.
- **Exit 1 with an `error: ...` line on stderr** — an actual failure
  (analysis, image generation, or gist publish). Surface the exact error
  text to the user. The key is normally already set up (`~/.cosplay/pollinations_key`
  or `POLLINATIONS_API_KEY` — see the project README's "One manual setup
  step"), so a missing-key error here means that file/var genuinely isn't
  present, not a transient issue. A `402` means the Pollinations.ai account
  has no Pollen balance to spend (free Pollen now only comes from claiming
  a Quest on the dashboard) — both require the user's own action, not a
  retry from here.
- **Exit 2** — bad input (missing file, unsupported image type). Fix the
  path/format and re-run.

Useful flags: `--candidates N` (default 4) to propose more or fewer costume
ideas; `--no-publish` to generate without creating a gist (e.g. if asked to
"just show me the idea first"); `--public` for a public gist instead of the
default secret one; `--model`/`--image-model` to point analysis or
generation at a different model (see the README's "Swapping providers").

## `cosplay list` — past runs

```sh
uv run cosplay list
```

Prints every past run (id, timestamp, status, chosen character, gist URL).
Use this when the user asks "what have I run before" or references an
earlier result without a fresh photo.

## `cosplay show <id>` — one run's full detail

```sh
uv run cosplay show 3
```

Prints that run's features, every candidate considered (chosen one marked),
the local result image path, and its gist URL. Use this to answer a
follow-up question about a specific past run (e.g. "what were the other
options for run 3?") without re-running analysis.

## Out of scope

Only one photo per `run` call — there is no batch mode. A request to process
several photos means calling `cosplay run` once per photo, each a separate
invocation.
