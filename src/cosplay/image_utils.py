"""Make an image fit for inline display in a GitHub gist.

GitHub's gist file viewer renders an attached image at its native pixel
size -- confirmed live against a real gist: a 2784x2080 phone photo
rendered full-size, overflowing the viewport with scrollbars, no
responsive scaling applied at all. This module downscales anything over a
reasonable display size before it's saved or published, so the gist (and
the local copy under the run's output directory) never carries an
oversized image in the first place.

While already decoding the image to check its size, this also corrects
EXIF orientation (`ImageOps.exif_transpose`) -- phone photos routinely
carry a rotation tag that most simple viewers, GitHub's gist preview
included, display sideways/upside-down if it's never applied.
"""

import io

from PIL import Image, ImageOps

#: Longest edge, in pixels, an image is allowed to keep. Generously sized
#: for a gist viewed on an ordinary screen -- large enough that a resized
#: photo still looks sharp, small enough that it only ever needs to scroll
#: vertically on a typical window, never both directions.
MAX_DIMENSION = 1600

#: JPEG re-encode quality when a resize actually happens. Not used when no
#: resize is needed -- the original bytes pass through untouched.
_JPEG_QUALITY = 88


def fit_for_display(data: bytes, *, max_dimension: int = MAX_DIMENSION) -> bytes:
    """Return `data` unchanged if it already fits, otherwise a resized copy.

    Checks the EXIF Orientation tag's actual value (not whether
    `ImageOps.exif_transpose` returned a different object -- it always
    does, a defensive copy regardless of whether any correction was
    needed, so that can't be used to detect "no correction needed").
    Downscales only if the long edge, post-correction, exceeds
    `max_dimension` -- aspect ratio is preserved. A corrected-orientation
    image that already fits size-wise is still re-encoded, since
    "unchanged bytes" would mean "still sideways."

    Args:
        data: The source image's raw bytes (any Pillow-readable format).
        max_dimension: The longest edge, in pixels, the result may have.

    Returns:
        The original `data` unchanged if orientation was already normal
        (no EXIF Orientation tag, or tag value `1`) and both dimensions
        were already within `max_dimension`; otherwise a re-encoded copy
        (JPEG, EXIF orientation applied, downscaled if it was oversized).
    """
    with Image.open(io.BytesIO(data)) as img:
        orientation = img.getexif().get(0x0112, 1)
        needs_rotation = orientation != 1
        oriented = ImageOps.exif_transpose(img) if needs_rotation else img
        width, height = oriented.size

        if not needs_rotation and width <= max_dimension and height <= max_dimension:
            return data

        if width > max_dimension or height > max_dimension:
            scale = max_dimension / max(width, height)
            new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
            oriented = oriented.resize(new_size, Image.Resampling.LANCZOS)

        out = io.BytesIO()
        oriented.convert("RGB").save(out, format="JPEG", quality=_JPEG_QUALITY)
        return out.getvalue()
