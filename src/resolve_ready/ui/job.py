"""Queue row model."""

from __future__ import annotations

from pathlib import Path

from gi.repository import GObject

from ..core.probe import Compatibility, MediaInfo


class JobItem(GObject.Object):
    """One source file in the conversion queue."""

    __gtype_name__ = "ResolveReadyJob"

    name = GObject.Property(type=str, default="")
    duration = GObject.Property(type=str, default="—")
    source = GObject.Property(type=str, default="")
    status = GObject.Property(type=str, default="Scanning…")
    progress = GObject.Property(type=float, default=0.0)
    state = GObject.Property(type=str, default="scanning")

    def __init__(self, path: Path, base_root: Path, rel_dir: Path) -> None:
        super().__init__()
        self.path = Path(path)
        self.base_root = Path(base_root)
        self.rel_dir = Path(rel_dir)
        self.info: MediaInfo | None = None
        self.compat: Compatibility | None = None
        self.dst: Path | None = None
        self.removed = False

        relative = self.rel_dir / self.path.name
        if str(self.rel_dir) in ("", "."):
            self.name = self.path.name
        else:
            self.name = relative.as_posix()

    @property
    def needs_conversion(self) -> bool:
        return self.info is not None and (self.compat is None or not self.compat.ready)

    @property
    def reasons_text(self) -> str:
        if self.compat and self.compat.reasons:
            return "\n".join(self.compat.reasons)
        return ""
