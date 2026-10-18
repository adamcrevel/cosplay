"""Pollinations.ai image provider: `POST /v1/images/edits`.

This is the only module in `src/cosplay` allowed to make outbound HTTP
calls to an image-generation provider -- parallel to `omp_client.py` being
the only one allowed to shell out to `omp`, and `gist_publish.py` the only
one allowed to shell out to `gh`.

Setup (one-time, manual -- see the project README): create a secret key at
https://enter.pollinations.ai/keys (Sign in with GitHub), then either
export it as `POLLINATIONS_API_KEY` or save it to `~/.cosplay/pollinations_key`
(see `DEFAULT_KEY_FILE`) -- the file is the recommended path: a shell
profile export (`~/.bashrc`/`~/.profile`) only reaches *interactive* shells,
confirmed by testing it does not reach a non-interactive tool invocation
(the shape this CLI actually runs under when an agent invokes the `cosplay`
skill), so an env-var-only setup can silently stop working outside a
terminal you opened yourself. Pollinations retired its hourly free-Pollen
refill; claim a one-off Quest on the dashboard for free Pollen before
creating the key, or the first request fails with a 402 until there's a
balance to spend. At this module's default model's real, verified price
(0.03 Pollen/image flat), a typical small Quest claim covers dozens of
images -- not unlimited, so expect to revisit Quests occasionally for
sustained use.
"""

import base64
import os

import requests

from cosplay.config import DEFAULT_STATE_DIR
from cosplay.providers.base import ImageProvider, ImageProviderError

EDITS_URL = "https://gen.pollinations.ai/v1/images/edits"

#: Env var holding the Pollinations.ai secret key (`sk_...`); checked first.
API_KEY_ENV_VAR = "POLLINATIONS_API_KEY"

#: Fallback file holding the key as its entire (whitespace-trimmed) content,
#: checked when `API_KEY_ENV_VAR` is unset. Not git-ignored by this project
#: specifically since it already lives outside any repo, under the user's
#: home directory, alongside the rest of this tool's state
#: (`cosplay.config.DEFAULT_STATE_DIR`) -- save it with `chmod 600`.
DEFAULT_KEY_FILE = DEFAULT_STATE_DIR / "pollinations_key"


class PollinationsProvider(ImageProvider):
    """Calls Pollinations.ai's OpenAI-compatible `/v1/images/edits` endpoint."""

    def __init__(self, *, model: str, api_key: str | None = None, timeout: float = 120.0) -> None:
        """Create a provider bound to one image-edit model.

        Args:
            model: Pollinations model id, e.g.
                `"black-forest-labs/flux.1-kontext-pro"`.
            api_key: Secret key to use. Falls back to the
                `POLLINATIONS_API_KEY` env var, then to `DEFAULT_KEY_FILE`'s
                contents, when omitted; never hardcoded.
            timeout: Request timeout in seconds.

        Raises:
            ImageProviderError: If no API key is given, `POLLINATIONS_API_KEY`
                is not set, and `DEFAULT_KEY_FILE` doesn't exist either.
        """
        self._model = model
        self._timeout = timeout
        key = api_key if api_key is not None else os.environ.get(API_KEY_ENV_VAR)
        if not key and DEFAULT_KEY_FILE.exists():
            key = DEFAULT_KEY_FILE.read_text(encoding="utf-8").strip()
        if not key:
            raise ImageProviderError(
                f"{API_KEY_ENV_VAR} is not set and {DEFAULT_KEY_FILE} doesn't exist. "
                "Create a secret key at https://enter.pollinations.ai/keys "
                "(Sign in with GitHub), then either export it or save it to "
                f"{DEFAULT_KEY_FILE} (chmod 600)."
            )
        self._api_key = key

    def edit_image(self, *, image_bytes: bytes, image_filename: str, prompt: str) -> bytes:
        """Edit `image_bytes` per `prompt` and return the result's raw bytes.

        Posts a `multipart/form-data` request with `response_format:
        b64_json`, decodes `data[0].b64_json` from the JSON reply.

        Args:
            image_bytes: The source photo's raw bytes.
            image_filename: The source photo's filename (sets the multipart
                field's filename/content-type hint).
            prompt: The edit prompt (see
                `cosplay.prompt_builder.build_image_prompt`).

        Returns:
            The edited image's raw bytes.

        Raises:
            ImageProviderError: If the request fails, times out, or the
                response doesn't carry `data[0].b64_json`.
        """

        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {"image": (image_filename, image_bytes)}
        data = {
            "prompt": prompt,
            "model": self._model,
            "response_format": "b64_json",
        }

        try:
            response = requests.post(
                EDITS_URL, headers=headers, files=files, data=data, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise ImageProviderError(f"request to Pollinations.ai failed: {exc}") from exc

        if response.status_code == 401:
            raise ImageProviderError(
                f"Pollinations.ai rejected {API_KEY_ENV_VAR} as invalid (401)."
            )
        if response.status_code == 402:
            raise ImageProviderError(
                "Pollinations.ai says the account/key budget is exhausted (402) -- "
                "check the account's tier/balance at enter.pollinations.ai."
            )
        if response.status_code != 200:
            raise ImageProviderError(
                f"Pollinations.ai edit request failed ({response.status_code}): "
                f"{response.text[:500]}"
            )

        try:
            payload = response.json()
            b64_data = payload["data"][0]["b64_json"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ImageProviderError(
                f"Pollinations.ai response did not carry data[0].b64_json: {response.text[:500]}"
            ) from exc

        try:
            return base64.b64decode(b64_data)
        except (ValueError, TypeError) as exc:
            raise ImageProviderError(
                "Pollinations.ai returned malformed base64 image data."
            ) from exc
