# cosplay

Give it a photo of one person. It checks there's exactly one of them, looks
at their visible features, proposes a few cosplay/Halloween costumes suited
to those features, picks the best one, generates a full-body image of them
in it, and publishes the whole thing — original photo, candidates, chosen
reasoning, result — as a GitHub gist.

## Install

This project is managed with [`uv`](https://docs.astral.sh/uv/).

```sh
uv sync
```

This installs the `cosplay` console script into the project's virtual
environment. Run it with `uv run cosplay ...`, or activate the venv and run
`cosplay ...` directly.

Two other CLIs must already be installed and authenticated:

- [`omp`](https://github.com) — does the vision analysis (counting people,
  describing features, proposing and picking a costume). No separate API key
  of its own here; it uses whatever model/credentials your `omp` setup is
  already configured with.
- [`gh`](https://cli.github.com/) — publishes the gist. Run `gh auth login`
  (with the `gist` scope) if you haven't already.

## One manual setup step: a Pollinations.ai key

Image generation calls [Pollinations.ai](https://pollinations.ai)'s
`/v1/images/edits` endpoint (the Flux Kontext model), which needs a secret
key. This step needs **your own** GitHub login in a browser, so it can't be
done on your behalf — do this once:

1. Go to **<https://enter.pollinations.ai/keys>**.
2. Click **"Sign in with GitHub"** and authorize it.
3. Create a new **secret key** (`sk_...`) with image-generation permission.
4. Export it:
   ```sh
   export POLLINATIONS_API_KEY=sk_...
   ```
   (Add that line to your shell profile to keep it across sessions. Never
   commit it — `.gitignore` already excludes `.env`.)
5. The Kontext edit model requires the account's "seed" tier or higher. A
   brand-new key may need to reach that tier before `/v1/images/edits`
   accepts requests — check your account status on the
   [dashboard](https://enter.pollinations.ai) if `cosplay run` reports a
   `402` from Pollinations.

## Usage

### `cosplay run` — the whole pipeline

```sh
uv run cosplay run photo.jpg
```

1. Analyzes the photo via `omp` (default model: a Claude model — see
   "Swapping providers" below). Rejects (prints why, exits 0 — this is
   expected behavior, not an error) if it finds zero people or more than
   one.
2. For exactly one person: describes their visible features, proposes
   `--candidates` costumes (default 4) with reasoning each, and picks one.
3. Builds an edit prompt from the chosen costume and generates a full-body
   image of the person in it via Pollinations.ai, keeping their identity
   recognizable.
4. Publishes a **secret** gist (`--public` for a public one instead)
   containing three files: the original photo, a Markdown write-up (features
   noticed, every candidate with the chosen one marked 🏆, why it was
   chosen), and the generated image. GitHub's gist viewer renders both image
   files inline.

Flags: `--candidates N`, `--model NAME` (the `omp --model` value for
analysis), `--image-model ID` (the Pollinations model id), `--no-publish`
(keep the run local-only), `--public`, `--state-dir PATH`, `--db-path PATH`.

Every run — rejected, failed, or published — is recorded in a local SQLite
store (`~/.cosplay/cosplay.db` by default).

### `cosplay list` — list every past run

```sh
uv run cosplay list
```

Prints id, timestamp, status, chosen character, and gist URL for every run.

### `cosplay show <id>` — one run's full detail

```sh
uv run cosplay show 3
```

Prints that run's features, every candidate (chosen one marked), the result
image's local path, and its gist URL.

## Swapping providers

Two seams exist precisely so a different backend can replace either side
without touching the rest of the pipeline:

- **Analysis model** — `vision.py` asks `omp --model <name>` to do the
  counting/description/costume-picking in one JSON-structured call. It
  defaults to a Claude model (`cosplay.config.DEFAULT_ANALYSIS_MODEL`),
  overridable with `--model` on the CLI or by editing that default — nothing
  else in the pipeline depends on which model answers.
- **Image generation** — `providers/base.ImageProvider` is a one-method
  interface (`edit_image`). `providers/pollinations.py` is the only
  implementation shipped; add another module implementing the same
  interface and wire it into `cli.py` in place of `PollinationsProvider` to
  switch backends.

## Layering

- Only `omp_client.py` shells out to `omp`.
- Only `gist_publish.py` shells out to `gh`.
- Only `providers/pollinations.py` makes outbound HTTP calls to an image
  provider.

## The `cosplay` skill

`.claude/skills/cosplay/SKILL.md` wraps this CLI for an LLM agent (Claude
Code / `omp`) — it's auto-discovered whenever you're working inside this
repo. To use it from any project, copy it into your global skills directory:

```sh
cp -r .claude/skills/cosplay ~/.claude/skills/cosplay
```

## Out of scope

Candidate costumes are described in the write-up as text only — no
concept-art image is generated per candidate, only for the one actually
chosen, to keep each run to a single image-generation call.
