"""Fast PNG previews of plate geometry (no CAD), for tuning infill parameters."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import LinearRing

from ..geometry.shapes import polygons

if TYPE_CHECKING:
    from ..pipeline.model import Kit, Plate

SOLID, EMPTY = 30, 255


def render_plate(
    plate: Plate, px_per_mm: float = 4.0, bounds: tuple[float, float, float, float] | None = None
) -> Image.Image:
    """Draw one plate seen from above (u right, v up), solid dark on white.

    Args:
        plate: Plate to draw (its infill geometry if present, else its outline).
        px_per_mm: Resolution.
        bounds: (u_lo, v_lo, u_hi, v_hi) frame in mm; defaults to the plate's own bounds.
            A shared frame keeps neighbouring slices aligned.

    Returns:
        Greyscale image.
    """
    geom = plate.geometry if plate.geometry is not None else plate.outline
    u_lo, v_lo, u_hi, v_hi = bounds or geom.bounds
    size = (max(math.ceil((u_hi - u_lo) * px_per_mm), 1), max(math.ceil((v_hi - v_lo) * px_per_mm), 1))
    image = Image.new("L", size, EMPTY)
    draw = ImageDraw.Draw(image)

    def pixels(ring: LinearRing) -> list[tuple[float, float]]:
        xy = np.asarray(ring.coords)
        return [((u - u_lo) * px_per_mm, (v_hi - v) * px_per_mm) for u, v in xy]

    for poly in polygons(geom):
        draw.polygon(pixels(poly.exterior), fill=SOLID)
        for hole in poly.interiors:
            draw.polygon(pixels(hole), fill=EMPTY)
    return image


def contact_sheet(kit: Kit, path: str | Path, px_per_mm: float = 4.0, columns: int | None = None) -> Path:
    """Draw all plates on one PNG, one labelled tile per plate.

    Plates are grouped by normal, and each family shares one frame, so flipping through
    neighbouring slices keeps the anatomy aligned.

    Args:
        kit: Kit to draw.
        path: PNG file to write (parent folders are created).
        px_per_mm: Resolution of each tile.
        columns: Tiles per row; defaults to a roughly square sheet.

    Returns:
        ``path`` as a Path.
    """
    tiles = []
    for normal in dict.fromkeys(p.normal for p in kit.plates):
        group = [p for p in kit.plates if p.normal == normal]
        # One frame per family so neighbouring slices line up when flipping through them.
        bounds = np.array([p.outline.bounds for p in group])
        frame = (*bounds[:, :2].min(axis=0), *bounds[:, 2:].max(axis=0))
        tiles += [(p.name, render_plate(p, px_per_mm, frame)) for p in group]

    columns = columns or math.ceil(math.sqrt(len(tiles)))
    pad, label = 8, 14
    tile_w = max(t.width for _, t in tiles) + pad
    tile_h = max(t.height for _, t in tiles) + pad + label
    rows = math.ceil(len(tiles) / columns)
    sheet = Image.new("L", (columns * tile_w + pad, rows * tile_h + pad), 200)
    draw = ImageDraw.Draw(sheet)
    for i, (name, tile) in enumerate(tiles):
        x, y = pad + (i % columns) * tile_w, pad + (i // columns) * tile_h
        draw.text((x, y), name, fill=0)
        sheet.paste(tile, (x, y + label))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return path
