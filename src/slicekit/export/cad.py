"""shapely -> build123d: extrude plate geometry, place it in the assembly and write STL/STEP."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from build123d import Compound, Face, Location, Plane, Solid, Vector, Wire, export_step, export_stl
from shapely.geometry import LinearRing, Polygon
from shapely.geometry.base import BaseGeometry

from ..axes import Axis
from ..geometry.shapes import polygons
from ..pipeline.progress import Progress, track
from .formats import EXPORT_FORMATS, ExportFormat

if TYPE_CHECKING:
    from ..pipeline.model import Kit

log = logging.getLogger(__name__)

# Local x and extrusion direction per plate normal, chosen so local (x, y) = plate (u, v).
_PLANE_DIRS: dict[Axis, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "z": ((1, 0, 0), (0, 0, 1)),
    "y": ((1, 0, 0), (0, -1, 0)),
    "x": ((0, 1, 0), (1, 0, 0)),
}


def polygon_face(poly: Polygon) -> Face:
    """Planar build123d face on XY from a shapely polygon, holes included.

    Args:
        poly: Polygon in plate (u, v) coordinates, mm.

    Returns:
        The face, with u along X and v along Y.
    """

    def wire(ring: LinearRing) -> Wire:
        return Wire.make_polygon([Vector(x, y, 0) for x, y in ring.coords[:-1]], close=True)

    return Face(wire(poly.exterior), [wire(r) for r in poly.interiors])


def extrude_flat(geom: BaseGeometry, thickness: float) -> Compound:
    """Extrude plate geometry into solids lying flat on XY, ready to print or cut.

    Args:
        geom: Plate geometry (Polygon or MultiPolygon) in its (u, v) frame.
        thickness: Extrusion height in mm (z from 0 to ``thickness``).

    Returns:
        One solid per polygon, as a compound.
    """
    solids = [Solid.extrude(polygon_face(p), Vector(0, 0, thickness)) for p in polygons(geom)]
    return Compound(solids)


def plate_plane(normal: Axis, position: float, thickness: float) -> Plane:
    """Plane that maps a flat plate onto its place in the assembled model.

    The plane's local X/Y match the plate's (u, v) axes and its normal points so that
    the extruded thickness is centred on ``position``.

    Args:
        normal: Plate normal.
        position: Plate centre along ``normal`` in mm.
        thickness: Plate thickness in mm.

    Returns:
        The placement plane.
    """
    x_dir, z_dir = _PLANE_DIRS[normal]
    axis = [0.0, 0.0, 0.0]
    axis["xyz".index(normal)] = position
    origin = Vector(*axis) - Vector(*z_dir) * (thickness / 2)
    return Plane(origin=origin, x_dir=x_dir, z_dir=z_dir)


def place(flat: Compound, normal: Axis, position: float, thickness: float) -> Compound:
    """Move a flat plate (from ``extrude_flat``) to its place in the model.

    Args:
        flat: Plate lying on XY.
        normal: Plate normal.
        position: Plate centre along ``normal`` in mm.
        thickness: Plate thickness in mm.

    Returns:
        The placed plate.
    """
    return flat.moved(Location(plate_plane(normal, position, thickness)))


def assemble(kit: Kit) -> Compound:
    """All plates of a kit moved to their place in the model, as one compound.

    Args:
        kit: The built kit.

    Returns:
        The assembly (e.g. for ``ocp_vscode.show``).
    """
    t = kit.params.thickness
    return Compound([place(p.flat(t), p.normal, p.position, t) for p in kit.plates])


def export_kit(
    kit: Kit, out_dir: str | Path, formats: Sequence[ExportFormat] = EXPORT_FORMATS, progress: Progress | None = None
) -> Path:
    """Export every plate flat (``plates/<name>.<ext>``) and the assembled model (``assembly.<ext>``).

    Takes about 3 s per plate.

    Args:
        kit: The built kit.
        out_dir: Output folder (created if missing).
        formats: File formats to write.
        progress: Optional progress wrapper such as ``rich.progress.track``.

    Returns:
        ``out_dir`` as a Path.
    """
    out = Path(out_dir)
    (out / "plates").mkdir(parents=True, exist_ok=True)
    t = kit.params.thickness
    placed = []
    for plate in track(kit.plates, "Exporting plates", progress):
        flat = plate.flat(t)
        placed.append(place(flat, plate.normal, plate.position, t))
        _write(flat, out / "plates" / plate.name, formats)
    _write(Compound(placed), out / "assembly", formats)
    log.info("Wrote %d plates to %s", len(kit.plates), out)
    return out


def _write(shape: Compound, stem: Path, formats: Sequence[ExportFormat]) -> None:
    """Write ``shape`` as ``stem.stl`` and/or ``stem.step``."""
    if "stl" in formats:
        export_stl(shape, str(stem.with_suffix(".stl")))
    if "step" in formats:
        export_step(shape, str(stem.with_suffix(".step")))
