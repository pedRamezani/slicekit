"""HU-modulated infill: CT density becomes the solid fraction of the plate.

What the eye reads on a printed plate is how much of it is solid, so every mode maps a
tone t in [0, 1] (from HU, see ``ToneMap``) to a solid fraction between the thinnest
printable lattice (t = 0) and fully solid (t = 1):

- ``hex``: fixed hex grid, each hole shrinks with t (amplitude-modulated halftone).
- ``dither``: fixed hex grid, each cell is either open or solid, chosen by error
  diffusion (Floyd-Steinberg on hex neighbours; frequency-modulated halftone).
- ``lines``: engraving-style line screen, line width follows t. Every line ends on the
  solid perimeter, so the plate stays one piece; ``line_wave`` gives wavy lines.
- ``voronoi``: cell pitch shrinks with t (density-weighted centroidal Voronoi, which
  relaxes to a hex grid where t is uniform), and walls thicken with t.

Holes are always cells shrunk inside a wall band (or gaps between lines anchored to the
perimeter), so the solid stays one connected piece.

With ``perceptual`` the solid fraction is chosen so equal tone steps look like equal
lightness steps (CIE L*), instead of equal coverage steps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
import shapely
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely.geometry.base import BaseGeometry

from ..geometry.sections import Section
from .tone import ToneMap, tone_curve, tone_field

if TYPE_CHECKING:
    from ..pipeline.params import KitParams


Bounds = tuple[float, float, float, float]  # (u_lo, v_lo, u_hi, v_hi)


HEX_AREA = np.sqrt(3) / 2  # area of a hex cell with unit centre-to-centre pitch


def sample(field: np.ndarray, section: Section, points: np.ndarray) -> np.ndarray:
    """Bilinear sample of a per-pixel field at arbitrary plate coordinates.

    Args:
        field: Values indexed like ``section.hu``.
        section: Gives the pixel grid (origin and step).
        points: (N, 2) array of (u, v) positions in mm.

    Returns:
        N values; points outside the grid take the nearest edge value.
    """
    pixel = [(points[:, 0] - section.u0) / section.step, (points[:, 1] - section.v0) / section.step]
    return np.asarray(ndimage.map_coordinates(field, pixel, order=1, mode="nearest"))


# Margin so holes at f_max survive the min_hole opening despite rounding.
HOLE_MARGIN = 1.05


def hex_fraction_range(pitch: npt.ArrayLike, p: KitParams) -> tuple[np.ndarray, np.ndarray]:
    """Printable range of solid fractions for a hex lattice.

    Args:
        pitch: Hex centre-to-centre distance in mm (scalar or per cell).
        p: Parameters giving ``wall`` (thinnest wall) and ``min_hole`` (narrowest hole).

    Returns:
        ``(f_min, f_max)``: the solid fraction with the thinnest walls and with the
        smallest printable holes.
    """
    pitch = np.asarray(pitch, dtype=float)
    f_min = 1.0 - np.clip((pitch - p.wall) / pitch, 0.0, 1.0) ** 2
    f_max = 1.0 - np.clip(HOLE_MARGIN * p.min_hole / pitch, 0.0, 1.0) ** 2
    return f_min, np.maximum(f_max, f_min)


def solid_fraction(t: npt.ArrayLike, f_min: npt.ArrayLike, f_max: npt.ArrayLike, p: KitParams) -> np.ndarray:
    """Solid fraction for a tone, kept within the printable range.

    Every tone below ``p.solid_tone`` keeps visible holes; denser tissue goes solid.

    Args:
        t: Tone in [0, 1].
        f_min: Solid fraction with the thinnest walls (tone 0).
        f_max: Solid fraction with the narrowest printable holes.
        p: Parameters giving ``perceptual`` and ``solid_tone``.

    Returns:
        Solid fraction in [f_min, f_max], or 1 where the tone reaches ``solid_tone``.
    """
    coverage = tone_curve(t, p.perceptual)
    lo, hi = np.asarray(f_min, dtype=float), np.asarray(f_max, dtype=float)
    f = lo + (hi - lo) * np.clip(coverage / p.solid_tone, 0.0, 1.0)
    return np.where(coverage >= p.solid_tone, 1.0, f)


def hole_inset(pitch: npt.ArrayLike, fraction: npt.ArrayLike) -> np.ndarray:
    """How far to shrink a hex cell so the lattice reaches a solid fraction.

    Args:
        pitch: Hex centre-to-centre distance in mm.
        fraction: Wanted solid fraction in [0, 1].

    Returns:
        Inset distance in mm (half the wall width).
    """
    open_fraction = np.clip(1.0 - np.asarray(fraction, dtype=float), 0.0, 1.0)
    return np.asarray(pitch, dtype=float) / 2 * (1.0 - np.sqrt(open_fraction))


# --- cell layouts -----------------------------------------------------------------------


def hex_grid(bounds: Bounds, pitch: float) -> tuple[np.ndarray, np.ndarray]:
    """Pointy-top hex grid covering a rectangle.

    Odd rows are offset by half a pitch to the right.

    Args:
        bounds: (u_lo, v_lo, u_hi, v_hi) in mm.
        pitch: Centre-to-centre distance in mm.

    Returns:
        (N, 2) cell centres in mm and (N, 2) integer (row, col) indices.
    """
    u_lo, v_lo, u_hi, v_hi = bounds
    row_step = pitch * np.sqrt(3) / 2
    rows = np.arange(int(np.ceil((v_hi - v_lo) / row_step)) + 2)
    cols = np.arange(int(np.ceil((u_hi - u_lo) / pitch)) + 2)
    r, c = np.meshgrid(rows, cols, indexing="ij")
    u = u_lo - pitch / 2 + c * pitch + (r % 2) * pitch / 2
    v = v_lo - row_step / 2 + r * row_step
    return np.column_stack([u.ravel(), v.ravel()]), np.column_stack([r.ravel(), c.ravel()])


def hexagons(centres: np.ndarray, pitch: float) -> np.ndarray:
    """Pointy-top hexagons that tile the plane when placed on ``hex_grid`` centres.

    Args:
        centres: (N, 2) centres in mm.
        pitch: Centre-to-centre distance; the inradius is ``pitch / 2``.

    Returns:
        N shapely Polygons.
    """
    angles = np.radians(30 + 60 * np.arange(6))
    ring = (pitch / np.sqrt(3)) * np.column_stack([np.cos(angles), np.sin(angles)])
    return np.asarray(shapely.polygons(centres[:, None, :] + ring[None, :, :]))


def error_diffusion(tone: np.ndarray, index: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Binary dither of per-cell tone on a hex grid (serpentine Floyd-Steinberg).

    The quantisation error goes 1/2 to the next cell in the row and 1/4 to each of the
    two cells below, so the share of solid cells follows the local tone.

    Args:
        tone: Tone per cell in [0, 1].
        index: (N, 2) (row, col) indices from ``hex_grid``.
        threshold: Accumulated tone at or above which a cell becomes solid.

    Returns:
        Boolean per cell: True = solid.
    """
    rows, cols = index.max(axis=0) + 1
    grid = np.full((rows, cols), np.nan)
    grid[index[:, 0], index[:, 1]] = tone
    out = np.zeros_like(grid, dtype=bool)
    for r in range(rows):
        step = 1 if r % 2 == 0 else -1
        # Odd rows sit half a pitch to the right, which shifts the two cells below.
        below = (-1, 0) if r % 2 == 0 else (0, 1)
        for c in range(cols)[::step]:
            value = grid[r, c]
            if np.isnan(value):
                continue
            out[r, c] = value >= threshold
            error = value - out[r, c]
            for dr, dc, w in ((0, step, 0.5), (1, below[0], 0.25), (1, below[1], 0.25)):
                rr, cc = r + dr, c + dc
                if rr < rows and 0 <= cc < cols and not np.isnan(grid[rr, cc]):
                    grid[rr, cc] += error * w
    return np.asarray(out[index[:, 0], index[:, 1]], dtype=bool)


def relaxed_seeds(
    points: np.ndarray, size: np.ndarray, pixel_area: float, iterations: int, rng: np.random.Generator
) -> np.ndarray:
    """Seeds for a graded Voronoi tessellation (density-weighted Lloyd relaxation).

    Where ``size`` is constant the cells relax into a regular hex grid.

    Args:
        points: (P, 2) sample positions covering the domain.
        size: Wanted cell pitch in mm at each sample.
        pixel_area: Area each sample represents, in mm².
        iterations: Lloyd relaxation steps.
        rng: Random generator for the initial seeds.

    Returns:
        (N, 2) seed positions in mm.
    """
    count = round(np.sum(pixel_area / (HEX_AREA * size**2)))
    count = min(max(count, 1), len(points))
    initial = size**-2.0
    seeds = points[rng.choice(len(points), size=count, replace=False, p=initial / initial.sum())]
    seeds = seeds + rng.uniform(-0.5, 0.5, seeds.shape) * np.sqrt(pixel_area)

    # In 2D a CVT with density rho has cell diameter ~ rho**-1/4, hence size**-4.
    rho = size**-4.0
    for _ in range(iterations):
        _, owner = cKDTree(seeds).query(points)
        weight = np.bincount(owner, rho, minlength=count)
        moved = weight > 0
        for axis in range(2):
            centroid = np.bincount(owner, rho * points[:, axis], minlength=count)
            seeds[moved, axis] = centroid[moved] / weight[moved]
    return np.asarray(seeds, dtype=float)


def _hex_cells(interior: BaseGeometry, field: np.ndarray, section: Section, p: KitParams, dither: bool) -> np.ndarray:
    centres, index = hex_grid(interior.bounds, p.pitch)
    keep = shapely.intersects_xy(interior.buffer(p.pitch / 2), centres[:, 0], centres[:, 1])
    centres, index = centres[keep], index[keep]
    t = sample(field, section, centres)
    if dither:
        solid = error_diffusion(tone_curve(t, p.perceptual), index)
        inset = np.where(solid, np.inf, p.wall / 2)
    else:
        f_min, f_max = hex_fraction_range(p.pitch, p)
        inset = hole_inset(p.pitch, solid_fraction(t, f_min, f_max, p))
    return _shrunk(hexagons(centres, p.pitch), inset)


def _shrunk(cells: np.ndarray, inset: np.ndarray) -> np.ndarray:
    """Cells shrunk by ``inset`` (inf = cell stays solid)."""
    open_cells = np.isfinite(inset)
    return np.asarray(shapely.buffer(cells[open_cells], -inset[open_cells], join_style="mitre"))


def _line_holes(interior: BaseGeometry, field: np.ndarray, section: Section, p: KitParams) -> np.ndarray:
    """Gaps between parallel (optionally wavy) lines whose width follows the tone."""
    angle = np.radians(p.line_angle)
    along = np.array([np.cos(angle), np.sin(angle)])
    across = np.array([-np.sin(angle), np.cos(angle)])
    u_lo, v_lo, u_hi, v_hi = interior.bounds
    corners = np.array([[u_lo, v_lo], [u_hi, v_lo], [u_hi, v_hi], [u_lo, v_hi]])
    s_lo, s_hi = (corners @ along).min() - p.pitch, (corners @ along).max() + p.pitch
    o_lo, o_hi = (corners @ across).min() - p.pitch, (corners @ across).max() + p.pitch

    s = np.arange(s_lo, s_hi, min(section.step, p.pitch / 4))
    wavelength = p.line_wavelength or 4 * p.pitch
    phase = 2 * np.pi * s / wavelength
    offset = p.line_wave * np.sin(phase)
    # Unit normal of the wavy centre line (tangent = along + offset' * across).
    slope = p.line_wave * 2 * np.pi / wavelength * np.cos(phase)
    normal = (across[None, :] - slope[:, None] * along[None, :]) / np.hypot(1, slope)[:, None]

    f_min = min(p.wall / p.pitch, 1.0)
    f_max = max(1.0 - HOLE_MARGIN * p.min_hole / p.pitch, f_min)
    lines = []
    for o in np.arange(o_lo, o_hi, p.pitch):
        centre = s[:, None] * along + (o + offset)[:, None] * across
        half = solid_fraction(sample(field, section, centre), f_min, f_max, p) * p.pitch / 2
        upper, lower = centre + half[:, None] * normal, centre - half[:, None] * normal
        lines.append(shapely.make_valid(shapely.Polygon(np.vstack([upper, lower[::-1]]))))
    gaps = interior.difference(shapely.union_all(lines))
    return np.array(shapely.get_parts(gaps))


def _voronoi_cells(
    interior: BaseGeometry, field: np.ndarray, section: Section, p: KitParams, rng: np.random.Generator
) -> np.ndarray | None:
    # Relax on a grid fine enough to resolve the smallest cells, not just the CT voxels.
    step = min(section.step, p.min_cell / 6)
    u_lo, v_lo, u_hi, v_hi = interior.bounds
    u, v = np.meshgrid(np.arange(u_lo, u_hi, step), np.arange(v_lo, v_hi, step), indexing="ij")
    inside = shapely.contains_xy(interior, u, v)
    if inside.sum() < 3:
        return None
    points = np.column_stack([u[inside], v[inside]])
    t = sample(field, section, points)
    size = p.max_cell + (p.min_cell - p.max_cell) * t

    seeds = relaxed_seeds(points, size, step**2, p.lloyd_iterations, rng)
    if len(seeds) < 2:
        return None
    diagram = shapely.voronoi_polygons(
        shapely.MultiPoint(seeds), extend_to=interior.envelope.buffer(p.max_cell), ordered=True
    )
    cells = np.asarray(shapely.get_parts(diagram))
    t_cell = sample(field, section, seeds)
    pitch = p.max_cell + (p.min_cell - p.max_cell) * t_cell
    f_min, f_max = hex_fraction_range(pitch, p)
    return _shrunk(cells, hole_inset(pitch, solid_fraction(p.wall_contrast * t_cell, f_min, f_max, p)))


def make_infill(
    outline: BaseGeometry, section: Section, tone: ToneMap, params: KitParams, rng: np.random.Generator
) -> BaseGeometry:
    """Cut the HU-modulated infill pattern into a plate outline.

    A solid band of ``params.perimeter`` is kept along every edge (including slots), and
    holes narrower than ``params.min_hole`` are dropped. The remaining solid is always one
    connected lattice.

    Args:
        outline: Plate outline (with slots) in its (u, v) frame.
        section: Plate section giving the HU.
        tone: HU -> tone curve, shared by all plates of a kit.
        params: Pattern settings (``infill``, ``pitch``, ``wall``, ``line_*``, ...).
        rng: Random generator (used by the voronoi mode).

    Returns:
        The outline minus the holes; unchanged for ``infill="none"`` or very small plates.
    """
    if params.infill == "none":
        return outline
    interior = outline.buffer(-params.perimeter, join_style="mitre")
    if interior.is_empty:
        return outline
    shapely.prepare(interior)
    field = tone_field(section, tone, params.tone_blur)

    if params.infill == "voronoi":
        holes = _voronoi_cells(interior, field, section, params, rng)
        if holes is None:
            return outline
    elif params.infill == "lines":
        holes = _line_holes(interior, field, section, params)
    else:
        holes = _hex_cells(interior, field, section, params, dither=params.infill == "dither")

    holes = shapely.intersection(holes, interior)
    # Morphological opening removes slivers too narrow to print.
    r = params.min_hole / 2
    holes = shapely.buffer(shapely.buffer(holes, -r, join_style="mitre"), r, join_style="mitre")
    holes = holes[~shapely.is_empty(holes)]
    if len(holes) == 0:
        return outline
    return outline.difference(shapely.union_all(holes))
