"""Pipeline: prepare the volume, place plates (interlocking or stack), slot them and add infill."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..arrays import Array
from ..axes import Axis
from ..geometry.sections import mask_outline, take_section
from ..geometry.shapes import polygons
from ..imaging.dicom import Volume, load_series
from ..imaging.segment import body_mask, crop_and_center, resample
from ..infill import make_infill, make_tone_map
from .layout import plate_positions, stack_positions
from .model import Kit, Plate
from .params import KitParams
from .progress import Progress, track
from .slots import cut_slots

log = logging.getLogger(__name__)


def prepare_volume(volume: Volume, params: KitParams) -> tuple[Volume, Array]:
    """Scale to printed size, resample, segment the body and crop around it.

    Args:
        volume: Volume as loaded (scanner size).
        params: Uses ``scale``, ``voxel_size``, ``body_hu`` and ``thickness`` (crop margin).

    Returns:
        The prepared volume, centred on the origin, and its body mask.
    """
    volume = resample(volume, params.voxel_size, params.scale)
    mask = body_mask(volume, params.body_hu)
    return crop_and_center(volume, mask, margin=params.thickness)


def _make_plates(volume: Volume, mask: Array, normal: Axis, positions: Array, params: KitParams) -> list[Plate]:
    plates = []
    digits = max(2, len(str(len(positions) - 1)))
    for i, pos in enumerate(positions):
        section = take_section(volume, mask, normal, pos, params.thickness)
        if section is None:
            continue
        outline = mask_outline(section, params.smooth, params.simplify, params.min_area)
        if not outline.is_empty:
            plates.append(Plate(f"{normal.upper()}{i:0{digits}d}", normal, float(pos), section, outline))
    return plates


def build_kit(volume: Volume, mask: Array, params: KitParams, progress: Progress | None = None) -> Kit:
    """Build all plates from a prepared volume: place, outline, slot and fill them.

    Args:
        volume: Prepared volume (see ``prepare_volume``).
        mask: Its body mask.
        params: Layout (interlocking, or a ``stack``) and infill settings.
        progress: Optional progress wrapper such as ``rich.progress.track``.

    Returns:
        The kit, with 2D geometry only; CAD solids are made on export.
    """
    if params.stack_axis:
        positions = stack_positions(volume, mask, params.stack_axis, params.thickness)
        plates = _make_plates(volume, mask, params.stack_axis, positions, params)
        log.info("Stack: %d slices along %s", len(plates), params.stack_axis)
    else:
        families = [
            _make_plates(volume, mask, normal, plate_positions(volume, mask, normal, params), params)
            for normal in params.normals
        ]
        log.info("Plates: %d x %s, %d x %s", len(families[0]), params.normals[0], len(families[1]), params.normals[1])
        cut_slots(families[0], families[1], params)
        plates = families[0] + families[1]

    tone = make_tone_map(volume, mask, params)
    log.info("Tone: %s, HU %.0f -> open, %.0f -> solid", params.tone, tone.hu[0], tone.hu[-1])
    for index, plate in enumerate(track(plates, "Infill", progress)):
        if len(polygons(plate.outline)) > 1:
            log.warning("%s has %d separate pieces", plate.name, len(polygons(plate.outline)))
        plate.geometry = make_infill(
            plate.outline, plate.section, tone, params, np.random.default_rng([params.seed, index])
        )
    return Kit(params, volume, mask, plates)


def make_kit(dicom_path: str | Path, params: KitParams | None = None, series_uid: str | None = None) -> Kit:
    """Load a DICOM series and build the kit in one call.

    Args:
        dicom_path: Series folder or multi-frame file (see ``load_series``).
        params: Kit parameters; defaults to ``KitParams()``.
        series_uid: Series to load when the folder holds several.

    Returns:
        The built kit.
    """
    params = params or KitParams()
    volume, mask = prepare_volume(load_series(dicom_path, series_uid), params)
    return build_kit(volume, mask, params)
