"""Archive backup helpers."""

from __future__ import annotations

import tarfile
from pathlib import Path


def create_backup(root: Path, files: list[Path], dest: Path) -> int:
    """Write a tar archive of the original files and verify its contents."""
    root = Path(root)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    part.unlink(missing_ok=True)

    try:
        with tarfile.open(part, "w") as archive:
            for path in files:
                try:
                    arcname = path.relative_to(root)
                except ValueError:
                    arcname = Path(path.name)
                archive.add(path, arcname=str(arcname))

        with tarfile.open(part, "r") as archive:
            count = sum(1 for member in archive.getmembers() if member.isfile())
        if count < len(files):
            raise OSError(f"backup contains {count} files, expected {len(files)}")
        part.replace(dest)
        return count
    except Exception:
        part.unlink(missing_ok=True)
        raise
