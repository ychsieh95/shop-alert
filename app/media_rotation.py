"""Rotate uploaded evidence while preserving its public file format."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence

from .media_files import make_media_file_readable


VALID_ROTATIONS = {0, 90, 180, 270}


class MediaRotationError(RuntimeError):
    """Raised when an uploaded file cannot be rotated safely."""


def parse_rotation(value: object) -> int | None:
    """Return a supported clockwise rotation, or ``None`` for invalid input."""

    try:
        rotation = int(str(value))
    except (TypeError, ValueError):
        return None
    return rotation if rotation in VALID_ROTATIONS else None


def _temporary_path(path: Path) -> Path:
    handle, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}-rotating-",
        suffix=path.suffix,
    )
    os.close(handle)
    return Path(name)


def _rotate_image(path: Path, rotation: int) -> None:
    temporary_path = _temporary_path(path)
    try:
        with Image.open(path) as source:
            image_format = source.format
            frames = [
                ImageOps.exif_transpose(frame.copy()).rotate(-rotation, expand=True)
                for frame in ImageSequence.Iterator(source)
            ]
            if not frames:
                raise MediaRotationError("The image contains no readable frames.")

            save_options: dict[str, object] = {}
            if len(frames) > 1:
                save_options.update(
                    save_all=True,
                    append_images=frames[1:],
                    loop=source.info.get("loop", 0),
                    duration=source.info.get("duration", 0),
                )
            if image_format == "JPEG":
                frames[0] = frames[0].convert("RGB")
                save_options.update(quality=95, optimize=True)

            frames[0].save(temporary_path, format=image_format, **save_options)
        make_media_file_readable(temporary_path)
        os.replace(temporary_path, path)
    except Exception as error:
        temporary_path.unlink(missing_ok=True)
        if isinstance(error, MediaRotationError):
            raise
        raise MediaRotationError("The image could not be rotated.") from error


def _rotate_video(path: Path, rotation: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise MediaRotationError("Video rotation requires FFmpeg.")

    video_filter = {
        90: "transpose=clock",
        180: "hflip,vflip",
        270: "transpose=cclock",
    }[rotation]
    temporary_path = _temporary_path(path)
    try:
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-vf",
                video_filter,
                "-metadata:s:v:0",
                "rotate=0",
                "-c:a",
                "copy",
                "-y",
                str(temporary_path),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        make_media_file_readable(temporary_path)
        os.replace(temporary_path, path)
    except (OSError, subprocess.SubprocessError) as error:
        temporary_path.unlink(missing_ok=True)
        raise MediaRotationError("The video could not be rotated.") from error


def rotate_media_file(path: Path, media_type: str, rotation: int) -> None:
    """Rotate one stored upload clockwise by 90, 180, or 270 degrees."""

    if rotation not in VALID_ROTATIONS:
        raise ValueError("Unsupported media rotation.")
    if rotation == 0:
        return
    if media_type == "image":
        _rotate_image(path, rotation)
        return
    if media_type == "video":
        _rotate_video(path, rotation)
        return
    raise ValueError("Unsupported media type.")
