"""Find and download public CT series from the NCI Imaging Data Commons (IDC).

Needs the optional ``download`` extra (installs idc-index). The command line for this
module is ``slicekit-download`` (``cli.download``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pandas import DataFrame

log = logging.getLogger(__name__)

# Reformats, projections and scouts are not stacks of axial slices.
NOT_AXIAL = r"(?i)\b(?:cor|coronal|sag|sagit+al|mip|minip|scout|topo|localizer|survey|3d|vr)\b"

COLUMNS = [
    "SeriesInstanceUID",
    "collection_id",
    "BodyPartExamined",
    "SeriesDescription",
    "instanceCount",
    "series_size_MB",
    "license_short_name",
]


class IDCClient(Protocol):
    """The part of ``idc_index.IDCClient`` slicekit uses (idc-index publishes no types)."""

    index: DataFrame
    """One row per series in IDC (collection, modality, body part, size, licence, ...)."""

    def get_series_size(self, seriesInstanceUID: str) -> float:
        """Download size of a series in MB."""
        ...

    def download_from_selection(
        self, *, downloadDir: str, seriesInstanceUID: list[str], dirTemplate: str, dry_run: bool
    ) -> None:
        """Download the selected series into ``downloadDir`` laid out by ``dirTemplate``."""
        ...


@lru_cache(maxsize=1)
def client() -> IDCClient:
    """Shared IDC client; its index (a few hundred MB in memory) is loaded once.

    Returns:
        The cached client.

    Raises:
        ImportError: The optional ``download`` extra (idc-index) is not installed.
    """
    try:
        from idc_index import index  # IDCClient is defined here; the package root does not export it
    except ImportError as err:
        raise ImportError('Downloading needs idc-index: pip install "slicekit[download]"') from err
    factory: Callable[[], IDCClient] = index.IDCClient
    return factory()


def find_ct_series(
    collection: str | None = None,
    body_part: str | None = None,
    min_slices: int = 80,
    max_slices: int | None = None,
    max_size_mb: float | None = None,
    licenses: tuple[str, ...] | None = ("CC BY 4.0", "CC BY 3.0"),
    axial_only: bool = True,
    limit: int = 20,
) -> DataFrame:
    """CT series in IDC matching the filters, smallest first.

    Args:
        collection: IDC collection id, case-insensitive (e.g. ``"nlst"``). None = any.
        body_part: BodyPartExamined, case-insensitive (e.g. ``"CHEST"``). None = any.
        min_slices: Fewest images in the series.
        max_slices: Most images in the series. None = no limit.
        max_size_mb: Largest download size in MB. None = no limit.
        licenses: Licences to accept; None accepts all, including non-commercial ones.
        axial_only: Drop series whose description looks like a coronal/sagittal
            reformat, MIP or scout. It is a heuristic, so check the series loads as
            an axial stack.
        limit: Most rows to return.

    Returns:
        One row per series with the columns in ``COLUMNS``, sorted by size.

    Raises:
        ImportError: The optional ``download`` extra (idc-index) is not installed.
    """
    index = client().index
    rows = index[(index.Modality == "CT") & (index.instanceCount >= min_slices)]
    if collection:
        rows = rows[rows.collection_id.str.lower() == collection.lower()]
    if body_part:
        rows = rows[rows.BodyPartExamined.str.upper() == body_part.upper()]
    if max_slices:
        rows = rows[rows.instanceCount <= max_slices]
    if max_size_mb:
        rows = rows[rows.series_size_MB <= max_size_mb]
    if licenses:
        rows = rows[rows.license_short_name.isin(licenses)]
    if axial_only:
        rows = rows[~rows.SeriesDescription.fillna("").str.contains(NOT_AXIAL)]
    return rows.sort_values("series_size_MB")[COLUMNS].head(limit).reset_index(drop=True)


def download_series(series_uid: str, out_dir: str | Path = "data", dry_run: bool = False) -> Path:
    """Download one series into ``out_dir/<SeriesInstanceUID>/``.

    Already-downloaded files are skipped by idc-index, so calling this again is cheap.

    Args:
        series_uid: SeriesInstanceUID, e.g. from ``find_ct_series``.
        out_dir: Folder that receives one subfolder per series.
        dry_run: Only report the size, without downloading.

    Returns:
        The folder holding the series' DICOM files.

    Raises:
        ImportError: The optional ``download`` extra (idc-index) is not installed.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    idc = client()
    log.info("Downloading %s (%.1f MB)", series_uid, idc.get_series_size(series_uid))
    idc.download_from_selection(
        downloadDir=str(out_dir),
        seriesInstanceUID=[series_uid],
        dirTemplate="%SeriesInstanceUID",
        dry_run=dry_run,
    )
    return out_dir / series_uid
