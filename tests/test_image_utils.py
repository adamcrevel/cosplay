"""Tests for `cosplay.image_utils.fit_for_display`."""

import io

from PIL import Image

from cosplay.image_utils import MAX_DIMENSION, fit_for_display


def _make_image(width: int, height: int, *, fmt: str = "PNG", exif=None) -> bytes:
    img = Image.new("RGB", (width, height), "red")
    buf = io.BytesIO()
    if exif is not None:
        img.save(buf, format=fmt, exif=exif)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def test_small_image_with_normal_orientation_returned_byte_identical():
    data = _make_image(200, 150)
    assert fit_for_display(data) == data


def test_oversized_image_is_downscaled_to_max_dimension():
    data = _make_image(3000, 2000)
    result = fit_for_display(data)
    with Image.open(io.BytesIO(result)) as out:
        assert max(out.size) == MAX_DIMENSION


def test_downscale_preserves_aspect_ratio():
    data = _make_image(2784, 2080)  # the real phone-photo dimensions that broke a real gist
    result = fit_for_display(data)
    with Image.open(io.BytesIO(result)) as out:
        width, height = out.size
    original_ratio = 2784 / 2080
    new_ratio = width / height
    assert abs(original_ratio - new_ratio) < 0.01
    assert max(width, height) <= MAX_DIMENSION


def test_exactly_at_max_dimension_is_untouched():
    data = _make_image(MAX_DIMENSION, 900)
    assert fit_for_display(data) == data


def test_one_pixel_over_max_dimension_is_resized():
    data = _make_image(MAX_DIMENSION + 1, 900)
    result = fit_for_display(data)
    with Image.open(io.BytesIO(result)) as out:
        assert max(out.size) == MAX_DIMENSION


def test_custom_max_dimension_is_honored():
    data = _make_image(1000, 500)
    result = fit_for_display(data, max_dimension=400)
    with Image.open(io.BytesIO(result)) as out:
        assert max(out.size) == 400


def test_exif_orientation_is_corrected_even_when_size_already_fits():
    # Orientation 6 = "rotate 90 CW to correct" -- a 100x50 raw image with
    # this tag is really a 50x100 portrait photo once corrected.
    exif = Image.Exif()
    exif[0x0112] = 6
    data = _make_image(100, 50, fmt="JPEG", exif=exif)
    result = fit_for_display(data)
    with Image.open(io.BytesIO(result)) as out:
        assert out.size == (50, 100)


def test_exif_corrected_image_is_reencoded_not_returned_unchanged():
    exif = Image.Exif()
    exif[0x0112] = 6
    data = _make_image(100, 50, fmt="JPEG", exif=exif)
    # The raw bytes still say 100x50 (orientation tag aside); fit_for_display
    # must not just pass them through, or the sideways photo ships as-is.
    assert fit_for_display(data) != data


def test_result_is_a_valid_reopenable_image():
    data = _make_image(3000, 3000)
    result = fit_for_display(data)
    with Image.open(io.BytesIO(result)) as out:
        out.load()  # raises if the re-encoded bytes are malformed
