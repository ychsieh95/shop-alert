"""Cached, downscaled copies of uploaded images for list and gallery views.

Report cards only need a small cover image, so serving the original upload makes
listings far heavier than they have to be. Each thumbnail is generated once, on
first request, and reused from the instance folder afterwards.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps


# Cards render the cover in a 218 px tall box, so this bounding box still looks
# sharp on high-density screens while staying a fraction of the upload's size.
THUMBNAIL_BOX = (720, 720)
THUMBNAIL_QUALITY = 78
THUMBNAIL_SUFFIX = ".webp"
THUMBNAIL_MIME_TYPE = "image/webp"


class ThumbnailError(RuntimeError):
    """Raised when a stored upload cannot be turned into a thumbnail."""


def thumbnail_folder() -> Path:
    return Path(current_app.config["THUMBNAIL_FOLDER"])


def thumbnail_path(stored_name: str) -> Path:
    """Return the cache path for an upload's thumbnail.

    Stored names are random and never reused, so the name alone is a safe key.
    """

    return thumbnail_folder() / f"{Path(stored_name).stem}{THUMBNAIL_SUFFIX}"


def _write_thumbnail(source: Path, target: Path) -> None:
    with Image.open(source) as image:
        # Phone photos carry their rotation in EXIF rather than in the pixels.
        frame = ImageOps.exif_transpose(image)
        frame = frame.convert("RGBA" if frame.mode in ("LA", "P", "RGBA") else "RGB")
        frame.thumbnail(THUMBNAIL_BOX, Image.LANCZOS)
        handle, temporary_name = tempfile.mkstemp(
            dir=target.parent, suffix=THUMBNAIL_SUFFIX
        )
        os.close(handle)
        temporary_path = Path(temporary_name)
        try:
            frame.save(temporary_path, format="WEBP", quality=THUMBNAIL_QUALITY)
            # Replacing atomically keeps concurrent requests from reading a
            # half-written file.
            os.replace(temporary_path, target)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise


def ensure_thumbnail(stored_name: str) -> Path:
    """Return the thumbnail for an upload, generating it when it is missing."""

    target = thumbnail_path(stored_name)
    if target.exists():
        return target

    source = Path(current_app.config["UPLOAD_FOLDER"]) / stored_name
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_thumbnail(source, target)
    except Exception as error:  # Unreadable, unsupported, or oversized images.
        raise ThumbnailError(f"Could not create a thumbnail for {stored_name}") from error
    return target


def discard_thumbnail(stored_name: str) -> None:
    """Remove a cached thumbnail whose upload is gone."""

    try:
        thumbnail_path(stored_name).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Could not remove thumbnail for %s", stored_name)
