"""CAD file formats (kept apart from ``cad`` so choosing a format does not load build123d)."""

from __future__ import annotations

from typing import Literal, get_args

ExportFormat = Literal["stl", "step"]


EXPORT_FORMATS: tuple[ExportFormat, ...] = get_args(ExportFormat)
