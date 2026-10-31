"""Result types: plates (2D geometry + placement) and the kit that holds them.

The CAD and PNG output lives in ``export``; the methods here are shortcuts to it.
build123d (OCP) takes seconds to import, so it is only loaded for CAD output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from shapely.geometry.base import BaseGeometry

from ..arrays import Array
from ..axes import Axis
from ..export.formats import EXPORT_FORMATS, ExportFormat
from ..geometry.sections import Section
from ..imaging.dicom import Volume
from .params import KitParams
from .progress import Progress

if TYPE_CHECKING:
    from build123d import Compound


@dataclass
class Plate:
    """One plate: its 2D geometry in the plate's (u, v) frame and where it sits in the model.

    Attributes:
        name: Normal axis and index, e.g. ``"Z03"``; also the export file name.
        normal: Plate normal (``x``, ``y`` or ``z``).
        position: Plate centre along ``normal`` in printed mm.
        section: Volume sampled on the plate (HU and body mask).
        outline: Body outline, with slots cut in the interlocking layout.
        geometry: Outline with the infill holes, once infill has run.
    """

    name: str
    normal: Axis
    position: float
    section: Section
    outline: BaseGeometry
    geometry: BaseGeometry | None = None

    def flat(self, thickness: float) -> Compound:
        """Solid lying flat on XY (z from 0 to ``thickness``), ready to print or cut.

        Loads build123d on first use.

        Args:
            thickness: Plate thickness in mm.

        Returns:
            The extruded plate (the infill geometry if present, else the outline).
        """
        from ..export import cad

        return cad.extrude_flat(self.geometry if self.geometry is not None else self.outline, thickness)


@dataclass
class Kit:
    """A built kit: its plates (interlocking or a slice stack) and what they were made from.

    Attributes:
        params: Parameters the kit was built with.
        volume: Prepared (scaled, isotropic, cropped) volume.
        mask: Body mask of ``volume``.
        plates: All plates; when interlocking, the first family followed by the second.
    """

    params: KitParams
    volume: Volume
    mask: Array
    plates: list[Plate]

    def flat_solids(self) -> dict[str, Compound]:
        """Every plate as a flat solid, keyed by plate name."""
        return {p.name: p.flat(self.params.thickness) for p in self.plates}

    def assembled(self) -> Compound:
        """All plates moved to their place in the model, as one compound (e.g. for ``show``)."""
        from ..export.cad import assemble

        return assemble(self)

    def preview(self, path: str | Path, px_per_mm: float = 4.0) -> Path:
        """Write a PNG contact sheet of all plates; fast, no CAD involved.

        Args:
            path: PNG file to write (parent folders are created).
            px_per_mm: Resolution of the drawing.

        Returns:
            ``path``.
        """
        from ..export.preview import contact_sheet

        return contact_sheet(self, path, px_per_mm)

    def export(
        self, out_dir: str | Path, formats: tuple[ExportFormat, ...] = EXPORT_FORMATS, progress: Progress | None = None
    ) -> Path:
        """Export every plate flat and the assembled model (see ``export.cad.export_kit``).

        Args:
            out_dir: Output folder (created if missing).
            formats: File formats to write.
            progress: Optional progress wrapper such as ``rich.progress.track``.

        Returns:
            ``out_dir`` as a Path.
        """
        from ..export.cad import export_kit

        return export_kit(self, out_dir, formats, progress)
