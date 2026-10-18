"""Tests for `cosplay.providers.pollinations.PollinationsProvider`."""

import base64

import pytest
import requests

from cosplay.providers.base import ImageProviderError
from cosplay.providers.pollinations import API_KEY_ENV_VAR, PollinationsProvider


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


def test_missing_api_key_raises_immediately(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    with pytest.raises(ImageProviderError, match=API_KEY_ENV_VAR):
        PollinationsProvider(model="black-forest-labs/flux.1-kontext-pro")


def test_explicit_api_key_overrides_env(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    provider = PollinationsProvider(model="m", api_key="sk_explicit")
    assert provider._api_key == "sk_explicit"


def test_successful_edit_decodes_b64_json(monkeypatch):
    raw_bytes = b"\x89PNG fake png bytes"
    encoded = base64.b64encode(raw_bytes).decode()

    def fake_post(url, headers, files, data, timeout):
        assert headers["Authorization"] == "Bearer sk_test"
        assert data["model"] == "m"
        assert data["response_format"] == "b64_json"
        return _FakeResponse(200, json_data={"data": [{"b64_json": encoded}]})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = PollinationsProvider(model="m", api_key="sk_test")
    result = provider.edit_image(image_bytes=b"src", image_filename="photo.jpg", prompt="a prompt")
    assert result == raw_bytes


def test_401_raises_image_provider_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(401, text="unauthorized"))
    provider = PollinationsProvider(model="m", api_key="sk_bad")
    with pytest.raises(ImageProviderError, match="invalid"):
        provider.edit_image(image_bytes=b"x", image_filename="p.jpg", prompt="p")


def test_402_raises_image_provider_error_about_budget(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(402))
    provider = PollinationsProvider(model="m", api_key="sk_test")
    with pytest.raises(ImageProviderError, match="budget"):
        provider.edit_image(image_bytes=b"x", image_filename="p.jpg", prompt="p")


def test_other_non_200_raises_with_status_and_body(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(500, text="server error"))
    provider = PollinationsProvider(model="m", api_key="sk_test")
    with pytest.raises(ImageProviderError, match="500"):
        provider.edit_image(image_bytes=b"x", image_filename="p.jpg", prompt="p")


def test_missing_data_field_raises(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(200, json_data={}))
    provider = PollinationsProvider(model="m", api_key="sk_test")
    with pytest.raises(ImageProviderError, match="b64_json"):
        provider.edit_image(image_bytes=b"x", image_filename="p.jpg", prompt="p")


def test_request_exception_raises_image_provider_error(monkeypatch):
    def fake_post(*a, **k):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(requests, "post", fake_post)
    provider = PollinationsProvider(model="m", api_key="sk_test")
    with pytest.raises(ImageProviderError, match="request to Pollinations.ai failed"):
        provider.edit_image(image_bytes=b"x", image_filename="p.jpg", prompt="p")


def test_only_this_module_is_allowed_to_import_requests():
    """Sanity check for the layering-boundary standing check (see test_layering.py)."""
    import cosplay.providers.pollinations as mod

    assert hasattr(mod, "requests")
