"""Shapely helpers shared by the geometry, pipeline and output code."""

from __future__ import annotations

import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from ..axes import PLATE_AXES, Axis


def polygons(geom: BaseGeometry) -> list[Polygon]:
    """Flatten any geometry into its polygon parts.

    Args:
        geom: Polygon, MultiPolygon or GeometryCollection.

    Returns:
        The polygons; points and lines are dropped.
    """
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in polygons(g)]
    return []


def keep_polygons(geom: BaseGeometry, min_area: float) -> BaseGeometry:
    """Repair a geometry and keep only its polygons of at least ``min_area`` mm².

    Args:
        geom: Geometry, possibly invalid after boolean operations.
        min_area: Smallest polygon area to keep, in mm².

    Returns:
        A single Polygon if one part remains, otherwise a MultiPolygon (possibly empty).
    """
    parts = [p for p in polygons(shapely.make_valid(geom)) if p.area >= min_area]
    if len(parts) == 1:
        return parts[0]
    return MultiPolygon(parts)


def plate_box(normal: Axis, ranges: dict[Axis, tuple[float, float]]) -> Polygon:
    """Axis-aligned rectangle in a plate's (u, v) frame.

    Args:
        normal: Plate normal, which fixes which world axes are u and v.
        ranges: (low, high) in mm for both of the plate's world axes.

    Returns:
        The rectangle in plate coordinates.
    """
    u, v = PLATE_AXES[normal]
    (u_lo, u_hi), (v_lo, v_hi) = ranges[u], ranges[v]
    return shapely.box(u_lo, v_lo, u_hi, v_hi)
