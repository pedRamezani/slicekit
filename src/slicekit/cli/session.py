"""Interactive session state (selected series, parameters, cached volume and kit) and its panels."""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.progress import track

from ..arrays import Array
from ..imaging.dicom import Volume, load_series, series_info
from ..pipeline import Kit, KitParams, build_kit, prepare_volume
from .prompts import console

log = logging.getLogger(__name__)


@dataclass
class Session:
    """What the menu is working on.

    The prepared volume and the built kit are cached and rebuilt only when their
    inputs change, so switching the infill re-runs in seconds without reloading the scan.

    Attributes:
        dicom: Selected series folder, or None before one is chosen.
        series_uid: SeriesInstanceUID to load from ``dicom``; None = the largest series.
        summary: One-line description of the series for the status panel.
        params: Current parameters.
        out: Output folder for previews and exports.
    """

    dicom: Path | None = None
    series_uid: str | None = None
    summary: str = ""
    params: KitParams = field(default_factory=lambda: KitParams(scale=0.4))
    out: Path = Path("kit_out")
    _prepared: tuple[tuple[Any, ...], Volume, Array] | None = None  # (key, volume, mask)
    _built: tuple[KitParams, Kit] | None = None

    def select(self, path: Path, series_uid: str | None = None) -> None:
        """Make a series current and drop the cached volume and kit.

        Args:
            path: Series folder or file.
            series_uid: Series to use when ``path`` holds several; None = the largest.
        """
        infos = series_info(path)
        chosen = next((i for i in infos if i.uid == series_uid), infos[0] if infos else None)
        if chosen is None:
            self.summary = "no DICOM images found"
        else:
            others = len(infos) - 1
            self.summary = chosen.summary() + (f" (+{others} other series)" if others else "")
        self.dicom, self.series_uid = path, series_uid
        self._prepared = self._built = None

    def prepared(self) -> tuple[Volume, Array]:
        """Prepared volume and body mask, loaded again only if the series or scale settings changed.

        Raises:
            ValueError: No series is selected.
        """
        if self.dicom is None:
            raise ValueError("No series selected")
        p = self.params
        key = (self.dicom, self.series_uid, p.scale, p.voxel_size, p.body_hu, p.thickness)
        if not self._prepared or self._prepared[0] != key:
            with console.status("Loading and segmenting the series..."):
                volume, mask = prepare_volume(load_series(self.dicom, self.series_uid), p)
            self._prepared = (key, volume, mask)
        _, volume, mask = self._prepared
        return volume, mask

    def kit(self) -> Kit:
        """Kit for the current parameters, rebuilt only if they changed since the last build.

        Raises:
            ValueError: No series is selected.
        """
        if not self._built or self._built[0] != self.params:
            volume, mask = self.prepared()
            self._built = (dataclasses.replace(self.params), build_kit(volume, mask, self.params, progress=track))
        return self._built[1]

    @property
    def built(self) -> Kit | None:
        """The cached kit if it matches the current parameters, else None."""
        return self._built[1] if self._built and self._built[0] == self.params else None
