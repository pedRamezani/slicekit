"""Plate placement: evenly pitched interlocking plates, or a gapless stack of slices."""

from __future__ import annotations

import numpy as np

from ..axes import AXIS_INDEX, Axis
from ..imaging.dicom import Volume
from .params import KitParams


def plate_positions(volume: Volume, mask: np.ndarray, normal: Axis, params: KitParams) -> np.ndarray:
    """Interlocking plate centres along one axis, evenly pitched and centred on the body.

    Args:
        volume: Prepared volume.
        mask: Body mask.
        normal: Axis the plates are stacked along.
        params: Uses ``plate_pitch`` (thickness + gap).

    Returns:
        Plate centre positions in mm (at least one).
    """
    axis = AXIS_INDEX[normal]
    occupied = np.flatnonzero(mask.any(axis=tuple(a for a in range(3) if a != axis)))
    lo, hi = volume.coords(axis)[[occupied[0], occupied[-1]]]
    count = max(int((hi - lo + params.gap) // params.plate_pitch), 1)
    return np.asarray((lo + hi) / 2 + (np.arange(count) - (count - 1) / 2) * params.plate_pitch)


def stack_positions(volume: Volume, mask: np.ndarray, normal: Axis, thickness: float) -> np.ndarray:
    """Slice centres for a gapless stack along one axis, covering the whole body.

    Args:
        volume: Prepared volume.
        mask: Body mask.
        normal: Axis the slices are stacked along.
        thickness: Slice thickness, which is also the pitch, in mm.

    Returns:
        Slice centre positions in mm.
    """
    axis = AXIS_INDEX[normal]
    occupied = np.flatnonzero(mask.any(axis=tuple(a for a in range(3) if a != axis)))
    lo, hi = volume.coords(axis)[[occupied[0], occupied[-1]]]
    count = int(np.ceil((hi - lo + volume.spacing[axis]) / thickness))
    return np.asarray((lo + hi) / 2 + (np.arange(count) - (count - 1) / 2) * thickness)
