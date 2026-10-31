"""Load a CT DICOM series into a Hounsfield-unit volume."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
from pydicom.errors import InvalidDicomError

from ..arrays import Array

log = logging.getLogger(__name__)


@dataclass
class Volume:
    """CT volume in Hounsfield units.

    The frame is the scanner voxel frame (DICOM LPS for axial scans).

    Attributes:
        hu: Voxel values in HU, indexed ``[z, y, x]``.
        spacing: Voxel size in mm, in (z, y, x) order.
        origin: Position in mm of the centre of voxel ``[0, 0, 0]``, in (z, y, x) order.
    """

    hu: Array
    spacing: tuple[float, float, float]
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def shape(self) -> tuple[int, int, int]:
        """Number of voxels along (z, y, x)."""
        z, y, x = self.hu.shape
        return z, y, x

    def coords(self, axis: int) -> Array:
        """World coordinates of the voxel centres along one array axis.

        Args:
            axis: Array axis: 0 = z, 1 = y, 2 = x.

        Returns:
            Coordinates in mm, one per voxel along that axis.
        """
        return self.origin[axis] + np.arange(self.hu.shape[axis]) * self.spacing[axis]


def load_series(path: str | Path, series_uid: str | None = None) -> Volume:
    """Read a folder of single-frame CT slices, or one multi-frame file.

    Files that are not DICOM images are skipped; slices are sorted by their position
    along the slice normal and converted to HU with the rescale slope and intercept.

    Args:
        path: Folder searched recursively for DICOM files, or a single multi-frame file.
        series_uid: SeriesInstanceUID to load when the folder holds several series.
            By default the series with the most images is used.

    Returns:
        The volume in HU with its spacing and origin.

    Raises:
        FileNotFoundError: No DICOM image was found under ``path``.
        KeyError: ``series_uid`` is not among the series found.
        ValueError: Two slices share a position (several acquisitions mixed in one series).
    """
    path = Path(path)
    series = scan_series(path)
    if not series:
        raise FileNotFoundError(f"No DICOM images found in {path}")

    if series_uid is None:
        series_uid = _largest(series)
        if len(series) > 1:
            log.warning(
                "%d series found, using %s (%d images); pass series_uid to choose another",
                len(series),
                series_uid,
                len(series[series_uid]),
            )
    elif series_uid not in series:
        raise KeyError(f"Series {series_uid} not found; available: {list(series)}")

    members = series[series_uid]
    if len(members) == 1 and int(members[0][1].get("NumberOfFrames", 1)) > 1:
        return _load_multiframe(members[0][0])
    return _load_single_frames(members)


Headers = dict[str, list[tuple[Path, pydicom.Dataset]]]
"""DICOM image headers grouped by SeriesInstanceUID."""

# Tags needed to group, describe and sort images; reading only these keeps scans fast.
_SCAN_TAGS = [
    "SeriesInstanceUID",
    "Modality",
    "BodyPartExamined",
    "SeriesDescription",
    "Rows",
    "Columns",
    "NumberOfFrames",
]


def _files_under(path: Path) -> list[Path]:
    return [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())


def _read_headers(files: Iterable[Path], tags: list[str] | None = None) -> Headers:
    """Headers of the DICOM images among ``files``; other files are skipped."""
    series: Headers = defaultdict(list)
    for f in files:
        try:
            ds = pydicom.dcmread(f, stop_before_pixels=True, specific_tags=tags)
        except (InvalidDicomError, OSError):
            continue
        if "Rows" in ds:  # an image, not e.g. a DICOMDIR or structured report
            series[str(ds.get("SeriesInstanceUID", ""))].append((f, ds))
    return dict(series)


def _largest(series: Headers) -> str:
    """UID of the series with the most images (what ``load_series`` picks by default)."""
    return max(series, key=lambda uid: len(series[uid]))


def scan_series(path: str | Path) -> Headers:
    """Read the headers of all DICOM images under ``path``, grouped by series.

    DICOM files are recognised by their content, not their extension, so files without
    a ``.dcm`` suffix (common in scanner and PACS exports) are found too.

    Args:
        path: Folder (searched recursively) or a single file.

    Returns:
        Headers (without pixel data) per SeriesInstanceUID; empty if there are none.
    """
    return _read_headers(_files_under(Path(path)))


@dataclass(frozen=True)
class SeriesInfo:
    """Summary of one series, read from its headers only.

    Attributes:
        uid: SeriesInstanceUID.
        folder: Folder the series was found in.
        images: Number of image files (a multi-frame file counts once).
        modality: e.g. ``"CT"``.
        body_part: BodyPartExamined, e.g. ``"CHEST"``; empty if not set.
        rows: Image height in pixels.
        columns: Image width in pixels.
        description: SeriesDescription; empty if not set.
    """

    uid: str
    folder: Path
    images: int
    modality: str
    body_part: str
    rows: int
    columns: int
    description: str

    @classmethod
    def from_headers(cls, uid: str, members: list[tuple[Path, pydicom.Dataset]], folder: Path) -> SeriesInfo:
        """Summarise one series from its image headers.

        Args:
            uid: SeriesInstanceUID.
            members: (file, header) pairs of the series' images.
            folder: Folder to report the series in.

        Returns:
            The summary, taken from the first header.
        """
        ds = members[0][1]
        return cls(
            uid=uid,
            folder=folder,
            images=len(members),
            modality=str(ds.get("Modality", "")),
            body_part=str(ds.get("BodyPartExamined", "")),
            rows=int(ds.get("Rows", 0)),
            columns=int(ds.get("Columns", 0)),
            description=str(ds.get("SeriesDescription", "")),
        )

    def summary(self) -> str:
        """One line such as ``CT | CHEST | 147 images | 512x512 | Lung 1.25mm``."""
        parts = [
            self.modality,
            self.body_part,
            f"{self.images} images",
            f"{self.rows}x{self.columns}",
            self.description,
        ]
        return " | ".join(p for p in parts if p)


def series_info(path: str | Path) -> list[SeriesInfo]:
    """Summaries of all series under ``path``, the one ``load_series`` would pick first.

    Args:
        path: Folder (searched recursively) or a single file, as for ``load_series``.

    Returns:
        One summary per series, largest first; empty if there are no DICOM images.
    """
    path = Path(path)
    series = _read_headers(_files_under(path), _SCAN_TAGS)
    folder = path if path.is_dir() else path.parent
    infos = [SeriesInfo.from_headers(uid, members, folder) for uid, members in series.items()]
    return sorted(infos, key=lambda i: -i.images)


def find_series(roots: Iterable[str | Path], max_depth: int = 4) -> list[SeriesInfo]:
    """Find series in the folders below ``roots``.

    Each folder is described by the images directly inside it. Hidden folders are
    skipped, and a folder reached from several roots is reported once.

    Args:
        roots: Folders to search; missing ones are skipped.
        max_depth: How many folder levels below each root to look.

    Returns:
        One summary per (folder, series), sorted by folder.
    """
    found: dict[tuple[Path, str], SeriesInfo] = {}
    for root in map(Path, roots):
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and depth < max_depth)
            folder = Path(dirpath).resolve()
            series = _read_headers((folder / f for f in sorted(filenames)), _SCAN_TAGS)
            for uid, members in series.items():
                found[folder, uid] = SeriesInfo.from_headers(uid, members, folder)
    return sorted(found.values(), key=lambda i: (str(i.folder), -i.images))


def _load_single_frames(members: list[tuple[Path, pydicom.Dataset]]) -> Volume:
    ref = members[0][1]
    row_cos, col_cos, normal = _orientation(ref.ImageOrientationPatient)
    members = sorted(members, key=lambda m: _project(m[1].ImagePositionPatient, normal))
    positions = np.array([_project(ds.ImagePositionPatient, normal) for _, ds in members])

    slices = []
    for f, _ in members:
        ds = pydicom.dcmread(f)
        slices.append(_to_hu(ds.pixel_array, ds.get("RescaleSlope", 1), ds.get("RescaleIntercept", 0)))
    hu = np.stack(slices)

    first = members[0][1].ImagePositionPatient
    dy, dx = (float(s) for s in ref.PixelSpacing)
    dz = _slice_spacing(positions, ref.get("SliceThickness"))
    origin = (positions[0], _project(first, col_cos), _project(first, row_cos))
    log.info("Loaded %s voxels, spacing %.3f x %.3f x %.3f mm", hu.shape, dz, dy, dx)
    return Volume(hu, (dz, dy, dx), origin)


def _load_multiframe(f: Path) -> Volume:
    ds = pydicom.dcmread(f)
    frames = ds.pixel_array
    shared = ds.SharedFunctionalGroupsSequence[0] if "SharedFunctionalGroupsSequence" in ds else None
    per_frame = ds.get("PerFrameFunctionalGroupsSequence")

    def lookup(sequence: str, attr: str, i: int, default: Any = None) -> Any:
        groups = ([per_frame[i]] if per_frame else []) + ([shared] if shared else [])
        for group in groups:
            if sequence in group and attr in group[sequence][0]:
                return group[sequence][0][attr].value
        return ds.get(attr, default)

    row_cos, col_cos, normal = _orientation(lookup("PlaneOrientationSequence", "ImageOrientationPatient", 0))
    corners = [lookup("PlanePositionSequence", "ImagePositionPatient", i) for i in range(len(frames))]
    order = np.argsort([_project(c, normal) for c in corners])

    hu = np.stack([
        _to_hu(
            frames[i],
            lookup("PixelValueTransformationSequence", "RescaleSlope", i, 1),
            lookup("PixelValueTransformationSequence", "RescaleIntercept", i, 0),
        )
        for i in order
    ])
    positions = np.array([_project(corners[i], normal) for i in order])
    dy, dx = (float(s) for s in lookup("PixelMeasuresSequence", "PixelSpacing", 0))
    dz = _slice_spacing(positions, lookup("PixelMeasuresSequence", "SliceThickness", 0))
    first = corners[order[0]]
    origin = (positions[0], _project(first, col_cos), _project(first, row_cos))
    return Volume(hu, (dz, dy, dx), origin)


def _orientation(iop: Sequence[float]) -> tuple[Array, Array, Array]:
    row_cos, col_cos = np.asarray(iop[:3], float), np.asarray(iop[3:], float)
    normal = np.cross(row_cos, col_cos)
    if max(abs(row_cos @ (1, 0, 0)), abs(col_cos @ (0, 1, 0))) < 0.99:
        log.warning("Oblique or non-axial acquisition; the kit is built in the voxel frame")
    return row_cos, col_cos, normal


def _project(position: Sequence[float], axis: Array) -> float:
    return float(np.asarray(position, float) @ axis)


def _to_hu(pixels: Array, slope: float, intercept: float) -> Array:
    hu = pixels.astype(np.float32) * float(slope) + float(intercept)
    return np.asarray(np.clip(np.rint(hu), -32768, 32767), dtype=np.int16)


def _slice_spacing(positions: Array, slice_thickness: float | None) -> float:
    if len(positions) < 2:
        return float(slice_thickness or 1.0)
    gaps = np.diff(positions)
    if np.any(gaps < 1e-3):
        raise ValueError("Duplicate slice positions; the series may hold several acquisitions")
    spacing = float(np.median(gaps))
    if np.ptp(gaps) > 0.1 * spacing:
        log.warning("Irregular slice spacing (%.3f-%.3f mm); using median %.3f mm", gaps.min(), gaps.max(), spacing)
    return spacing
