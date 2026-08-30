"""Shared filesystem permissions for publicly served media files."""

from __future__ import annotations

import stat
from pathlib import Path


SHARED_FILE_MODE = 0o644


def make_media_file_readable(path: Path) -> None:
    """Give the owner write access and every deployment user read access."""

    path.chmod(SHARED_FILE_MODE)


def repair_media_folder_permissions(folder: Path) -> list[Path]:
    """Add missing read bits to existing files and return any failures."""

    failures = []
    for path in folder.iterdir():
        if not path.is_file():
            continue
        try:
            current_mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(current_mode | stat.S_IRGRP | stat.S_IROTH)
        except OSError:
            failures.append(path)
    return failures
