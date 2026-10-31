"""Plate sections: the volume sampled on one plate and its body outline.

Each plate lives in its own (u, v) frame, the two world axes it spans (``axes.PLATE_AXES``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import reduce

import numpy as np
import shapely
from scipy import ndimage
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from skimage import measure

from ..axes import AXIS_INDEX, PLATE_AXES, Axis
from ..imaging.dicom import Volume
from .shapes import keep_polygons

# scikit-image publishes no types; this is the one function we use from it.
_find_contours: Callable[[np.ndarray, float], list[np.ndarray]] = measure.find_contours


@dataclass
class Section:
    """Volume sampled on one plate, in the plate's (u, v) frame.

    Attributes:
        hu: Mean HU through the plate thickness, indexed ``[u, v]``.
        mask: Body mask on the plate's mid-plane, indexed ``[u, v]``.
        u0: u coordinate in mm of pixel ``[0, 0]``.
        v0: v coordinate in mm of pixel ``[0, 0]``.
        step: Pixel pitch in mm (the isotropic voxel size).
    """

    hu: np.ndarray
    mask: np.ndarray
    u0: float
    v0: float
    step: float


def take_section(volume: Volume, mask: np.ndarray, normal: Axis, position: float, thickness: float) -> Section | None:
    """Sample the volume on one plate.

    Args:
        volume: Isotropic volume (see ``imaging.segment.resample``).
        mask: Body mask with the volume's shape.
        normal: Plate normal; the plate spans the other two axes (``PLATE_AXES``).
        position: Plate centre along ``normal`` in mm.
        thickness: Plate thickness in mm; HU are averaged through it.

    Returns:
        The section, or None if the plate lies outside the volume or misses the body.

    Raises:
        ValueError: The volume is not isotropic.
    """
    if not np.allclose(volume.spacing, volume.spacing[0]):
        raise ValueError("take_section needs an isotropic volume; resample first")
    axis = AXIS_INDEX[normal]
    step = volume.spacing[axis]
    centre = round((position - volume.origin[axis]) / step)
    if not 0 <= centre < volume.shape[axis]:
        return None
    half = round(thickness / 2 / step)
    slab = range(max(centre - half, 0), min(centre + half + 1, volume.shape[axis]))

    # Remaining array axes are in (z, y, x) order; plate (u, v) is the reverse.
    hu = volume.hu.take(slab, axis=axis).mean(axis=axis, dtype=np.float32).T
    plate_mask = mask.take(centre, axis=axis).T
    if not plate_mask.any():
        return None
    u, v = PLATE_AXES[normal]
    return Section(hu, plate_mask, volume.origin[AXIS_INDEX[u]], volume.origin[AXIS_INDEX[v]], step)


def mask_outline(section: Section, smooth: float = 1.0, simplify: float = 0.1, min_area: float = 4.0) -> BaseGeometry:
    """Polygonal outline of a section's body mask, with internal cavities filled.

    Args:
        section: Section to outline.
        smooth: Gaussian sigma in pixels applied to the mask before contouring.
        simplify: Douglas-Peucker tolerance in mm; 0 keeps every contour point.
        min_area: Islands smaller than this (mm²) are dropped.

    Returns:
        A Polygon or MultiPolygon in the plate's (u, v) frame, possibly empty.
    """
    filled = np.pad(ndimage.binary_fill_holes(section.mask).astype(np.float32), 1)
    if smooth > 0:
        filled = ndimage.gaussian_filter(filled, smooth)

    rings = []
    for contour in _find_contours(filled, 0.5):
        if len(contour) < 4:
            continue
        pts = np.column_stack([
            section.u0 + (contour[:, 0] - 1) * section.step,
            section.v0 + (contour[:, 1] - 1) * section.step,
        ])
        rings.append(shapely.make_valid(Polygon(pts)))
    # Even-odd fill: XOR of all rings resolves islands and holes without nesting logic.
    empty: BaseGeometry = Polygon()
    outline = reduce(lambda a, b: a.symmetric_difference(b), rings, empty)
    if simplify > 0:
        outline = outline.simplify(simplify)
    return keep_polygons(outline, min_area)
