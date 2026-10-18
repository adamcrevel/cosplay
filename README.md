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
`/v1/images/edits` endpoint. This needs **your own** GitHub login in a
browser, so it can't be done on your behalf — do this once:

1. Go to **<https://enter.pollinations.ai/keys>** and click **"Sign in with
   GitHub"**. No payment method is requested anywhere in this flow.
2. **Claim free Pollen before creating a key.** Pollinations retired its
   hourly free-Pollen refill; the only Pollen that costs nothing now comes
   from one-off **Quests** on the dashboard (e.g. "make your first API
   call", "link GitHub") — look for a "Quests" link/tab after signing in and
   claim whatever's available. Skipping this is fine too; it just means your
   balance starts at 0 and the first real request fails with a `402` until
   you claim something (see the balance check below) — no surprise charge
   either way, 402 just means "nothing to spend." **Expect to come back and
   claim another Quest periodically** — see the cost note below; this isn't
   a one-time thing.
3. Click **"Create secret key"** (or **"+ New key"**). In the dialog:
   - **Budget** — a numeric Pollen cap. This only *limits* spending from
     Pollen you already have; it is not a card charge and nothing is ever
     auto-billed unless you separately buy Pollen. The default (`5`) works
     fine; your actual balance (not the budget field) is the real ceiling.
   - **Expiry** — defaults to 7 days. If the dialog offers a longer option
     (30/90 days, or no expiry), pick that for a personal tool you'll keep
     using; otherwise you'll need to regenerate the key weekly.
   - **Models / permissions** — this is the part that controls whether the
     key can actually call image generation. Look for a "Models" or "Model
     access" section and check the **"image"** category (covers
     `black-forest-labs/flux.1-kontext-pro`, this project's default, plus
     any model you swap to later), or search for and select that exact
     model id if you'd rather scope it tighter. Leave the separate
     **account permissions** (sometimes labeled `profile`/`usage`/`keys`)
     unchecked — this CLI only ever generates images, never manages the
     account (checking `usage` too doesn't hurt — it only enables reading
     your balance back, as the next step does).
4. Copy the `sk_...` value shown (usually shown once) and export it:
   ```sh
   export POLLINATIONS_API_KEY=sk_...
   ```
   (Add that line to your shell profile to keep it across sessions. Never
   commit it — `.gitignore` already excludes `.env`.)
5. **Verify it actually took**, with two read-only calls that need no extra
   permission on the key:
   ```sh
   # Confirms the key is valid and shows what it's permitted to call:
   curl -H "Authorization: Bearer $POLLINATIONS_API_KEY" https://gen.pollinations.ai/account/key
   # Confirms there's Pollen on it to actually spend:
   curl -H "Authorization: Bearer $POLLINATIONS_API_KEY" https://gen.pollinations.ai/account/balance
   ```
   A `0` balance means step 2's Quest Pollen wasn't claimed (or there wasn't
   any available) — `cosplay run` will reach image generation and fail with
   a clear `402` from Pollinations.ai until there's something to spend.

**Cost, for real** — measured by actually generating images and reading
`GET /account/key/usage` and the balance delta back, not estimated from the
catalog's per-token price (that number is easy to misread as per-image; an
earlier version of this README did exactly that and was wrong):

| Model | Real cost/image | Full-body result from a headshot? |
| --- | --- | --- |
| `black-forest-labs/flux.1-kontext-pro` (default) | **0.03 Pollen**, flat | Yes — extended to a full standing body |
| `openai/gpt-image-1.5` | 0.043 Pollen | No — stayed a bust/seated crop |
| `openai/gpt-image-1-mini` | 0.0102 Pollen | No — stayed a bust crop |

`gpt-image-1-mini` is the cheapest of the three but didn't do the one thing
this tool actually needs; `flux.1-kontext-pro` is the best balance of cost
and the full-body requirement, so it's the default. At 0.03 Pollen/image, a
typical small Quest reward (think low single digits of Pollen) covers
**dozens** of runs, not thousands — plan to revisit the Quests page
occasionally, not once ever. (We also checked Gemini, OpenAI direct,
Stability, and Replicate: none of them let you generate a single image
without first linking a card — Pollinations' Quest Pollen remains the only
no-card-at-all path that exists for this, it's just not as cheap as
originally advertised here.)

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
