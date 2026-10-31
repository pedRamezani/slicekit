"""Volume preparation: isotropic resampling and body segmentation."""

from __future__ import annotations

from typing import cast

import numpy as np
from scipy import ndimage

from ..arrays import Array
from .dicom import Volume


def resample(volume: Volume, voxel_size: float, scale: float = 1.0) -> Volume:
    """Scale the volume to printed size and resample it to isotropic voxels.

    Scaling here means every later length (thickness, cells, tolerances) is in
    printed millimetres.

    Args:
        volume: Volume at scanner size.
        voxel_size: Edge length in mm of the resampled (printed-size) voxels.
        scale: Model scale, e.g. 0.4 prints the body at 40 %.

    Returns:
        Volume with spacing ``(voxel_size,) * 3`` and a scaled origin.
    """
    factors = [s * scale / voxel_size for s in volume.spacing]
    hu = volume.hu if np.allclose(factors, 1.0) else ndimage.zoom(volume.hu, factors, order=1, mode="nearest")
    z, y, x = (o * scale for o in volume.origin)
    return Volume(hu, (voxel_size, voxel_size, voxel_size), (z, y, x))


def body_mask(volume: Volume, threshold: float = -400.0, opening: float = 1.0) -> Array:
    """Mask of the body: threshold, keep the largest component, fill internal air.

    Args:
        volume: Isotropic volume in HU.
        threshold: HU above which a voxel counts as body (skin/air boundary is ~-400 HU).
        opening: Morphological opening in mm, which detaches thin structures such as the
            scanner table or blankets before the largest connected component is picked.

    Returns:
        Boolean mask with the volume's shape. Lungs and bowel gas are filled slice by
        slice, so the mask is bounded by the skin.

    Raises:
        ValueError: No voxel is above ``threshold``.
    """
    mask = volume.hu > threshold
    iterations = round(opening / volume.spacing[0])
    if iterations > 0:
        mask = ndimage.binary_opening(mask, iterations=iterations)

    # Without ``output`` this is always (labels, count); scipy-stubs < 1.16 type it as a union with int.
    labels, count = cast("tuple[Array, int]", ndimage.label(mask))
    if count == 0:
        raise ValueError(f"No voxels above {threshold} HU")
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    mask = labels == sizes.argmax()

    # Lungs and bowel gas are open to the outside in 3D, so fill per axial slice.
    for k in range(mask.shape[0]):
        mask[k] = ndimage.binary_fill_holes(mask[k])
    return np.asarray(mask, dtype=bool)


def crop_and_center(volume: Volume, mask: Array, margin: float = 2.0) -> tuple[Volume, Array]:
    """Crop the volume and mask to the mask's bounding box and centre it on the origin.

    Args:
        volume: Volume to crop.
        mask: Body mask with the volume's shape.
        margin: Extra space in mm kept around the bounding box.

    Returns:
        The cropped volume (origin chosen so its centre is at 0, 0, 0) and the cropped mask.
    """
    slices = []
    for axis in range(3):
        occupied = np.flatnonzero(mask.any(axis=tuple(a for a in range(3) if a != axis)))
        pad = int(np.ceil(margin / volume.spacing[axis]))
        slices.append(slice(max(occupied[0] - pad, 0), min(occupied[-1] + pad + 1, mask.shape[axis])))
    bounds = tuple(slices)
    hu, mask = volume.hu[bounds], mask[bounds]
    z, y, x = (-(n - 1) * s / 2 for n, s in zip(hu.shape, volume.spacing, strict=False))
    return Volume(hu, volume.spacing, (z, y, x)), mask
